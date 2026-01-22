# ─── Standard library imports ───
import time
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


# ─── Cache layout ───
CACHE_DIR = Path.home() / ".cache" / "update_dns"
CACHE_DIR.mkdir(parents=True, exist_ok=True) 

CLOUDFLARE_IP_FILE = CACHE_DIR / "cloudflare_ip.json"
GOOGLE_SHEET_ID_FILE = CACHE_DIR / 'google_sheet_id.txt'

@dataclass(frozen=True)
class CacheLookupResult:
    """
    Result of a cache lookup.

    Fields represent prior observation only — never system truth.
    """
    ip: Optional[str]
    observed_at: Optional[float]
    age_s: Optional[float]
    hit: bool
    elapsed_ms: float

def load_cached_cloudflare_ip() -> CacheLookupResult:
    """
    Load the last observed Cloudflare IP from local cache.

    This cache encodes historical observation only.
    It must never be treated as authoritative, correct, or fresh.

    Any failure or incomplete payload is treated as a cache miss.
    """
    start = time.monotonic()
    now = time.time()

    try:
        data = json.loads(CLOUDFLARE_IP_FILE.read_text())
        ip = data.get("last_ip")
        observed_at = data.get("observed_at")

        #if ip is not None and observed_at is not None:
        if ip and observed_at:
            age = now - observed_at
            hit = True
        else:
            ip = None
            observed_at = None
            age = None
            hit = False

    except (FileNotFoundError, json.JSONDecodeError, OSError):
        ip = None
        observed_at = None
        age = None
        hit = False

    return CacheLookupResult(
        ip=ip,
        observed_at=observed_at,
        age_s=age,
        hit=hit,
        elapsed_ms=(time.monotonic() - start) * 1000,
    )

def store_cloudflare_ip(ip: Optional[str]) -> None:
    """
    Persist the last observed Cloudflare IP and observation time.

    This cache is a performance optimization only. It encodes
    observation history, not correctness, validity or freshness.

    Best-effort only - write failures are intentionally ignored.
    """
    try:
        payload = {
            "last_ip": ip,
            "observed_at": time.time() if ip is not None else None,
        }
        CLOUDFLARE_IP_FILE.write_text(json.dumps(payload, indent=2))
    
    except OSError:
        pass
