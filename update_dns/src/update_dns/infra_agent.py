# --- Standard library imports ---
from enum import Enum, auto

# --- Project imports ---
from .config import Config
from .telemetry import tlog
from .logger import get_logger
from .time_service import TimeService
from .recovery import trigger_recovery
from .cloudflare import CloudflareClient
from .gsheets_service import GSheetsService
from .utils import ping_host, get_ip, doh_lookup
from .cache import load_cached_cloudflare_ip, store_cloudflare_ip
#from .db import log_metrics


class NetworkState(Enum):
    HEALTHY = auto()
    ROUTER_DOWN = auto()
    WAN_DOWN = auto()
    ERROR = auto()
    UNKNOWN = auto()

    @property
    def label(self) -> str:
        return {
            NetworkState.HEALTHY: "HEALTHY",
            NetworkState.ROUTER_DOWN: "Router unreachable (rebooting or offline)",
            NetworkState.WAN_DOWN: "Router reachable, WAN unreachable",
            NetworkState.ERROR: "Unexpected internal error",
            NetworkState.UNKNOWN: "Initial or indeterminate state",
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

            doh_result = doh_lookup(self.cloudflare_client.dns_name)

            if doh_result.success and doh_result.ip:
                store_cloudflare_ip(doh_result.ip)
                self.logger.info(
                    "Cloudflare L1 cache initialized via DoH | "
                    f"ip={doh_result.ip} rtt={doh_result.elapsed_ms:.1f}ms"
                )
            else:
                # DoH completed but returned no usable IP
                store_cloudflare_ip("__INIT__")
                self.logger.warning(
                    "Cloudflare L1 cache not initialized via DoH | "
                    f"success={doh_result.success} "
                    f"rtt={doh_result.elapsed_ms:.1f}ms"
                )

        except Exception as e:
            # Defensive fallback: init must never crash the agent
            store_cloudflare_ip("")
            self.logger.error(
                "Cloudflare L1 cache init failed | "
                f"error={type(e).__name__}: {e}"
            )

        self.consec_wan_fails = 0
        self.watchdog_enabled = Config.WATCHDOG_ENABLED
        self.max_consec_fails = max_consec_fails
        self.router_ip = Config.Hardware.ROUTER_IP

        ##################
        # For testing only
        ##################
        self.count = 0

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
                HEALTHY        – Router and WAN are reachable
                ROUTER_DOWN    – Router unreachable (rebooting or offline)
                WAN_DOWN       – Router reachable, WAN unreachable
                ERROR          – Unexpected internal error
                UNKNOWN        – Initial or indeterminate state
        """

        # --- Heartbeat (local only, no network dependency) ---
        dt_local, dt_str = self.time.now_local()
        #heartbeat = self.time.heartbeat_string(dt_local)
        tlog("💚", "HEARTBEAT", "OK")

        # --- PHASE 0: Router Alive Gate ---
        router_up = ping_host(self.router_ip)

        tlog(
            "🟢" if router_up else "🟡", 
            "ROUTER", 
            "UP" if router_up else "DOWN", 
            primary=f"router ip={self.router_ip}"
        ) 

        if not router_up:
            self.consec_wan_fails = 0
            return NetworkState.ROUTER_DOWN   # hard stop, never recover here

        # --- PHASE 1: External Connectivity Check (WAN) ---
        public = get_ip()
        detected_ip: str = public.ip

        # ######################
        # ######################
        # # For testing only
        # ######################
        # ######################
        # self.count += 1
        # if self.count % 2 == 0:
        #     detected_ip = "192.168.0.77"   # For testing only
        # else:
        #     detected_ip = get_ip().ip

        tlog(
            "🟢" if public.success else "🔴",
            "IP",
            "OK" if public.success else "FAIL",
            primary=f"detected ip={detected_ip}",
            meta=f"rtt={public.elapsed_ms:.1f}ms | attempts={public.attempts}"
        )

        if detected_ip:

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

            tlog(
                "🟢" if cache.hit and cache.ip == detected_ip else "🟡",
                "CACHE",
                "HIT" if cache.hit and cache.ip == detected_ip else "MISS",
                primary=f"cache ip={cache.ip}",
                meta=f"rtt={cache.elapsed_ms:.1f}ms"
            )

            if cache.hit and cache.ip == detected_ip:
                return NetworkState.HEALTHY


            # --- Authoritative DoH verification ---
            doh_result = doh_lookup(self.cloudflare_client.dns_name)

            # If DoH matches detected IP, DNS as seen by world is correct
            if doh_result.success and doh_result.ip == detected_ip:
                tlog(
                    "🟢", 
                    "DNS", 
                    "OK", 
                    primary=f"DoH ip={doh_result.ip}",
                    meta=f"rtt={doh_result.elapsed_ms:.1f}ms"
                )
                store_cloudflare_ip(detected_ip)   # Refresh cache
                return NetworkState.HEALTHY
            else:
                tlog(
                    "🟡" if doh_result.success else "🔴", 
                    "DNS", 
                    "STALE" if doh_result.success else "FAIL", 
                    primary=f"DoH ip={doh_result.ip}",
                    meta=f"rtt={doh_result.elapsed_ms:.1f}ms"
                )

            # --- PHASE 2: Cloudflare DNS Update Needed ---
            update_result = self.cloudflare_client.update_dns(detected_ip)
            store_cloudflare_ip(detected_ip)
            tlog(
                "🟡", 
                "DNS", 
                "UPDATE", 
                primary=f"{doh_result.ip} → {detected_ip}"
                )

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

            # Low-frequency audit log
            gsheets_ok = self.gsheets_service.update_status(
                    ip_address=detected_ip,
                    current_time=None,
                    dns_last_modified=dns_last_modified
                )

            if gsheets_ok:
                tlog("🟢", "GSHEET", "OK", primary="audit ip update")

            return NetworkState.HEALTHY


        # --- PHASE 3: WAN Failure (Router UP, Internet DOWN) ---

        #PING_TARGET_IP = "api.cloudflare.com"
        PING_TARGET_IP = "8.8.8.8"   # Google DNS Primary IP (Stable DNS check)
        wan_up = ping_host(PING_TARGET_IP)

        if wan_up:
            self.consec_wan_fails = 0
            tlog("🟢", "WAN", "UP", primary=PING_TARGET_IP)
            return NetworkState.HEALTHY

        # --- WAN is DOWN ---
        self.consec_wan_fails += 1
        self.logger.warning(
            f"🌐 IP unresolved "
            f"({public.elapsed_ms:.1f} ms, {public.attempts} attempts)"
        )
        self.logger.warning(
            f"WAN un-reachable "
            f"[{self.consec_wan_fails}/{self.max_consec_fails}]"
        )

        tlog(
            "⚠️",
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
            # self.logger.error(
            #     "Persistent WAN failure → triggering recovery "
            #     "(likely real outage)"
            # )
            tlog("❌", "RECOVERY", "TRIGGER", primary="smart-plug")

            if trigger_recovery():
                tlog("🟢", "RECOVERY", "OK", primary="power-cycle complete")
            else:
                tlog("❌", "RECOVERY", "FAIL")

            # if not trigger_recovery():
            #     self.logger.error("Recovery action failed")

            # Always reset counter after recovery attempt
            self.consec_wan_fails = 0
        
        return NetworkState.WAN_DOWN
