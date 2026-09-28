import { AppShell } from "@/components/shell";
import { Card, DemoBadge, PageHeader, SectionHeading } from "@/components/ui";
import { demoActivity, getDemoEmployees } from "@/lib/mock/data";

/* DEMO DATA — replace with lib/api/resources.ts calls when backend is wired. */

export default function AnalyticsPage() {
  const maxActivity = Math.max(...demoActivity.map((day) => day.calls));

  return (
    <AppShell>
      <PageHeader
        title="Analytics"
        subtitle="How your AI workforce is performing."
        actions={<DemoBadge />}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        {(
          [
            ["Total calls (7d)", "214", "+12% week over week"],
            ["Avg. success rate", "86%", "+3 pts"],
            ["Avg. call duration", "3m 08s", "−14s faster"],
          ] as const
        ).map(([label, value, delta]) => (
          <Card key={label} className="p-5">
            <p className="text-sm font-medium text-ink-500">{label}</p>
            <p className="mt-1 font-display text-3xl text-ink-900">{value}</p>
            <p className="mt-1 text-xs text-emerald-700">{delta}</p>
          </Card>
        ))}
      </div>

      <div className="mt-10">
        <SectionHeading title="Calls per day" subtitle="Last 7 days" />
        <Card className="p-6">
          <div className="flex h-44 items-end gap-3" role="img" aria-label="Calls per day bar chart">
            {demoActivity.map((day) => (
              <div key={day.label} className="flex flex-1 flex-col items-center gap-2">
                <span className="text-xs font-medium text-ink-700">{day.calls}</span>
                <div
                  className="w-full rounded-t-lg bg-brand-700/85"
                  style={{ height: `${(day.calls / maxActivity) * 100}%`, minHeight: 8 }}
                />
                <span className="text-xs text-ink-500">{day.label}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-10">
        <SectionHeading title="Outcome mix" />
        <div className="grid gap-4 sm:grid-cols-3">
          {(
            [
              ["Lead captured", "34%", "73 calls"],
              ["Resolved", "41%", "88 calls"],
              ["Follow-up needed", "11%", "24 calls"],
            ] as const
          ).map(([label, share, count]) => (
            <Card key={label} className="p-5">
              <p className="text-sm font-medium text-ink-500">{label}</p>
              <p className="mt-1 font-display text-2xl text-ink-900">{share}</p>
              <p className="mt-0.5 text-xs text-ink-500">{count}</p>
            </Card>
          ))}
        </div>
      </div>

      <div className="mt-10">
        <SectionHeading title="Per employee" />
        <Card>
          <ul className="divide-y divide-line-200">
            {getDemoEmployees().map((employee) => (
              <li key={employee.id} className="flex items-center gap-4 px-5 py-4">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-700 text-xs font-semibold text-white">
                  {employee.initials}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-ink-900">
                    {employee.name}
                  </span>
                  <span className="block text-xs text-ink-500">
                    {employee.calls} calls · {employee.leads} leads
                  </span>
                </span>
                <span className="text-sm font-semibold text-ink-900">
                  {employee.successRate}%
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </AppShell>
  );
}
