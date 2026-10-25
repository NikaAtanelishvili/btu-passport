// Display type from the design: Outfit 900 paired with 200, uppercase, tight leading.
import { AsteriskIcon, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

const SIZES = {
  hero: "text-[clamp(2.75rem,8vw,7rem)]",
  page: "text-[clamp(2.25rem,5vw,4rem)]",
  card: "text-[clamp(1.5rem,2.6vw,2rem)]",
} as const;

/** A heading with a heavy first part and an optional light second line ("VERIFY / A PASSPORT"). */
export function DisplayHeading({
  strong,
  light,
  size = "page",
  inline = false,
  as: Tag = "h1",
  className,
}: {
  strong: React.ReactNode;
  light?: React.ReactNode;
  size?: keyof typeof SIZES;
  /** Light part on the same line (card titles) instead of below. */
  inline?: boolean;
  as?: "h1" | "h2" | "h3" | "p";
  className?: string;
}) {
  return (
    <Tag className={cn("font-display uppercase", SIZES[size], className, "leading-[0.92]")}>
      <span className={cn("font-black", !inline && "block")}>{strong}</span>
      {light && (
        <>
          {inline && " "}
          <span className={cn("font-extralight", !inline && "block")}>{light}</span>
        </>
      )}
    </Tag>
  );
}

/** The three orange asterisks beside hero headings. Decorative. */
export function Asterisks({ className }: { className?: string }) {
  return (
    <span className={cn("flex flex-col text-stamp-orange", className)} aria-hidden>
      {[0, 1, 2].map((i) => (
        <AsteriskIcon key={i} className="-my-1 size-[1em]" strokeWidth={4} />
      ))}
    </span>
  );
}

/** A small uppercase label above a value ("HOLDER", "PASSPORT ID"). */
export function Eyebrow({ className, children }: { className?: string; children: React.ReactNode }) {
  return <p className={cn("eyebrow text-muted-foreground", className)}>{children}</p>;
}

/** An icon in a black circle, used by the status panels and check-in cards. */
export function IconDisc({ icon: Icon, className }: { icon: LucideIcon; className?: string }) {
  return (
    <span className={cn("grid size-16 shrink-0 place-items-center rounded-full bg-black sm:size-24", className)}>
      <Icon className="size-8 sm:size-12" strokeWidth={3} aria-hidden />
    </span>
  );
}
