

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


# ─── Load environment variables once at module level ───
load_dotenv()


@dataclass(frozen=True)
class HardwareConfig:
    """Hardware-specific endpoints and timing constants."""
    ROUTER_IP: str = field(default_factory=lambda: os.getenv("ROUTER_IP", "192.168.0.1"))
    PLUG_IP: str = field(default_factory=lambda: os.getenv("PLUG_IP", "192.168.0.150"))

    REBOOT_DELAY_S: int = int(os.getenv("REBOOT_DELAY_S", "30"))
    RECOVERY_COOLDOWN_S: int = int(os.getenv("RECOVERY_COOLDOWN_S", "1800"))

@dataclass(frozen=True)
class Config:
    """
    Top-level configuration namespace for the Network Health & DNS Reconciliation Agent.

    All user-tunable values are sourced from .env (with sane defaults).
    Non-configurable constants are defined inline.
    """

    # ─── Scheduling & Polling ─── 
    CYCLE_INTERVAL_S: int = int(os.getenv("CYCLE_INTERVAL_S", "65"))

    # Jitter added to each interval to make polling appear human-like
    # Helps avoid Cloudflare rate limiting patterns
    POLLING_JITTER_S: int = 5

    # Adaptive polling scalars (multipliers applied to base interval)
    FAST_POLL_SCALAR: float = 0.5  # ~2x faster during DOWN/DEGRADED
    SLOW_POLL_SCALAR: float = 2.0  # ~2x slower in steady state (UP)

    # Whether to enforce minimum TTL safety during DNS updates
    ENFORCE_TTL_POLICY: bool = os.getenv("ENFORCE_TTL_POLICY", "true").lower() in ("true", "1", "yes")

    # ─── DNS & Cache Policy (freshness & reconciliation behavior) ───
    # Maximum age before cache is considered stale and forces re-verification
    # Chosen to cover ~5 slow UP cycles (~120s) while expiring quickly enough during fast recovery (~30s)
    #MAX_CACHE_AGE_S: int = 600  # 10 minutes
    MAX_CACHE_AGE_S: int = 3600  # 60 minutes

    # ─── Cloudflare / DNS constraints (hard limits) ─── 
    CLOUDFLARE_MIN_TTL_S: int = 60

    # ─── Network I/O & safety (timesouts, throttling) ───
    API_TIMEOUT_S: int = 8  # Safe timeout for all external HTTP/DoH calls

    # ─── Observability (logging & monitoring) ───
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # ─── Recovery & Safety (physical actions & guardrails) ───
    ALLOW_PHYSICAL_RECOVERY: bool = os.getenv("ALLOW_PHYSICAL_RECOVERY", "false").lower() in ("true", "1", "yes")

    # ─── Hardware settings (physical endpoints & timing) ───
    Hardware: HardwareConfig = field(default_factory=HardwareConfig)

# Global singleton access (preferred usage pattern)
config = Config()
