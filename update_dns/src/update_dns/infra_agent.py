# --- Standard library imports ---
import time
from enum import Enum, auto
from typing import Optional

# --- Third-party imports ---
import requests

# --- Project imports ---
from .config import Config
from .telemetry import tlog
from .logger import get_logger
from .time_service import TimeService
from .cloudflare import CloudflareClient
from .gsheets_service import GSheetsService
from .cache import load_cached_cloudflare_ip, store_cloudflare_ip
from .utils import ping_host, verify_wan_reachability, get_ip, doh_lookup, IPResolutionResult
#from .db import log_metrics


class NetworkState(Enum):
    HEALTHY = auto()
    ROUTER_DOWN = auto()
    WAN_WARMING = auto()
    WAN_DOWN = auto()
    ERROR = auto()
    UNKNOWN = auto()

    @property
    def label(self) -> str:
        return {
            NetworkState.HEALTHY: "WAN_CONFIRMED",
            NetworkState.ROUTER_DOWN: "LAN_UNREACHABLE",
            NetworkState.WAN_WARMING: "WAN_CONFIRMING",
            NetworkState.WAN_DOWN: "WAN_UNREACHABLE",
            NetworkState.ERROR: "INTERNAL_ERROR",
            NetworkState.UNKNOWN: "STATE_UNKNOWN",
        }[self]

class WanVerdict(Enum):
    STABLE = auto()
    WARMING = auto()
    UNREACHABLE = auto()

class WanFSM:
    """
    WAN confidence state machine.

    Invariants:
      - consec_fails increments only on UNREACHABLE verdicts
      - consec_fails resets only on STABLE verdicts
      - FSM does not perform network I/O — only reasons about results
    """

    def __init__(self, max_consec_fails: int):
        self.max_consec_fails = max_consec_fails
        self.consec_fails = 0

    def update(self, verdict: WanVerdict) -> bool:
        """
        Apply a WAN verdict for this cycle.

        Returns:
            True if recovery escalation should trigger.
        """
        if verdict == WanVerdict.UNREACHABLE:
            self.consec_fails += 1
            return self.consec_fails >= self.max_consec_fails

        if verdict == WanVerdict.STABLE:
            self.consec_fails = 0

        # WARMING intentionally does not mutate counters
        return False

def classify_wan(
    lan_ok: bool,
    wan_probe_ok: bool,
    wan_ready: bool
) -> WanVerdict:
    """
    Derive WAN confidence verdict from layered observations.

    Module level pure logic (No side effects.)
    """
    if not lan_ok:
        return WanVerdict.UNREACHABLE

    if wan_probe_ok and wan_ready:
        return WanVerdict.STABLE

    if wan_probe_ok:
        return WanVerdict.WARMING

    return WanVerdict.UNREACHABLE

class NetworkWatchdog:
    """
    Background agent that maintains consistency between the device’s
    current public IP and its Cloudflare DNS record.

    Optimized for fast no-op cycles under normal conditions when everything's
    healthy with explicit recovery behavior on sustained failures.
    """

    def __init__(self, max_consec_fails=4):

        # Initialize time, clients, logs, and benchmark timing
        self.time = TimeService()
        self.cloudflare_client = CloudflareClient()
        self.gsheets_service = GSheetsService()
        self.logger = get_logger("infra_agent")

        # --- Cloudflare IP Cache Priming (authoritative DNS over HTTPS (DoH) ---
        try:

            doh = doh_lookup(self.cloudflare_client.dns_name)

            if doh.success and doh.ip:
                store_cloudflare_ip(doh.ip)
                self.logger.info(
                    "Cloudflare L1 cache initialized via DoH | "
                    f"ip={doh.ip} rtt={doh.elapsed_ms:.1f}ms"
                )
            else:
                # DoH completed but returned no usable IP
                store_cloudflare_ip("__INIT__")
                self.logger.warning(
                    "Cloudflare L1 cache not initialized via DoH | "
                    f"success={doh.success} "
                    f"rtt={doh.elapsed_ms:.1f}ms"
                )

        except Exception as e:
            # Defensive fallback: init must never crash the agent
            store_cloudflare_ip("")
            self.logger.error(
                "Cloudflare L1 cache init failed | "
                f"error={type(e).__name__}: {e}"
            )

        # --- Configuration (static) ---
        self.router_ip = Config.Hardware.ROUTER_IP        # Local router gateway IP
        self.watchdog_enabled = Config.WATCHDOG_ENABLED   # Enable recovery actions

        # --- WAN Failure Policy ---
        self.wan_fsm = WanFSM(max_consec_fails)

        # --- WAN Observation State ---
        self.last_detected_ip: Optional[str] = None   # Last observed public IP
        self.ip_stability_count: int = 0              # Consecutive identical IP detections

        # --- WAN Readiness Policy ---
        self.MIN_IP_STABILITY_CYCLES: int = 2   # Required IP stability cycles

        ##################
        # For testing only
        ##################
        self.count = 0

    def _update_ip_stability(self, result: IPResolutionResult) -> bool:
        """
        Update WAN IP stability across cycles.
        Returns True once WAN is considered stable.
        """

        if not result.success:
            self.ip_stability_count = 0
            self.last_detected_ip = None
            return False

        ip = result.ip  # success guarantees validity

        if ip == self.last_detected_ip:
            self.ip_stability_count += 1
        else:
            self.ip_stability_count = 1
            self.last_detected_ip = ip

        return self.ip_stability_count >= self.MIN_IP_STABILITY_CYCLES



