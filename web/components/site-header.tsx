"use client";

import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { hasRole, signOut, useSession } from "@/lib/session";

export function SiteHeader() {
  const session = useSession();
  const info = session.data;

  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-4 px-4">
        <Link href="/" className="font-semibold">
          BTU AI Skills Passport
        </Link>
        <nav className="flex items-center gap-2">
          <Link href="/" className={buttonVariants({ variant: "ghost" })}>
            Verify
          </Link>
          {info && hasRole(info, "student") && (
            <Link href="/me" className={buttonVariants({ variant: "ghost" })}>
              My passport
            </Link>
          )}
          {info && hasRole(info, "admin") && (
            <Link href="/admin" className={buttonVariants({ variant: "ghost" })}>
              Admin
            </Link>
          )}
          {info?.authenticated ? (
            <>
              <span className="hidden text-sm text-muted-foreground sm:inline">{info.user?.email}</span>
              <Button variant="outline" onClick={() => void signOut()}>
                Sign out
              </Button>
            </>
          ) : (
            <Link href="/login" className={buttonVariants({ variant: "outline" })}>
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
