"use client";

import { use } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState } from "@/components/data-states";
import { EmployeeHeader } from "@/components/employee-header";
import { EmployeeTabs } from "@/components/employee-tabs";
import { Badge, Card, EmptyState, SectionHeading } from "@/components/ui";
import { callsApi } from "@/lib/api/resources";
import {
  callDurationSeconds,
  formatDateTime,
  formatDuration,
} from "@/lib/format";
import { useEmployee } from "@/lib/use-employee";
import { useResource } from "@/lib/use-resource";
import { PhoneCall } from "lucide-react";

export default function EmployeeCallsPage({
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
  const { data: calls } = useResource(() => callsApi.list(tenantId, 100));

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

  // The calls API exposes no agent_id query parameter, so the tenant call
  // list is filtered to this employee client-side. Only this employee's real
  // records are ever shown.
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
      <div className="mt-2">
        <EmployeeTabs employeeId={employee.id} />
      </div>

      <div className="mt-8">
        <SectionHeading
          title="Calls"
          subtitle={`${employeeCalls.length} call${employeeCalls.length === 1 ? "" : "s"} for ${employee.name}. Newest first.`}
        />
        {calls === null ? (
          <LoadingState label="calls" />
        ) : employeeCalls.length === 0 ? (
          <EmptyState
            icon={<PhoneCall size={22} />}
            title="No calls yet"
            description={`${employee.name} has not handled any calls in tenant ${tenantId}.`}
          />
        ) : (
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-left text-sm">
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
                  {employeeCalls.map((call) => {
                    const seconds = callDurationSeconds(
                      call.created_at,
                      call.ended_at,
                    );
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
      </div>
    </AppShell>
  );
}
