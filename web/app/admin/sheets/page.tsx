"use client";

// SH-07: Google Sheets (addendum §5). Last run, next scheduled run, Sync now, and every Sheet
// row's last decision (errors and flags first) with links to the student and version. Status
// refetches every 3 s while a run is queued or running, else every 15 s.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCwIcon, SheetIcon, UploadIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/data-table";
import { DisplayHeading } from "@/components/display";
import { ErrorAlert } from "@/components/error-alert";
import { Notice } from "@/components/notice";
import { OUTCOME_LABELS, OutcomeBadge, RunStatusBadge, countLines } from "@/components/sheet-outcome";
import { VersionPill } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDateTime } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";

type RecordRow = components["schemas"]["SheetRecordRow"];
type RunRow = components["schemas"]["SheetRunOut"];

const PAGE_SIZE = 25;
const ALL = "all";
const ATTENTION = "ERROR,CHANGED_AFTER_PROCESSING,REVOKED_IN_SHEET,CONFLICT";
const TABS = { "Verified Skills": "Verified Skills", Students: "Students", "Skills Catalog": "Skills Catalog" };
const OUTCOME_FILTERS: Record<string, string> = { [ATTENTION]: "Errors and flags", ...OUTCOME_LABELS };

function FilterSelect({
  label,
  value,
  onChange,
  items,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  items: Record<string, string>;
}) {
  const all = { [ALL]: label, ...items };
  return (
    <Select value={value} onValueChange={(v) => onChange((v as string | null) ?? ALL)} items={all}>
      <SelectTrigger aria-label={label} className="w-[calc(50%-0.375rem)] sm:w-56">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {Object.entries(all).map(([v, text]) => (
          <SelectItem key={v} value={v}>
            {text}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function RunSummary({ run }: { run: RunRow }) {
  const lines = countLines(run.counts);
  const versions = typeof run.counts.versions === "number" ? run.counts.versions : 0;
  return (
    <ul className="space-y-0.5 text-sm">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
      {run.status === "DONE" && <li>{versions ? `${versions} new version${versions === 1 ? "" : "s"}` : "No new versions"}</li>}
    </ul>
  );
}

export default function SheetsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [tab, setTab] = useState(ALL);
  const [outcome, setOutcome] = useState(ALL);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const status = useQuery({
    queryKey: queryKeys.admin.sheetStatus,
    queryFn: async () => (await api.GET("/api/admin/sheet-sync/status")).data!,
    refetchInterval: (query) => (query.state.data?.active_run_id ? 3_000 : 15_000),
  });
  const s = status.data;
  const lastRunKey = `${s?.last_run?.run_id}:${s?.last_run?.status}`;

  const params = {
    q: q || undefined,
    tab: tab === ALL ? undefined : tab,
    outcome: outcome === ALL ? undefined : outcome,
    page,
    page_size: PAGE_SIZE,
  };
  const records = useQuery({
    queryKey: queryKeys.admin.sheetRecords({ ...params, lastRunKey }),
    queryFn: async () => (await api.GET("/api/admin/sheet-sync/records", { params: { query: params } })).data!,
    placeholderData: keepPreviousData,
  });
  const runs = useQuery({
    queryKey: queryKeys.admin.sheetRuns(lastRunKey),
    queryFn: async () => (await api.GET("/api/admin/sheet-sync/runs", { params: { query: { page_size: 10 } } })).data!,
  });

  const syncNow = useMutation({
    mutationFn: async () => (await api.POST("/api/admin/sheet-sync")).data!,
    onSuccess: (r) => {
      toast.success(r.already_running ? `Run ${r.run_id} is already ${r.status.toLowerCase()}` : `Sync run ${r.run_id} queued`);
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.sheetStatus });
    },
    onError: (error) => toast.error(error.message),
  });

  // SH-11: the same three tabs as an .xlsx, through the same checks, as an Upload run.
  const fileInput = useRef<HTMLInputElement>(null);
  const importFile = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return (
        await api.POST("/api/admin/sheet-sync/upload", {
          // The generated type says string; openapi-fetch sends FormData as multipart as is.
          body: body as unknown as { file: string },
        })
      ).data!;
    },
    onSuccess: (run) => {
      if (run.status === "DONE") toast.success(`Imported ${run.source.replace(/^upload /, "")}: run ${run.run_id}`);
      else toast.error(`Import failed: ${run.error ?? "see the run"}`);
      void queryClient.invalidateQueries({ queryKey: ["admin", "sheets"] });
    },
    onError: (error) => toast.error(error instanceof ApiError && error.fields.file ? error.fields.file : error.message),
    onSettled: () => {
      if (fileInput.current) fileInput.current.value = "";
    },
  });

  function filter(set: (value: string) => void) {
    return (value: string) => {
      set(value);
      setPage(1);
    };
  }

  const busy = Boolean(s?.active_run_id) || syncNow.isPending;
  const last = s?.last_run;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <DisplayHeading strong="Google" light="Sheets" />
        <div className="flex flex-wrap gap-2">
          <input
            ref={fileInput}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="sr-only"
            aria-label="Excel file to import"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) importFile.mutate(file);
            }}
          />
          <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={busy || importFile.isPending}>
            <UploadIcon aria-hidden />
            {importFile.isPending ? "Importing…" : "Import Excel file"}
          </Button>
          <Button onClick={() => syncNow.mutate()} disabled={!s?.configured || busy || importFile.isPending}>
            <RefreshCwIcon className={busy ? "animate-spin" : undefined} aria-hidden />
            {busy ? "Syncing…" : "Sync now"}
          </Button>
        </div>
      </div>

      <p className="max-w-3xl text-base text-muted-foreground">
        BTU&apos;s official channel for students and verified skills. Staff enter records in the Google Sheet; every
        sync reads it, checks each row and issues new passport versions for new CONFIRMED records. Events and direct
        awards in this panel add to the same passports. An Excel file with the same three tabs (Students, Skills
        Catalog, Verified Skills) can be imported through the same checks.
      </p>

      {status.isError && <ErrorAlert error={status.error} />}
      {s && !s.configured && (
        <Notice icon={SheetIcon}>
          No Google Sheet is configured. Set <span className="font-mono">GOOGLE_SHEETS_ID</span> and the service account
          key in the server&apos;s environment; until then nothing is synced.
        </Notice>
      )}
      {last?.status === "FAILED" && (
        <Alert
          variant="destructive"
          className="border-0 bg-status-invalid-soft text-black *:data-[slot=alert-description]:text-black *:[svg]:text-status-invalid-ink"
        >
          <SheetIcon />
          <AlertTitle className="font-semibold">The last sync failed</AlertTitle>
          <AlertDescription>{last.error}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Last run</CardDescription>
            <CardTitle className="flex flex-wrap items-center gap-2 text-xl">
              {last ? (
                <>
                  {formatDateTime(last.finished_at ?? last.created_at)} <RunStatusBadge status={last.status} />
                </>
              ) : (
                "No runs yet"
              )}
            </CardTitle>
          </CardHeader>
          {last && (
            <CardContent>
              <RunSummary run={last} />
            </CardContent>
          )}
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Next scheduled run</CardDescription>
            <CardTitle className="text-xl">
              {s?.configured ? (s.next_run_at ? formatDateTime(s.next_run_at) : "–") : "Off"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-0.5 text-sm">
            {s && <p>Every {s.interval_seconds} seconds</p>}
            {s?.last_success_at && <p>Last successful sync {formatDateTime(s.last_success_at)}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Needs attention</CardDescription>
            <CardTitle className="font-display text-5xl font-black">{s ? s.errors + s.flags : "–"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-0.5 text-sm">
            {s && (
              <p>
                {s.errors} error{s.errors === 1 ? "" : "s"}, {s.flags} flag{s.flags === 1 ? "" : "s"}
              </p>
            )}
            {s && <p>Write-back to the Sheet {s.writeback ? "on" : "off"}</p>}
          </CardContent>
        </Card>
      </div>

      <section className="space-y-2">
        <h2 className="font-display text-2xl font-black uppercase">Records</h2>
        {records.isError && <ErrorAlert error={records.error} />}
        <DataTable<RecordRow>
          rows={records.data?.items}
          loading={records.isPending}
          rowKey={(r) => `${r.tab}:${r.key}`}
          total={records.data?.total}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={setPage}
          empty={q || tab !== ALL || outcome !== ALL ? "No records match." : "Nothing synced yet."}
          toolbar={
            <>
              <Input
                aria-label="Search records"
                placeholder="Search Record ID, Student ID or message"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full sm:w-80"
              />
              <FilterSelect label="All tabs" value={tab} onChange={filter(setTab)} items={TABS} />
              <FilterSelect label="All outcomes" value={outcome} onChange={filter(setOutcome)} items={OUTCOME_FILTERS} />
            </>
          }
          columns={[
            { header: "Tab", cell: (r) => r.tab },
            { header: "Row", cell: (r) => r.row_number },
            { header: "Record", cell: (r) => <span className="font-mono">{r.key.startsWith("@") ? "–" : r.key.split("@")[0]}</span> },
            { header: "Outcome", cell: (r) => <OutcomeBadge outcome={r.outcome} /> },
            { header: "Message", cell: (r) => r.message ?? "", className: "max-w-md whitespace-normal" },
            {
              header: "Student",
              cell: (r) =>
                r.student_id ? (
                  <Link href={`/admin/students/${r.student_id}`} className="font-mono underline-offset-4 hover:underline">
                    {r.student_id}
                  </Link>
                ) : (
                  "–"
                ),
            },
            {
              header: "Version",
              cell: (r) =>
                r.version_no && r.student_id ? (
                  <Link href={`/admin/students/${r.student_id}`} aria-label={`${r.passport_id} v${r.version_no}`}>
                    <VersionPill versionNo={r.version_no} />
                  </Link>
                ) : (
                  "–"
                ),
            },
            { header: "Decided", cell: (r) => formatDateTime(r.decided_at) },
          ]}
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-display text-2xl font-black uppercase">Recent runs</h2>
        {runs.isError && <ErrorAlert error={runs.error} />}
        <DataTable<RunRow>
          rows={runs.data?.items}
          loading={runs.isPending}
          rowKey={(r) => r.run_id}
          empty="No runs yet."
          columns={[
            { header: "Run", cell: (r) => <span className="font-mono">{r.run_id}</span> },
            { header: "Started", cell: (r) => formatDateTime(r.started_at ?? r.created_at) },
            { header: "Trigger", cell: (r) => ({ SCHEDULE: "Scheduled", MANUAL: "Sync now", UPLOAD: "Upload" })[r.trigger] ?? r.trigger },
            { header: "Status", cell: (r) => <RunStatusBadge status={r.status} /> },
            {
              header: "Result",
              cell: (r) => (r.error ? <span>{r.error}</span> : <RunSummary run={r} />),
              className: "max-w-md whitespace-normal",
            },
          ]}
        />
      </section>
    </div>
  );
}
