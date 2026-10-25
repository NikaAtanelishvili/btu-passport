"use client";

// FE-21: dashboard (Web App Design A1). Counters refetch every 15 s and link to filtered
// lists; admins see Events only from here (the sidebar's Events is in the super admin group).
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { DisplayHeading } from "@/components/display";
import { DataTable } from "@/components/data-table";
import { ErrorAlert } from "@/components/error-alert";
import { StatusBadge, VersionPill } from "@/components/status-badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDateTime } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";
import { hasRole, useSession } from "@/lib/session";

type VersionRow = components["schemas"]["VersionRow"];

function Counter({ label, value, href }: { label: string; value: number | undefined; href?: string }) {
  const card = (
    <Card className={href ? "transition-colors hover:bg-muted/50" : undefined}>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="font-display text-5xl font-black">{value ?? "–"}</CardTitle>
      </CardHeader>
    </Card>
  );
  return href ? <Link href={href}>{card}</Link> : card;
}

export default function AdminDashboardPage() {
  const session = useSession();
  const superAdmin = session.data ? hasRole(session.data, "super_admin") : false;
  const dashboard = useQuery({
    queryKey: queryKeys.admin.dashboard,
    queryFn: async () => (await api.GET("/api/admin/dashboard")).data!,
    refetchInterval: 15_000,
  });
  const d = dashboard.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <DisplayHeading strong="Dashboard" />
        <div className="flex flex-wrap gap-2">
          <Link href="/admin/students/new" className={buttonVariants({ variant: "outline" })}>
            Register student
          </Link>
          <Link href="/admin/awards/new" className={buttonVariants({ variant: "outline" })}>
            Direct award
          </Link>
          {superAdmin && (
            <Link href="/admin/events/new" className={buttonVariants({ variant: "outline" })}>
              Create event
            </Link>
          )}
        </div>
      </div>

      {dashboard.isError && <ErrorAlert error={dashboard.error} />}

      <section className="space-y-2">
        <h2 className="font-display text-2xl font-black uppercase">Needs action</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Counter label="Check-in open now" value={d?.checkin_open} href="/admin/events?status=CHECKIN_OPEN" />
          <Counter
            label="Waiting to be marked done"
            value={d?.awaiting_completion}
            href="/admin/events?status=CHECKIN_CLOSED"
          />
          <Counter label="Unregistered check-ins" value={d?.unregistered_checkins} href="/admin/events?status=CHECKIN_CLOSED" />
          <Counter label="Failed issuances" value={d?.failed_versions} href="/admin/issuance?tab=failed" />
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="font-display text-2xl font-black uppercase">Recent activity</h2>
        <DataTable<VersionRow>
          rows={d?.recent}
          loading={dashboard.isPending}
          rowKey={(v) => v.version_id}
          empty="No passports issued yet."
          columns={[
            {
              header: "Student",
              cell: (v) => (
                <Link href={`/admin/students/${v.student_id}`} className="underline-offset-4 hover:underline">
                  {v.student_name}
                </Link>
              ),
            },
            { header: "Passport ID", cell: (v) => <span className="font-mono">{v.passport_id}</span> },
            { header: "Version", cell: (v) => <VersionPill versionNo={v.version_no} /> },
            { header: "Status", cell: (v) => <StatusBadge status={v.status} /> },
            { header: "Issued", cell: (v) => (v.issued_at ? formatDateTime(v.issued_at) : "–") },
          ]}
        />
      </section>
    </div>
  );
}
