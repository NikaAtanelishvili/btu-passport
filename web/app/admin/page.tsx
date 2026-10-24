"use client";

// Placeholder until FE-21 (M6): proves sign-in lands admins here.
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useSession } from "@/lib/session";

export default function AdminDashboardPage() {
  const { data } = useSession();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Admin</CardTitle>
        <CardDescription>The dashboard arrives in a later milestone.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <p>Signed in as {data?.user?.email}</p>
        <p>Role: {data?.role}</p>
      </CardContent>
    </Card>
  );
}
