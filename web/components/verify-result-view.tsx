"use client";

// FE-11: the verdict, the two checks, the browser's own chain check (FE-12), the official data
// and the proof. Shared by /v/[code] and the upload card on /verify.
import { useQuery } from "@tanstack/react-query";
import { CheckIcon, InfoIcon, LoaderIcon, TriangleAlertIcon, XIcon } from "lucide-react";

import { Sticker } from "@/components/brand";
import { Eyebrow } from "@/components/display";
import { StampImage } from "@/components/stamp-image";
import { StatusPanel, type Tone } from "@/components/status-panel";
import { buttonVariants } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import { formatDate, verdictHeadline } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import {
  type CheckInput,
  type IndependentResult,
  type VerifyResult,
  checkInputFor,
  independentCheck,
} from "@/lib/verify";

const EXPLORER_TX_URL = process.env.NEXT_PUBLIC_EXPLORER_TX_URL ?? "";

export function CheckRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-sm font-medium sm:text-base">
      {ok ? (
        <CheckIcon aria-label="passed" className="size-5 shrink-0 text-status-valid-ink" strokeWidth={3} />
      ) : (
        <XIcon aria-label="failed" className="size-5 shrink-0 text-status-invalid-ink" strokeWidth={3} />
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
  const { tone, text } = check.isPending
    ? { tone: "pending" as const, text: "Checking directly on the blockchain from your browser…" }
    : describe(check.data, expected);
  const Icon = { pending: LoaderIcon, ok: CheckIcon, warn: TriangleAlertIcon, bad: XIcon }[tone];
  return (
    <p className="flex items-start gap-2 text-sm font-medium sm:text-base" data-testid="independent-check">
      <Icon
        aria-hidden
        strokeWidth={3}
        className={cn(
          "mt-0.5 size-5 shrink-0",
          tone === "pending" && "animate-spin text-muted-foreground",
          tone === "ok" && "text-status-valid-ink",
          tone === "warn" && "text-status-superseded-ink",
          tone === "bad" && "text-status-invalid-ink",
        )}
      />
      <span>{text}</span>
    </p>
  );
}

function describe(
  result: IndependentResult | undefined,
  expected?: { document: boolean; issuer: boolean },
): { tone: "ok" | "warn" | "bad"; text: string } {
  if (!result || result.unreachable) {
    return {
      tone: "warn",
      text: "Couldn't reach the blockchain from your browser; the result above is from BTU's server.",
    };
  }
  const source =
    result.issuerSource === "bundled"
      ? " (BTU's issuer file couldn't be fetched; the issuer built into this page was used)"
      : "";
  if (expected && (expected.document !== result.documentOk || expected.issuer !== result.issuerOk)) {
    return {
      tone: "warn",
      text: `Your browser's own check on the blockchain disagrees with BTU's server: document ${result.documentOk ? "✓" : "✗"}, issuer ${result.issuerOk ? "✓" : "✗"}${source}.`,
    };
  }
  if (result.documentOk && result.issuerOk && !result.revoked) {
    return { tone: "ok", text: `Your browser checked the blockchain directly${source}` };
  }
  return {
    tone: "bad",
    text: `Checked directly on the blockchain from your browser: document ${result.documentOk ? "✓" : "✗"}, issuer ${result.issuerOk ? "✓" : "✗"}${result.revoked ? ", revoked" : ""}${source}.`,
  };
}

type Verdict = VerifyResult["verdict"];

const PANEL: Record<Verdict, { tone: Tone; word: string }> = {
  VALID: { tone: "valid", word: "Valid" },
  SUPERSEDED: { tone: "superseded", word: "Superseded" },
  NOT_FOUND: { tone: "invalid", word: "Not valid" },
  UNKNOWN_CODE: { tone: "invalid", word: "Not valid" },
  NOT_ISSUED_BY_BTU: { tone: "invalid", word: "Not valid" },
  REVOKED: { tone: "invalid", word: "Not valid" },
};

function subtitle(result: VerifyResult): string {
  switch (result.verdict) {
    case "VALID":
      return "Issued by Business and Technology University. This is the latest version and it matches the blockchain record.";
    case "SUPERSEDED":
      return `A real BTU passport, but not the latest. A newer version (v${result.latest_version_no ?? "?"}) replaced it.`;
    case "NOT_FOUND":
      return "This file doesn't match any passport BTU issued.";
    case "UNKNOWN_CODE":
      return "No passport matches this code.";
    case "NOT_ISSUED_BY_BTU":
      return "This passport was not issued by BTU.";
    case "REVOKED":
      return "BTU has revoked this passport version.";
  }
}

/** Why it failed, and what the verifier can do next. */
const FAILURE: Partial<Record<Verdict, { why: string; todo: string[] }>> = {
  UNKNOWN_CODE: {
    why: "BTU has no passport with this verification code. Codes look like XXXX-XXXX-XX and are printed on the passport.",
    todo: [
      "Check the code for typos and try again.",
      "Ask the holder for the PDF that BTU sent them and check that file.",
      "Don't accept this passport until it verifies.",
    ],
  },
  NOT_FOUND: {
    why: "Even a one-character change gives a different fingerprint. Ask the holder for the original file, or check the code printed on it.",
    todo: [
      "Ask the holder for the PDF that BTU sent them and check that file.",
      "Or enter the verification code printed on the passport.",
      "Don't accept this passport until it verifies.",
    ],
  },
  NOT_ISSUED_BY_BTU: {
    why: "The blockchain record this passport points to was not written by BTU's issuer, so it proves nothing about a BTU passport.",
    todo: ["Ask the holder for the PDF that BTU sent them and check that file.", "Don't accept this passport until it verifies."],
  },
  REVOKED: {
    why: "BTU has withdrawn this version; it no longer counts as a BTU passport.",
    todo: ["Ask the holder for their latest passport PDF or its verification code.", "Don't accept this passport until it verifies."],
  },
};

function Fact({ label, children, sub }: { label: string; children: React.ReactNode; sub?: string }) {
  return (
    <div className="min-w-0">
      <dt>
        <Eyebrow>{label}</Eyebrow>
      </dt>
      <dd className="mt-2">
        {children}
        {sub && <p className="mt-1 text-muted-foreground">{sub}</p>}
      </dd>
    </div>
  );
}

const BIG = "font-display text-3xl leading-tight font-extrabold sm:text-4xl";

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
  const { tone, word } = PANEL[result.verdict];
  const failure = FAILURE[result.verdict];
  const superseded = result.verdict === "SUPERSEDED";
  const fingerprint = result.proof?.pdf_sha256;

  return (
    <div data-testid="verify-result">
      <StatusPanel
        tone={tone}
        word={word}
        wordProps={{ "data-testid": "verdict", title: verdictHeadline(result.verdict, result.latest_version_no) }}
        subtitle={subtitle(result)}
        aside={
          result.verdict === "VALID" && (
            <Sticker name="blockchain-verified" width={240} rotate={-6} className="w-[200px] sm:w-[240px]" />
          )
        }
      >
        <div className="space-y-8">
          {failure && (
            <>
              <p className="max-w-3xl text-lg">{failure.why}</p>
              <div className="rounded-2xl bg-status-invalid-soft p-5 sm:p-6">
                <p className="eyebrow">What you can do</p>
                <ul className="mt-3 list-disc space-y-1.5 pl-5 sm:text-lg">
                  {failure.todo.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {version && (
            <dl className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <Fact label="Holder">
                <span className={BIG}>{version.holder_name}</span>
              </Fact>
              <Fact label="Passport ID">
                <span className="font-mono text-2xl whitespace-nowrap sm:text-[1.75rem]">{version.passport_id}</span>
              </Fact>
              <Fact
                label={superseded ? "This version" : "Version"}
                sub={superseded ? `Issued ${formatDate(version.issued_at)}` : undefined}
              >
                <span className={BIG}>
                  v{version.version_no}
                  {!superseded && " · latest"}
                </span>
              </Fact>
              {superseded ? (
                <Fact label="Latest version">
                  <span className={BIG}>v{result.latest_version_no}</span>
                </Fact>
              ) : (
                <Fact label="Date of issue">
                  <span className={BIG}>{formatDate(version.issued_at)}</span>
                </Fact>
              )}
            </dl>
          )}

          {superseded && (
            <p className="flex items-start gap-3 rounded-2xl bg-status-superseded-soft p-5 sm:text-lg">
              <InfoIcon className="mt-0.5 size-6 shrink-0" aria-hidden />
              <span>
                <strong>Skills may have changed since this version.</strong> Ask the holder for their latest
                passport PDF or its verification code.
              </span>
            </p>
          )}

          {version && version.skills.length > 0 && (
            <div>
              <Eyebrow>
                Skills on this version · {version.skills.length}
              </Eyebrow>
              <ul className="mt-3 grid gap-3 md:grid-cols-2">
                {version.skills.map((skill) => (
                  <li
                    key={`${skill.name}-${skill.date_earned}`}
                    className="flex items-center gap-4 rounded-2xl border p-4"
                  >
                    {skill.stamp_sha256 && (
                      <StampImage sha256={skill.stamp_sha256} category={skill.category} size={64} />
                    )}
                    <div className="min-w-0">
                      <p className="text-lg leading-snug font-semibold">{skill.name}</p>
                      <p className="text-muted-foreground">
                        {skill.category} · earned {formatDate(skill.date_earned)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(!unknown || input || (chain && result.proof)) && (
            <div className="space-y-4">
              {version && <Separator />}
              <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-center lg:gap-x-8">
                {!unknown && (
                  <ul className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-x-6">
                    <CheckRow
                      ok={result.checks.document}
                      label={
                        superseded && result.checks.document
                          ? `Fingerprint matches the v${version?.version_no} record`
                          : "Document unchanged since issue"
                      }
                    />
                    <CheckRow ok={result.checks.issuer} label="Issued by BTU" />
                  </ul>
                )}
                {input && <IndependentCheckRow input={input} expected={result.checks} />}
              </div>
              {chain && result.proof && (
                <Collapsible>
                  <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
                    {fingerprint && (
                      <p className="text-muted-foreground">
                        Fingerprint{" "}
                        <span className="font-mono text-foreground">
                          [{fingerprint.slice(0, 10)}…{fingerprint.slice(-4)}]
                        </span>
                      </p>
                    )}
                    <CollapsibleTrigger className="font-medium text-link underline underline-offset-4 hover:no-underline">
                      View blockchain record
                    </CollapsibleTrigger>
                    {code && (
                      <a
                        href={`/api/verify/${code}/pdf`}
                        className={buttonVariants({ variant: "outline" })}
                      >
                        Download the official copy
                      </a>
                    )}
                  </div>
                  <CollapsibleContent>
                    <dl className="mt-4 grid gap-1 rounded-2xl bg-muted p-4 font-mono text-xs break-all sm:grid-cols-[10rem_1fr]">
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
                          <a className="text-link underline" href={`${EXPLORER_TX_URL}${chain.tx_hash}`}>
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
                        className={cn(buttonVariants({ variant: "link" }), "px-0 text-link")}
                      >
                        Download proof.json
                      </a>
                    )}
                  </CollapsibleContent>
                </Collapsible>
              )}
            </div>
          )}
        </div>
      </StatusPanel>
    </div>
  );
}

/** NFR-09: BTU's server is unreachable, so the browser checks the file on the chain alone. */
export function ChainOnlyResult({ input, hasProofFile }: { input: CheckInput; hasProofFile: boolean }) {
  const check = useQuery({
    queryKey: queryKeys.verify.independent(input),
    queryFn: () => independentCheck(input),
    staleTime: Infinity,
    retry: false,
  });
  if (check.isPending) {
    return <p className="text-muted-foreground">Checking directly on the blockchain from your browser…</p>;
  }
  const result = check.data;
  if (!result || result.unreachable) {
    return (
      <StatusPanel
        tone="invalid"
        word="Can't check"
        subtitle="The blockchain can't be reached from your browser either. Try again later."
      />
    );
  }
  const valid = result.documentOk && result.issuerOk && !result.revoked;
  return (
    <div data-testid="verify-result">
      <StatusPanel
        tone={valid ? "valid" : "invalid"}
        word={valid ? "Valid" : "Not valid"}
        wordProps={{ "data-testid": "verdict" }}
        subtitle={
          valid
            ? "Valid on the blockchain — issued by BTU"
            : !result.issuerOk
              ? verdictHeadline("NOT_ISSUED_BY_BTU")
              : result.revoked
                ? verdictHeadline("REVOKED")
                : hasProofFile
                  ? "This file doesn't match its proof"
                  : "Not found on the blockchain by this file alone"
        }
      >
        <div className="space-y-4">
          <p className="max-w-3xl text-lg">
            {valid
              ? "Checked directly on the blockchain from your browser. Whether this is the passport's latest version can only be checked when BTU's server is back."
              : !hasProofFile && result.issuerOk
                ? "Most passports need their proof file for this check. Add the proof.json that came with the passport."
                : "Even a one-character change gives a different fingerprint."}
          </p>
          <ul className="flex flex-col gap-2 sm:flex-row sm:gap-x-6">
            <CheckRow ok={result.documentOk} label="Document unchanged since issue" />
            <CheckRow ok={result.issuerOk} label="Issued by BTU" />
          </ul>
          {result.issuerSource === "bundled" && (
            <p className="text-sm text-muted-foreground">
              BTU&apos;s issuer file couldn&apos;t be fetched; the issuer identity built into this page was used.
            </p>
          )}
        </div>
      </StatusPanel>
    </div>
  );
}
