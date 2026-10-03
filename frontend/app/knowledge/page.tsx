"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Beaker,
  CheckCircle2,
  ChevronDown,
  FileText,
  Globe,
  Link2,
  Loader2,
  Plus,
  RotateCw,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState } from "@/components/data-states";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  Field,
  PageHeader,
  SectionHeading,
  Select,
  Textarea,
  TextInput,
} from "@/components/ui";
import {
  agentsApi,
  knowledgeApi,
  type KnowledgeDocument,
  type RetrievedChunk,
} from "@/lib/api/resources";
import { formatDateTime } from "@/lib/format";
import { getTenantId } from "@/lib/tenant";
import { useResource } from "@/lib/use-resource";
import { clsx } from "clsx";

/** Mirrors the knowledge-service extraction whitelist and upload limit so the
 * browser rejects the same files the backend would, before a wasted round
 * trip. Keep in sync with `extraction.SUPPORTED_EXTENSIONS` and
 * `KNOWLEDGE_MAX_FILE_BYTES`. */
const SUPPORTED_EXTENSIONS = [
  ".pdf",
  ".docx",
  ".xlsx",
  ".csv",
  ".txt",
  ".md",
  ".markdown",
  ".html",
  ".htm",
  ".json",
];
const MAX_FILE_BYTES = 10_000_000;
const ACCEPTED_TYPES = SUPPORTED_EXTENSIONS.join(",");

type UploadPhase = "selected" | "uploading" | "ready" | "failed" | "rejected";

interface UploadItem {
  key: string;
  file: File;
  fileName: string;
  phase: UploadPhase;
  detail: string;
  documentId?: string;
  chunks?: number;
  retryable: boolean;
}

function extensionOf(name: string): string | null {
  const lower = name.toLowerCase();
  return SUPPORTED_EXTENSIONS.find((ext) => lower.endsWith(ext)) ?? null;
}

/** Return a human rejection reason, or null when the file may be uploaded. */
function validateFile(file: File, queuedNames: Set<string>): string | null {
  if (!extensionOf(file.name)) return `Unsupported file type “${file.name}”.`;
  if (file.size === 0) return `“${file.name}” is empty.`;
  if (file.size > MAX_FILE_BYTES) return `“${file.name}” exceeds the 10 MB limit.`;
  if (queuedNames.has(file.name)) return `“${file.name}” is already in this batch.`;
  return null;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "ready"
      ? "completed"
      : status === "failed"
        ? "failed"
        : "in-progress";
  return <Badge status={tone} label={status.toUpperCase()} />;
}

function UploadRow({
  item,
  onRetry,
}: {
  item: UploadItem;
  onRetry: (item: UploadItem) => void;
}) {
  const icon =
    item.phase === "ready" ? (
      <CheckCircle2 size={16} className="text-emerald-600" />
    ) : item.phase === "failed" || item.phase === "rejected" ? (
      <AlertCircle size={16} className="text-red-600" />
    ) : item.phase === "uploading" ? (
      <Loader2 size={16} className="animate-spin text-brand-600" />
    ) : (
      <FileText size={16} className="text-ink-500" />
    );
  const label =
    item.phase === "ready"
      ? "Ready"
      : item.phase === "failed"
        ? "Failed"
        : item.phase === "rejected"
          ? "Rejected"
          : item.phase === "uploading"
            ? "Uploading & processing"
            : "Selected";
  return (
    <li className="rounded-lg border border-line-200 bg-white px-4 py-2.5 text-sm">
      <span className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2">
          {icon}
          <span className="truncate font-medium text-ink-900">{item.fileName}</span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span
            className={clsx(
              "text-xs font-medium",
              item.phase === "ready"
                ? "text-emerald-700"
                : item.phase === "failed" || item.phase === "rejected"
                  ? "text-red-700"
                  : "text-ink-500",
            )}
          >
            {label}
          </span>
          {item.phase === "failed" && item.retryable ? (
            <Button size="sm" variant="secondary" onClick={() => onRetry(item)}>
              <RotateCw size={14} /> Retry
            </Button>
          ) : null}
        </span>
      </span>
      <span className="mt-0.5 block text-xs text-ink-500">{item.detail}</span>
    </li>
  );
}

