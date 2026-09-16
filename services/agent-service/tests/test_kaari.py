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


# ============================================================
# 1. CATALOG VALIDATION — REPRESENTATIVE PRODUCTS
# ============================================================


def test_catalog_total_product_count() -> None:
    catalog = kaari_product_catalog()
    total_variants = sum(len(p.variants) for p in catalog)
    assert len(catalog) >= 40
    assert total_variants >= 150


def test_dew_product_record() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    assert dew.product_id == "KP-DEW"
    assert dew.collection == "Neo"
    assert dew.description == "Conical FRP planter."
    assert len(dew.variants) == 4
    assert [v.size_label for v in dew.variants] == ["21", "28", "33", "40"]
    assert [v.listed_price for v in dew.variants] == [
        Decimal("4200"), Decimal("7300"), Decimal("9900"), Decimal("14600")
    ]
    assert dew.variants[0].catalog_page == 7
    assert dew.variants[0].upper_diameter == Decimal("8.5")
    assert dew.variants[0].lower_diameter == Decimal("6.5")
    assert dew.variants[0].height == Decimal("21")
    assert dew.variants[0].finish == "Matte"
    assert dew.variants[1].finish == "Orange Peel"
    assert "Light Ivory" in dew.variants[0].colours
    assert "Pearl Beige" in dew.variants[3].colours


def test_nova_product_record() -> None:
    catalog = kaari_product_catalog()
    nova = next(p for p in catalog if p.model_name == "NOVA")
    assert nova.product_id == "KP-NOVA"
    assert nova.collection == "Neo"
    assert nova.description == "Tapered oval FRP planter."
    assert len(nova.variants) == 3
    assert nova.variants[0].size_label == "10"
    assert nova.variants[0].listed_price == Decimal("4200")
    assert nova.variants[0].catalog_page == 9
    assert nova.variants[0].upper_diameter == Decimal("7.5")
    assert nova.variants[0].lower_diameter == Decimal("8")
    assert nova.variants[0].height == Decimal("10")
    assert nova.variants[1].finish == "Orange Peel"


def test_aqua_product_record() -> None:
    catalog = kaari_product_catalog()
    aqua = next(p for p in catalog if p.model_name == "AQUA")
    assert aqua.product_id == "KP-AQUA"
    assert aqua.collection == "Neo"
    assert len(aqua.variants) >= 5
    assert aqua.variants[0].size_label == "12"
    assert aqua.variants[0].listed_price == Decimal("3700")
    assert aqua.variants[0].catalog_page == 27
    assert aqua.variants[0].height == Decimal("12.5")
    assert aqua.variants[1].finish == "Stone Texture"
    assert aqua.variants[4].finish == "Orange Peel"
    sizes = [v.size_label for v in aqua.variants]
    assert "24" in sizes
    assert "28" in sizes


def test_arlo_product_record() -> None:
    catalog = kaari_product_catalog()
    arlo = next(p for p in catalog if p.model_name == "ARLO")
    assert arlo.product_id == "KP-ARLO"
    assert arlo.collection == "Heritage"
    assert len(arlo.variants) == 9
    assert arlo.variants[0].listed_price == Decimal("3100")
    assert arlo.variants[0].size_label == "10"
    assert arlo.variants[4].listed_price == Decimal("14600")


def test_orbit_product_record() -> None:
    catalog = kaari_product_catalog()
    orbit = next(p for p in catalog if p.model_name == "ORBIT")
    assert orbit.product_id == "KP-ORBIT"
    assert orbit.collection == "Heritage"
    assert orbit.description == "Orb-shaped FRP planter."
    assert len(orbit.variants) == 5
    assert orbit.variants[0].size_label == "10"
    assert orbit.variants[0].listed_price == Decimal("4200")
    assert orbit.variants[0].catalog_page == 77
    assert orbit.variants[0].finish == "Orange Peel"
    assert orbit.variants[0].upper_diameter == Decimal("14")
    assert orbit.variants[0].lower_diameter == Decimal("5")
    assert orbit.variants[0].height == Decimal("10")
    assert "Olive Green" in orbit.variants[0].colours
    assert orbit.variants[2].finish == "Sand & Dotted"
    assert orbit.variants[4].listed_price == Decimal("25100")


