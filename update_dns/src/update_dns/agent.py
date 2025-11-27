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

    The main loop (run_cycle) executes the following sequence:
    1. Check network health by attempting to detect the current public IP
    2. If successful, update the cached public IP and proceed to DNS synchronization
    3. Compare the detected IP with the DNS record settings (hosted in Cloudflare)
    4. If the IP has changed, update the Cloudflare 'A' record (IPv4 address)
    5. Update the status log in the Google Sheet
    6. If public IP detection fails, track consecutive failures
    7. If consecutive failures exceed a defined threshold (i.e., 3 attempts), 
       trigger the self-healing process to power-cycle the smart plug 
       (if the watchdog flag is enabled)
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
        #self.dns_name = Config.Cloudflare.DNS_NAME


    def run_cycle(self):
        """
        Executes the main monitoring and update logic: Checks network,
        syncs DNS, and updates the status log
        """

        self.logger.info("💚 Heartbeat alive...")
        
        # --- Phase 1: Network Health Check ---

        # The primary goal is to rely solely on the result of 
        # get_public_ip() to determine the overall network health

        # Source of truth for connectivity

        # One full HTTPS request, if successful, the entire network stack 
        # (DNS resolution, routing, and application layer protocols) is functional

        detected_ip = get_public_ip()
        self.detected_ip = detected_ip   # Store for Cloudflare update

        # The Internet is OK if and only if we have a detected IP string
        internet_ok = bool(detected_ip)

        if internet_ok:
            self.logger.info(f"Internet OK | IP: {detected_ip}") 
            self.failed_ping_count = 0

            # --- Phase 2: Core Task (DNS update and status log) ---
            try:
                # Get cached IP to pass to the client
                #cached_ip = self.cloudflare_client.get_cloudflare_ip() 
                cached_ip = get_cloudflare_ip()
                
                # Call the dedicated client method
                update_result = self.cloudflare_client.sync_dns(
                    detected_ip=self.detected_ip,
                    cached_ip=cached_ip
                )
                
                # Handle Update Data / Success or Skip
                if update_result:
                    # Update occurred (update_result is the new record dict)
                    new_modified_on = update_result.get('modified_on')
                    self.dns_last_modified = to_local_time(new_modified_on)
                    update_cloudflare_ip(self.detected_ip)
                    self.logger.info("DNS synchronization completed successfully")
                    
                elif update_result is None: 
                    # Update skipped (IP matched)
                    self.logger.info("DNS sync skipped (IP unchanged)")
                    # When skipped, the last_modified time is not guaranteed to be current, 
                    # but we proceed with logging the current system status




                # # Handle Update Data / Success
                # # The client should return a dict containing the new 'modified_on' timestamp
                # if update_data and update_data.get('modified_on'):
                #     # Update the NetworkWatchdog's state with the result
                #     self.dns_last_modified = update_data['modified_on']
                #     self.logger.info("DNS synchronization handled successfully")
                # elif update_data is not None: 
                #     # Case where IP matched and update was skipped (update_data might be {} or specific skip signal)
                #     self.logger.info("DNS sync skipped (IP unchanged)")


            except (RuntimeError, ValueError) as e:
                # Catch API/logic failures raised by CloudflareClient
                self.logger.error(f"DNS sync failed: {e}")
                return False
            except Exception as e:
                # Last-resort safeguard
                self.logger.exception(f"🔥 Unexpected fatal failure during DNS sync: {e}")
                return False


            # Future code
            # Update Google Sheets

            # self.gsheets_service.append_ip_log(
            #     ip_address=self.detected_ip, 
            #     hostname=os.environ.get("HOSTNAME", "local")
            # )
            


            # self.gsheets_service.update_status(
            #     self.dns_name, 
            #     self.dns_last_modified, 
            #     self.detected_ip
            # )

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
        

        # log_to_sheets(ip=detected_ip,
        #               internet_ok=internet_ok,
        #               dns_changed=dns_changed)

        # Optional: log metrics to SQLite
        # log_metrics(ip=detected_ip,
        #             internet_ok=internet_ok,
        #             dns_changed=dns_changed)
        
