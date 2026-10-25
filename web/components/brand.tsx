// BTU brand pieces from web/public/brand, used as they are (never redrawn).
import Image from "next/image";

import { cn } from "@/lib/utils";

// btu-logo.png is a square canvas with the mark inside this box (fractions of the canvas),
// so the mark is shown by cropping the canvas rather than editing the file.
const LOGO_BOX = { left: 0.2102, top: 0.2807, width: 0.5794, height: 0.7014 };

/** The BTU mark, `height` px tall. `white` turns it white for pink or black panels. */
export function BtuLogo({ height, white = false, className }: { height: number; white?: boolean; className?: string }) {
  const canvas = height / LOGO_BOX.height;
  return (
    <span
      className={cn("relative block shrink-0 overflow-hidden", className)}
      style={{ height, width: Math.round(canvas * LOGO_BOX.width) }}
    >
      <Image
        src="/brand/btu-logo.png"
        alt="BTU"
        width={Math.round(canvas)}
        height={Math.round(canvas)}
        priority
        className={cn("absolute max-w-none", white && "brightness-0 invert")}
        style={{ left: -canvas * LOGO_BOX.left, top: -canvas * LOGO_BOX.top, width: canvas, height: canvas }}
      />
    </span>
  );
}

/** "AI SKILLS / DIGITAL PASSPORT" beside the mark, as in the header. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("font-display text-[1.25rem] leading-[0.95] sm:text-[1.375rem]", className)}>
      <span className="block font-black">AI Skills</span>
      <span className="block font-extralight">Digital Passport</span>
    </span>
  );
}

const STICKERS = {
  "blockchain-verified": { file: "sticker-blockchain-verified.png", alt: "Blockchain verified", w: 1051, h: 429 },
  "issued-by-btu": { file: "sticker-issued-by-btu.png", alt: "Issued by Business and Technology University", w: 1485, h: 429 },
  "intl-recognised": { file: "sticker-intl-recognised.png", alt: "Skills in AI, internationally recognised", w: 860, h: 860 },
  "ai-skills-digital-passport": { file: "sticker-ai-skills-digital-passport.png", alt: "AI Skills Digital Passport", w: 1251, h: 641 },
  "latest-skillset": { file: "sticker-latest-skillset.png", alt: "Latest AI skillset", w: 1498, h: 321 },
} as const;

// The stickers are flat PNGs on white; round and triangular ones are clipped to their shape
// so no white corners show on a coloured panel.
const CLIP: Partial<Record<keyof typeof STICKERS, string>> = {
  "intl-recognised": "circle(49.5% at 50% 50%)",
  "ai-skills-digital-passport": "polygon(50% 0, 100% 100%, 0 100%)",
};

/** A cover sticker, `width` px wide, optionally rotated (the design tilts them −4° to −8°). */
export function Sticker({
  name,
  width,
  rotate = 0,
  className,
}: {
  name: keyof typeof STICKERS;
  width: number;
  rotate?: number;
  className?: string;
}) {
  const s = STICKERS[name];
  return (
    <Image
      src={`/brand/${s.file}`}
      alt={s.alt}
      width={width}
      height={Math.round((width * s.h) / s.w)}
      className={cn("shrink-0", className)}
      style={{ transform: rotate ? `rotate(${rotate}deg)` : undefined, clipPath: CLIP[name] }}
    />
  );
}
