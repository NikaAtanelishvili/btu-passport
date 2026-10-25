"use client";

// Student portal top nav (Frontend tab §4): a pill group, the current page in black.
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/me", label: "My passport" },
  { href: "/me/history", label: "History" },
  { href: "/me/events", label: "My events" },
];

export function StudentNav() {
  const pathname = usePathname();
  return (
    <nav className="mb-8 flex w-full gap-1 rounded-full border p-1 sm:w-fit">
      {ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex h-11 flex-1 items-center justify-center rounded-full px-4 text-base font-medium whitespace-nowrap sm:flex-none sm:px-5 sm:text-lg",
              active ? "bg-foreground text-background" : "hover:bg-muted",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
