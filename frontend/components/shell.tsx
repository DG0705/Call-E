"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import {
  BarChart3,
  Bell,
  BookOpen,
  Bot,
  ChevronDown,
  Code2,
  ContactRound,
  Home,
  Menu,
  PhoneCall,
  Plug,
  Search,
  Settings,
  Users,
  X,
} from "lucide-react";
import { clsx } from "clsx";
import { getWorkspaceProfile } from "@/lib/workspace";

interface NavItem {
  label: string;
  href?: string;
  icon: ReactNode;
  children?: { label: string; href: string }[];
}

const NAV: { section?: string; items: NavItem[] }[] = [
  {
    items: [{ label: "Overview", href: "/overview", icon: <Home size={18} /> }],
  },
  {
    section: "Workforce",
    items: [
      {
        label: "AI Employees",
        icon: <Bot size={18} />,
        children: [
          { label: "All Employees", href: "/employees" },
          { label: "Create Employee", href: "/employees/new" },
        ],
      },
      {
        label: "Calls",
        icon: <PhoneCall size={18} />,
        children: [
          { label: "Live Calls", href: "/calls/live" },
          { label: "Call History", href: "/calls/history" },
        ],
      },
      { label: "Knowledge", href: "/knowledge", icon: <BookOpen size={18} /> },
      { label: "Contacts", href: "/contacts", icon: <ContactRound size={18} /> },
      { label: "Analytics", href: "/analytics", icon: <BarChart3 size={18} /> },
    ],
  },
  {
    section: "Build",
    items: [
      { label: "Integrations", href: "/integrations", icon: <Plug size={18} /> },
      {
        label: "Developer",
        icon: <Code2 size={18} />,
        children: [
          { label: "API Keys", href: "/developer/api-keys" },
          { label: "Webhooks", href: "/developer/webhooks" },
          { label: "API Docs", href: "/developer/docs" },
        ],
      },
      { label: "Settings", href: "/settings", icon: <Settings size={18} /> },
    ],
  },
];

