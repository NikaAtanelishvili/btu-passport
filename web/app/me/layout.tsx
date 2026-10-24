import { RequireRole } from "@/components/require-role";
import { StudentNav } from "@/components/student-nav";

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole role="student">
      <StudentNav />
      {children}
    </RequireRole>
  );
}
