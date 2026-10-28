"use client";

// FE-10: public verification (Web App Design P1), by code or by the PDF itself. The PDF is
// hashed in the browser and only its SHA-256 is sent; if BTU's server is down, the browser
// checks the file on the blockchain alone (NFR-09).
import { useMutation } from "@tanstack/react-query";
import { LockIcon, UploadIcon } from "lucide-react";
import { useState } from "react";

import { Asterisks, DisplayHeading } from "@/components/display";
import { ErrorAlert } from "@/components/error-alert";
import { VerifyCodeForm } from "@/components/verify-code-form";
import { ChainOnlyResult, VerifyResultView } from "@/components/verify-result-view";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import { sha256File } from "@/lib/merkle";
import { cn } from "@/lib/utils";
import { type ProofFile, type VerifyResult, chainOnlyInput, lookupHash, readProofFile } from "@/lib/verify";

const STEPS = [
  "Every passport version BTU issues has a fingerprint (SHA-256) recorded on a public blockchain.",
  "Checking a PDF compares its fingerprint with that record; changing even one character breaks the match.",
  "Your browser also checks the blockchain directly, so you don't have to take BTU's server on trust.",
];

/** The local hash, and the server's result, or why the server couldn't give one. */
type Lookup = { sha256: string; result?: VerifyResult; error?: Error };

export default function VerifyPage() {
  const [proofFile, setProofFile] = useState<ProofFile>();
  const [proofError, setProofError] = useState<string>();
  const [fileName, setFileName] = useState<string>();
  const lookup = useMutation({
    mutationFn: async (file: File): Promise<Lookup> => {
      const sha256 = await sha256File(file); // the file never leaves this device
      try {
        return { sha256, result: await lookupHash(sha256) };
      } catch (error) {
        if (error instanceof ApiError && error.status < 500) throw error;
        return { sha256, error: error as Error }; // BTU's server down: check on the chain alone
      }
    },
  });
  const done = lookup.data;

  return (
    <div className="space-y-10 sm:space-y-14">
      <div className="flex items-start justify-between gap-4">
        <DisplayHeading strong="Verify" light="a passport" size="hero" />
        <Asterisks className="text-[2.25rem] sm:text-[3.5rem]" />
      </div>

      <div className="grid items-start gap-6 md:grid-cols-[9fr_8fr] md:gap-8">
        <Card className="gap-6 rounded-[28px]! border-[1.5px] border-foreground py-8 ring-0 sm:py-12">
          <CardHeader className="px-6 sm:px-12">
            <CardTitle className="font-display text-[clamp(1.5rem,2.6vw,2rem)] font-black uppercase">
              Verify a passport
            </CardTitle>
            <CardDescription className="text-lg">Enter the verification code printed on the passport.</CardDescription>
          </CardHeader>
          <CardContent className="px-6 sm:px-12">
            <VerifyCodeForm variant="hero" />
          </CardContent>
        </Card>

        <Card id="check-pdf" className="scroll-mt-24 gap-6 rounded-[28px]! py-8 sm:py-12">
          <CardHeader className="px-6 sm:px-12">
            <CardTitle className="font-display text-[clamp(1.5rem,2.6vw,2rem)] leading-tight uppercase">
              <span className="font-black">Or check</span> <span className="font-extralight">the PDF you received</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-6 sm:px-12">
            <Field>
              <FieldLabel htmlFor="pdf" className="text-base">
                Passport PDF
              </FieldLabel>
              <label
                htmlFor="pdf"
                className="relative flex cursor-pointer flex-col overflow-hidden items-center gap-3 rounded-2xl border-[1.5px] border-dashed border-foreground px-4 py-8 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring"
              >
                <UploadIcon className="size-7" aria-hidden />
                <span className="flex flex-wrap items-center justify-center gap-3">
                  <span className={cn(buttonVariants({ variant: "outline" }), "h-11! text-lg!")}>Choose file</span>
                  <span className="text-muted-foreground">{fileName ?? "No file chosen"}</span>
                </span>
                <Input
                  id="pdf"
                  type="file"
                  accept="application/pdf"
                  className="sr-only"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    setProofFile(undefined);
                    setFileName(file?.name);
                    if (file) lookup.mutate(file);
                  }}
                />
              </label>
              <FieldDescription className="flex items-start gap-2">
                <LockIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
                Your file stays on your device; only its fingerprint is sent.
              </FieldDescription>
            </Field>
          </CardContent>
        </Card>
      </div>

      {(lookup.isPending || lookup.isError || done) && (
        <section aria-live="polite" className="space-y-6">
          {lookup.isPending && <p className="text-lg text-muted-foreground">Checking…</p>}
          {lookup.isError && <ErrorAlert error={lookup.error} />}
          {done?.result && <VerifyResultView result={done.result} localSha256={done.sha256} />}
          {done?.error && (
            <div className="space-y-6">
              <ErrorAlert
                error={done.error}
                title="BTU's server can't be reached — checking the blockchain directly instead"
              />
              <ChainOnlyResult input={chainOnlyInput(done.sha256, proofFile)} hasProofFile={!!proofFile} />
              <Field data-invalid={!!proofError} className="max-w-xl">
                <FieldLabel htmlFor="proof">Proof file (optional)</FieldLabel>
                <Input
                  id="proof"
                  type="file"
                  accept="application/json,.json"
                  onChange={async (event) => {
                    const file = event.target.files?.[0];
                    setProofError(undefined);
                    if (!file) return setProofFile(undefined);
                    try {
                      setProofFile(await readProofFile(file));
                    } catch (error) {
                      setProofError(error instanceof Error ? error.message : String(error));
                    }
                  }}
                />
                <FieldDescription>The proof.json offered with the passport. It also stays on your device.</FieldDescription>
                {proofError && <FieldError>{proofError}</FieldError>}
              </Field>
            </div>
          )}
        </section>
      )}

      <section className="border-t pt-10">
        <h2 className="eyebrow text-sm">How it works</h2>
        <ol className="mt-6 grid gap-8 md:grid-cols-3">
          {STEPS.map((step, i) => (
            <li key={step} className="flex gap-5">
              <span className="w-[1.25em] shrink-0 font-display text-5xl leading-none font-black text-primary sm:text-6xl">
                {String(i + 1).padStart(2, "0")}
              </span>
              <p className="text-lg">{step}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
