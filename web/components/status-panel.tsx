// A result panel: a coloured band with an icon, one big word and a sentence, then a white
// body. Status is always colour + icon + words (tokens.md).
import { CheckIcon, ClockIcon, HistoryIcon, XIcon, type LucideIcon } from "lucide-react";

import { IconDisc } from "@/components/display";
import { cn } from "@/lib/utils";

export type Tone = "valid" | "superseded" | "invalid" | "expired";

const TONES: Record<Tone, { band: string; icon: LucideIcon; iconColor: string }> = {
  valid: { band: "bg-status-valid", icon: CheckIcon, iconColor: "text-status-valid" },
  superseded: { band: "bg-status-superseded", icon: HistoryIcon, iconColor: "text-status-superseded" },
  invalid: { band: "bg-status-invalid", icon: XIcon, iconColor: "text-status-invalid" },
  // An expired check-in code is a failure but not "not valid": coral with a clock.
  expired: { band: "bg-status-invalid", icon: ClockIcon, iconColor: "text-status-invalid" },
};

export function StatusPanel({
  tone,
  word,
  light,
  subtitle,
  aside,
  stacked = false,
  wordProps,
  className,
  children,
}: {
  tone: Tone;
  /** The big word: VALID, SUPERSEDED, NOT VALID, CHECKED IN … */
  word: string;
  /** A light second line under the word (check-in cards). */
  light?: string;
  subtitle?: React.ReactNode;
  /** Beside the text on wide screens, below it on phones (the Blockchain verified sticker). */
  aside?: React.ReactNode;
  /** Icon above the word at every width (the narrow check-in cards). */
  stacked?: boolean;
  wordProps?: React.HTMLAttributes<HTMLParagraphElement> & Record<`data-${string}`, string>;
  className?: string;
  children?: React.ReactNode;
}) {
  const t = TONES[tone];
  // Long words get a smaller size so they never run past the panel at 390 px.
  const fontSize = `min(8rem, ${Math.min(22, 150 / word.length).toFixed(1)}cqw)`;
  return (
    <section
      className={cn("overflow-hidden rounded-[28px] border-[1.5px] border-foreground bg-background", className)}
    >
      <div
        className={cn(
          "flex flex-col gap-5 px-6 py-7",
          !stacked && "sm:flex-row sm:items-center sm:gap-8 sm:px-12 sm:py-12",
          stacked && "sm:px-8",
          t.band,
        )}
      >
        <IconDisc icon={t.icon} className={cn(t.iconColor, stacked && "sm:size-20")} />
        <div className="@container min-w-0 flex-1 text-black">
          <p className="font-display font-black" style={{ fontSize }} {...wordProps}>
            {word}
          </p>
          {light && (
            <p className="font-display text-[clamp(1.25rem,7.5cqw,3.25rem)] font-extralight">{light}</p>
          )}
          {subtitle && <div className="mt-4 text-lg leading-snug font-semibold sm:text-2xl">{subtitle}</div>}
        </div>
        {aside}
      </div>
      {children && <div className={cn("px-6 py-7", stacked ? "sm:px-8 sm:py-8" : "sm:px-12 sm:py-10")}>{children}</div>}
    </section>
  );
}
