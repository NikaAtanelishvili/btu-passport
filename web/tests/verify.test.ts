// FE-12: the browser's own check against the chain, and FE-10's upload path (only the hash
// is ever sent).
import { createHash } from "node:crypto";

import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api";
import { hashPair, leafFromPdfSha256 } from "@/lib/merkle";
import {
  type ChainReader,
  type IssuerFile,
  type ProofFile,
  chainOnlyInput,
  independentCheck,
  lookupFile,
  readProofFile,
} from "@/lib/verify";

const CONTRACT = "0x5FbDB2315678afecb367f032d93F642f64180aa3";
const BTU = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";
const OTHER = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8";
const issuer: IssuerFile = {
  issuer_name: "Business and Technology University",
  chain_id: 31337,
  contract_address: CONTRACT,
  issuer_address: BTU,
};

const sha = (text: string) => `0x${createHash("sha256").update(text).digest("hex")}`;
const pdfSha256 = sha("the issued pdf");
const sibling = leafFromPdfSha256(sha("another passport in the batch"));
const root = hashPair(leafFromPdfSha256(pdfSha256), sibling);

function chain(overrides: Partial<ChainReader> = {}): ChainReader {
  return {
    chainId: async () => 31337,
    owner: async () => BTU,
    anchoredAt: async (_c, r) => (r === root ? BigInt(1_700_000_000) : BigInt(0)),
    revoked: async () => false,
    ...overrides,
  };
}

const input = {
  pdfSha256,
  proof: [sibling],
  merkleRoot: root,
  chainId: 31337,
  contractAddress: CONTRACT,
};

describe("independentCheck", () => {
  it("confirms an anchored document on BTU's registry", async () => {
    const result = await independentCheck(input, {
      chain: chain(),
      fetchIssuer: async () => issuer,
    });
    expect(result).toEqual({
      unreachable: false,
      documentOk: true,
      issuerOk: true,
      revoked: false,
      issuerSource: "file",
    });
  });

  it("uses the locally computed hash: an edited file fails the document check", async () => {
    const result = await independentCheck(
      { ...input, pdfSha256: sha("the issued pdf, edited") },
      { chain: chain(), fetchIssuer: async () => issuer },
    );
    expect(result).toMatchObject({ documentOk: false, issuerOk: true });
  });

  it("fails the issuer check when the issuer file names another owner", async () => {
    const result = await independentCheck(input, {
      chain: chain(),
      fetchIssuer: async () => ({ ...issuer, issuer_address: OTHER }),
    });
    expect(result).toMatchObject({ documentOk: true, issuerOk: false });
  });

  it("fails the issuer check for a registry other than the issuer file's", async () => {
    const result = await independentCheck(
      { ...input, contractAddress: "0x" + "11".repeat(20) },
      { chain: chain(), fetchIssuer: async () => issuer },
    );
    expect(result).toMatchObject({ issuerOk: false });
  });

  it("falls back to the issuer identity built into the page when the file is unreachable", async () => {
    const result = await independentCheck(input, {
      chain: chain(),
      fetchIssuer: async () => {
        throw new TypeError("Failed to fetch");
      },
      bundledIssuer: issuer,
    });
    expect(result).toMatchObject({ documentOk: true, issuerOk: true, issuerSource: "bundled" });
  });

  it("reports unreachable when the RPC fails", async () => {
    const result = await independentCheck(input, {
      chain: chain({
        owner: async () => {
          throw new Error("fetch failed");
        },
      }),
      fetchIssuer: async () => issuer,
    });
    expect(result).toEqual({ unreachable: true, reason: "fetch failed" });
  });

  it("reports unreachable when the RPC is on another chain", async () => {
    const result = await independentCheck(input, {
      chain: chain({ chainId: async () => 1 }),
      fetchIssuer: async () => issuer,
    });
    expect(result).toMatchObject({ unreachable: true });
  });

  it("reports revocation", async () => {
    const result = await independentCheck(input, {
      chain: chain({ revoked: async () => true }),
      fetchIssuer: async () => issuer,
    });
    expect(result).toMatchObject({ documentOk: true, revoked: true });
  });

  it("with no proof, checks the leaf as a root (a batch of one)", async () => {
    const alone = sha("a passport anchored alone");
    const result = await independentCheck(
      { pdfSha256: alone, proof: [], chainId: 31337, contractAddress: CONTRACT },
      {
        chain: chain({
          anchoredAt: async (_c, r) => (r === leafFromPdfSha256(alone) ? BigInt(1) : BigInt(0)),
        }),
        fetchIssuer: async () => issuer,
      },
    );
    expect(result).toMatchObject({ documentOk: true, issuerOk: true });
  });
});

describe("lookupFile", () => {
  it("hashes the PDF locally and sends only its SHA-256", async () => {
    const marker = "%PDF-1.7 SECRET-CONTENT-MARKER";
    const file = new File([marker], "passport.pdf", { type: "application/pdf" });
    const requests: Request[] = [];
    const fetchSpy = vi.fn(async (request: Request) => {
      requests.push(request.clone());
      return Response.json({ verdict: "NOT_FOUND", checks: { document: false, issuer: false } });
    });
    const client = createApiClient({ baseUrl: "http://localhost", fetch: fetchSpy });

    const { sha256, result } = await lookupFile(file, client);

    expect(sha256).toBe(sha(marker));
    expect(result.verdict).toBe("NOT_FOUND");
    expect(requests).toHaveLength(1);
    expect(new URL(requests[0].url).pathname).toBe("/api/verify/hash");
    const body = await requests[0].text();
    expect(JSON.parse(body)).toEqual({ sha256: sha(marker) });
    expect(body).not.toContain("SECRET-CONTENT-MARKER");
    expect(requests[0].headers.get("content-type")).toBe("application/json");
  });
});

describe("checking on the chain alone (BTU's API down)", () => {
  const proofFile = {
    schema: "btu-ai-passport-proof/1",
    pdf_sha256: pdfSha256,
    proof: [sibling],
    merkle_root: root,
    chain_id: 31337,
    contract_address: CONTRACT,
  } as ProofFile;
  const deps = { chain: chain(), fetchIssuer: async () => issuer };

  it("confirms the file with its proof.json", async () => {
    const result = await independentCheck(chainOnlyInput(pdfSha256, proofFile), deps);
    expect(result).toMatchObject({ documentOk: true, issuerOk: true });
  });

  it("a proof.json for another file does not vouch for this one", async () => {
    const result = await independentCheck(chainOnlyInput(sha("edited"), proofFile), deps);
    expect(result).toMatchObject({ documentOk: false });
  });

  it("without proof.json a passport from a bigger batch is not found", async () => {
    const result = await independentCheck(chainOnlyInput(pdfSha256), deps);
    expect(result).toMatchObject({ documentOk: false, issuerOk: true });
  });

  it("reads only proof files", async () => {
    const file = (text: string) => new Blob([text], { type: "application/json" });
    await expect(readProofFile(file(JSON.stringify(proofFile)))).resolves.toMatchObject({
      merkle_root: root,
    });
    await expect(readProofFile(file('{"schema": "other"}'))).rejects.toThrow(/not a BTU/);
    await expect(readProofFile(file("not json"))).rejects.toThrow();
  });
});
