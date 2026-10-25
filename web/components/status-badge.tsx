// One fixed mapping of version and event status → badge look and label: admin pages show
// the pipeline status, the student portal what it means for the student (FE-41).
// Status is always colour + icon + words: the soft tint with black text and an icon (tokens.md).
import {
  CheckIcon,
  CircleDotIcon,
  ClockIcon,
  FileClockIcon,
  HistoryIcon,
  LoaderIcon,
  TriangleAlertIcon,
  XIcon,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type Look = "valid" | "superseded" | "invalid" | "pending" | "legacy" | "navy";

const LOOKS: Record<Look, string> = {
  valid: "border-transparent bg-status-valid-soft text-black",
  superseded: "border-transparent bg-status-superseded-soft text-black",
  invalid: "border-transparent bg-status-invalid-soft text-black",
  pending: "border-transparent bg-muted text-black",
  legacy: "border-[1.5px] border-foreground bg-background text-black",
  navy: "border-transparent bg-navy-soft text-stamp-navy",
};

export function StatusPill({ look, icon: Icon, label, spin }: { look: Look; icon: LucideIcon; label: string; spin?: boolean }) {
  return (
    <Badge variant="outline" className={cn("h-6 gap-1.5 px-2.5 text-[0.8rem]", LOOKS[look])}>
      <Icon aria-hidden className={cn(spin && "animate-spin")} />
      {label}
    </Badge>
  );
}

const VERSION: Record<string, { look: Look; icon: LucideIcon; label: string }> = {
  LEGACY: { look: "legacy", icon: FileClockIcon, label: "Legacy" },
  PENDING: { look: "pending", icon: ClockIcon, label: "Pending" },
  RENDERED: { look: "pending", icon: ClockIcon, label: "Rendered" },
  ANCHORING: { look: "pending", icon: LoaderIcon, label: "Anchoring" },
  ANCHORED: { look: "valid", icon: CheckIcon, label: "Anchored" },
  FAILED: { look: "invalid", icon: XIcon, label: "Failed" },
};

export function StatusBadge({ status }: { status: string }) {
  const v = VERSION[status] ?? { look: "legacy", icon: CircleDotIcon, label: status };
  return <StatusPill look={v.look} icon={v.icon} label={v.label} spin={status === "ANCHORING"} />;
}

const EVENT: Record<string, { look: Look; icon: LucideIcon; label: string }> = {
  DRAFT: { look: "legacy", icon: CircleDotIcon, label: "Draft" },
  CHECKIN_OPEN: { look: "valid", icon: CircleDotIcon, label: "Check-in open" },
  CHECKIN_CLOSED: { look: "pending", icon: ClockIcon, label: "Check-in closed" },
  COMPLETED: { look: "navy", icon: CheckIcon, label: "Completed" },
};

export function EventStatusBadge({ status }: { status: string }) {
  const v = EVENT[status] ?? { look: "legacy", icon: CircleDotIcon, label: status };
  return <StatusPill look={v.look} icon={v.icon} label={v.label} />;
}

type StudentVersion = { status: string; superseded: boolean };

/** Current / Superseded / Legacy for the student; the pipeline steps are all "Issuing". */
export function StudentVersionBadge({ version }: { version: StudentVersion }) {
  if (version.status === "ANCHORED") {
    return version.superseded ? (
      <StatusPill look="superseded" icon={HistoryIcon} label="Superseded" />
    ) : (
      <StatusPill look="valid" icon={CheckIcon} label="Current" />
    );
  }
  if (version.status === "LEGACY") return <StatusPill look="legacy" icon={FileClockIcon} label="Legacy, not verifiable" />;
  if (version.status === "FAILED") return <StatusPill look="superseded" icon={TriangleAlertIcon} label="Delayed" />;
  return <StatusPill look="pending" icon={LoaderIcon} label="Issuing" spin />;
}

/** A version number pill, as in the design's student table ("● v1"); "—" when none. */
export function VersionPill({ versionNo }: { versionNo: number | null | undefined }) {
  if (!versionNo) return <span className="text-muted-foreground">—</span>;
  return (
    <Badge variant="outline" className="h-6 gap-1.5 border-transparent bg-violet-soft px-2.5 text-[0.8rem] text-black">
      <span className="size-2 rounded-full bg-stamp-violet" aria-hidden />v{versionNo}
    </Badge>
  );
}
