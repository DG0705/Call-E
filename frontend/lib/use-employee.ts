"use client";

import { useState } from "react";
import { agentsApi, type Employee } from "./api/resources";
import { getTenantId } from "./tenant";
import { useResource } from "./use-resource";

/** Shared employee loader + pause/resume used by every employee section page. */

interface EmployeeState {
  employee: Employee | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  toggling: boolean;
  toggleStatus: (current: Employee) => Promise<void>;
  toggleError: string | null;
  tenantId: string;
  id: string;
}

export function useEmployee(id: string): EmployeeState {
  const tenantId = getTenantId();
  const { data, error, loading, reload } = useResource(() =>
    agentsApi.get(decodeURIComponent(id), tenantId),
  );
  const [toggling, setToggling] = useState(false);
  const [toggleError, setToggleError] = useState<string | null>(null);

  async function toggleStatus(current: Employee) {
    setToggling(true);
    setToggleError(null);
    try {
      await agentsApi.update(current.id, {
        tenant_id: current.tenant_id,
        name: current.name,
        description: current.description,
        role: current.role,
        status: current.status === "active" ? "paused" : "active",
        system_prompt: current.system_prompt,
        personality: current.personality,
        language: current.language,
        voice_id: current.voice_id,
        greeting: current.greeting,
        goals: current.goals,
        allowed_tools: current.allowed_tools,
        knowledge_sources: current.knowledge_sources,
      });
      reload();
    } catch (error) {
      setToggleError(
        error instanceof Error ? error.message : "Could not update status.",
      );
    } finally {
      setToggling(false);
    }
  }

  return {
    employee: data,
    error,
    loading,
    reload,
    toggling,
    toggleStatus,
    toggleError,
    tenantId,
    id,
  };
}
