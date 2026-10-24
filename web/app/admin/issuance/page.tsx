"use client";

// FE-25: issuance (Web App Design A5). Tabs Failed · In progress · Recent, kept in ?tab= so
// the dashboard and the award form can link to one. In progress refetches every 5 s.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { DataTable } from "@/components/data-table";
import { ErrorAlert } from "@/components/error-alert";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDateTime } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";

type VersionRow = components["schemas"]["VersionRow"];
const PAGE_SIZE = 25;

const TABS = {
  failed: { label: "Failed", status: "FAILED", poll: 15_000 },
  "in-progress": { label: "In progress", status: "PENDING,RENDERED,ANCHORING", poll: 5_000 },
  recent: { label: "Recent", status: "ANCHORED", poll: 15_000 },
} as const;
type Tab = keyof typeof TABS;

export default function IssuancePage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <Issuance />
    </Suspense>
  );
}

function Issuance() {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const requested = useSearchParams().get("tab");
  const tab: Tab = requested && requested in TABS ? (requested as Tab) : "failed";
  const [page, setPage] = useState(1);

  const params = { status: TABS[tab].status, page, page_size: PAGE_SIZE };
  const versions = useQuery({
    queryKey: queryKeys.admin.versions(params),
    queryFn: async () => (await api.GET("/api/admin/versions", { params: { query: params } })).data!,
    refetchInterval: TABS[tab].poll,
    placeholderData: (previous) => previous,
  });

  const refresh = () => void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
  const retry = useMutation({
    mutationFn: async (versionId: number) =>
      (await api.POST("/api/admin/versions/{version_id}/retry", { params: { path: { version_id: versionId } } }))
        .data!,
    onSuccess: (v) => {
      toast.success(`Retrying ${v.passport_id} v${v.version_no}`);
      refresh();
    },
    onError: (error) => toast.error(error.message),
  });
  const retryAll = useMutation({
    mutationFn: async () => (await api.POST("/api/admin/versions/retry-failed")).data!,
    onSuccess: ({ count }) => {
      toast.success(count ? `Retrying ${count} failed version${count === 1 ? "" : "s"}` : "Nothing to retry");
      refresh();
    },
    onError: (error) => toast.error(error.message),
  });

  function selectTab(value: unknown) {
    setPage(1);
    router.replace(`${pathname}?tab=${String(value)}`);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Issuance</h1>
        {tab === "failed" && (
          <ConfirmDialog
            trigger={<Button variant="outline" />}
            disabled={!versions.data?.total || retryAll.isPending}
            title="Retry all failed versions?"
            description={`${versions.data?.total ?? 0} failed version(s) go back into the queue: rendered ones are re-anchored, the others are rendered again.`}
            confirmLabel="Retry all"
            onConfirm={() => retryAll.mutate()}
          >
            Retry all failed
          </ConfirmDialog>
        )}
      </div>
      <Tabs value={tab} onValueChange={selectTab}>
        <TabsList>
          {Object.entries(TABS).map(([value, t]) => (
            <TabsTrigger key={value} value={value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {versions.isError && <ErrorAlert error={versions.error} />}
      <DataTable<VersionRow>
        rows={versions.data?.items}
        loading={versions.isPending}
        rowKey={(v) => v.version_id}
        total={versions.data?.total}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        empty={tab === "failed" ? "No failed issuances." : tab === "in-progress" ? "Nothing in progress." : "Nothing issued yet."}
        columns={[
          {
            header: "Student",
            cell: (v) => (
              <Link href={`/admin/students/${v.student_id}`} className="underline-offset-4 hover:underline">
                {v.student_name}
              </Link>
            ),
          },
          { header: "Passport ID", cell: (v) => v.passport_id },
          { header: "Version", cell: (v) => `v${v.version_no}` },
          { header: "Status", cell: (v) => <StatusBadge status={v.status} /> },
          { header: "Error", cell: (v) => v.error ?? "", className: "max-w-sm whitespace-normal" },
          { header: "Time", cell: (v) => formatDateTime(v.issued_at ?? v.created_at) },
          {
            header: "",
            cell: (v) =>
              v.status === "FAILED" ? (
                <Button size="sm" variant="outline" disabled={retry.isPending} onClick={() => retry.mutate(v.version_id)}>
                  Retry
                </Button>
              ) : null,
          },
        ]}
      />
    </div>
  );
}
