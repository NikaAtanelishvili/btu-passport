// A failed request as an Alert in the "not valid" tint with an icon (shared ErrorState).
import { CircleXIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ApiError } from "@/lib/api";

export function ErrorAlert({ error, title }: { error: Error; title?: string }) {
  const unreachable = !(error instanceof ApiError) || error.status >= 500;
  return (
    <Alert
      variant="destructive"
      className="border-0 bg-status-invalid-soft text-black *:data-[slot=alert-description]:text-black *:[svg]:text-status-invalid-ink"
    >
      <CircleXIcon />
      <AlertTitle className="font-semibold">
        {title ?? (unreachable ? "BTU's server can't be reached" : "Something went wrong")}
      </AlertTitle>
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>
  );
}
