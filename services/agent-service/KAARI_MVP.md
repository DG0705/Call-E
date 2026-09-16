# Kaari AI Sales Agent — MVP for Real Phone Calls

This document describes the Kaari agent configuration, capabilities, and how it
integrates with the voice-service for real phone calls.

## Agent Configuration

The Kaari agent is seeded on agent-service startup (`AGENT_SERVICE_SEED=true`):

- **Tenant ID**: `kaari-planters`
- **Agent ID**: `kaari-sales-agent`
- **Role**: AI Sales Representative
- **Language**: English (`en`)
- **Voice ID**: `null` (uses TTS provider default)
- **Greeting**:
  > "Hello, thank you for calling Kaari Planters. I would be happy to help you find the right planters. What are you looking for today?"

## Capabilities

The Kaari agent is equipped with three tools for handling sales enquiries:

### 1. `search_products`
Searches the Kaari product catalog by query, collection, colour, finish, size,
or height range.

**Arguments:**
```json
{
  "query": "string (optional)",
  "collection": "string (optional: Neo|Linea|Heritage|Dew|Nova|Aqua|Arlo|Orbit|Mandala)",
  "colour": "string (optional)",
  "finish": "string (optional: Matte|Orange Peel|Stone|Gloss)",
  "height_min": "number (optional, inches)",
  "height_max": "number (optional, inches)"
}
```

**Returns:**
```json
{
  "count": 3,
  "products": [
    {
      "product_id": "KP-DEW",
      "model_name": "DEW",
      "collection": "Neo",
      "description": "Conical FRP planter.",
      "variants": [
        {
          "variant_id": "DEW-40",
          "size_label": "40",
          "height_inches": 40,
          "upper_diameter_inches": 12.5,
          "listed_price_inr": 14600,
          "finish": "Matte",
          "colours": ["Light Ivory", "Pearl Beige"]
        }
      ]
    }
  ]
}
```

### 2. `calculate_retail_price`
Calculates the retail price for a specific product variant and quantity using
the Kaari pricing policy.

**Arguments:**
```json
{
  "product_id": "KP-DEW",
  "variant_id": "DEW-40",
  "quantity": 10
}
```

**Returns:**
```json
{
  "product_id": "KP-DEW",
  "variant_id": "DEW-40",
  "quantity": 10,
  "unit_list_price": "14600",
  "discount_min": "30%",
  "discount_max": "30%",
  "unit_discounted_price": "10220.00",
  "total_discounted_price": "102200.00",
  "bulk_quote_required": false,
  "pricing_notes": "Standard retail discount applied. 4-19 units qualify for 30% discount."
}
```

### 3. `create_sales_lead`
Creates a sales lead in MongoDB when the customer wants to proceed.

**Arguments:**
```json
{
  "customer_name": "John Smith",
  "phone": "+919876543210",
  "requirements": "10 DEW-40 planters for office",
  "product_ids": ["KP-DEW"],
  "quantity": 10,
  "preferred_colours": ["Pearl Beige"]
}
```

**Returns:**
```json
{
  "lead_id": "507f1f77bcf86cd799439011",
  "status": "new",
  "bulk_order": false
}
```

## Pricing Policy (Enforced by Agent)

| Quantity | Discount | Notes |
|----------|----------|-------|
| 1–3 | 20–25% indicative retail discount | Agent communicates as a range |
| 4–19 | 30% exact standard retail discount | Agent states exact percentage |
| 20+ | Bulk quote required | Agent **never invents** a bulk price; says final commercial discount requires Kaari sales team confirmation |

## Safety Guardrails

The agent's system prompt enforces:

- **No stock claims**: "Products are made to order; we do not hold inventory."
- **No delivery promises**: "Timelines depend on production scheduling; I cannot guarantee a delivery date."
- **Customization available**: "Colour and texture customization is available per the Kaari catalog (Matte, Orange Peel, Stone, Gloss finishes; multiple colours per model)."
- **Pricing accuracy**: Uses exact catalog prices from `catalog_seed.json`; never estimates or rounds.

## Tool Registry

The Kaari agent's `allowed_tools`:
- `search_products`
- `calculate_retail_price`
- `create_sales_lead`

These are registered in `KaariService.create_tool_registry()` and only
available to agents with matching `tenant_id` and `allowed_tools`.

## Knowledge Grounding

The agent has `knowledge_sources: ["kaari-faq"]` configured. Each turn:
1. User message → `KaariKnowledgeRetriever.retrieve(tenant, agent, query, top_k=3)`
2. Retrieved chunks appended to per-turn system instruction
3. LLM uses grounded knowledge for responses

The knowledge base includes:
- Made-to-order policy
- Pricing tiers
- Warranty (10 years structural, 2 years finish)
- Customization options
- Lead process

## Integration with Voice Service

The agent is invoked via the voice-service's `AgentRuntimeClient` (HTTP boundary):
- Voice service `VoiceSessionManager` → `AgentRuntimeClient.respond()`
- Conversation context preserved across turns via `conversation_id`
- Tool execution history returned in `RuntimeResult.tool_execution_history`

## Running the Kaari Agent in a Real Call

See **voice-service/README.md → "How to run a real Kaari phone call"** for
the complete setup: environment variables, Asterisk config, SIP registration,
and the expected conversation flow.

## Mock Mode

For development without paid APIs:

```powershell
# Agent service with mock LLM
LLM_PROVIDER=mock uv run uvicorn agent_service.main:app --reload

# Run smoke test (uses all mocks)
uv run pytest services/agent-service/tests/test_kaari.py::test_kaari_mvp_smoke_test -v
```

The mock LLM provider can be programmed with `planned_tool_calls` to exercise
specific tool sequences without Groq.