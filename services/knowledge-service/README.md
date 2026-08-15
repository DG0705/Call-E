# knowledge-service

The knowledge service hosts the knowledge and retrieval foundation for Call-E.
It owns tenant-scoped knowledge sources and documents, deterministic ingestion
(normalize → chunk → embed → store), and a provider-neutral retriever that
scopes retrieval to one tenant and one agent.

## Domain model

- `KnowledgeSource`: a tenant-scoped grouping of knowledge documents.
- `KnowledgeDocument`: one tenant-scoped document inside a source. It keeps the
  raw content and a `source_type` (`text`, `markdown`, `html`, or `pdf`).
- `KnowledgeChunk`: a normalized, indexable slice of a document with a
  deterministic id `{document_id}:{index}`.

All three collections are tenant-isolated: every read is filtered by
`tenant_id`, and every write validates the owning tenant.

## Ingestion flow

```text
Document
 ↓
Normalize (strip HTML, collapse whitespace)
 ↓
Chunk (deterministic overlapping windows)
 ↓
Embed (provider-neutral EmbeddingProvider)
 ↓
Store (VectorRepository, one row per chunk)
```

- `normalize_text` strips HTML tags and entities when the source type is
  `html`, then collapses whitespace for every source type.
- `chunk_text` is deterministic: the same document produces the same chunks.
  Defaults are `chunk_size=1000` characters with `chunk_overlap=200`. Repeating
  chunks are broken at word boundaries when possible.
- Chunk ids are deterministic (`{document_id}:{index}`), so re-ingesting a
  document replaces its chunks. Stale chunks are removed before storage.
- Embeddings go through the `EmbeddingProvider` protocol. The default
  `MockEmbeddingProvider` is deterministic and needs no external service; a
  production provider can be injected without changing the pipeline.

## Storage

Embedded chunks are persisted through the `VectorRepository` protocol. The
default `CollectionVectorRepository` stores chunks in the
`knowledge_chunks` collection and computes cosine similarity in-process, so no
separate vector database is required yet. The storage layer is a replaceable
abstraction for a real vector database later.

## Retrieval flow

```text
Query
 ↓
Resolve agent sources (AgentKnowledgeResolver)
 ↓
Resolve documents inside those sources (tenant-scoped)
 ↓
Embed the query
 ↓
Cosine search over the tenant + document boundary
 ↓
RetrievedChunk list
```

- Retrieval returns nothing when the agent has no allowed sources or when none
  of those sources contain documents. It never falls back to whole-tenant
  search.
- The `AgentKnowledgeResolver` protocol decides which sources an agent may use.
  The default `MappingAgentKnowledgeResolver` is an explicit agent-to-source
  mapping; production deployments can inject a resolver backed by agent
  configuration.
- `build_knowledge_context` formats retrieved chunks into a stable grounding
  block consumed by the Agent Runtime in `agent-service`.

## Endpoints

- `POST /api/v1/knowledge/sources` — create a tenant-scoped source.
- `GET /api/v1/knowledge/sources?tenant_id={tenant_id}` — list tenant sources.
- `POST /api/v1/knowledge/documents` — create a document inside a source.
- `GET /api/v1/knowledge/documents?tenant_id={tenant_id}` — list tenant documents.
- `POST /api/v1/knowledge/documents/{document_id}/ingest` — normalize, chunk,
  embed, and store a document.
- `POST /api/v1/knowledge/search` — retrieve chunks for a tenant + agent.

Search example:

```bash
curl -X POST 'http://localhost/api/v1/knowledge/search' \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"tenant-1","agent_id":"agent-1","query":"refund policy","top_k":3}'
```

The default application wiring uses an in-memory database so development and
tests need no MongoDB. Production wiring (`main.py`) connects to MongoDB and
creates the tenant-scoped indexes at startup:

- `knowledge_sources` on `tenant_id`
- `knowledge_documents` on `tenant_id` + `source_id`
- `knowledge_chunks` on `tenant_id` + `document_id`

## Runtime integration

The Agent Runtime in `agent-service` consumes the `KnowledgeRetriever` protocol.
When an agent has `knowledge_sources` configured, the runtime retrieves the
top-k chunks for the user message and appends the resulting knowledge block to
the per-turn system instruction. The retrieved knowledge is transient: it never
becomes part of the persisted conversation history.

Telephony, STT/TTS, PDF extraction, web crawling, and external embedding or
vector services deliberately come later. This service does not implement those
integrations yet.
