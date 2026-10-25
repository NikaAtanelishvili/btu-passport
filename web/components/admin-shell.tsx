"use client";

// FE-20: admin sidebar (Operations, and Super admin for SUPER_ADMIN only), with the user's
// email, role and Sign out in its footer. On phones the pages are one row of pills (design).
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { hasRole, signOut, useSession } from "@/lib/session";

type NavItem = { href: string; label: string; exact?: boolean };

const OPERATIONS: NavItem[] = [
  { href: "/admin", label: "Dashboard", exact: true },
  { href: "/admin/students", label: "Students" },
  { href: "/admin/awards/new", label: "Direct award" },
  { href: "/admin/issuance", label: "Issuance" },
];

const SUPER_ADMIN: NavItem[] = [
  { href: "/admin/events", label: "Events" },
  { href: "/admin/skills", label: "Skills" },
  { href: "/admin/categories", label: "Categories & stamps" },
  { href: "/admin/roles", label: "Admins & roles" },
  { href: "/admin/audit", label: "Audit log" },
];

function useActive() {
  const pathname = usePathname();
  return (item: NavItem) => (item.exact ? pathname === item.href : pathname.startsWith(item.href));
}

function NavLinks({ items }: { items: NavItem[] }) {
  const isActive = useActive();
  return (
    <ul className="space-y-1">
      {items.map((item) => {
        const active = isActive(item);
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-11 items-center rounded-md px-4 text-base font-medium",
                active ? "bg-stamp-navy text-white" : "hover:bg-muted",
              )}
            >
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function Group({ label, marker, children }: { label: string; marker: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="eyebrow mb-3 flex items-center gap-2 px-4 text-muted-foreground">
        <span className={cn("size-2.5 rounded-[3px]", marker)} aria-hidden />
        {label}
      </p>
      {children}
    </div>
  );
}

function RoleBadge({ superAdmin }: { superAdmin: boolean }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-6 border-transparent px-2.5 text-sm",
        superAdmin ? "bg-stamp-violet text-white" : "bg-navy-soft text-stamp-navy",
      )}
    >
      {superAdmin ? "Super admin" : "Admin"}
    </Badge>
  );
}

function Sidebar() {
  const { data } = useSession();
  const superAdmin = data ? hasRole(data, "super_admin") : false;
  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="Admin" className="space-y-6">
        <Group label="Operations" marker="bg-stamp-orange">
          <NavLinks items={OPERATIONS} />
        </Group>
        {superAdmin && (
          <Group label="Super admin" marker="bg-stamp-violet">
            <NavLinks items={SUPER_ADMIN} />
          </Group>
        )}
      </nav>
      <Separator />
      <div className="space-y-3 px-4">
        <div className="space-y-1.5">
          <p className="truncate font-medium">{data?.user?.email}</p>
          <RoleBadge superAdmin={data?.role === "SUPER_ADMIN"} />
        </div>
        <Button variant="outline" className="w-full" onClick={() => void signOut()}>
          Sign out
        </Button>
      </div>
    </div>
  );
}

/** Phones: every admin page as a pill in one row that scrolls sideways on its own. */
function MobileNav() {
  const { data } = useSession();
  const superAdmin = data ? hasRole(data, "super_admin") : false;
  const isActive = useActive();
  const items = superAdmin ? [...OPERATIONS, ...SUPER_ADMIN] : OPERATIONS;
  return (
    <nav aria-label="Admin" className="-mx-4 overflow-x-auto px-4 pb-2 md:hidden">
      <ul className="flex w-max gap-2">
        {items.map((item) => {
          const active = isActive(item);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-10 items-center rounded-full border-[1.5px] px-4 text-base font-medium whitespace-nowrap",
                  active ? "border-stamp-navy bg-stamp-navy text-white" : "border-foreground",
                )}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function AdminShell({ children }: { children: React.ReactNode }) {
  return (
    <div data-admin-shell className="flex flex-col gap-6 md:flex-row md:gap-10">
      <aside className="hidden w-60 shrink-0 md:block">
        <Sidebar />
      </aside>
      <MobileNav />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
