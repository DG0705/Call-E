from fastapi.testclient import TestClient

from api_gateway.app import create_gateway_app


def test_gateway_health_returns_shared_response_shape() -> None:
    client = TestClient(create_gateway_app())

    response = client.get("/health", headers={"X-Request-ID": "health-request"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "api-gateway",
        "request_id": "health-request",
    }
    assert response.headers["X-Request-ID"] == "health-request"


def test_gateway_status_exposes_public_platform_route() -> None:
    client = TestClient(create_gateway_app())

    response = client.get("/api/v1/status", headers={"X-Request-ID": "status-request"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service_name": "api-gateway",
        "request_id": "status-request",
        "version": "v1",
    }
    assert response.headers["X-Request-ID"] == "status-request"


def test_gateway_info_exposes_stable_public_metadata() -> None:
    client = TestClient(create_gateway_app())

    response = client.get("/api/v1/info", headers={"X-Request-ID": "info-request"})

    assert response.status_code == 200
    assert response.json() == {
        "service_name": "api-gateway",
        "status": "healthy",
        "request_id": "info-request",
        "version": "v1",
        "description": "Call-E public API Gateway",
    }
    assert response.headers["X-Request-ID"] == "info-request"


def test_gateway_ping_exposes_compact_uptime_response() -> None:
    client = TestClient(create_gateway_app())

    response = client.get("/api/v1/ping", headers={"X-Request-ID": "ping-request"})

    assert response.status_code == 200
    assert response.json() == {
        "service_name": "api-gateway",
        "status": "ok",
        "version": "v1",
        "request_id": "ping-request",
    }
    assert response.headers["X-Request-ID"] == "ping-request"
