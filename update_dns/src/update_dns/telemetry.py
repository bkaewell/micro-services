# --- Standard library imports ---
import logging


def tlog(
    logger: logging.Logger,
    emoji: str,
    subsystem: str,
    state: str,
    primary: str = "—--",
    meta: str | None = None,
) -> None:
    """
    Emit a standardized telemetry log "tlog" line.

    Format:
        SUBSYSTEM STATE PRIMARY | meta data
    """
    msg = f"{subsystem:<12} {state:<20} {primary:<16}"
    if meta:
        msg += f" | {meta}"
    
    logger.info(f"{emoji} {msg}", stacklevel=2)
