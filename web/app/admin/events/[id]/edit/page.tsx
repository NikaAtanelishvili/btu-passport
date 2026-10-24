"use client";

// FE-30: edit an event (super admin). The skill is locked once someone has checked in
// (409 skill_locked shows under the field); completed events can't be edited.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { ErrorAlert } from "@/components/error-alert";
import { EventForm, useEventForm } from "@/components/event-form";
import { RequireRole } from "@/components/require-role";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { type EventForm as EventFormValues, toEventBody, toLocalInput } from "@/lib/events";
import { applyServerErrors } from "@/lib/forms";
import { queryKeys } from "@/lib/query-keys";

type EventDetail = components["schemas"]["EventDetail"];

export default function EditEventPage() {
  const { id } = useParams<{ id: string }>();
  const event = useQuery({
    queryKey: queryKeys.admin.event(id),
    queryFn: async () => (await api.GET("/api/admin/events/{event_id}", { params: { path: { event_id: id } } })).data!,
  });
  return (
    <RequireRole role="super_admin">
      {event.isError ? (
        <ErrorAlert error={event.error} />
      ) : !event.data ? (
        <Skeleton className="h-96 w-full max-w-2xl" />
      ) : event.data.status === "COMPLETED" ? (
        <Alert>
          <AlertTitle>A completed event is read-only</AlertTitle>
        </Alert>
      ) : (
        <EditEvent event={event.data} />
      )}
    </RequireRole>
  );
}

function values(e: EventDetail): EventFormValues {
  return {
    name: e.name,
    skill_id: e.skill_id,
    description: e.description ?? "",
    location: e.location ?? "",
    starts_at: toLocalInput(e.starts_at),
    ends_at: toLocalInput(e.ends_at),
    checkin_opens_at: toLocalInput(e.checkin_opens_at),
    checkin_closes_at: toLocalInput(e.checkin_closes_at),
  };
}

function EditEvent({ event }: { event: EventDetail }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const form = useEventForm(values(event));
  const save = useMutation({
    mutationFn: async (v: EventFormValues) => {
      const body = toEventBody(v);
      const dirty = Object.fromEntries(
        Object.entries(body).filter(([k]) => form.formState.dirtyFields[k as keyof EventFormValues]),
      );
      return (
        await api.PATCH("/api/admin/events/{event_id}", { params: { path: { event_id: event.event_id } }, body: dirty })
      ).data!;
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.admin.event(event.event_id), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
      toast.success("Event saved");
      router.push(`/admin/events/${event.event_id}`);
    },
    onError: (error) => applyServerErrors(form, error),
  });
  return (
    <EventForm
      form={form}
      title="Edit event"
      skillLocked={event.skill_locked}
      submitLabel="Save changes"
      pending={save.isPending}
      onSubmit={(v) => save.mutate(v)}
      onCancel={() => router.back()}
    />
  );
}
