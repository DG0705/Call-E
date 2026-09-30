"use client";

import { use } from "react";
import { notFound } from "next/navigation";
import { MessagesSquare } from "lucide-react";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState } from "@/components/data-states";
import { EmployeeHeader } from "@/components/employee-header";
import { EmployeeTabs } from "@/components/employee-tabs";
import { EmptyState } from "@/components/ui";
import { useEmployee } from "@/lib/use-employee";

/** Transcripts live in service logs today — no stored conversation history
 * exists — so this section is an honest empty state, never mock dialogue. */

export default function EmployeeConversationPage({
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
  } = useEmployee(id);

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
        <EmptyState
          icon={<MessagesSquare size={22} />}
          title="Conversation history is not available yet"
          description="Turn transcripts are emitted to service logs today and are not stored per employee. Per-call records live under this employee's Calls tab."
        />
      </div>
    </AppShell>
  );
}