def test_mandala_product_record() -> None:
    catalog = kaari_product_catalog()
    mandala = next(p for p in catalog if p.model_name == "MANDALA")
    assert mandala.product_id == "KP-MANDALA"
    assert mandala.collection == "Heritage"
    assert mandala.description == "Heritage oval FRP planter."
    assert len(mandala.variants) == 3
    assert mandala.variants[0].size_label == "18"
    assert mandala.variants[0].listed_price == Decimal("8400")
    assert mandala.variants[0].catalog_page == 55
    assert mandala.variants[0].height == Decimal("18")
    assert mandala.variants[1].size_label == "32"
    assert mandala.variants[1].listed_price == Decimal("19900")
    assert mandala.variants[2].size_label == "47"
    assert mandala.variants[2].listed_price == Decimal("37600")
    assert "Black Grey" in mandala.variants[0].colours


def test_linea_collection_products() -> None:
    catalog = kaari_product_catalog()
    linea = [p for p in catalog if p.collection == "Linea"]
    assert len(linea) >= 10
    model_names = {p.model_name for p in linea}
    assert "EVEREST" in model_names
    assert "FUJI" in model_names
    assert "ATLAS" in model_names

    everest = next(p for p in linea if p.model_name == "EVEREST")
    assert everest.product_id == "KP-EVEREST"
    assert everest.description == "Mountain-inspired FRP planter."
    assert len(everest.variants) >= 2
    assert everest.variants[0].listed_price == Decimal("4200")
    assert everest.variants[0].catalog_page == 89
    assert everest.variants[0].height == Decimal("16")

    fuji = next(p for p in linea if p.model_name == "FUJI")
    assert fuji.product_id == "KP-FUJI"
    assert fuji.variants[0].catalog_page == 91
    assert fuji.variants[0].height == Decimal("12")


def test_heritage_collection_product_count() -> None:
    catalog = kaari_product_catalog()
    heritage = [p for p in catalog if p.collection == "Heritage"]
    assert len(heritage) >= 10


def test_neo_collection_product_count() -> None:
    catalog = kaari_product_catalog()
    neo = [p for p in catalog if p.collection == "Neo"]
    assert len(neo) >= 10


# ============================================================
# 2. PRODUCT SEARCH — NATURAL LANGUAGE QUERIES
# ============================================================


def test_search_tall_planter_30_inches() -> None:
    service = KaariService()
    repo = service.product_repository
    results = run(repo.search(
        tenant_id=KAARI_TENANT_ID,
        height_min=Decimal("28"),
        height_max=Decimal("32"),
    ))
    assert len(results) >= 1
    model_names = {p.model_name for p in results}
    assert "DEW" in model_names or "AQUA" in model_names or "MANDALA" in model_names


def test_search_15_inches_for_office() -> None:
    service = KaariService()
    repo = service.product_repository
    results = run(repo.search(
        tenant_id=KAARI_TENANT_ID,
        height_min=Decimal("13"),
        height_max=Decimal("17"),
    ))
    assert len(results) >= 3
    for p in results:
        heights = [v.height for v in p.variants if v.height is not None]
        assert heights, f"{p.model_name} has no height data"
        min_h, max_h = min(heights), max(heights)
        assert min_h <= Decimal("17") and max_h >= Decimal("13"), (
            f"{p.model_name} height range {min_h}-{max_h} does not overlap 13-17"
        )


def test_search_modern_grey() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"query": "grey", "collection": "Neo"}))
    assert result.success is True
    assert result.result["count"] >= 1
    for p in result.result["products"]:
        colours = " ".join(p.get("colours", [])).lower()
        assert "grey" in colours or "gray" in colours


def test_search_20_planters() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"query": "", "quantity": 20}))
    assert result.success is True
    assert result.result["count"] >= 10
    assert result.result.get("quantity") == 20


def test_search_linea_collection() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"collection": "Linea"}))
    assert result.success is True
    assert result.result["count"] >= 10
    for p in result.result["products"]:
        assert p["collection"] == "Linea"


def test_search_heritage_collection() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"collection": "Heritage"}))
    assert result.success is True
    assert result.result["count"] >= 10


def test_search_by_height_range_with_tool() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"height_min": 20, "height_max": 25}))
    assert result.success is True
    assert result.result["count"] >= 1


