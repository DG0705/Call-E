"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";

const SECTIONS = [
  { label: "Overview", href: "" },
  { label: "Calls", href: "/calls" },
  { label: "Knowledge", href: "/knowledge" },
  { label: "Conversation", href: "/conversation" },
  { label: "Settings", href: "/settings" },
] as const;

export function EmployeeTabs({ employeeId }: { employeeId: string }) {
  const pathname = usePathname();
  const base = `/employees/${encodeURIComponent(employeeId)}`;

  return (
    <nav
      className="flex gap-1 overflow-x-auto border-b border-line-200"
      aria-label="Employee sections"
    >
      {SECTIONS.map((section) => {
        const href = `${base}${section.href}`;
        const active =
          section.href === "" ? pathname === base : pathname === href;
        return (
          <Link
            key={section.label}
            href={href}
            aria-current={active ? "page" : undefined}
            className={clsx(
              "whitespace-nowrap px-3 py-2 text-sm transition-colors",
              active
                ? "border-b-2 border-brand-700 font-medium text-brand-800"
                : "text-ink-500 hover:text-ink-900",
            )}
          >
            {section.label}
          </Link>
        );
      })}
    </nav>
  );
}
