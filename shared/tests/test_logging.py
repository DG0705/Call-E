import json

from call_e_shared.logging import JSONFormatter, configure_logging


def test_configure_logging_is_idempotent() -> None:
    logger = configure_logging(service_name="test-service", level="INFO")
    configure_logging(service_name="test-service", level="DEBUG")

    assert logger.level == 10
    assert len(logger.handlers) == 1
    formatter = logger.handlers[0].formatter
    assert isinstance(formatter, JSONFormatter)
    assert formatter.service_name == "test-service"

    payload = json.loads(formatter.format(logger.makeRecord(
        logger.name, 20, __file__, 1, "runtime ready", (), None
    )))
    assert payload["service"] == "test-service"
    assert "request_id" in payload
