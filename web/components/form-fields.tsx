"use client";

// Text and select fields for react-hook-form: label, control and the field's error (from zod
// or the server, via applyServerErrors) underneath.
import { Controller, type FieldValues, type Path, type UseFormReturn } from "react-hook-form";

import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function TextField<T extends FieldValues>({
  form,
  name,
  label,
  ...input
}: {
  form: UseFormReturn<T>;
  name: Path<T>;
  label: string;
} & Omit<React.ComponentProps<typeof Input>, "form" | "name">) {
  return (
    <Controller
      name={name}
      control={form.control}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldLabel htmlFor={name}>{label}</FieldLabel>
          <Input {...input} {...field} id={name} aria-invalid={fieldState.invalid} />
          {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
        </Field>
      )}
    />
  );
}

export function SelectField<T extends FieldValues>({
  form,
  name,
  label,
  items,
}: {
  form: UseFormReturn<T>;
  name: Path<T>;
  label: string;
  items: Record<string, string>;
}) {
  return (
    <Controller
      name={name}
      control={form.control}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldLabel htmlFor={name}>{label}</FieldLabel>
          <Select value={field.value} onValueChange={field.onChange} items={items}>
            <SelectTrigger id={name} aria-invalid={fieldState.invalid} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(items).map(([value, text]) => (
                <SelectItem key={value} value={value}>
                  {text}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
        </Field>
      )}
    />
  );
}
