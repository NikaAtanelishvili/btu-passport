"use client";

// FE-30: create an event (super admin). It starts as Draft; check-in opens by itself at the
// window's start, or with "Open check-in now" on the event page.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { EventForm, useEventForm } from "@/components/event-form";
import { RequireRole } from "@/components/require-role";
import { api } from "@/lib/api";
import { CLOSES_AFTER_END_MIN, type EventForm as EventFormValues, OPENS_BEFORE_END_MIN, shiftLocal, toEventBody, toLocalInput } from "@/lib/events";
import { applyServerErrors } from "@/lib/forms";
import { queryKeys } from "@/lib/query-keys";

function defaults(): EventFormValues {
  // Next full hour, two hours long.
  const start = new Date();
  start.setHours(start.getHours() + 1, 0, 0, 0);
  const starts_at = toLocalInput(start.toISOString());
  const ends_at = shiftLocal(starts_at, 120);
  return {
    name: "",
    skill_id: "",
    description: "",
    location: "",
    starts_at,
    ends_at,
    checkin_opens_at: shiftLocal(ends_at, -OPENS_BEFORE_END_MIN),
    checkin_closes_at: shiftLocal(ends_at, CLOSES_AFTER_END_MIN),
  };
}

export default function NewEventPage() {
  return (
    <RequireRole role="super_admin">
      <NewEvent />
    </RequireRole>
  );
}

function NewEvent() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [initial] = useState(defaults);
  const form = useEventForm(initial);
  const create = useMutation({
    mutationFn: async (values: EventFormValues) =>
      (await api.POST("/api/admin/events", { body: toEventBody(values) })).data!,
    onSuccess: (event) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
      toast.success("Event created");
      router.push(`/admin/events/${event.event_id}`);
    },
    onError: (error) => applyServerErrors(form, error),
  });
  return (
    <EventForm
      form={form}
      title="Create event"
      description="Students who check in by QR receive the skill when you mark the event as done."
      submitLabel="Create event"
      pending={create.isPending}
      onSubmit={(values) => create.mutate(values)}
      onCancel={() => router.back()}
    />
  );
}
