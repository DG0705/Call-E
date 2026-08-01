from fastapi.testclient import TestClient

from auth_service.app import create_auth_app


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
