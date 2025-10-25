import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
    CLOUDFLARE_ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    METRICS_DB = os.getenv("METRICS_DB", "metrics.db")
    AUTOPILOT_INTERVAL = int(os.getenv("AUTOPILOT_INTERVAL", "60"))
