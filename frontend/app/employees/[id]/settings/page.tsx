"use client";

import { use, useState } from "react";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState } from "@/components/data-states";
import { EmployeeHeader } from "@/components/employee-header";
import { EmployeeTabs } from "@/components/employee-tabs";
import {
  Button,
  Card,
  Field,
  SectionHeading,
  Select,
  Textarea,
  TextInput,
} from "@/components/ui";
import { agentsApi } from "@/lib/api/resources";
import { useEmployee } from "@/lib/use-employee";

/** Settings exposes exactly the Agent fields the PATCH endpoint persists:
 * name, description, role, language and greeting. Anything else is omitted
 * rather than faked. */

export default function EmployeeSettingsPage({
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

  const [draft, setDraft] = useState<{
    name: string;
    description: string;
    role: string;
    language: string;
    greeting: string;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

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

  async function save(current: NonNullable<typeof employee>) {
    // Draft overlays the loaded record; untouched fields keep backend values.
    const form = {
      name: current.name,
      description: current.description,
      role: current.role,
      language: current.language,
      greeting: current.greeting ?? "",
      ...draft,
    };
    if (saving) return;
    setSaving(true);
    setSaved(false);
    setSaveError(null);
    try {
      await agentsApi.update(current.id, {
        tenant_id: current.tenant_id,
        name: form.name.trim() || current.name,
        description: form.description,
        role: form.role.trim() || current.role,
        status: current.status,
        system_prompt: current.system_prompt,
        personality: current.personality,
        language: form.language,
        voice_id: current.voice_id,
        greeting: form.greeting.trim() || null,
        goals: current.goals,
        allowed_tools: current.allowed_tools,
        knowledge_sources: current.knowledge_sources,
      });
      setSaved(true);
      setDraft(null);
      reload();
    } catch (error) {
      setSaveError(
        error instanceof Error ? error.message : "Could not save settings.",
      );
    } finally {
      setSaving(false);
    }
  }

  function edit<Key extends keyof NonNullable<typeof draft>>(
    key: Key,
    value: string,
  ) {
    const base = employee
      ? {
          name: employee.name,
          description: employee.description,
          role: employee.role,
          language: employee.language,
          greeting: employee.greeting ?? "",
        }
      : { name: "", description: "", role: "", language: "en", greeting: "" };
    setDraft({ ...base, ...draft, [key]: value });
  }

  const form = employee
    ? {
        name: employee.name,
        description: employee.description,
        role: employee.role,
        language: employee.language,
        greeting: employee.greeting ?? "",
        ...draft,
      }
    : { name: "", description: "", role: "", language: "en", greeting: "" };

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

      <div className="mt-8 max-w-2xl">
        <SectionHeading
          title="Settings"
          subtitle="Only fields the backend persists are shown."
        />
        {saved ? (
          <p className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800" role="status">
            Saved — the employee record was updated.
          </p>
        ) : null}
        {saveError ? (
          <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800" role="alert">
            Save failed: {saveError} — nothing was changed.
          </p>
        ) : null}
        <Card className="space-y-5 p-6">
          <Field label="Employee name">
            <TextInput
              value={form.name}
              onChange={(event) => edit("name", event.target.value)}
            />
          </Field>
          <Field label="Description">
            <Textarea
              value={form.description}
              onChange={(event) => edit("description", event.target.value)}
            />
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Role">
              <TextInput
              value={form.role}
              onChange={(event) => edit("role", event.target.value)}
              />
            </Field>
            <Field label="Language">
              <Select
              value={form.language}
              onChange={(event) => edit("language", event.target.value)}
              >
                <option value="en">English</option>
                <option value="hi">Hindi</option>
              </Select>
            </Field>
          </div>
          <Field
            label="Greeting"
            hint="Spoken first when a call connects. Empty means no greeting."
          >
            <Textarea
              value={form.greeting}
              onChange={(event) => edit("greeting", event.target.value)}
            />
          </Field>
          <div>
            <Button onClick={() => save(employee)} disabled={saving}>
              {saving ? "Saving…" : "Save settings"}
            </Button>
          </div>
        </Card>
        <p className="mt-3 text-xs text-ink-500">
          Status is controlled by Pause/Resume above. Voice catalogs, behavior
          rules and phone provisioning have no backend fields yet.
        </p>
      </div>
    </AppShell>
  );
}
