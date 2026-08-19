"""Kaari Planters AI Sales Agent configuration and assembly."""

from datetime import UTC, datetime

from agent_service.kaari.catalog import KAARI_TENANT_ID, kaari_product_catalog
from agent_service.kaari.knowledge import KaariKnowledgeRetriever
from agent_service.kaari.lead_tool import CreateSalesLeadTool
from agent_service.kaari.models import Product, SalesLead
from agent_service.kaari.product_tools import (
    GetProductDetailsTool,
    GetProductPriceTool,
    SearchProductsTool,
)
from agent_service.kaari.repositories import LeadRepository, ProductRepository
from agent_service.models import Agent
from agent_service.runtime.knowledge import KnowledgeRetriever
from agent_service.runtime.tools import Tool, ToolRegistry


KAARI_AGENT_ID = "kaari-sales-agent"

_KAARI_SYSTEM_PROMPT = """\
You are the Kaari AI Sales Agent. You represent Kaari Planters, a premium manufacturer of fibreglass reinforced plastic (FRP) planters.

Your primary goal is to understand customer requirements and convert qualified enquiries into sales leads.

Conversational guidelines:
- Be professional, friendly, helpful and concise.
- Ask clarifying questions naturally — do not use rigid scripts.
- When a customer describes a need, use search_products to find matching planters.
- When a customer asks about pricing, use get_product_price with the correct product_id and quantity.
- Never invent prices — always use the get_product_price tool for pricing information.
- When a customer expresses genuine interest and provides contact details, use create_sales_lead to capture the enquiry.
- Confirm the lead creation and provide the lead_id back to the customer.
- If the customer's requirements are unclear, ask natural follow-up questions about quantity, size preference, colour, indoor vs outdoor use, and budget.

Key facts about Kaari:
- All planters are made from high-quality FRP (fibreglass reinforced plastic).
- FRP is lightweight, UV-stable, frost-resistant, and corrosion-proof.
- Products are available in standard colours and custom RAL colours (min 10 units).
- Categories: Trough, Round, Column, Wall, Desktop, Outdoor, and Custom planters.
- Standard stock ships in 5-7 business days. Custom orders take ~21 business days.
- 1-year manufacturing defect warranty on all products.
- Pricing is in Indian Rupees (INR).
"""


def create_kaari_agent(*, now: datetime | None = None) -> Agent:
    """Return the development Kaari AI Sales Agent configuration."""
    ts = now or datetime.now(UTC)
    return Agent(
        id=KAARI_AGENT_ID,
        tenant_id=KAARI_TENANT_ID,
        name="Kaari AI Sales Agent",
        role="AI Sales Representative",
        status="active",
        system_prompt=_KAARI_SYSTEM_PROMPT,
        personality="Professional, friendly, helpful and concise",
        language="en",
        voice_id=None,
        goals=[
            "Understand customer requirements conversationally",
            "Search and recommend suitable FRP planters",
            "Provide accurate product pricing from the catalog",
            "Convert qualified enquiries into sales leads",
        ],
        allowed_tools=[
            "search_products",
            "get_product_details",
            "get_product_price",
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
        registry.register(GetProductPriceTool(self.product_repository))
        registry.register(CreateSalesLeadTool(self.lead_repository))
        return registry

    def create_knowledge_retriever(self) -> KnowledgeRetriever:
        """Return the Kaari knowledge retriever."""
        return self.knowledge_retriever
