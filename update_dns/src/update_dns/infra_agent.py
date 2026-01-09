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
    DEGRADED = auto()
    DOWN = auto()
    ERROR = auto()
    UNKNOWN = auto()

    @property
    def label(self) -> str:
        return {
            NetworkState.HEALTHY: "HEALTHY",
            NetworkState.DEGRADED: "DEGRADED",
            NetworkState.DOWN: "DOWN",
            NetworkState.ERROR: "ERROR",
            NetworkState.UNKNOWN: "UNKNOWN",
        }[self]

class WanHealth(Enum):
    UP = auto()        # Confirmed stable
    DEGRADED = auto()  # Reachable but not yet trusted
    DOWN = auto()      # Unreachable

HEALTH_EMOJI = {
    WanHealth.UP: "🟢",
    WanHealth.DEGRADED: "🟡",
    WanHealth.DOWN: "🔴",
}

class WanFSM:
    """
    WAN confidence state machine.

    Invariants:
      - Counts consecutive DOWN observations
      - Resets only on UP
    """

    def __init__(self, max_failure_streak: int):
        self.max_failure_streak = max_failure_streak
        self.failure_streak = 0

    def advance(self, health: WanHealth) -> bool:
        """
        Returns True if recovery escalation should trigger.
        """
        if health == WanHealth.DOWN:
            self.failure_streak += 1
            return self.failure_streak >= self.max_failure_streak

        if health == WanHealth.UP:
            self.failure_streak = 0

        # DEGRADED does not affect counters
        return False

def classify_wan(lan_ok: bool, wan_path_ok: bool, wan_trusted: bool) -> WanHealth:
    """
    Derive pure WAN health confidence from layered observations.
    """
    if not lan_ok:
        return WanHealth.DOWN

    if wan_path_ok and wan_trusted:
        return WanHealth.UP

    if wan_path_ok:
        return WanHealth.DEGRADED

    return WanHealth.DOWN

