import json
import logging

from call_e_shared.logging import JSONFormatter, configure_logging


def test_configure_logging_is_idempotent() -> None:
    logger = configure_logging(service_name="test-service", level="INFO")
    configure_logging(service_name="test-service", level="DEBUG")

    assert logger.level == 10
    stream_handlers = [
        handler
        for handler in logger.handlers
        if type(handler) is logging.StreamHandler
    ]
    assert len(stream_handlers) == 1
    formatter = stream_handlers[0].formatter
    assert isinstance(formatter, JSONFormatter)
    assert formatter.service_name == "test-service"

    payload = json.loads(formatter.format(logger.makeRecord(
        logger.name, 20, __file__, 1, "runtime ready", (), None
    )))
    assert payload["service"] == "test-service"
    assert "request_id" in payload
