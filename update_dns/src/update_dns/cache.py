# ─── Standard library imports ───
import os
import time
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


def get_cache_dir() -> Path:
    """
    Automatically detect runtime environment and return appropriate cache directory.

    - Local/host: ~/.cache/update_dns/
    - Docker/container: /app/cache/update_dns/ (volume-mounted)
    """
    # Docker detection: presence of /.dockerenv file (most reliable)
    is_docker = os.path.exists('/.dockerenv')

    # Fallback: check for common container env vars
    if not is_docker:
        is_docker = any(
            key in os.environ
            for key in ('DOCKER_CONTAINER', 'CONTAINER_ID', 'KUBERNETES_SERVICE_HOST')
        )

    if is_docker:
        # Fixed path inside container – must be volume-mounted in docker-compose
        return Path("/app/cache/update_dns")
    else:
        # Local development / host
        return Path.home() / ".cache" / "update_dns"

# ─── Cache layout (persistent storage) ───
CACHE_DIR = get_cache_dir()
CACHE_DIR.mkdir(parents=True, exist_ok=True) 

CLOUDFLARE_IP_FILE = CACHE_DIR / "cloudflare_ip.json"
GOOGLE_SHEET_ID_FILE = CACHE_DIR / 'google_sheet_id.txt'
UPTIME_FILE = CACHE_DIR / "uptime.json"

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

@dataclass
class Uptime:
    """
    Tracks cumulative uptime based on observed healthy states.

    - total:    number of measurement points (control cycles)
    - up:       number of those points where the network was healthy (UP)
    - last_update: timestamp of most recent write (monotonic time)
    """
    total: int = 0
    up: int = 0
    last_update: float = 0.0

    @property
    def percentage(self) -> float:
        """Current uptime percentage (0.0 - 100.0)"""
        return (self.up / self.total * 100) if self.total > 0 else 0.0

    def __str__(self) -> str:
        return f"{self.percentage:.2f}% ({self.up}/{self.total})"


def load_uptime() -> Uptime:
    """
    Load previously persisted uptime counters.

    Returns a fresh Uptime object (0/0) if the file is missing,
    corrupted, or unreadable. Failures are silent.
    """
    now = time.time()

    try:
        data = json.loads(UPTIME_FILE.read_text())
        return Uptime(
            total=data.get("total", 0),
            up=data.get("up", 0),
            last_update=data.get("last_update", now)
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return Uptime()

def store_uptime(uptime: Uptime) -> None:
    """
    Persist current uptime counters to disk.

    Best-effort operation — failures are ignored to avoid
    impacting the main control loop. The file survives container
    restarts if the cache directory is volume-mounted.
    """
    now = time.time()

    try:
        payload = {
            "total": uptime.total,
            "up": uptime.up,
            "last_update": now
        }
        UPTIME_FILE.write_text(json.dumps(payload, indent=2))
    except OSError:
        pass
