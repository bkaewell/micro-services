# --- Standard library imports ---
import time
from enum import Enum, auto

# --- Project imports ---
from .config import Config
from .logger import get_logger
from .time_service import TimeService
from .watchdog import reset_smart_plug
from .cloudflare import CloudflareClient
from .gsheets_service import GSheetsService
from .utils import get_ip, dns_ready, doh_lookup, Timer
from .cache import load_cached_cloudflare_ip, store_cloudflare_ip
#from .db import log_metrics

# For informational purposes, not operational
class NetworkState(Enum):
    HEALTHY = auto()
    ROUTER_DOWN = auto()
    WAN_DOWN = auto()

class NetworkWatchdog:
    """
    Background agent that maintains consistency between the device’s
    current public IP and its Cloudflare DNS record.

    Optimized for fast no-op cycles under normal conditions when everything's
    healthy with explicit recovery behavior on sustained failures.
    """

    def __init__(self, max_consecutive_failures=4):

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

        self.failed_ping_count = 0
        self.watchdog_enabled = Config.WATCHDOG_ENABLED
        self.max_consecutive_failures = max_consecutive_failures

        self.outage_start_ts: float | None = None
        self.reboot_grace_period = 240  # seconds (tunable)


        ##################
        # For testing only
        ##################
        self.count = 0

    def run_cycle(self) -> NetworkState:
        """
        Run a single watchdog cycle.

        Workflow:
        1. Detect the current external IP
        2. Check DNS state using cache and/or DoH (source of truth)
        3. Update Cloudflare only if the IP has changed
        4. Refresh local state and log the results

        Optimized for the common case where DNS is already correct,
        with built-in timing and clear logging for observability.

        Returns:
            bool: True if the cycle completed normally or made progress,
                False if the cycle exited in a degraded or recovery path.
        """

        # --- Get current local time ---
        dt_local, dt_str = self.time.now_local()
        heartbeat = self.time.heartbeat_string(dt_local)
        self.logger.info(f"💚 Heartbeat OK [{heartbeat}]")

        # --- PHASE 1: Network Health Check ---

        #router_up = ping_router(Config.Hardware.ROUTER_IP)   # TBD
        router_up = True

        if not router_up:
            self.logger.warning("Router un-reachable (likely rebooting)")
            self.failed_ping_count = 0
            return NetworkState.ROUTER_DOWN   # hard stop, never recover here


        self.timer.start_cycle()
        detected_ip = get_ip()
        self.timer.lap("utils.get_ip()")
        # ######################
        # ######################
        # # For testing only
        # ######################
        # ######################
        # self.count += 1
        # if self.count % 2 == 0:
        #     detected_ip = "1.2.3.4"   # For testing only
        # else:
        #     detected_ip = get_ip()


        if detected_ip:
            state = HEALTHY
            self.logger.info(f"🌐 IP OK [{detected_ip}]")
            # reset failure counters
            self.failed_ping_count = 0






        if detected_ip:
            self.logger.info(f"🌐 IP OK [{detected_ip}]")
            self.failed_ping_count = 0

            # --- High-frequency heartbeat (timestamp) to Google Sheet ---
            gsheets_ok = self.gsheets_service.update_status(
                ip_address=None,  # No change
                current_time=dt_str,
                dns_last_modified=None   # No change
            )
            self.timer.lap("gsheets_service.update_status()")

            if gsheets_ok:
                self.logger.info(f"📊 GSheets uplink OK")

            # --- Cache check (no network calls) ---
            cached_ip = load_cached_cloudflare_ip()
            self.timer.lap("cache.load_cached_cloudflare_ip()")

            if cached_ip == detected_ip:
                self.logger.info("🐾🌤️  Cloudflare DNS OK [cache]")
                self.timer.end_cycle()
                return NetworkState.HEALTHY

            # --- DoH check (authoritative) ---
            doh_ip = doh_lookup(self.cloudflare_client.dns_name)
            self.timer.lap("utils.doh_lookup()")

            # If DoH matches detected IP, DNS as seen by world is correct
            if doh_ip == detected_ip:
                self.logger.info("🐾🌤️  Cloudflare DNS OK [DoH]")
                store_cloudflare_ip(detected_ip)   # Refresh cache
                self.timer.end_cycle()
                return NetworkState.HEALTHY

            # --- PHASE 2: Cloudflare DNS Update Needed ---
            update_result = self.cloudflare_client.update_dns(detected_ip)
            store_cloudflare_ip(detected_ip)
            self.timer.lap("cloudflare_client.update_dns()")
            dns_last_modified = self.time.iso_to_local_string(
                update_result.get('modified_on')
            )

            # Low-frequency audit log
            gsheets_ok = self.gsheets_service.update_status(
                    ip_address=detected_ip,
                    current_time=None,
                    dns_last_modified=dns_last_modified
                )
            self.timer.lap("gsheets_service.update_status()")

            if gsheets_ok:
                self.logger.info(f"📊 GSheets uplink OK")
            self.logger.info(
                f"🐾 🌤️  Cloudflare DNS updated  [{doh_ip} → {detected_ip}]"
            )
            self.timer.end_cycle()
            return NetworkState.HEALTHY


        # Router is up, but WAN is down
        return NetworkState.WAN_DOWN
        # incremenet failure count

        #if router_up and failures >= WAN_FAILURE_THRESHOLD:
        #    trigger_recovery() / reset_smart_plug()



