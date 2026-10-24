"use client";

// FE-22: students list (Web App Design A2): debounced search, filters, server paging.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DataTable } from "@/components/data-table";
import { ErrorAlert } from "@/components/error-alert";
import { StatusBadge } from "@/components/status-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { queryKeys } from "@/lib/query-keys";
import { EDUCATION_LEVELS, STUDENT_STATUSES } from "@/lib/students";

type StudentRow = components["schemas"]["StudentRow"];
const PAGE_SIZE = 25;
const ALL = "all";

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
      <SelectTrigger aria-label={label} className="w-44">
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

export default function StudentsPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [program, setProgram] = useState(ALL);
  const [level, setLevel] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const [issued, setIssued] = useState(ALL);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const params = {
    q: q || undefined,
    program: program === ALL ? undefined : program,
    education_level: level === ALL ? undefined : level,
    status: status === ALL ? undefined : status,
    has_passport: issued === ALL ? undefined : issued === "yes",
    page,
    page_size: PAGE_SIZE,
  };
  const students = useQuery({
    queryKey: queryKeys.admin.students(params),
    queryFn: async () => (await api.GET("/api/admin/students", { params: { query: params } })).data!,
    placeholderData: (previous) => previous,
  });
  const programs = useQuery({
    queryKey: queryKeys.admin.programs,
    queryFn: async () => (await api.GET("/api/admin/programs")).data!,
  });

  function filter(set: (v: string) => void) {
    return (v: string) => {
      set(v);
      setPage(1);
    };
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Students</h1>
        <div className="flex gap-2">
          <Tooltip>
            <TooltipTrigger render={<span />}>
              <Button variant="outline" disabled>
                Import CSV
              </Button>
            </TooltipTrigger>
            <TooltipContent>Coming later</TooltipContent>
          </Tooltip>
          <Link href="/admin/students/new" className={buttonVariants()}>
            Register student
          </Link>
        </div>
      </div>
      {students.isError && <ErrorAlert error={students.error} />}
      <DataTable<StudentRow>
        toolbar={
          <>
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, Student ID or email"
              aria-label="Search students"
              className="w-72"
            />
            <FilterSelect
              label="All programs"
              value={program}
              onChange={filter(setProgram)}
              items={Object.fromEntries((programs.data ?? []).map((p) => [p, p]))}
            />
            <FilterSelect label="All levels" value={level} onChange={filter(setLevel)} items={EDUCATION_LEVELS} />
            <FilterSelect label="All statuses" value={status} onChange={filter(setStatus)} items={STUDENT_STATUSES} />
            <FilterSelect
              label="Passport: any"
              value={issued}
              onChange={filter(setIssued)}
              items={{ yes: "Passport issued", no: "Not issued yet" }}
            />
          </>
        }
        rows={students.data?.items}
        loading={students.isPending}
        rowKey={(s) => s.student_id}
        total={students.data?.total}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        onRowClick={(s) => router.push(`/admin/students/${s.student_id}`)}
        empty="No students match."
        columns={[
          { header: "Student ID", cell: (s) => s.student_id },
          { header: "Name", cell: (s) => `${s.first_name} ${s.last_name}` },
          { header: "Program", cell: (s) => s.program },
          { header: "Passport ID", cell: (s) => s.passport_id ?? "–" },
          { header: "Version", cell: (s) => (s.latest_version_no ? `v${s.latest_version_no}` : "–") },
          { header: "Status", cell: (s) => (s.latest_status ? <StatusBadge status={s.latest_status} /> : "–") },
        ]}
      />
    </div>
  );
}
