from call_e_shared.config import ServiceSettings
from call_e_shared.health import build_health_response


def test_health_response_contains_service_name_and_request_id() -> None:
    response = build_health_response(
        ServiceSettings(service_name="test-service"),
        request_id="request-123",
    )

    assert response.status == "healthy"
    assert response.service_name == "test-service"
    assert response.version == "v1"
    assert response.request_id == "request-123"