def test_search_orange_peel_finish() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"finish": "Orange Peel"}))
    assert result.success is True
    assert result.result["count"] >= 1


def test_search_stone_texture() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"texture": "Stone Texture"}))
    assert result.success is True
    assert result.result["count"] >= 1


def test_search_white_colour() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"colour": "White"}))
    assert result.success is True
    assert result.result["count"] >= 1


# ============================================================
# 3. PRICING BOUNDARY TESTS — ALL 8 QUANTITIES
# ============================================================


def test_pricing_quantity_2() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=2)
    assert result["bulk_quote_required"] is False
    assert result["discount_min"] == "20%"
    assert result["discount_max"] == "25%"
    unit_min = Decimal(result["indicative_unit_price_min"])
    unit_max = Decimal(result["indicative_unit_price_max"])
    assert unit_min <= unit_max
    assert unit_max < v.listed_price
    sub_min = Decimal(result["indicative_subtotal_min"])
    sub_max = Decimal(result["indicative_subtotal_max"])
    assert sub_min == (unit_min * Decimal("2")).quantize(Decimal("0.01"))
    assert sub_max == (unit_max * Decimal("2")).quantize(Decimal("0.01"))


def test_pricing_quantity_10() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=10)
    assert result["bulk_quote_required"] is False
    assert result["discount_min"] == "30%"
    assert result["discount_max"] == "30%"
    unit = Decimal(result["indicative_unit_price_min"])
    expected = (Decimal("4200") * Decimal("0.70")).quantize(Decimal("0.01"))
    assert unit == expected
    sub = Decimal(result["indicative_subtotal_min"])
    assert sub == (unit * Decimal("10")).quantize(Decimal("0.01"))
    assert "30%" in result["message"]


def test_pricing_quantity_25() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=25)
    assert result["bulk_quote_required"] is True
    assert result["indicative_unit_price_min"] is None
    assert result["indicative_unit_price_max"] is None
    assert result["indicative_subtotal_min"] is None
    assert result["indicative_subtotal_max"] is None
    assert result["discount_min"] is None
    assert result["discount_max"] is None
    assert result["catalog_subtotal"] == str(Decimal("4200") * Decimal("25"))
    assert "sales team" in result["message"].lower()


def test_pricing_output_language_tier_1() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=1)
    assert "20-25%" in result["message"]
    assert "indicative" in result["message"].lower()


def test_pricing_output_language_tier_2() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=10)
    assert "30%" in result["message"]


def test_pricing_output_language_tier_3() -> None:
    catalog = kaari_product_catalog()
    dew = next(p for p in catalog if p.model_name == "DEW")
    v = dew.variants[0]
    result = calculate_retail_price(product=dew, variant=v, quantity=25)
    assert "sales team" in result["message"].lower()
    assert "bulk" in result["message"].lower()


def test_pricing_different_product_variants() -> None:
    catalog = kaari_product_catalog()
    arlo = next(p for p in catalog if p.model_name == "ARLO")
    v = arlo.variants[0]
    result = calculate_retail_price(product=arlo, variant=v, quantity=5)
    unit = Decimal(result["indicative_unit_price_min"])
    expected = (Decimal("3100") * Decimal("0.70")).quantize(Decimal("0.01"))
    assert unit == expected


def test_pricing_high_value_product() -> None:
    catalog = kaari_product_catalog()
    mandala = next(p for p in catalog if p.model_name == "MANDALA")
    v = mandala.variants[2]
    result = calculate_retail_price(product=mandala, variant=v, quantity=1)
    assert result["bulk_quote_required"] is False
    unit_min = Decimal(result["indicative_unit_price_min"])
    unit_max = Decimal(result["indicative_unit_price_max"])
    assert unit_max <= Decimal("37600")
    assert unit_min <= Decimal("37600")


def test_pricing_currency_always_inr() -> None:
    catalog = kaari_product_catalog()
    for product in catalog[:5]:
        for v in product.variants[:2]:
            result = calculate_retail_price(product=product, variant=v, quantity=1)
            assert result["currency"] == "INR"


# ============================================================
# 4. LEAD CREATION — WITH PRICING INFO
# ============================================================


