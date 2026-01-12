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

class WanState(Enum):
    UP = auto()        # Confirmed stable
    DEGRADED = auto()  # Reachable but not yet trusted
    DOWN = auto()      # Unreachable

WAN_HEALTH_EMOJI = {
    WanState.UP: "🟢",
    WanState.DEGRADED: "🟡",
    WanState.DOWN: "🔴",
}

class WanFSM:
    """
    Pure WAN health finite-state machine.

    Responsibilities:
    - Classify WAN health from raw signals
    - Enforce DOWN → DEGRADED → UP promotion
    - Reset confidence on any failure

    Non-responsibilities:
    - No recovery actions
    - No timers
    - No side effects
    """

    def __init__(self, promotion_threshold: int = 2):
        self.state: WanState = WanState.DOWN
        self.promotion_threshold = promotion_threshold
        self.good_observation_count = 0

    def _enter_down(self) -> None:
        self.state = WanState.DOWN
        self.good_observation_count = 0

    def transition(
        self,
        lan_ok: bool,
        wan_path_ok: bool,
        public_ok: bool,
        allow_promotion: bool = True,
    ) -> WanState:
        """
        Transition WAN state from strongest observed signals. 
        Weak: LAN (currently omitted) 
        Strong: WAN
        Strongest: Public IP
        Promotion to UP is gated by allow_promotion.
        """

        # # Any failure immediately collapses confidence
        # if not lan_ok or not wan_path_ok or not public_ok:
        #     self._enter_down()
        #     return self.state

        # Strong WAN evidence overrides LAN probe noise
        if wan_path_ok and public_ok:
            self.good_observation_count += 1

            if self.state == WanState.DOWN:
                self.state = WanState.DEGRADED

            elif (
                self.state == WanState.DEGRADED
                and self.good_observation_count >= self.promotion_threshold
                and allow_promotion
            ):
                self.state = WanState.UP

            return self.state
    
        # True failure paths
        self._enter_down()
        return self.state

