"use client";

// FE-40: My passport (Web App Design S1). The current (latest anchored) version with its code,
// verify link and downloads, and one card per skill. While a newer version is on its way the
// page says so and refetches every 5 s.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { LoaderIcon } from "lucide-react";

import { CodeDisplay, copyText } from "@/components/code-display";
import { Asterisks, DisplayHeading } from "@/components/display";
import { EmptyState } from "@/components/empty-state";
import { ErrorAlert } from "@/components/error-alert";
import { Notice } from "@/components/notice";
import { StampImage } from "@/components/stamp-image";
import { StudentVersionBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";

type VersionSummary = components["schemas"]["VersionSummary"];
type SkillOnPassport = components["schemas"]["SkillOnPassport"];

export default function MyPassportPage() {
  const passport = useQuery({
    queryKey: queryKeys.me.passport,
    queryFn: async () => (await api.GET("/api/me/passport")).data!,
    refetchInterval: (query) => (query.state.data?.issuing ? 5000 : false),
  });

  if (passport.isError) return <ErrorAlert error={passport.error} />;
  if (passport.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-72 w-full rounded-[28px]" />
        <Skeleton className="h-48 w-full rounded-[24px]" />
      </div>
    );
  }
  const p = passport.data;
  const nothingYet = !p.current && !p.issuing && p.skills.length === 0;

  return (
    <div className="space-y-8">
      <section className="rounded-[28px] border-[1.5px] border-foreground p-6 sm:p-12">
        <div className="flex items-start justify-between gap-4">
          <DisplayHeading strong="AI Skills" light="Digital Passport" className="text-[clamp(2.25rem,6.5vw,6rem)]" />
          <Asterisks className="text-[2.5rem] sm:text-[3.5rem]" />
        </div>
        <Separator className="my-6 sm:my-8" />
        <dl className="grid gap-5 sm:grid-cols-4">
          <PassportField label="Name">{p.first_name}</PassportField>
          <PassportField label="Surname">{p.last_name}</PassportField>
          <PassportField label="Passport ID" mono>
            {p.passport_id}
          </PassportField>
          <PassportField label="First issued">{p.first_issued_on ? formatDate(p.first_issued_on) : "Not yet"}</PassportField>
        </dl>
      </section>

      {p.issuing && (
        <Notice icon={LoaderIcon} spin>
          <strong>Issuing version {p.issuing.version_no}…</strong> It appears here once it is anchored on the
          blockchain, usually within a minute.
        </Notice>
      )}

      {nothingYet && <EmptyState>No passport yet. Attend a BTU event to earn your first skill.</EmptyState>}
      {p.current && <CurrentVersion version={p.current} />}
      {!p.current && p.skills.length > 0 && (
        <Notice>
          These skills come from BTU&apos;s earlier records. They become part of a verifiable PDF with your next
          issued version.
        </Notice>
      )}

      {p.skills.length > 0 && (
        <section className="space-y-4">
          <h2 className="flex items-center gap-3 font-display text-3xl font-black uppercase sm:text-4xl">
            Skills
            <span className="grid size-9 place-items-center rounded-full bg-foreground font-sans text-base font-semibold text-background sm:size-10 sm:text-lg">
              {p.skills.length}
            </span>
          </h2>
          <div className="grid gap-4 md:grid-cols-2 md:gap-6">
            {p.skills.map((s) => (
              <SkillCard key={`${s.name}-${s.date_earned}`} skill={s} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function PassportField({ label, mono = false, children }: { label: string; mono?: boolean; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="font-display text-sm font-extrabold uppercase sm:text-base">{label}:</dt>
      <dd className={mono ? "mt-1 font-mono text-2xl sm:text-[1.75rem]" : "mt-1 font-display text-2xl sm:text-3xl"}>
        {children}
      </dd>
    </div>
  );
}

function CurrentVersion({ version }: { version: VersionSummary }) {
  const code = version.verification_code!;
  const verifyPath = `/v/${code}`;
  return (
    <Card className="gap-5 rounded-[24px]! py-6 sm:py-8">
      <CardHeader className="px-6 sm:px-8">
        <div className="flex flex-wrap items-center gap-3">
          <CardTitle className="font-display text-3xl font-black uppercase">Version {version.version_no}</CardTitle>
          <StudentVersionBadge version={version} />
        </div>
        <CardDescription className="text-base">
          Issued {version.issued_at ? formatDate(version.issued_at) : "—"} · {version.skill_count} skill
          {version.skill_count === 1 ? "" : "s"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 px-6 sm:px-8">
        <p className="eyebrow text-muted-foreground">Verification code</p>
        <CodeDisplay code={code} />
        <p className="break-all">
          Anyone can check it at{" "}
          <Link href={verifyPath} className="font-medium text-link underline underline-offset-4">
            {verifyPath}
          </Link>
        </p>
      </CardContent>
      <CardFooter className="flex flex-wrap gap-3 border-t-0 bg-transparent px-6 sm:px-8">
        <a href={`/api/me/versions/${version.version_no}/pdf`} className={buttonVariants()}>
          Download PDF
        </a>
        <Button
          variant="outline"
          onClick={() => copyText(`${window.location.origin}${verifyPath}`, "Verify link copied")}
        >
          Copy verify link
        </Button>
        <a
          href={`/api/me/versions/${version.version_no}/proof.json`}
          className={buttonVariants({ variant: "outline" })}
        >
          Download proof.json
        </a>
      </CardFooter>
    </Card>
  );
}

function SkillCard({ skill }: { skill: SkillOnPassport }) {
  return (
    <article className="flex flex-col rounded-[24px] border p-6 sm:p-8">
      <div className="flex items-start gap-5">
        {skill.stamp_sha256 && <StampImage sha256={skill.stamp_sha256} category={skill.category} size={88} />}
        <div className="min-w-0 space-y-2">
          <Badge variant="outline" className="h-7 border-[1.5px] border-foreground px-3 text-sm">
            {skill.category}
          </Badge>
          <h3 className="font-display text-2xl leading-tight font-extrabold sm:text-[1.75rem]">{skill.name}</h3>
        </div>
      </div>
      {skill.description && <p className="mt-5 text-lg">{skill.description}</p>}
      <Separator className="mt-5 mb-4" />
      <p className="text-muted-foreground">
        Earned {formatDate(skill.date_earned)} ·{" "}
        {skill.source === "EVENT" && skill.event_name ? skill.event_name : "Awarded by BTU"}
      </p>
    </article>
  );
}