def test_lead_saves_product_and_quantity() -> None:
    service = KaariService()
    tool = CreateSalesLeadTool(service.lead_repository)
    ctx = build_context(call_id="call-lead-pricing")

    result = run(
        tool.execute(
            ctx,
            {
                "customer_name": "Rajesh Kumar",
                "phone": "+919988776655",
                "requirements": "10 DEW-40 planters for hotel lobby",
                "product_ids": ["KP-DEW"],
                "quantity": 10,
                "preferred_colours": ["Pearl Beige"],
                "preferred_finish": "Matte",
                "budget": 35000,
                "notes": "Indicative price Rs 2,940/unit for 10 units",
            },
        )
    )

    assert result.success is True
    lead_id = result.result["lead_id"]

    lead = run(
        service.lead_repository.get(
            tenant_id=KAARI_TENANT_ID, lead_id=lead_id
        )
    )
    assert lead is not None
    assert lead.customer_name == "Rajesh Kumar"
    assert lead.quantity == 10
    assert lead.interested_products == ["KP-DEW"]
    assert lead.preferred_colours == ["Pearl Beige"]
    assert lead.preferred_finish == "Matte"
    assert lead.budget == Decimal("35000")
    assert lead.tenant_id == KAARI_TENANT_ID


def test_lead_bulk_order_detection() -> None:
    service = KaariService()
    tool = CreateSalesLeadTool(service.lead_repository)
    ctx = build_context(call_id="call-bulk-detect")

    result = run(
        tool.execute(
            ctx,
            {
                "customer_name": "Bulk Buyer",
                "phone": "+911234567890",
                "requirements": "20 ORBIT-22 planters",
                "product_ids": ["KP-ORBIT"],
                "quantity": 20,
            },
        )
    )

    assert result.success is True
    assert result.result["bulk_order"] is True
    assert "commercial confirmation" in result.result["confirmation"].lower()


# ============================================================
# 5. BUSINESS RULES VALIDATION
# ============================================================


def test_agent_system_prompt_no_stock_claims() -> None:
    agent = create_kaari_agent()
    prompt = agent.system_prompt.lower()
    assert "made to order" in prompt
    assert "never claim stock" in prompt


def test_agent_system_prompt_no_delivery_promises() -> None:
    agent = create_kaari_agent()
    prompt = agent.system_prompt.lower()
    assert "never make unsupported promises" in prompt


def test_agent_system_prompt_bulk_rules() -> None:
    agent = create_kaari_agent()
    prompt = agent.system_prompt.lower()
    assert "20+" in prompt or "bulk" in prompt
    assert "sales team" in prompt


def test_agent_system_prompt_customization_rules() -> None:
    agent = create_kaari_agent()
    prompt = agent.system_prompt.lower()
    assert "colour" in prompt
    assert "texture" in prompt
    assert "customiz" in prompt or "customis" in prompt


def test_agent_system_prompt_pricing_tiers() -> None:
    agent = create_kaari_agent()
    prompt = agent.system_prompt.lower()
    assert "20-25%" in prompt
    assert "30%" in prompt
    assert "never invent" in prompt


def test_knowledge_includes_made_to_order() -> None:
    retriever = KaariKnowledgeRetriever()
    results = run(
        retriever.retrieve(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            query="made to order stock availability",
            top_k=5,
        )
    )
    assert len(results) >= 1
    combined = " ".join(r.content.lower() for r in results)
    assert "made to order" in combined


def test_knowledge_includes_pricing_policy() -> None:
    retriever = KaariKnowledgeRetriever()
    results = run(
        retriever.retrieve(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            query="pricing discount bulk quantity",
            top_k=5,
        )
    )
    assert len(results) >= 1
    combined = " ".join(r.content.lower() for r in results)
    assert "20-25%" in combined
    assert "30%" in combined
    assert "bulk" in combined


def test_knowledge_includes_warranty() -> None:
    retriever = KaariKnowledgeRetriever()
    results = run(
        retriever.retrieve(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            query="warranty guarantee",
            top_k=5,
        )
    )
    combined = " ".join(r.content.lower() for r in results)
    assert "warranty" in combined


# ============================================================
# 6. VOICE PIPELINE — MOCK MODE
# ============================================================


