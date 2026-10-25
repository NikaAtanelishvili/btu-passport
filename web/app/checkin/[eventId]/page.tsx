"use client";

// FE-33: check-in from the presenter QR (Web App Design P3), made for phones. One card per
// state from the API. Signed out: the QR token (30-60 s) is checked right away and swapped for
// a check-in pass (10 min, one use) that the API keeps in an HttpOnly cookie for this event; the
// sign-in link carries no token or pass. Back here in the same browser, the API reports
// `from_pass` and the page checks in by itself, so nobody has to scan twice.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { CalendarIcon, ClockIcon, InfoIcon, MapPinIcon } from "lucide-react";

import { DisplayHeading } from "@/components/display";
import { ErrorAlert } from "@/components/error-alert";
import { StampImage } from "@/components/stamp-image";
import { StatusPanel, type Tone } from "@/components/status-panel";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatEventWhen, formatTime, splitTitle } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";
import { hasRole, signOut, useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

type CheckinView = components["schemas"]["CheckinView"];
type State = CheckinView["state"];

export default function CheckinPage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-64 w-full max-w-[34rem] rounded-[28px]" />}>
      <Checkin />
    </Suspense>
  );
}

function Checkin() {
  const { eventId } = useParams<{ eventId: string }>();
  const params = useSearchParams();
  const t = params.get("t") ?? "";
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
    enabled: signedOut && t !== "",
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  // With a pass (or nothing to scan) sign in and come back to the bare URL: no token, no pass.
  const toSignIn = signedOut && (pass.isSuccess || t === "");
  useEffect(() => {
    if (toSignIn) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [toSignIn, router, pathname]);

  const view = useQuery({
    queryKey: queryKeys.checkin(eventId, t),
    queryFn: async () =>
      (await api.GET("/api/checkin/{event_id}", { params: { path: { event_id: eventId }, query: { t } } })).data!,
    enabled: session.data?.authenticated === true,
    refetchOnWindowFocus: false,
  });
  const checkIn = useMutation({
    mutationFn: async () =>
      (await api.POST("/api/checkin/{event_id}", { params: { path: { event_id: eventId } }, body: { t } })).data!,
    onSuccess: (result) => {
      queryClient.setQueryData<CheckinView>(queryKeys.checkin(eventId, t), (old) =>
        old ? { ...old, ...result, state: "CHECKED_IN" } : old,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.me.events });
    },
    onError: (error) => {
      const state = error instanceof ApiError ? (error.body.state as State | undefined) : undefined;
      if (state) setPostState(state);
    },
  });

  // Back from sign-in with this browser's pass: the scan already said "check me in".
  const { mutate } = checkIn;
  const autoSent = useRef(false);
  const fromPass = view.data?.state === "CONFIRM" && view.data.from_pass;
  useEffect(() => {
    if (fromPass && !autoSent.current) {
      autoSent.current = true;
      mutate();
    }
  }, [fromPass, mutate]);

  if (signedOut && pass.isError) {
    // No pass (expired code, check-in not open, …): say so now, before any sign-in.
    const state = pass.error instanceof ApiError ? (pass.error.body.state as State | undefined) : undefined;
    return (
      <div className="mx-auto w-full max-w-[34rem] space-y-6">
        {state && MESSAGES[state] ? <MessageCard state={state} /> : <ErrorAlert error={pass.error} />}
      </div>
    );
  }
  if (session.isPending || signedOut || (view.isPending && !view.isError)) {
    return <Skeleton className="mx-auto h-64 w-full max-w-[34rem] rounded-[28px]" />;
  }
  if (view.isError) return <ErrorAlert error={view.error} />;
  const v = view.data;
  const state = postState ?? v.state;
  const isStudent = session.data ? hasRole(session.data, "student") : false;

  return (
    <div className="mx-auto w-full max-w-[34rem] space-y-6">
      <StateCard
        state={state}
        view={v}
        email={session.data?.user?.email ?? undefined}
        isStudent={isStudent}
        pending={checkIn.isPending}
        error={checkIn.isError && !postState ? checkIn.error : null}
        onCheckIn={() => checkIn.mutate()}
      />
    </div>
  );
}

function EventHeading({ view }: { view: CheckinView }) {
  const e = view.event!;
  const [strong, light] = splitTitle(e.name);
  return (
    <div className="space-y-5">
      <p className="eyebrow text-sm text-link sm:text-base">Event check-in</p>
      <DisplayHeading strong={strong} light={light} className="text-[clamp(2.5rem,7vw,4.5rem)]" />
      <ul className="space-y-1.5 text-lg sm:text-xl">
        <li className="flex items-center gap-3">
          <CalendarIcon className="size-5 shrink-0" aria-hidden /> {formatEventWhen(e.starts_at, e.ends_at)}
        </li>
        {e.location && (
          <li className="flex items-center gap-3">
            <MapPinIcon className="size-5 shrink-0" aria-hidden /> {e.location}
          </li>
        )}
      </ul>
      {e.description && <p className="text-lg text-muted-foreground">{e.description}</p>}
    </div>
  );
}

