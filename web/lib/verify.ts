// FE-12: the browser checks the server's verdict on its own, straight against the chain
// (Blockchain tab §5, steps 3–5), and FE-10's upload path, which sends only the PDF's hash.
import { createPublicClient, getAddress, http, isAddressEqual } from "viem";

import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { type Hex32, leafFromPdfSha256, processProof, sha256File } from "@/lib/merkle";
import { passportRegistryAbi } from "@/lib/passport-registry-abi";

export type VerifyResult = components["schemas"]["VerifyResult"];
export type IssuerFile = components["schemas"]["IssuerFile"];
export type ProofFile = components["schemas"]["ProofFile"];

/** Read-only access to the registry; `viemChain()` in the browser, a fake in tests. */
export type ChainReader = {
  chainId(): Promise<number>;
  owner(contract: string): Promise<string>;
  anchoredAt(contract: string, root: Hex32): Promise<bigint>;
  revoked(contract: string, leaf: Hex32): Promise<boolean>;
};

export type CheckInput = {
  /** For an upload, the hash computed here, never one the server sent back. */
  pdfSha256: string;
  proof: readonly string[];
  /** Root the proof should lead to; omitted when only the PDF is at hand (no proof). */
  merkleRoot?: string;
  /** Chain and registry the proof claims; omitted when there is no proof (BTU's are used). */
  chainId?: number;
  contractAddress?: string;
};

export type IndependentResult =
  | {
      unreachable: false;
      documentOk: boolean;
      issuerOk: boolean;
      revoked: boolean;
      /** "bundled": the issuer file couldn't be fetched, so the copy built into this page was used. */
      issuerSource: "file" | "bundled";
    }
  | { unreachable: true; reason: string };

export function viemChain(rpcUrl = process.env.NEXT_PUBLIC_RPC_URL ?? ""): ChainReader {
  const client = createPublicClient({ transport: http(rpcUrl, { timeout: 10_000 }) });
  const read = { abi: passportRegistryAbi } as const;
  return {
    chainId: () => client.getChainId(),
    owner: (contract) =>
      client.readContract({ ...read, address: getAddress(contract), functionName: "owner" }),
    anchoredAt: (contract, root) =>
      client.readContract({
        ...read,
        address: getAddress(contract),
        functionName: "anchoredAt",
        args: [root],
      }),
    revoked: (contract, leaf) =>
      client.readContract({
        ...read,
        address: getAddress(contract),
        functionName: "revoked",
        args: [leaf],
      }),
  };
}

export async function fetchIssuerFile(): Promise<IssuerFile> {
  const response = await fetch("/.well-known/ai-passport-issuer.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`issuer file: HTTP ${response.status}`);
  return (await response.json()) as IssuerFile;
}

/** BTU's issuer identity as configured when this page was built (next.config.ts). Used only
 * when the issuer file can't be fetched, e.g. while BTU's API is down (NFR-09). */
export function bundledIssuerFile(): IssuerFile | undefined {
  const raw = process.env.NEXT_PUBLIC_BTU_ISSUER;
  if (!raw) return undefined;
  const parsed = JSON.parse(raw) as IssuerFile;
  return parsed.contract_address && parsed.issuer_address ? parsed : undefined;
}

type Deps = {
  chain?: ChainReader;
  fetchIssuer?: () => Promise<IssuerFile>;
  bundledIssuer?: IssuerFile;
};

function sameAddress(a: string, b: string): boolean {
  try {
    return isAddressEqual(getAddress(a), getAddress(b));
  } catch {
    return false;
  }
}

export async function independentCheck(
  input: CheckInput,
  {
    chain = viemChain(),
    fetchIssuer = fetchIssuerFile,
    bundledIssuer = bundledIssuerFile(),
  }: Deps = {},
): Promise<IndependentResult> {
  let issuer: IssuerFile;
  let issuerSource: "file" | "bundled" = "file";
  try {
    issuer = await fetchIssuer();
  } catch (error) {
    if (!bundledIssuer) return { unreachable: true, reason: String(error) };
    issuer = bundledIssuer;
    issuerSource = "bundled";
  }

  const leaf = leafFromPdfSha256(input.pdfSha256);
  const root = processProof(leaf, input.proof);
  const rootMatches = input.merkleRoot === undefined || root === input.merkleRoot.toLowerCase();
  const registry = issuer.contract_address; // BTU's registry, whatever the proof claims

  try {
    if ((await chain.chainId()) !== issuer.chain_id) {
      return { unreachable: true, reason: `the RPC is not on chain ${issuer.chain_id}` };
    }
    const [owner, anchoredAt, revoked] = await Promise.all([
      chain.owner(registry),
      rootMatches ? chain.anchoredAt(registry, root) : Promise.resolve(BigInt(0)),
      chain.revoked(registry, leaf),
    ]);
    return {
      unreachable: false,
      documentOk: rootMatches && anchoredAt > BigInt(0),
      issuerOk:
        (input.chainId ?? issuer.chain_id) === issuer.chain_id &&
        sameAddress(input.contractAddress ?? registry, registry) &&
        sameAddress(owner, issuer.issuer_address),
      revoked,
      issuerSource,
    };
  } catch (error) {
    return { unreachable: true, reason: error instanceof Error ? error.message : String(error) };
  }
}

/** The check's input for a server result: the server's proof, but for an upload the hash
 * this browser computed. Null when there is nothing to re-check (code or file unknown). */
export function checkInputFor(result: VerifyResult, localSha256?: string): CheckInput | null {
  if (!result.proof || !result.chain) return null;
  return {
    pdfSha256: localSha256 ?? result.proof.pdf_sha256,
    proof: result.proof.proof,
    merkleRoot: result.chain.merkle_root,
    chainId: result.chain.chain_id,
    contractAddress: result.chain.contract_address,
  };
}

/** FE-10: hash the PDF here and send only the hash. The file itself never leaves the device. */
export async function lookupFile(
  file: Blob,
  client = api,
): Promise<{ sha256: Hex32; result: VerifyResult }> {
  const sha256 = await sha256File(file);
  const { data } = await client.POST("/api/verify/hash", { body: { sha256 } });
  return { sha256, result: data as VerifyResult };
}
