// An informational note in the design's dashed box (legacy skills, a version on its way).
import { InfoIcon, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export function Notice({
  icon: Icon = InfoIcon,
  spin = false,
  className,
  children,
}: {
  icon?: LucideIcon;
  spin?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-3 rounded-2xl border-[1.5px] border-dashed border-foreground px-5 py-4 text-base sm:text-lg",
        className,
      )}
    >
      <Icon className={cn("mt-1 size-5 shrink-0", spin && "animate-spin")} aria-hidden />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
