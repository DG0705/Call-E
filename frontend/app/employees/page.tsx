import Link from "next/link";
import { Pause, Pencil, PhoneCall, Play, Plus } from "lucide-react";
import { AppShell } from "@/components/shell";
import { Badge, Button, Card, DemoBadge, PageHeader } from "@/components/ui";
import { getDemoEmployees } from "@/lib/mock/data";

/* DEMO DATA — replace with lib/api/resources.ts calls when backend is wired. */

export default function EmployeesPage() {
  const employees = getDemoEmployees();

  return (
    <AppShell>
      <PageHeader
        title="AI Employees"
        subtitle="Create, configure and deploy AI employees that handle real customer conversations."
        actions={
          <>
            <DemoBadge />
            <Link href="/employees/new">
              <Button>
                <Plus size={16} /> Create AI Employee
              </Button>
            </Link>
          </>
        }
      />

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {employees.map((employee) => (
          <Card key={employee.id} className="flex flex-col p-6">
            <div className="flex items-start justify-between gap-3">
              <span className="flex size-12 items-center justify-center rounded-xl bg-brand-700 font-display text-base font-semibold text-white">
                {employee.initials}
              </span>
              <Badge status={employee.status} />
            </div>
            <h2 className="mt-4 font-display text-xl text-ink-900">
              {employee.name}
            </h2>
            <p className="mt-1 text-sm text-ink-500">{employee.description}</p>

            <dl className="mt-5 grid grid-cols-3 gap-3 border-t border-line-200 pt-4">
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wider text-ink-500">
                  Calls
                </dt>
                <dd className="mt-0.5 text-base font-semibold text-ink-900">
                  {employee.calls}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wider text-ink-500">
                  Success
                </dt>
                <dd className="mt-0.5 text-base font-semibold text-ink-900">
                  {employee.successRate}%
                </dd>
              </div>
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wider text-ink-500">
                  Avg call
                </dt>
                <dd className="mt-0.5 text-base font-semibold text-ink-900">
                  {employee.avgDuration}
                </dd>
              </div>
            </dl>

            <div className="mt-5 flex flex-wrap gap-2 border-t border-line-200 pt-4">
              <Link href={`/employees/${employee.id}`} className="flex-1">
                <Button variant="secondary" size="sm" className="w-full">
                  Open
                </Button>
              </Link>
              <Button variant="secondary" size="sm" aria-label={`Edit ${employee.name}`}>
                <Pencil size={15} />
              </Button>
              <Button variant="secondary" size="sm" aria-label={`Test call ${employee.name}`}>
                <PhoneCall size={15} />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`${employee.status === "live" ? "Pause" : "Resume"} ${employee.name}`}
              >
                {employee.status === "live" ? <Pause size={15} /> : <Play size={15} />}
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
