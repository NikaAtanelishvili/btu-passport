"use client";

// FE-03: guard for the me/ and admin/ layouts. Signed out → /login?next=…; wrong role →
// a no-access alert. The API enforces the same rules (BE-12). Layouts render it inside
// <Suspense fallback={<GuardSkeleton />}>: usePathname() (here and in the shells) suspends on
// routes with dynamic params, so the route streams instead of blocking (Cache Components).
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { hasRole, type RequiredRole, useSession } from "@/lib/session";

export function RequireRole({ role, children }: { role: RequiredRole; children: React.ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const signedOut = session.isSuccess && !session.data.authenticated;

  useEffect(() => {
    if (signedOut) {
      router.replace(`/login?next=${encodeURIComponent(pathname + window.location.search)}`);
    }
  }, [signedOut, router, pathname]);

  if (session.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Couldn&apos;t check your session</AlertTitle>
        <AlertDescription>{session.error.message}</AlertDescription>
      </Alert>
    );
  }
  if (!session.isSuccess || signedOut) return <GuardSkeleton />;
  if (!hasRole(session.data, role)) {
    return (
      <Alert>
        <AlertTitle>You don&apos;t have access to this page</AlertTitle>
        <AlertDescription>
          <Link href="/" className={buttonVariants({ variant: "link" }) + " px-0"}>
            Go to the home page
          </Link>
        </AlertDescription>
      </Alert>
    );
  }
  return <>{children}</>;
}

export function GuardSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
