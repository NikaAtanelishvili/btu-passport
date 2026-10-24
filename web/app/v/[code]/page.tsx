"use client";

// FE-11: verify by code (Web App Design P2). Public; the printed QR code links here.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense } from "react";

import { ErrorAlert } from "@/components/error-alert";
import { VerifyResultView } from "@/components/verify-result-view";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { VerifyResult } from "@/lib/verify";

export default function VerifyCodePage() {
  return (
    <Suspense fallback={<Skeleton className="h-40 w-full" />}>
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
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-xl font-semibold">Passport verification</h1>
      {result.isPending && <Skeleton className="h-40 w-full" />}
      {result.isError && <ErrorAlert error={result.error} />}
      {result.isSuccess && <VerifyResultView result={result.data} />}
      <Link href="/verify" className={buttonVariants({ variant: "link" })}>
        Verify another passport
      </Link>
    </div>
  );
}
