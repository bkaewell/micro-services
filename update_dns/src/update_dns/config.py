# ─── Future imports ───
from __future__ import annotations

# ─── Standard library imports ───
import os
from dataclasses import dataclass, field

# ─── Third-party imports ───
from dotenv import load_dotenv


# Load environment variables once at module level
load_dotenv()

@dataclass(frozen=True)
class HardwareConfig:
    """
    Hardware-specific network endpoints.

    These values identify locally managed devices.
    """
    ROUTER_IP: str = field(default_factory=lambda: os.getenv("ROUTER_IP", "192.168.0.1"))
    PLUG_IP: str = field(default_factory=lambda: os.getenv("PLUG_IP", "192.168.0.150"))

@dataclass(frozen=True)
class Config:
    """
    Top-level configuration namespace for the Network Health & DNS
    Reconciliation Agent.

    Values represent operator-tunable inputs sourced from environment
    variables with sane defaults. Policy-derived and computed values
    are intentionally defined outside this class.
    """

    # Baseline control-loop interval in seconds.
    # Actual polling cadence is derived via state-based scaling and jitter.
    CYCLE_INTERVAL_S: int = int(os.getenv("CYCLE_INTERVAL_S", "60"))

    # Maximum positive jitter added to polling intervals.
    # Used to avoid detectable periodic API access patterns (Cloudflare, etc.).
    POLLING_JITTER_S: int = 10

    # Adaptive polling scalars (multipliers applied to base interval)
    FAST_POLL_SCALAR: float = 0.5  # FASTER during DOWN/DEGRADED
    SLOW_POLL_SCALAR: float = 2.0  # SLOWER in steady-state UP

    # Maximum age before cache is considered stale (and forces re-verification)
    #MAX_CACHE_AGE_S: int = 600-900  # 10 minutes - 15 minutes
    MAX_CACHE_AGE_S: int = 3600  # 60 minutes

    # Cloudflare DNS hard limit (minimum allowed TTL)
    CLOUDFLARE_MIN_TTL_S: int = 60

    # Timeout applied to all external HTTP / DoH requests (seconds)
    API_TIMEOUT_S: int = 8 

    # Global log level for agent runtime
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Gate for performing physical recovery actions (e.g., smart plug reboot)
    ALLOW_PHYSICAL_RECOVERY: bool = (
        os.getenv("ALLOW_PHYSICAL_RECOVERY", "false").lower() in ("true", "1", "yes")
    )

    # Hardware endpoints
    Hardware: HardwareConfig = field(default_factory=HardwareConfig)

# Global singleton access (preferred usage pattern)
config = Config()
