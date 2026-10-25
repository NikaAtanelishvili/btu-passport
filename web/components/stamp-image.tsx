// A category stamp by content hash; served publicly by GET /api/stamps/{sha256}.
// Shown at 72–96 px on skill cards and 40–64 px in lists (design).
import { cn } from "@/lib/utils";

export function StampImage({
  sha256,
  category,
  size = 48,
  className,
}: {
  sha256: string;
  category: string;
  size?: number;
  className?: string;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- small, immutable, same origin
    <img
      src={`/api/stamps/${sha256}`}
      alt={category}
      width={size}
      height={size}
      className={cn("shrink-0 object-contain", className)}
      style={{ width: size, height: size }}
    />
  );
}
