"use client";

// A verification code as printed (XXXX-XXXX-XX) with a copy button (Frontend tab §3).
import { CopyIcon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatCode } from "@/lib/format";

/** The clipboard API needs a secure context (not a phone on http://<LAN IP>); say so. */
export async function copyText(text: string, done: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(done);
  } catch {
    toast.error("Couldn't copy here. Select the text and copy it instead.");
  }
}

export function CodeDisplay({ code }: { code: string }) {
  const shown = formatCode(code);
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-2xl tracking-wider select-all sm:text-3xl">{shown}</span>
      <Tooltip>
        <TooltipTrigger
          render={<Button variant="ghost" size="icon" aria-label="Copy code" onClick={() => copyText(shown, "Code copied")} />}
        >
          <CopyIcon />
        </TooltipTrigger>
        <TooltipContent>Copy code</TooltipContent>
      </Tooltip>
    </div>
  );
}
