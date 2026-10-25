"use client";

// Site-wide header: black bar with the BTU logo and the wordmark, the brand stripe under it.
// The current section's link is the pink button; on phones the nav wraps under the logo.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { BtuLogo, Wordmark } from "@/components/brand";
import { cn } from "@/lib/utils";
import { hasRole, signOut, useSession } from "@/lib/session";

const NAV =
  "inline-flex h-10 items-center rounded-md px-3 font-display text-[0.95rem] leading-none font-extrabold whitespace-nowrap uppercase sm:px-4";
const PLAIN = "text-white hover:bg-white/10";
const ACTIVE = "bg-primary text-primary-foreground";
const OUTLINED = "border-[1.5px] border-white text-white hover:bg-white/10";

export function SiteHeader() {
  return (
    <header className="bg-black text-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-3" aria-label="BTU AI Skills Digital Passport, home">
          <BtuLogo height={48} />
          <span className="h-12 w-px bg-white/60" aria-hidden />
          <Wordmark />
        </Link>
        {/* usePathname() suspends on routes with dynamic params (as in the FE-03 layouts). */}
        <Suspense fallback={<nav className="h-10" />}>
          <HeaderNav />
        </Suspense>
      </div>
      <div className="h-2 bg-brand-stripe" aria-hidden />
    </header>
  );
}

function HeaderNav() {
  const session = useSession();
  const info = session.data;
  const pathname = usePathname();
  const at = (prefix: string) => pathname === prefix || pathname.startsWith(`${prefix}/`);
  const onVerify = at("/verify") || at("/v");

  return (
    <nav className="flex flex-wrap items-center gap-1.5 sm:gap-2">
      <Link href="/verify" className={cn(NAV, onVerify ? ACTIVE : PLAIN)}>
        Verify
      </Link>
      {info && hasRole(info, "student") && (
        <Link href="/me" className={cn(NAV, at("/me") ? ACTIVE : PLAIN)}>
          My passport
        </Link>
      )}
      {info && hasRole(info, "admin") && (
        <Link href="/admin" className={cn(NAV, at("/admin") ? ACTIVE : PLAIN)}>
          Admin
        </Link>
      )}
      {info?.authenticated ? (
        <>
          <span className="hidden px-1 text-sm text-white/70 lg:inline">{info.user?.email}</span>
          <button type="button" className={cn(NAV, OUTLINED)} onClick={() => void signOut()}>
            Sign out
          </button>
        </>
      ) : (
        <Link href="/login" className={cn(NAV, at("/login") ? ACTIVE : OUTLINED)}>
          Sign in
        </Link>
      )}
    </nav>
  );
}

export function SiteFooter() {
  return (
    <footer className="mx-auto flex w-full max-w-6xl items-center gap-4 px-4 pb-10 sm:px-6">
      <span className="eyebrow shrink-0 text-[0.7rem] sm:text-xs">Business and Technology University</span>
      <span className="h-px flex-1 bg-foreground" aria-hidden />
    </footer>
  );
}
