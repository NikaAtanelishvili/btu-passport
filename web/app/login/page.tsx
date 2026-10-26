"use client";

// FE-04: passwordless sign-in in two steps (Web App Design P4). The API decides where the
// user lands; this page only collects the email and the 6-digit code.
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { BtuLogo, Sticker } from "@/components/brand";
import { DisplayHeading } from "@/components/display";
import { Button } from "@/components/ui/button";
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
    <Suspense fallback={<Skeleton className="h-96 w-full rounded-[28px]" />}>
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
    return <Skeleton className="h-96 w-full rounded-[28px]" />;
  }

  return (
    <div className="grid items-center gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] md:gap-16">
      <Cover />
      <div className="w-full max-w-md md:max-w-none">
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
    </div>
  );
}

/** The passport cover: pink panel, white wordmark and the brand stickers (fewer on phones). */
function Cover() {
  return (
    <div className="overflow-hidden rounded-[28px] bg-primary p-6 text-white sm:p-12">
      <div className="hidden items-center gap-4 md:flex">
        <BtuLogo height={56} white />
        <span className="h-14 w-px bg-white" aria-hidden />
        <span className="eyebrow text-sm leading-snug">
          Business and
          <br />
          Technology University
        </span>
      </div>
      <DisplayHeading
        as="p"
        strong="AI Skills"
        light={
          <>
            Digital <br className="hidden md:inline" />
            Passport
          </>
        }
        className="text-[2rem] sm:text-[2.5rem] md:mt-8 md:text-[clamp(2.5rem,4.4vw,4rem)]"
      />
      <div className="mt-4 flex items-center pl-1 md:hidden" aria-hidden>
        <Sticker name="intl-recognised" width={92} rotate={-10} />
        <Sticker name="stamp-ai-advanced" width={62} rotate={12} className="relative z-10 -mt-8 -ml-4" />
        <Sticker name="blockchain-verified" width={128} rotate={-5} className="-ml-3 mt-3" />
      </div>
      {/* A loose pile: sizes and positions in % of the cover so it scales with the column;
          neighbours overlap a little, and the cover's overflow-hidden keeps them off the form. */}
      <div className="relative mt-6 hidden aspect-[4/3] md:block [&>img]:absolute [&>img]:h-auto" aria-hidden>
        <Sticker name="issued-by-btu" width={260} rotate={-6} className="top-[7%] left-0 w-[60%]" />
        <Sticker name="latest-skillset" width={210} rotate={5} className="top-0 right-0 w-[48%]" />
        <Sticker name="blockchain-verified" width={210} rotate={-9} className="top-[30%] left-[20%] z-10 w-[50%]" />
        <Sticker name="stamp-ai-advanced" width={100} rotate={10} className="top-[30%] right-[3%] w-[24%]" />
        <Sticker name="intl-recognised" width={150} rotate={-12} className="bottom-[3%] left-[1%] z-10 w-[35%]" />
        <Sticker name="ai-skills-digital-passport" width={190} rotate={4} className="right-[12%] bottom-0 w-[45%]" />
      </div>
    </div>
  );
}

const BIG_BUTTON = "h-14! w-full font-display text-xl! font-black uppercase sm:h-16! sm:text-2xl!";

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
    <div className="space-y-6">
      <div className="space-y-4">
        <DisplayHeading strong="Sign in" light="to your passport" className="text-[2.25rem] sm:text-[2.5rem] md:text-[clamp(2.5rem,3.4vw,3.25rem)]" />
        <p className="text-base text-muted-foreground sm:text-lg">We&apos;ll email you a 6-digit code. No password needed.</p>
      </div>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-5">
        <FieldGroup>
          <Controller
            name="email"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor="email" className="text-base">
                  Email
                </FieldLabel>
                <Input
                  {...field}
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="name@btu.edu.ge"
                  autoFocus
                  aria-invalid={fieldState.invalid}
                  className="h-14! text-lg!"
                />
                {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
              </Field>
            )}
          />
        </FieldGroup>
        <Button type="submit" className={BIG_BUTTON} disabled={form.formState.isSubmitting}>
          Send code
        </Button>
      </form>
      {/* "/" is the alias of /verify (FE-10); guests never sign in. */}
      <p className="text-muted-foreground">
        Checking someone&apos;s passport?{" "}
        <Link href="/verify" className="font-medium text-link underline underline-offset-4">
          Verify it
        </Link>{" "}
        — no sign-in needed.
      </p>
    </div>
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
    <div className="space-y-6">
      <div className="space-y-4">
        <DisplayHeading strong="Check" light="your email" className="text-[2.25rem] sm:text-[2.5rem] md:text-[clamp(2.5rem,3.4vw,3.25rem)]" />
        <p className="text-base text-muted-foreground sm:text-lg">
          We sent a 6-digit code to <span className="font-semibold text-foreground">{email}</span>.
          {resent && " A new code is on its way; only the newest one works."}
        </p>
      </div>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-5">
        <FieldGroup>
          <Controller
            name="code"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor="code" className="text-base">
                  Code
                </FieldLabel>
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
                  <InputOTPGroup className="gap-2 sm:gap-3">
                    {[0, 1, 2, 3, 4, 5].map((i) => (
                      <InputOTPSlot
                        key={i}
                        index={i}
                        className="h-14 w-12 rounded-md! border-[1.5px]! border-foreground font-mono text-2xl sm:h-16 sm:w-14"
                      />
                    ))}
                  </InputOTPGroup>
                </InputOTP>
                {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
              </Field>
            )}
          />
        </FieldGroup>
        <Button type="submit" className={BIG_BUTTON} disabled={form.formState.isSubmitting}>
          Sign in
        </Button>
      </form>
      <div className="flex flex-wrap justify-between gap-3">
        <button
          type="button"
          className="font-medium underline underline-offset-4 hover:text-link"
          onClick={() => onRestart(null)}
        >
          Use a different email
        </button>
        <button
          type="button"
          className="text-muted-foreground enabled:font-medium enabled:text-link enabled:underline enabled:underline-offset-4 enabled:hover:text-foreground"
          disabled={cooldown > 0}
          onClick={() => void resend()}
        >
          {cooldown > 0 ? `Resend code (${cooldown}s)` : "Resend code"}
        </button>
      </div>
    </div>
  );
}
