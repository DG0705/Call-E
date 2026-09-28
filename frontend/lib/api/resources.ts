import { apiRequest } from "./client";

/** Shared backend envelope conventions for Call-E resources. */

export type EmployeeStatus = "live" | "paused" | "draft" | "error";

export interface Employee {
  id: string;
  tenantId: string;
  name: string;
  description: string;
  role: string;
  status: EmployeeStatus;
  language: string;
  voiceId: string | null;
  greeting: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CreateEmployeePayload {
  name: string;
  description: string;
  role: string;
  roleDescription?: string;
  language: string;
  voiceId?: string;
  phoneNumber?: string;
  workingHours?: string;
  timezone?: string;
}

export interface CallRecord {
  id: string;
  agentId: string;
  conversationId: string;
  direction: "inbound" | "outbound";
  status: string;
  startedAt: string;
  endedAt: string | null;
  durationSeconds: number | null;
  customerNumber?: string;
}

export interface KnowledgeSource {
  id: string;
  name: string;
  kind: "document" | "website" | "text";
  status: string;
  createdAt: string;
}

const V1 = "/api/v1";

export const agentsApi = {
  list: (token?: string) =>
    apiRequest<Employee[]>(`${V1}/agents`, { token }),
  get: (id: string, token?: string) =>
    apiRequest<Employee>(`${V1}/agents/${id}`, { token }),
  create: (payload: CreateEmployeePayload, token?: string) =>
    apiRequest<Employee>(`${V1}/agents`, {
      method: "POST",
      body: payload,
      token,
    }),
};

export const callsApi = {
  list: (token?: string) => apiRequest<CallRecord[]>(`${V1}/calls`, { token }),
  get: (id: string, token?: string) =>
    apiRequest<CallRecord>(`${V1}/calls/${id}`, { token }),
};

export const knowledgeApi = {
  list: (token?: string) =>
    apiRequest<KnowledgeSource[]>(`${V1}/knowledge/sources`, { token }),
};
