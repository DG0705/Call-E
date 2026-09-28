"use client";

import { useState } from "react";
import { Plus, Webhook } from "lucide-react";
import { AppShell } from "@/components/shell";
import {
  Button,
  Card,
  DemoBadge,
  Field,
  PageHeader,
  SectionHeading,
  TextInput,
  Toggle,
} from "@/components/ui";

/* DEMO DATA — webhook configuration is a visual shell in this demo. */

const EVENTS = [
  { name: "call.started", description: "A call connects.", on: true },
  { name: "call.ended", description: "A call finishes.", on: true },
  { name: "call.failed", description: "A call fails to complete.", on: false },
  { name: "transcript.produced", description: "A turn is transcribed.", on: false },
  { name: "lead.captured", description: "An employee captures a lead.", on: true },
];

export default function WebhooksPage() {
  const [subscribed, setSubscribed] = useState<Record<string, boolean>>(
    Object.fromEntries(EVENTS.map((event) => [event.name, event.on])),
  );

  return (
    <AppShell>
      <PageHeader
        title="Webhooks"
        subtitle="Get notified when things happen in your workspace."
        actions={
          <>
            <DemoBadge />
            <Button>
              <Plus size={16} /> Add endpoint
            </Button>
          </>
        }
      />
      <SectionHeading title="Endpoint" />
      <Card className="space-y-4 p-5">
        <Field label="Destination URL" hint="HTTPS only. We retry failed deliveries for 24 hours.">
          <TextInput defaultValue="https://example.com/hooks/call-e" inputMode="url" />
        </Field>
        <Field label="Signing secret" hint="Shown once when you save. Never hardcode it.">
          <TextInput defaultValue="whsec_demo_••••••••" readOnly />
        </Field>
      </Card>

      <div className="mt-10">
        <SectionHeading title="Events" subtitle="Choose what posts to your endpoint." />
        <Card>
          <ul className="divide-y divide-line-200">
            {EVENTS.map((event) => (
              <li key={event.name} className="flex items-center justify-between gap-4 px-5 py-3.5">
                <span className="flex items-center gap-3">
                  <Webhook size={16} className="shrink-0 text-ink-500" />
                  <span>
                    <span className="block font-mono text-sm text-ink-900">{event.name}</span>
                    <span className="block text-xs text-ink-500">{event.description}</span>
                  </span>
                </span>
                <Toggle
                  checked={subscribed[event.name] ?? false}
                  onChange={(value) =>
                    setSubscribed((prev) => ({ ...prev, [event.name]: value }))
                  }
                  label={`Subscribe to ${event.name}`}
                />
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </AppShell>
  );
}
