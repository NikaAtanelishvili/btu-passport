"use client";

// FE-34: My events (Web App Design S3): every event the student checked in to and what
// became of it.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { CheckIcon, ClockIcon, XIcon } from "lucide-react";

import { DataTable } from "@/components/data-table";
import { DisplayHeading } from "@/components/display";
import { ErrorAlert } from "@/components/error-alert";
import { StatusPill } from "@/components/status-badge";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";

type MyEvent = components["schemas"]["MyEvent"];

function status(e: MyEvent): React.ReactNode {
  switch (e.status) {
    case "WAITING":
      return <StatusPill look="pending" icon={ClockIcon} label="Waiting for organiser" />;
    case "AWARDED":
      return (
        <Link href="/me" className="rounded-full focus-visible:outline-2">
          <StatusPill look="valid" icon={CheckIcon} label={`Awarded in v${e.version_no}`} />
        </Link>
      );
    case "ALREADY_HELD":
      return <StatusPill look="navy" icon={CheckIcon} label="Already held" />;
    case "NOT_CONFIRMED":
      return <StatusPill look="invalid" icon={XIcon} label="Not confirmed" />;
    case "EVENT_DELETED":
      return <StatusPill look="invalid" icon={XIcon} label="Event deleted" />;
  }
}

export default function MyEventsPage() {
  const events = useQuery({
    queryKey: queryKeys.me.events,
    queryFn: async () => (await api.GET("/api/me/events")).data!,
  });
  return (
    <div className="space-y-6">
      <DisplayHeading strong="My" light="events" />
      {events.isError && <ErrorAlert error={events.error} />}
      <DataTable<MyEvent>
        rows={events.data}
        loading={events.isPending}
        rowKey={(e) => e.event_id}
        empty="No check-ins yet. Scan the QR code at a BTU event to check in."
        mobileCard={(e) => (
          <>
            <p className="font-display text-xl font-extrabold">{e.name}</p>
            <p className="text-muted-foreground">
              {formatDate(e.event_date)} · {e.skill_name}
            </p>
            <div className="pt-1">{status(e)}</div>
          </>
        )}
        columns={[
          { header: "Event", cell: (e) => <span className="font-medium">{e.name}</span> },
          { header: "Date", cell: (e) => formatDate(e.event_date) },
          { header: "Skill", cell: (e) => e.skill_name },
          { header: "Status", cell: status },
        ]}
      />
    </div>
  );
}
