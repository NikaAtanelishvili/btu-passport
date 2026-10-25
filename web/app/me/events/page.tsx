"use client";

// FE-34: My events (Web App Design S3): every event the student checked in to and what
// became of it.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { DataTable } from "@/components/data-table";
import { ErrorAlert } from "@/components/error-alert";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";

type MyEvent = components["schemas"]["MyEvent"];

function status(e: MyEvent): React.ReactNode {
  switch (e.status) {
    case "WAITING":
      return "Waiting for organiser";
    case "AWARDED":
      return (
        <Link href="/me" className="underline underline-offset-4">
          Awarded in v{e.version_no}
        </Link>
      );
    case "ALREADY_HELD":
      return "Already held";
    case "NOT_CONFIRMED":
      return "Not confirmed";
    case "EVENT_DELETED":
      return "Event deleted";
  }
}

export default function MyEventsPage() {
  const events = useQuery({
    queryKey: queryKeys.me.events,
    queryFn: async () => (await api.GET("/api/me/events")).data!,
  });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">My events</h1>
      {events.isError && <ErrorAlert error={events.error} />}
      <DataTable<MyEvent>
        rows={events.data}
        loading={events.isPending}
        rowKey={(e) => e.event_id}
        empty="No check-ins yet. Scan the QR code at a BTU event to check in."
        mobileCard={(e) => (
          <>
            <p className="font-medium">{e.name}</p>
            <p className="text-muted-foreground">
              {formatDate(e.event_date)} · {e.skill_name}
            </p>
            <p>{status(e)}</p>
          </>
        )}
        columns={[
          { header: "Event", cell: (e) => e.name },
          { header: "Date", cell: (e) => formatDate(e.event_date) },
          { header: "Skill", cell: (e) => e.skill_name },
          { header: "Status", cell: status },
        ]}
      />
    </div>
  );
}
