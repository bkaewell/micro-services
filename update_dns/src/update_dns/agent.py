import time

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
    Keeps Cloudflare DNS synchronized with the device's current public IP
    and provides automatic recovery when connectivity degrades.

    Core functions:
    - Detect current external IP 
    - Verify DNS correctness via cache and DNS-over-HTTPS (DoH)
    - Update Cloudflare DNS only when necessary
    - Log IP/DNS status to Google Sheets
    - Track consecutive failures and optionally trigger a smart plug reset
    """

    def __init__(self, max_consecutive_failures=3):

        # Initialize time, clients, logs, and timing
        self.time = TimeService()
        self.cloudflare_client = CloudflareClient()
        self.gsheets_service = GSheetsService()
        self.logger = get_logger("agent")
        self.timer = Timer(self.logger, Config.TIMING_ENABLED)

        # --- Cloudflare IP Cache Init ---
        try:

            # Preload cache from DNS over HTTPS (DoH),
            # authoritatively initialized from truth
            doh_ip = doh_lookup(self.cloudflare_client.dns_name)

            if doh_ip:
                update_cloudflare_ip(doh_ip)
                self.logger.info(
                    f"Cloudflare cache initialized using DoH value: {doh_ip}"
                )
            else:
                # DoH returned nothing or invalid
                update_cloudflare_ip("__INIT__")
                self.logger.warning(
                    "DoH lookup returned no usable IP; Cache "
                    "cleared for recovery"
                )

        except Exception as exc:
            # Defensive fallback
            update_cloudflare_ip("")
            self.logger.error(
                f"DoH init failed ({type(exc).__name__}: {exc}); "
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
        Single monitoring and DNS update cycle.

        Workflow:
        1. Detect external IP
        2. Verify DNS via DoH (authoritative source)
        3. Update Cloudflare only if necessary
        4. Update cache and log to Google Sheets
        """

        self.timer.start_cycle()

        # --- Get current local time ---
        dt_local, dt_str = self.time.now_local()
        heartbeat = self.time.heartbeat_string(dt_local)
        self.logger.info(f"💚 Heartbeat OK ... {heartbeat}")
        self.timer.lap("Local time")

        # --- PHASE 1: Network Health Check ---
        detected_ip = get_ip()
        self.timer.lap("IP detection")



        #######################
        #######################
        ## For testing only
        #######################
        #######################
        self.count += 1
        if self.count % 3 == 0:
            detected_ip = "192.168.1.1"   # For testing only
        else:
            detected_ip = get_ip()



        if detected_ip:
            self.logger.info("🌐 IP OK")
            self.failed_ping_count = 0

            # --- High-frequency heartbeat (IP/timestamp) to Google Sheet ---
            gsheets_ok = self.gsheets_service.update_status(
                    ip_address=detected_ip,
                    current_time=dt_str,
                    dns_last_modified=None
            )
            
            if gsheets_ok:
                self.timer.lap("GSheets IP update")
                self.logger.info(
                    f"📊 GSheets updated | dns={self.cloudflare_client.dns_name}"
                    f" | ip={detected_ip} | time={dt_str}"
                )
            else:
                self.timer.lap("GSheets update skipped")


            # --- Cache check (no network calls) ---
            cached_ip = get_cloudflare_ip()
            self.timer.lap("Cache read")

            if cached_ip == detected_ip:
                self.logger.info("🐾 🌤️  Cloudflare DNS OK | source: cache IP")
                self.timer.end_cycle()
                return True

            # --- DoH check (authoritative) ---
            doh_ip = doh_lookup(self.cloudflare_client.dns_name)
            self.timer.lap("DoH lookup")
            self.logger.debug(f"DoH resolved IP: {doh_ip} (detected: {detected_ip})")

            # If DoH matches detected IP, DNS as seen by world is correct
            if doh_ip == detected_ip:
                self.logger.info("🐾 🌤️  Cloudflare DNS OK | source: DoH IP")
                update_cloudflare_ip(detected_ip)   # Refresh cache
                self.timer.end_cycle()
                return True

            # --- STATE 2: Out-of-Sync, Cloudflare DNS Update Needed ---
            update_result = self.cloudflare_client.sync_dns(detected_ip)
            update_cloudflare_ip(detected_ip)   # Refresh cache
            self.timer.lap("Cloudflare DNS sync")

            dns_last_modified = self.time.iso_to_local_string(
                update_result.get('modified_on')
            )

            # Low-frequency audit log
            gsheets_ok = self.gsheets_service.update_status(
                    ip_address=None,
                    current_time=None,
                    dns_last_modified=dns_last_modified
                )
            
            if gsheets_ok:
                self.timer.lap("GSheets audit update")
                self.logger.info(
                    f"📊 GSheets updated | dns={self.cloudflare_client.dns_name} | "
                    f"dns_last_modified={dns_last_modified}"
                )
            else:
                self.timer.lap("GSheets audit skipped")

            self.logger.info(
                f"🐾 🌤️  Cloudflare DNS updated | {doh_ip} → {detected_ip}"
            )
            self.timer.end_cycle()
            return True
        
        else:
            # --- Phase 3: Failure Handling & Watchdog ---
            self.failed_ping_count += 1
            self.logger.warning(
                f"Internet check failed ({self.failed_ping_count}/{self.max_consecutive_failures})"
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

