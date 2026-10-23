"use client";

// Temporary home page (FE-01): proves the /api rewrite reaches FastAPI.
// Replaced by the Verify page in FE-10 (M5).
import { useQuery } from "@tanstack/react-query";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

type Health = { ok: boolean };

async function fetchHealth(): Promise<Health> {
  const response = await fetch("/api/healthz");
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return (await response.json()) as Health;
}

export default function HomePage() {
  const health = useQuery({ queryKey: ["healthz"], queryFn: fetchHealth });

  return (
    <Card>
      <CardHeader>
        <CardTitle>API status</CardTitle>
      </CardHeader>
      <CardContent>
        {health.isPending && <Skeleton className="h-5 w-24" />}
        {health.isError && (
          <Alert variant="destructive">
            <AlertTitle>API unreachable</AlertTitle>
            <AlertDescription>{health.error.message}</AlertDescription>
          </Alert>
        )}
        {health.isSuccess && (
          <p data-testid="health">ok: {String(health.data.ok)}</p>
        )}
      </CardContent>
    </Card>
  );
}