/** The skill (or, after check-in, the event) beside its stamp. */
function SkillCard({ view, lead, eventLine = false }: { view: CheckinView; lead?: string; eventLine?: boolean }) {
  const e = view.event!;
  return (
    <div className="flex items-center gap-4 rounded-[24px] border p-4 sm:gap-5 sm:p-6 [&_img]:size-16 sm:[&_img]:size-20">
      {e.skill.stamp_sha256 && <StampImage sha256={e.skill.stamp_sha256} category={e.skill.category} size={80} />}
      <div className="min-w-0">
        {lead && <p className="text-muted-foreground sm:text-lg">{lead}</p>}
        <p className="font-display text-xl leading-tight font-extrabold sm:text-[1.75rem]">
          {eventLine ? e.name : e.skill.name}
        </p>
        <p className="text-muted-foreground sm:text-lg">{eventLine ? formatEventWhen(e.starts_at, e.ends_at) : e.skill.category}</p>
      </div>
    </div>
  );
}

const BIG_BUTTON = "h-16! w-full rounded-[20px]! font-display text-2xl! font-black uppercase sm:h-20! sm:text-4xl!";

const MESSAGES: Partial<Record<State, { tone: Tone; word: string; light: string; text: string }>> = {
  TOKEN_EXPIRED: {
    tone: "expired",
    word: "Code expired",
    light: "You're not checked in",
    text: "This QR code is no longer valid. Scan the code on the screen again to check in.",
  },
  NOT_OPEN: {
    tone: "expired",
    word: "Not open yet",
    light: "Check-in hasn't opened",
    text: "Try again when the organiser opens check-in.",
  },
  CLOSED: {
    tone: "expired",
    word: "Closed",
    light: "Check-in has closed",
    text: "Talk to the organiser if you attended.",
  },
  REMOVED: {
    tone: "invalid",
    word: "Removed",
    light: "You're not on the list",
    text: "The organiser removed your check-in. Please talk to them.",
  },
  NOT_FOUND: {
    tone: "invalid",
    word: "Not found",
    light: "No such event",
    text: "The link may be wrong, or the event was deleted.",
  },
};

function StateCard({
  state,
  view,
  email,
  isStudent,
  pending,
  error,
  onCheckIn,
}: {
  state: State;
  view: CheckinView;
  email?: string;
  isStudent: boolean;
  pending: boolean;
  error: Error | null;
  onCheckIn: () => void;
}) {
  if (state === "CONFIRM") {
    return (
      <>
        <EventHeading view={view} />
        <SkillCard view={view} lead="You'll earn" />
        {view.already_holds_skill && (
          <Alert>
            <InfoIcon />
            <AlertDescription>You already have this skill; your passport won&apos;t change.</AlertDescription>
          </Alert>
        )}
        <Button className={BIG_BUTTON} disabled={pending} onClick={onCheckIn}>
          Check in
        </Button>
        {error && <ErrorAlert error={error} />}
        {email && (
          <div className="space-y-1 text-center text-lg text-muted-foreground">
            <p>
              Signed in as <span className="font-medium text-foreground">{email}</span>
            </p>
            <p>
              Not you?{" "}
              <button
                type="button"
                className="font-medium text-link underline underline-offset-4"
                onClick={() => void signOut()}
              >
                Sign out
              </button>
            </p>
          </div>
        )}
        <p className="flex items-center justify-center gap-2 text-muted-foreground">
          <ClockIcon className="size-4" aria-hidden /> Check-in closes at {formatTime(view.event!.checkin_closes_at)}
        </p>
      </>
    );
  }
  if (state === "CHECKED_IN") {
    return (
      <>
        <StatusPanel stacked tone="valid" word="Checked in" light="You're on the list">
          <div className="space-y-2 text-lg">
            <p>
              You&apos;ll receive <strong>{view.event!.skill.name}</strong> when BTU marks the event as done.
            </p>
            {view.unregistered && (
              <p>Your account isn&apos;t in BTU&apos;s student records yet; the organiser will add you.</p>
            )}
            {view.already_holds_skill && <p>You already have this skill; your passport won&apos;t change.</p>}
          </div>
        </StatusPanel>
        <SkillCard view={view} eventLine />
        {isStudent && <MyEventsButton />}
      </>
    );
  }
  return <MessageCard state={state} showMyEvents={isStudent} />;
}

function MyEventsButton() {
  return (
    <Link href="/me/events" className={cn(buttonVariants({ variant: "outline" }), BIG_BUTTON, "text-xl! sm:text-2xl!")}>
      See my events
    </Link>
  );
}

function MessageCard({ state, showMyEvents = false }: { state: State; showMyEvents?: boolean }) {
  const m = MESSAGES[state]!;
  return (
    <>
      <StatusPanel stacked tone={m.tone} word={m.word} light={m.light}>
        <p className="text-lg">{m.text}</p>
      </StatusPanel>
      {state === "TOKEN_EXPIRED" && (
        <p className="text-muted-foreground">If check-in has already closed, ask the event organiser to add you.</p>
      )}
      {showMyEvents && <MyEventsButton />}
    </>
  );
}
