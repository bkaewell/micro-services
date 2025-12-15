import os

from pathlib import Path
from dotenv import load_dotenv

# Load .env once
load_dotenv()

class Config:
    """Centralized config for Operational Parameters and Hardware data structures"""

    # --- Operational Parameters ---

    # Safe integer conversion with default
    try:
        CYCLE_INTERVAL = int(os.getenv("CYCLE_INTERVAL", 60))
    except ValueError:
        CYCLE_INTERVAL = 60

    API_TIMEOUT = 8   # seconds (safe, balanced)
    DEBUG_ENABLED = os.getenv("DEBUG_ENABLED", "false").lower() == "true"
    WATCHDOG_ENABLED = os.getenv("WATCHDOG_ENABLED", "false").lower() == "true"
    TIMING_ENABLED = os.getenv("TIMING_ENABLED", "false").lower() == "true"
    # METRICS_DB = os.getenv("METRICS_DB", "metrics.db")

    # --- Hardware ---
    class Hardware:
        ROUTER_IP = os.getenv("ROUTER_IP")
        PLUG_IP = os.getenv("PLUG_IP")

        # Safe integer conversion with defaults
        try:
            REBOOT_DELAY = int(os.getenv("REBOOT_DELAY", 30))
        except ValueError:
            REBOOT_DELAY = 30

        try:
            INIT_DELAY = int(os.getenv("INIT_DELAY", 30))
        except ValueError:
            INIT_DELAY = 30

