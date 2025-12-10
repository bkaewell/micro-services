import sys
import logging


# Why not, make it fun 
LOG_LEVEL_EMOJIS = {
    logging.DEBUG: "🧱",
    #logging.INFO: " 🟢",
    logging.INFO: "🟢",
    #logging.WARNING: " ⚠️ ",
    logging.WARNING: "⚠️",
    logging.ERROR: "❌",
    logging.CRITICAL: "🔥",  # For severe errors, typically logged via exception()
}

# Shorten default log level names for uniform 4-5 character output
LEVEL_NAME_MAP = {
    "WARNING": "WARN",
    "CRITICAL": "FATAL",
}

class EmojiFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        """
        Formatter that prepends an emoji per 
        log level and shortens log level names.
        """
        record.levelemoji = LOG_LEVEL_EMOJIS.get(record.levelno, "")
        record.levelname = LEVEL_NAME_MAP.get(record.levelname, record.levelname)
        return super().format(record)

def setup_logging(level=logging.INFO) -> None:
    """
    Configure global application logging with emoji decorations.
    """
    handler = logging.StreamHandler(sys.stdout)
    formatter = EmojiFormatter(
        #fmt="%(asctime)s [%(levelname)s] %(levelemoji)s %(name)s:%(funcName)s:%(lineno)d → %(message)s",
        #datefmt="%Y-%m-%d %H:%M:%S",
        fmt="%(asctime)s %(levelemoji)s %(name)s:%(funcName)s → %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

def get_logger(name: str) -> logging.Logger:
    """
    Return a namespaced logger for any module.
    """
    #return logging.getLogger(f"update_dns.{name}") # w/ namespace (update_dns)
    return logging.getLogger(f"{name}")
