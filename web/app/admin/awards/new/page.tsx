"use client";

// FE-24: direct award (Web App Design A4), two steps on one page. The Idempotency-Key is made
// once when the review step opens, so a double click or a resent request reuses it and the
// server creates the award only once (A3).
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ErrorAlert } from "@/components/error-alert";
import { StampImage } from "@/components/stamp-image";
import { type PickedStudent, StudentPicker } from "@/components/student-picker";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDate, todayInTbilisi } from "@/lib/format";
import { applyServerErrors } from "@/lib/forms";
import { queryKeys } from "@/lib/query-keys";

type PreviewRow = components["schemas"]["PreviewRow"];
const REASON_MAX = 300;

// Mirrors backend/app/services/issuance.py; the server checks again (A9).
const awardSchema = z.object({
  students: z.array(z.object({ student_id: z.string(), name: z.string() })).min(1, "Choose at least one student"),
  skill_id: z.string().min(1, "Choose a skill"),
  date_earned: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Enter the date earned")
    .refine((d) => d <= todayInTbilisi(), "Date earned can't be in the future."),
  reason: z.string().trim().min(1, "Give a reason").max(REASON_MAX, `At most ${REASON_MAX} characters`),
});
type AwardForm = z.infer<typeof awardSchema>;
type Review = { body: components["schemas"]["AwardIn"]; rows: PreviewRow[]; key: string };

export default function DirectAwardPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <DirectAward />
    </Suspense>
  );
}

function toBody(values: AwardForm): components["schemas"]["AwardIn"] {
  return {
    student_ids: values.students.map((s) => s.student_id),
    skill_id: values.skill_id,
    date_earned: values.date_earned,
    reason: values.reason.trim(),
  };
}

function DirectAward() {
  const preselect = useSearchParams().get("student");
  const [review, setReview] = useState<Review | null>(null);
  const form = useForm<AwardForm>({
    resolver: zodResolver(awardSchema),
    defaultValues: { students: [], skill_id: "", date_earned: todayInTbilisi(), reason: "" },
  });

  // ?student= pre-fills the picker (Student detail → Direct award).
  const { getValues, setValue } = form;
  useEffect(() => {
    if (!preselect) return;
    void api
      .GET("/api/admin/students/{student_id}", { params: { path: { student_id: preselect } } })
      .then(({ data }) => {
        if (data && getValues("students").length === 0) {
          const name = `${data.profile.first_name} ${data.profile.last_name}`;
          setValue("students", [{ student_id: data.profile.student_id, name }]);
        }
      })
      .catch(() => undefined);
  }, [preselect, getValues, setValue]);

  const preview = useMutation({
    mutationFn: async (body: components["schemas"]["AwardIn"]) =>
      (await api.POST("/api/admin/awards/preview", { body })).data!,
    onSuccess: (data, body) => {
      // Nothing to issue: say why under the field instead of a review with Confirm disabled.
      if (data.rows.every((r) => r.result === "SKIP_ALREADY_HELD")) {
        const message =
          data.rows.length === 1
            ? `${data.rows[0].name} already holds this skill.`
            : "All selected students already hold this skill.";
        form.setError("students", { message }, { shouldFocus: true });
        return;
      }
      setReview({ body, rows: data.rows, key: crypto.randomUUID() });
    },
    onError: (error) => applyServerErrors(form, serverFieldsToForm(error)),
  });

  return review ? (
    <ReviewStep review={review} onBack={() => setReview(null)} />
  ) : (
    <AwardFormCard form={form} onSubmit={(values) => preview.mutate(toBody(values))} pending={preview.isPending} />
  );
}

/** The API names the students field `student_ids`; the form calls it `students`. */
function serverFieldsToForm(error: unknown): unknown {
  if (error && typeof error === "object" && "fields" in error) {
    const e = error as { fields: Record<string, string> };
    if (e.fields.student_ids) {
      e.fields.students = e.fields.student_ids;
      delete e.fields.student_ids;
    }
  }
  return error;
}

