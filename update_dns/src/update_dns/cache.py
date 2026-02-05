# ─── Standard library imports ───
import os
import time
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


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

@dataclass
class Uptime:
    """
    Rolling uptime counters from control-loop observations.

    • total — cycles observed
    • up    — cycles in READY state
    """
    total: int = 0
    up: int = 0
    last_update: float = 0.0

    @property
    def percentage(self) -> float:
        return (self.up / self.total * 100) if self.total > 0 else 0.0

    def __str__(self) -> str:
        return f"{self.percentage:.2f}% ({self.up}/{self.total})"

class PersistentCache:
    """
    Filesystem-backed cache for low-frequency control-plane state.

    Purpose:
    • Avoid redundant external calls (DNS, APIs)
    • Preserve low-frequency state across restarts
    • Improve stability without adding correctness risk

    Design:
    • Best-effort only (never blocks control loop)
    • Encodes observation history, never truth
    • Safe to delete at any time (rebuilds automatically)
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize cache storage.

        • Auto-detects runtime (host vs container) if no path is provided
        • Ensures cache directory exists
        • Performs no validation or I/O beyond setup
        """
        self.cache_dir = base_dir or self._detect_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.cloudflare_ip_file = self.cache_dir / "cloudflare_ip.json"
        self.uptime_file = self.cache_dir / "uptime.json"
        #self.gsheet_file = self.cache_dir / "google_sheet_id.txt"

    @staticmethod
    def _detect_cache_dir() -> Path:
        """
        Resolve cache directory based on runtime environment.

        • Local: ~/.cache/cloudflare_verified_ddns/
        • Docker: /app/cache/cloudflare_verified_ddns/ (expected volume-mounted)
        """
        is_docker = os.path.exists("/.dockerenv") or any(
            key in os.environ
            for key in ("DOCKER_CONTAINER", "CONTAINER_ID", "KUBERNETES_SERVICE_HOST")
        )

        if is_docker:
            return Path("/app/cache/cloudflare_verified_ddns")
        else:
            return Path.home() / ".cache" / "cloudflare_verified_ddns"

    def load_cloudflare_ip(self) -> CacheLookupResult:
        """
        Load last observed Cloudflare DNS IP.

        • Observation only — never authoritative
        • Any failure is treated as a cache miss
        • Used strictly as a performance optimization
        """
        start = time.monotonic()
        now = time.time()

        try:
            data = json.loads(self.cloudflare_ip_file.read_text())
            ip = data.get("last_ip")
            observed_at = data.get("observed_at")

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
    
    def store_cloudflare_ip(self, ip: Optional[str]) -> None:
        """
        Persist last observed Cloudflare DNS IP.

        • Best-effort write
        • Failures are intentionally ignored
        """
        try:
            payload = {
                "last_ip": ip,
                "observed_at": time.time() if ip is not None else None,
            }
            self.cloudflare_ip_file.write_text(json.dumps(payload, indent=2))
        except OSError:
            pass

    def load_uptime(self) -> Uptime:
        """
        Load persisted uptime counters.

        • Missing/corrupt data returns zeroed counters
        • Startup must never fail due to metrics
        """
        now = time.time()

        try:
            data = json.loads(self.uptime_file.read_text())
            return Uptime(
                total=data.get("total", 0),
                up=data.get("up", 0),
                last_update=data.get("last_update", now),
            )
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return Uptime()

    def store_uptime(self, uptime: Uptime) -> None:
        """
        Persist current uptime counters to disk.

        • Best-effort
        • Metrics only — never impacts control flow
        """
        try:
            payload = {
                "total": uptime.total,
                "up": uptime.up,
                "last_update": time.time(),
            }
            self.uptime_file.write_text(json.dumps(payload, indent=2))
        except OSError:
            pass
