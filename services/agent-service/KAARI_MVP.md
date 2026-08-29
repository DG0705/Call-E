# Kaari Planters — AI Sales Agent MVP

## Business Problem

Kaari Planters sells handcrafted FRP (Fibreglass Reinforced Plastic) planters to homeowners, landscapers,
and commercial buyers across India. Sales staff handle repetitive inbound calls — product enquiries, pricing,
sizing, drainage questions, and lead capture. The MVP automates this with an AI phone agent that can answer
product questions, search the catalog, quote accurate prices, and create sales leads — all without a
human operator.

## Agent Responsibilities

The Kaari sales agent handles:

- **Product discovery**: Search catalog by query, collection, colour, finish, texture, or height range
- **Product details**: Return name, dimensions, variants, prices, colours, finish, texture
- **Pricing**: Authoritative INR pricing via the pricing engine — the agent never invents prices
- **Pricing policy communication**: Correctly communicate discount tiers (20-25% for 1-3, 30% for 4-19, bulk quote for 20+)
- **Made-to-order communication**: All products are made to order; never claim stock
- **Knowledge Q&A**: Material durability, drainage, customisation, sizing guidance, FAQs
- **Lead capture**: Collect name, phone, email, company, location, requirements, preferred colours/finish/texture, budget, and quantity

## Pricing Policy

| Quantity | Discount | Notes |
|----------|----------|-------|
| 1-3 pieces | 20-25% off retail | Indicative range; exact % depends on product/order |
| 4-19 pieces | 30% off retail | Exact, standard discount |
| 20+ pieces | Bulk quote required | Commercial discount confirmed by Kaari's sales team |

The `calculate_retail_price` tool enforces this policy. For 20+ pieces the tool returns `bulk_quote_required: true`
and the agent must communicate that the final price requires Kaari sales team confirmation.

## Knowledge Sources

All knowledge is keyword-retrieved in-memory (no vector DB required for MVP).

| Source | Content |
|--------|---------|
| `kaari/catalog_seed.json` | 55+ real product models (Neo, Heritage, Linea collections) with all variants, prices, dimensions |
| `kaari/knowledge.py` | 13 knowledge chunks covering company info, materials, collections, measurements, colours/finishes, made-to-order policy, pricing policy, customisation, use cases, warranty |

Knowledge is injected into the agent's system prompt at conversation start via `KaariService.knowledge_retriever`.

## Tools

| Tool | Purpose |
|------|---------|
| `search_products` | Search across model name, collection, colours, finish, texture, description; filter by collection, colour, finish, texture, height range |
| `get_product_details` | Return complete product info including all variants by `product_id` |
| `calculate_retail_price` | Calculate indicative pricing for 1-19 pieces; flag bulk_quote_required for 20+ |
| `create_sales_lead` | Validate and persist a lead with contact + requirement + preferred attributes + budget |

All tools are registered in a per-tenant `ToolRegistry` and executed via the existing `ToolEngine`.

## Conversation Flow

```
Caller dials number → Asterisk receives call → ARI bridge created
  → Voice Engine streams STT (Whisper/Deepgram) → Agent Runtime
  → LLM generates response (tools available) → TTS streamed back via Voice Engine
  → On lead creation or call end → SalesLead persisted → Call logged
```

Multi-turn: conversation history is maintained across turns via `conversation_id`.

## Architecture

```
agent-service/
├── kaari/
│   ├── __init__.py            # Public API
│   ├── models.py              # ProductVariant, Product, SalesLead, CatalogImportWarning/Summary
│   ├── repositories.py        # ProductRepository (search by collection/colour/finish/height), LeadRepository
│   ├── catalog.py             # Loads real catalog from catalog_seed.json
│   ├── catalog_seed.json      # 55+ real products with all variants (generated from PDF)
│   ├── parser.py              # PDF parser for programmatic catalog extraction
│   ├── pricing.py             # Decimal-safe pricing engine (3 tiers, bulk quote escalation)
│   ├── knowledge.py           # KaariKnowledgeRetriever + 13 chunks
│   ├── product_tools.py       # SearchProductsTool v2, GetProductDetailsTool v2, CalculateRetailPriceTool
│   ├── lead_tool.py           # CreateSalesLeadTool v2 (extended fields)
│   └── service.py             # KaariService + create_kaari_agent()
├── routes/kaari.py            # POST /api/v1/kaari/sales/test
├── scripts/
│   └── generate_catalog.py    # Generates catalog_seed.json from extracted PDF data
└── app.py                     # Wires KaariService + kaari router
```

## Local Testing

### Test endpoint

```bash
curl -X POST http://localhost:8000/api/v1/kaari/sales/test \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "kaari-planters",
    "agent_id": "kaari-sales-agent",
    "conversation_id": "conv-test-1",
    "message": "What FRP planters do you have?"
  }'
```

### Running tests

```bash
python -m pytest -q  # 277 tests (109 Kaari-specific)
```

