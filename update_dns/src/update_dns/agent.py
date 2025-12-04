from datetime import datetime, timezone

from .config import Config
from .logger import get_logger
from .utils import get_ip, to_local_time
from .watchdog import reset_smart_plug
from .cloudflare import CloudflareClient
from .google_sheets_service import GSheetsService 
from .cache import get_cloudflare_ip, update_cloudflare_ip
# from .sheets import log_to_sheets
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

        self.max_consecutive_failures = max_consecutive_failures
        self.failed_ping_count = 0
        self.watchdog_enabled = Config.WATCHDOG_ENABLED

        # Initialize the Cloudflare client
        self.cloudflare_client = CloudflareClient()

        # Initialize the standalone GSheets service
        self.gsheets_service = GSheetsService()

        # Outputs 
        self.detected_ip = ""
        self.dns_last_modified = ""
        self.count = 0


    def run_cycle(self):
        """
        Executes the full monitoring and update logic sequence.

        The method handles three distinct phases:
        1. Phase 1 (Health Check): Attempts to retrieve the external IP. If successful, 
           resets the failure counter
        2. Phase 2 (Core Task): Calls `cloudflare_client.sync_dns()` to update the 
           DNS record only if the IP has changed. On success, the local IP cache 
           is updated. Logs the final status to Google Sheets
        3. Phase 3 (Failure Handling): If the network check fails, increments the 
           failure counter. If the counter meets the threshold and the watchdog is enabled, 
           it attempts to self-heal by resetting the smart plug

        Returns:
            bool: True if the IP detection was successful and the cycle completed 
                  without critical error (DNS sync may still have soft failed)
                  False if the network check failed or a critical sync error occurred
        """

        # Capture current local time for the heartbeat log
        current_time_utc = datetime.now(timezone.utc).isoformat()
        current_time_str = to_local_time(current_time_utc)

        # Parse it back to a datetime (ignore the timezone label)
        current_time = datetime.strptime(current_time_str, "%m/%d/%y @ %H:%M:%S %Z")

        heartbeat_date = current_time.strftime("%a %b %d %Y")  # Tue Dec 03 2025

        self.logger.info(f"💚 Heartbeat OK ... {heartbeat_date}")
        
        # --- Phase 1: Network Health Check ---

        # The primary goal is to rely solely on the result of 
        # get_ip() to determine the overall network health

        # Source of truth for connectivity

        # One full HTTPS request, if successful, the entire network stack 
        # (DNS resolution, routing, and application layer protocols) is functional

        self.detected_ip = get_ip()

        if self.detected_ip:
            self.logger.info("🌐 IP OK")
            self.failed_ping_count = 0

            # Capture current time for the heartbeat log
            #current_time_utc = datetime.now(timezone.utc).isoformat()
            #current_time = to_local_time(current_time_utc)

            # Only update status with current heartbeat info (IP and time)
            # This is the high-frequency, minimum data update
            self.gsheets_service.update_status(
                ip_address=self.detected_ip,
                current_time=current_time_str,
                dns_last_modified=None   # Do not update
            )
            self.logger.info(
                f"📊 Google Sheet updated | dns={self.cloudflare_client.dns_name} | ip={self.detected_ip} "
                f"| time={current_time}"
            )

            # --- Phase 2: Core Task (DNS update and status log) ---
            try:
                # Get cached IP to pass to the client
                cached_ip = get_cloudflare_ip()
                
                # Call the dedicated client method
                update_result = self.cloudflare_client.sync_dns(
                    cached_ip=cached_ip,
                    detected_ip=self.detected_ip
                )
                
                # Handle Update Data / Success or Skip
                if update_result:
                    # Cloudflare update was successful
                    self.dns_last_modified = to_local_time(update_result.get('modified_on'))
                    self.logger.info(f"🐾 🌤️  Cloudflare DNS updated | {cached_ip} → {self.detected_ip}")

                    # Update status with the DNS modification time
                    # This is the low-frequency, audit-logging update
                    self.gsheets_service.update_status(
                        ip_address=None,   # Ignore, previously updated
                        current_time=None, # Ignore, previously updated
                        dns_last_modified=self.dns_last_modified   # The new value
                    )
                    self.logger.info(
                        f"📊 Google Sheet updated | dns={self.cloudflare_client.dns_name} | "
                        f"last_modified={self.dns_last_modified}"
                    )

                    # Update local cache file with new IP
                    update_cloudflare_ip(self.detected_ip)

                elif update_result is None: 
                    # DNS No-op
                    self.logger.info("🐾 🌤️  Cloudflare DNS OK")

            except (RuntimeError, ValueError) as e:
                # Catch API/logic failures raised by CloudflareClient
                self.logger.error(f"Cloudflare DNS sync failed: {e}")
                return False
            except Exception as e:
                # Last-resort safeguard
                self.logger.exception(f"Unexpected fatal failure during Cloudflare DNS sync: {e}")
                return False

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
        