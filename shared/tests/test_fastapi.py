from fastapi.testclient import TestClient

from call_e_shared.config import ServiceSettings
from call_e_shared.fastapi import create_app


def test_app_factory_exposes_health_and_request_id() -> None:
    client = TestClient(create_app(ServiceSettings(service_name="test-service")))

    response = client.get("/health", headers={"X-Request-ID": "request-123"})

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "test-service"}
    assert response.headers["X-Request-ID"] == "request-123"