class NetworkWatchdog:
    """
    Background agent that maintains consistency between the device’s
    current public IP and its Cloudflare DNS record.

    Optimized for fast no-op cycles under normal conditions when everything's
    healthy with explicit recovery behavior on sustained failures.
    """

    def __init__(self, max_failure_streak: int = 4):
        """
        Initialize the NetworkWatchdog runtime, clients, and WAN health machinery.

        Constructor is defensive by design and must never crash the agent.
        """

        # --- Core services (time, external clients, logging) ---
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
        self.wan_fsm = WanFSM(max_failure_streak)

        # --- WAN Observation State ---
        self.last_detected_ip: Optional[str] = None   # Last observed public IP
        self.ip_stability_count: int = 0              # Consecutive identical IP detections

        # --- WAN Readiness Policy ---
        self.MIN_IP_STABILITY_CYCLES: int = 2   # Required IP stability cycles

        ##################
        # For testing only
        ##################
        self.count = 0
        self.flag = True

    def _observe_ip_consistency(self, result: IPResolutionResult) -> bool:
        """
        Track consecutive agreement of the observed public IP across cycles.

        Builds confidence that the WAN IP is no longer flapping after recovery.
        Resets immediately on resolution failure or IP change.

        Returns:
            True once the same public IP has been observed for the minimum
            required number of consecutive cycles, indicating WAN stability.
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

    def _sync_dns_if_drifted(self, public_ip: str) -> None:
        """
        Ensure authoritative DNS reflects the current stable public IP.

        Performs a layered reconciliation:
        1. Local cache (fast no-op)
        2. Authoritative DNS lookup (truth check)
        3. Provider mutation only if drift is detected

        This function is side-effecting and is intentionally invoked
        only when the WAN is confirmed stable.
        """

        # --- L1 Cache (Cheap, local, fast no-op) ---
        cache = load_cached_cloudflare_ip()
        cache_match = cache.hit and cache.ip == public_ip

        tlog(
            "🟢" if cache_match else "🟡",
            "CACHE",
            "HIT" if cache_match else "MISS",
            primary=f"ip={cache.ip}",
            meta=f"rtt={cache.elapsed_ms:.1f}ms"
        )

        if cache_match:
            return  # Fast no-op

        # --- L2 DoH (Authoritative DNS, external truth) ---
        doh = doh_lookup(self.cloudflare_client.dns_name)

        if doh.success and doh.ip == public_ip:
            tlog(
                "🟢",
                "DNS",
                "OK",
                primary=f"ip={doh.ip}",
                meta=f"rtt={doh.elapsed_ms:.1f}ms"
            )
            store_cloudflare_ip(public_ip)   # Refresh cache
            return

        # --- Mutation required ---
        result = self.cloudflare_client.update_dns(public_ip)
        store_cloudflare_ip(public_ip)
        dns_last_modified = \
            self.time.iso_to_local_string(result.get("modified_on"))
        tlog(
            "🟢",
            "DNS",
            "UPDATED",
            primary="provider=Cloudflare",
            meta=f"{doh.ip} → {public_ip} | modified={dns_last_modified}"
        )

        # --- Low-frequency audit log ---
        gsheets_ok = self.gsheets_service.update_status(
                ip_address=public_ip,
                current_time=None,
                dns_last_modified=dns_last_modified
        )
        if gsheets_ok:
            tlog("🟢", "GSHEET", "OK", primary="audit dns update")

    def _power_cycle_edge(self) -> bool:
        """
        Execute a physical recovery by power-cycling the network edge device.

        Performs no validation or health assessment.
        All escalation decisions are handled upstream by the WAN FSM.

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

    def _escalate_recovery(self) -> None:
        """
        Execute the configured WAN recovery escalation strategy.

        Currently implemented as a physical power-cycle of the network edge.
        """

        tlog("🔴", "RECOVERY", "TRIGGER", primary="power-cycle router/modem")

        success = self._power_cycle_edge()

        tlog(
            "🟢" if success else "🔴",
            "RECOVERY",
            "OK" if success else "FAIL",
            primary="recovery attempt complete"
        )   


    #********************************
    #********************************
    #********************************
    #********************************
    #********************************
    def _override_public_ip_for_test(
        self,
        public: IPResolutionResult,
    ) -> IPResolutionResult:
        
        if self.count % 3 == 0:
            self.flag = not self.flag
        
        if self.flag:
            return IPResolutionResult(
                ip="192.168.0.77",
                elapsed_ms=public.elapsed_ms,
                attempts=public.attempts,
                success=True,
            )
        
        return public

    #********************************
    #********************************
    #********************************
    #********************************
    #********************************


    def evaluate_cycle(self) -> NetworkState:
        """
        Execute a single watchdog evaluation cycle.

        Observes LAN/WAN signals, updates WAN health via FSM,
        performs gated side-effects (DNS sync, recovery),
        and returns the resulting high-level network state.
        """

        # --- Heartbeat (local process health only) ---
        _, dt_str = self.time.now_local()
        tlog("💚", "HEARTBEAT", "OK")

        # --- Observe ---

        # --- LAN (L2/L3) ---
        lan_ok = ping_host(self.router_ip)
        tlog(
            "🟢" if lan_ok else "🔴", 
            "ROUTER", 
            "UP" if lan_ok else "DOWN", 
            primary=f"ip={self.router_ip}"
            #compute rtt in future?
        )

        # --- WAN path probe (L4-L7) ---
        wan_path_ok = verify_wan_reachability()
        tlog(
            "🟢" if wan_path_ok else "🔴", 
            "WAN",
            "PATH",
            primary="OK" if wan_path_ok else "FAIL"
            #compute rtt in future?
        )

        # --- Public IP (L7) --- 
        public = get_ip()

        #********************************
        #********************************
        #********************************
        #public = self._override_public_ip_for_test(public)  
        #self.count += 1
        #********************************
        #********************************
        #********************************

        tlog(
            "🟢" if public.success else "🔴",
            "PUBLIC IP",
            "OK" if public.success else "FAIL",
            primary=f"ip={public.ip}",
            meta=f"rtt={public.elapsed_ms:.1f}ms | attempts={public.attempts}"
        )

        # --- Confidence building --- 
        wan_trusted = (public.success and self._observe_ip_consistency(public))

        # --- Classify ---
        wan_health = classify_wan(
            lan_ok=lan_ok, 
            wan_path_ok=wan_path_ok, 
            wan_trusted=wan_trusted
        )

        # --- Advance the Finite State Machine (FSM) ---
        escalate = self.wan_fsm.advance(wan_health)

        emoji = HEALTH_EMOJI[wan_health]
        meta = []

        if wan_health == WanHealth.UP:
            meta.append(
                f"uptime={self.ip_stability_count} loops"
            )

        if wan_health == WanHealth.DEGRADED:
            meta.append(
                f"confidence={self.ip_stability_count}/{self.MIN_IP_STABILITY_CYCLES} consecutive loops"
            )

        if wan_health == WanHealth.DOWN:
            meta.append(
                f"failures={self.wan_fsm.failure_streak}/{self.wan_fsm.max_failure_streak} loops"
            )

        meta.append(f"escalate={escalate}")

        tlog(
            emoji,
            "WAN",
            "HEALTH",
            primary=wan_health.name,
            meta=" | ".join(meta)
        )

        # --- Act (Final state mapping) ---
        if not lan_ok:
            return NetworkState.DOWN

        if wan_health == WanHealth.UP:
            assert public.success and public.ip, "UP WAN requires valid public IP"
            self._sync_dns_if_drifted(public.ip)

            # --- High-frequency heartbeat (timestamp) to Google Sheet ---
            gsheets_ok = self.gsheets_service.update_status(
                ip_address=None,  # No change
                current_time=dt_str,
                dns_last_modified=None   # No change
            )
            if gsheets_ok:
                tlog("🟢", "GSHEET", "OK")

            return NetworkState.HEALTHY
        
        if wan_health == WanHealth.DEGRADED:
            return NetworkState.DEGRADED
        
        # DOWN
        if wan_health == WanHealth.DOWN:
            if self.watchdog_enabled and escalate:
                self._escalate_recovery()
            return NetworkState.DOWN

        return NetworkState.UNKNOWN