export default function KnowledgePage() {
  const tenantId = getTenantId();
  const sources = useResource(() => knowledgeApi.listSources(tenantId));
  const documents = useResource(() => knowledgeApi.listDocuments(tenantId));
  const employees = useResource(() =>
    import("@/lib/api/resources").then((api) => api.agentsApi.list(tenantId)),
  );

  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string[]>([]);

  // Upload queue (per-file independent state)
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const mounted = useRef(true);
  const keySeq = useRef(0);

  // Note form
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [noteTitle, setNoteTitle] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [targetSource, setTargetSource] = useState("");

  // Website form
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [websiteName, setWebsiteName] = useState("");

  // Retrieval tester
  const [testAgent, setTestAgent] = useState("");
  const [testQuery, setTestQuery] = useState("");
  const [testResults, setTestResults] = useState<RetrievedChunk[] | null>(null);
  const [testing, setTesting] = useState(false);

  // Attach/detach
  const [attachEmployee, setAttachEmployee] = useState("");
  const [attachSource, setAttachSource] = useState("");

  // Delete confirmation
  const [confirm, setConfirm] = useState<
    { kind: "source" | "document"; id: string; name: string } | null
  >(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!confirm) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setConfirm(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirm]);

  function refreshAll() {
    sources.reload();
    documents.reload();
    employees.reload();
  }

  function updateItem(key: string, patch: Partial<UploadItem>) {
    if (!mounted.current) return;
    setUploads((prev) =>
      prev.map((item) => (item.key === key ? { ...item, ...patch } : item)),
    );
  }

  /** Upload each file in its own request so one failure never masks another. */
  async function processUploads(items: UploadItem[]) {
    for (const item of items) {
      if (!mounted.current) return;
      updateItem(item.key, {
        phase: "uploading",
        detail: "Uploading and processing…",
      });
      try {
        const result = await knowledgeApi.uploadFiles(tenantId, [item.file]);
        const file = result.files[0];
        if (!file) {
          updateItem(item.key, {
            phase: "failed",
            detail: "Upload returned no result.",
            retryable: false,
          });
          continue;
        }
        if (file.status === "ready") {
          updateItem(item.key, {
            phase: "ready",
            detail: `${file.chunks} chunk${file.chunks === 1 ? "" : "s"} indexed.`,
            documentId: file.document_id ?? undefined,
            chunks: file.chunks,
            retryable: false,
          });
        } else {
          // Uploaded but extraction/ingestion failed (or rejected server-side).
          updateItem(item.key, {
            phase: "failed",
            detail: file.error ?? "Processing failed.",
            documentId: file.document_id ?? undefined,
            retryable: Boolean(file.document_id),
          });
        }
      } catch (error) {
        updateItem(item.key, {
          phase: "failed",
          detail: errorMessage(error, "Upload failed."),
          retryable: false,
        });
      }
    }
    if (mounted.current) refreshAll();
  }

  function handleFiles(list: FileList | null) {
    if (!list || list.length === 0 || uploading) return;
    const incoming = Array.from(list);
    const queuedNames = new Set(uploads.map((item) => item.fileName));
    const created: UploadItem[] = [];
    for (const file of incoming) {
      const reason = validateFile(file, queuedNames);
      const key = `upload-${keySeq.current++}`;
      if (reason) {
        created.push({
          key,
          file,
          fileName: file.name,
          phase: "rejected",
          detail: reason,
          retryable: false,
        });
      } else {
        queuedNames.add(file.name);
        created.push({
          key,
          file,
          fileName: file.name,
          phase: "selected",
          detail: "Waiting to upload…",
          retryable: false,
        });
      }
    }
    setUploads((prev) => [...created, ...prev]);
    setFailure(null);
    const valid = created.filter((item) => item.phase === "selected");
    if (valid.length === 0) return;
    setUploading(true);
    void processUploads(valid).finally(() => {
      if (mounted.current) setUploading(false);
    });
  }

  /** Re-ingest an existing document (idempotent — never creates duplicates). */
  async function retryItem(item: UploadItem) {
    if (!item.documentId) return;
    updateItem(item.key, {
      phase: "uploading",
      detail: "Re-processing…",
      retryable: false,
    });
    try {
      const result = await knowledgeApi.ingestDocument(item.documentId, tenantId);
      updateItem(item.key, {
        phase: "ready",
        detail: `${result.chunks} chunk${result.chunks === 1 ? "" : "s"} indexed.`,
        chunks: result.chunks,
        retryable: false,
      });
      setNotice(`“${item.fileName}” re-processed.`);
      refreshAll();
    } catch (error) {
      updateItem(item.key, {
        phase: "failed",
        detail: errorMessage(error, "Re-processing failed."),
        retryable: true,
      });
    }
  }

  async function retryDocument(document: KnowledgeDocument) {
    setFailure(null);
    setNotice(null);
    try {
      const result = await knowledgeApi.ingestDocument(
        document.id,
        document.tenant_id,
      );
      setNotice(
        `“${document.title}” re-processed into ${result.chunks} chunk${result.chunks === 1 ? "" : "s"}.`,
      );
    } catch (error) {
      setFailure(errorMessage(error, "Re-processing failed."));
    } finally {
      refreshAll();
    }
  }

  async function confirmDelete() {
    if (!confirm) return;
    setDeleting(true);
    setFailure(null);
    try {
      if (confirm.kind === "source") {
        await knowledgeApi.deleteSource(confirm.id, tenantId);
      } else {
        await knowledgeApi.deleteDocument(confirm.id, tenantId);
      }
      setNotice(
        `${confirm.kind === "source" ? "Source" : "Document"} “${confirm.name}” deleted.`,
      );
      setConfirm(null);
      refreshAll();
    } catch (error) {
      setFailure(errorMessage(error, "Delete failed."));
    } finally {
      setDeleting(false);
    }
  }

  async function createSource() {
    if (!name.trim() || busy) return;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      const source = await knowledgeApi.createSource({
        tenant_id: tenantId,
        name: name.trim(),
        description: description.trim(),
        source_type: "text",
      });
      setName("");
      setDescription("");
      setNotice(`Source “${source.name}” created.`);
      refreshAll();
    } catch (error) {
      setFailure(errorMessage(error, "Could not create the source."));
    } finally {
      setBusy(false);
    }
  }

  async function addNote() {
    if (!targetSource || !noteTitle.trim() || !noteBody.trim() || busy) return;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      const document = await knowledgeApi.createDocument({
        tenant_id: tenantId,
        source_id: targetSource,
        title: noteTitle.trim(),
        source_type: "text",
        raw_content: noteBody,
      });
      const result = await knowledgeApi.ingestDocument(document.id, tenantId);
      setNoteTitle("");
      setNoteBody("");
      setNotice(
        `Note ingested into ${result.chunks} chunk${result.chunks === 1 ? "" : "s"}.`,
      );
      refreshAll();
    } catch (error) {
      setFailure(errorMessage(error, "Could not add the note."));
    } finally {
      setBusy(false);
    }
  }

  async function addWebsite() {
    if (!websiteUrl.trim() || busy) return;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      const document = await knowledgeApi.ingestWebsite({
        tenant_id: tenantId,
        url: websiteUrl.trim(),
        name: websiteName.trim() || undefined,
      });
      setWebsiteUrl("");
      setWebsiteName("");
      if (document.status === "ready") {
        setNotice(`Page ingested into ${document.chunks} chunks.`);
      } else {
        setFailure(document.error ?? "Website ingestion failed.");
      }
      refreshAll();
    } catch (error) {
      setFailure(errorMessage(error, "Could not ingest the URL."));
    } finally {
      setBusy(false);
    }
  }

  async function runRetrievalTest() {
    if (!testAgent || !testQuery.trim() || testing) return;
    setTesting(true);
    setFailure(null);
    try {
      const agent = (employees.data ?? []).find((item) => item.id === testAgent);
      const result = await knowledgeApi.search({
        tenant_id: tenantId,
        agent_id: testAgent,
        query: testQuery.trim(),
        top_k: 5,
        source_ids:
          agent && agent.knowledge_sources.length > 0
            ? agent.knowledge_sources
            : undefined,
      });
      setTestResults(result.results);
    } catch (error) {
      setFailure(errorMessage(error, "Retrieval test failed."));
    } finally {
      setTesting(false);
    }
  }

  async function attachSelected(attach: boolean) {
    const agent = (employees.data ?? []).find(
      (item) => item.id === attachEmployee,
    );
    if (!agent || !attachSource || busy) return;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      const current = new Set(agent.knowledge_sources);
      if (attach) current.add(attachSource);
      else current.delete(attachSource);
      await agentsApi.update(agent.id, {
        tenant_id: agent.tenant_id,
        name: agent.name,
        description: agent.description,
        role: agent.role,
        status: agent.status,
        system_prompt: agent.system_prompt,
        personality: agent.personality,
        language: agent.language,
        voice_id: agent.voice_id,
        greeting: agent.greeting,
        goals: agent.goals,
        allowed_tools: agent.allowed_tools,
        knowledge_sources: Array.from(current),
      });
      setNotice(
        attach
          ? `Source attached to ${agent.name}.`
          : `Source detached from ${agent.name} — future retrieval skips it.`,
      );
      employees.reload();
    } catch (error) {
      setFailure(errorMessage(error, "Association update failed."));
    } finally {
      setBusy(false);
    }
  }

  function toggleExpanded(id: string) {
    setExpanded((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  }

  const docsBySource = new Map<string, KnowledgeDocument[]>();
  for (const document of documents.data ?? []) {
    const list = docsBySource.get(document.source_id) ?? [];
    list.push(document);
    docsBySource.set(document.source_id, list);
  }
  const documentById = new Map(
    (documents.data ?? []).map((document) => [document.id, document]),
  );
  const sourceById = new Map(
    (sources.data ?? []).map((source) => [source.id, source]),
  );

  return (
    <AppShell>
      <PageHeader
        title="Knowledge"
        subtitle={`Upload files, add a website page or write notes — everything lands in tenant ${tenantId} and becomes retrievable.`}
      />

      {notice ? (
        <p
          className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800"
          role="status"
        >
          {notice}
        </p>
      ) : null}
      {failure ? (
        <p
          className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800"
          role="alert"
        >
          {failure}
        </p>
      ) : null}

      <div className="grid gap-8 lg:grid-cols-3">
        <section>
          <SectionHeading
            title="Upload files"
            subtitle="PDF, DOCX, XLSX, CSV, TXT, MD, HTML, JSON · up to 10 MB each."
          />
          <div
            onDragOver={(event) => {
              event.preventDefault();
              if (!uploading) setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragActive(false);
              handleFiles(event.dataTransfer.files);
            }}
            className={clsx(
              "rounded-xl border border-dashed bg-white p-6 text-center transition-colors",
              dragActive
                ? "border-brand-500 bg-brand-50/60"
                : "border-line-300 hover:border-brand-400 hover:bg-brand-50/40",
            )}
          >
            <UploadCloud size={22} className="mx-auto text-ink-500" />
            <span className="mt-2 block text-sm font-medium text-ink-900">
              {uploading ? "Working…" : "Drag and drop, or choose files"}
            </span>
            <span className="mt-0.5 block text-xs text-ink-500">
              Multiple files at once · validated before upload
            </span>
            <label className="mt-3 inline-flex">
              <span
                className={clsx(
                  "inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-line-300 bg-white px-4 py-2 text-sm font-medium text-ink-800 shadow-sm transition-colors hover:bg-cream-100",
                  uploading && "cursor-not-allowed opacity-50",
                )}
              >
                {uploading ? "Uploading…" : "Choose files"}
              </span>
              <input
                type="file"
                multiple
                accept={ACCEPTED_TYPES}
                className="sr-only"
                disabled={uploading}
                onChange={(event) => {
                  handleFiles(event.target.files);
                  event.target.value = "";
                }}
              />
            </label>
          </div>
          {uploads.length > 0 ? (
            <ul className="mt-3 space-y-2">
              {uploads.map((item) => (
                <UploadRow
                  key={item.key}
                  item={item}
                  onRetry={(target) => void retryItem(target)}
                />
              ))}
            </ul>
          ) : null}
        </section>

        <section>
          <SectionHeading
            title="Add website page"
            subtitle="One URL → one document. No crawler yet."
          />
          <Card className="space-y-4 p-5">
            <Field
              label="Page URL"
              hint="Public http(s) pages only. Private hosts are refused."
            >
              <TextInput
                value={websiteUrl}
                onChange={(event) => setWebsiteUrl(event.target.value)}
                placeholder="https://www.example.com/pricing"
                inputMode="url"
              />
            </Field>
            <Field label="Name (optional)">
              <TextInput
                value={websiteName}
                onChange={(event) => setWebsiteName(event.target.value)}
                placeholder="Defaults to the page title"
              />
            </Field>
            <div>
              <Button onClick={addWebsite} disabled={!websiteUrl.trim() || busy}>
                <Globe size={16} /> {busy ? "Fetching…" : "Fetch and ingest"}
              </Button>
            </div>
          </Card>
        </section>

        <section>
          <SectionHeading
            title="Add a note"
            subtitle="Typed text, ingested immediately."
          />
          <Card className="space-y-4 p-5">
            <Field label="Source">
              <Select
                value={targetSource}
                onChange={(event) => setTargetSource(event.target.value)}
              >
                <option value="">Select a source…</option>
                {(sources.data ?? []).map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.name}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="New source name">
                <TextInput
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. Pricing policy"
                />
              </Field>
              <div className="flex items-end">
                <Button
                  variant="secondary"
                  onClick={createSource}
                  disabled={!name.trim() || busy}
                >
                  <Plus size={16} /> Create source
                </Button>
              </div>
            </div>
            <Field label="Note title">
              <TextInput
                value={noteTitle}
                onChange={(event) => setNoteTitle(event.target.value)}
                placeholder="e.g. Bulk discount rule"
              />
            </Field>
            <Field label="Content">
              <Textarea
                value={noteBody}
                onChange={(event) => setNoteBody(event.target.value)}
                placeholder="Paste the exact wording the employee should use…"
              />
            </Field>
            <div>
              <Button
                onClick={addNote}
                disabled={
                  !targetSource || !noteTitle.trim() || !noteBody.trim() || busy
                }
              >
                <Plus size={16} /> {busy ? "Ingesting…" : "Add and ingest"}
              </Button>
            </div>
          </Card>
        </section>
      </div>

      <div className="mt-10">
        <SectionHeading
          title="Sources"
          subtitle="Real backend state — status per document below."
        />
        {sources.loading || documents.loading ? (
          <LoadingState label="knowledge" />
        ) : sources.error || documents.error || !sources.data || !documents.data ? (
          <ErrorState
            message={sources.error ?? documents.error ?? "Could not load knowledge."}
            onRetry={refreshAll}
          />
        ) : sources.data.length === 0 ? (
          <p className="rounded-xl border border-dashed border-line-300 bg-white px-5 py-8 text-center text-sm text-ink-500">
            No knowledge sources in this tenant yet. Upload a file or add a note
            above.
          </p>
        ) : (
          <Card>
            <ul className="divide-y divide-line-200">
              {sources.data.map((source) => {
                const docs = docsBySource.get(source.id) ?? [];
                const open = expanded.includes(source.id);
                const attached = (employees.data ?? []).filter((agent) =>
                  agent.knowledge_sources.includes(source.id),
                );
                return (
                  <li key={source.id}>
                    <div className="flex w-full items-center gap-4 px-5 py-4">
                      <button
                        type="button"
                        onClick={() => toggleExpanded(source.id)}
                        aria-expanded={open}
                        className="flex min-w-0 flex-1 cursor-pointer items-center gap-4 text-left"
                      >
                        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-cream-100 text-ink-600">
                          <FileText size={17} />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-ink-900">
                            {source.name}
                          </span>
                          <span className="block text-xs text-ink-500">
                            {docs.length} document{docs.length === 1 ? "" : "s"} ·{" "}
                            {source.source_type} · updated{" "}
                            {formatDateTime(source.updated_at)}
                          </span>
                          <span className="mt-0.5 block text-xs text-ink-500">
                            Attached to:{" "}
                            {attached.length > 0
                              ? attached.map((agent) => agent.name).join(", ")
                              : "no employees"}
                          </span>
                        </span>
                        <ChevronDown
                          size={16}
                          className={clsx(
                            "shrink-0 text-ink-500 transition-transform",
                            open && "rotate-180",
                          )}
                        />
                      </button>
                      <Button
                        size="sm"
                        variant="destructive"
                        className="shrink-0"
                        disabled={busy || deleting}
                        onClick={() =>
                          setConfirm({
                            kind: "source",
                            id: source.id,
                            name: source.name,
                          })
                        }
                        aria-label={`Delete source ${source.name}`}
                      >
                        <Trash2 size={14} />
                      </Button>
                    </div>
                    {open ? (
                      <ul className="border-t border-line-200 bg-cream-50/60">
                        {docs.length === 0 ? (
                          <li className="px-5 py-3 text-xs text-ink-500">
                            No documents in this source yet.
                          </li>
                        ) : (
                          docs.map((document) => (
                            <li
                              key={document.id}
                              className="flex items-start justify-between gap-3 px-5 py-3"
                            >
                              <span className="min-w-0">
                                <span className="flex items-center justify-between gap-2">
                                  <span className="truncate text-sm font-medium text-ink-800">
                                    {document.title}
                                  </span>
                                  <StatusBadge status={document.status} />
                                </span>
                                <span className="mt-0.5 block text-xs text-ink-500">
                                  {document.chunks} chunk
                                  {document.chunks === 1 ? "" : "s"}
                                  {document.file_name ? ` · ${document.file_name}` : ""}
                                  {document.source_url ? ` · ${document.source_url}` : ""}
                                </span>
                                {document.error ? (
                                  <span className="mt-0.5 block text-xs text-red-700">
                                    {document.error}
                                  </span>
                                ) : null}
                              </span>
                              <span className="flex shrink-0 items-center gap-2">
                                {document.status === "failed" ? (
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    disabled={busy}
                                    onClick={() => void retryDocument(document)}
                                  >
                                    <RotateCw size={14} /> Retry
                                  </Button>
                                ) : null}
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  disabled={busy || deleting}
                                  onClick={() =>
                                    setConfirm({
                                      kind: "document",
                                      id: document.id,
                                      name: document.title,
                                    })
                                  }
                                  aria-label={`Delete document ${document.title}`}
                                >
                                  <Trash2 size={14} />
                                </Button>
                              </span>
                            </li>
                          ))
                        )}
                      </ul>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
      </div>

      <div className="mt-10 grid gap-8 lg:grid-cols-2">
        <section>
          <SectionHeading
            title="Attach to employee"
            subtitle="Persists on the real agent record."
          />
          <Card className="space-y-4 p-5">
            <Field label="AI employee">
              <Select
                value={attachEmployee}
                onChange={(event) => setAttachEmployee(event.target.value)}
              >
                <option value="">Select an employee…</option>
                {(employees.data ?? []).map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Knowledge source">
              <Select
                value={attachSource}
                onChange={(event) => setAttachSource(event.target.value)}
              >
                <option value="">Select a source…</option>
                {(sources.data ?? []).map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.name}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                disabled={!attachEmployee || !attachSource || busy}
                onClick={() => void attachSelected(true)}
              >
                <Link2 size={15} /> Attach
              </Button>
              <Button
                variant="ghost"
                disabled={!attachEmployee || !attachSource || busy}
                onClick={() => void attachSelected(false)}
              >
                Detach
              </Button>
            </div>
            <p className="text-xs text-ink-500">
              Associated sources on the selected employee:{" "}
              {(employees.data ?? [])
                .find((item) => item.id === attachEmployee)
                ?.knowledge_sources.map((id) => sourceById.get(id)?.name ?? id)
                .join(", ") || "—"}
            </p>
          </Card>
        </section>

        <section>
          <SectionHeading
            title="Test retrieval"
            subtitle="Real search — no LLM involved."
          />
          <Card className="space-y-4 p-5">
            <Field label="AI employee (uses their attached sources)">
              <Select
                value={testAgent}
                onChange={(event) => setTestAgent(event.target.value)}
              >
                <option value="">Select an employee…</option>
                {(employees.data ?? []).map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Question">
              <Textarea
                value={testQuery}
                onChange={(event) => setTestQuery(event.target.value)}
                placeholder="Ask a question the uploaded knowledge should answer…"
              />
            </Field>
            <div>
              <Button
                onClick={runRetrievalTest}
                disabled={!testAgent || !testQuery.trim() || testing}
              >
                <Beaker size={16} /> {testing ? "Searching…" : "Run retrieval test"}
              </Button>
            </div>
            {testResults !== null ? (
              testResults.length === 0 ? (
                <p className="rounded-lg border border-dashed border-line-300 px-4 py-3 text-sm text-ink-500">
                  No chunks retrieved — the employee may have no attached
                  sources, or nothing matched.
                </p>
              ) : (
                <ul className="space-y-2">
                  {testResults.map((chunk) => {
                    const doc = documentById.get(chunk.document_id);
                    const src = doc ? sourceById.get(doc.source_id) : undefined;
                    return (
                      <li
                        key={chunk.chunk_id}
                        className="rounded-lg border border-line-200 px-4 py-3"
                      >
                        <p className="flex items-center justify-between gap-2 text-xs text-ink-500">
                          <span className="truncate">
                            {doc?.title ?? "Unknown document"}
                            {src ? ` · ${src.name}` : ""}
                          </span>
                          <span className="shrink-0">
                            score {chunk.score.toFixed(3)}
                          </span>
                        </p>
                        <p className="mt-1 text-sm text-ink-800">{chunk.content}</p>
                      </li>
                    );
                  })}
                </ul>
              )
            ) : null}
          </Card>
        </section>
      </div>

      <p className="mt-6 rounded-xl border border-dashed border-line-300 px-5 py-4 text-center text-xs text-ink-500">
        Coming later: multi-page website crawling and voice-file transcription.
      </p>

      <ConfirmDialog
        open={confirm !== null}
        busy={deleting}
        title={
          confirm?.kind === "source"
            ? "Delete knowledge source?"
            : "Delete document?"
        }
        message={
          confirm?.kind === "source"
            ? `“${confirm?.name}” and all of its documents and indexed chunks will be permanently removed. Attached employees keep their configuration.`
            : `“${confirm?.name}” and its indexed chunks will be permanently removed.`
        }
        onConfirm={() => void confirmDelete()}
        onCancel={() => setConfirm(null)}
      />
    </AppShell>
  );
}
