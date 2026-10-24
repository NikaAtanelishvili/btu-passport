"use client";

// FE-30: create / edit event form (Web App Design A6). Times are entered in local time and
// sent as UTC. While the window fields are untouched, changing the end time moves them to
// the suggested values (end − 15 min, end + 30 min).
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { LockIcon } from "lucide-react";
import { useEffect, useRef } from "react";
import { Controller, useForm } from "react-hook-form";

import { TextField } from "@/components/form-fields";
import { StampImage } from "@/components/stamp-image";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import {
  CLOSES_AFTER_END_MIN,
  type EventForm as EventFormValues,
  eventSchema,
  OPENS_BEFORE_END_MIN,
  shiftLocal,
} from "@/lib/events";
import { queryKeys } from "@/lib/query-keys";

export function useEventForm(defaultValues: EventFormValues) {
  return useForm<EventFormValues>({ resolver: zodResolver(eventSchema), defaultValues });
}

export function EventForm({
  form,
  title,
  description,
  skillLocked,
  submitLabel,
  pending,
  onSubmit,
  onCancel,
}: {
  form: ReturnType<typeof useEventForm>;
  title: string;
  description?: string;
  skillLocked?: boolean;
  submitLabel: string;
  pending: boolean;
  onSubmit: (values: EventFormValues) => void;
  onCancel: () => void;
}) {
  const skills = useQuery({
    queryKey: queryKeys.admin.skills,
    queryFn: async () => (await api.GET("/api/admin/skills")).data!,
  });

  // Follow changes of the end time only (not the loaded value), and only while the window
  // fields haven't been touched by hand. Shifted values are marked dirty so an edit saves them.
  const endsAt = form.watch("ends_at");
  const lastEnd = useRef(endsAt);
  const { getFieldState, setValue } = form;
  useEffect(() => {
    if (endsAt === lastEnd.current) return;
    lastEnd.current = endsAt;
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(endsAt)) return;
    if (!getFieldState("checkin_opens_at").isTouched) {
      setValue("checkin_opens_at", shiftLocal(endsAt, -OPENS_BEFORE_END_MIN), { shouldDirty: true });
    }
    if (!getFieldState("checkin_closes_at").isTouched) {
      setValue("checkin_closes_at", shiftLocal(endsAt, CLOSES_AFTER_END_MIN), { shouldDirty: true });
    }
  }, [endsAt, getFieldState, setValue]);

  const skillId = form.watch("skill_id");
  const skill = skills.data?.find((s) => s.skill_id === skillId);
  const desc = form.watch("description");

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate>
        <CardContent>
          <FieldGroup>
            <TextField form={form} name="name" label="Name" />
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
                    disabled={skillLocked}
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
                  {skillLocked && (
                    <FieldDescription className="flex items-center gap-1">
                      <LockIcon className="size-3" /> Locked: participants have checked in
                    </FieldDescription>
                  )}
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
              name="description"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="description">Description (optional)</FieldLabel>
                  <Textarea {...field} id="description" aria-invalid={fieldState.invalid} />
                  <FieldDescription>Shown to students on the check-in page. {desc.length}/500</FieldDescription>
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField form={form} name="starts_at" label="Starts" type="datetime-local" />
              <TextField form={form} name="ends_at" label="Ends" type="datetime-local" />
            </div>
            <TextField form={form} name="location" label="Location (optional)" />
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField form={form} name="checkin_opens_at" label="Check-in opens" type="datetime-local" />
              <TextField form={form} name="checkin_closes_at" label="Check-in closes" type="datetime-local" />
            </div>
            <p className="-mt-4 text-sm text-muted-foreground">
              Suggested: {OPENS_BEFORE_END_MIN} min before the end to {CLOSES_AFTER_END_MIN} min after it. Check-in opens and
              closes by itself at these times.
            </p>
          </FieldGroup>
        </CardContent>
        <CardFooter className="mt-6 gap-2">
          <Button type="submit" disabled={pending}>
            {submitLabel}
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
