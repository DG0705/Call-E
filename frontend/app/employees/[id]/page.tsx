import Link from "next/link";
import { notFound } from "next/navigation";
import { Pause, Pencil, PhoneCall } from "lucide-react";
import { AppShell } from "@/components/shell";
import { Badge, Button, Card, DemoBadge, SectionHeading } from "@/components/ui";
import { getDemoCalls, getDemoEmployee } from "@/lib/mock/data";

/* DEMO DATA — replace with lib/api/resources.ts calls when backend is wired. */

const TABS = ["Overview", "Calls", "Knowledge", "Conversation", "Settings"];

export default async function EmployeeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const employee = getDemoEmployee(id);
  if (!employee) notFound();

  const calls = getDemoCalls().filter((call) => call.employeeId === id);

  return (
    <AppShell>
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <span className="flex size-14 items-center justify-center rounded-2xl bg-brand-700 font-display text-lg font-semibold text-white">
            {employee.initials}
          </span>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="font-display text-3xl tracking-tight text-ink-900">
                {employee.name}
              </h1>
              <Badge status={employee.status} />
            </div>
            <p className="mt-1 text-[15px] text-ink-500">{employee.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <DemoBadge />
          <Button variant="secondary">
            <PhoneCall size={16} /> Test Call
          </Button>
          <Button variant="secondary" aria-label={`Edit ${employee.name}`}>
            <Pencil size={16} />
          </Button>
          <Button variant="secondary">
            <Pause size={16} /> Pause
          </Button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {(
          [
            ["Calls", String(employee.calls)],
            ["Success rate", `${employee.successRate}%`],
            ["Average duration", employee.avgDuration],
            ["Leads", String(employee.leads)],
          ] as const
        ).map(([label, value]) => (
          <Card key={label} className="p-5">
            <p className="text-sm font-medium text-ink-500">{label}</p>
            <p className="mt-1 font-display text-2xl text-ink-900">{value}</p>
          </Card>
        ))}
      </div>

      <nav className="mt-8 flex gap-1 overflow-x-auto border-b border-line-200" aria-label="Employee sections">
        {TABS.map((tab, index) => (
          <span
            key={tab}
            aria-current={index === 0 ? "page" : undefined}
            className={
              index === 0
                ? "whitespace-nowrap border-b-2 border-brand-700 px-3 py-2 text-sm font-medium text-brand-800"
                : "whitespace-nowrap px-3 py-2 text-sm text-ink-500"
            }
          >
            {tab}
          </span>
        ))}
      </nav>

      <div className="mt-8">
        <SectionHeading
          title="Recent calls"
          action={
            <Link
              href="/calls/history"
              className="text-sm font-medium text-brand-700 hover:text-brand-800"
            >
              View all
            </Link>
          }
        />
        <Card>
          {calls.length === 0 ? (
            <p className="px-5 py-8 text-center text-sm text-ink-500">
              No calls yet for this employee.
            </p>
          ) : (
            <ul className="divide-y divide-line-200">
              {calls.map((call) => (
                <li key={call.id}>
                  <Link
                    href={`/calls/history/${call.id}`}
                    className="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-cream-50"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-ink-900">
                        {call.customer}
                      </span>
                      <span className="block text-xs text-ink-500">
                        {call.date} · {call.time} · {call.duration}
                      </span>
                    </span>
                    <Badge status={call.status} label={call.outcome} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="mt-8">
        <SectionHeading title="Performance" subtitle="Last 7 days" />
        <Card className="p-5">
          <dl className="grid gap-4 sm:grid-cols-3">
            <div>
              <dt className="text-sm text-ink-500">Conversations handled</dt>
              <dd className="mt-1 text-lg font-semibold text-ink-900">{employee.calls}</dd>
            </div>
            <div>
              <dt className="text-sm text-ink-500">Leads captured</dt>
              <dd className="mt-1 text-lg font-semibold text-ink-900">{employee.leads}</dd>
            </div>
            <div>
              <dt className="text-sm text-ink-500">Avg. response latency</dt>
              <dd className="mt-1 text-lg font-semibold text-ink-900">6.4s</dd>
            </div>
          </dl>
        </Card>
      </div>
    </AppShell>
  );
}
