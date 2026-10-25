"use client";

// The verification-code form: the big card on /verify, and the bar above a result on /v/[code].
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Button, buttonVariants } from "@/components/ui/button";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { normalizeCode } from "@/lib/format";
import { cn } from "@/lib/utils";

const codeSchema = z.object({
  code: z
    .string()
    .refine((value) => normalizeCode(value) !== null, "Enter the code printed on the passport, e.g. K7QM-3XWP-9D"),
});
type CodeForm = z.infer<typeof codeSchema>;

export function VerifyCodeForm({ variant, defaultCode = "" }: { variant: "hero" | "bar"; defaultCode?: string }) {
  const router = useRouter();
  const form = useForm<CodeForm>({ resolver: zodResolver(codeSchema), defaultValues: { code: defaultCode } });
  const hero = variant === "hero";
  return (
    <form
      onSubmit={form.handleSubmit(({ code }) => router.push(`/v/${normalizeCode(code)}`))}
      noValidate
    >
      <Controller
        name="code"
        control={form.control}
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor="code" className="text-base">
              Verification code
            </FieldLabel>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Input
                {...field}
                id="code"
                placeholder="XXXX-XXXX-XX"
                autoComplete="off"
                autoCapitalize="characters"
                aria-invalid={fieldState.invalid}
                className={cn(
                  "font-mono tracking-[0.08em] uppercase",
                  hero ? "h-16! text-2xl!" : "h-12! text-xl!",
                )}
              />
              <div className={cn("grid gap-3", !hero && "grid-cols-2 sm:flex")}>
                <Button
                  type="submit"
                  className={cn(
                    hero
                      ? "h-16! px-10! font-display text-3xl! font-black uppercase"
                      : "h-12! px-10! text-lg!",
                  )}
                >
                  Verify
                </Button>
                {!hero && (
                  <Link href="/verify" className={cn(buttonVariants({ variant: "outline" }), "h-12! px-6! text-lg!")}>
                    Check a PDF
                  </Link>
                )}
              </div>
            </div>
            {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
          </Field>
        )}
      />
    </form>
  );
}
