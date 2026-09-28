import Link from "next/link";
import { ArrowRight, ArrowUpRight, PhoneCall, Sparkles, UserPlus, Users } from "lucide-react";
import { AppShell } from "@/components/shell";
import { Badge, Card, DemoBadge, PageHeader, SectionHeading } from "@/components/ui";
import {
  DEMO_DATA_BADGE,
  demoActivity,
  demoMetrics,
  getDemoCalls,
  getDemoEmployees,
} from "@/lib/mock/data";

/* DEMO DATA — replace with lib/api/resources.ts calls when backend is wired. */

function StatCard({
  label,
  value,
  delta,
  icon,
}: {
  label: string;
  value: string;
  delta: string;
  icon: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-ink-500">{label}</p>
        <span className="text-ink-500">{icon}</span>
      </div>
      <p className="mt-2 font-display text-3xl tracking-tight text-ink-900">
        {value}
      </p>
      <p className="mt-1 flex items-center gap-1 text-xs text-emerald-700">
        <ArrowUpRight size={13} />
        {delta}
      </p>
    </Card>
  );
}

export default function OverviewPage() {
  const employees = getDemoEmployees();
  const calls = getDemoCalls().slice(0, 4);
  const maxActivity = Math.max(...demoActivity.map((day) => day.calls));

  return (
    <AppShell>
      <PageHeader
        title="Welcome back"
        subtitle="Your AI workforce at a glance."
        actions={<DemoBadge />}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Active AI Employees"
          value={String(demoMetrics.activeEmployees)}
          delta="2 live now"
          icon={<Users size={17} />}
        />
        <StatCard
          label="Calls Today"
          value={String(demoMetrics.callsToday)}
          delta="+18% vs yesterday"
          icon={<PhoneCall size={17} />}
        />
        <StatCard
          label="Successful Conversations"
          value={String(demoMetrics.successfulConversations)}
          delta="87% success rate"
          icon={<Sparkles size={17} />}
        />
        <StatCard
          label="Leads Captured"
          value={String(demoMetrics.leadsCaptured)}
          delta="+4 this week"
          icon={<UserPlus size={17} />}
        />
      </div>

      <div className="mt-10 grid gap-8 lg:grid-cols-5">
        <section className="lg:col-span-3">
          <SectionHeading
            title="Recent Calls"
            subtitle={DEMO_DATA_BADGE}
            action={
              <Link
                href="/calls/history"
                className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:text-brand-800"
              >
                View all <ArrowRight size={15} />
              </Link>
            }
          />
          <Card>
            <ul className="divide-y divide-line-200">
              {calls.map((call) => (
                <li key={call.id}>
                  <Link
                    href={`/calls/history/${call.id}`}
                    className="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-cream-50"
                  >
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-cream-100 text-xs font-semibold text-ink-700">
                      {call.customer.slice(-2)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-ink-900">
                        {call.employee} · {call.customer}
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
          </Card>
        </section>

        <div className="space-y-8 lg:col-span-2">
          <section>
            <SectionHeading title="AI Employee Performance" />
            <Card className="space-y-1 p-2">
              {employees.map((employee) => (
                <Link
                  key={employee.id}
                  href={`/employees/${employee.id}`}
                  className="flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-cream-50"
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-700 text-xs font-semibold text-white">
                    {employee.initials}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink-900">
                      {employee.name}
                    </span>
                    <span className="block text-xs text-ink-500">
                      {employee.successRate}% success · {employee.avgDuration} avg
                    </span>
                  </span>
                  <Badge status={employee.status} />
                </Link>
              ))}
            </Card>
          </section>

          <section>
            <SectionHeading title="Call Activity" subtitle="Calls per day" />
            <Card className="p-5">
              <div className="flex h-28 items-end gap-2" role="img" aria-label="Calls per day bar chart">
                {demoActivity.map((day) => (
                  <div key={day.label} className="flex flex-1 flex-col items-center gap-1.5">
                    <div
                      className="w-full rounded-t-md bg-brand-700/85"
                      style={{ height: `${(day.calls / maxActivity) * 100}%`, minHeight: 6 }}
                    />
                    <span className="text-[11px] text-ink-500">{day.label}</span>
                  </div>
                ))}
              </div>
            </Card>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
