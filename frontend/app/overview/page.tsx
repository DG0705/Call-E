"use client";

import Link from "next/link";
import { ArrowRight, PhoneCall } from "lucide-react";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState, Unavailable } from "@/components/data-states";
import { Badge, Button, Card, EmptyState, PageHeader, SectionHeading } from "@/components/ui";
import { agentsApi, callsApi } from "@/lib/api/resources";
import {
  callDurationSeconds,
  formatDateTime,
  formatDuration,
  isToday,
} from "@/lib/format";
import { getTenantId } from "@/lib/tenant";
import { useResource } from "@/lib/use-resource";

export default function OverviewPage() {
  const tenantId = getTenantId();
  const employees = useResource(() => agentsApi.list(tenantId));
  const calls = useResource(() => callsApi.list(tenantId, 50));

  const liveEmployees = (employees.data ?? []).filter(
    (employee) => employee.status === "active",
  );
  const todaysCalls = (calls.data ?? []).filter((call) => isToday(call.created_at));
  const recentCalls = (calls.data ?? []).slice(0, 4);

  return (
    <AppShell>
      <PageHeader
        title="Welcome back"
        subtitle={`Your AI workforce at a glance · tenant ${tenantId}.`}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-500">Active AI Employees</p>
          <p className="mt-2 font-display text-3xl tracking-tight text-ink-900">
            {employees.data ? liveEmployees.length : "—"}
          </p>
          <p className="mt-1 text-xs text-ink-500">
            {employees.data
              ? `${employees.data.length} total`
              : "Loading…"}
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-500">Calls Today</p>
          <p className="mt-2 font-display text-3xl tracking-tight text-ink-900">
            {calls.data ? todaysCalls.length : "—"}
          </p>
          <p className="mt-1 text-xs text-ink-500">From call records</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-500">Successful Conversations</p>
          <p className="mt-2 font-display text-3xl tracking-tight text-ink-900">—</p>
          <p className="mt-1 text-xs text-ink-500">Not available yet</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-500">Leads Captured</p>
          <p className="mt-2 font-display text-3xl tracking-tight text-ink-900">—</p>
          <p className="mt-1 text-xs text-ink-500">Not available yet</p>
        </Card>
      </div>

      {(employees.error || calls.error) && (
        <div className="mt-6">
          <ErrorState
            message={employees.error ?? calls.error ?? "Could not load overview."}
            onRetry={() => {
              employees.reload();
              calls.reload();
            }}
          />
        </div>
      )}

      <div className="mt-10 grid gap-8 lg:grid-cols-5">
        <section className="lg:col-span-3">
          <SectionHeading
            title="Recent Calls"
            action={
              <Link
                href="/calls/history"
                className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:text-brand-800"
              >
                View all <ArrowRight size={15} />
              </Link>
            }
          />
          {calls.loading ? (
            <LoadingState label="recent calls" />
          ) : recentCalls.length === 0 ? (
            <EmptyState
              icon={<PhoneCall size={22} />}
              title="No calls yet"
              description="Place a real call and it will appear here."
            />
          ) : (
            <Card>
              <ul className="divide-y divide-line-200">
                {recentCalls.map((call) => {
                  const seconds = callDurationSeconds(call.created_at, call.ended_at);
                  return (
                    <li key={call.call_id}>
                      <Link
                        href={`/calls/history/${encodeURIComponent(call.call_id)}`}
                        className="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-cream-50"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-ink-900">
                            {call.caller_number ?? call.destination_number}
                          </span>
                          <span className="block text-xs text-ink-500">
                            {formatDateTime(call.created_at)} · {formatDuration(seconds)}
                          </span>
                        </span>
                        <Badge status={call.status} />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </section>

        <div className="space-y-8 lg:col-span-2">
          <section>
            <SectionHeading title="AI Employees" />
            {employees.loading ? (
              <LoadingState label="employees" />
            ) : (employees.data ?? []).length === 0 ? (
              <Card className="p-5 text-center">
                <p className="text-sm text-ink-500">No employees yet.</p>
                <div className="mt-3">
                  <Link href="/employees/new">
                    <Button variant="secondary" size="sm">Create one</Button>
                  </Link>
                </div>
              </Card>
            ) : (
              <Card className="space-y-1 p-2">
                {(employees.data ?? []).map((employee) => (
                  <Link
                    key={employee.id}
                    href={`/employees/${encodeURIComponent(employee.id)}`}
                    className="flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-cream-50"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-ink-900">
                        {employee.name}
                      </span>
                      <span className="block text-xs text-ink-500">
                        {employee.role}
                      </span>
                    </span>
                    <Badge status={employee.status} />
                  </Link>
                ))}
              </Card>
            )}
          </section>

          <section>
            <SectionHeading title="Call Activity" />
            <Card className="p-5">
              <Unavailable label="Per-day activity chart" />
              <p className="mt-1 text-xs text-ink-500">
                Needs an analytics aggregate endpoint first.
              </p>
            </Card>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
