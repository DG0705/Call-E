from call_e_shared import build_platform_response


def test_build_platform_response_uses_stable_defaults() -> None:
    response = build_platform_response(
        service_name="test-service",
        request_id="request-123",
    )

    assert response.model_dump(exclude_none=True) == {
        "service_name": "test-service",
        "status": "healthy",
        "version": "v1",
        "request_id": "request-123",
    }


def test_build_platform_response_supports_optional_description() -> None:
    response = build_platform_response(
        service_name="test-service",
        description="Test platform endpoint",
    )

    assert response.description == "Test platform endpoint"
