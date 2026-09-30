"use client";

import { use } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState } from "@/components/data-states";
import { EmployeeHeader } from "@/components/employee-header";
import { EmployeeTabs } from "@/components/employee-tabs";
import { Badge, Card, SectionHeading } from "@/components/ui";
import { knowledgeApi } from "@/lib/api/resources";
import { formatDateTime } from "@/lib/format";
import { useEmployee } from "@/lib/use-employee";
import { useResource } from "@/lib/use-resource";

export default function EmployeeKnowledgePage({
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
  const { data: sources } = useResource(() =>
    knowledgeApi.listSources(tenantId),
  );

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

  const associated = new Set(employee.knowledge_sources);

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

      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <section>
          <SectionHeading
            title="Associated sources"
            subtitle="Source references stored on this employee."
          />
          {employee.knowledge_sources.length === 0 ? (
            <p className="rounded-xl border border-dashed border-line-300 bg-white px-5 py-8 text-center text-sm text-ink-500">
              No knowledge sources are associated with {employee.name} yet.
            </p>
          ) : (
            <Card>
              <ul className="divide-y divide-line-200">
                {employee.knowledge_sources.map((source) => (
                  <li key={source} className="px-5 py-3.5">
                    <p className="font-mono text-sm text-ink-900">{source}</p>
                    <p className="mt-0.5 text-xs text-ink-500">
                      Associated reference — resolved against tenant sources on the right.
                    </p>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </section>

        <section>
          <SectionHeading
            title="Tenant sources"
            subtitle="Real sources in this tenant. Badges mark actual association."
            action={
              <Link
                href="/knowledge"
                className="text-sm font-medium text-brand-700 hover:text-brand-800"
              >
                Manage
              </Link>
            }
          />
          {sources === null ? (
            <LoadingState label="knowledge sources" />
          ) : sources.length === 0 ? (
            <p className="rounded-xl border border-dashed border-line-300 bg-white px-5 py-8 text-center text-sm text-ink-500">
              No knowledge sources in tenant {tenantId} yet.
            </p>
          ) : (
            <Card>
              <ul className="divide-y divide-line-200">
                {sources.map((source) => (
                  <li key={source.id} className="flex items-center gap-4 px-5 py-3.5">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-ink-900">
                        {source.name}
                      </span>
                      <span className="block text-xs text-ink-500">
                        {source.source_type} · updated {formatDateTime(source.updated_at)}
                      </span>
                    </span>
                    {associated.has(source.id) || associated.has(source.name) ? (
                      <Badge status="completed" label="ASSOCIATED" />
                    ) : (
                      <span className="text-xs text-ink-500">Not associated</span>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </section>
      </div>
    </AppShell>
  );
}