function Wordmark() {
  return (
    <Link href="/overview" className="flex items-center gap-2.5" aria-label="Call-E home">
      <span className="flex size-9 items-center justify-center rounded-lg bg-brand-700 font-display text-lg font-semibold text-white">
        E
      </span>
      <span className="font-display text-xl font-semibold tracking-tight text-ink-900">
        Call-E
      </span>
    </Link>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const [open, setOpen] = useState<string[]>(["AI Employees", "Calls", "Developer"]);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  const toggle = (label: string) =>
    setOpen((prev) =>
      prev.includes(label) ? prev.filter((item) => item !== label) : [...prev, label],
    );

  return (
    <div className="flex h-full flex-col">
      <div className="px-5 pb-5 pt-6">
        <Wordmark />
      </div>
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4" aria-label="Primary">
        {NAV.map((group, groupIndex) => (
          <div key={group.section ?? `group-${groupIndex}`}>
            {group.section ? (
              <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-500">
                {group.section}
              </p>
            ) : null}
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                if (!item.children) {
                  const active = item.href ? isActive(item.href) : false;
                  return (
                    <li key={item.label}>
                      <Link
                        href={item.href ?? "#"}
                        onClick={onNavigate}
                        aria-current={active ? "page" : undefined}
                        className={clsx(
                          "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                          active
                            ? "bg-brand-50 text-brand-800"
                            : "text-ink-600 hover:bg-cream-100 hover:text-ink-900",
                        )}
                      >
                        <span className={active ? "text-brand-700" : "text-ink-500"}>
                          {item.icon}
                        </span>
                        {item.label}
                      </Link>
                    </li>
                  );
                }
                const expanded = open.includes(item.label);
                const childActive = item.children.some((child) =>
                  isActive(child.href),
                );
                return (
                  <li key={item.label}>
                    <button
                      type="button"
                      onClick={() => toggle(item.label)}
                      aria-expanded={expanded}
                      className={clsx(
                        "flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                        childActive
                          ? "text-ink-900"
                          : "text-ink-600 hover:bg-cream-100 hover:text-ink-900",
                      )}
                    >
                      <span
                        className={childActive ? "text-brand-700" : "text-ink-500"}
                      >
                        {item.icon}
                      </span>
                      <span className="flex-1 text-left">{item.label}</span>
                      <ChevronDown
                        size={15}
                        className={clsx(
                          "text-ink-500 transition-transform",
                          expanded && "rotate-180",
                        )}
                      />
                    </button>
                    {expanded ? (
                      <ul className="ml-5 mt-0.5 space-y-0.5 border-l border-line-200 pl-3">
                        {item.children.map((child) => {
                          const active = isActive(child.href);
                          return (
                            <li key={child.href}>
                              <Link
                                href={child.href}
                                onClick={onNavigate}
                                aria-current={active ? "page" : undefined}
                                className={clsx(
                                  "block rounded-md px-2 py-1.5 text-sm transition-colors",
                                  active
                                    ? "font-medium text-brand-800"
                                    : "text-ink-600 hover:text-ink-900",
                                )}
                              >
                                {child.label}
                              </Link>
                            </li>
                          );
                        })}
                      </ul>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="border-t border-line-200 px-5 py-4">
        <div className="flex items-center gap-2 text-xs text-ink-500">
          <Users size={14} />
          <span>Open Source</span>
          <span aria-hidden>·</span>
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="font-medium text-ink-700 hover:text-brand-700"
          >
            GitHub
          </a>
        </div>
        <p className="mt-1 text-[11px] text-ink-500">v0.1.0 · self-hosted</p>
      </div>
    </div>
  );
}

function Topbar({ title, onMenu }: { title: string; onMenu: () => void }) {
  // Workspace-level identity: no authenticated-user endpoint exists yet, so
  // the header shows the real tenant workspace (see lib/workspace.ts) rather
  // than a fabricated person.
  const profile = getWorkspaceProfile();
  return (
    <header className="sticky top-0 z-20 border-b border-line-200 bg-cream-50/90 backdrop-blur">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-8">
        <button
          type="button"
          onClick={onMenu}
          aria-label="Open navigation"
          className="rounded-lg p-2 text-ink-700 hover:bg-cream-100 lg:hidden"
        >
          <Menu size={20} />
        </button>
        <h1 className="font-display text-lg text-ink-900 sm:hidden">{title}</h1>
        <div className="hidden max-w-md flex-1 sm:block">
          <label className="relative block">
            <Search
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-500"
            />
            <input
              type="search"
              placeholder="Search employees, calls, contacts…"
              aria-label="Search"
              className="w-full rounded-lg border border-line-200 bg-white py-2 pl-9 pr-3 text-sm text-ink-900 placeholder:text-ink-500/60 focus:border-brand-600 focus:outline-none"
            />
          </label>
        </div>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            aria-label="Notifications"
            className="relative rounded-lg p-2 text-ink-600 hover:bg-cream-100"
          >
            <Bell size={19} />
            <span className="absolute right-2 top-2 size-2 rounded-full bg-brand-600" />
          </button>
          <button
            type="button"
            aria-label={`Workspace menu for ${profile.label}`}
            title={profile.tenantId}
            className="ml-1 flex items-center gap-2 rounded-lg p-1.5 hover:bg-cream-100"
          >
            <span className="flex size-8 items-center justify-center rounded-full bg-brand-700 text-xs font-semibold text-white">
              {profile.initials}
            </span>
            <span className="hidden text-left text-xs leading-tight md:block">
              <span className="block font-medium text-ink-900">{profile.label}</span>
              <span className="block text-ink-500">{profile.sublabel}</span>
            </span>
          </button>
        </div>
      </div>
    </header>
  );
}

const TITLES: [RegExp, string][] = [
  [/^\/employees\/new$/, "Create AI Employee"],
  [/^\/employees\/.+$/, "Employee Detail"],
  [/^\/employees$/, "AI Employees"],
  [/^\/calls\/live$/, "Live Calls"],
  [/^\/calls\/history\/.+$/, "Call Detail"],
  [/^\/calls\/history$/, "Call History"],
  [/^\/knowledge$/, "Knowledge"],
  [/^\/contacts$/, "Contacts"],
  [/^\/analytics$/, "Analytics"],
  [/^\/integrations$/, "Integrations"],
  [/^\/developer/, "Developer"],
  [/^\/settings/, "Settings"],
  [/^\/overview$/, "Overview"],
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const title =
    TITLES.find(([pattern]) => pattern.test(pathname))?.[1] ?? "Call-E";

  return (
    <div className="min-h-screen lg:flex">
      <aside className="sticky top-0 hidden h-screen w-72 shrink-0 border-r border-line-200 bg-white lg:block">
        <SidebarContent />
      </aside>
      {mobileOpen ? (
        <div className="fixed inset-0 z-30 lg:hidden" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 bg-ink-900/30"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <div className="absolute inset-y-0 left-0 w-72 bg-white shadow-xl">
            <div className="flex justify-end p-3">
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
                className="rounded-lg p-2 text-ink-700 hover:bg-cream-100"
              >
                <X size={20} />
              </button>
            </div>
            <div className="h-[calc(100%-60px)]">
              <SidebarContent onNavigate={() => setMobileOpen(false)} />
            </div>
          </div>
        </div>
      ) : null}
      <div className="min-w-0 flex-1">
        <Topbar title={title} onMenu={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
