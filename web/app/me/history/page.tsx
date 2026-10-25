"use client";

// FE-41: version history (Web App Design S2), newest first. Only anchored versions have a PDF;
// the seed's legacy V1 is listed as "Legacy, not verifiable".
import { useQuery } from "@tanstack/react-query";

import { DataTable } from "@/components/data-table";
import { DisplayHeading } from "@/components/display";
import { ErrorAlert } from "@/components/error-alert";
import { StudentVersionBadge } from "@/components/status-badge";
import { buttonVariants } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";

type VersionSummary = components["schemas"]["VersionSummary"];
const IN_PROGRESS = new Set(["PENDING", "RENDERED", "ANCHORING"]);

const changed = (v: VersionSummary) => v.added_skills.map((s) => `+ ${s}`).join(", ");

function download(v: VersionSummary) {
  return (
    <a href={`/api/me/versions/${v.version_no}/pdf`} className={buttonVariants({ variant: "outline", size: "sm" })}>
      Download PDF
    </a>
  );
}

export default function HistoryPage() {
  const versions = useQuery({
    queryKey: queryKeys.me.versions,
    queryFn: async () => (await api.GET("/api/me/versions")).data!,
    refetchInterval: (query) => (query.state.data?.some((v) => IN_PROGRESS.has(v.status)) ? 5000 : false),
  });
  return (
    <div className="space-y-6">
      <DisplayHeading strong="Version" light="history" />
      {versions.isError && <ErrorAlert error={versions.error} />}
      <DataTable<VersionSummary>
        rows={versions.data}
        loading={versions.isPending}
        rowKey={(v) => v.version_no}
        empty="No versions yet. Your first appears when BTU issues your passport."
        mobileCard={(v) => (
          <>
            <div className="flex items-center justify-between gap-2">
              <p className="font-display text-xl font-extrabold">Version {v.version_no}</p>
              <StudentVersionBadge version={v} />
            </div>
            <p className="text-muted-foreground">
              {v.issued_at ? formatDate(v.issued_at) : "Not issued yet"} · {v.skill_count} skill
              {v.skill_count === 1 ? "" : "s"}
            </p>
            {v.added_skills.length > 0 && <p>{changed(v)}</p>}
            {v.status === "ANCHORED" && <div className="pt-2">{download(v)}</div>}
          </>
        )}
        columns={[
          { header: "Version", cell: (v) => <span className="font-display text-lg font-extrabold">v{v.version_no}</span> },
          { header: "Issued", cell: (v) => (v.issued_at ? formatDate(v.issued_at) : "—") },
          { header: "Skills", cell: (v) => v.skill_count },
          {
            header: "What changed",
            cell: (v) => (v.added_skills.length ? changed(v) : "—"),
            className: "whitespace-normal",
          },
          { header: "Status", cell: (v) => <StudentVersionBadge version={v} /> },
          {
            header: "Download",
            cell: (v) => (v.status === "ANCHORED" ? download(v) : null),
          },
        ]}
      />
    </div>
  );
}
