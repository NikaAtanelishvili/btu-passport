"use client";

// FE-32: presenter view (Web App Design A8) for the room's screen: no shell, a large QR that
// is refetched when its token runs out (tokens rotate every 30 s), the link as text and a
// live count. Super admins only (the QR route is too).
import { useQuery } from "@tanstack/react-query";
import { ClockIcon } from "lucide-react";
import { useParams } from "next/navigation";

import { BtuLogo, Wordmark } from "@/components/brand";
import { DisplayHeading } from "@/components/display";
import { ErrorAlert } from "@/components/error-alert";
import { RequireRole } from "@/components/require-role";
import { StampImage } from "@/components/stamp-image";
import { api } from "@/lib/api";
import { formatTime, splitTitle } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";

export default function PresenterPage() {
  return (
    // Covers the site header: the projector shows only this.
    <div className="fixed inset-0 z-50 overflow-auto bg-background p-4 sm:p-10">
      <RequireRole role="super_admin">
        <Presenter />
      </RequireRole>
    </div>
  );
}

const PILL = "inline-flex h-11 items-center gap-2 rounded-xl px-4 font-display text-base font-extrabold uppercase sm:h-12 sm:text-xl";

function Presenter() {
  const { id } = useParams<{ id: string }>();
  const event = useQuery({
    queryKey: queryKeys.admin.event(id),
    queryFn: async () => (await api.GET("/api/admin/events/{event_id}", { params: { path: { event_id: id } } })).data!,
    refetchInterval: 15_000,
  });
  const qr = useQuery({
    queryKey: queryKeys.admin.qr(id),
    queryFn: async () => (await api.GET("/api/admin/events/{event_id}/qr", { params: { path: { event_id: id } } })).data!,
    // Just after the token's window ends, and at least every 30 s.
    refetchInterval: (q) => Math.min(30, q.state.data?.refresh_in_seconds ?? 30) * 1000 + 250,
    refetchIntervalInBackground: true,
  });

  if (qr.isError) return <ErrorAlert error={qr.error} />;
  const q = qr.data;
  const e = event.data;
  const open = q?.status === "CHECKIN_OPEN" && q.svg && q.url;
  const [strong, light] = splitTitle(e?.name ?? " ");

  return (
    <div className="mx-auto flex min-h-full max-w-[1400px] flex-col gap-8 sm:gap-10">
      <header className="overflow-hidden rounded-[28px] bg-black text-white">
        <div className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div className="flex items-center gap-3">
            <BtuLogo height={52} />
            <span className="h-14 w-px bg-white/60" aria-hidden />
            <Wordmark className="sm:text-[1.75rem]" />
          </div>
          <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
            {q && (
              <span
                className={cn(
                  PILL,
                  q.status === "CHECKIN_OPEN" ? "bg-status-valid text-black" : "bg-white/15 text-white",
                )}
              >
                <span className="size-3 rounded-full bg-current" aria-hidden />
                {q.status === "CHECKIN_OPEN"
                  ? "Check-in open"
                  : q.status === "DRAFT"
                    ? "Check-in not open yet"
                    : "Check-in closed"}
              </span>
            )}
            {e && q?.status === "CHECKIN_OPEN" && (
              <span className={cn(PILL, "border-[1.5px] border-white")}>
                <ClockIcon className="size-5" aria-hidden /> Closes {formatTime(e.checkin_closes_at)}
              </span>
            )}
          </div>
        </div>
        <div className="h-2 bg-brand-stripe" aria-hidden />
      </header>

      <div className="grid flex-1 content-start items-start gap-10 lg:grid-cols-2 lg:gap-16">
        <div className="space-y-8">
          <p className="eyebrow text-lg text-link sm:text-2xl">Scan to check in</p>
          <DisplayHeading strong={strong} light={light} className="text-[clamp(2.75rem,6vw,6rem)]" />
          {e && (
            <div className="flex items-center gap-5">
              {e.skill.stamp_sha256 && (
                <StampImage sha256={e.skill.stamp_sha256} category={e.skill.category} size={88} />
              )}
              <div>
                <p className="text-lg text-muted-foreground sm:text-xl">Everyone checked in earns</p>
                <p className="font-display text-2xl leading-tight font-extrabold sm:text-3xl">{e.skill.name}</p>
              </div>
            </div>
          )}
          <div className="border-t pt-8">
            <p className="eyebrow text-lg sm:text-2xl">Checked in</p>
            <p className="font-display text-[clamp(6rem,14vw,11rem)] leading-[0.85] font-black text-primary">
              {q?.participant_count ?? 0}
            </p>
          </div>
        </div>

        <div className="flex flex-col items-center gap-4">
          {open ? (
            <>
              <div
                className="aspect-square w-full max-w-[min(70vh,600px)] rounded-[28px] border-[1.5px] border-foreground p-4 sm:p-8 [&>svg]:size-full"
                // The SVG is generated by our own API (segno), not user input.
                dangerouslySetInnerHTML={{ __html: q.svg! }}
              />
              <p className="text-center text-lg text-muted-foreground sm:text-xl">
                Open your phone camera and point it at the code
              </p>
              <p className="text-center text-sm text-muted-foreground">
                or open <span className="font-mono break-all text-foreground">{q.url}</span>
              </p>
            </>
          ) : (
            <div className="grid aspect-square w-full max-w-[min(70vh,600px)] place-items-center rounded-[28px] border-[1.5px] border-dashed border-foreground p-8 text-center">
              <p className="font-display text-3xl leading-tight font-extrabold uppercase sm:text-4xl">
                {q?.status === "DRAFT" ? "Check-in hasn't opened yet" : q ? "Check-in closed" : "Loading…"}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
