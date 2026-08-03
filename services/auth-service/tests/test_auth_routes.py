import asyncio

from fastapi.testclient import TestClient

from auth_service.app import create_auth_app
from auth_service.models import AUTH_ACCOUNTS_COLLECTION, AuthAccount
from auth_service.repositories import AuthAccountRepository


class FakeAuthDatabase:
    def __init__(self, collections: list[str]) -> None:
        self.collections = collections
        self.filters: list[dict[str, str]] = []

    async def list_collection_names(self, **kwargs: object) -> list[str]:
        self.filters.append(kwargs["filter"])
        return self.collections


def test_auth_health_uses_the_shared_response_contract() -> None:
    client = TestClient(create_auth_app())

    response = client.get("/health", headers={"X-Request-ID": "health-request"})

    assert response.status_code == 200
    assert response.json() == {
        "service_name": "auth-service",
        "status": "healthy",
        "version": "v1",
        "request_id": "health-request",
    }
    assert response.headers["X-Request-ID"] == "health-request"


def test_auth_foundation_status_propagates_request_id() -> None:
    client = TestClient(create_auth_app())

    response = client.get(
        "/api/v1/auth/status",
        headers={"X-Request-ID": "auth-status-request"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "service_name": "auth-service",
        "status": "healthy",
        "version": "v1",
        "request_id": "auth-status-request",
        "description": "Call-E authentication foundation",
    }
    assert response.headers["X-Request-ID"] == "auth-status-request"


def test_auth_account_model_is_minimal_and_serializes_mongo_id() -> None:
    account = AuthAccount.model_validate(
        {
            "_id": "account-1",
            "service_name": "auth-service",
            "created_at": "2026-08-03T12:00:00Z",
            "updated_at": "2026-08-03T12:00:00Z",
        }
    )

    assert account.status == "active"
    assert account.model_dump(by_alias=True)["_id"] == "account-1"


def test_auth_repository_checks_only_the_auth_collection() -> None:
    database = FakeAuthDatabase([AUTH_ACCOUNTS_COLLECTION])
    repository = AuthAccountRepository(database)

    assert asyncio.run(repository.collection_exists()) is True
    assert database.filters == [{"name": AUTH_ACCOUNTS_COLLECTION}]


def test_auth_repository_reports_a_missing_collection_without_creating_it() -> None:
    database = FakeAuthDatabase([])

    assert asyncio.run(AuthAccountRepository(database).collection_exists()) is False
    assert database.filters == [{"name": AUTH_ACCOUNTS_COLLECTION}]


def test_auth_database_ping_is_read_only_and_propagates_request_id() -> None:
    database = FakeAuthDatabase([AUTH_ACCOUNTS_COLLECTION])
    client = TestClient(create_auth_app(auth_repository=AuthAccountRepository(database)))

    response = client.get(
        "/api/v1/auth/ping-db", headers={"X-Request-ID": "auth-db-request"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "service_name": "auth-service",
        "status": "healthy",
        "version": "v1",
        "request_id": "auth-db-request",
        "description": "Auth database connection verified",
    }
    assert response.headers["X-Request-ID"] == "auth-db-request"
