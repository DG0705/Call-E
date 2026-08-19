"""Comprehensive tests for the Kaari AI Sales Agent MVP."""

import asyncio
from datetime import UTC, datetime

import pytest

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


# --- Agent Configuration ---


def test_kaari_agent_configuration() -> None:
    agent = create_kaari_agent()

    assert agent.id == "kaari-sales-agent"
    assert agent.tenant_id == KAARI_TENANT_ID
    assert agent.name == "Kaari AI Sales Agent"
    assert agent.role == "AI Sales Representative"
    assert "search_products" in agent.allowed_tools
    assert "get_product_details" in agent.allowed_tools
    assert "get_product_price" in agent.allowed_tools
    assert "create_sales_lead" in agent.allowed_tools
    assert len(agent.system_prompt) > 100
    assert agent.language == "en"
    assert isinstance(agent.goals, list)
    assert len(agent.goals) > 0


def test_kaari_agent_model_roundtrips() -> None:
    agent = create_kaari_agent()
    data = agent.model_dump()
    restored = Agent.model_validate(data)
    assert restored.id == agent.id
    assert restored.allowed_tools == agent.allowed_tools


# --- Product Model ---


def test_product_model_has_required_fields() -> None:
    product = Product(
        product_id="test-1",
        tenant_id=KAARI_TENANT_ID,
        product_code="T01",
        name="Test Product",
        description="A test product",
        category="Test",
        dimensions="10x10x10",
        material="FRP",
        colours=["White"],
        finish="Matte",
        base_price=1000.0,
        currency="INR",
    )
    assert product.product_id == "test-1"
    assert product.active is True
    assert product.price_display == "INR 1,000.00"
    assert product.metadata == {}


def test_product_catalog_is_not_empty() -> None:
    catalog = kaari_product_catalog()
    assert len(catalog) >= 5
    assert all(p.tenant_id == KAARI_TENANT_ID for p in catalog)
    assert all(p.product_id for p in catalog)
    assert all(p.base_price > 0 for p in catalog)


# --- Product Repository ---


def test_product_repository_seed_and_get() -> None:
    repo = ProductRepository()
    catalog = kaari_product_catalog()
    repo.seed(catalog)

    product = run(repo.get(tenant_id=KAARI_TENANT_ID, product_id="KP-FRP-001"))
    assert product is not None
    assert product.name == "Classic FRP Trough Planter"
    assert product.base_price == 2499.0


def test_product_repository_tenant_isolation() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())

    product = run(repo.get(tenant_id="other-tenant", product_id="KP-FRP-001"))
    assert product is None


def test_product_repository_search_by_query() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())

    results = run(repo.search(tenant_id=KAARI_TENANT_ID, query="outdoor"))
    assert len(results) >= 1
    assert any("outdoor" in p.name.lower() or "outdoor" in p.description.lower() for p in results)


def test_product_repository_search_by_category() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())

    results = run(repo.search(tenant_id=KAARI_TENANT_ID, query="", category="Desktop Planter"))
    assert len(results) == 1
    assert results[0].product_id == "KP-FRP-005"


def test_product_repository_search_by_size() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())

    results = run(repo.search(tenant_id=KAARI_TENANT_ID, query="", size="80cm"))
    assert len(results) >= 1
    assert any("80cm" in p.dimensions.lower() for p in results)


def test_product_repository_search_no_results() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())

    results = run(repo.search(tenant_id=KAARI_TENANT_ID, query="xyznonexistent"))
    assert results == []


def test_product_repository_list_all() -> None:
    repo = ProductRepository()
    repo.seed(kaari_product_catalog())

    all_products = run(repo.list_all(tenant_id=KAARI_TENANT_ID))
    assert len(all_products) == len(kaari_product_catalog())


# --- Lead Repository ---


def test_lead_repository_create_and_get() -> None:
    repo = LeadRepository()
    lead = SalesLead(
        lead_id="lead-1",
        tenant_id=KAARI_TENANT_ID,
        customer_name="Test Customer",
        phone="+911234567890",
        requirements="20 planters",
        interested_products=["KP-FRP-001"],
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
        customer_name="Test Customer",
        phone="+911234567890",
        requirements="20 planters",
    )
    run(repo.create(lead))

    result = run(repo.get(tenant_id="other-tenant", lead_id="lead-1"))
    assert result is None


# --- Search Products Tool ---


