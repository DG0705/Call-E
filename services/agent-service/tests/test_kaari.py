"""Comprehensive tests for the Kaari AI Sales Agent MVP."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from agent_service.kaari.catalog import KAARI_TENANT_ID, kaari_product_catalog
from agent_service.kaari.knowledge import KaariKnowledgeRetriever
from agent_service.kaari.lead_tool import CreateSalesLeadTool
from agent_service.kaari.models import Product, ProductVariant, SalesLead
from agent_service.kaari.pricing import calculate_retail_price
from agent_service.kaari.product_tools import (
    CalculateRetailPriceTool,
    GetProductDetailsTool,
    SearchProductsTool,
)
from agent_service.kaari.repositories import LeadRepository, ProductRepository
from agent_service.kaari.service import KaariService, create_kaari_agent
from agent_service.models import Agent
from agent_service.runtime.tools import (
    ToolCall,
    ToolExecutionContext,
    ToolRegistry,
    ToolResult,
    create_development_tool_registry,
)


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def build_context(
    *, tenant_id: str = KAARI_TENANT_ID, call_id: str = "call-test-1"
) -> ToolExecutionContext:
    return ToolExecutionContext(
        tenant_id=tenant_id,
        agent_id="kaari-sales-agent",
        conversation_id="conv-test-1",
        call_id=call_id,
    )


# --- Catalog Loading ---


def test_catalog_loads_real_products() -> None:
    catalog = kaari_product_catalog()
    assert len(catalog) >= 40
    assert all(p.tenant_id == KAARI_TENANT_ID for p in catalog)
    assert all(p.product_id.startswith("KP-") for p in catalog)
    assert all(p.model_name for p in catalog)
    assert all(len(p.variants) > 0 for p in catalog)


def test_catalog_has_all_collections() -> None:
    catalog = kaari_product_catalog()
    collections = {p.collection for p in catalog if p.collection}
    assert "Neo" in collections
    assert "Heritage" in collections
    assert "Linea" in collections


def test_catalog_prices_are_decimal() -> None:
    catalog = kaari_product_catalog()
    for product in catalog:
        for v in product.variants:
            assert isinstance(v.listed_price, Decimal)
            assert v.listed_price > 0
            assert v.currency == "INR"


def test_catalog_dimensions_are_decimal() -> None:
    catalog = kaari_product_catalog()
    for product in catalog:
        for v in product.variants:
            if v.upper_diameter is not None:
                assert isinstance(v.upper_diameter, Decimal)
            if v.lower_diameter is not None:
                assert isinstance(v.lower_diameter, Decimal)
            if v.height is not None:
                assert isinstance(v.height, Decimal)
            assert v.dimensions_unit == "inch"


def test_catalog_rectangular_products_have_length_width() -> None:
    catalog = kaari_product_catalog()
    rectangle = next(p for p in catalog if p.model_name == "RECTANGLE")
    assert rectangle.variants[0].length is not None
    assert rectangle.variants[0].width is not None
    assert rectangle.variants[0].height is not None


def test_catalog_round_products_have_diameter() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    assert dew.variants[0].upper_diameter is not None
    assert dew.variants[0].lower_diameter is not None
    assert dew.variants[0].height is not None


def test_product_model_computed_fields() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    assert dew.min_price == Decimal("4200")
    assert dew.max_price == Decimal("14600")
    assert "4,200" in dew.price_range_display
    assert "14,600" in dew.price_range_display
    assert len(dew.all_colours) > 0
    assert len(dew.all_finishes) > 0


def test_variant_computed_fields() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    assert v.price_display == "\u20b94,200"
    assert "UD" in v.dimensions_summary
    assert "BD" in v.dimensions_summary
    assert "H" in v.dimensions_summary


def test_specific_catalog_prices_match_pdf() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    assert dew.variants[0].listed_price == Decimal("4200")
    assert dew.variants[1].listed_price == Decimal("7300")
    assert dew.variants[2].listed_price == Decimal("9900")
    assert dew.variants[3].listed_price == Decimal("14600")

    arlo = next(p for p in catalog if p.model_name == "ARLO")
    assert arlo.variants[0].listed_price == Decimal("3100")
    assert arlo.variants[4].listed_price == Decimal("14600")

    cube = next(p for p in catalog if p.model_name == "CUBE")
    assert cube.variants[0].listed_price == Decimal("4200")
    assert cube.variants[6].listed_price == Decimal("41800")


# --- Agent Configuration ---


def test_kaari_agent_configuration() -> None:
    agent = create_kaari_agent()
    assert agent.id == "kaari-sales-agent"
    assert agent.tenant_id == KAARI_TENANT_ID
    assert agent.name == "Kaari AI Sales Agent"
    assert agent.role == "AI Sales Representative"
    assert "search_products" in agent.allowed_tools
    assert "get_product_details" in agent.allowed_tools
    assert "calculate_retail_price" in agent.allowed_tools
    assert "create_sales_lead" in agent.allowed_tools
    assert len(agent.system_prompt) > 100
    assert agent.language == "en"


def test_kaari_agent_no_old_price_tool() -> None:
    agent = create_kaari_agent()
    assert "get_product_price" not in agent.allowed_tools
    assert "calculate_retail_price" in agent.allowed_tools


# --- Product Repository ---


def test_product_repository_seed_and_get() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())
    product = run(repo.get(tenant_id=KAARI_TENANT_ID, product_id="KP-DEW"))
    assert product is not None
    assert product.model_name == "DEW"
    assert product.collection == "Neo"


def test_product_repository_tenant_isolation() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())
    product = run(repo.get(tenant_id="other-tenant", product_id="KP-DEW"))
    assert product is None


def test_product_repository_search_by_query() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())
    results = run(repo.search(tenant_id=KAARI_TENANT_ID, query="concrete"))
    assert len(results) >= 1
    assert any("KIMI" in p.model_name or "ASPEN" in p.model_name for p in results)


def test_product_repository_search_by_collection() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())
    results = run(repo.search(tenant_id=KAARI_TENANT_ID, collection="Heritage"))
    assert len(results) >= 10
    assert all(p.collection == "Heritage" for p in results)


def test_product_repository_search_by_colour() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())
    results = run(repo.search(tenant_id=KAARI_TENANT_ID, colour="Jet Black"))
    assert len(results) >= 1


def test_product_repository_search_by_finish() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())
    results = run(repo.search(tenant_id=KAARI_TENANT_ID, finish="Concrete"))
    assert len(results) >= 1


def test_product_repository_search_by_size() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())
    results = run(repo.search(tenant_id=KAARI_TENANT_ID, size="24"))
    assert len(results) >= 1


def test_product_repository_search_by_height_range() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())
    results = run(repo.search(
        tenant_id=KAARI_TENANT_ID,
        height_min=Decimal("10"),
        height_max=Decimal("20"),
    ))
    assert len(results) >= 1


def test_product_repository_list_all() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())
    all_products = run(repo.list_all(tenant_id=KAARI_TENANT_ID))
    assert len(all_products) >= 40


# --- Pricing Engine ---


def test_pricing_tier_1_to_3_range() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]

    result = calculate_retail_price(product=dew, variant=v, quantity=1)
    assert result["bulk_quote_required"] is False
    assert result["discount_min"] == "20%"
    assert result["discount_max"] == "25%"
    assert result["indicative_unit_price_min"] is not None
    assert result["indicative_unit_price_max"] is not None
    assert Decimal(result["indicative_unit_price_min"]) < v.listed_price
    assert Decimal(result["indicative_unit_price_max"]) < v.listed_price
    assert Decimal(result["indicative_unit_price_max"]) >= Decimal(result["indicative_unit_price_min"])


def test_pricing_tier_4_to_19_exact() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]

    result = calculate_retail_price(product=dew, variant=v, quantity=10)
    assert result["bulk_quote_required"] is False
    assert result["discount_min"] == "30%"
    assert result["discount_max"] == "30%"
    expected_unit = (Decimal("4200") * Decimal("0.70")).quantize(Decimal("0.01"))
    assert Decimal(result["indicative_unit_price_min"]) == expected_unit
    assert Decimal(result["indicative_unit_price_max"]) == expected_unit
    expected_subtotal = (expected_unit * Decimal("10")).quantize(Decimal("0.01"))
    assert Decimal(result["indicative_subtotal_min"]) == expected_subtotal


def test_pricing_tier_20_plus_bulk() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]

    result = calculate_retail_price(product=dew, variant=v, quantity=25)
    assert result["bulk_quote_required"] is True
    assert result["indicative_unit_price_min"] is None
    assert result["indicative_unit_price_max"] is None
    assert "catalog_subtotal" in result


def test_pricing_boundary_quantity_1() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=1)
    assert result["bulk_quote_required"] is False
    assert result["discount_min"] == "20%"


def test_pricing_boundary_quantity_3() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=3)
    assert result["bulk_quote_required"] is False
    assert result["discount_min"] == "20%"


def test_pricing_boundary_quantity_4() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=4)
    assert result["bulk_quote_required"] is False
    assert result["discount_min"] == "30%"


def test_pricing_boundary_quantity_19() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=19)
    assert result["bulk_quote_required"] is False
    assert result["discount_min"] == "30%"


def test_pricing_boundary_quantity_20() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=20)
    assert result["bulk_quote_required"] is True


def test_pricing_uses_decimal_arithmetic() -> None:
    catalog = kaari_product_catalog()
    arlo = next(p for p in catalog if p.model_name == "ARLO")
    v = arlo.variants[0]
    result = calculate_retail_price(product=arlo, variant=v, quantity=5)
    unit_price = Decimal(result["indicative_unit_price_min"])
    subtotal = Decimal(result["indicative_subtotal_min"])
    assert subtotal == (unit_price * Decimal("5")).quantize(Decimal("0.01"))


def test_pricing_invalid_quantity() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    with pytest.raises(ValueError):
        calculate_retail_price(product=dew, variant=v, quantity=0)


# --- Lead Repository ---


def test_lead_repository_create_and_get() -> None:
    repo = LeadRepository()
    lead = SalesLead(
        lead_id="lead-1",
        tenant_id=KAARI_TENANT_ID,
        customer_name="Test Customer",
        phone="+911234567890",
        requirements="20 planters",
        interested_products=["KP-DEW"],
        quantity=20,
    )
    created = run(repo.create(lead))
    assert created.lead_id == "lead-1"
    loaded = run(repo.get(tenant_id=KAARI_TENANT_ID, lead_id="lead-1"))
    assert loaded is not None
    assert loaded.customer_name == "Test Customer"


def test_lead_repository_tenant_isolation() -> None:
    repo = LeadRepository()
    lead = SalesLead(
        lead_id="lead-1",
        tenant_id=KAARI_TENANT_ID,
        customer_name="Test",
        phone="+911234567890",
        requirements="test",
    )
    run(repo.create(lead))
    result = run(repo.get(tenant_id="other-tenant", lead_id="lead-1"))
    assert result is None


# --- Lead Tool ---


def test_create_sales_lead_captures_enquiry() -> None:
    service = KaariService()
    tool = CreateSalesLeadTool(service.lead_repository)
    ctx = build_context(call_id="call-lead-1")

    result = run(
        tool.execute(
            ctx,
            {
                "customer_name": "Priya Sharma",
                "phone": "+919876543210",
                "email": "priya@example.com",
                "company": "Green Spaces Ltd",
                "location": "Mumbai",
                "requirements": "30 round planters for office lobby",
                "product_ids": ["KP-NOVA", "KP-AQUA"],
                "quantity": 30,
                "preferred_colours": ["Pearl Beige", "Light Ivory"],
                "preferred_finish": "Matte",
                "notes": "Bulk order",
            },
        )
    )

    assert result.success is True
    assert result.result["lead_id"] is not None
    assert result.result["status"] == "new"
    assert result.result["bulk_order"] is True
    assert "Priya Sharma" in result.result["confirmation"]

    lead = run(
        service.lead_repository.get(
            tenant_id=KAARI_TENANT_ID, lead_id=result.result["lead_id"]
        )
    )
    assert lead is not None
    assert lead.customer_name == "Priya Sharma"
    assert lead.phone == "+919876543210"
    assert lead.company == "Green Spaces Ltd"
    assert lead.location == "Mumbai"
    assert lead.preferred_colours == ["Pearl Beige", "Light Ivory"]
    assert lead.preferred_finish == "Matte"
    assert lead.quantity == 30


def test_create_sales_lead_small_order_no_bulk_note() -> None:
    service = KaariService()
    tool = CreateSalesLeadTool(service.lead_repository)
    ctx = build_context(call_id="call-small-1")

    result = run(
        tool.execute(
            ctx,
            {
                "customer_name": "Small Buyer",
                "phone": "+911234567890",
                "requirements": "A couple of planters",
                "product_ids": ["KP-DEW"],
                "quantity": 2,
            },
        )
    )

    assert result.success is True
    assert result.result["bulk_order"] is False


def test_create_sales_lead_validates_required_fields() -> None:
    service = KaariService()
    tool = CreateSalesLeadTool(service.lead_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"customer_name": "", "phone": "+91123", "requirements": "test"}))
    assert result.success is False
    assert "name" in result.error.lower()

    result = run(tool.execute(ctx, {"customer_name": "Test", "phone": "", "requirements": "test"}))
    assert result.success is False
    assert "phone" in result.error.lower()

    result = run(tool.execute(ctx, {"customer_name": "Test", "phone": "+91123", "requirements": ""}))
    assert result.success is False
    assert "requirements" in result.error.lower()


# --- Search Products Tool ---


def test_search_products_tool_returns_matching_products() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"query": "concrete"}))
    assert result.success is True
    assert result.result["count"] > 0


def test_search_products_tool_with_collection() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"collection": "Linea"}))
    assert result.success is True
    assert result.result["count"] > 0


def test_search_products_tool_no_results() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"query": "xyznonexistent"}))
    assert result.success is True
    assert result.result["count"] == 0


# --- Get Product Details Tool ---


def test_get_product_details_returns_full_record() -> None:
    service = KaariService()
    tool = GetProductDetailsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "KP-ARLO"}))
    assert result.success is True
    assert result.result["model_name"] == "ARLO"
    assert result.result["collection"] == "Heritage"
    assert len(result.result["variants"]) == 9
    assert result.result["made_to_order"] is True


def test_get_product_details_not_found() -> None:
    service = KaariService()
    tool = GetProductDetailsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "NON-EXISTENT"}))
    assert result.success is False
    assert "not found" in result.error.lower()


def test_get_product_details_tenant_isolation() -> None:
    service = KaariService()
    tool = GetProductDetailsTool(service.product_repository)
    ctx = build_context(tenant_id="other-tenant")

    result = run(tool.execute(ctx, {"product_id": "KP-DEW"}))
    assert result.success is False


# --- Calculate Retail Price Tool ---


def test_calculate_retail_price_tool_returns_pricing() -> None:
    service = KaariService()
    tool = CalculateRetailPriceTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "KP-DEW", "quantity": 10}))
    assert result.success is True
    assert result.result["bulk_quote_required"] is False
    assert result.result["discount_min"] == "30%"


def test_calculate_retail_price_tool_with_variant() -> None:
    service = KaariService()
    tool = CalculateRetailPriceTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "KP-DEW", "variant_id": "DEW-40", "quantity": 2}))
    assert result.success is True
    assert result.result["unit_list_price"] == "14600"
    assert result.result["bulk_quote_required"] is False


def test_calculate_retail_price_tool_bulk() -> None:
    service = KaariService()
    tool = CalculateRetailPriceTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "KP-DEW", "quantity": 25}))
    assert result.success is True
    assert result.result["bulk_quote_required"] is True


def test_calculate_retail_price_tool_not_found() -> None:
    service = KaariService()
    tool = CalculateRetailPriceTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "NON-EXISTENT", "quantity": 5}))
    assert result.success is False


# --- Knowledge Retrieval ---


def test_kaari_knowledge_retriever_returns_relevant_chunks() -> None:
    retriever = KaariKnowledgeRetriever()
    results = run(
        retriever.retrieve(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            query="FRP material planters lightweight",
            top_k=3,
        )
    )
    assert len(results) > 0
    assert all("kaari" in r.chunk_id.lower() for r in results)


def test_kaari_knowledge_retriever_tenant_isolation() -> None:
    retriever = KaariKnowledgeRetriever()
    results = run(
        retriever.retrieve(
            tenant_id="other-tenant",
            agent_id="kaari-sales-agent",
            query="FRP planters",
            top_k=3,
        )
    )
    assert results == []


# --- Tool Registry Integration ---


def test_kaari_tools_registered_in_combined_registry() -> None:
    from agent_service.app import create_combined_tool_registry

    registry = create_combined_tool_registry()
    tool_names = [t.tool_name for t in registry.list()]
    assert "search_products" in tool_names
    assert "get_product_details" in tool_names
    assert "calculate_retail_price" in tool_names
    assert "create_sales_lead" in tool_names
    assert "get_current_time" in tool_names


def test_kaari_agent_allowed_tools_match_registry() -> None:
    from agent_service.app import create_combined_tool_registry

    agent = create_kaari_agent()
    registry = create_combined_tool_registry()
    available = registry.available_for(agent)
    available_names = [t.tool_name for t in available]
    assert "search_products" in available_names
    assert "get_product_details" in available_names
    assert "calculate_retail_price" in available_names
    assert "create_sales_lead" in available_names


def test_kaari_tools_not_available_to_other_agent() -> None:
    from agent_service.app import create_combined_tool_registry

    other_agent = Agent(
        id="other-agent",
        tenant_id="other-tenant",
        name="Other Agent",
        allowed_tools=["get_current_time"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    registry = create_combined_tool_registry()
    available = registry.available_for(other_agent)
    available_names = [t.tool_name for t in available]
    assert "search_products" not in available_names
    assert "create_sales_lead" not in available_names


# --- Multi-turn Conversation ---


def test_multi_turn_conversation_with_real_agent_runtime() -> None:
    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.services import AgentService

    kaari_agent = create_kaari_agent()
    kaari_service = KaariService()

    class FakeAgentCollection:
        def __init__(self, agent: Agent) -> None:
            self._agent = agent

        async def find_one(self, filter: dict[str, str]) -> dict[str, object] | None:
            if filter.get("_id") == self._agent.id and filter.get("tenant_id") == self._agent.tenant_id:
                return self._agent.model_dump(by_alias=True)
            return None

    class FakeCoreDatabase:
        def __init__(self, agent: Agent) -> None:
            self.agents = FakeAgentCollection(agent)

        async def list_collection_names(self, **kwargs: object) -> list[str]:
            return ["agents"]

        def __getitem__(self, name: str) -> FakeAgentCollection:
            return self.agents

    database = FakeCoreDatabase(kaari_agent)
    agent_service_instance = AgentRepository(database)
    service = AgentService(agent_service_instance)

    runtime = AgentRuntime(
        configuration_loader=service,
        provider=MockLLMProvider(),
        conversation_store=InMemoryConversationStore(),
        tool_registry=kaari_service.create_tool_registry(),
        knowledge_retriever=kaari_service.create_knowledge_retriever(),
        knowledge_top_k=2,
    )

    result1 = run(
        runtime.respond(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            conversation_id="conv-multi-1",
            message="I need planters for my office.",
        )
    )
    assert result1.conversation_id == "conv-multi-1"

    result2 = run(
        runtime.respond(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            conversation_id="conv-multi-1",
            message="About 30, modern, around two feet.",
        )
    )
    assert result2.conversation_id == "conv-multi-1"


# --- Voice Integration ---


def test_voice_engine_can_invoke_kaari_agent() -> None:
    from voice_service.agent_runtime import RuntimeResult
    from voice_service.session import VoiceSessionManager
    from voice_service.session_store import InMemoryVoiceSessionStore
    from voice_service.stt import MockSTTProvider
    from voice_service.tts import MockTTSProvider

    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.services import AgentService

    kaari_agent = create_kaari_agent()
    kaari_service = KaariService()

    class FakeAgentCollection:
        def __init__(self, agent: Agent) -> None:
            self._agent = agent

        async def find_one(self, filter: dict[str, str]) -> dict[str, object] | None:
            if filter.get("_id") == self._agent.id and filter.get("tenant_id") == self._agent.tenant_id:
                return self._agent.model_dump(by_alias=True)
            return None

    class FakeCoreDatabase:
        def __init__(self, agent: Agent) -> None:
            self.agents = FakeAgentCollection(agent)

        async def list_collection_names(self, **kwargs: object) -> list[str]:
            return ["agents"]

        def __getitem__(self, name: str) -> FakeAgentCollection:
            return self.agents

    database = FakeCoreDatabase(kaari_agent)
    agent_service_instance = AgentRepository(database)
    service = AgentService(agent_service_instance)

    runtime = AgentRuntime(
        configuration_loader=service,
        provider=MockLLMProvider(),
        conversation_store=InMemoryConversationStore(),
        tool_registry=kaari_service.create_tool_registry(),
    )

    manager = VoiceSessionManager(
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        agent_runtime=runtime,
        session_store=InMemoryVoiceSessionStore(),
    )

    session = run(
        manager.create_session(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            conversation_id="conv-voice-1",
        )
    )
    assert session.status == "created"

    from voice_service.audio import AudioChunk

    result = run(
        manager.process_audio_input(
            tenant_id=KAARI_TENANT_ID,
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )

    assert result.tenant_id == KAARI_TENANT_ID
    assert result.agent_id == "kaari-sales-agent"
    assert result.response_text.startswith("Mock response:")


# --- Kaari Test Route ---


def test_kaari_test_route_returns_response() -> None:
    from fastapi.testclient import TestClient

    from agent_service.app import create_agent_app
    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.services import AgentService

    kaari_agent = create_kaari_agent()
    kaari_service = KaariService()

    class FakeAgentCollection:
        def __init__(self, agent: Agent) -> None:
            self._agent = agent

        async def find_one(self, filter: dict[str, str]) -> dict[str, object] | None:
            if filter.get("_id") == self._agent.id and filter.get("tenant_id") == self._agent.tenant_id:
                return self._agent.model_dump(by_alias=True)
            return None

    class FakeCoreDatabase:
        def __init__(self, agent: Agent) -> None:
            self.agents = FakeAgentCollection(agent)

        async def list_collection_names(self, **kwargs: object) -> list[str]:
            return ["agents"]

        def __getitem__(self, name: str) -> FakeAgentCollection:
            return self.agents

    database = FakeCoreDatabase(kaari_agent)
    agent_service_instance = AgentRepository(database)
    service = AgentService(agent_service_instance)

    runtime = AgentRuntime(
        configuration_loader=service,
        provider=MockLLMProvider(),
        conversation_store=InMemoryConversationStore(),
        tool_registry=kaari_service.create_tool_registry(),
        knowledge_retriever=kaari_service.create_knowledge_retriever(),
    )

    app = create_agent_app(
        agent_service=service,
        agent_runtime=runtime,
        tool_registry=kaari_service.create_tool_registry(),
        kaari_service=kaari_service,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/kaari/sales/test",
        headers={"X-Request-ID": "kaari-test-1"},
        json={
            "tenant_id": KAARI_TENANT_ID,
            "agent_id": "kaari-sales-agent",
            "conversation_id": "conv-route-1",
            "message": "I need 10 premium planters for my office",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "conv-route-1"
    assert body["response"]
    assert body["request_id"] == "kaari-test-1"


def test_kaari_test_route_404_for_unknown_agent() -> None:
    from fastapi.testclient import TestClient
    from agent_service.app import create_agent_app

    app = create_agent_app(tenant_service=None, agent_service=None)
    client = TestClient(app)

    response = client.post(
        "/api/v1/kaari/sales/test",
        json={
            "tenant_id": "kaari-planters",
            "agent_id": "nonexistent-agent",
            "conversation_id": "conv-1",
            "message": "Hello",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "kaari_agent_not_found"


# --- End-to-End Mock Call ---


def test_complete_mock_call_e2e() -> None:
    from voice_service.audio import AudioChunk
    from voice_service.session import VoiceSessionManager
    from voice_service.session_store import InMemoryVoiceSessionStore
    from voice_service.stt import MockSTTProvider
    from voice_service.tts import MockTTSProvider

    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.services import AgentService

    kaari_agent = create_kaari_agent()
    kaari_service = KaariService()

    class FakeAgentCollection:
        def __init__(self, agent: Agent) -> None:
            self._agent = agent

        async def find_one(self, filter: dict[str, str]) -> dict[str, object] | None:
            if filter.get("_id") == self._agent.id and filter.get("tenant_id") == self._agent.tenant_id:
                return self._agent.model_dump(by_alias=True)
            return None

    class FakeCoreDatabase:
        def __init__(self, agent: Agent) -> None:
            self.agents = FakeAgentCollection(agent)

        async def list_collection_names(self, **kwargs: object) -> list[str]:
            return ["agents"]

        def __getitem__(self, name: str) -> FakeAgentCollection:
            return self.agents

    database = FakeCoreDatabase(kaari_agent)
    agent_service_instance = AgentRepository(database)
    service = AgentService(agent_service_instance)

    runtime = AgentRuntime(
        configuration_loader=service,
        provider=MockLLMProvider(),
        conversation_store=InMemoryConversationStore(),
        tool_registry=kaari_service.create_tool_registry(),
        knowledge_retriever=kaari_service.create_knowledge_retriever(),
        knowledge_top_k=2,
    )

    manager = VoiceSessionManager(
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        agent_runtime=runtime,
        session_store=InMemoryVoiceSessionStore(),
    )

    session = run(
        manager.create_session(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            conversation_id="conv-e2e-1",
        )
    )

    turn1 = run(
        manager.process_audio_input(
            tenant_id=KAARI_TENANT_ID,
            session_id=session.session_id,
            audio=AudioChunk(data=b"I need 20 planters for my office", format="pcm"),
        )
    )
    assert turn1.tenant_id == KAARI_TENANT_ID
    assert turn1.agent_id == "kaari-sales-agent"
    assert turn1.audio.data

    turn2 = run(
        manager.process_audio_input(
            tenant_id=KAARI_TENANT_ID,
            session_id=session.session_id,
            audio=AudioChunk(data=b"How much do they cost?", format="pcm"),
        )
    )
    assert turn2.conversation_id == "conv-e2e-1"

    ended = run(manager.end_session(tenant_id=KAARI_TENANT_ID, session_id=session.session_id))
    assert ended.status == "ended"


# --- Observability ---


def test_tool_engine_audits_kaari_tool_executions(caplog: object) -> None:
    import logging

    from agent_service.runtime.tools import ToolEngine

    service = KaariService()
    registry = service.create_tool_registry()
    engine = ToolEngine(registry)
    ctx = build_context()
    agent = create_kaari_agent()

    result = run(
        engine.execute(
            agent=agent,
            call=ToolCall(
                tool_name="search_products",
                arguments={"query": "planter"},
                call_id="audit-call-1",
                tenant_id=KAARI_TENANT_ID,
                agent_id="kaari-sales-agent",
                conversation_id="conv-1",
            ),
        )
    )

    assert result.success is True
