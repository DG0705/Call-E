"use client";

import { useState } from "react";
import {
  Beaker,
  ChevronDown,
  FileText,
  Globe,
  Link2,
  Plus,
  UploadCloud,
} from "lucide-react";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState } from "@/components/data-states";
import {
  Badge,
  Button,
  Card,
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
  type UploadFileResult,
} from "@/lib/api/resources";
import { formatDateTime } from "@/lib/format";
import { getTenantId } from "@/lib/tenant";
import { useResource } from "@/lib/use-resource";
import { clsx } from "clsx";

const ACCEPTED_TYPES =
  ".pdf,.docx,.xlsx,.csv,.txt,.md,.markdown,.html,.htm,.json";

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "ready"
      ? "completed"
      : status === "failed"
        ? "failed"
        : "in-progress";
  return <Badge status={tone} label={status.toUpperCase()} />;
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
  const [uploadResults, setUploadResults] = useState<UploadFileResult[]>([]);
  const [expanded, setExpanded] = useState<string[]>([]);

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
  const [testQuery, setTestQuery] = useState("What is the price of DEW 28?");
  const [testResults, setTestResults] = useState<RetrievedChunk[] | null>(null);
  const [testing, setTesting] = useState(false);

  // Attach/detach
  const [attachEmployee, setAttachEmployee] = useState("");
  const [attachSource, setAttachSource] = useState("");

  function refreshAll() {
    sources.reload();
    documents.reload();
    employees.reload();
  }

  async function uploadFiles(files: FileList | null) {
    if (!files || files.length === 0 || busy) return;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      const result = await knowledgeApi.uploadFiles(
        tenantId,
        Array.from(files),
      );
      setUploadResults(result.files);
      const failed = result.files.filter((file) => file.error);
      setNotice(
        failed.length === 0
          ? `${result.files.length} file${result.files.length === 1 ? "" : "s"} ingested.`
          : `${result.files.length - failed.length} ingested, ${failed.length} failed — see per-file results.`,
      );
      refreshAll();
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setBusy(false);
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
      setFailure(error instanceof Error ? error.message : "Could not create the source.");
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
      setNotice(`Note ingested into ${result.chunks} chunk${result.chunks === 1 ? "" : "s"}.`);
      refreshAll();
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "Could not add the note.");
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
      setFailure(error instanceof Error ? error.message : "Could not ingest the URL.");
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
      setFailure(error instanceof Error ? error.message : "Retrieval test failed.");
    } finally {
      setTesting(false);
    }
  }

  async function attachSelected(attach: boolean) {
    const agent = (employees.data ?? []).find((item) => item.id === attachEmployee);
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
      setFailure(
        error instanceof Error ? error.message : "Association update failed.",
      );
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

  return (
    <AppShell>
      <PageHeader
        title="Knowledge"
        subtitle={`Upload files, add a website page or write notes — everything lands in tenant ${tenantId} and becomes retrievable.`}
      />

      {notice ? (
        <p className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800" role="status">
          {notice}
        </p>
      ) : null}
      {failure ? (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800" role="alert">
          {failure}
        </p>
      ) : null}

      <div className="grid gap-8 lg:grid-cols-3">
        <section>
          <SectionHeading title="Upload files" subtitle="PDF, DOCX, XLSX, CSV, TXT, MD, HTML, JSON." />
          <label className="block cursor-pointer rounded-xl border border-dashed border-line-300 bg-white p-6 text-center transition-colors hover:border-brand-400 hover:bg-brand-50/40">
            <UploadCloud size={22} className="mx-auto text-ink-500" />
            <span className="mt-2 block text-sm font-medium text-ink-900">
              {busy ? "Working…" : "Choose files"}
            </span>
            <span className="mt-0.5 block text-xs text-ink-500">
              Multiple files at once · 10 MB each
            </span>
            <input
              type="file"
              multiple
              accept={ACCEPTED_TYPES}
              className="sr-only"
              disabled={busy}
              onChange={(event) => {
                void uploadFiles(event.target.files);
                event.target.value = "";
              }}
            />
          </label>
          {uploadResults.length > 0 ? (
            <ul className="mt-3 space-y-2">
              {uploadResults.map((file) => (
                <li
                  key={`${file.file_name}-${file.document_id ?? "failed"}`}
                  className="rounded-lg border border-line-200 bg-white px-4 py-2.5 text-sm"
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium text-ink-900">{file.file_name}</span>
                    <StatusBadge status={file.status} />
                  </span>
                  <span className="mt-0.5 block text-xs text-ink-500">
                    {file.error ?? `${file.chunks} chunk${file.chunks === 1 ? "" : "s"} indexed`}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <section>
          <SectionHeading title="Add website page" subtitle="One URL → one document. No crawler yet." />
          <Card className="space-y-4 p-5">
            <Field label="Page URL" hint="Public http(s) pages only. Private hosts are refused.">
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
          <SectionHeading title="Add a note" subtitle="Typed text, ingested immediately." />
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
                <Button variant="secondary" onClick={createSource} disabled={!name.trim() || busy}>
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
                disabled={!targetSource || !noteTitle.trim() || !noteBody.trim() || busy}
              >
                <Plus size={16} /> {busy ? "Ingesting…" : "Add and ingest"}
              </Button>
            </div>
          </Card>
        </section>
      </div>

      <div className="mt-10">
        <SectionHeading title="Sources" subtitle="Real backend state — status per document below." />
        {sources.loading || documents.loading ? (
          <LoadingState label="knowledge" />
        ) : sources.error || documents.error || !sources.data || !documents.data ? (
          <ErrorState
            message={sources.error ?? documents.error ?? "Could not load knowledge."}
            onRetry={refreshAll}
          />
        ) : sources.data.length === 0 ? (
          <p className="rounded-xl border border-dashed border-line-300 bg-white px-5 py-8 text-center text-sm text-ink-500">
            No knowledge sources in this tenant yet. Upload a file or add a note above.
          </p>
        ) : (
          <Card>
            <ul className="divide-y divide-line-200">
              {sources.data.map((source) => {
                const docs = docsBySource.get(source.id) ?? [];
                const open = expanded.includes(source.id);
                return (
                  <li key={source.id}>
                    <button
                      type="button"
                      onClick={() => toggleExpanded(source.id)}
                      aria-expanded={open}
                      className="flex w-full cursor-pointer items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-cream-50"
                    >
                      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-cream-100 text-ink-600">
                        <FileText size={17} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink-900">
                          {source.name}
                        </span>
                        <span className="block text-xs text-ink-500">
                          {docs.length} document{docs.length === 1 ? "" : "s"} · updated{" "}
                          {formatDateTime(source.updated_at)}
                        </span>
                        <span className="mt-0.5 block text-xs text-ink-500">
                          Used by:{" "}
                          {(employees.data ?? [])
                            .filter((agent) => agent.knowledge_sources.includes(source.id))
                            .map((agent) => agent.name)
                            .join(", ") || "no employees"}
                        </span>
                      </span>
                      <ChevronDown
                        size={16}
                        className={clsx("text-ink-500 transition-transform", open && "rotate-180")}
                      />
                    </button>
                    {open ? (
                      <ul className="border-t border-line-200 bg-cream-50/60">
                        {docs.length === 0 ? (
                          <li className="px-5 py-3 text-xs text-ink-500">
                            No documents in this source yet.
                          </li>
                        ) : (
                          docs.map((document) => (
                            <li key={document.id} className="px-5 py-3">
                              <span className="flex items-center justify-between gap-2">
                                <span className="truncate text-sm font-medium text-ink-800">
                                  {document.title}
                                </span>
                                <StatusBadge status={document.status} />
                              </span>
                              <span className="mt-0.5 block text-xs text-ink-500">
                                {document.chunks} chunk{document.chunks === 1 ? "" : "s"}
                                {document.file_name ? ` · ${document.file_name}` : ""}
                                {document.source_url ? ` · ${document.source_url}` : ""}
                                {document.error ? ` · ${document.error}` : ""}
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
          <SectionHeading title="Attach to employee" subtitle="Persists on the real agent record." />
          <Card className="space-y-4 p-5">
            <Field label="AI employee">
              <Select value={attachEmployee} onChange={(event) => setAttachEmployee(event.target.value)}>
                <option value="">Select an employee…</option>
                {(employees.data ?? []).map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Knowledge source">
              <Select value={attachSource} onChange={(event) => setAttachSource(event.target.value)}>
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
              {(employees.data ?? []).find((item) => item.id === attachEmployee)?.knowledge_sources.join(", ") || "—"}
            </p>
          </Card>
        </section>

        <section>
          <SectionHeading title="Test retrieval" subtitle="Real search — no LLM involved." />
          <Card className="space-y-4 p-5">
            <Field label="AI employee (uses their attached sources)">
              <Select value={testAgent} onChange={(event) => setTestAgent(event.target.value)}>
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
              />
            </Field>
            <div>
              <Button onClick={runRetrievalTest} disabled={!testAgent || !testQuery.trim() || testing}>
                <Beaker size={16} /> {testing ? "Searching…" : "Run retrieval test"}
              </Button>
            </div>
            {testResults !== null ? (
              testResults.length === 0 ? (
                <p className="rounded-lg border border-dashed border-line-300 px-4 py-3 text-sm text-ink-500">
                  No chunks retrieved — the employee may have no attached sources, or nothing matched.
                </p>
              ) : (
                <ul className="space-y-2">
                  {testResults.map((chunk) => (
                    <li key={chunk.chunk_id} className="rounded-lg border border-line-200 px-4 py-3">
                      <p className="flex items-center justify-between gap-2 text-xs text-ink-500">
                        <span className="truncate font-mono">{chunk.chunk_id}</span>
                        <span>score {chunk.score.toFixed(3)}</span>
                      </p>
                      <p className="mt-1 text-sm text-ink-800">{chunk.content}</p>
                      <p className="mt-1 text-xs text-ink-500">document {chunk.document_id}</p>
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </Card>
        </section>
      </div>

      <p className="mt-6 rounded-xl border border-dashed border-line-300 px-5 py-4 text-center text-xs text-ink-500">
        Coming later: multi-page website crawling, re-ingestion controls, and voice-file transcription.
      </p>
    </AppShell>
  );
}
