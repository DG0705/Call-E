# Kaari Planters — AI Sales Agent MVP

## Business Problem

Kaari Planters sells FRP (Fiber Reinforced Polymer) planters to homeowners, landscapers, and commercial
buyers across India. Sales staff handle repetitive inbound calls — product enquiries, pricing, sizing,
drainage questions, and lead capture. The MVP automates this with an AI phone agent that can answer
product questions, search the catalog, quote accurate prices, and create sales leads — all without a
human operator.

## Agent Responsibilities

The Kaari sales agent handles:

- **Product discovery**: Search catalog by query, category, or size
- **Product details**: Return name, dimensions, weight, colours, price, description
- **Price retrieval**: Authoritative INR pricing — the agent never invents prices
- **Knowledge Q&A**: Material durability, drainage, customisation, sizing guidance, FAQs
- **Lead capture**: Collect name, phone, email, requirement, and optionally preferred product

## Knowledge Sources

All knowledge is keyword-retrieved in-memory (no vector DB required for MVP).

| Source | Content |
|--------|---------|
| `kaari/catalog.py` | 8 FRP planter products with pricing, dimensions, categories |
| `kaari/knowledge.py` | 11 knowledge chunks covering company info, materials, categories, colours, customisation, sizing, pricing policy, drainage, FAQs, use cases |

Knowledge is injected into the agent's system prompt at conversation start via `KaariService.knowledge_retriever`.

## Tools

| Tool | Purpose |
|------|---------|
| `search_products` | Full-text search across name, description, category, material, finish, colours |
| `get_product_details` | Return complete product info by `product_id` |
| `get_product_price` | Return authoritative price for a product (LLM never fabricates) |
| `create_sales_lead` | Validate and persist a lead with contact + requirement |

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
│   ├── __init__.py          # Public API
│   ├── models.py            # Product, SalesLead
│   ├── repositories.py      # ProductRepository, LeadRepository
│   ├── catalog.py           # 8 FRP planter products
│   ├── knowledge.py         # KeywordRetriever + 11 chunks
│   ├── product_tools.py     # SearchProductsTool, GetProductDetailsTool, GetProductPriceTool
│   ├── lead_tool.py         # CreateSalesLeadTool
│   └── service.py           # KaariService + create_kaari_agent()
├── routes/kaari.py          # POST /api/v1/kaari/sales/test
└── app.py                   # Wires KaariService + kaari router
```

## Local Testing

### Test endpoint

```bash
curl -X POST http://localhost:8000/api/v1/kaari/sales/test \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "kaari-sales-agent",
    "message": "What FRP planters do you have?",
    "caller_phone": "+919876543210",
    "caller_name": "Test User"
  }'
```

### Running tests

```bash
python -m pytest -q  # 209 tests (41 Kaari-specific)
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
- Product catalog is sample data (8 products) — replace with real inventory
- Lead storage is in-memory — will be lost on restart
