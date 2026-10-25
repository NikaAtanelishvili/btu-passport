"use client";

// FE-20: admin sidebar (Operations, and Super admin for SUPER_ADMIN only), with the user's
// email, role and Sign out in its footer. On small screens the sidebar opens in a Sheet.
import { MenuIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { hasRole, signOut, useSession } from "@/lib/session";

type NavItem = { href: string; label: string; exact?: boolean };

const OPERATIONS: NavItem[] = [
  { href: "/admin", label: "Dashboard", exact: true },
  { href: "/admin/students", label: "Students" },
  { href: "/admin/awards/new", label: "Direct award" },
  { href: "/admin/issuance", label: "Issuance" },
];

// Catalog, roles and audit (M9) are listed without links until they exist.
const SUPER_ADMIN: (NavItem & { later?: boolean })[] = [
  { href: "/admin/events", label: "Events" },
  { href: "/admin/skills", label: "Skills" },
  { href: "/admin/categories", label: "Categories & stamps" },
  { href: "/admin/roles", label: "Admins & roles" },
  { href: "/admin/audit", label: "Audit log", later: true },
];

function NavLinks({ items, onNavigate }: { items: (NavItem & { later?: boolean })[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <ul className="space-y-1">
      {items.map((item) => {
        const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
        return (
          <li key={item.href}>
            {item.later ? (
              <span className={cn(buttonVariants({ variant: "ghost" }), "w-full justify-start text-muted-foreground")}>
                {item.label} <span className="ml-auto text-xs">later</span>
              </span>
            ) : (
              <Link
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(buttonVariants({ variant: active ? "secondary" : "ghost" }), "w-full justify-start")}
              >
                {item.label}
              </Link>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { data } = useSession();
  const superAdmin = data ? hasRole(data, "super_admin") : false;
  return (
    <div className="flex h-full flex-col gap-4">
      <nav className="space-y-4">
        <div>
          <p className="mb-2 px-2 text-xs font-medium text-muted-foreground">Operations</p>
          <NavLinks items={OPERATIONS} onNavigate={onNavigate} />
        </div>
        {superAdmin && (
          <div>
            <p className="mb-2 px-2 text-xs font-medium text-muted-foreground">Super admin</p>
            <NavLinks items={SUPER_ADMIN} onNavigate={onNavigate} />
          </div>
        )}
      </nav>
      <div className="mt-auto space-y-2">
        <Separator />
        <div className="px-2 text-sm">
          <p className="truncate">{data?.user?.email}</p>
          <p className="text-muted-foreground">{data?.role === "SUPER_ADMIN" ? "Super admin" : "Admin"}</p>
        </div>
        <Button variant="outline" className="w-full" onClick={() => void signOut()}>
          Sign out
        </Button>
      </div>
    </div>
  );
}

export function AdminShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-6 md:flex-row">
      <aside className="hidden w-56 shrink-0 md:block">
        <Sidebar />
      </aside>
      <div className="md:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger render={<Button variant="outline" size="sm" />}>
            <MenuIcon /> Menu
          </SheetTrigger>
          <SheetContent side="left" className="p-4">
            <SheetHeader className="p-0">
              <SheetTitle>Admin</SheetTitle>
            </SheetHeader>
            <Sidebar onNavigate={() => setOpen(false)} />
          </SheetContent>
        </Sheet>
      </div>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
