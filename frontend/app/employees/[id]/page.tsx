"use client";

import { use } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState, Unavailable } from "@/components/data-states";
import { EmployeeHeader } from "@/components/employee-header";
import { EmployeeTabs } from "@/components/employee-tabs";
import { Badge, Card, SectionHeading } from "@/components/ui";
import { callsApi } from "@/lib/api/resources";
import {
  callDurationSeconds,
  formatDateTime,
  formatDuration,
} from "@/lib/format";
import { useEmployee } from "@/lib/use-employee";
import { useResource } from "@/lib/use-resource";

export default function EmployeeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const {
    employee,
    error,
    loading,
    reload,
    toggling,
    toggleStatus,
    toggleError,
    tenantId,
  } = useEmployee(id);
  const { data: calls } = useResource(() => callsApi.list(tenantId, 50));

  if (loading) {
    return (
      <AppShell>
        <LoadingState label="employee" />
      </AppShell>
    );
  }
  if (!employee) {
    if (error?.includes("404") || error?.includes("not found")) notFound();
    return (
      <AppShell>
        <ErrorState message={error ?? "Employee not found."} onRetry={reload} />
      </AppShell>
    );
  }

  // The calls API has no server-side agent filter, so the tenant call list
  // is filtered to this employee client-side. Counts below are real records.
  const employeeCalls = (calls ?? []).filter(
    (call) => call.agent_id === employee.id,
  );

  return (
    <AppShell>
      <EmployeeHeader
        employee={employee}
        toggling={toggling}
        onToggle={toggleStatus}
      />
      {toggleError ? (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800" role="alert">
          {toggleError}
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-500">Calls (recent)</p>
          <p className="mt-1 font-display text-2xl text-ink-900">
            {calls ? employeeCalls.length : "—"}
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-500">Success rate</p>
          <p className="mt-1 font-display text-2xl text-ink-900">—</p>
          <p className="mt-1 text-xs text-ink-500">Not available yet</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-500">Leads</p>
          <p className="mt-1 font-display text-2xl text-ink-900">—</p>
          <p className="mt-1 text-xs text-ink-500">Not available yet</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-500">Voice</p>
          <p className="mt-1 font-display text-2xl text-ink-900">
            {employee.voice_id ?? "Default"}
          </p>
          <p className="mt-1 text-xs text-ink-500">{employee.language}</p>
        </Card>
      </div>

      <div className="mt-8">
        <EmployeeTabs employeeId={employee.id} />
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <section>
          <SectionHeading title="Configuration" />
          <Card className="p-5">
            <dl className="space-y-3 text-sm">
              {(
                [
                  ["Role", employee.role],
                  ["Personality", employee.personality],
                  ["Language", employee.language],
                  ["Voice", employee.voice_id ?? "Default"],
                  ["Greeting", employee.greeting ?? "—"],
                  ["Tools", employee.allowed_tools.length ? employee.allowed_tools.join(", ") : "—"],
                  ["Knowledge sources", employee.knowledge_sources.length ? employee.knowledge_sources.join(", ") : "—"],
                  ["Updated", formatDateTime(employee.updated_at)],
                ] as const
              ).map(([term, value]) => (
                <div key={term} className="flex gap-4">
                  <dt className="w-36 shrink-0 text-ink-500">{term}</dt>
                  <dd className="text-ink-800">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </section>

        <section>
          <SectionHeading
            title="Recent calls"
            action={
              <Link
                href={`/employees/${encodeURIComponent(employee.id)}/calls`}
                className="text-sm font-medium text-brand-700 hover:text-brand-800"
              >
                View all
              </Link>
            }
          />
          <Card>
            {calls === null ? (
              <p className="px-5 py-8 text-center text-sm text-ink-500">
                Loading calls…
              </p>
            ) : employeeCalls.length === 0 ? (
              <p className="px-5 py-8 text-center text-sm text-ink-500">
                No calls yet for this employee.
              </p>
            ) : (
              <ul className="divide-y divide-line-200">
                {employeeCalls.slice(0, 5).map((call) => {
                  const seconds = callDurationSeconds(call.created_at, call.ended_at);
                  return (
                    <li key={call.call_id}>
                      <Link
                        href={`/calls/history/${encodeURIComponent(call.call_id)}`}
                        className="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-cream-50"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium text-ink-900">
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
            )}
          </Card>
          <div className="mt-4">
            <Unavailable label="Success rate, leads and latency" />
          </div>
        </section>
      </div>
    </AppShell>
  );
}
