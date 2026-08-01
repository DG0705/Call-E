from fastapi import FastAPI
from fastapi.testclient import TestClient

from call_e_shared.fastapi import create_app


def test_app_factory_creates_fastapi_app() -> None:
    app = create_app("test-service")

    assert isinstance(app, FastAPI)
    assert app.title == "test-service"


def test_health_propagates_request_id() -> None:
    client = TestClient(create_app("test-service"))
    response = client.get("/health", headers={"X-Request-ID": "request-123"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "test-service",
        "request_id": "request-123",
    }
    assert response.headers["X-Request-ID"] == "request-123"
