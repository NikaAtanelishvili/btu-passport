// FE-02: show server validation errors under their fields, or as a toast when there are none.
import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";

export function applyServerErrors<T extends FieldValues>(
  form: { setError: UseFormSetError<T> },
  error: unknown,
): void {
  if (!(error instanceof ApiError)) {
    toast.error("Something went wrong. Please try again.");
    return;
  }
  const entries = Object.entries(error.fields);
  if (entries.length === 0) {
    toast.error(error.message);
    return;
  }
  for (const [name, message] of entries) {
    form.setError(name as Path<T>, { type: "server", message });
  }
}
