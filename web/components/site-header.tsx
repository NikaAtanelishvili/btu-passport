import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

// Sign out and the session-aware state arrive with FE-03 (M3).
export function SiteHeader() {
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
          {/* Plain <a>: /auth/* is proxied to the API, not a Next.js route. */}
          <a href="/auth/login" className={buttonVariants({ variant: "outline" })}>
            Sign in
          </a>
        </nav>
      </div>
    </header>
  );
}