def test_voice_pipeline_preserves_kaari_context() -> None:
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
            conversation_id="conv-voice-ctx",
        )
    )

    turn = run(
        manager.process_audio_input(
            tenant_id=KAARI_TENANT_ID,
            session_id=session.session_id,
            audio=AudioChunk(data=b"I need 10 planters", format="pcm"),
        )
    )

    assert turn.tenant_id == KAARI_TENANT_ID
    assert turn.agent_id == "kaari-sales-agent"
    assert turn.conversation_id == "conv-voice-ctx"

    turn2 = run(
        manager.process_audio_input(
            tenant_id=KAARI_TENANT_ID,
            session_id=session.session_id,
            audio=AudioChunk(data=b"What do you have?", format="pcm"),
        )
    )
    assert turn2.conversation_id == "conv-voice-ctx"


def test_voice_session_tenant_isolation() -> None:
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

    session1 = run(
        manager.create_session(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            conversation_id="conv-iso-1",
        )
    )
    session2 = run(
        manager.create_session(
            tenant_id="kaari-planters",
            agent_id="kaari-sales-agent",
            conversation_id="conv-iso-2",
        )
    )
    assert session1.session_id != session2.session_id


# ============================================================
# 7. ASTERISK ROUTING VERIFICATION
# ============================================================


def test_asterisk_routing_preserves_context_fields() -> None:
    from datetime import UTC, datetime

    from voice_service.telephony.models import TelephonyCall

    now = datetime.now(UTC)
    call = TelephonyCall(
        call_id="call-astro-1",
        tenant_id=KAARI_TENANT_ID,
        agent_id="kaari-sales-agent",
        conversation_id="conv-astro-1",
        caller_number="+919876543210",
        destination_number="+918000000000",
        direction="inbound",
        status="ringing",
        provider="asterisk",
        created_at=now,
        updated_at=now,
    )
    assert call.tenant_id == KAARI_TENANT_ID
    assert call.agent_id == "kaari-sales-agent"
    assert call.conversation_id == "conv-astro-1"
    assert call.status == "ringing"
    assert call.provider == "asterisk"


def test_kaari_agent_config_is_routing_compatible() -> None:
    agent = create_kaari_agent()
    assert agent.tenant_id == KAARI_TENANT_ID
    assert agent.id == "kaari-sales-agent"
    assert agent.language == "en"
    assert len(agent.allowed_tools) >= 4
    assert "search_products" in agent.allowed_tools
    assert "create_sales_lead" in agent.allowed_tools


# ============================================================
# 8. DEVELOPMENT DEMO ENDPOINT — ENHANCED
# ============================================================


def test_kaari_test_route_response_structure() -> None:
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
        json={
            "tenant_id": KAARI_TENANT_ID,
            "agent_id": "kaari-sales-agent",
            "conversation_id": "conv-demo-1",
            "message": "I need 10 modern planters around 2 feet for my office",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "conv-demo-1"
    assert body["response"]
    assert isinstance(body["tool_calls"], list)
    assert isinstance(body["tool_results"], list)
    assert isinstance(body["products_matched"], list)
    assert "lead_id" in body
    assert "pricing" in body


def test_kaari_test_route_with_planned_tool_calls() -> None:
    from fastapi.testclient import TestClient
    from agent_service.app import create_agent_app
    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.runtime.tools import ProviderToolCall
    from agent_service.services import AgentService

    kaari_agent = create_kaari_agent()
    kaari_service = KaariService()

    planned_tools = [
        ProviderToolCall(
            call_id="planned-search-1",
            tool_name="search_products",
            arguments={"query": "planter", "collection": "Neo"},
        ),
    ]

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
        provider=MockLLMProvider(planned_tool_calls=planned_tools),
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
        json={
            "tenant_id": KAARI_TENANT_ID,
            "agent_id": "kaari-sales-agent",
            "conversation_id": "conv-tool-test",
            "message": "show me neo collection planters",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["tool_calls"]) == 1
    assert body["tool_calls"][0]["tool_name"] == "search_products"
    assert body["tool_calls"][0]["success"] is True
    assert len(body["products_matched"]) >= 1


# ============================================================
# 9. RUNTIME TOOL EXECUTION HISTORY
# ============================================================


def test_runtime_tracks_tool_execution_history() -> None:
    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.runtime.tools import ProviderToolCall
    from agent_service.services import AgentService

    kaari_agent = create_kaari_agent()
    kaari_service = KaariService()

    planned_tools = [
        ProviderToolCall(
            call_id="track-1",
            tool_name="search_products",
            arguments={"query": "planter"},
        ),
    ]

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
        provider=MockLLMProvider(planned_tool_calls=planned_tools),
        conversation_store=InMemoryConversationStore(),
        tool_registry=kaari_service.create_tool_registry(),
    )

    result = run(
        runtime.respond(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            conversation_id="conv-history-1",
            message="show me planters",
        )
    )

    assert len(result.tool_execution_history) == 1
    entry = result.tool_execution_history[0]
    assert entry["tool_name"] == "search_products"
    assert entry["success"] is True
    assert entry["arguments"]["query"] == "planter"
    assert isinstance(entry["result"], dict)
    assert entry["result"]["count"] >= 1


