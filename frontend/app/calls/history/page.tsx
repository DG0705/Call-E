import Link from "next/link";
import { AppShell } from "@/components/shell";
import { Badge, Card, DemoBadge, PageHeader } from "@/components/ui";
import { getDemoCalls } from "@/lib/mock/data";

/* DEMO DATA — replace with lib/api/resources.ts calls when backend is wired. */

export default function CallHistoryPage() {
  const calls = getDemoCalls();

  return (
    <AppShell>
      <PageHeader
        title="Call History"
        subtitle="Every conversation your AI employees have handled."
        actions={<DemoBadge />}
      />
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-line-200 text-xs uppercase tracking-wider text-ink-500">
                <th scope="col" className="px-5 py-3 font-medium">Date</th>
                <th scope="col" className="px-5 py-3 font-medium">AI Employee</th>
                <th scope="col" className="px-5 py-3 font-medium">Customer</th>
                <th scope="col" className="px-5 py-3 font-medium">Duration</th>
                <th scope="col" className="px-5 py-3 font-medium">Outcome</th>
                <th scope="col" className="px-5 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-200">
              {calls.map((call) => (
                <tr key={call.id} className="transition-colors hover:bg-cream-50">
                  <td className="whitespace-nowrap px-5 py-3.5 text-ink-700">
                    {call.date} · {call.time}
                  </td>
                  <td className="px-5 py-3.5">
                    <Link
                      href={`/calls/history/${call.id}`}
                      className="font-medium text-brand-700 hover:text-brand-800"
                    >
                      {call.employee}
                    </Link>
                  </td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-ink-700">
                    {call.customer}
                  </td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-ink-700">
                    {call.duration}
                  </td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-ink-700">
                    {call.outcome}
                  </td>
                  <td className="whitespace-nowrap px-5 py-3.5">
                    <Badge status={call.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </AppShell>
  );
}
