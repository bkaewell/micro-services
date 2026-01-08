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

    def _recover_wan(self) -> bool:
        """
        Execute a physical network recovery action by power-cycling
        the smart plug connected to the router/modem.

        This function performs NO health checks.
        All validation and escalation decisions are handled upstream
        by the WAN finite state machine.

        Returns:
            True if the power-cycle command sequence completed successfully,
            False otherwise.
        """
        plug_ip = Config.Hardware.PLUG_IP
        reboot_delay = Config.Hardware.REBOOT_DELAY

        try:
            # Power OFF
            off = requests.get(
                f"http://{plug_ip}/relay/0?turn=off", timeout=Config.API_TIMEOUT
            )
            off.raise_for_status()
            self.logger.debug("Smart plug powered OFF")
            time.sleep(reboot_delay)

            # Power ON
            on = requests.get(
                f"http://{plug_ip}/relay/0?turn=on", timeout=Config.API_TIMEOUT
            )
            on.raise_for_status()
            self.logger.debug("Smart plug powered ON")
            return True

        except requests.RequestException:
            self.logger.exception("Failed to communicate with smart plug")
            return False
        except Exception:
            self.logger.exception("Unexpected error during recovery")
            return False

    def run_cycle(self) -> NetworkState:
        """
        Single evaluation and execution of one cycle from the Wartime CEO
        """

        # --- Heartbeat (local process health only) ---
        #_, dt_str = self.time.now_local()
        tlog("💚", "HEARTBEAT", "OK")

        # --- Observe ---

        # --- LAN (L2/L3) ---
        lan_ok = ping_host(self.router_ip)
        tlog(
            "🟢" if lan_ok else "🟡", 
            "ROUTER", 
            "UP" if lan_ok else "DOWN", 
            primary=f"ip={self.router_ip}"
            #compute rtt in future?
        )

        # --- WAN path probe (L4-L7) ---
        wan_probe_ok = verify_wan_reachability()
        tlog(
            "🟢" if wan_probe_ok else "🟡", 
            "WAN",
            "REACHABLE" if wan_probe_ok else "UNREACHABLE",
            primary="probe",
            #compute rtt in future?
        )

        # --- Public IP (L7) --- 
        public = get_ip()
        tlog(
            "🟢" if public.success else "🔴",
            "PUBLIC IP",
            "OK" if public.success else "FAIL",
            primary=f"ip={public.ip}",
            meta=f"rtt={public.elapsed_ms:.1f}ms | attempts={public.attempts}"
        )

        # --- Confidence building --- 
        wan_ready = (public.success and self._update_ip_stability(public))

        if public.success:
            if wan_ready:
                tlog(
                    "🟢",
                    "WAN",
                    "CONFIRMED",
                    primary=f"ip={public.ip}",
                    meta=f"confirmed={self.ip_stability_count} consecutive cycles"
                )
            else:
                tlog(
                    "🟡",
                    "WAN",
                    "WARMING",
                    primary=f"ip={public.ip}",
                    meta=f"confirmed={self.ip_stability_count}/{self.MIN_IP_STABILITY_CYCLES} consecutive cycles"
                )

        # --- Classify ---
        verdict = classify_wan(
            lan_ok=lan_ok, 
            wan_probe_ok=wan_probe_ok, 
            wan_ready=wan_ready
        )

        # --- Finite State Machine (FSM) update ---
        should_escalate = self.wan_fsm.update(verdict)

        tlog(
            "🟢" if verdict ==  WanVerdict.STABLE else "🟡",
            "WAN",
            "VERDICT",
            primary=verdict.name,
            meta=f"failures={self.wan_fsm.consec_fails}/{self.wan_fsm.max_consec_fails} | should_escalate={should_escalate}"
        )


        return NetworkState.UNKNOWN