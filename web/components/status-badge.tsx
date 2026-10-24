// One fixed mapping of version status → badge variant and label (shared by admin pages).
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
