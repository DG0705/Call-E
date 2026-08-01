from call_e_shared.config import ServiceSettings
from call_e_shared.health import build_health_response


def test_health_response_contains_service_name() -> None:
    response = build_health_response(ServiceSettings(service_name="test-service"))

    assert response.status == "healthy"
    assert response.service == "test-service"
