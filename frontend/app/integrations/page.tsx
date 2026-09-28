import { CalendarCheck, CreditCard, MessageSquare, Plug, Truck } from "lucide-react";
import { AppShell } from "@/components/shell";
import { Badge, Button, Card, DemoBadge, PageHeader, SectionHeading } from "@/components/ui";

/* DEMO DATA — integration connections are visual only in this demo. */

const INTEGRATIONS = [
  {
    icon: <CalendarCheck size={19} />,
    name: "Google Calendar",
    description: "Let employees book and confirm appointments.",
    connected: true,
  },
  {
    icon: <MessageSquare size={19} />,
    name: "WhatsApp",
    description: "Follow up on calls with messages.",
    connected: true,
  },
  {
    icon: <CreditCard size={19} />,
    name: "Razorpay",
    description: "Collect payments during a call.",
    connected: false,
  },
  {
    icon: <Truck size={19} />,
    name: "Shiprocket",
    description: "Quote delivery dates from live data.",
    connected: false,
  },
];

export default function IntegrationsPage() {
  return (
    <AppShell>
      <PageHeader
        title="Integrations"
        subtitle="Connect the tools your AI employees should act through."
        actions={<DemoBadge />}
      />
      <SectionHeading title="Available" subtitle="4 integrations" />
      <div className="grid gap-4 sm:grid-cols-2">
        {INTEGRATIONS.map((integration) => (
          <Card key={integration.name} className="flex items-center gap-4 p-5">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-cream-100 text-ink-700">
              {integration.icon}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2 text-sm font-semibold text-ink-900">
                {integration.name}
                {integration.connected ? (
                  <Badge status="completed" label="CONNECTED" />
                ) : null}
              </span>
              <span className="mt-0.5 block text-sm text-ink-500">
                {integration.description}
              </span>
            </span>
            <Button variant="secondary" size="sm">
              <Plug size={14} />
              {integration.connected ? "Manage" : "Connect"}
            </Button>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
