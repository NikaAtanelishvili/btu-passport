// Event form rules and helpers shared by the event pages (FE-30 - FE-32). Rules mirror
// backend/app/services/events.py; the server checks them again.
import { z } from "zod";

import type { components } from "@/lib/api-types";

export type EventStatus = components["schemas"]["EventDetail"]["status"];
export type Blocker = components["schemas"]["EventDetail"]["complete_blockers"][number];

export const EVENT_STATUS_LABELS: Record<EventStatus, string> = {
  DRAFT: "Draft",
  CHECKIN_OPEN: "Check-in open",
  CHECKIN_CLOSED: "Check-in closed",
  COMPLETED: "Completed",
};

export const BLOCKER_TEXT: Record<Blocker, string> = {
  DRAFT: "Check-in hasn't been opened yet",
  CHECKIN_OPEN: "Close check-in first",
  UNREGISTERED_PRESENT: "Register or remove the Unregistered participants",
  NO_PARTICIPANTS: "Nobody has checked in",
};

// DEFAULT(Q17): check-in opens 15 min before the end and closes 30 min after it.
export const OPENS_BEFORE_END_MIN = 15;
export const CLOSES_AFTER_END_MIN = 30;

/** ISO instant -> 'YYYY-MM-DDTHH:mm' in the browser's local time (datetime-local input). */
export function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** datetime-local value (local time) -> UTC ISO string for the API. */
export function fromLocalInput(value: string): string {
  return new Date(value).toISOString();
}

/** A datetime-local value shifted by some minutes, still as a datetime-local value. */
export function shiftLocal(value: string, minutes: number): string {
  return toLocalInput(new Date(new Date(value).getTime() + minutes * 60_000).toISOString());
}

const localDateTime = z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/, "Enter a date and time");

export const eventSchema = z
  .object({
    name: z.string().trim().min(1, "Required").max(120, "At most 120 characters"),
    skill_id: z.string().min(1, "Choose a skill"),
    description: z.string().max(500, "At most 500 characters"),
    location: z.string(),
    starts_at: localDateTime,
    ends_at: localDateTime,
    checkin_opens_at: localDateTime,
    checkin_closes_at: localDateTime,
  })
  .refine((v) => new Date(v.ends_at) > new Date(v.starts_at), {
    path: ["ends_at"],
    message: "The end must be after the start",
  })
  .refine((v) => new Date(v.checkin_closes_at) > new Date(v.checkin_opens_at), {
    path: ["checkin_closes_at"],
    message: "Check-in must close after it opens",
  });

export type EventForm = z.infer<typeof eventSchema>;

export function toEventBody(v: EventForm): components["schemas"]["EventCreate"] {
  return {
    name: v.name.trim(),
    skill_id: v.skill_id,
    description: v.description.trim() || null,
    location: v.location.trim() || null,
    starts_at: fromLocalInput(v.starts_at),
    ends_at: fromLocalInput(v.ends_at),
    checkin_opens_at: fromLocalInput(v.checkin_opens_at),
    checkin_closes_at: fromLocalInput(v.checkin_closes_at),
  };
}
