import time

from datetime import datetime, timezone

from .config import Config
from .logger import get_logger
from .utils import get_public_ip, to_local_time
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
    in sync with the current public IP address    

    The main loop (run_cycle) executes the following sequence:
    1. Check network health by attempting to detect the current public IP
    2. If successful, delegate DNS synchronization
       (IP comparison/update/caching) to the Cloudflare client
    3. Log the cycle status (including the DNS record's last modified timestamp) 
       to the Google Sheet service
    4. If public IP detection fails, track consecutive failures
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


    def run_cycle(self):
        """
        Executes the full monitoring and update logic sequence.

        The method handles three distinct phases:
        1. Phase 1 (Health Check): Attempts to retrieve the public IP. If successful, 
           resets the failure counter
        2. Phase 2 (Core Task): Calls `cloudflare_client.sync_dns()` to update the 
           DNS record only if the IP has changed. On success, the local IP cache 
           is updated. Logs the final status to Google Sheets
        3. Phase 3 (Failure Handling): If the network check fails, increments the 
           failure counter. If the counter meets the threshold and the watchdog is enabled, 
           it attempts to self-heal by resetting the smart plug

        Returns:
            bool: True if the public IP detection was successful and the cycle completed 
                  without critical error (DNS sync may still have soft failed)
                  False if the network check failed or a critical sync error occurred
        """

        self.logger.info("💚 Heartbeat alive...")
        
        # --- Phase 1: Network Health Check ---

        # The primary goal is to rely solely on the result of 
        # get_public_ip() to determine the overall network health

        # Source of truth for connectivity

        # One full HTTPS request, if successful, the entire network stack 
        # (DNS resolution, routing, and application layer protocols) is functional

        self.detected_ip = get_public_ip()
        #self.detected_ip = "192.168.1.1"   # For testing only

        if self.detected_ip:
            self.logger.info(f"Internet OK | IP: {self.detected_ip}") 
            self.failed_ping_count = 0

            # Capture current time for the heartbeat log
            current_time_utc = datetime.now(timezone.utc).isoformat()
            current_time = to_local_time(current_time_utc)

            # Only update status with current heartbeat info (IP and time)
            # This is the high-frequency, minimum data update
            self.gsheets_service.update_status(
                ip_address=self.detected_ip,
                current_time=current_time,
                dns_last_modified=None   # Do not update
            )

            update_occurred = False   # Flag to track if the DNS was updated

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

                    # Persist the newly confirmed IP to local cache for next comparison
                    update_cloudflare_ip(self.detected_ip)
                    self.logger.info(f"Cache UPDATED: {cached_ip} → {get_cloudflare_ip()}")
                    self.logger.info("DNS synchronization completed successfully")

                    update_occurred = True   # Set flag

                elif update_result is None: 
                    # Update skipped (IP matched)
                    self.logger.info("DNS sync skipped (IP unchanged)")
                    # When skipped, the last_modified time is not guaranteed to be current, 
                    # but we proceed with logging the current system status

            except (RuntimeError, ValueError) as e:
                # Catch API/logic failures raised by CloudflareClient
                self.logger.error(f"DNS sync failed: {e}")
                return False
            except Exception as e:
                # Last-resort safeguard
                self.logger.exception(f"🔥 Unexpected fatal failure during DNS sync: {e}")
                return False

            # Update Google Sheets
            if update_occurred:

                # Update status with the DNS modification time
                # This is the low-frequency, audit-logging update
                self.gsheets_service.update_status(
                    ip_address=None,   # Ignore, previously updated
                    current_time=None, # Ignore, previously updated
                    dns_last_modified=self.dns_last_modified   # The new value
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
        