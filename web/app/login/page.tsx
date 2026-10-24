"use client";

// FE-04: passwordless sign-in in two steps (Web App Design P4). The API decides where the
// user lands; this page only collects the email and the 6-digit code.
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { applyServerErrors } from "@/lib/forms";
import { homeFor, useSession } from "@/lib/session";

const RESEND_SECONDS = 60;

const emailSchema = z.object({ email: z.string().trim().email("Enter your email address") });
const codeSchema = z.object({ code: z.string().regex(/^\d{6}$/, "Enter the 6-digit code") });
type EmailForm = z.infer<typeof emailSchema>;
type CodeForm = z.infer<typeof codeSchema>;

export default function LoginPage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-64 w-full max-w-sm" />}>
      <Login />
    </Suspense>
  );
}

function Login() {
  const router = useRouter();
  const next = useSearchParams().get("next") ?? undefined;
  const session = useSession();
  const [email, setEmail] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (session.data?.authenticated) router.replace(homeFor(session.data));
  }, [session.data, router]);

  if (session.isPending || session.data?.authenticated) {
    return <Skeleton className="mx-auto h-64 w-full max-w-sm" />;
  }

  return (
    <div className="mx-auto w-full max-w-sm">
      {email === null ? (
        <EmailStep
          notice={notice}
          onSent={(sentTo) => {
            setNotice(null);
            setEmail(sentTo);
          }}
        />
      ) : (
        <CodeStep
          email={email}
          next={next}
          onRestart={(message) => {
            setNotice(message);
            setEmail(null);
          }}
        />
      )}
    </div>
  );
}

async function requestCode(email: string): Promise<void> {
  await api.POST("/auth/request-code", { body: { email } });
}

function EmailStep({ notice, onSent }: { notice: string | null; onSent: (email: string) => void }) {
  const form = useForm<EmailForm>({ resolver: zodResolver(emailSchema), defaultValues: { email: "" } });

  useEffect(() => {
    if (notice) form.setError("email", { type: "server", message: notice });
  }, [notice, form]);

  async function onSubmit({ email }: EmailForm) {
    try {
      await requestCode(email);
      onSent(email.trim().toLowerCase());
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        form.setError("email", { type: "server", message: "Too many codes requested, try again later" });
      } else {
        applyServerErrors(form, error);
      }
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>We&apos;ll email you a 6-digit code. No password needed.</CardDescription>
      </CardHeader>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate>
        <CardContent>
          <FieldGroup>
            <Controller
              name="email"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="email">BTU email</FieldLabel>
                  <Input
                    {...field}
                    id="email"
                    type="email"
                    autoComplete="email"
                    autoFocus
                    aria-invalid={fieldState.invalid}
                  />
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
          </FieldGroup>
        </CardContent>
        <CardFooter className="mt-6 flex flex-col gap-3">
          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            Send code
          </Button>
          {/* "/" is the alias of /verify (FE-10); guests never sign in. */}
          <Link href="/" className="text-sm text-muted-foreground underline-offset-4 hover:underline">
            Continue as guest
          </Link>
        </CardFooter>
      </form>
    </Card>
  );
}

function CodeStep({
  email,
  next,
  onRestart,
}: {
  email: string;
  next: string | undefined;
  onRestart: (message: string | null) => void;
}) {
  const form = useForm<CodeForm>({ resolver: zodResolver(codeSchema), defaultValues: { code: "" } });
  const [cooldown, setCooldown] = useState(RESEND_SECONDS);
  const [resent, setResent] = useState(false);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function onSubmit({ code }: CodeForm) {
    try {
      const { data } = await api.POST("/auth/verify-code", { body: { email, code, next } });
      // Full load so the new cookies and every query start fresh.
      window.location.assign(data?.redirect ?? "/");
    } catch (error) {
      if (!(error instanceof ApiError)) return applyServerErrors(form, error);
      if (error.error === "code_expired") return onRestart("Code expired, send a new one");
      if (error.error === "code_invalid") {
        const left = Number(error.body.attempts_left ?? 0);
        if (left <= 0) return onRestart("Too many wrong tries, send a new code");
        form.setValue("code", "");
        return form.setError("code", { type: "server", message: `Wrong code, ${left} tries left` });
      }
      applyServerErrors(form, error);
    }
  }

  async function resend() {
    try {
      await requestCode(email);
      form.reset({ code: "" });
      setResent(true);
      setCooldown(RESEND_SECONDS);
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        form.setError("code", { type: "server", message: "Too many codes requested, try again later" });
      } else {
        applyServerErrors(form, error);
      }
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Check your email</CardTitle>
        <CardDescription>
          We sent a 6-digit code to <span className="font-medium text-foreground">{email}</span>.
          {resent && " A new code is on its way; only the newest one works."}
        </CardDescription>
      </CardHeader>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate>
        <CardContent>
          <FieldGroup>
            <Controller
              name="code"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="code">Code</FieldLabel>
                  <InputOTP
                    id="code"
                    maxLength={6}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="^[0-9]*$"
                    autoFocus
                    value={field.value}
                    onChange={field.onChange}
                    aria-invalid={fieldState.invalid}
                  >
                    <InputOTPGroup>
                      {[0, 1, 2, 3, 4, 5].map((i) => (
                        <InputOTPSlot key={i} index={i} />
                      ))}
                    </InputOTPGroup>
                  </InputOTP>
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
          </FieldGroup>
        </CardContent>
        <CardFooter className="mt-6 flex flex-col gap-3">
          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            Sign in
          </Button>
          <div className="flex w-full justify-between">
            <Button type="button" variant="link" className="px-0" onClick={() => onRestart(null)}>
              Use a different email
            </Button>
            <Button
              type="button"
              variant="link"
              className="px-0"
              disabled={cooldown > 0}
              onClick={() => void resend()}
            >
              {cooldown > 0 ? `Resend code (${cooldown}s)` : "Resend code"}
            </Button>
          </div>
        </CardFooter>
      </form>
    </Card>
  );
}
