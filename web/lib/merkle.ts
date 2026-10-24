// BC-06: browser-side Merkle proof checks, same format as backend/app/services/merkle.py
// (sorted-pair keccak256, double-hashed leaves). Values are "0x" + 64 lowercase hex.
// No tree building here: the browser only checks proofs it is given.
import { keccak_256 } from "@noble/hashes/sha3.js";
import { bytesToHex, concatBytes, hexToBytes } from "@noble/hashes/utils.js";

export type Hex32 = `0x${string}`;

function toBytes(value: string): Uint8Array {
  const raw = value.startsWith("0x") || value.startsWith("0X") ? value.slice(2) : value;
  if (!/^[0-9a-fA-F]{64}$/.test(raw)) {
    throw new Error(`expected 32 bytes of hex, got ${JSON.stringify(value)}`);
  }
  return hexToBytes(raw);
}

function toHex(value: Uint8Array): Hex32 {
  return `0x${bytesToHex(value)}`;
}

function compare(a: Uint8Array, b: Uint8Array): number {
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return 0;
}

function pair(a: Uint8Array, b: Uint8Array): Uint8Array {
  return compare(a, b) < 0 ? keccak_256(concatBytes(a, b)) : keccak_256(concatBytes(b, a));
}

/** keccak256(keccak256(pdfSha256)), the PDF hash taken as 32 raw bytes. */
export function leafFromPdfSha256(pdfSha256: string): Hex32 {
  return toHex(keccak_256(keccak_256(toBytes(pdfSha256))));
}

export function hashPair(a: string, b: string): Hex32 {
  return toHex(pair(toBytes(a), toBytes(b)));
}

/** Folds hashPair over the proof starting from the leaf; equals the root if valid. */
export function processProof(leaf: string, proof: readonly string[]): Hex32 {
  let node = toBytes(leaf);
  for (const sibling of proof) node = pair(node, toBytes(sibling));
  return toHex(node);
}

/** SHA-256 of a file, computed locally; only this hash ever leaves the device. */
export async function sha256File(file: Blob): Promise<Hex32> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return toHex(new Uint8Array(digest));
}
