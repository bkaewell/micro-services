import os
from dotenv import load_dotenv

# Load .env once (handles local or Docker environments)
load_dotenv()

class Config:
    """Centralized config for Cloudflare, Google, and Hardware data structures"""

    # --- Cloudflare ---
    class Cloudflare:
        API_BASE_URL = os.getenv("CLOUDFLARE_API_BASE_URL")
        API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
        ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
        DNS_NAME = os.getenv("CLOUDFLARE_DNS_NAME")

    # --- Google ---
    class Google:
        SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
        WORKSHEET = os.getenv("GOOGLE_WORKSHEET")
        API_KEY_LOCAL = os.getenv("GOOGLE_API_KEY_LOCAL")
        API_KEY_DOCKER = os.getenv("GOOGLE_API_KEY_DOCKER")

    # --- Hardware ---
    class Hardware:
        ROUTER_IP = os.getenv("ROUTER_IP")
        PLUG_IP = os.getenv("PLUG_IP")
        REBOOT_DELAY = int(os.getenv("REBOOT_DELAY", 30))
        INIT_DELAY = int(os.getenv("INIT_DELAY", 30))

    # METRICS_DB = os.getenv("METRICS_DB", "metrics.db")
    # AUTOPILOT_INTERVAL = int(os.getenv("AUTOPILOT_INTERVAL", "60"))
