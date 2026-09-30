"use client";

import { Pause, Play } from "lucide-react";
import { Badge, Button } from "./ui";
import { initials } from "@/lib/format";
import type { Employee } from "@/lib/api/resources";

export function EmployeeHeader({
  employee,
  toggling,
  onToggle,
}: {
  employee: Employee;
  toggling: boolean;
  onToggle: (employee: Employee) => void;
}) {
  const live = employee.status === "active";
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-center gap-4">
        <span className="flex size-14 items-center justify-center rounded-2xl bg-brand-700 font-display text-lg font-semibold text-white">
          {initials(employee.name)}
        </span>
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-3xl tracking-tight text-ink-900">
              {employee.name}
            </h1>
            <Badge status={employee.status} />
          </div>
          <p className="mt-1 text-[15px] text-ink-500">
            {employee.description || employee.role} · {employee.tenant_id}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="secondary" disabled={toggling} onClick={() => onToggle(employee)}>
          {live ? <Pause size={16} /> : <Play size={16} />}
          {live ? "Pause" : "Resume"}
        </Button>
      </div>
    </div>
  );
}
