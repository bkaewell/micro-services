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
        Execute one watchdog evaluation cycle and return the authoritative network state.

        This method implements a defensive, multi-phase state machine that separates:
        - LAN reachability (router health)
        - WAN availability (external connectivity)
        - WAN readiness (confirmed stability across consecutive cycles)

        Core principles:
        - No single probe is trusted; confidence is accumulated over time.
        - Expected disruptions (router reboots, ISP warm-up, transient loss) are not escalated.
        - Recovery actions trigger only after sustained, externally confirmed failures.

        State model:
        - ROUTER_DOWN: Router unreachable; WAN signals ignored, counters reset.
        - WAN_WARMING: Router up, WAN signals present but not yet stable
                    (e.g., IP changing or insufficient consecutive confirmations).
        - HEALTHY: Router reachable and WAN stability confirmed across cycles.
        - WAN_DOWN: Router reachable but WAN confirmed unreachable after escalation thresholds.

        Side effects:
        - Maintains consecutive-failure and IP-stability counters across cycles.
        - Updates external observability (logs, cache, DNS, audit sinks) only when confidence allows.
        - Optionally triggers automated recovery after sustained WAN failure.

        Returns:
            NetworkState: The resolved, confidence-weighted network state for this cycle.
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

        # --- High-frequency heartbeat (timestamp) to Google Sheet ---
        gsheets_ok = self.gsheets_service.update_status(
            ip_address=None,  # No change
            current_time=dt_str,
            dns_last_modified=None   # No change
        )
        if gsheets_ok:
            tlog("🟢", "GSHEET", "OK")

        # --- Cache check (no network calls) ---
        cache = load_cached_cloudflare_ip()
        cache_ip_matches_detected = cache.hit and cache.ip == public.ip
        tlog(
            "🟢" if cache_ip_matches_detected else "🟡",
            "CACHE",
            "HIT" if cache_ip_matches_detected else "MISS",
            primary=f"ip={cache.ip}",
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
                    primary=f"ip={doh.ip}",
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
                primary="Cloudflare updated",
                meta=f"modified={dns_last_modified}"
            )

            # --- Low-frequency audit log ---
            gsheets_ok = self.gsheets_service.update_status(
                    ip_address=public.ip,
                    current_time=None,
                    dns_last_modified=dns_last_modified
            )
            if gsheets_ok:
                tlog("🟢", "GSHEET", "OK", primary="audit ip update")

            return NetworkState.HEALTHY
        
        else:
            # --- PHASE 3 (WAN): Confidence Collapse & Recovery ---
            # At this point:
            # - LAN is reachable
            # - WAN failed readiness confirmation
            # - We actively probe a known-stable external endpoint

            PROBE_IP = "8.8.8.8"   # Stable external reachability signal (Google DNS)

            if ping_host(PROBE_IP):
                # WAN path exists, but higher-level signals are not yet trustworthy
                # Do NOT reset failure counters — confidence has not been restored
                tlog("🟢", "WAN", "REACHABLE", primary=PROBE_IP)
                return NetworkState.WAN_WARMING

            # WAN confirmed un-reachable at external layer
            self.consec_wan_fails += 1

            tlog(
                "🟡",
                "WAN",
                "UNREACHABLE",
                primary=PROBE_IP,
                meta=f"failures={self.consec_wan_fails}/{self.max_consec_fails}"
            )

            # --- POLICY: Automated Recovery Escalation ---
            # Trigger only after sustained, confirmed WAN failures
            if (
                self.watchdog_enabled 
                and self.consec_wan_fails >= self.max_consec_fails
            ):
                tlog("🔴", "RECOVERY", "TRIGGER", primary="power-cycle router")

                success = trigger_recovery()
                tlog(
                    "🟢" if success else "🔴", 
                    "RECOVERY", 
                    "OK" if success else "FAIL", 
                    primary="recovery attempt complete"
                )

                # Reset after intervention — confidence must be rebuilt from Phase 0
                self.consec_wan_fails = 0
            
            return NetworkState.WAN_DOWN
