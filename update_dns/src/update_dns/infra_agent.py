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
from .utils import ping_host, get_ip, doh_lookup, Timer
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
        self.timer = Timer(self.logger) 

        # --- Cloudflare IP Cache Init ---
        try:

            # Preload cache from DNS over HTTPS (DoH),
            # authoritatively initialized from truth
            doh_ip = doh_lookup(self.cloudflare_client.dns_name)

            if doh_ip:
                store_cloudflare_ip(doh_ip)
                self.logger.info(
                    f"Cloudflare L1 cache initialized using DoH value: "
                    f"[{doh_ip}]"
                )
            else:
                # DoH returned nothing or invalid
                store_cloudflare_ip("__INIT__")
                self.logger.warning(
                    "DoH lookup returned no usable IP; "
                    "Cache cleared for recovery"
                )

        except Exception as e:
            # Defensive fallback
            store_cloudflare_ip("")
            self.logger.error(
                f"DoH init failed ({type(e).__name__}: {e}); "
                "Cache cleared for recovery"
            )

        self.cycle = 0
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
        self.cycle += 1
        dt_local, dt_str = self.time.now_local()
        #heartbeat = self.time.heartbeat_string(dt_local)
        #self.logger.info(f"💚 Heartbeat OK [{heartbeat}]")
        tlog("💚", "HEARTBEAT", "OK", meta=f"cycle={self.cycle}") 


        # --- PHASE 0: Router Alive Gate ---
        self.timer.start_cycle()
        router_up = ping_host(self.router_ip)
        self.timer.lap("utils.ping_host()")

        if not router_up:
            tlog("🟡", "ROUTER", "DOWN", primary=f"router ip={self.router_ip}")
            self.consec_wan_fails = 0
            self.timer.end_cycle()
            return NetworkState.ROUTER_DOWN   # hard stop, never recover here

        tlog("🟢", "ROUTER", "UP", primary=f"router ip={self.router_ip}") 
        
        # --- PHASE 1: External Connectivity Check (WAN) ---
        result = get_ip()
        detected_ip: str = result.ip
        self.timer.lap("utils.get_ip()")
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


        if detected_ip:
            # self.logger.info(
            #     f"🌐 IP OK [{result.ip}] "
            #     f"({result.elapsed_ms:.1f} ms, {result.attempts} attempt(s))"
            # )

            tlog(
                "🟢",
                "IP",
                "OK",
                primary=f"detected ip={detected_ip}",
                meta=f"rtt={result.elapsed_ms:.1f}ms | attempts={result.attempts}"
            )
            #self.logger.info(f"🌐 IP OK [{detected_ip}]")
            # IP resolved successfully
            # tlog(self.logger, logging.INFO, "IP", "OK", result.ip,
            #     latency=f"{result.elapsed_ms:.1f}ms",
            #     attempts=result.attempts)

            self.consec_wan_fails = 0

            # --- High-frequency heartbeat (timestamp) to Google Sheet ---
            gsheets_ok = self.gsheets_service.update_status(
                ip_address=None,  # No change
                current_time=dt_str,
                dns_last_modified=None   # No change
            )
            self.timer.lap("gsheets_service.update_status()")

            if gsheets_ok:
                #self.logger.info(f"📊 GSheets uplink OK")
                tlog("🟢", "GSHEET", "OK")

            # --- Cache check (no network calls) ---
            cache = load_cached_cloudflare_ip()
            self.timer.lap("cache.load_cached_cloudflare_ip()")

            if cache.hit and cache.ip == detected_ip:
                #self.logger.info("🐾🌤️  Cloudflare DNS OK [cache]")
                tlog(
                    "🟢",
                    "CACHE",
                    "HIT",
                    primary=f"cache ip={cache.ip}",
                    meta=f"rtt={cache.elapsed_ms:.1f}ms",
                )
                self.timer.end_cycle()
                return NetworkState.HEALTHY
            else:
                tlog(
                    "🟡",
                    "CACHE",
                    "MISS",
                    primary=f"cache ip={cache.ip}",
                    meta=f"rtt={cache.elapsed_ms:.1f}ms",
                )

            # --- Authoritative DoH verification ---
            doh_ip = doh_lookup(self.cloudflare_client.dns_name)
            self.timer.lap("utils.doh_lookup()")

            # If DoH matches detected IP, DNS as seen by world is correct
            if doh_ip == detected_ip:
                #self.logger.info("🐾🌤️  Cloudflare DNS OK [DoH]")
                tlog("🟢", "DNS", "OK", primary=f"DoH ip={doh_ip}")
                store_cloudflare_ip(detected_ip)   # Refresh cache
                self.timer.end_cycle()
                return NetworkState.HEALTHY
            else:
                tlog("🟡", "DNS", "STALE", primary=f"DoH ip={doh_ip}")

            # --- PHASE 2: Cloudflare DNS Update Needed ---
            update_result = self.cloudflare_client.update_dns(detected_ip)
            store_cloudflare_ip(detected_ip)
            self.timer.lap("cloudflare_client.update_dns()")

            dns_last_modified = self.time.iso_to_local_string(
                update_result.get('modified_on')
            )
            tlog("❌", "DNS", "UPDATE", primary=f"{doh_ip} → {detected_ip}")

            # Low-frequency audit log
            gsheets_ok = self.gsheets_service.update_status(
                    ip_address=detected_ip,
                    current_time=None,
                    dns_last_modified=dns_last_modified
                )
            self.timer.lap("gsheets_service.update_status()")

            if gsheets_ok:
                #self.logger.info(f"📊 GSheets uplink OK")
                tlog("🟢", "GSHEET", "OK", primary="audit ip update")

            # self.logger.info(
            #     f"🐾 🌤️  Cloudflare DNS updated  [{doh_ip} → {detected_ip}]"
            # )

            self.timer.end_cycle()
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
            f"({result.elapsed_ms:.1f} ms, {result.attempts} attempts)"
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
