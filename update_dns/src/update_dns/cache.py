# --- Standard library imports ---
import time
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


# --- Cache layout ---
CACHE_DIR = Path.home() / ".cache" / "update_dns"
CACHE_DIR.mkdir(parents=True, exist_ok=True) 

CLOUDFLARE_IP_FILE = CACHE_DIR / "cloudflare_ip.json"
GOOGLE_SHEET_ID_FILE = CACHE_DIR / 'google_sheet_id.txt'

@dataclass(frozen=True)
class CacheLookupResult:
    ip: Optional[str]
    elapsed_ms: float
    hit: bool

# --- Cloudflare IP cache ---
def load_cached_cloudflare_ip() -> CacheLookupResult:
    """
    Load the last known Cloudflare IP from local cache.

    This is a performance optimization only. 
    Any failure is treated as a cache miss.
    """
    start = time.monotonic()
    try:
        data = json.loads(CLOUDFLARE_IP_FILE.read_text())
        ip = data.get("last_ip")
        hit = ip is not None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        ip = None
        hit = False

    return CacheLookupResult(
        ip=ip,
        hit=hit,
        elapsed_ms=(time.monotonic() - start) * 1000,
    )

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
