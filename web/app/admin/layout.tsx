import { AdminShell } from "@/components/admin-shell";
import { RequireRole } from "@/components/require-role";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole role="admin">
      <AdminShell>{children}</AdminShell>
    </RequireRole>
  );
}
