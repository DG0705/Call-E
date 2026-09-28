"use client";

import { useState } from "react";
import { AppShell } from "@/components/shell";
import { Button, Card, DemoBadge, Field, PageHeader, SectionHeading, Select, TextInput, Toggle } from "@/components/ui";
import { clsx } from "clsx";

/* Settings shell — no backend settings integration in this demo. */

const TABS = ["Workspace", "Profile", "Team", "Billing", "Security", "Notifications"];

export default function SettingsPage() {
  const [tab, setTab] = useState("Workspace");
  const [emailNotifs, setEmailNotifs] = useState(true);
  const [smsNotifs, setSmsNotifs] = useState(false);

  return (
    <AppShell>
      <PageHeader
        title="Settings"
        subtitle="Workspace preferences and account controls."
        actions={<DemoBadge />}
      />
      <div className="flex flex-col gap-8 lg:flex-row">
        <nav className="flex shrink-0 gap-1 overflow-x-auto lg:w-52 lg:flex-col" aria-label="Settings sections">
          {TABS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setTab(option)}
              aria-current={tab === option ? "page" : undefined}
              className={clsx(
                "cursor-pointer whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                tab === option
                  ? "bg-brand-50 text-brand-800"
                  : "text-ink-600 hover:bg-cream-100",
              )}
            >
              {option}
            </button>
          ))}
        </nav>

        <div className="min-w-0 flex-1">
          {tab === "Workspace" && (
            <Card className="space-y-5 p-6">
              <SectionHeading title="Workspace" subtitle="Shown across the product." />
              <Field label="Workspace name">
                <TextInput defaultValue="Kaari Planters" />
              </Field>
              <Field label="Default timezone">
                <Select defaultValue="Asia/Kolkata">
                  <option>Asia/Kolkata</option>
                  <option>UTC</option>
                  <option>America/New_York</option>
                </Select>
              </Field>
              <div><Button>Save changes</Button></div>
            </Card>
          )}

          {tab === "Profile" && (
            <Card className="space-y-5 p-6">
              <SectionHeading title="Profile" />
              <Field label="Full name">
                <TextInput defaultValue="Aarav Rao" />
              </Field>
              <Field label="Email">
                <TextInput defaultValue="aarav@example.com" inputMode="email" />
              </Field>
              <div><Button>Save changes</Button></div>
            </Card>
          )}

          {tab === "Team" && (
            <Card className="p-6">
              <SectionHeading
                title="Team"
                subtitle="2 seats used"
                action={<Button variant="secondary" size="sm">Invite member</Button>}
              />
              <ul className="divide-y divide-line-200">
                {(
                  [
                    ["Aarav Rao", "Owner", "AR"],
                    ["Meera Iyer", "Admin", "MI"],
                  ] as const
                ).map(([name, role, initials]) => (
                  <li key={name} className="flex items-center gap-3 py-3">
                    <span className="flex size-9 items-center justify-center rounded-full bg-brand-700 text-xs font-semibold text-white">
                      {initials}
                    </span>
                    <span className="flex-1">
                      <span className="block text-sm font-medium text-ink-900">{name}</span>
                      <span className="block text-xs text-ink-500">{role}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {tab === "Billing" && (
            <Card className="p-6">
              <SectionHeading title="Billing" subtitle="Usage-based, cancel anytime." />
              <div className="rounded-xl bg-cream-100 p-4 text-sm text-ink-700">
                Current plan: <strong>Open-source self-hosted</strong> — no card
                required. Cloud billing is a placeholder in this demo.
              </div>
              <div className="mt-4"><Button variant="secondary">Compare plans</Button></div>
            </Card>
          )}

          {tab === "Security" && (
            <Card className="space-y-4 p-6">
              <SectionHeading title="Security" />
              <div className="flex items-center justify-between gap-4">
                <span className="text-sm text-ink-800">
                  Require two-factor authentication for all members
                </span>
                <Toggle checked={false} onChange={() => undefined} label="Require two-factor authentication" />
              </div>
              <Button variant="secondary">Rotate all API keys</Button>
            </Card>
          )}

          {tab === "Notifications" && (
            <Card className="space-y-4 p-6">
              <SectionHeading title="Notifications" />
              <div className="flex items-center justify-between gap-4">
                <span className="text-sm text-ink-800">Email me when a lead is captured</span>
                <Toggle checked={emailNotifs} onChange={setEmailNotifs} label="Email on lead captured" />
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-sm text-ink-800">SMS me on failed calls</span>
                <Toggle checked={smsNotifs} onChange={setSmsNotifs} label="SMS on failed calls" />
              </div>
            </Card>
          )}
        </div>
      </div>
    </AppShell>
  );
}
