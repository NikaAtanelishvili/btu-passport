"use client";

// FE-23: student detail (Web App Design A3): profile edit, passport versions, skills, events.
// Names printed on an issued passport stay as printed; editing them only changes the record
// and future versions (FR-11).
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LockIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { DisplayHeading } from "@/components/display";
import { DataTable } from "@/components/data-table";
import { ErrorAlert } from "@/components/error-alert";
import { SelectField, TextField } from "@/components/form-fields";
import { ProgramField } from "@/components/program-field";
import { StampImage } from "@/components/stamp-image";
import { StatusBadge, VersionPill } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { FieldGroup } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDate, formatDateTime } from "@/lib/format";
import { applyServerErrors } from "@/lib/forms";
import { queryKeys } from "@/lib/query-keys";
import { EDUCATION_LEVELS, type ProfileForm, profileSchema, STUDENT_STATUSES } from "@/lib/students";

type StudentDetail = components["schemas"]["StudentDetail"];
type VersionRow = components["schemas"]["VersionRow"];
type AwardRow = components["schemas"]["AwardRow"];
type ParticipationRow = components["schemas"]["ParticipationRow"];

const FROZEN_NOTE = "Printed on issued passports; changing them needs a reissue decision.";

export default function StudentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const student = useQuery({
    queryKey: queryKeys.admin.student(id),
    queryFn: async () =>
      (await api.GET("/api/admin/students/{student_id}", { params: { path: { student_id: id } } })).data!,
    // Poll while a version is on its way to ANCHORED.
    refetchInterval: (query) =>
      query.state.data?.passport.versions.some((v) => ["PENDING", "RENDERED", "ANCHORING"].includes(v.status))
        ? 5_000
        : false,
  });

  if (student.isError) return <ErrorAlert error={student.error} />;
  if (!student.data) return <Skeleton className="h-96 w-full" />;
  const d = student.data;
  const p = d.profile;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <DisplayHeading strong={p.first_name} light={p.last_name} />
          <p className="mt-3 font-mono text-muted-foreground">
            {p.student_id} · {d.passport.passport_id}
          </p>
        </div>
        <Link href={`/admin/awards/new?student=${p.student_id}`} className={buttonVariants()}>
          Direct award
        </Link>
      </div>
      <ProfileCard detail={d} />
      <PassportCard detail={d} />
      <SkillsCard awards={d.awards} />
      <EventsCard events={d.events} />
    </div>
  );
}

function profileValues(p: StudentDetail["profile"]): ProfileForm {
  return {
    first_name: p.first_name,
    last_name: p.last_name,
    email: p.email,
    program: p.program,
    education_level: p.education_level as ProfileForm["education_level"],
    status: p.status as ProfileForm["status"],
  };
}

function ProfileCard({ detail }: { detail: StudentDetail }) {
  const queryClient = useQueryClient();
  const { profile, passport } = detail;
  const form = useForm<ProfileForm>({ resolver: zodResolver(profileSchema), defaultValues: profileValues(profile) });
  const { reset } = form;
  useEffect(() => reset(profileValues(profile)), [profile, reset]);

  const save = useMutation({
    mutationFn: async (body: ProfileForm) => {
      const dirty = Object.fromEntries(
        Object.entries(body).filter(([k]) => form.formState.dirtyFields[k as keyof ProfileForm]),
      );
      const { data } = await api.PATCH("/api/admin/students/{student_id}", {
        params: { path: { student_id: profile.student_id } },
        body: dirty,
      });
      return data!;
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.admin.student(profile.student_id), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.students() });
      toast.success("Profile saved");
    },
    onError: (error) => applyServerErrors(form, error),
  });

  const nameDiffers =
    passport.frozen &&
    (passport.holder_first_name !== profile.first_name || passport.holder_last_name !== profile.last_name);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
      </CardHeader>
      <form onSubmit={form.handleSubmit((body) => save.mutate(body))} noValidate>
        <CardContent className="space-y-4">
          {nameDiffers && (
            <Alert>
              <AlertTitle>The name differs from the issued passport</AlertTitle>
              <AlertDescription>
                Issued versions show {passport.holder_first_name} {passport.holder_last_name}. The passport keeps the
                printed name; deciding on a reissue is outside this page.
              </AlertDescription>
            </Alert>
          )}
          <dl className="grid gap-3 text-sm sm:grid-cols-3">
            <Locked label="Student ID" value={profile.student_id} note="Never changes." />
            <Locked label="Passport ID" value={passport.passport_id} note={FROZEN_NOTE} />
            <Locked
              label="First issued"
              value={passport.first_issued_on ? formatDate(passport.first_issued_on) : "Not issued yet"}
              note={FROZEN_NOTE}
            />
          </dl>
          <FieldGroup>
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField form={form} name="first_name" label="First name" />
              <TextField form={form} name="last_name" label="Last name" />
            </div>
            {passport.frozen && (
              <p className="-mt-4 flex items-center gap-1 text-sm text-muted-foreground">
                <LockIcon className="size-3" /> Names: {FROZEN_NOTE}
              </p>
            )}
            <TextField form={form} name="email" label="BTU email" type="email" />
            <ProgramField form={form} name="program" />
            <div className="grid gap-4 sm:grid-cols-2">
              <SelectField form={form} name="education_level" label="Education level" items={EDUCATION_LEVELS} />
              <SelectField form={form} name="status" label="Status" items={STUDENT_STATUSES} />
            </div>
          </FieldGroup>
        </CardContent>
        <CardFooter className="mt-6 gap-2">
          <Button type="submit" disabled={!form.formState.isDirty || save.isPending}>
            Save changes
          </Button>
          {form.formState.isDirty && (
            <Button type="button" variant="ghost" onClick={() => reset(profileValues(profile))}>
              Discard
            </Button>
          )}
        </CardFooter>
      </form>
    </Card>
  );
}