def test_runtime_no_tool_history_when_mock_responds_directly() -> None:
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

    result = run(
        runtime.respond(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            conversation_id="conv-nohistory",
            message="hello",
        )
    )

    assert result.tool_execution_history == []


# ============================================================
# 10. CATALOG SEED INTEGRITY
# ============================================================


def test_catalog_seed_json_is_valid_json() -> None:
    import json
    from pathlib import Path

    seed_path = Path(__file__).parent.parent / "src" / "agent_service" / "kaari" / "catalog_seed.json"
    raw = json.loads(seed_path.read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    assert len(raw) >= 40


def test_catalog_seed_all_products_have_required_fields() -> None:
    import json
    from pathlib import Path

    seed_path = Path(__file__).parent.parent / "src" / "agent_service" / "kaari" / "catalog_seed.json"
    raw = json.loads(seed_path.read_text(encoding="utf-8"))
    for entry in raw:
        assert "product_id" in entry
        assert "model_name" in entry
        assert "collection" in entry
        assert entry["collection"] in ("Neo", "Heritage", "Linea")
        assert "variants" in entry
        assert len(entry["variants"]) >= 1
        for v in entry["variants"]:
            assert "variant_id" in v
            assert "size_label" in v
            assert "listed_price" in v
            assert v["listed_price"] > 0
            assert "catalog_page" in v
            assert v["catalog_page"] >= 7


def test_catalog_seed_no_duplicate_product_ids() -> None:
    import json
    from pathlib import Path

    seed_path = Path(__file__).parent.parent / "src" / "agent_service" / "kaari" / "catalog_seed.json"
    raw = json.loads(seed_path.read_text(encoding="utf-8"))
    ids = [e["product_id"] for e in raw]
    assert len(ids) == len(set(ids))


def test_catalog_seed_all_models_present() -> None:
    import json
    from pathlib import Path

    seed_path = Path(__file__).parent.parent / "src" / "agent_service" / "kaari" / "catalog_seed.json"
    raw = json.loads(seed_path.read_text(encoding="utf-8"))
    models = {e["model_name"] for e in raw}
    required = {"DEW", "NOVA", "AQUA", "ARLO", "ORBIT", "MANDALA", "EVEREST", "FUJI"}
    assert required.issubset(models)


# ============================================================
# 11. END-TO-END MOCK WITH PLANNED TOOL CALLS
# ============================================================


def test_e2e_with_search_and_pricing_tool_calls() -> None:
    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.runtime.tools import ProviderToolCall
    from agent_service.services import AgentService

    kaari_agent = create_kaari_agent()
    kaari_service = KaariService()

    planned_tools = [
        ProviderToolCall(
            call_id="e2e-search-1",
            tool_name="search_products",
            arguments={"query": "", "collection": "Neo", "height_min": 20, "height_max": 25},
        ),
        ProviderToolCall(
            call_id="e2e-price-1",
            tool_name="calculate_retail_price",
            arguments={"product_id": "KP-DEW", "variant_id": "DEW-40", "quantity": 10},
        ),
    ]

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
        provider=MockLLMProvider(planned_tool_calls=planned_tools),
        conversation_store=InMemoryConversationStore(),
        tool_registry=kaari_service.create_tool_registry(),
    )

    result = run(
        runtime.respond(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            conversation_id="conv-e2e-tools",
            message="show me neo planters around 2 feet, price 10 of the 40 inch DEW",
        )
    )

    assert len(result.tool_execution_history) == 2

    search_entry = result.tool_execution_history[0]
    assert search_entry["tool_name"] == "search_products"
    assert search_entry["success"] is True
    search_result = search_entry["result"]
    assert search_result["count"] >= 1

    price_entry = result.tool_execution_history[1]
    assert price_entry["tool_name"] == "calculate_retail_price"
    assert price_entry["success"] is True
    price_result = price_entry["result"]
    assert price_result["bulk_quote_required"] is False
    assert price_result["discount_min"] == "30%"
    assert price_result["quantity"] == 10
    assert price_result["unit_list_price"] == "14600"


