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


def test_configure_logging_enables_named_event_loggers() -> None:
    configure_logging(service_name="event-service", level="INFO")

    assert (
        logging.getLogger("voice_service.events").getEffectiveLevel()
        == logging.INFO
    )
    assert (
        logging.getLogger("agent_service.runtime.events").getEffectiveLevel()
        == logging.INFO
    )


def test_configure_logging_routes_event_records_to_stdout() -> None:
    configure_logging(service_name="sink-service", level="INFO")

    root_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(getattr(handler, "formatter", None), JSONFormatter)
    ]
    assert len(root_handlers) == 1

    # Idempotent: reconfiguring must not stack duplicate root handlers.
    configure_logging(service_name="other-service", level="INFO")
    root_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(getattr(handler, "formatter", None), JSONFormatter)
    ]
    assert len(root_handlers) == 1

    # A namespaced event logger with no handlers of its own still reaches
    # the root sink (this is what was silently dropped in production).
    event_logger = logging.getLogger("voice_service.telephony.events")
    assert event_logger.handlers == []
    record = event_logger.makeRecord(
        event_logger.name, logging.INFO, __file__, 1, "ari_stream_connected",
        (), None,
    )
    assert event_logger.isEnabledFor(logging.INFO)
    assert root_handlers[0].level == logging.NOTSET
    payload = json.loads(root_handlers[0].formatter.format(record))
    assert payload["message"] == "ari_stream_connected"
    assert payload["level"] == "INFO"
