import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    CLOUDFLARE_API_BASE_URL = os.getenv("CLOUDFLARE_API_BASE_URL")
    CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
    CLOUDFLARE_ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
    CLOUDFLARE_DNS_NAME = os.getenv("CLOUDFLARE_DNS_NAME")

    GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
    GOOGLE_WORKSHEET = os.getenv("GOOGLE_WORKSHEET")
    GOOGLE_API_KEY_LOCAL = os.getenv("GOOGLE_API_KEY_LOCAL")
    GOOGLE_API_KEY_DOCKER = os.getenv("GOOGLE_API_KEY_DOCKER")

    # METRICS_DB = os.getenv("METRICS_DB", "metrics.db")
    # AUTOPILOT_INTERVAL = int(os.getenv("AUTOPILOT_INTERVAL", "60"))

    # cloudflare_config = {}
    # google_config = {}



# Expand this for watchdog.py

# # =============== CONFIG ================
# PLUG_IP = "192.168.0.150"   # Shelly plug static IP
# CHECK_HOST = "8.8.8.8"      # Google DNS (reliable ping target)
# REBOOT_DELAY = 3            # seconds
# # REBOOT_DELAY = 30            # seconds
# # =======================================