class NetworkControlAgent:
    """
    Autonomous background agent that monitors LAN/WAN health and maintains
    consistency between the device's public IP and its Cloudflare DNS record.

    The agent is optimized for fast, low-noise no-op cycles under healthy
    conditions and performs explicit recovery actions only after sustained
    failure is confirmed by policy.

    Responsibilities:
        - Observe local router, WAN reachability, and public IP state
        - Build confidence in WAN stability across cycles
        - Detect and reconcile DNS drift with Cloudflare
        - Escalate recovery actions via a finite state machine
        - Expose a single NetworkState result per evaluation cycle
    """

    def __init__(self):
        """
        Initialize the NetworkControlAgent runtime, policies, and observation state.

        The agent is designed to be resilient at startup: initialization failures
        are logged but do not prevent execution.
        """

        # --- Core services (pure dependencies) --- 
        self.time = TimeService()
        self.cloudflare_client = CloudflareClient()
        self.gsheets_service = GSheetsService()
        # Future work - add notifications via Telegram API
        self.logger = get_logger("infra_agent")

        # --- Static configuration ---
        self.router_ip = Config.Hardware.ROUTER_IP
        self.allow_physical_recovery = Config.ALLOW_PHYSICAL_RECOVERY

        # --- WAN promotion policy (health → trust) ---
        self.WAN_PROMOTION_CYCLES = 2   # DEGRADED → UP requires N clean observations
        self.MAX_CONSECUTIVE_FAILS = 4  # Escalation threshold

        self.wan_fsm = WanFSM(
            promotion_threshold=self.WAN_PROMOTION_CYCLES
        )

        # --- WAN observation state (cross-cycle memory) ---
        self.last_wan_state: Optional[WanState] = None
        self.consecutive_fails: int = 0

        # IP stability (used ONLY during WAN DEGRADED)
        self.last_public_ip: Optional[str] = None
        self.ip_stability_count: int = 0        

        # --- Telemetry / epochs ---
        self.wan_epoch: int = 0

        # --- startup priming ---
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

    def _update_ip_stability(self, public_ip: Optional[str]) -> bool:
        """
        Track whether public IP is stable across consecutive cycles.
        Used ONLY during WAN DEGRADED promotion.
        """

        if not public_ip:
            self.ip_stability_count = 0
            self.last_public_ip = None
            return False

        if public_ip == self.last_public_ip:
            self.ip_stability_count += 1
        else:
            self.ip_stability_count = 1
            self.last_public_ip = public_ip

        return self.ip_stability_count >= self.WAN_PROMOTION_CYCLES

    def _on_wan_down_transition(self):
        """
        TBD
        """
        self.wan_epoch += 1
        #self.ip_good_observation_count = 0
        self.ip_stability_count = 0
        self.last_public_ip = None

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

    def _trigger_physical_recovery(self) -> bool:
        """
        Trigger a WAN recovery action after policy-driven escalation.

        Currently implemented as a physical power-cycle of the network edge.

        Returns:
            bool: True if recovery action was successfully executed.
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

        # if success:
        #     # --- CRITICAL RESET ---
        #     # Recovery breaks trust, even if IP remains unchanged
        #     # Enforce re-promotion of WAN (DOWN → DEGRADED → UP)           
        #     self.wan_fsm.failure_streak = 0
        #     self.ip_consistency_count = 0
        #     #self.last_observed_ip = None        

        plug_ok_after = ping_host(plug_ip)

        tlog(
            "🟢" if success else "🔴",
            "RECOVERY",
            "OK" if success else "FAIL",
            primary="recovery attempt complete",
            meta=f"plug_pre_toggle={plug_ok} | plug_post_toggle={plug_ok_after}"
        )

        return success


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


    def run_control_cycle(self) -> NetworkState:
        """
        Execute a single control loop:
            Observe → Assess → Decide → Act → Report
        """

        # --- Heartbeat (process liveness only) ---
        _, dt_str = self.time.now_local()
        tlog("💚", "HEARTBEAT", "OK")

        # ---OBSERVE ---
        # --- LAN ---
        lan_ok = ping_host(self.router_ip)
        tlog(
            "🟢" if lan_ok else "🔴",
            "ROUTER",
            "UP" if lan_ok else "DOWN",
            primary=f"ip={self.router_ip}"
        )

        # --- WAN path ---
        wan_path_ok = verify_wan_reachability()
        tlog(
            "🟢" if wan_path_ok else "🔴",
            "WAN",
            "PATH",
            primary="OK" if wan_path_ok else "FAIL"
        )

        # --- Public IP ---
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

        # --- ASSESS (FSM owns health) ---

        # Determine whether promotion (DEGRADED → UP) is allowed
        allow_promotion = True

        if self.wan_fsm.state == WanState.DEGRADED:
            allow_promotion = self._update_ip_stability(public.ip)

        wan_state = self.wan_fsm.transition(
            lan_ok=lan_ok,
            wan_path_ok=wan_path_ok,
            public_ok=public.success,
            allow_promotion = allow_promotion,
        )

        # Detect first transition into DOWN (telemetry hook)
        if wan_state == WanState.DOWN and self.last_wan_state != WanState.DOWN:
            self._on_wan_down_transition()

        self.last_wan_state = wan_state

        # --- DECIDE (policy & escalation) ---
        if wan_state == WanState.DOWN:
            self.consecutive_fails += 1
        else:
            self.consecutive_fails = 0

        escalate = (
            wan_state == WanState.DOWN
            and self.consecutive_fails >= self.MAX_CONSECUTIVE_FAILS
        )

        # --- REPORT (telemetry) ---
        meta = []
        if wan_state == WanState.UP:
            meta.append(f"confidence={self.wan_fsm.good_observation_count} loops")
        elif wan_state == WanState.DEGRADED:
            meta.append(
                f"confidence={self.wan_fsm.good_observation_count}/"
                f"{self.wan_fsm.promotion_threshold} observations"
            )
        elif wan_state == WanState.DOWN:
            meta.append(f"failures={self.consecutive_fails}/{self.MAX_CONSECUTIVE_FAILS}")
            meta.append(f"escalate={escalate}")

        tlog(
            WAN_HEALTH_EMOJI[wan_state],
            "WAN",
            "STATE",
            primary=wan_state.name,
            meta=" | ".join(meta)
        )

        # --- ACT (side effects) ---
        if not lan_ok:
            return NetworkState.DOWN   # ??????

        if wan_state == WanState.UP:
            assert public.success and public.ip, "UP WAN requires valid public IP"

            self._sync_dns_if_drifted(public.ip)

            # High-frequency uptime heartbeat
            if self.gsheets_service.update_status(
                ip_address=None,
                current_time=dt_str,
                dns_last_modified=None
            ):
                tlog("🟢", "GSHEET", "OK")

            return NetworkState.HEALTHY

        if wan_state == WanState.DEGRADED:
            return NetworkState.DEGRADED

        # --- WAN DOWN ---
        if escalate and self.allow_physical_recovery:
            recovery_ok = self._trigger_physical_recovery()

            if recovery_ok:
                # CRITICAL:
                # Successful recovery prevents rapid re-trigger loops
                self.consecutive_fails = 0
 
        elif escalate:
            tlog(
                "🟡",
                "RECOVERY",
                "SUPPRESSED",
                primary="physical recovery disabled",
                meta="failure threshold reached"
            )

        return NetworkState.DOWN

