import { apiRequest, apiUpload } from "./client";

/** Typed resources backed by the real Call-E services.
 *
 * Browsers enforce CORS and the backend services emit no CORS headers, so
 * pages never call service ports directly. All paths below are same-origin
 * `/backend/*` routes that the Next.js server proxies to the configured
 * service (see `next.config.ts` rewrites). No backend change is needed.
 */

const AGENT_API = "/backend/agents";
const KNOWLEDGE_API = "/backend/knowledge";
const VOICE_API = "/backend/voice";

export type EmployeeStatus = "live" | "active" | "paused" | "draft" | "error" | "failed" | "ended";

/** AI employee exactly as the agent-service persists it. */
export interface Employee {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  role: string;
  status: string;
  system_prompt: string;
  personality: string;
  language: string;
  voice_id: string | null;
  greeting: string | null;
  goals: string[];
  allowed_tools: string[];
  knowledge_sources: string[];
  created_at: string;
  updated_at: string;
}

export interface CreateEmployeePayload {
  tenant_id: string;
  name: string;
  description?: string;
  role?: string;
  status?: string;
  system_prompt?: string;
  personality?: string;
  language?: string;
  voice_id?: string | null;
  greeting?: string | null;
  goals?: string[];
  allowed_tools?: string[];
  knowledge_sources?: string[];
}

export type UpdateEmployeePayload = CreateEmployeePayload;

/** Call record exactly as the voice-service persists it. */
export interface CallRecord {
  call_id: string;
  tenant_id: string;
  agent_id: string;
  conversation_id: string;
  caller_number: string | null;
  destination_number: string;
  direction: "inbound" | "outbound";
  status: "ringing" | "answered" | "active" | "ended" | "failed";
  provider: string;
  created_at: string;
  updated_at: string;
  ended_at: string | null;
  error_code: string | null;
}

/** Knowledge source exactly as the knowledge-service persists it. */
export interface KnowledgeSource {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  source_type: "text" | "markdown" | "html" | "pdf";
  status: string;
  created_at: string;
  updated_at: string;
}

