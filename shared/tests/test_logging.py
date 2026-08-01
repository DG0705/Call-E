from call_e_shared.logging import JSONFormatter, configure_logging


def test_configure_logging_is_idempotent() -> None:
    logger = configure_logging(level="INFO", logger_name="test.call_e.shared")
    configure_logging(level="DEBUG", logger_name="test.call_e.shared")

    assert logger.level == 10
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, JSONFormatter)
