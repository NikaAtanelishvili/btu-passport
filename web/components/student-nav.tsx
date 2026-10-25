"use client";

// Student portal top nav (Frontend tab §4).
import Link from "next/link";
import { usePathname } from "next/navigation";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/me", label: "My passport" },
  { href: "/me/history", label: "History" },
  { href: "/me/events", label: "My events" },
];

export function StudentNav() {
  const pathname = usePathname();
  return (
    <nav className="mb-6 flex flex-wrap gap-2">
      {ITEMS.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={pathname === item.href ? "page" : undefined}
          className={cn(buttonVariants({ variant: pathname === item.href ? "secondary" : "ghost" }))}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
