"use client";

// FE-53: audit log (Web App Design A12, FR-09), super admin only. Filters: person (part of the
// email, debounced), action, and a date range in BTU's calendar days; newest first, server paging.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { DisplayHeading } from "@/components/display";
import { DataTable } from "@/components/data-table";
import { ErrorAlert } from "@/components/error-alert";
import { RequireRole } from "@/components/require-role";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDateTime } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";

type AuditRow = components["schemas"]["AuditRow"];

const PAGE_SIZE = 25;
const ALL = "all";

// Entities with a page of their own; the rest (award submissions, versions) show as text.
function entityHref(row: AuditRow): string | null {
  switch (row.entity) {
    case "student":
      return `/admin/students/${encodeURIComponent(row.entity_id)}`;
    case "event":
      return `/admin/events/${encodeURIComponent(row.entity_id)}`;
    case "skill":
      return "/admin/skills";
    case "category":
      return "/admin/categories";
    case "user_role":
      return "/admin/roles";
    default:
      return null;
  }
}

export default function AuditPage() {
  return (
    <RequireRole role="super_admin">
      <Audit />
    </RequireRole>
  );
}

function Audit() {
  const [search, setSearch] = useState("");
  const [actor, setActor] = useState("");
  const [action, setAction] = useState(ALL);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = setTimeout(() => {
      setActor(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const params = {
    actor: actor || undefined,
    action: action === ALL ? undefined : action,
    from: from || undefined,
    to: to || undefined,
    page,
    page_size: PAGE_SIZE,
  };
  const audit = useQuery({
    queryKey: queryKeys.admin.audit(params),
    queryFn: async () => (await api.GET("/api/admin/audit", { params: { query: params } })).data!,
    placeholderData: keepPreviousData,
  });
  const actions = useQuery({
    queryKey: queryKeys.admin.auditActions,
    queryFn: async () => (await api.GET("/api/admin/audit/actions")).data!,
  });
  // A range that ends before it starts comes back as 422 with fields.to.
  const fieldErrors = audit.error instanceof ApiError ? audit.error.fields : {};
  const actionItems = { [ALL]: "All actions", ...Object.fromEntries((actions.data ?? []).map((a) => [a, a])) };

  const setDate = (set: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    set(e.target.value);
    setPage(1);
  };

  return (
    <div className="space-y-4">
      <DisplayHeading strong="Audit" light="log" />
      {audit.isError && !fieldErrors.to && <ErrorAlert error={audit.error} />}
      <DataTable<AuditRow>
        toolbar={
          <>
            <Field className="w-64">
              <FieldLabel htmlFor="audit-actor">Person</FieldLabel>
              <Input
                id="audit-actor"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Email"
              />
            </Field>
            <Field className="w-52">
              <FieldLabel htmlFor="audit-action">Action</FieldLabel>
              <Select
                value={action}
                onValueChange={(v) => {
                  setAction((v as string | null) ?? ALL);
                  setPage(1);
                }}
                items={actionItems}
              >
                <SelectTrigger id="audit-action" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(actionItems).map(([v, text]) => (
                    <SelectItem key={v} value={v}>
                      {text}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field className="w-40">
              <FieldLabel htmlFor="audit-from">From</FieldLabel>
              <Input id="audit-from" type="date" value={from} max={to || undefined} onChange={setDate(setFrom)} />
            </Field>
            <Field className="w-40" data-invalid={!!fieldErrors.to}>
              <FieldLabel htmlFor="audit-to">To</FieldLabel>
              <Input
                id="audit-to"
                type="date"
                value={to}
                min={from || undefined}
                aria-invalid={!!fieldErrors.to}
                onChange={setDate(setTo)}
              />
              {fieldErrors.to && <FieldError>{fieldErrors.to}</FieldError>}
            </Field>
          </>
        }
        rows={audit.data?.items}
        loading={audit.isPending}
        rowKey={(r) => r.id}
        total={audit.data?.total}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        empty="No entries match."
        mobileCard={(r) => (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Badge variant="outline">{r.action}</Badge>
              <span className="text-muted-foreground">{formatDateTime(r.at)}</span>
            </div>
            <p className="break-all">{r.actor_email ?? "System"}</p>
            <p className="break-all text-muted-foreground">
              <Entity row={r} />
            </p>
            <Details row={r} />
          </>
        )}
        columns={[
          { header: "Time", cell: (r) => formatDateTime(r.at) },
          { header: "Who", cell: (r) => r.actor_email ?? <span className="text-muted-foreground">System</span> },
          { header: "Action", cell: (r) => <Badge variant="outline">{r.action}</Badge> },
          { header: "Entity", cell: (r) => <Entity row={r} /> },
          { header: "Details", cell: (r) => <Details row={r} />, className: "whitespace-normal" },
        ]}
      />
    </div>
  );
}

function Entity({ row }: { row: AuditRow }) {
  const href = entityHref(row);
  const label = `${row.entity} ${row.entity_id}`;
  return href ? (
    <Link href={href} className="underline-offset-4 hover:underline">
      {label}
    </Link>
  ) : (
    label
  );
}

function Details({ row }: { row: AuditRow }) {
  if (!row.before && !row.after) return <span className="text-muted-foreground">—</span>;
  return (
    <Collapsible>
      <CollapsibleTrigger className={buttonVariants({ variant: "ghost", size: "sm" })}>Show</CollapsibleTrigger>
      <CollapsibleContent className="grid gap-2 pt-2 sm:grid-cols-2">
        {(["before", "after"] as const).map((key) => (
          <div key={key} className="min-w-0">
            <p className="text-xs font-medium text-muted-foreground">{key === "before" ? "Before" : "After"}</p>
            <pre className="overflow-x-auto rounded-md bg-muted p-2 text-xs">
              {row[key] ? JSON.stringify(row[key], null, 2) : "—"}
            </pre>
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
