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
        self.escalation_fired = False

    def advance(self, health: WanHealth) -> bool:
        """
        Advance WAN failure state.

        Returns True only once per outage when escalation should trigger.
        """
        if health == WanHealth.DOWN:
            self.failure_streak += 1

            if (
                self.failure_streak >= self.max_failure_streak
                and not self.escalation_fired
            ):
                self.escalation_fired = True
                return True

            return False

        # Any non-DOWN state resets failure tracking
        self.failure_streak = 0
        self.escalation_fired = False
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
    Autonomous background agent that monitors LAN/WAN health and maintains
    consistency between the device's public IP and its Cloudflare DNS record.

    The watchdog is optimized for fast, low-noise no-op cycles under healthy
    conditions and performs explicit recovery actions only after sustained
    failure is confirmed by policy.

    Responsibilities:
        - Observe local router, WAN reachability, and public IP state
        - Build confidence in WAN stability across cycles
        - Detect and reconcile DNS drift with Cloudflare
        - Escalate recovery actions via a finite state machine
        - Expose a single NetworkState result per evaluation cycle
    """

    def __init__(self, max_failure_streak: int = 4):
        """
        Initialize the NetworkWatchdog runtime, policies, and observation state.

        Startup is defensive by design: failures during initialization are logged
        but never prevent the agent from running.
        """

        # --- Core services (time, external clients, logging) ---
        self.time = TimeService()
        self.cloudflare_client = CloudflareClient()
        self.gsheets_service = GSheetsService()
        self.logger = get_logger("infra_agent")

        # --- Static configuration ---
        self.router_ip = Config.Hardware.ROUTER_IP        # Local router gateway IP
        self.watchdog_enabled = Config.WATCHDOG_ENABLED   # Enable recovery actions

        # --- WAN health policy (finite state machine) ---
        self.wan_fsm = WanFSM(max_failure_streak=max_failure_streak)

        # --- WAN observation state (cross-cycle memory) ---
        self.last_observed_ip: Optional[str] = None
        self.ip_consistency_count: int = 0

        # --- WAN trust thresholds ---
        self.MIN_IP_CONSISTENCY_CYCLES: int = 2

        # --- DNS cache priming (authoritative truth via DoH ---
        self._prime_dns_cache()

        ##################
        # For testing only
        ##################
        self.count = 0
        self.flag = True

    def _prime_dns_cache(self) -> None:
        """
        Prime the local DNS cache using authoritative DNS over HTTPS (DoH).

        This establishes an initial baseline for DNS drift detection.
        Failures are tolerated and never block agent startup.
        """
        try:

            doh = doh_lookup(self.cloudflare_client.dns_name)

            if doh.success and doh.ip:
                store_cloudflare_ip(doh.ip)
                self.logger.info(
                    "DNS cache primed via DoH | "
                    f"ip={doh.ip} rtt={doh.elapsed_ms:.1f}ms"
                )
            else:
                store_cloudflare_ip("__INIT__")
                self.logger.warning(
                    "DNS cache not primed | "
                    f"success={doh.success} "
                    f"rtt={doh.elapsed_ms:.1f}ms"
                )
    
        except Exception as e:
            store_cloudflare_ip("")
            self.logger.error(
                f"DNS cache priming failed | error={type(e).__name__}: {e}"
            )

    def _observe_ip_consistency(self, result: IPResolutionResult) -> bool:
        """
        Track public IP consistency across cycles to determine WAN stability.

        Returns True once the same public IP has been observed for the minimum
        number of required cycles, indicating a stable WAN state.
        """

        if not result.success:
            self.ip_consistency_count = 0
            self.last_observed_ip = None
            return False

        ip = result.ip

        if ip == self.last_observed_ip:
            self.ip_consistency_count += 1
        else:
            self.ip_consistency_count = 1
            self.last_observed_ip = ip

        return self.ip_consistency_count >= self.MIN_IP_CONSISTENCY_CYCLES

    def _sync_dns_if_drifted(self, public_ip: str) -> None:
        """
        Reconcile Cloudflare DNS if the authoritative record differs from
        the current public IP.

        Uses a layered approach:
        1. Local cache (fast no-op)
        2. Authoritative DoH lookup (truth check)
        3. Provider mutation only if drift is detected

        This function is idempotent and and safe to call repeatedly 
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
        Execute a physical recovery action by power-cycling the network edge 
        device via a smart plug.

        This function performs no health checks and makes no policy decisions.
        All escalation logic is handled by the WAN finite state machine.

        Returns:
            True if the power-cycle command sequence completed successfully,
            False otherwise.
        """

        plug_ip = Config.Hardware.PLUG_IP
        reboot_delay = Config.Hardware.REBOOT_DELAY

        try:
            # Power OFF
            off = requests.get(
                f"http://{plug_ip}/relay/0?turn=off", 
                timeout=Config.API_TIMEOUT
            )
            off.raise_for_status()
            self.logger.debug("Smart plug powered OFF")

            time.sleep(reboot_delay)

            # Power ON
            on = requests.get(
                f"http://{plug_ip}/relay/0?turn=on", 
                timeout=Config.API_TIMEOUT
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
        Trigger a WAN recovery action after policy-driven escalation.

        Currently implemented as a physical power-cycle of the network edge.
        """

        plug_ip = Config.Hardware.PLUG_IP
        sleep = Config.Hardware.REBOOT_DELAY

        tlog(
            "🔴", 
            "RECOVERY", 
            "TRIGGER", 
            primary="power-cycle edge device",
            meta=f"sleep={sleep}s"
        )
    
        plug_ok = ping_host(plug_ip)

        tlog(
            "🟡",
            "EDGE",
            "COMMAND",
            primary="plug-relay toggle",
            meta=f"plug_ip={plug_ip}"
        )

        success = self._power_cycle_edge()

        if success:
            # --- CRITICAL RESET ---
            # Recovery breaks trust, even if IP remains unchanged
            # Enforce re-promotion of WAN (DOWN → DEGRADED → UP)           
            self.wan_fsm.failure_streak = 0
            self.ip_consistency_count = 0
            self.last_observed_ip = None        

        plug_ok_after = ping_host(plug_ip)

        tlog(
            "🟢" if success else "🔴",
            "RECOVERY",
            "OK" if success else "FAIL",
            primary="recovery attempt complete",
            meta=f"plug_pre_toggle={plug_ok} | plug_post_toggle={plug_ok_after}"
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
        Execute a single observation, classification, and action cycle.

        This method:
            - Observes LAN, WAN, and public IP state
            - Classifies WAN health using confidence and FSM policy
            - Reconciles DNS when WAN is confirmed stable
            - Escalates recovery actions on sustained failure

        Returns:
            A NetworkState representing the overall network condition
            for this evaluation cycle.
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
                f"uptime={self.ip_consistency_count} loops"
            )
            meta.append(f"escalate={escalate}")

        if wan_health == WanHealth.DEGRADED:
            meta.append(
                f"confidence={self.ip_consistency_count}/{self.MIN_IP_CONSISTENCY_CYCLES} observations"
            )
            meta.append(f"escalate={escalate}")

        if wan_health == WanHealth.DOWN:
            # meta.append(
            #     f"failures={self.wan_fsm.failure_streak}/{self.wan_fsm.max_failure_streak} loops"
            # )
            meta.append(f"failures={self.wan_fsm.failure_streak}")
            meta.append(f"threshold={self.wan_fsm.max_failure_streak}")
            meta.append(f"escalate={escalate}")
            meta.append(f"escalated={self.wan_fsm.escalation_fired}")

        #meta.append(f"escalate={escalate}")

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
            if escalate and self.watchdog_enabled:
                self._escalate_recovery()

            if escalate and not self.watchdog_enabled:
                tlog(
                    "🟡",
                    "RECOVERY",
                    "SUPPRESSED",
                    primary="watchdog disabled",
                    meta="escalation threshold reached"
                )

            return NetworkState.DOWN

        return NetworkState.UNKNOWN
