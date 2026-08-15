"""Tests for the read-only tenant and agent core routes."""

import asyncio

from fastapi.testclient import TestClient

from agent_service.app import create_agent_app
from agent_service.models import AGENTS_COLLECTION, TENANTS_COLLECTION, Agent, Tenant
from agent_service.repositories import AgentRepository, TenantRepository
from agent_service.services import AgentService, TenantService


class FakeCoreDatabase:
    def __init__(self, collections: list[str]) -> None:
        self.collections = collections
        self.filters: list[dict[str, str]] = []

    async def list_collection_names(self, **kwargs: object) -> list[str]:
        self.filters.append(kwargs["filter"])
        return self.collections


def test_tenant_model_serializes_mongo_id() -> None:
    tenant = Tenant.model_validate(
        {
            "_id": "tenant-1",
            "name": "Example tenant",
            "created_at": "2026-08-03T12:00:00Z",
            "updated_at": "2026-08-03T12:00:00Z",
        }
    )

    assert tenant.status == "active"
    assert tenant.model_dump(by_alias=True)["_id"] == "tenant-1"


def test_agent_model_links_to_a_tenant() -> None:
    agent = Agent.model_validate(
        {
            "_id": "agent-1",
            "tenant_id": "tenant-1",
            "name": "Receptionist",
            "created_at": "2026-08-03T12:00:00Z",
            "updated_at": "2026-08-03T12:00:00Z",
        }
    )

    assert agent.tenant_id == "tenant-1"
    assert agent.status == "active"


def test_repositories_and_services_check_only_their_collection() -> None:
    database = FakeCoreDatabase([TENANTS_COLLECTION, AGENTS_COLLECTION])

    assert asyncio.run(TenantService(TenantRepository(database)).collection_exists()) is True
    assert asyncio.run(AgentService(AgentRepository(database)).collection_exists()) is True
    assert database.filters == [
        {"name": TENANTS_COLLECTION},
        {"name": AGENTS_COLLECTION},
    ]


def test_tenant_status_propagates_request_id() -> None:
    database = FakeCoreDatabase([TENANTS_COLLECTION, AGENTS_COLLECTION])
    client = TestClient(
        create_agent_app(
            tenant_service=TenantService(TenantRepository(database)),
            agent_service=AgentService(AgentRepository(database)),
        )
    )

    response = client.get(
        "/api/v1/tenants/status", headers={"X-Request-ID": "tenant-status-request"}
    )

    assert response.status_code == 200
    assert response.json()["description"] == "Call-E tenant core"
    assert response.json()["request_id"] == "tenant-status-request"
    assert response.headers["X-Request-ID"] == "tenant-status-request"


def test_agent_status_and_database_check_are_read_only() -> None:
    database = FakeCoreDatabase([TENANTS_COLLECTION, AGENTS_COLLECTION])
    client = TestClient(
        create_agent_app(
            tenant_service=TenantService(TenantRepository(database)),
            agent_service=AgentService(AgentRepository(database)),
        )
    )

    status = client.get("/api/v1/agents/status")
    ping = client.get("/api/v1/agents/ping-db", headers={"X-Request-ID": "agent-db-request"})

    assert status.status_code == 200
    assert status.json()["description"] == "Call-E agent core"
    assert ping.status_code == 200
    assert ping.json()["request_id"] == "agent-db-request"
    assert database.filters == [{"name": AGENTS_COLLECTION}]


def test_tenant_database_check_is_read_only() -> None:
    database = FakeCoreDatabase([TENANTS_COLLECTION, AGENTS_COLLECTION])
    client = TestClient(
        create_agent_app(
            tenant_service=TenantService(TenantRepository(database)),
            agent_service=AgentService(AgentRepository(database)),
        )
    )

    response = client.get("/api/v1/tenants/ping-db")

    assert response.status_code == 200
    assert database.filters == [{"name": TENANTS_COLLECTION}]
