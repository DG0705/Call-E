"use client";

import Link from "next/link";
import { Pause, Play, Plus } from "lucide-react";
import { useState } from "react";
import { AppShell } from "@/components/shell";
import { ErrorState } from "@/components/data-states";
import { Badge, Button, Card, EmptyState, PageHeader } from "@/components/ui";
import { agentsApi, type Employee } from "@/lib/api/resources";
import { initials } from "@/lib/format";
import { getTenantId } from "@/lib/tenant";
import { useResource } from "@/lib/use-resource";
import { Bot } from "lucide-react";

function EmployeeCard({
  employee,
  onToggle,
  toggling,
}: {
  employee: Employee;
  onToggle: (employee: Employee) => void;
  toggling: boolean;
}) {
  const live = employee.status === "active";
  return (
    <Card className="flex flex-col p-6">
      <div className="flex items-start justify-between gap-3">
        <span className="flex size-12 items-center justify-center rounded-xl bg-brand-700 font-display text-base font-semibold text-white">
          {initials(employee.name)}
        </span>
        <Badge status={employee.status} />
      </div>
      <h2 className="mt-4 font-display text-xl text-ink-900">{employee.name}</h2>
      <p className="mt-1 text-sm text-ink-500">
        {employee.description || employee.role}
      </p>

      <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-line-200 pt-4">
        <div>
          <dt className="text-[11px] font-medium uppercase tracking-wider text-ink-500">
            Role
          </dt>
          <dd className="mt-0.5 text-sm font-semibold text-ink-900">
            {employee.role}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium uppercase tracking-wider text-ink-500">
            Language
          </dt>
          <dd className="mt-0.5 text-sm font-semibold text-ink-900">
            {employee.language}
          </dd>
        </div>
      </dl>

      <div className="mt-5 flex flex-wrap gap-2 border-t border-line-200 pt-4">
        <Link href={`/employees/${encodeURIComponent(employee.id)}`} className="flex-1">
          <Button variant="secondary" size="sm" className="w-full">
            Open
          </Button>
        </Link>
        <Button
          variant="secondary"
          size="sm"
          disabled={toggling}
          onClick={() => onToggle(employee)}
          aria-label={`${live ? "Pause" : "Resume"} ${employee.name}`}
        >
          {live ? <Pause size={15} /> : <Play size={15} />}
          {live ? "Pause" : "Resume"}
        </Button>
      </div>
    </Card>
  );
}

export default function EmployeesPage() {
  const tenantId = getTenantId();
  const { data, error, loading, reload } = useResource(() =>
    agentsApi.list(tenantId),
  );
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);

  async function toggleStatus(employee: Employee) {
    setTogglingId(employee.id);
    setToggleError(null);
    try {
      await agentsApi.update(employee.id, {
        tenant_id: employee.tenant_id,
        name: employee.name,
        description: employee.description,
        role: employee.role,
        status: employee.status === "active" ? "paused" : "active",
        system_prompt: employee.system_prompt,
        personality: employee.personality,
        language: employee.language,
        voice_id: employee.voice_id,
        greeting: employee.greeting,
        goals: employee.goals,
        allowed_tools: employee.allowed_tools,
        knowledge_sources: employee.knowledge_sources,
      });
      reload();
    } catch (error) {
      setToggleError(
        error instanceof Error ? error.message : "Could not update status.",
      );
    } finally {
      setTogglingId(null);
    }
  }

  return (
    <AppShell>
      <PageHeader
        title="AI Employees"
        subtitle="Create, configure and deploy AI employees that handle real customer conversations."
        actions={
          <Link href="/employees/new">
            <Button>
              <Plus size={16} /> Create AI Employee
            </Button>
          </Link>
        }
      />

      {toggleError ? (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800" role="alert">
          {toggleError}
        </p>
      ) : null}

      {loading ? (
        <Card className="px-5 py-10 text-center text-sm text-ink-500" >
          <span role="status">Loading employees…</span>
        </Card>
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data === null || data.length === 0 ? (
        <EmptyState
          icon={<Bot size={22} />}
          title="No AI employees yet"
          description="Create your first employee to start handling customer conversations."
          action={
            <Link href="/employees/new">
              <Button>
                <Plus size={16} /> Create AI Employee
              </Button>
            </Link>
          }
        />
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {data.map((employee) => (
            <EmployeeCard
              key={employee.id}
              employee={employee}
              toggling={togglingId === employee.id}
              onToggle={toggleStatus}
            />
          ))}
        </div>
      )}
    </AppShell>
  );
}
