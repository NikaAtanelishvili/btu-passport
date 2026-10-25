"use client";

// FE-30: events list (Web App Design A6). Tabs by status, kept in ?status= so the dashboard
// counters can link to one. Admins see it read-only (DEFAULT(Q14)).
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { DisplayHeading } from "@/components/display";
import { DataTable } from "@/components/data-table";
import { ErrorAlert } from "@/components/error-alert";
import { EventStatusBadge } from "@/components/status-badge";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { EVENT_STATUS_LABELS, type EventStatus } from "@/lib/events";
import { formatDateTime } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";
import { hasRole, useSession } from "@/lib/session";

type EventRow = components["schemas"]["EventRow"];
const PAGE_SIZE = 25;
const STATUSES = Object.keys(EVENT_STATUS_LABELS) as EventStatus[];

export default function EventsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <Events />
    </Suspense>
  );
}

function Events() {
  const router = useRouter();
  const pathname = usePathname();
  const session = useSession();
  const superAdmin = session.data ? hasRole(session.data, "super_admin") : false;
  const requested = useSearchParams().get("status");
  const status: EventStatus = STATUSES.includes(requested as EventStatus) ? (requested as EventStatus) : "DRAFT";
  const [page, setPage] = useState(1);

  const params = { status, page, page_size: PAGE_SIZE };
  const events = useQuery({
    queryKey: queryKeys.admin.events(params),
    queryFn: async () => (await api.GET("/api/admin/events", { params: { query: params } })).data!,
    refetchInterval: 15_000,
    placeholderData: (previous) => previous,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <DisplayHeading strong="Events" />
        {superAdmin && (
          <Link href="/admin/events/new" className={buttonVariants()}>
            Create event
          </Link>
        )}
      </div>
      <Tabs
        value={status}
        onValueChange={(v) => {
          setPage(1);
          router.replace(`${pathname}?status=${String(v)}`);
        }}
      >
        <TabsList className="max-w-full justify-start overflow-x-auto">
          {STATUSES.map((s) => (
            <TabsTrigger key={s} value={s}>
              {EVENT_STATUS_LABELS[s]}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {events.isError && <ErrorAlert error={events.error} />}
      <DataTable<EventRow>
        rows={events.data?.items}
        loading={events.isPending}
        rowKey={(e) => e.event_id}
        total={events.data?.total}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        onRowClick={(e) => router.push(`/admin/events/${e.event_id}`)}
        empty={`No ${EVENT_STATUS_LABELS[status].toLowerCase()} events.`}
        columns={[
          { header: "Name", cell: (e) => e.name },
          { header: "Skill", cell: (e) => e.skill_name },
          { header: "Date", cell: (e) => formatDateTime(e.starts_at) },
          { header: "Participants", cell: (e) => e.participant_count },
          { header: "Status", cell: (e) => <EventStatusBadge status={e.status} /> },
        ]}
      />
    </div>
  );
}
