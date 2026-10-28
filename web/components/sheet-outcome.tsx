// SH-07: a Sheet record's outcome and a sync run's status as status pills (colour + icon + word),
// and a run's counts as one short line per tab.
import {
  CheckIcon,
  ClockIcon,
  CopyIcon,
  LoaderIcon,
  MinusIcon,
  TriangleAlertIcon,
  XIcon,
  type LucideIcon,
} from "lucide-react";

import { StatusPill, type Look } from "@/components/status-badge";

const OUTCOMES: Record<string, { look: Look; icon: LucideIcon; label: string }> = {
  PROCESSED: { look: "valid", icon: CheckIcon, label: "Processed" },
  CREATED: { look: "valid", icon: CheckIcon, label: "Created" },
  UPDATED: { look: "valid", icon: CheckIcon, label: "Updated" },
  UNCHANGED: { look: "legacy", icon: MinusIcon, label: "Unchanged" },
  DUPLICATE: { look: "legacy", icon: CopyIcon, label: "Duplicate" },
  WAITING: { look: "pending", icon: ClockIcon, label: "Waiting" },
  IGNORED: { look: "pending", icon: MinusIcon, label: "Ignored" },
  ERROR: { look: "invalid", icon: XIcon, label: "Error" },
  CHANGED_AFTER_PROCESSING: { look: "superseded", icon: TriangleAlertIcon, label: "Changed after processing" },
  REVOKED_IN_SHEET: { look: "superseded", icon: TriangleAlertIcon, label: "Rejected after processing" },
  CONFLICT: { look: "superseded", icon: TriangleAlertIcon, label: "Conflict" },
};

export const OUTCOME_LABELS: Record<string, string> = Object.fromEntries(
  Object.entries(OUTCOMES).map(([k, v]) => [k, v.label]),
);

export function OutcomeBadge({ outcome }: { outcome: string }) {
  const o = OUTCOMES[outcome] ?? { look: "legacy" as Look, icon: MinusIcon, label: outcome };
  return <StatusPill look={o.look} icon={o.icon} label={o.label} />;
}

const TAB_ORDER = ["Verified Skills", "Students", "Skills Catalog"];

/** {"Verified Skills": {"PROCESSED": 1, "DUPLICATE": 60}, …} → ["Verified Skills: 1 processed, 60 duplicate", …] */
export function countLines(counts: Record<string, unknown>): string[] {
  return TAB_ORDER.flatMap((tab) => {
    const byOutcome = counts[tab];
    if (!byOutcome || typeof byOutcome !== "object") return [];
    const parts = Object.entries(byOutcome as Record<string, number>)
      .sort(([, a], [, b]) => b - a)
      .map(([outcome, n]) => `${n} ${(OUTCOME_LABELS[outcome] ?? outcome).toLowerCase()}`);
    return parts.length ? [`${tab}: ${parts.join(", ")}`] : [];
  });
}

const RUN: Record<string, { look: Look; icon: LucideIcon; label: string }> = {
  QUEUED: { look: "pending", icon: ClockIcon, label: "Queued" },
  RUNNING: { look: "pending", icon: LoaderIcon, label: "Running" },
  DONE: { look: "valid", icon: CheckIcon, label: "Done" },
  FAILED: { look: "invalid", icon: XIcon, label: "Failed" },
};

export function RunStatusBadge({ status }: { status: string }) {
  const r = RUN[status] ?? { look: "legacy" as Look, icon: MinusIcon, label: status };
  return <StatusPill look={r.look} icon={r.icon} label={r.label} spin={status === "RUNNING"} />;
}
