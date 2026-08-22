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
python -m pytest -q  # 224 tests (56 Kaari-specific)
```

## Phone Deployment Requirements

To move from test endpoint to live phone calls:

1. **Asterisk server** with SIP trunk provisioned (Twilio SIP, BICS, etc.)
2. **ARI configuration** pointing to this agent-service
3. **STT provider** configured (Deepgram or Whisper API key)
4. **TTS provider** configured (ElevenLabs or similar API key)
5. **Real phone number** purchased and routed through Asterisk
6. **MongoDB** for persistent lead storage (replace in-memory repos)
7. **Environment variables** set: `STT_API_KEY`, `TTS_API_KEY`, `MONGODB_URI`

## Scope Limitations (MVP)

- No WhatsApp, email, or CRM integration
- No payment or quotation generation
- No outbound campaigns or follow-ups
- No human escalation or agent handoff
- No analytics dashboard
- No multi-agent orchestration
- Lead storage is in-memory — will be lost on restart