def test_search_products_tool_returns_matching_products() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"query": "planter"}))

    assert result.success is True
    assert result.result is not None
    assert result.result["count"] > 0  # type: ignore[index]
    products = result.result["products"]  # type: ignore[index]
    assert all("product_id" in p for p in products)


def test_search_products_tool_with_category() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"query": "planter", "category": "Desktop Planter"}))

    assert result.success is True
    assert result.result["count"] == 1  # type: ignore[index]


def test_search_products_tool_no_results() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"query": "xyznonexistent"}))

    assert result.success is True
    products = result.result["products"]  # type: ignore[index]
    assert products == []


def test_search_products_tool_definition_has_correct_schema() -> None:
    service = KaariService()
    tool = SearchProductsTool(service.product_repository)
    definition = tool.definition()

    assert definition.tool_name == "search_products"
    assert "query" in definition.input_schema["required"]
    assert definition.risk_level == "low"


# --- Get Product Details Tool ---


def test_get_product_details_returns_full_record() -> None:
    service = KaariService()
    tool = GetProductDetailsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "KP-FRP-001"}))

    assert result.success is True
    assert result.result["name"] == "Classic FRP Trough Planter"  # type: ignore[index]
    assert result.result["material"] == "Fibreglass Reinforced Plastic"  # type: ignore[index]
    assert "White" in result.result["colours"]  # type: ignore[index]
    assert result.result["base_price"] == 2499.0  # type: ignore[index]


def test_get_product_details_not_found() -> None:
    service = KaariService()
    tool = GetProductDetailsTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "NON-EXISTENT"}))

    assert result.success is False
    assert "not found" in result.error.lower()  # type: ignore[union-attr]


def test_get_product_details_tenant_isolation() -> None:
    service = KaariService()
    tool = GetProductDetailsTool(service.product_repository)
    ctx = build_context(tenant_id="other-tenant")

    result = run(tool.execute(ctx, {"product_id": "KP-FRP-001"}))

    assert result.success is False


# --- Get Product Price Tool ---


def test_get_product_price_returns_authoritative_price() -> None:
    service = KaariService()
    tool = GetProductPriceTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "KP-FRP-001", "quantity": 10}))

    assert result.success is True
    assert result.result["unit_price"] == 2499.0  # type: ignore[index]
    assert result.result["quantity"] == 10  # type: ignore[index]
    assert result.result["subtotal"] == 24990.0  # type: ignore[index]
    assert result.result["currency"] == "INR"  # type: ignore[index]


def test_get_product_price_single_unit() -> None:
    service = KaariService()
    tool = GetProductPriceTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "KP-FRP-005", "quantity": 1}))

    assert result.success is True
    assert result.result["subtotal"] == 799.0  # type: ignore[index]


def test_get_product_price_not_found() -> None:
    service = KaariService()
    tool = GetProductPriceTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "NON-EXISTENT", "quantity": 5}))

    assert result.success is False
    assert "not found" in result.error.lower()  # type: ignore[union-attr]


def test_get_product_price_never_invents_prices() -> None:
    """The tool must return the authoritative price from the repository."""
    service = KaariService()
    tool = GetProductPriceTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "KP-FRP-003", "quantity": 25}))

    assert result.success is True
    assert result.result["unit_price"] == 3999.0  # type: ignore[index]
    assert result.result["subtotal"] == 99975.0  # type: ignore[index]


def test_get_product_price_invalid_quantity() -> None:
    service = KaariService()
    tool = GetProductPriceTool(service.product_repository)
    ctx = build_context()

    result = run(tool.execute(ctx, {"product_id": "KP-FRP-001", "quantity": 0}))

    assert result.success is False
    assert "quantity" in result.error.lower()  # type: ignore[union-attr]


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
                "requirements": "30 round planters for office lobby",
                "product_ids": ["KP-FRP-002"],
                "quantity": 30,
                "notes": "Looking for sage green finish",
            },
        )
    )

    assert result.success is True
    assert result.result["lead_id"] is not None  # type: ignore[index]
    assert result.result["status"] == "new"  # type: ignore[index]
    assert "Priya Sharma" in result.result["confirmation"]  # type: ignore[index]

    lead = run(
        service.lead_repository.get(
            tenant_id=KAARI_TENANT_ID, lead_id=result.result["lead_id"]  # type: ignore[index]
        )
    )
    assert lead is not None
    assert lead.customer_name == "Priya Sharma"
    assert lead.phone == "+919876543210"
    assert lead.company == "Green Spaces Ltd"
    assert lead.interested_products == ["KP-FRP-002"]
    assert lead.quantity == 30


