"use client";

// FE-31: event detail (Web App Design A7). Participants poll every 3 s while check-in is
// open (15 s otherwise). Every action is for super admins; admins see the page read-only.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { DataTable } from "@/components/data-table";
import { ErrorAlert } from "@/components/error-alert";
import { StampImage } from "@/components/stamp-image";
import { EventStatusBadge } from "@/components/status-badge";
import { type PickedStudent, StudentPicker } from "@/components/student-picker";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { BLOCKER_TEXT } from "@/lib/events";
import { formatDate, formatDateTime } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";
import { hasRole, useSession } from "@/lib/session";

type EventDetail = components["schemas"]["EventDetail"];
type Participant = components["schemas"]["Participant"];

/** The event's date in BTU's timezone (the date earned of its awards, as on the server). */
function eventDate(startsAt: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tbilisi" }).format(new Date(startsAt));
}

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const session = useSession();
  const canEdit = session.data ? hasRole(session.data, "super_admin") : false;
  const event = useQuery({
    queryKey: queryKeys.admin.event(id),
    queryFn: async () => (await api.GET("/api/admin/events/{event_id}", { params: { path: { event_id: id } } })).data!,
    refetchInterval: (q) => (q.state.data?.status === "CHECKIN_OPEN" ? 3_000 : 15_000),
  });
  const participants = useQuery({
    queryKey: queryKeys.admin.participants(id),
    queryFn: async () =>
      (await api.GET("/api/admin/events/{event_id}/participants", { params: { path: { event_id: id } } })).data!,
    refetchInterval: event.data?.status === "CHECKIN_OPEN" ? 3_000 : 15_000,
  });

  if (event.isError) return <ErrorAlert error={event.error} />;
  if (!event.data) return <Skeleton className="h-96 w-full" />;
  const e = event.data;
  const readOnly = !canEdit || e.status === "COMPLETED";

  return (
    <div className="space-y-6">
      <Header event={e} canEdit={canEdit} />
      <CheckinCard event={e} readOnly={readOnly} />
      <ParticipantsCard event={e} rows={participants.data} loading={participants.isPending} readOnly={readOnly} />
      {e.status === "COMPLETED" ? <CompletionCard event={e} /> : <CompleteCard event={e} rows={participants.data ?? []} readOnly={readOnly} />}
      {!readOnly && <DangerZone event={e} />}
    </div>
  );
}

function useEventAction() {
  const queryClient = useQueryClient();
  return (eventId: string) => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.event(eventId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.participants(eventId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
  };
}

function Header({ event: e, canEdit }: { event: EventDetail; canEdit: boolean }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold">{e.name}</h1>
          <EventStatusBadge status={e.status} />
        </div>
        <div className="flex items-center gap-3 text-sm">
          {e.skill.stamp_sha256 && <StampImage sha256={e.skill.stamp_sha256} category={e.skill.category} />}
          <div>
            <p>{e.skill.name}</p>
            <p className="text-muted-foreground">
              {formatDateTime(e.starts_at)} – {formatDateTime(e.ends_at)}
              {e.location ? ` · ${e.location}` : ""}
            </p>
          </div>
        </div>
        {e.description && <p className="max-w-prose text-sm text-muted-foreground">{e.description}</p>}
      </div>
      {canEdit && e.status !== "COMPLETED" && (
        <Link href={`/admin/events/${e.event_id}/edit`} className={buttonVariants({ variant: "outline" })}>
          Edit
        </Link>
      )}
    </div>
  );
}

