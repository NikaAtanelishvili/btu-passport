"use client";

// FE-11: the verdict, the two checks, the browser's own chain check (FE-12), the official data
// and the proof. Shared by /v/[code] and the upload card on /verify.
import { useQuery } from "@tanstack/react-query";
import { CheckIcon, ChevronDownIcon, XIcon } from "lucide-react";

import { StampImage } from "@/components/stamp-image";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { formatCode, formatDate, verdictHeadline } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";
import {
  type CheckInput,
  type IndependentResult,
  type VerifyResult,
  checkInputFor,
  independentCheck,
} from "@/lib/verify";

const FAILURES = new Set(["NOT_FOUND", "UNKNOWN_CODE", "NOT_ISSUED_BY_BTU", "REVOKED"]);
const EXPLORER_TX_URL = process.env.NEXT_PUBLIC_EXPLORER_TX_URL ?? "";

export function CheckRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      {ok ? (
        <CheckIcon aria-label="passed" className="size-4" />
      ) : (
        <XIcon aria-label="failed" className="size-4 text-destructive" />
      )}
      {label}
    </li>
  );
}

/** FE-12 as a row. Never blocks the page: the server's verdict is already showing. */
export function IndependentCheckRow({
  input,
  expected,
}: {
  input: CheckInput;
  /** The server's checks, to flag a disagreement; omitted when the server was unreachable. */
  expected?: { document: boolean; issuer: boolean };
}) {
  const check = useQuery({
    queryKey: queryKeys.verify.independent(input),
    queryFn: () => independentCheck(input),
    staleTime: Infinity,
    retry: false,
  });
  return (
    <p className="text-sm text-muted-foreground" data-testid="independent-check">
      {check.isPending ? "Checking directly on the blockchain from your browser…" : describe(check.data, expected)}
    </p>
  );
}

function describe(
  result: IndependentResult | undefined,
  expected?: { document: boolean; issuer: boolean },
): string {
  if (!result || result.unreachable) {
    return "Couldn't reach the blockchain from your browser; the result above is from BTU's server.";
  }
  const source =
    result.issuerSource === "bundled"
      ? " (BTU's issuer file couldn't be fetched; the issuer built into this page was used)"
      : "";
  if (expected && (expected.document !== result.documentOk || expected.issuer !== result.issuerOk)) {
    return `Your browser's own check on the blockchain disagrees with BTU's server: document ${result.documentOk ? "✓" : "✗"}, issuer ${result.issuerOk ? "✓" : "✗"}${source}.`;
  }
  if (result.documentOk && result.issuerOk && !result.revoked) {
    return `Also checked directly on the blockchain from your browser ✓${source}`;
  }
  return `Checked directly on the blockchain from your browser: document ${result.documentOk ? "✓" : "✗"}, issuer ${result.issuerOk ? "✓" : "✗"}${result.revoked ? ", revoked" : ""}${source}.`;
}

export function VerifyResultView({
  result,
  localSha256,
}: {
  result: VerifyResult;
  /** Set for an upload: the browser re-checks the hash it computed itself. */
  localSha256?: string;
}) {
  const input = checkInputFor(result, localSha256);
  const version = result.version;
  const chain = result.chain;
  const code = version?.verification_code;
  const unknown = result.verdict === "NOT_FOUND" || result.verdict === "UNKNOWN_CODE";

  return (
    <div className="space-y-4" data-testid="verify-result">
      <Alert variant={FAILURES.has(result.verdict) ? "destructive" : "default"}>
        <AlertTitle data-testid="verdict">
          {verdictHeadline(result.verdict, result.latest_version_no)}
        </AlertTitle>
        {result.verdict === "NOT_FOUND" && (
          <AlertDescription>
            Even a one-character change gives a different fingerprint. Ask the holder for the
            original file, or check the code printed on it.
          </AlertDescription>
        )}
      </Alert>

      {!unknown && (
        <ul className="space-y-1">
          <CheckRow ok={result.checks.document} label="Document unchanged since issue" />
          <CheckRow ok={result.checks.issuer} label="Issued by BTU" />
        </ul>
      )}
      {input && <IndependentCheckRow input={input} expected={result.checks} />}

      {version && (
        <Card>
          <CardHeader>
            <CardTitle>{version.holder_name}</CardTitle>
            <CardDescription>
              Passport {version.passport_id} · version {version.version_no} · issued{" "}
              {formatDate(version.issued_at)} · code {formatCode(version.verification_code)}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul className="space-y-3">
              {version.skills.map((skill) => (
                <li key={`${skill.name}-${skill.date_earned}`} className="flex items-center gap-3">
                  {skill.stamp_sha256 && (
                    <StampImage sha256={skill.stamp_sha256} category={skill.category} />
                  )}
                  <div className="text-sm">
                    <p className="font-medium">{skill.name}</p>
                    <p className="text-muted-foreground">
                      {skill.category} · earned {formatDate(skill.date_earned)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
            <a href={`/api/verify/${code}/pdf`} className={buttonVariants({ variant: "outline" })}>
              Download the official copy
            </a>
          </CardContent>
        </Card>
      )}

      {chain && result.proof && (
        <Collapsible>
          <CollapsibleTrigger className={buttonVariants({ variant: "ghost", size: "sm" })}>
            Proof <ChevronDownIcon className="size-4" />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <dl className="mt-2 grid gap-1 break-all text-xs sm:grid-cols-[10rem_1fr]">
              <dt className="text-muted-foreground">Chain</dt>
              <dd>{chain.chain_id}</dd>
              <dt className="text-muted-foreground">Contract</dt>
              <dd>{chain.contract_address}</dd>
              <dt className="text-muted-foreground">Issuer address</dt>
              <dd>{chain.issuer_address}</dd>
              <dt className="text-muted-foreground">Merkle root</dt>
              <dd>{chain.merkle_root}</dd>
              <dt className="text-muted-foreground">Transaction</dt>
              <dd>
                {EXPLORER_TX_URL ? (
                  <a className="underline" href={`${EXPLORER_TX_URL}${chain.tx_hash}`}>
                    {chain.tx_hash}
                  </a>
                ) : (
                  chain.tx_hash
                )}{" "}
                (block {chain.block_number}, {formatDate(chain.anchored_at)})
              </dd>
              <dt className="text-muted-foreground">PDF SHA-256</dt>
              <dd>{result.proof.pdf_sha256}</dd>
            </dl>
            {code && (
              <a
                href={`/api/verify/${code}/proof.json`}
                className={buttonVariants({ variant: "link", size: "sm" })}
              >
                Download proof.json
              </a>
            )}
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
