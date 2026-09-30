"use client";

import Link from "next/link";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState } from "@/components/data-states";
import { Badge, Card, EmptyState, PageHeader } from "@/components/ui";
import { callsApi } from "@/lib/api/resources";
import {
  callDurationSeconds,
  formatDateTime,
  formatDuration,
} from "@/lib/format";
import { getTenantId } from "@/lib/tenant";
import { useResource } from "@/lib/use-resource";
import { PhoneCall } from "lucide-react";

export default function CallHistoryPage() {
  const tenantId = getTenantId();
  const { data, error, loading, reload } = useResource(() =>
    callsApi.list(tenantId, 50),
  );

  return (
    <AppShell>
      <PageHeader
        title="Call History"
        subtitle={`Every recorded conversation in tenant ${tenantId}. Audio recordings are not stored by the backend.`}
      />
      {loading ? (
        <LoadingState label="calls" />
      ) : error || !data ? (
        <ErrorState message={error ?? "Could not load calls."} onRetry={reload} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<PhoneCall size={22} />}
          title="No calls yet"
          description="Place a real call to your inbound number and it will appear here."
        />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-line-200 text-xs uppercase tracking-wider text-ink-500">
                  <th scope="col" className="px-5 py-3 font-medium">Date</th>
                  <th scope="col" className="px-5 py-3 font-medium">Customer</th>
                  <th scope="col" className="px-5 py-3 font-medium">Direction</th>
                  <th scope="col" className="px-5 py-3 font-medium">Duration</th>
                  <th scope="col" className="px-5 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-200">
                {data.map((call) => {
                  const seconds = callDurationSeconds(call.created_at, call.ended_at);
                  return (
                    <tr key={call.call_id} className="transition-colors hover:bg-cream-50">
                      <td className="whitespace-nowrap px-5 py-3.5 text-ink-700">
                        {formatDateTime(call.created_at)}
                      </td>
                      <td className="px-5 py-3.5">
                        <Link
                          href={`/calls/history/${encodeURIComponent(call.call_id)}`}
                          className="font-medium text-brand-700 hover:text-brand-800"
                        >
                          {call.caller_number ?? call.destination_number}
                        </Link>
                      </td>
                      <td className="whitespace-nowrap px-5 py-3.5 text-ink-700">
                        {call.direction}
                      </td>
                      <td className="whitespace-nowrap px-5 py-3.5 text-ink-700">
                        {formatDuration(seconds)}
                      </td>
                      <td className="whitespace-nowrap px-5 py-3.5">
                        <Badge status={call.status} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </AppShell>
  );
}
