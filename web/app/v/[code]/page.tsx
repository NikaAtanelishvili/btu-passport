"use client";

// FE-11: verify by code (Web App Design P2). Public; the printed QR code links here.
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { Suspense } from "react";

import { ErrorAlert } from "@/components/error-alert";
import { VerifyCodeForm } from "@/components/verify-code-form";
import { VerifyResultView } from "@/components/verify-result-view";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatCode } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";
import type { VerifyResult } from "@/lib/verify";

export default function VerifyCodePage() {
  return (
    <Suspense fallback={<Skeleton className="h-40 w-full rounded-[28px]" />}>
      <VerifyCode />
    </Suspense>
  );
}

function VerifyCode() {
  const { code } = useParams<{ code: string }>();
  const result = useQuery({
    queryKey: queryKeys.verify.code(code),
    queryFn: async (): Promise<VerifyResult> => {
      const { data } = await api.GET("/api/verify/{code}", { params: { path: { code } } });
      return data as VerifyResult;
    },
    retry: false,
  });

  return (
    <div className="space-y-8 sm:space-y-12">
      <h1 className="sr-only">Passport verification</h1>
      <Card className="rounded-[28px]! py-5 sm:py-6">
        <CardContent className="px-5 sm:px-6">
          <VerifyCodeForm key={code} variant="bar" defaultCode={formatCode(code)} />
        </CardContent>
      </Card>
      {result.isPending && <Skeleton className="h-80 w-full rounded-[28px]" />}
      {result.isError && <ErrorAlert error={result.error} />}
      {result.isSuccess && <VerifyResultView result={result.data} />}
    </div>
  );
}
