# --- Standard library imports ---
import sys
import logging

# --- Project imports ---
from .config import Config


# --- Custom log levels ---
TIMING = 25   # Between INFO (20) and WARNING (30)
logging.addLevelName(TIMING, "TIME")

def timing(self, message, *args, **kwargs):
    """Add `timing` method to Logger for TIMING-level logs."""
    if self.isEnabledFor(TIMING):
        self._log(TIMING, message, args, stacklevel=2, **kwargs)

logging.Logger.timing = timing

# --- Filters ---
class TimingFilter(logging.Filter):
    """Filter out TIMING logs unless explicitly enabled."""
    def __init__(self, enabled: bool):
        super().__init__()
        self.enabled = enabled

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == TIMING:
            return self.enabled
        return True

# --- Format configuration constants ---
LOG_LEVEL_EMOJIS = {
    logging.DEBUG: "🧱",
    logging.INFO: "🟢",
    TIMING: "⚡️",
    logging.WARNING: "⚠️ ",
    logging.ERROR: "❌",
    logging.CRITICAL: "🔥",
}

LEVEL_NAME_MAP = {
    "WARNING": "WARN",
    "CRITICAL": "FATAL",
}

# --- Formatters ---
class EmojiFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        """
        Formatter that prepends an emoji per 
        log level and shortens log level names.
        """
        record.levelemoji = LOG_LEVEL_EMOJIS.get(record.levelno, "")
        record.levelname = LEVEL_NAME_MAP.get(record.levelname, record.levelname)
        return super().format(record)

# --- Public logging setup API ---
def setup_logging(level=logging.INFO) -> None:
    """
    Configure global logging with emoji decorations and optional TIMING logs.
    """
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    formatter = EmojiFormatter(
        #fmt="%(asctime)s [%(levelname)s] %(levelemoji)s %(name)s:%(funcName)s:%(lineno)d → %(message)s",
        #datefmt="%Y-%m-%d %H:%M:%S",
        fmt="%(asctime)s %(levelemoji)s %(name)s:%(funcName)s → %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Apply optional TIMING filter based on config
    handler.addFilter(TimingFilter(enabled=Config.LOG_TIMING))
    root.addHandler(handler)

def get_logger(name: str) -> logging.Logger:
    """
    Return a namespaced logger for any module.
    """
    #return logging.getLogger(f"update_dns.{name}") # w/ namespace (update_dns)
    return logging.getLogger(f"{name}")
