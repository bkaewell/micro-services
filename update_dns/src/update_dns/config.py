import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env once
load_dotenv()

class Config:
    """Centralized config for Hardware and Feature flag data structures"""

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

    # --- Feature flags ---
    DEBUG_ENABLED = os.getenv("DEBUG_ENABLED", "false").lower() == "true"
    RUNNING_IN_DOCKER = Path("/.dockerenv").exists() or os.getenv("DOCKER", "false").lower() == "true"
    WATCHDOG_ENABLED = os.getenv("WATCHDOG_ENABLED", "false").lower() == "true"
    # METRICS_DB = os.getenv("METRICS_DB", "metrics.db")
    # AUTOPILOT_INTERVAL = int(os.getenv("AUTOPILOT_INTERVAL", "60"))