## Kaari MVP Demo

A complete sales conversation can be reproduced locally using the development endpoint.

### Step 1 — Start the agent service

```bash
cd services/agent-service
uvicorn agent_service.app:create_agent_app --factory --reload
```

### Step 2 — Customer: "I need planters for my office"

```bash
curl -s -X POST http://localhost:8000/api/v1/kaari/sales/test \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "kaari-planters",
    "agent_id": "kaari-sales-agent",
    "conversation_id": "conv-demo-1",
    "message": "I need planters for my office."
  }' | python -m json.tool
```

Agent searches the catalog and asks clarifying questions (quantity, size, style).

### Step 3 — Customer: "About 10, around 2 feet high, modern style"

```bash
curl -s -X POST http://localhost:8000/api/v1/kaari/sales/test \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "kaari-planters",
    "agent_id": "kaari-sales-agent",
    "conversation_id": "conv-demo-1",
    "message": "About 10, around 2 feet high, modern style"
  }' | python -m json.tool
```

Agent searches catalog with height range 20-28 inches, returns matching products.

### Step 4 — Customer: "I like the DEW. What is the price for 10?"

```bash
curl -s -X POST http://localhost:8000/api/v1/kaari/sales/test \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "kaari-planters",
    "agent_id": "kaari-sales-agent",
    "conversation_id": "conv-demo-1",
    "message": "I like the DEW. What is the price for 10?"
  }' | python -m json.tool
```

Agent calls `calculate_retail_price(product_id="KP-DEW", variant_id="DEW-40", quantity=10)`.
Response includes pricing result: 30% discount, Rs 10,220/unit, subtotal Rs 1,02,200.

### Step 5 — Customer: "I want to proceed. My name is Priya, phone +919876543210"

```bash
curl -s -X POST http://localhost:8000/api/v1/kaari/sales/test \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "kaari-planters",
    "agent_id": "kaari-sales-agent",
    "conversation_id": "conv-demo-1",
    "message": "I want to proceed. My name is Priya Sharma, phone +919876543210, email priya@example.com, company Green Spaces Ltd, Mumbai"
  }' | python -m json.tool
```

Agent calls `create_sales_lead(...)` and confirms lead creation with a lead ID.

### Demo response structure

Every response includes:

| Field | Description |
|-------|-------------|
| `conversation_id` | Persistent across turns |
| `response` | Agent's natural language reply |
| `tool_calls` | List of tools invoked (name, arguments, success) |
| `tool_results` | Tool output for each call |
| `products_matched` | Model names from search results |
| `pricing` | Pricing result if calculate_retail_price was called |
| `lead_id` | Lead ID if create_sales_lead was called |
| `request_id` | Propagated request ID for tracing |

### Pricing tier reference

| Quantity | Discount | Output |
|----------|----------|--------|
| 1-3 | 20-25% (range) | "Kaari generally offers a 20-25% retail discount" |
| 4-19 | 30% (exact) | "The standard retail discount is 30%" |
| 20+ | Bulk quote | "Final commercial discount confirmed by Kaari's sales team" |

### Business rules enforced by the agent

- Products are made to order — never claims stock availability
- Colour and texture can be customised (handcrafted FRP)
- 20+ quantity requires human commercial confirmation
- No unsupported delivery date promises
- All prices are authoritative from the pricing engine

## Phone Deployment Requirements

To move from test endpoint to live phone calls, the following is required:

1. **Asterisk server** with PJSIP configured and a SIP trunk provisioned (Twilio SIP, BICS, etc.)
2. **Environment variables** (all required):
   - `TELEPHONY_PROVIDER=asterisk`
   - `ASTERISK_URL=http://<asterisk-host>:8088` (ARI HTTP interface)
   - `ASTERISK_USERNAME=<ari-username>`
   - `ASTERISK_PASSWORD=<ari-password>`
   - `STT_API_KEY=<deepgram-or-whisper-api-key>`
   - `TTS_API_KEY=<elevenlabs-or-tts-api-key>`
   - `MONGODB_URI=mongodb://localhost:27017` (for persistent leads)
   - `LLM_PROVIDER=openai` and `OPENAI_API_KEY=<key>` (for real LLM responses)
3. **Phone number** purchased and routed through the SIP trunk to Asterisk
4. **Dialplan** configured to accept inbound calls and route to the agent

The Kaari agent configuration (`tenant_id="kaari-planters"`, `agent_id="kaari-sales-agent"`) is
already wired through `create_kaari_agent()` and `KaariService`. When a call arrives via
Asterisk, the `TelephonyService` creates a voice session, and the same Kaari tools (search,
pricing, lead creation) are available through the agent runtime.

## Scope Limitations (MVP)

- No WhatsApp, email, or CRM integration
- No payment or quotation generation
- No outbound campaigns or follow-ups
- No human escalation or agent handoff
- No analytics dashboard
- No multi-agent orchestration
- Lead storage is in-memory — will be lost on restart
