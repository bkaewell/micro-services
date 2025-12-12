from .config import Config
from .logger import get_logger
from .time_service import TimeService
from .utils import get_ip, doh_lookup
from .watchdog import reset_smart_plug
from .cloudflare import CloudflareClient
from .google_sheets_service import GSheetsService
from .cache import get_cloudflare_ip, update_cloudflare_ip
#from .db import log_metrics

import time

def ms():
    return time.monotonic() * 1000   # helper for readability

class NetworkWatchdog:
    """
    Keeps Cloudflare DNS synchronized with the device’s current public IP
    and provides automatic recovery when connectivity degrades.

    Core functions:
    - Detect current external IP 
    - Verify DNS correctness via cache and DNS-over-HTTPS (DoH)
    - Update Cloudflare DNS only when necessary
    - Log IP/DNS status to Google Sheets
    - Track consecutive failures and optionally trigger a smart plug reset
    """

    def __init__(self, max_consecutive_failures=3):

        # Define the logger once for the entire class
        self.logger = get_logger("agent")

        self.watchdog_enabled = Config.WATCHDOG_ENABLED
        self.failed_ping_count = 0
        self.max_consecutive_failures = max_consecutive_failures

        # Initialize Cloudflare and GSheets client
        self.cloudflare_client = CloudflareClient()
        self.gsheets_service = GSheetsService()

        # Load timezone and time utilities once
        self.time = TimeService()

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

        t0 = ms()

        # --- Get current local time ---
        t1 = ms()
        dt_local, dt_str = self.time.now_local()
        heartbeat = self.time.heartbeat_string(dt_local)
        self.logger.info(f"💚 Heartbeat OK ... {heartbeat}")
        self.logger.critical(f"Timing | Local time: {ms() - t1:.2f}ms")


        # --- PHASE 1: Network Health Check ---
        t2 = ms()
        detected_ip = get_ip()
        self.logger.critical(f"Timing | IP detection: {ms() - t2:.2f}ms")


        #################
        #################
        #For testing only
        #################
        #################
        # self.count += 1
        # if self.count % 3 == 0:
        #     detected_ip = "192.168.1.1"   # For testing only
        # else:
        #     detected_ip = get_ip()

        if detected_ip:
            self.logger.info("🌐 IP OK")
            self.failed_ping_count = 0

            # --- High-frequency heartbeat (IP/timestamp) to Google Sheet ---
            t3 = ms()
            self.gsheets_service.update_status(
                ip_address=detected_ip,
                current_time=dt_str,
                dns_last_modified=None
            )
            self.logger.critical(f"Timing | Google Sheets IP update: {ms() - t3:.2f}ms")

            self.logger.info(
                f"📊 Google Sheet updated | dns={self.cloudflare_client.dns_name}"
                f" | ip={detected_ip} | time={dt_str}"
            )

            # --- Cache check (no network calls) ---
            t4 = ms()
            cached_ip = get_cloudflare_ip()
            self.logger.critical(f"Timing | Cache read: {ms() - t4:.2f}ms")
            if cached_ip == detected_ip:
                self.logger.info("🐾 🌤️  Cloudflare DNS OK | source: cached IP")
                self.logger.critical(f"Timing | Total run_cycle: {ms() - t0:.2f}ms")
                return True

            # --- DoH check (authoritative) ---
            t5 = ms()
            doh_ip = doh_lookup(self.cloudflare_client.dns_name)
            self.logger.critical(f"Timing | DoH lookup: {ms() - t5:.2f}ms")
            self.logger.debug(f"DoH resolved IP: {doh_ip} (detected: {detected_ip})")

            # If DoH matches detected IP -> DNS as seen by world is correct
            if doh_ip == detected_ip:
                self.logger.info("🐾 🌤️  Cloudflare DNS OK | source: DoH IP")
                update_cloudflare_ip(detected_ip)   # Refresh cache
                self.logger.critical(f"Timing | Total run_cycle: {ms() - t0:.2f}ms")
                return True

            # --- STATE 2: Out-of-Sync, Cloudflare DNS Update Needed ---
            t6 = ms()
            update_result = self.cloudflare_client.sync_dns(detected_ip)
            update_cloudflare_ip(detected_ip)   # Refresh cache
            self.logger.critical(f"Timing | Cloudflare DNS sync: {ms() - t6:.2f}ms")

            t7 = ms()
            dns_last_modified = self.time.iso_to_local_string(
                update_result.get('modified_on')
            )

            # Low-frequency audit log
            self.gsheets_service.update_status(
                ip_address=None,
                current_time=None,
                dns_last_modified=dns_last_modified
            )
            self.logger.critical(f"Timing | Google Sheets audit log: {ms() - t7:.2f}ms")

            self.logger.info(
                f"🐾 🌤️  Cloudflare DNS updated | {doh_ip} → {detected_ip}"
            )
            self.logger.info(
                f"📊 Google Sheet updated | dns={self.cloudflare_client.dns_name} | "
                f"dns_last_modified={dns_last_modified}"
            )

            self.logger.critical(f"Timing | Total run_cycle: {ms() - t0:.2f}ms")
            return True
        
        else:
            # --- Phase 3: Failure Handling & Watchdog ---
            self.failed_ping_count += 1
            self.logger.warning(f"Internet check failed ({self.failed_ping_count}/{self.max_consecutive_failures})")

            # Check flag in .env
            if self.watchdog_enabled and self.failed_ping_count >= self.max_consecutive_failures:
                self.logger.error("Triggering smart plug reset...")

                # The execution of reset_smart_plug() is the self-correction action
                if not reset_smart_plug():
                    self.logger.error("Smart plug reset failed")
                    # Do not return True here, the cycle failed

                # Reset counter after attempting recovery, regardless of success
                self.failed_ping_count = 0 

            # Always return False if the cycle failed (IP detection failed)
            return False 

