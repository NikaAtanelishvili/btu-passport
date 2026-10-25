"use client";

// FE-33: check-in from the presenter QR (Web App Design P3), made for phones. One card per
// state from the API. Signed out: the QR token (30-60 s) is checked right away and swapped for
// a check-in pass (10 min, one use) that comes back here as ?p= after sign-in; the page then
// checks in by itself, so nobody has to scan twice.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { ErrorAlert } from "@/components/error-alert";
import { StampImage } from "@/components/stamp-image";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDateTime } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";
import { hasRole, useSession } from "@/lib/session";

type CheckinView = components["schemas"]["CheckinView"];
type State = CheckinView["state"];

export default function CheckinPage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-64 w-full max-w-md" />}>
      <Checkin />
    </Suspense>
  );
}

function Checkin() {
  const { eventId } = useParams<{ eventId: string }>();
  const params = useSearchParams();
  const t = params.get("t") ?? "";
  const p = params.get("p") ?? "";
  const pathname = usePathname();
  const router = useRouter();
  const session = useSession();
  const queryClient = useQueryClient();
  const signedOut = session.isSuccess && !session.data.authenticated;
  // A failed POST (e.g. the token ran out while the page was open) shows its state's card.
  const [postState, setPostState] = useState<State | null>(null);

  const pass = useQuery({
    queryKey: queryKeys.checkinPass(eventId, t),
    queryFn: async () =>
      (await api.POST("/api/checkin/{event_id}/pass", { params: { path: { event_id: eventId } }, body: { t } })).data!,
    enabled: signedOut && !p,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  const passToken = p || pass.data?.pass;
  useEffect(() => {
    if (signedOut && passToken) {
      router.replace(`/login?next=${encodeURIComponent(`${pathname}?p=${encodeURIComponent(passToken)}`)}`);
    }
  }, [signedOut, passToken, router, pathname]);

  const view = useQuery({
    queryKey: queryKeys.checkin(eventId, t, p),
    queryFn: async () =>
      (await api.GET("/api/checkin/{event_id}", { params: { path: { event_id: eventId }, query: { t, p } } }))
        .data!,
    enabled: session.data?.authenticated === true,
    refetchOnWindowFocus: false,
  });
  const checkIn = useMutation({
    mutationFn: async () =>
      (await api.POST("/api/checkin/{event_id}", { params: { path: { event_id: eventId } }, body: { t, p } })).data!,
    onSuccess: (result) => {
      queryClient.setQueryData<CheckinView>(queryKeys.checkin(eventId, t, p), (old) =>
        old ? { ...old, ...result, state: "CHECKED_IN" } : old,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.me.events });
    },
    onError: (error) => {
      const state = error instanceof ApiError ? (error.body.state as State | undefined) : undefined;
      if (state) setPostState(state);
    },
  });

  // Back from sign-in with a pass: the scan already said "check me in".
  const { mutate } = checkIn;
  const autoSent = useRef(false);
  useEffect(() => {
    if (p && view.data?.state === "CONFIRM" && !autoSent.current) {
      autoSent.current = true;
      mutate();
    }
  }, [p, view.data?.state, mutate]);

  if (signedOut && pass.isError) {
    // No pass (expired code, check-in not open, …): say so now, before any sign-in.
    const state = pass.error instanceof ApiError ? (pass.error.body.state as State | undefined) : undefined;
    return (
      <div className="mx-auto w-full max-w-md">
        {state && MESSAGES[state] ? <MessageCard state={state} /> : <ErrorAlert error={pass.error} />}
      </div>
    );
  }
  if (session.isPending || signedOut || (view.isPending && !view.isError)) {
    return <Skeleton className="mx-auto h-64 w-full max-w-md" />;
  }
  if (view.isError) return <ErrorAlert error={view.error} />;
  const v = view.data;
  const state = postState ?? v.state;
  const isStudent = session.data ? hasRole(session.data, "student") : false;

  return (
    <div className="mx-auto w-full max-w-md space-y-4">
      {v.event && <EventCard view={v} />}
      <StateCard
        state={state}
        view={v}
        isStudent={isStudent}
        pending={checkIn.isPending}
        error={checkIn.isError && !postState ? checkIn.error : null}
        onCheckIn={() => checkIn.mutate()}
      />
    </div>
  );
}

function EventCard({ view }: { view: CheckinView }) {
  const e = view.event!;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">{e.name}</CardTitle>
        <CardDescription>
          {formatDateTime(e.starts_at)}
          {e.location ? ` · ${e.location}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          {e.skill.stamp_sha256 && <StampImage sha256={e.skill.stamp_sha256} category={e.skill.category} />}
          <div>
            <p className="font-medium">{e.skill.name}</p>
            <p className="text-sm text-muted-foreground">{e.skill.category}</p>
          </div>
        </div>
        {e.description && <p className="text-sm text-muted-foreground">{e.description}</p>}
      </CardContent>
    </Card>
  );
}

const MESSAGES: Partial<Record<State, { title: string; text: string }>> = {
  TOKEN_EXPIRED: { title: "This code has expired", text: "Scan the code on the screen again." },
  NOT_OPEN: { title: "Check-in hasn't opened yet", text: "Try again when the organiser opens check-in." },
  CLOSED: { title: "Check-in has closed", text: "Talk to the organiser if you attended." },
  REMOVED: { title: "The organiser removed your check-in", text: "Please talk to them." },
  NOT_FOUND: { title: "Event not found", text: "The link may be wrong, or the event was deleted." },
};

function StateCard({
  state,
  view,
  isStudent,
  pending,
  error,
  onCheckIn,
}: {
  state: State;
  view: CheckinView;
  isStudent: boolean;
  pending: boolean;
  error: Error | null;
  onCheckIn: () => void;
}) {
  if (state === "CONFIRM") {
    return (
      <Card>
        <CardContent className="space-y-3 pt-6">
          {view.already_holds_skill && (
            <Alert>
              <AlertDescription>You already have this skill; your passport won&apos;t change.</AlertDescription>
            </Alert>
          )}
          <Button size="lg" className="h-14 w-full text-lg" disabled={pending} onClick={onCheckIn}>
            Check in
          </Button>
          {error && <ErrorAlert error={error} />}
        </CardContent>
      </Card>
    );
  }
  if (state === "CHECKED_IN") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>You&apos;re checked in</CardTitle>
          <CardDescription>
            The skill will appear on your passport once the organiser completes the event.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {view.unregistered && (
            <p>Your account isn&apos;t in BTU&apos;s student records yet; the organiser will add you.</p>
          )}
          {view.already_holds_skill && <p>You already have this skill; your passport won&apos;t change.</p>}
        </CardContent>
        {isStudent && (
          <CardFooter>
            <Link href="/me/events" className={buttonVariants({ variant: "outline" })}>
              My events
            </Link>
          </CardFooter>
        )}
      </Card>
    );
  }
  return <MessageCard state={state} />;
}

function MessageCard({ state }: { state: State }) {
  const m = MESSAGES[state]!;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{m.title}</CardTitle>
        <CardDescription>{m.text}</CardDescription>
      </CardHeader>
    </Card>
  );
}