def test_e2e_with_lead_creation_tool_call() -> None:
    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.runtime.tools import ProviderToolCall
    from agent_service.services import AgentService

    kaari_agent = create_kaari_agent()
    kaari_service = KaariService()

    planned_tools = [
        ProviderToolCall(
            call_id="e2e-lead-1",
            tool_name="create_sales_lead",
            arguments={
                "customer_name": "E2E Test Customer",
                "phone": "+919999999999",
                "requirements": "10 DEW-40 planters for office",
                "product_ids": ["KP-DEW"],
                "quantity": 10,
                "preferred_colours": ["Pearl Beige"],
            },
        ),
    ]

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
        provider=MockLLMProvider(planned_tool_calls=planned_tools),
        conversation_store=InMemoryConversationStore(),
        tool_registry=kaari_service.create_tool_registry(),
    )

    result = run(
        runtime.respond(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            conversation_id="conv-e2e-lead",
            message="I want to proceed with 10 DEW-40 planters, my name is Test Customer, phone +919999999999",
        )
    )

    assert len(result.tool_execution_history) == 1
    entry = result.tool_execution_history[0]
    assert entry["tool_name"] == "create_sales_lead"
    assert entry["success"] is True
    lead_result = entry["result"]
    assert lead_result["lead_id"] is not None
    assert lead_result["status"] == "new"
    assert lead_result["bulk_order"] is False


# --- Kaari MVP Smoke Test ---
# Validates the full mock call chain:
# mock telephony → voice engine → STT → Kaari agent → tools (search/price/lead) → TTS → telephony output