/** Knowledge document exactly as the knowledge-service persists it. */
export interface KnowledgeDocument {
  id: string;
  tenant_id: string;
  source_id: string;
  title: string;
  source_type: "text" | "markdown" | "html" | "pdf";
  status: "uploaded" | "processing" | "ready" | "failed";
  error: string | null;
  chunks: number;
  file_name: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  source_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface UploadFileResult {
  file_name: string;
  source_id: string | null;
  document_id: string | null;
  status: string;
  chunks: number;
  error: string | null;
}

export interface RetrievedChunk {
  document_id: string;
  chunk_id: string;
  content: string;
  score: number;
}

function withTenant(path: string, tenantId: string, extra = "") {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}tenant_id=${encodeURIComponent(tenantId)}${extra}`;
}

export const agentsApi = {
  list: (tenantId: string, token?: string) =>
    apiRequest<Employee[]>(AGENT_API, withTenant("/api/v1/agents", tenantId), {
      token,
    }),
  get: (agentId: string, tenantId: string, token?: string) =>
    apiRequest<Employee>(
      AGENT_API,
      withTenant(`/api/v1/agents/${encodeURIComponent(agentId)}`, tenantId),
      { token },
    ),
  create: (payload: CreateEmployeePayload, token?: string) =>
    apiRequest<Employee>(AGENT_API, "/api/v1/agents", {
      method: "POST",
      body: payload,
      token,
    }),
  update: (agentId: string, payload: UpdateEmployeePayload, token?: string) =>
    apiRequest<Employee>(
      AGENT_API,
      `/api/v1/agents/${encodeURIComponent(agentId)}`,
      { method: "PATCH", body: payload, token },
    ),
};

export const callsApi = {
  list: (tenantId: string, limit = 50, token?: string) =>
    apiRequest<CallRecord[]>(
      VOICE_API,
      withTenant("/api/v1/telephony/calls", tenantId, `&limit=${limit}`),
      { token },
    ),
  get: (callId: string, tenantId: string, token?: string) =>
    apiRequest<CallRecord>(
      VOICE_API,
      withTenant(
        `/api/v1/telephony/calls/${encodeURIComponent(callId)}`,
        tenantId,
      ),
      { token },
    ),
};

export const knowledgeApi = {
  listSources: (tenantId: string, token?: string) =>
    apiRequest<KnowledgeSource[]>(
      KNOWLEDGE_API,
      withTenant("/api/v1/knowledge/sources", tenantId),
      { token },
    ),
  createSource: (
    payload: {
      tenant_id: string;
      name: string;
      description?: string;
      source_type?: KnowledgeSource["source_type"];
    },
    token?: string,
  ) =>
    apiRequest<KnowledgeSource>(KNOWLEDGE_API, "/api/v1/knowledge/sources", {
      method: "POST",
      body: payload,
      token,
    }),
  listDocuments: (tenantId: string, token?: string) =>
    apiRequest<KnowledgeDocument[]>(
      KNOWLEDGE_API,
      withTenant("/api/v1/knowledge/documents", tenantId),
      { token },
    ),
  createDocument: (
    payload: {
      tenant_id: string;
      source_id: string;
      title: string;
      source_type?: KnowledgeDocument["source_type"];
      raw_content: string;
    },
    token?: string,
  ) =>
    apiRequest<KnowledgeDocument>(KNOWLEDGE_API, "/api/v1/knowledge/documents", {
      method: "POST",
      body: payload,
      token,
    }),
  ingestDocument: (documentId: string, tenantId: string, token?: string) =>
    apiRequest<{ document_id: string; tenant_id: string; chunks: number }>(
      KNOWLEDGE_API,
      `/api/v1/knowledge/documents/${encodeURIComponent(documentId)}/ingest`,
      { method: "POST", body: { tenant_id: tenantId }, token },
    ),
  getSource: (sourceId: string, tenantId: string, token?: string) =>
    apiRequest<KnowledgeSource>(
      KNOWLEDGE_API,
      withTenant(
        `/api/v1/knowledge/sources/${encodeURIComponent(sourceId)}`,
        tenantId,
      ),
      { token },
    ),
  getDocument: (documentId: string, tenantId: string, token?: string) =>
    apiRequest<KnowledgeDocument>(
      KNOWLEDGE_API,
      withTenant(
        `/api/v1/knowledge/documents/${encodeURIComponent(documentId)}`,
        tenantId,
      ),
      { token },
    ),
  deleteSource: (sourceId: string, tenantId: string, token?: string) =>
    apiRequest<void>(
      KNOWLEDGE_API,
      withTenant(
        `/api/v1/knowledge/sources/${encodeURIComponent(sourceId)}`,
        tenantId,
      ),
      { method: "DELETE", token },
    ),
  deleteDocument: (documentId: string, tenantId: string, token?: string) =>
    apiRequest<void>(
      KNOWLEDGE_API,
      withTenant(
        `/api/v1/knowledge/documents/${encodeURIComponent(documentId)}`,
        tenantId,
      ),
      { method: "DELETE", token },
    ),
  uploadFiles: (tenantId: string, files: File[], token?: string) => {
    const form = new FormData();
    form.append("tenant_id", tenantId);
    for (const file of files) form.append("files", file, file.name);
    return apiUpload<{ files: UploadFileResult[] }>(
      KNOWLEDGE_API,
      "/api/v1/knowledge/uploads",
      form,
      { token },
    );
  },
  ingestWebsite: (
    payload: { tenant_id: string; url: string; name?: string },
    token?: string,
  ) =>
    apiRequest<KnowledgeDocument>(KNOWLEDGE_API, "/api/v1/knowledge/websites", {
      method: "POST",
      body: payload,
      token,
    }),
  search: (
    payload: {
      tenant_id: string;
      agent_id: string;
      query: string;
      top_k?: number;
      source_ids?: string[];
    },
    token?: string,
  ) =>
    apiRequest<{
      tenant_id: string;
      agent_id: string;
      query: string;
      results: RetrievedChunk[];
    }>(KNOWLEDGE_API, "/api/v1/knowledge/search", {
      method: "POST",
      body: payload,
      token,
    }),
};
