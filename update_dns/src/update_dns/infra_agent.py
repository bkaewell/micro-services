# --- Standard library imports ---
from enum import Enum, auto
from typing import Optional

# --- Project imports ---
from .config import Config
from .telemetry import tlog
from .logger import get_logger
from .time_service import TimeService
from .recovery import trigger_recovery
from .cloudflare import CloudflareClient
from .gsheets_service import GSheetsService
from .cache import load_cached_cloudflare_ip, store_cloudflare_ip
from .utils import ping_host, get_ip, doh_lookup, IPResolutionResult
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

        # --- Cloudflare IP Cache Init (authoritative DNS over HTTPS (DoH) ---
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

        """Network watchdog with WAN readiness and convergence awareness."""

        # --- Configuration (static) ---
        self.router_ip = Config.Hardware.ROUTER_IP        # Local router gateway IP
        self.watchdog_enabled = Config.WATCHDOG_ENABLED   # Enable recovery actions
        self.max_consec_fails = max_consec_fails          # Escalation threshold

        # --- LAN/WAN Failure Tracking (dynamic) ---
        self.consec_wan_fails: int = 0   # Consecutive confirmed WAN failures

        # --- WAN Observation State ---
        self.last_detected_ip: Optional[str] = None   # Last observed public IP
        self.ip_stability_count: int = 0              # Consecutive identical IP detections

        # --- WAN Readiness Policy ---
        self.MIN_IP_STABILITY_CYCLES: int = 2   # Required IP stability cycles

        ##################
        # For testing only
        ##################
        self.count = 0

    def update_ip_stability(self, result: IPResolutionResult) -> bool:
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


    def run_cycle(self) -> NetworkState:
        """
        Execute a single watchdog evaluation cycle and return the observed network state.

        This function implements a defensive, state-machine-based health check designed
        to distinguish between normal operation, router reboot scenarios, transient
        failures, and persistent WAN outages.

        Decision flow:
            1. Router health check (LAN reachability)
            - If the router is unreachable, assume reboot or offline state.
            - No recovery action is taken in this state.

            2. WAN health check (external reachability)
            - If the router is reachable but external connectivity fails,
                track consecutive failures.

            3. Escalation and recovery
            - Only after a configurable number of consecutive WAN failures
                is a recovery action triggered (e.g., power-cycling modem/router).
            - Counters are reset after recovery attempts.

        Design goals:
            - Avoid false positives during expected router reboots
            - Ignore transient packet loss and DNS flakiness
            - Fail fast, but recover conservatively
            - Provide clear, observable system state for logging and monitoring

        Returns:
            NetworkState:
                HEALTHY        - Router and WAN are reachable
                ROUTER_DOWN    - Router unreachable (rebooting or offline)
                WAN_WARMING    - 
                WAN_DOWN       - Router reachable, WAN unreachable
                ERROR          - Unexpected internal error
                UNKNOWN        - Initial or indeterminate state
        """

        # --- Heartbeat (local process health only) ---
        dt_local, dt_str = self.time.now_local()
        tlog("💚", "HEARTBEAT", "OK")

        # --- PHASE 0 (LAN): Router Reachability Check ---
        router_up = ping_host(self.router_ip)

        tlog(
            "🟢" if router_up else "🟡", 
            "ROUTER", 
            "UP" if router_up else "DOWN", 
            primary=f"ip={self.router_ip}"
        ) 

        if not router_up:
            self.consec_wan_fails = 0
            self.ip_stability_count = 0
            self.last_detected_ip = None
            self.last_router_up_ts = None
            return NetworkState.ROUTER_DOWN
        
        # --- PHASE 1 (WAN): External IP Observation (No assumptions) ---
        public = get_ip()


        # ######################
        # ######################
        # # For testing only
        # ######################
        # ######################
        # self.count += 1
        # if self.count % 2 == 0:
        #     public.ip = "192.168.0.77"   # For testing only


        tlog(
            "🟢" if public.success else "🔴",
            "PUBLIC IP",
            "OK" if public.success else "FAIL",
            primary=f"ip={public.ip}",
            meta=f"rtt={public.elapsed_ms:.1f}ms | attempts={public.attempts}"
        )

        # --- PHASE 2 (WAN): Stability Confirmation Across Cycles ---
        wan_ready = self.update_ip_stability(public)

        if (public.success and not wan_ready):
            tlog(
                "🟡",
                "WAN",
                "WARMING",
                primary=f"ip={public.ip}",
                meta=f"confirmed={self.ip_stability_count}/{self.MIN_IP_STABILITY_CYCLES} consecutive cycles"
            )
            return NetworkState.WAN_WARMING

        ### --- WAN is now considered STABLE ---
        self.consec_wan_fails = 0




        # # --- High-frequency heartbeat (timestamp) to Google Sheet ---
        # gsheets_ok = self.gsheets_service.update_status(
        #     ip_address=None,  # No change
        #     current_time=dt_str,
        #     dns_last_modified=None   # No change
        # )

        # if gsheets_ok:
        #     tlog("🟢", "GSHEET", "OK")


        

        # --- Cache check (no network calls) ---
        cache = load_cached_cloudflare_ip()
        cache_ip_matches_detected = cache.hit and cache.ip == public.ip
        tlog(
            "🟢" if cache_ip_matches_detected else "🟡",
            "CACHE",
            "HIT" if cache_ip_matches_detected else "MISS",
            primary=f"cache ip={cache.ip}",
            meta=f"rtt={cache.elapsed_ms:.1f}ms"
        )


        if wan_ready:

            self.consec_wan_fails = 0

            if cache_ip_matches_detected:
                return NetworkState.HEALTHY

            # --- Authoritative DoH verification ---
            doh = doh_lookup(self.cloudflare_client.dns_name)

            # If DoH matches detected IP, DNS as seen by world is correct
            if doh.success and doh.ip == public.ip:
                tlog(
                    "🟢", 
                    "DNS", 
                    "OK", 
                    primary=f"DoH ip={doh.ip}",
                    meta=f"rtt={doh.elapsed_ms:.1f}ms"
                )
                store_cloudflare_ip(public.ip)   # Refresh cache
                return NetworkState.HEALTHY

            # --- PHASE 2: Cloudflare DNS Update Needed ---
            tlog("🟡", "DNS", "CHANGE", primary=f"{doh.ip} → {public.ip}")

            update_result = self.cloudflare_client.update_dns(public.ip)
            store_cloudflare_ip(public.ip)

            dns_last_modified = self.time.iso_to_local_string(
                update_result.get('modified_on')
            )
            tlog(
                "🟢",
                "DNS",
                "UPDATE",
                primary="Cloudflare record updated",
                meta=f"modified={dns_last_modified}"
            )

            # # --- Low-frequency audit log ---
            # gsheets_ok = self.gsheets_service.update_status(
            #         ip_address=public.ip,
            #         current_time=None,
            #         dns_last_modified=dns_last_modified
            # )

            # if gsheets_ok:
            #     tlog("🟢", "GSHEET", "OK", primary="audit ip update")

            return NetworkState.HEALTHY
        
        else:
    
            # --- PHASE 3: WAN Failure (Router UP, Internet DOWN) ---
            #PING_TARGET_IP = "api.cloudflare.com"
            PING_TARGET_IP = "8.8.8.8"   # Google DNS Primary IP (Stable DNS check)

            if ping_host(PING_TARGET_IP):
                # WAN reachable but not ready (do not reset failure counter)
                tlog("🟢", "WAN", "UP", primary=PING_TARGET_IP)
                return NetworkState.WAN_WARMING

            # WAN confirmed DOWN
            self.consec_wan_fails += 1

            tlog(
                "🟡",
                "WAN",
                "DOWN",
                primary=PING_TARGET_IP,
                meta=f"failures={self.consec_wan_fails}/{self.max_consec_fails}"
            )

            # --- Escalation gate ---
            if (
                self.watchdog_enabled 
                and self.consec_wan_fails >= self.max_consec_fails
            ):
                tlog("🔴", "RECOVERY", "TRIGGER", primary="reset smart-plug")

                success = trigger_recovery()
                tlog(
                    "🟢" if success else "🔴", 
                    "RECOVERY", 
                    "OK" if success else "FAIL", 
                    primary="power-cycle complete"
                )

                # Reset only after recovery attempt
                self.consec_wan_fails = 0
            
            return NetworkState.WAN_DOWN