function Locked({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div>
      <dt className="flex items-center gap-1 text-muted-foreground" title={note}>
        <LockIcon className="size-3" aria-label="Locked" /> {label}
      </dt>
      <dd>{value}</dd>
    </div>
  );
}

function PassportCard({ detail }: { detail: StudentDetail }) {
  const queryClient = useQueryClient();
  const retry = useMutation({
    mutationFn: async (versionId: number) =>
      (await api.POST("/api/admin/versions/{version_id}/retry", { params: { path: { version_id: versionId } } }))
        .data!,
    onSuccess: (v) => {
      toast.success(`Retrying v${v.version_no}`);
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
    },
    onError: (error) => toast.error(error.message),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Passport</CardTitle>
        <CardDescription>Only anchored versions can be downloaded or verified.</CardDescription>
      </CardHeader>
      <CardContent>
        <DataTable<VersionRow>
          rows={detail.passport.versions}
          rowKey={(v) => v.version_id}
          empty="No versions yet. The first is issued with the student's first skill."
          columns={[
            { header: "Version", cell: (v) => <VersionPill versionNo={v.version_no} /> },
            { header: "Status", cell: (v) => <StatusBadge status={v.status} /> },
            { header: "Issued", cell: (v) => (v.issued_at ? formatDateTime(v.issued_at) : "–") },
            { header: "Error", cell: (v) => v.error ?? "", className: "max-w-xs whitespace-normal" },
            {
              header: "",
              cell: (v) =>
                v.status === "ANCHORED" ? (
                  <a href={`/api/admin/versions/${v.version_id}/pdf`} className={buttonVariants({ variant: "outline", size: "sm" })}>
                    Download
                  </a>
                ) : v.status === "FAILED" ? (
                  <Button size="sm" variant="outline" disabled={retry.isPending} onClick={() => retry.mutate(v.version_id)}>
                    Retry
                  </Button>
                ) : null,
            },
          ]}
        />
      </CardContent>
    </Card>
  );
}

function source(a: AwardRow): string {
  if (a.source === "EVENT") return `Event: ${a.event_name ?? "deleted event"}`;
  if (a.source === "SEED") return `Imported${a.legacy_record_id ? ` (${a.legacy_record_id})` : ""}`;
  return `Direct award${a.reason ? `: ${a.reason}` : ""}`;
}

function SkillsCard({ awards }: { awards: AwardRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Skills</CardTitle>
      </CardHeader>
      <CardContent>
        <DataTable<AwardRow>
          rows={awards}
          rowKey={(a) => a.award_id}
          empty="No skills yet."
          columns={[
            {
              header: "Skill",
              cell: (a) => (
                <div className="flex items-center gap-2">
                  {a.stamp_sha256 && <StampImage sha256={a.stamp_sha256} category={a.category} />}
                  <div>
                    <p>{a.skill_name}</p>
                    <p className="text-xs text-muted-foreground">{a.category}</p>
                  </div>
                </div>
              ),
            },
            { header: "Date earned", cell: (a) => formatDate(a.date_earned) },
            { header: "Source", cell: source, className: "max-w-xs whitespace-normal" },
            { header: "Awarded by", cell: (a) => a.awarded_by ?? "–" },
          ]}
        />
      </CardContent>
    </Card>
  );
}

function EventsCard({ events }: { events: ParticipationRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Events</CardTitle>
      </CardHeader>
      <CardContent>
        <DataTable<ParticipationRow>
          rows={events}
          rowKey={(e) => e.event_id}
          empty="No check-ins yet."
          columns={[
            { header: "Event", cell: (e) => e.event_name },
            { header: "Date", cell: (e) => formatDate(e.starts_at) },
            { header: "Checked in", cell: (e) => `${formatDateTime(e.checked_in_at)} (${e.method === "QR" ? "QR" : "added"})` },
            {
              header: "Status",
              cell: (e) =>
                e.event_deleted
                  ? "Event deleted"
                  : e.removed
                    ? "Removed by organiser"
                    : e.event_status === "COMPLETED"
                      ? "Completed"
                      : "Waiting for organiser",
            },
          ]}
        />
      </CardContent>
    </Card>
  );
}
