import os

from dotenv import load_dotenv

# Load .env once
load_dotenv()

class Config:
    """Centralized config for Operational Parameters and Hardware data structures"""

    # --- Operational Parameters ---
    # --- Execution Policy ---
    try:
        CYCLE_INTERVAL = int(os.getenv("CYCLE_INTERVAL", 60))
    except ValueError:
        CYCLE_INTERVAL = 60

    # --- Network Policy ---
    API_TIMEOUT = 8   # seconds (safe, balanced)

    # --- Observability Policy ---
    LOG_LEVEL = os.getenv("LOG_LEVEL")
    LOG_TIMING = os.getenv("LOG_TIMING", "false").lower() == "true"

    # --- Recovery Policy ---
    WATCHDOG_ENABLED = os.getenv("WATCHDOG_ENABLED", "false").lower() == "true"

    # --- Hardware ---
    class Hardware:
        ROUTER_IP = os.getenv("ROUTER_IP")
        PLUG_IP = os.getenv("PLUG_IP")

        try:
            REBOOT_DELAY = int(os.getenv("REBOOT_DELAY", 30))
        except ValueError:
            REBOOT_DELAY = 30

        try:
            INIT_DELAY = int(os.getenv("INIT_DELAY", 30))
        except ValueError:
            INIT_DELAY = 30
