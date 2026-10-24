import { RequireRole } from "@/components/require-role";

// The AdminShell sidebar arrives with FE-20 (M6).
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <RequireRole role="admin">{children}</RequireRole>;
}
