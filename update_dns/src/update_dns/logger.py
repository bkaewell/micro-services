import logging
import sys

def setup_logging(level=logging.INFO) -> None:
    """Configure global application logging"""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(funcName)s:%(lineno)d → %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger for any module"""
    return logging.getLogger(f"update_dns.{name}")
