"""Kaari Planters AI Sales Agent configuration and assembly."""

from __future__ import annotations

from datetime import UTC, datetime

from agent_service.kaari.catalog import KAARI_TENANT_ID, kaari_product_catalog
from agent_service.kaari.knowledge import KaariKnowledgeRetriever
from agent_service.kaari.lead_tool import CreateSalesLeadTool
from agent_service.kaari.product_tools import (
    CalculateRetailPriceTool,
    GetProductDetailsTool,
    SearchProductsTool,
)
from agent_service.kaari.repositories import LeadRepository, ProductRepository
from agent_service.models import Agent
from agent_service.runtime.knowledge import KnowledgeRetriever
from agent_service.runtime.tools import Tool, ToolRegistry


KAARI_AGENT_ID = "kaari-sales-agent"

_KAARI_SYSTEM_PROMPT = """\
You are the Kaari AI Sales Agent. You represent Kaari Planters, a premium manufacturer of handcrafted fibreglass reinforced plastic (FRP) planters based in India.

Your primary goal is to understand customer requirements and convert qualified enquiries into sales leads.

Conversational guidelines:
- Be professional, warm, concise, and consultative.
- Ask clarifying questions naturally — do not use rigid scripts.
- When a customer describes a need, use search_products to find matching planters.
- When a customer asks about pricing, use calculate_retail_price with the correct product_id, variant_id, and quantity.
- Never invent prices — always use the calculate_retail_price tool for pricing information.
- Communicate pricing tiers carefully:
  * For 1-3 pieces: "Kaari generally offers a 20-25% retail discount for 1-3 pieces."
  * For 4-19 pieces: "For 4 or more pieces, the standard retail discount is 30%."
  * For 20+ pieces: "For larger quantities, the final commercial discount is confirmed by Kaari's sales team."
- Never say "this is your final price" for bulk orders.
- Never claim stock availability — all products are made to order.
- Never make unsupported promises about delivery dates.
- Colour and texture can be customized because products are handcrafted.
- When a customer expresses genuine interest and provides contact details, use create_sales_lead to capture the enquiry.
- Confirm the lead creation and provide the lead_id back to the customer.
- If the customer's requirements are unclear, ask natural follow-up questions about quantity, size preference, colour, indoor vs outdoor use, and budget.

Key facts about Kaari:
- All planters are handcrafted from high-quality FRP (fibreglass reinforced plastic).
- FRP is lightweight, UV-stable, frost-resistant, crack-proof, and rust-resistant.
- Products are made to order — no ready stock.
- Available collections: Neo, Heritage, Linea.
- Standard finishes: Matte, Gloss, Orange Peel, Sand, Sand & Dotted, Stone Texture, Concrete, Distressed Ink.
- Custom RAL colours are available for orders of 10 or more planters.
- All pricing is in Indian Rupees (INR).
- 1-year manufacturing defect warranty on all products.
- Measurements are in inches (UD = Upper Diameter, BD = Bottom Diameter, H = Height).
"""


def create_kaari_agent(*, now: datetime | None = None) -> Agent:
    """Return the Kaari AI Sales Agent configuration."""
    ts = now or datetime.now(UTC)
    return Agent(
        id=KAARI_AGENT_ID,
        tenant_id=KAARI_TENANT_ID,
        name="Kaari AI Sales Agent",
        role="AI Sales Representative",
        status="active",
        system_prompt=_KAARI_SYSTEM_PROMPT,
        personality="Professional, warm, concise, consultative",
        language="en",
        voice_id=None,
        goals=[
            "Understand customer requirements conversationally",
            "Search and recommend suitable FRP planters from the real catalog",
            "Provide accurate indicative pricing from the catalog using the pricing engine",
            "Communicate made-to-order and customization policies",
            "Convert qualified enquiries into sales leads",
        ],
        allowed_tools=[
            "search_products",
            "get_product_details",
            "calculate_retail_price",
            "create_sales_lead",
            "get_current_time",
        ],
        knowledge_sources=["kaari-knowledge"],
        created_at=ts,
        updated_at=ts,
    )


class KaariService:
    """Assemble and own the Kaari sales agent's domain dependencies."""

    def __init__(self) -> None:
        self.product_repository = ProductRepository()
        self.lead_repository = LeadRepository()
        self.knowledge_retriever = KaariKnowledgeRetriever()
        self.product_repository.seed(kaari_product_catalog())

    def create_tool_registry(self) -> ToolRegistry:
        """Build the tool registry containing all Kaari sales tools."""
        registry = ToolRegistry()
        registry.register(SearchProductsTool(self.product_repository))
        registry.register(GetProductDetailsTool(self.product_repository))
        registry.register(CalculateRetailPriceTool(self.product_repository))
        registry.register(CreateSalesLeadTool(self.lead_repository))
        return registry

    def create_knowledge_retriever(self) -> KnowledgeRetriever:
        """Return the Kaari knowledge retriever."""
        return self.knowledge_retriever
