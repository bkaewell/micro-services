from .config import Config
from .logger import get_logger
from .time_service import TimeService
from .utils import get_ip, doh_lookup
from .watchdog import reset_smart_plug
from .cloudflare import CloudflareClient
from .google_sheets_service import GSheetsService
from .cache import get_cloudflare_ip, update_cloudflare_ip
#from .db import log_metrics


class NetworkWatchdog:
    """
    Manages a dynamic DNS update cycle with self-healing capabilities

    The primary goal is to maintain the local DNS record (in Cloudflare) 
    in sync with the current IP address    

    The main loop (run_cycle) executes the following sequence:
    1. Check network health by attempting to detect the current IP
    2. If successful, delegate DNS synchronization
       (IP comparison/update/caching) to the Cloudflare client
    3. Log the cycle status (including the DNS record's last modified timestamp) 
       to the Google Sheet service
    4. If IP detection fails, track consecutive failures
    5. If consecutive failures exceed a defined threshold, trigger the self-healing 
       process to power-cycle the smart plug (if the watchdog flag is enabled)
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

        # Preload cache from DNS over HTTPS (DoH); Authoritatively initialized 
        # from truth. If DoH fails, clear cache to trigger auto-correction on 
        # first cycle
        try:
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


    def run_cycle2(self):
        """
        Single monitoring and DNS update cycle.

        Workflow:
        1. Detect external IP
        2. Verify DNS via DoH (authoritative source)
        3. Update Cloudflare only if necessary
        4. Update cache and log to Google Sheets
        """

        # --- Get current local time once ---
        dt_local, dt_str = self.time.now_local()
        heartbeat = self.time.heartbeat_string(dt_local)
        self.logger.info(f"💚 Heartbeat OK ... {heartbeat}")

        # --- PHASE 1: Network Health Check ---
        detected_ip = get_ip()

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
            self.gsheets_service.update_status(
                ip_address=detected_ip,
                current_time=dt_str,
                dns_last_modified=None
            )
            self.logger.info(
                f"📊 Google Sheet updated | dns={self.cloudflare_client.dns_name}"
                f" | ip={detected_ip} | time={dt_str}"
            )

            # --- Cache check (no network calls) ---
            cached_ip = get_cloudflare_ip()
            if cached_ip == detected_ip:
                self.logger.info("🐾 🌤️  Cloudflare DNS OK | source: cached IP")
                return True

            # --- DoH check (authoritative) ---
            doh_ip = doh_lookup(self.cloudflare_client.dns_name)
            self.logger.debug(f"DoH resolved IP: {doh_ip} (detected: {detected_ip})")

            # If DoH matches detected IP -> DNS as seen by world is correct
            if doh_ip == detected_ip:
                self.logger.info("🐾 🌤️  Cloudflare DNS OK | source: DoH IP")
                update_cloudflare_ip(detected_ip)   # Refresh cache
                return True

            # --- STATE 2: Out-of-Sync, Cloudflare DNS Update Needed ---
            
            update_result = self.cloudflare_client.sync_dns(detected_ip)
            update_cloudflare_ip(detected_ip)   # Refresh cache
            dns_last_modified = self.time.iso_to_local_string(
                update_result.get('modified_on')
            )
            self.logger.info(
                f"🐾 🌤️  Cloudflare DNS updated | {doh_ip} → {detected_ip}"
            )

            # Low-frequency audit log
            self.gsheets_service.update_status(
                ip_address=None,
                current_time=None,
                dns_last_modified=dns_last_modified
            )
            self.logger.info(
                f"📊 Google Sheet updated | dns={self.cloudflare_client.dns_name} | "
                f"dns_last_modified={dns_last_modified}"
            )

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


        # Optional: log metrics to SQLite
        # log_metrics(ip=detected_ip,
        #             internet_ok=internet_ok,
        #             dns_changed=dns_changed)


