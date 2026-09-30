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
              <SectionHeading
                title="Profile"
                subtitle="No user-profile endpoint exists yet — these fields are not saved anywhere."
              />
              <Field label="Full name">
                <TextInput placeholder="Your full name" />
              </Field>
              <Field label="Email">
                <TextInput placeholder="you@example.com" inputMode="email" />
              </Field>
              <div><Button>Save changes</Button></div>
            </Card>
          )}

          {tab === "Team" && (
            <Card className="p-6">
              <SectionHeading title="Team" />
              <p className="rounded-xl border border-dashed border-line-300 px-5 py-8 text-center text-sm text-ink-500">
                Team membership is not connected to any backend yet — no members
                to show.
              </p>
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