function AwardFormCard({
  form,
  onSubmit,
  pending,
}: {
  form: ReturnType<typeof useForm<AwardForm>>;
  onSubmit: (values: AwardForm) => void;
  pending: boolean;
}) {
  const skills = useQuery({
    queryKey: queryKeys.admin.skills,
    queryFn: async () => (await api.GET("/api/admin/skills")).data!,
  });
  const skillId = form.watch("skill_id");
  const reason = form.watch("reason");
  const skill = skills.data?.find((s) => s.skill_id === skillId);

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Direct award</CardTitle>
        <CardDescription>For skills earned outside an event. You review the result before anything is issued.</CardDescription>
      </CardHeader>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate>
        <CardContent>
          {skills.isError && <ErrorAlert error={skills.error} />}
          <FieldGroup>
            <Controller
              name="students"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="students">Students</FieldLabel>
                  <StudentPicker
                    id="students"
                    value={field.value as PickedStudent[]}
                    onChange={field.onChange}
                    invalid={fieldState.invalid}
                  />
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
            <Controller
              name="skill_id"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="skill_id">Skill</FieldLabel>
                  <Select
                    value={field.value || null}
                    onValueChange={(v) => field.onChange(v ?? "")}
                    items={Object.fromEntries((skills.data ?? []).map((s) => [s.skill_id, s.name]))}
                  >
                    <SelectTrigger id="skill_id" aria-invalid={fieldState.invalid} className="w-full">
                      <SelectValue placeholder="Choose a skill" />
                    </SelectTrigger>
                    <SelectContent>
                      {(skills.data ?? []).map((s) => (
                        <SelectItem key={s.skill_id} value={s.skill_id}>
                          {s.name}
                          <span className="text-muted-foreground">{s.category.name}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {skill && (
                    <div className="flex items-start gap-3 text-sm">
                      {skill.category.stamp_sha256 && (
                        <StampImage sha256={skill.category.stamp_sha256} category={skill.category.name} />
                      )}
                      <p className="text-muted-foreground">{skill.description}</p>
                    </div>
                  )}
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
            <Controller
              name="date_earned"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="date_earned">Date earned</FieldLabel>
                  <Input
                    {...field}
                    id="date_earned"
                    type="date"
                    max={todayInTbilisi()}
                    aria-invalid={fieldState.invalid}
                    className="w-48"
                  />
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
            <Controller
              name="reason"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="reason">Reason</FieldLabel>
                  <Textarea
                    {...field}
                    id="reason"
                    placeholder="Course completion, Correction, …"
                    aria-invalid={fieldState.invalid}
                  />
                  <FieldDescription>
                    Goes to the audit log. {reason.length}/{REASON_MAX}
                  </FieldDescription>
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
          </FieldGroup>
        </CardContent>
        <CardFooter className="mt-6">
          <Button type="submit" disabled={pending}>
            Review
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

function ReviewStep({ review, onBack }: { review: Review; onBack: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const sent = useRef(false);
  const submit = useMutation({
    mutationFn: async () =>
      (await api.POST("/api/admin/awards", { body: review.body, params: { header: { "Idempotency-Key": review.key } } }))
        .data!,
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
      const n = data.versions.length;
      toast.success(n ? `Issuing ${n} new passport version${n === 1 ? "" : "s"}` : "Nothing to issue: all already hold the skill");
      router.push("/admin/issuance?tab=in-progress");
    },
    onError: (error) => {
      sent.current = false; // the same key may be sent again; the server replays or retries
      toast.error(error.message);
    },
  });
  const newCount = review.rows.filter((r) => r.result === "NEW_VERSION").length;
  const held = review.rows.filter((r) => r.result === "SKIP_ALREADY_HELD");

  function confirm() {
    if (sent.current) return; // a second click before the first re-render
    sent.current = true;
    submit.mutate();
  }

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Review</CardTitle>
        <CardDescription>
          Date earned {formatDate(review.body.date_earned)} · Reason: {review.body.reason}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {held.length > 0 && (
          <Alert>
            <AlertDescription>
              {held.length === 1
                ? `${held[0].name} already holds this skill and will be skipped.`
                : `${held.length} students already hold this skill and will be skipped.`}
            </AlertDescription>
          </Alert>
        )}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Student</TableHead>
              <TableHead>Student ID</TableHead>
              <TableHead>Result</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {review.rows.map((r) => (
              <TableRow key={r.student_id} className={r.result === "SKIP_ALREADY_HELD" ? "text-muted-foreground" : undefined}>
                <TableCell>{r.name}</TableCell>
                <TableCell>{r.student_id}</TableCell>
                <TableCell>
                  {r.result === "SKIP_ALREADY_HELD"
                    ? "already holds this skill"
                    : r.from_version
                      ? `v${r.from_version} → v${r.to_version}`
                      : `first version (v${r.to_version})`}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <CardFooter className="mt-6 gap-2">
        <Button onClick={confirm} disabled={submit.isPending || newCount === 0}>
          Confirm and issue
        </Button>
        <Button variant="ghost" onClick={onBack} disabled={submit.isPending}>
          Back
        </Button>
      </CardFooter>
    </Card>
  );
}
