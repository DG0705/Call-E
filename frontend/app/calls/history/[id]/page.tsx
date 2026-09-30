"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, Disc3 } from "lucide-react";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState, Unavailable } from "@/components/data-states";
import { Badge, Card, SectionHeading } from "@/components/ui";
import { agentsApi, callsApi } from "@/lib/api/resources";
import {
  callDurationSeconds,
  formatDateTime,
  formatDuration,
} from "@/lib/format";
import { getTenantId } from "@/lib/tenant";
import { useResource } from "@/lib/use-resource";

export default function CallDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const tenantId = getTenantId();
  const callId = decodeURIComponent(id);
  const { data: call, error, loading, reload } = useResource(() =>
    callsApi.get(callId, tenantId),
  );
  const { data: agents } = useResource(() => agentsApi.list(tenantId));

  if (loading) {
    return (
      <AppShell>
        <LoadingState label="call" />
      </AppShell>
    );
  }
  if (!call) {
    if (error?.includes("404") || error?.includes("not found")) notFound();
    return (
      <AppShell>
        <ErrorState message={error ?? "Call not found."} onRetry={reload} />
      </AppShell>
    );
  }

  const agentName =
    agents?.find((agent) => agent.id === call.agent_id)?.name ?? call.agent_id;
  const seconds = callDurationSeconds(call.created_at, call.ended_at);

  return (
    <AppShell>
      <Link
        href="/calls/history"
        className="inline-flex items-center gap-1 text-sm font-medium text-ink-500 hover:text-ink-900"
      >
        <ArrowLeft size={15} /> Call history
      </Link>

      <div className="mb-8 mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl tracking-tight text-ink-900">
            {agentName} · {call.caller_number ?? call.destination_number}
          </h1>
          <p className="mt-2 text-[15px] text-ink-500">
            {formatDateTime(call.created_at)} · {formatDuration(seconds)} · {call.direction}
          </p>
        </div>
        <Badge status={call.status} />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <section>
            <SectionHeading title="Call record" />
            <Card className="p-5">
              <dl className="space-y-3 text-sm">
                {(
                  [
                    ["Call ID", call.call_id],
                    ["Conversation", call.conversation_id],
                    ["Agent", agentName],
                    ["Customer", call.caller_number ?? "—"],
                    ["Destination", call.destination_number],
                    ["Provider", call.provider],
                    ["Started", formatDateTime(call.created_at)],
                    ["Ended", call.ended_at ? formatDateTime(call.ended_at) : "—"],
                    ["Error", call.error_code ?? "—"],
                  ] as const
                ).map(([term, value]) => (
                  <div key={term} className="flex gap-4">
                    <dt className="w-28 shrink-0 text-ink-500">{term}</dt>
                    <dd className="break-all text-ink-800">{value}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </section>

          <section>
            <SectionHeading title="Transcript" />
            <Card className="p-5">
              <Unavailable label="Turn-by-turn transcript" />
              <p className="mt-1 text-xs text-ink-500">
                Transcripts are emitted to service logs today, not stored per call.
              </p>
            </Card>
          </section>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <section>
            <SectionHeading title="Timeline" />
            <Card className="p-5">
              <ol className="relative space-y-3 border-l border-line-200 pl-5 text-sm">
                <li className="relative">
                  <span className="absolute -left-[26px] top-1 size-2 rounded-full bg-brand-600" aria-hidden />
                  <span className="font-medium text-ink-900">Created</span>
                  <span className="text-ink-500"> · {formatDateTime(call.created_at)}</span>
                </li>
                <li className="relative">
                  <span className="absolute -left-[26px] top-1 size-2 rounded-full bg-brand-600" aria-hidden />
                  <span className="font-medium text-ink-900">Last update</span>
                  <span className="text-ink-500"> · {formatDateTime(call.updated_at)}</span>
                </li>
                {call.ended_at ? (
                  <li className="relative">
                    <span className="absolute -left-[26px] top-1 size-2 rounded-full bg-brand-600" aria-hidden />
                    <span className="font-medium text-ink-900">Ended</span>
                    <span className="text-ink-500"> · {formatDateTime(call.ended_at)}</span>
                  </li>
                ) : null}
              </ol>
            </Card>
          </section>

          <section>
            <SectionHeading title="Recording" />
            <Card className="p-5">
              <p className="flex items-center gap-2 text-sm text-ink-700">
                <Disc3 size={15} className="text-ink-500" />
                Not available
              </p>
              <p className="mt-1 text-xs text-ink-500">
                Call recording storage does not exist in the backend yet — audio
                is intentionally not kept.
              </p>
            </Card>
          </section>

          <section>
            <SectionHeading title="Analysis" />
            <Card className="p-5 space-y-2">
              <Unavailable label="Outcome, tools used and latency" />
            </Card>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
