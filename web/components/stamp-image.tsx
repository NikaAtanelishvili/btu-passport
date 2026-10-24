// A category stamp by content hash; served publicly by GET /api/stamps/{sha256}.
export function StampImage({ sha256, category }: { sha256: string; category: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- small, immutable, same origin
    <img src={`/api/stamps/${sha256}`} alt={category} width={48} height={48} className="size-12" />
  );
}
