"use client";

// Program on the student forms: a combobox (Command in a Popover, like the student picker)
// over /api/admin/programs, with "Use "<typed>" as a new program" when nothing matches
// exactly. Sends the same string as the text field it replaces.
import { useQuery } from "@tanstack/react-query";
import { ChevronsUpDownIcon, PlusIcon } from "lucide-react";
import { useState } from "react";
import { Controller, type FieldValues, type Path, type UseFormReturn } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";

/** Existing programs containing `search` (case-insensitive), an exact match first so Enter
 *  picks what was typed, and whether `search` should be offered as a new program (non-empty,
 *  no exact case-insensitive match). */
export function matchPrograms(programs: string[], search: string): { matches: string[]; offerNew: boolean } {
  const typed = search.trim().toLowerCase();
  if (!typed) return { matches: programs, offerNew: false };
  const exact = programs.filter((p) => p.toLowerCase() === typed);
  const partial = programs.filter((p) => p.toLowerCase() !== typed && p.toLowerCase().includes(typed));
  return { matches: [...exact, ...partial], offerNew: exact.length === 0 };
}

export function ProgramField<T extends FieldValues>({ form, name }: { form: UseFormReturn<T>; name: Path<T> }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const programs = useQuery({
    queryKey: queryKeys.admin.programs,
    queryFn: async () => (await api.GET("/api/admin/programs")).data!,
  });

  return (
    <Controller
      name={name}
      control={form.control}
      render={({ field, fieldState }) => {
        const { matches, offerNew } = matchPrograms(programs.data ?? [], search);
        const choose = (program: string) => {
          field.onChange(program);
          setOpen(false);
        };
        return (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor={name}>Program</FieldLabel>
            {/* Flex gap, not space-y: see StudentPicker (Base UI focus guards). */}
            <div className="flex flex-col">
              <Popover
                open={open}
                onOpenChange={(next) => {
                  setOpen(next);
                  if (next) setSearch("");
                  else field.onBlur();
                }}
              >
                <PopoverTrigger
                  render={
                    <Button
                      id={name}
                      ref={field.ref}
                      variant="outline"
                      role="combobox"
                      aria-expanded={open}
                      aria-invalid={fieldState.invalid}
                      className="w-full justify-between font-normal"
                    />
                  }
                >
                  <span className={cn("truncate", !field.value && "text-muted-foreground")}>
                    {field.value || "Choose or type a program"}
                  </span>
                  <ChevronsUpDownIcon className="opacity-50" />
                </PopoverTrigger>
                <PopoverContent className="w-(--anchor-width) p-0" align="start">
                  <Command shouldFilter={false}>
                    <CommandInput value={search} onValueChange={setSearch} placeholder="Search or type a new program" />
                    <CommandList>
                      <CommandEmpty>{programs.isPending ? "Loading…" : "Type a program name."}</CommandEmpty>
                      {matches.map((program) => (
                        <CommandItem
                          key={program}
                          value={program}
                          data-checked={program === field.value}
                          onSelect={() => choose(program)}
                        >
                          <span className="min-w-0 flex-1">{program}</span>
                        </CommandItem>
                      ))}
                      {offerNew && (
                        <CommandItem value={`new:${search}`} onSelect={() => choose(search.trim())}>
                          <PlusIcon />
                          <span className="min-w-0 flex-1">
                            Use &ldquo;{search.trim()}&rdquo; as a new program
                          </span>
                        </CommandItem>
                      )}
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>
            {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
          </Field>
        );
      }}
    />
  );
}
