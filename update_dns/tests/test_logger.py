import pytest
import logging
from update_dns.logger import setup_logging, get_logger

@pytest.mark.parametrize(
    "level, message, expected_in_output",
    [
        (logging.DEBUG, "Of Course I Still Log You", True),
        (logging.INFO, "Just Read The Assertions", True),
        (logging.WARNING, "Starlink, Made On Earth By Humans", True), 
        (logging.ERROR, "Optimus reviewing logs...", True), 
        (logging.CRITICAL, "Tesla FSD Mad Max mode logging enabled", True), 
    ],
)

def test_logger_configuration(capsys, level, message, expected_in_output):
    """Smoke test to ensure logger setup produces expected formatted output at various levels"""
    setup_logging(level=logging.DEBUG)  # always capture all messages
    logger = get_logger("test")

    # Emit log at the parametrized level
    if level == logging.DEBUG:
        logger.debug(message)
    elif level == logging.INFO:
        logger.info(message)
    elif level == logging.WARNING:
        logger.warning(message)
    elif level == logging.ERROR:
        logger.error(message)
    elif level == logging.CRITICAL:
        logger.critical(message)

    captured = capsys.readouterr()
    assert message in captured.out
    