"use client";

// Multi-select search over /api/admin/students?q= (Command in a Popover). Selected students
// show as removable badges under the trigger.
import { useQuery } from "@tanstack/react-query";
import { ChevronsUpDownIcon, XIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

export type PickedStudent = { student_id: string; name: string };

export function StudentPicker({
  id,
  value,
  onChange,
  invalid,
}: {
  id?: string;
  value: PickedStudent[];
  onChange: (value: PickedStudent[]) => void;
  invalid?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setQ(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const params = { q: q || undefined, page_size: 20 };
  const results = useQuery({
    queryKey: queryKeys.admin.students(params),
    queryFn: async () => (await api.GET("/api/admin/students", { params: { query: params } })).data!,
    enabled: open,
    placeholderData: (previous) => previous,
  });
  const picked = new Set(value.map((s) => s.student_id));

  function toggle(student: PickedStudent) {
    onChange(
      picked.has(student.student_id)
        ? value.filter((s) => s.student_id !== student.student_id)
        : [...value, student],
    );
  }

  return (
    <div className="space-y-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          render={
            <Button
              id={id}
              variant="outline"
              role="combobox"
              aria-expanded={open}
              aria-invalid={invalid}
              className="w-full justify-between font-normal"
            />
          }
        >
          {value.length ? `${value.length} selected` : "Search students…"}
          <ChevronsUpDownIcon className="opacity-50" />
        </PopoverTrigger>
        <PopoverContent className="w-(--anchor-width) p-0" align="start">
          <Command shouldFilter={false}>
            <CommandInput value={search} onValueChange={setSearch} placeholder="Name, Student ID or email" />
            <CommandList>
              <CommandEmpty>{results.isFetching ? "Searching…" : "No students found."}</CommandEmpty>
              {results.data?.items.map((s) => {
                const student = { student_id: s.student_id, name: `${s.first_name} ${s.last_name}` };
                return (
                  <CommandItem
                    key={s.student_id}
                    value={s.student_id}
                    data-checked={picked.has(s.student_id)}
                    onSelect={() => toggle(student)}
                  >
                    <span>{student.name}</span>
                    <span className="text-muted-foreground">{s.student_id}</span>
                  </CommandItem>
                );
              })}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((s) => (
            <Badge key={s.student_id} variant="secondary" className="gap-1">
              {s.name} · {s.student_id}
              <button type="button" aria-label={`Remove ${s.name}`} onClick={() => toggle(s)}>
                <XIcon className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
