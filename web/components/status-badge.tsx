// One fixed mapping of version and event status → badge variant and label: admin pages show
// the pipeline status, the student portal what it means for the student (FE-41).
import { Badge } from "@/components/ui/badge";

type Variant = "default" | "secondary" | "destructive" | "outline";

const VERSION: Record<string, { variant: Variant; label: string }> = {
  LEGACY: { variant: "outline", label: "Legacy" },
  PENDING: { variant: "secondary", label: "Pending" },
  RENDERED: { variant: "secondary", label: "Rendered" },
  ANCHORING: { variant: "secondary", label: "Anchoring" },
  ANCHORED: { variant: "default", label: "Anchored" },
  FAILED: { variant: "destructive", label: "Failed" },
};

export function StatusBadge({ status }: { status: string }) {
  const { variant, label } = VERSION[status] ?? { variant: "outline", label: status };
  return <Badge variant={variant}>{label}</Badge>;
}

const EVENT: Record<string, { variant: Variant; label: string }> = {
  DRAFT: { variant: "outline", label: "Draft" },
  CHECKIN_OPEN: { variant: "default", label: "Check-in open" },
  CHECKIN_CLOSED: { variant: "secondary", label: "Check-in closed" },
  COMPLETED: { variant: "secondary", label: "Completed" },
};

export function EventStatusBadge({ status }: { status: string }) {
  const { variant, label } = EVENT[status] ?? { variant: "outline", label: status };
  return <Badge variant={variant}>{label}</Badge>;
}

type StudentVersion = { status: string; superseded: boolean };

/** Current / Superseded / Legacy for the student; the pipeline steps are all "Issuing". */
export function StudentVersionBadge({ version }: { version: StudentVersion }) {
  const { variant, label } =
    version.status === "ANCHORED"
      ? version.superseded
        ? { variant: "secondary" as const, label: "Superseded" }
        : { variant: "default" as const, label: "Current" }
      : version.status === "LEGACY"
        ? { variant: "outline" as const, label: "Legacy, not verifiable" }
        : version.status === "FAILED"
          ? { variant: "outline" as const, label: "Delayed" }
          : { variant: "secondary" as const, label: "Issuing" };
  return <Badge variant={variant}>{label}</Badge>;
}
