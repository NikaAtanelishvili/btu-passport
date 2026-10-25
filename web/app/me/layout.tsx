import { Suspense } from "react";

import { GuardSkeleton, RequireRole } from "@/components/require-role";
import { StudentNav } from "@/components/student-nav";

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<GuardSkeleton />}>
      <RequireRole role="student">
        <StudentNav />
        {children}
      </RequireRole>
    </Suspense>
  );
}
