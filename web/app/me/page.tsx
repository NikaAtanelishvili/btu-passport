"use client";

// Placeholder until FE-40 (M8): proves sign-in lands students here.
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useSession } from "@/lib/session";

export default function MyPassportPage() {
  const { data } = useSession();
  return (
    <Card>
      <CardHeader>
        <CardTitle>My passport</CardTitle>
        <CardDescription>Your passport and history arrive in a later milestone.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <p>Signed in as {data?.user?.name}</p>
        <p>Student ID: {data?.student?.student_id}</p>
        <p>Passport ID: {data?.student?.passport_id}</p>
      </CardContent>
    </Card>
  );
}