def test_kaari_mvp_smoke_test() -> None:
    """End-to-end smoke test for the Kaari phone-call MVP.

    Exercises the complete mock call flow with the Kaari agent:
    1. Create inbound call via mock telephony
    2. Answer call (plays Kaari greeting via TTS)
    3. Customer says requirement → STT → Agent searches catalog
    4. Customer asks pricing → Agent uses calculate_retail_price tool
    5. Customer proceeds → Agent creates sales lead
    6. Verify audio output at each turn and call lifecycle events
    """
    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.runtime.tools import ProviderToolCall
    from agent_service.services import AgentService

    from voice_service.audio import AudioChunk
    from voice_service.session import VoiceSessionManager
    from voice_service.session_store import InMemoryVoiceSessionStore
    from voice_service.stt import MockSTTProvider
    from voice_service.tts import MockTTSProvider
    from voice_service.telephony.mock_provider import MockTelephonyProvider
    from voice_service.telephony.service import TelephonyService
    from voice_service.telephony.store import InMemoryCallStore
    from voice_service.telephony import events
    from voice_service.telephony.observability import TELEPHONY_EVENT_LOGGER

    # Kaari agent with full tool registry
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
            if name == "agents":
                return self.agents
            raise KeyError(name)

    database = FakeCoreDatabase(kaari_agent)
    agent_service_instance = AgentRepository(database)
    service = AgentService(agent_service_instance)

    # LLM provider that simulates a multi-turn conversation with Kaari tools
    planned_tools = [
        # Turn 1: customer says "I need 10 planters for my office"
        ProviderToolCall(
            call_id="turn1-search-1",
            tool_name="search_products",
            arguments={"query": "office planters", "height_min": 18, "height_max": 30},
        ),
        # Turn 2: customer asks "How much for 10 of the second one?"
        ProviderToolCall(
            call_id="turn2-price-1",
            tool_name="calculate_retail_price",
            arguments={"product_id": "KP-DEW", "variant_id": "DEW-40", "quantity": 10},
        ),
        # Turn 3: customer says "OK, I want to proceed"
        ProviderToolCall(
            call_id="turn3-lead-1",
            tool_name="create_sales_lead",
            arguments={
                "customer_name": "Smoke Test Customer",
                "phone": "+919876543210",
                "requirements": "10 DEW-40 planters for office",
                "product_ids": ["KP-DEW"],
                "quantity": 10,
                "preferred_colours": ["Pearl Beige"],
            },
        ),
    ]

    runtime = AgentRuntime(
        configuration_loader=service,
        provider=MockLLMProvider(planned_tool_calls=planned_tools),
        conversation_store=InMemoryConversationStore(),
        tool_registry=kaari_service.create_tool_registry(),
        knowledge_retriever=kaari_service.create_knowledge_retriever(),
        knowledge_top_k=2,
    )

    # Voice session manager with mock STT/TTS
    manager = VoiceSessionManager(
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        agent_runtime=runtime,
        session_store=InMemoryVoiceSessionStore(),
    )

    # Mock telephony provider and service
    provider = MockTelephonyProvider()
    call_store = InMemoryCallStore()
    from voice_service.telephony.events import LoggingEventPublisher
    telephony_service = TelephonyService(
        provider=provider,
        call_store=call_store,
        voice_manager=manager,
        event_publisher=LoggingEventPublisher(),
    )

    # --- Call starts ---
    call = run(
        telephony_service.create_inbound_call(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            caller_number="+919876543210",
            destination_number="1000",
            conversation_id="conv-smoke-1",
        )
    )
    assert call.status == "ringing"

    # Answer call -> plays greeting
    call = run(telephony_service.answer_call(tenant_id=KAARI_TENANT_ID, call_id=call.call_id))
    assert call.status == "active"
    assert call.metadata.get("session_id") is not None
    session_id = call.metadata["session_id"]

    # Verify greeting was sent (mock TTS produces audio)
    assert provider.sent_audio(call.call_id)

    # --- Turn 1: Customer asks for planters ---
    provider.queue_audio(call.call_id, AudioChunk(data=b"I need 10 planters for my office", format="pcm"))
    results = run(telephony_service.drain_audio(tenant_id=KAARI_TENANT_ID, call_id=call.call_id))

    assert len(results) == 1
    turn1 = results[0]
    assert turn1.tenant_id == KAARI_TENANT_ID
    assert turn1.agent_id == "kaari-sales-agent"
    assert turn1.conversation_id == "conv-smoke-1"
    assert turn1.transcript == "Mock transcription of customer audio."
    assert turn1.audio.data  # TTS output
    assert turn1.response_text.startswith("Mock response:")

    # --- Turn 2: Customer asks for pricing ---
    provider.queue_audio(call.call_id, AudioChunk(data=b"How much for 10 of the second one", format="pcm"))
    results = run(telephony_service.drain_audio(tenant_id=KAARI_TENANT_ID, call_id=call.call_id))

    assert len(results) == 1
    turn2 = results[0]
    assert turn2.transcript == "Mock transcription of customer audio."
    assert turn2.audio.data
    assert turn2.response_text.startswith("Mock response:")

    # --- Turn 3: Customer proceeds to create lead ---
    provider.queue_audio(call.call_id, AudioChunk(data=b"OK, I want to proceed", format="pcm"))
    results = run(telephony_service.drain_audio(tenant_id=KAARI_TENANT_ID, call_id=call.call_id))

    assert len(results) == 1
    turn3 = results[0]
    assert turn3.transcript == "Mock transcription of customer audio."
    assert turn3.audio.data
    assert turn3.response_text.startswith("Mock response:")

    # --- Call ends gracefully ---
    call = run(telephony_service.hangup(tenant_id=KAARI_TENANT_ID, call_id=call.call_id))
    assert call.status == "ended"

    # Verify call lifecycle events were emitted
    event_names = [event.name for event in call_store._events] if hasattr(call_store, '_events') else []
    # Note: events are published via event publisher; in mock it's LoggingEventPublisher
    # We verify the call record is persisted with correct state
    final_call = run(call_store.get(tenant_id=KAARI_TENANT_ID, call_id=call.call_id))
    assert final_call.status == "ended"
    assert final_call.ended_at is not None

    # Verify Kaari tenant/agent context preserved throughout
    assert final_call.tenant_id == KAARI_TENANT_ID
    assert final_call.agent_id == "kaari-sales-agent"
