// FE-51: a quick look at a stamp file before upload, with the server's messages
// (backend/app/services/stamps.py). The server reads the bytes and checks again.
const MAX_BYTES = 1024 * 1024;
const PNG_MIN = 300; // longest side

export type StampFacts = { kind: "png" | "svg" | "other"; size: number; width?: number; height?: number };

// DEFAULT(FE-51): the size is checked for PNGs only, like the server; an SVG scales to any size.
export function stampProblem({ kind, size, width, height }: StampFacts): string | null {
  if (size > MAX_BYTES) return "The file is larger than 1 MB.";
  if (kind === "other") return "Upload a PNG or SVG image.";
  if (kind === "svg") return null;
  if (width === undefined || height === undefined) return "Upload a PNG or SVG image; this PNG can't be read.";
  if (Math.max(width, height) < PNG_MIN) {
    return `The PNG's longest side must be at least ${PNG_MIN} px; this one is ${width}x${height}.`;
  }
  return null;
}

export async function checkStampFile(file: File): Promise<string | null> {
  const name = file.name.toLowerCase();
  const kind =
    file.type === "image/png" || name.endsWith(".png")
      ? "png"
      : file.type === "image/svg+xml" || name.endsWith(".svg")
        ? "svg"
        : "other";
  if (kind !== "png" || file.size > MAX_BYTES) return stampProblem({ kind, size: file.size });
  try {
    const bitmap = await createImageBitmap(file);
    const facts = { kind, size: file.size, width: bitmap.width, height: bitmap.height } as const;
    bitmap.close();
    return stampProblem(facts);
  } catch {
    return stampProblem({ kind, size: file.size });
  }
}
