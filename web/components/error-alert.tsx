// A failed request as a destructive Alert (shared ErrorState, used by the verify pages first).
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ApiError } from "@/lib/api";

export function ErrorAlert({ error, title }: { error: Error; title?: string }) {
  const unreachable = !(error instanceof ApiError) || error.status >= 500;
  return (
    <Alert variant="destructive">
      <AlertTitle>{title ?? (unreachable ? "BTU's server can't be reached" : "Something went wrong")}</AlertTitle>
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>
  );
}
