import { Suspense } from "react";

import { AdminShell } from "@/components/admin-shell";
import { GuardSkeleton, RequireRole } from "@/components/require-role";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<GuardSkeleton />}>
      <RequireRole role="admin">
        <AdminShell>{children}</AdminShell>
      </RequireRole>
    </Suspense>
  );
}