function CheckinCard({ event: e, readOnly }: { event: EventDetail; readOnly: boolean }) {
  const refresh = useEventAction();
  const action = useMutation({
    mutationFn: async (kind: "open" | "close" | "reopen") => {
      const path = { event_id: e.event_id };
      if (kind === "open") return (await api.POST("/api/admin/events/{event_id}/open", { params: { path } })).data!;
      if (kind === "close") return (await api.POST("/api/admin/events/{event_id}/close", { params: { path } })).data!;
      return (await api.POST("/api/admin/events/{event_id}/reopen", { params: { path } })).data!;
    },
    onSuccess: () => refresh(e.event_id),
    onError: (error) => toast.error(error.message),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Check-in</CardTitle>
        <CardDescription>
          Window: {formatDateTime(e.checkin_opens_at)} – {formatDateTime(e.checkin_closes_at)}. Check-in opens and closes by
          itself at these times.
        </CardDescription>
      </CardHeader>
      {!readOnly && (
        <CardContent className="flex flex-wrap gap-2">
          {e.status === "DRAFT" && (
            <Button disabled={action.isPending} onClick={() => action.mutate("open")}>
              Open check-in now
            </Button>
          )}
          {e.status === "CHECKIN_OPEN" && (
            <Button variant="outline" disabled={action.isPending} onClick={() => action.mutate("close")}>
              Close check-in now
            </Button>
          )}
          {e.status === "CHECKIN_CLOSED" && (
            <Button variant="outline" disabled={action.isPending} onClick={() => action.mutate("reopen")}>
              Reopen check-in
            </Button>
          )}
          <a
            href={`/admin/events/${e.event_id}/present`}
            target="_blank"
            rel="noopener"
            className={buttonVariants({ variant: "outline" })}
          >
            Open presenter view
          </a>
        </CardContent>
      )}
    </Card>
  );
}

function ParticipantsCard({
  event: e,
  rows,
  loading,
  readOnly,
}: {
  event: EventDetail;
  rows: Participant[] | undefined;
  loading: boolean;
  readOnly: boolean;
}) {
  const refresh = useEventAction();
  const [picked, setPicked] = useState<PickedStudent[]>([]);
  const add = useMutation({
    mutationFn: async (studentId: string) =>
      (
        await api.POST("/api/admin/events/{event_id}/participants", {
          params: { path: { event_id: e.event_id } },
          body: { student_id: studentId },
        })
      ).data!,
    onSuccess: (p) => {
      toast.success(`Added ${p.name}`);
      refresh(e.event_id);
    },
    onError: (error) => toast.error(error.message),
    onSettled: () => setPicked([]),
  });
  const remove = useMutation({
    mutationFn: async (email: string) =>
      api.DELETE("/api/admin/events/{event_id}/participants/{email}", {
        params: { path: { event_id: e.event_id, email } },
      }),
    onSuccess: () => refresh(e.event_id),
    onError: (error) => toast.error(error.message),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Participants ({e.counts.total})</CardTitle>
        <CardDescription>
          {e.counts.unregistered > 0 && `${e.counts.unregistered} Unregistered · `}
          {e.counts.already_held} already hold the skill
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!readOnly && (
          <div className="max-w-md">
            <Label className="mb-2">Add participant</Label>
            <StudentPicker
              value={picked}
              onChange={(next) => {
                const added = next.find((s) => !picked.some((p) => p.student_id === s.student_id));
                setPicked(next);
                if (added) add.mutate(added.student_id);
              }}
            />
          </div>
        )}
        <DataTable<Participant>
          rows={rows}
          loading={loading}
          rowKey={(p) => p.email}
          empty="Nobody has checked in yet."
          columns={[
            { header: "Name", cell: (p) => <span title={p.email}>{p.name}</span> },
            {
              header: "Student ID",
              cell: (p) =>
                p.student_id ? (
                  <Link href={`/admin/students/${p.student_id}`} className="underline-offset-4 hover:underline">
                    {p.student_id}
                  </Link>
                ) : (
                  p.email
                ),
            },
            { header: "Checked in", cell: (p) => formatDateTime(p.checked_in_at) },
            { header: "Method", cell: (p) => (p.method === "QR" ? "QR" : "Manual") },
            {
              header: "Flags",
              cell: (p) => (
                <div className="flex gap-1">
                  {p.flags.includes("UNREGISTERED") && <Badge variant="destructive">Unregistered</Badge>}
                  {p.flags.includes("ALREADY_HOLDS") && <Badge variant="secondary">Already holds skill</Badge>}
                </div>
              ),
            },
            {
              header: "",
              cell: (p) =>
                readOnly ? null : (
                  <div className="flex justify-end gap-2">
                    {p.flags.includes("UNREGISTERED") && (
                      <a
                        href={`/admin/students/new?email=${encodeURIComponent(p.email)}`}
                        target="_blank"
                        rel="noopener"
                        className={buttonVariants({ variant: "outline", size: "sm" })}
                      >
                        Register student
                      </a>
                    )}
                    <ConfirmDialog
                      trigger={<Button variant="ghost" size="sm" />}
                      title={`Remove ${p.name}?`}
                      description="They won't receive the skill. They can be added again later."
                      confirmLabel="Remove"
                      onConfirm={() => remove.mutate(p.email)}
                    >
                      Remove
                    </ConfirmDialog>
                  </div>
                ),
            },
          ]}
        />
      </CardContent>
    </Card>
  );
}

function CompleteCard({ event: e, rows, readOnly }: { event: EventDetail; rows: Participant[]; readOnly: boolean }) {
  const refresh = useEventAction();
  const [checked, setChecked] = useState(false);
  const sent = useRef(false);
  const receive = rows.filter((p) => p.student_id && !p.flags.includes("ALREADY_HOLDS"));
  const skipped = rows.filter((p) => p.flags.includes("ALREADY_HOLDS"));
  const complete = useMutation({
    mutationFn: async () =>
      (await api.POST("/api/admin/events/{event_id}/complete", { params: { path: { event_id: e.event_id } } })).data!,
    onSuccess: (out) => {
      toast.success(`Marked as done: ${out.awarded.length} awarded, ${out.skipped.length} skipped`);
      refresh(e.event_id);
    },
    onError: (error) => {
      sent.current = false;
      toast.error(error.message);
    },
  });
  function confirm() {
    if (sent.current) return; // a second click before the re-render; the server is idempotent too
    sent.current = true;
    complete.mutate();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Mark as done</CardTitle>
        <CardDescription>
          Awards the skill to every participant who doesn&apos;t hold it yet, dated {formatDate(eventDate(e.starts_at))}. The
          event is read-only afterwards.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {e.complete_blockers.length > 0 && (
          <ul className="list-disc pl-5 text-sm text-muted-foreground">
            {e.complete_blockers.map((b) => (
              <li key={b}>{b === "UNREGISTERED_PRESENT" ? `${BLOCKER_TEXT[b]} (${e.counts.unregistered})` : BLOCKER_TEXT[b]}</li>
            ))}
          </ul>
        )}
        {!readOnly && (
          <AlertDialog onOpenChange={() => setChecked(false)}>
            <AlertDialogTrigger render={<Button />} disabled={!e.can_complete || complete.isPending}>
              Mark as done
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Mark {e.name} as done?</AlertDialogTitle>
                <AlertDialogDescription>
                  {receive.length} student{receive.length === 1 ? "" : "s"} will receive {e.skill.name}, dated{" "}
                  {formatDate(eventDate(e.starts_at))}.{" "}
                  {skipped.length === 1 && "1 already holds it and will be skipped."}
                  {skipped.length > 1 && `${skipped.length} already hold it and will be skipped.`}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <div className="max-h-64 space-y-3 overflow-y-auto text-sm">
                <div>
                  <p className="font-medium">Will receive the skill</p>
                  <ul className="text-muted-foreground">
                    {receive.map((p) => (
                      <li key={p.email}>
                        {p.name} · {p.student_id}
                      </li>
                    ))}
                  </ul>
                </div>
                {skipped.length > 0 && (
                  <div>
                    <p className="font-medium">Skipped: already hold the skill</p>
                    <ul className="text-muted-foreground">
                      {skipped.map((p) => (
                        <li key={p.email}>
                          {p.name} · {p.student_id}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              <Label className="flex items-center gap-2">
                <Checkbox checked={checked} onCheckedChange={(v) => setChecked(v === true)} />I checked the participant list
              </Label>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogCancel variant="default" disabled={!checked} onClick={confirm}>
                  Confirm
                </AlertDialogCancel>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </CardContent>
    </Card>
  );
}

function CompletionCard({ event: e }: { event: EventDetail }) {
  const c = e.completion;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Completed</CardTitle>
        <CardDescription>
          {e.completed_at && `Marked as done ${formatDateTime(e.completed_at)}. `}
          New passport versions go through issuance:{" "}
          <Link href="/admin/issuance?tab=in-progress" className="underline underline-offset-4">
            see the Issuance page
          </Link>
          .
        </CardDescription>
      </CardHeader>
      {c && (
        <CardContent className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <p className="font-medium">Awarded ({c.awarded.length})</p>
            <ul>
              {c.awarded.map((a) => (
                <li key={a.student_id}>
                  <Link href={`/admin/students/${a.student_id}`} className="underline-offset-4 hover:underline">
                    {a.student_id}
                  </Link>{" "}
                  · new version v{a.version_no}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="font-medium">Skipped: already held the skill ({c.skipped.length})</p>
            <ul>
              {c.skipped.map((s) => (
                <li key={s}>
                  <Link href={`/admin/students/${s}`} className="underline-offset-4 hover:underline">
                    {s}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

function DangerZone({ event: e }: { event: EventDetail }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const del = useMutation({
    mutationFn: async () => api.DELETE("/api/admin/events/{event_id}", { params: { path: { event_id: e.event_id } } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
      toast.success("Event deleted");
      router.push("/admin/events");
    },
    onError: (error) => toast.error(error.message),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Danger zone</CardTitle>
        <CardDescription>
          Deleting hides the event and its check-ins; students see &ldquo;Event deleted&rdquo;. Completed events can&apos;t be
          deleted.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ConfirmDialog
          trigger={<Button variant="destructive" />}
          title={`Delete ${e.name}?`}
          description={`Its ${e.counts.total} check-in(s) won't lead to any award.`}
          confirmLabel="Delete event"
          onConfirm={() => del.mutate()}
          disabled={del.isPending}
        >
          Delete event
        </ConfirmDialog>
      </CardContent>
    </Card>
  );
}
