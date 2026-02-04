# --- Standard library imports ---
from datetime import datetime


def tlog(
    emoji: str,
    subsystem: str,
    state: str,
    primary: str | None = "—————————",
    meta: str | None = None,
) -> None:
    """
    Emit a standardized, human-facing telemetry line.
    """
    ts = datetime.now().strftime("%H:%M:%S")

    primary = primary or "—————————"

    line = f"{ts} {emoji} {subsystem:<11} {state:<10} {primary:<34}"
    if meta:
        line += f" | {meta}"

    print(line, flush=True)
