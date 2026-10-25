"use client";

// FE-40: My passport (Web App Design S1). The current (latest anchored) version with its code,
// verify link and downloads, and one card per skill. While a newer version is on its way the
// page says so and refetches every 5 s.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { CodeDisplay, copyText } from "@/components/code-display";
import { EmptyState } from "@/components/empty-state";
import { ErrorAlert } from "@/components/error-alert";
import { StampImage } from "@/components/stamp-image";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
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
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  const p = passport.data;
  const nothingYet = !p.current && !p.issuing && p.skills.length === 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">{p.holder_name}</CardTitle>
          <CardDescription>
            Passport ID <span className="font-mono">{p.passport_id}</span>
            {p.first_issued_on && ` · First issued ${formatDate(p.first_issued_on)}`}
          </CardDescription>
        </CardHeader>
      </Card>

      {p.issuing && (
        <Alert>
          <AlertTitle>Issuing version {p.issuing.version_no}…</AlertTitle>
          <AlertDescription>
            It appears here once it is anchored on the blockchain, usually within a minute.
          </AlertDescription>
        </Alert>
      )}

      {nothingYet && <EmptyState>No passport yet. Attend a BTU event to earn your first skill.</EmptyState>}
      {p.current && <CurrentVersion version={p.current} />}
      {!p.current && p.skills.length > 0 && (
        <Alert>
          <AlertDescription>
            These skills come from BTU&apos;s earlier records. They become part of a verifiable PDF with your next
            issued version.
          </AlertDescription>
        </Alert>
      )}

      {p.skills.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Skills</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {p.skills.map((s) => (
              <SkillCard key={`${s.name}-${s.date_earned}`} skill={s} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function CurrentVersion({ version }: { version: VersionSummary }) {
  const code = version.verification_code!;
  const verifyPath = `/v/${code}`;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Version {version.version_no}</CardTitle>
        <CardDescription>
          Issued {version.issued_at ? formatDate(version.issued_at) : "—"} · {version.skill_count} skill
          {version.skill_count === 1 ? "" : "s"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-sm text-muted-foreground">Verification code</p>
        <CodeDisplay code={code} />
        <p className="text-sm break-all">
          Anyone can check it at{" "}
          <Link href={verifyPath} className="underline underline-offset-4">
            {verifyPath}
          </Link>
        </p>
      </CardContent>
      <CardFooter className="flex flex-wrap gap-2">
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
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          {skill.stamp_sha256 && <StampImage sha256={skill.stamp_sha256} category={skill.category} />}
          <div className="min-w-0">
            <CardTitle>{skill.name}</CardTitle>
            <CardDescription>{skill.category}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {skill.description && <p>{skill.description}</p>}
        <p className="text-muted-foreground">
          Earned {formatDate(skill.date_earned)} ·{" "}
          {skill.source === "EVENT" && skill.event_name ? skill.event_name : "Awarded by BTU"}
        </p>
      </CardContent>
    </Card>
  );
}
