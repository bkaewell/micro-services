# --- Standard library imports ---
import time

# --- Project imports ---
from .config import Config
from .logger import get_logger
from .time_service import TimeService
from .watchdog import reset_smart_plug
from .cloudflare import CloudflareClient
from .google_sheets_service import GSheetsService
from .utils import get_ip, dns_ready, doh_lookup, Timer
from .cache import get_cloudflare_ip, update_cloudflare_ip
#from .db import log_metrics


class NetworkWatchdog:
    """
    Background agent that maintains consistency between the device’s
    current public IP and its Cloudflare DNS record.

    Optimized for fast no-op cycles under normal conditions when everything's
    healthy with explicit recovery behavior on sustained failures.
    """

    def __init__(self, max_consecutive_failures=3):

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
                update_cloudflare_ip(doh_ip)
                self.logger.info(
                    f"Cloudflare L1 cache initialized using DoH value: "
                    f"[{doh_ip}]"
                )
            else:
                # DoH returned nothing or invalid
                update_cloudflare_ip("__INIT__")
                self.logger.warning(
                    "DoH lookup returned no usable IP; "
                    "Cache cleared for recovery"
                )

        except Exception as e:
            # Defensive fallback
            update_cloudflare_ip("")
            self.logger.error(
                f"DoH init failed ({type(e).__name__}: {e}); "
                "Cache cleared for recovery"
            )

        self.failed_ping_count = 0
        self.watchdog_enabled = Config.WATCHDOG_ENABLED
        self.max_consecutive_failures = max_consecutive_failures
        ##################
        # For testing only
        ##################
        self.count = 0

    def run_cycle(self):
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

        self.timer.start_cycle()

        # --- Get current local time ---
        dt_local, dt_str = self.time.now_local()
        heartbeat = self.time.heartbeat_string(dt_local)
        self.logger.info(f"💚 Heartbeat OK [{heartbeat}]")

        # --- PHASE 1: Network Health Check ---
        detected_ip = get_ip()
        self.timer.lap("utils.get_ip()")

        # ######################
        # ######################
        # # For testing only
        # ######################
        # ######################
        # self.count += 1
        # if self.count % 3 == 0:
        #     detected_ip = "1.2.3.4"   # For testing only
        # else:
        #     detected_ip = get_ip()

        if detected_ip:
            self.logger.info(f"🌐 IP OK [{detected_ip}]")
            self.failed_ping_count = 0

            # --- High-frequency heartbeat (IP/timestamp) to Google Sheet ---
            gsheets_ok = self.gsheets_service.update_status(
                ip_address=None,  # No change
                current_time=dt_str,
                dns_last_modified=None
            )
            self.timer.lap("gsheets_service.update_status()")

            if gsheets_ok:
                self.logger.info(f"📊 GSheets uplink OK")

            # --- Cache check (no network calls) ---
            cached_ip = get_cloudflare_ip()
            self.timer.lap("cache.get_cloudflare_ip()")

            if cached_ip == detected_ip:
                self.logger.info("🐾🌤️  Cloudflare DNS OK [L1 Cache]")
                self.timer.end_cycle()
                return True

            # --- DoH check (authoritative) ---
            doh_ip = doh_lookup(self.cloudflare_client.dns_name)
            self.timer.lap("utils.doh_lookup()")

            # If DoH matches detected IP, DNS as seen by world is correct
            if doh_ip == detected_ip:
                self.logger.info("🐾🌤️  Cloudflare DNS OK [DoH]")
                update_cloudflare_ip(detected_ip)   # Refresh cache
                self.timer.end_cycle()
                return True

            # --- PHASE 2: Cloudflare DNS Update Needed ---
            update_result = self.cloudflare_client.update_dns(detected_ip)

            update_cloudflare_ip(detected_ip)   # Refresh cache
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
            return True
        
        else:
            # --- Phase 3: Failure Handling & Watchdog ---
            self.failed_ping_count += 1
            self.logger.warning(
                f"Internet check failed [{self.failed_ping_count}/{self.max_consecutive_failures}]"
            )

            # Check flag in .env
            if self.watchdog_enabled and self.failed_ping_count >= self.max_consecutive_failures:
                self.logger.error("Triggering smart plug reset...")

                # The execution of reset_smart_plug() is the self-correction action
                if not reset_smart_plug():
                    self.logger.error("Smart plug reset failed")


                # # --- DNS Readiness Gate ---
                # if not dns_ready("api.cloudflare.com"):
                #     self.logger.warning(
                #         "Cloudflare DNS resolver not ready; skipping API-dependent steps this cycle"
                #     )
                #     return True   # graceful skip, not a failure


                # --- DNS Warm-up Phase (NO RESET HERE) ---
                self.logger.info("Waiting for DNS to become ready...")
                max_dns_wait = 30  # seconds
                dns_ready_deadline = time.monotonic() + max_dns_wait

                while time.monotonic() < dns_ready_deadline:
                    if dns_ready("api.cloudflare.com"):
                        self.logger.info("Cloudflare DNS ready after recovery")
                        break
                    time.sleep(2)
                else:
                    self.logger.warning(
                        "DNS not ready after reset; deferring DNS sync this cycle"
                    )

                self.failed_ping_count = 0
            
            return False
