# --- Standard library imports ---
import json
from pathlib import Path
from typing import Optional


# --- Cache layout ---
CACHE_DIR = Path.home() / ".cache" / "update_dns"
CACHE_DIR.mkdir(parents=True, exist_ok=True) 

CLOUDFLARE_IP_FILE = CACHE_DIR / "cloudflare_ip.json"
GOOGLE_SHEET_ID_FILE = CACHE_DIR / 'google_sheet_id.txt'

# --- Cloudflare IP cache ---
def load_cached_cloudflare_ip() -> Optional[str]:
    """
    Return the last known Cloudflare IP from local cache.

    This cache is a performance optimization only.
    Failure or corruption is treated as a cache miss.
    """
    try:
        data = json.loads(CLOUDFLARE_IP_FILE.read_text())
        return data.get("last_ip")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

def store_cloudflare_ip(ip: str) -> None:
    """
    Persist the current Cloudflare IP to local cache.

    Best-effort only — failures are intentionally ignored.
    """
    try:
        CLOUDFLARE_IP_FILE.write_text(
            json.dumps({"last_ip": ip}, indent=2)
        )
    except OSError:
        pass