def test_create_sales_lead_enforces_tenant_isolation() -> None:
    service = KaariService()
    tool = CreateSalesLeadTool(service.lead_repository)
    ctx = build_context(tenant_id="other-tenant", call_id="call-other-1")

    result = run(
        tool.execute(
            ctx,
            {
                "customer_name": "Other Customer",
                "phone": "+911111111111",
                "requirements": "planters",
                "product_ids": ["KP-FRP-001"],
            },
        )
    )

    assert result.success is True
    lead = run(
        service.lead_repository.get(
            tenant_id=KAARI_TENANT_ID,
            lead_id=result.result["lead_id"],  # type: ignore[index]
        )
    )
    assert lead is None


def test_create_sales_lead_validates_required_fields() -> None:
    service = KaariService()
    tool = CreateSalesLeadTool(service.lead_repository)
    ctx = build_context()

    result = run(
        tool.execute(
            ctx,
            {
                "customer_name": "",
                "phone": "+911234567890",
                "requirements": "test",
                "product_ids": ["KP-FRP-001"],
            },
        )
    )
    assert result.success is False
    assert "name" in result.error.lower()  # type: ignore[union-attr]


def test_create_sales_lead_validates_product_ids() -> None:
    service = KaariService()
    tool = CreateSalesLeadTool(service.lead_repository)
    ctx = build_context()

    result = run(
        tool.execute(
            ctx,
            {
                "customer_name": "Test",
                "phone": "+911234567890",
                "requirements": "test",
                "product_ids": [],
            },
        )
    )
    assert result.success is False
    assert "product" in result.error.lower()  # type: ignore[union-attr]


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


def test_kaari_knowledge_retriever_returns_empty_for_unrelated_query() -> None:
    retriever = KaariKnowledgeRetriever()

    results = run(
        retriever.retrieve(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            query="xyzxyzxyz",
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
    assert "get_product_price" in tool_names
    assert "create_sales_lead" in tool_names
    assert "get_current_time" in tool_names
    assert "echo_customer_context" in tool_names


def test_kaari_agent_allowed_tools_match_registry() -> None:
    from agent_service.app import create_combined_tool_registry

    agent = create_kaari_agent()
    registry = create_combined_tool_registry()
    available = registry.available_for(agent)
    available_names = [t.tool_name for t in available]

    assert "search_products" in available_names
    assert "get_product_details" in available_names
    assert "get_product_price" in available_names
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
    """Simulate a multi-turn sales conversation through the agent runtime."""
    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore

    from agent_service.kaari.service import KaariService, create_kaari_agent

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

    kaari_agent = create_kaari_agent()
    kaari_service = KaariService()
    tool_registry = kaari_service.create_tool_registry()

    database = FakeCoreDatabase(kaari_agent)
    agent_service_instance = AgentRepository(database)
    from agent_service.services import AgentService

    service = AgentService(agent_service_instance)

    runtime = AgentRuntime(
        configuration_loader=service,
        provider=MockLLMProvider(),
        conversation_store=InMemoryConversationStore(),
        tool_registry=tool_registry,
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

    result3 = run(
        runtime.respond(
            tenant_id=KAARI_TENANT_ID,
            agent_id="kaari-sales-agent",
            conversation_id="conv-multi-1",
            message="How much do they cost?",
        )
    )
    assert result3.conversation_id == "conv-multi-1"


# --- Voice Integration ---


def test_voice_engine_can_invoke_kaari_agent() -> None:
    """Verify the voice service can invoke the Kaari agent runtime."""
    from voice_service.agent_runtime import AgentConfiguration, RuntimeResult

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
            "message": "I need 20 planters for my office",
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

    app = create_agent_app(
        tenant_service=None,
        agent_service=None,
    )
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


# --- Complete Mock Call E2E ---


def test_complete_mock_call_e2e() -> None:
    """End-to-end test: text -> mock STT -> agent runtime -> knowledge -> tools -> mock TTS."""
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
    assert turn1.audio.data  # TTS produced audio

    turn2 = run(
        manager.process_audio_input(
            tenant_id=KAARI_TENANT_ID,
            session_id=session.session_id,
            audio=AudioChunk(data=b"How much do they cost?", format="pcm"),
        )
    )
    assert turn2.conversation_id == "conv-e2e-1"

    ended = run(
        manager.end_session(
            tenant_id=KAARI_TENANT_ID, session_id=session.session_id
        )
    )
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
