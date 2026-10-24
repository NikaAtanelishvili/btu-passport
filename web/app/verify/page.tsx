"use client";

// FE-10: public verification (Web App Design P1), by code or by the PDF itself. The PDF is
// hashed in the browser and only its SHA-256 is sent; if BTU's server is down, the browser
// checks the file on the blockchain alone (NFR-09).
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ErrorAlert } from "@/components/error-alert";
import { ChainOnlyResult, VerifyResultView } from "@/components/verify-result-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import { normalizeCode } from "@/lib/format";
import { sha256File } from "@/lib/merkle";
import {
  type ProofFile,
  type VerifyResult,
  chainOnlyInput,
  lookupHash,
  readProofFile,
} from "@/lib/verify";

const codeSchema = z.object({
  code: z
    .string()
    .refine((value) => normalizeCode(value) !== null, "Enter the code printed on the passport, e.g. K7QM-3XWP-9D"),
});
type CodeForm = z.infer<typeof codeSchema>;

export default function VerifyPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <CodeCard />
      <FileCard />
      <section className="space-y-1 text-sm text-muted-foreground">
        <h2 className="font-medium text-foreground">How it works</h2>
        <p>Every passport version BTU issues has a fingerprint (SHA-256) recorded on a public blockchain.</p>
        <p>Checking a PDF compares its fingerprint with that record; changing even one character breaks the match.</p>
        <p>Your browser also checks the blockchain directly, so you don&apos;t have to take BTU&apos;s server on trust.</p>
      </section>
    </div>
  );
}

function CodeCard() {
  const router = useRouter();
  const form = useForm<CodeForm>({ resolver: zodResolver(codeSchema), defaultValues: { code: "" } });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Verify a passport</CardTitle>
        <CardDescription>Enter the verification code printed on the passport.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={form.handleSubmit(({ code }) => router.push(`/v/${normalizeCode(code)}`))}
          noValidate
        >
          <FieldGroup>
            <Controller
              name="code"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="code">Verification code</FieldLabel>
                  <div className="flex gap-2">
                    <Input
                      {...field}
                      id="code"
                      placeholder="XXXX-XXXX-XX"
                      autoComplete="off"
                      autoCapitalize="characters"
                      aria-invalid={fieldState.invalid}
                    />
                    <Button type="submit">Verify</Button>
                  </div>
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}

/** The local hash, and the server's result, or why the server couldn't give one. */
type Lookup = { sha256: string; result?: VerifyResult; error?: Error };

function FileCard() {
  const [proofFile, setProofFile] = useState<ProofFile>();
  const [proofError, setProofError] = useState<string>();
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
    <Card>
      <CardHeader>
        <CardTitle>Or check the PDF you received</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field>
          <FieldLabel htmlFor="pdf">Passport PDF</FieldLabel>
          <Input
            id="pdf"
            type="file"
            accept="application/pdf"
            onChange={(event) => {
              const file = event.target.files?.[0];
              setProofFile(undefined);
              if (file) lookup.mutate(file);
            }}
          />
          <FieldDescription>Your file stays on your device; only its fingerprint is sent.</FieldDescription>
        </Field>

        {lookup.isPending && <p className="text-sm text-muted-foreground">Checking…</p>}
        {lookup.isError && <ErrorAlert error={lookup.error} />}
        {done?.result && <VerifyResultView result={done.result} localSha256={done.sha256} />}
        {done?.error && (
          <div className="space-y-4">
            <ErrorAlert
              error={done.error}
              title="BTU's server can't be reached — checking the blockchain directly instead"
            />
            <ChainOnlyResult input={chainOnlyInput(done.sha256, proofFile)} hasProofFile={!!proofFile} />
            <Field data-invalid={!!proofError}>
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
      </CardContent>
    </Card>
  );
}
