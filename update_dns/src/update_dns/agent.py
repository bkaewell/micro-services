from .config import Config
from .logger import get_logger
from .cloudflare import sync_dns
from .utils import get_public_ip
from .watchdog import reset_smart_plug
from .google_sheets_service import GSheetsService 
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

        # Cloudflare
        self.config_cloudflare = Config.Cloudflare

        # Initialize the standalone GSheets Service
        self.gsheets_service = GSheetsService(
            config_google=Config.Google,
            sheet_name=Config.Google.SHEET_NAME,
            worksheet_name=Config.Google.WORKSHEET
        )

        # Outputs 
        self.detected_ip = ""                       # populated by utils.get_public_ip() via https://api.ipify.org
        self.dns_last_modified = ""                 # populated by sync_dns()
        self.dns_name = Config.Cloudflare.DNS_NAME  # populated by config.Config via .env


    def run_cycle(self):
        """ Executes the main monitoring and update logic """

        self.logger.info("💚 Heartbeat alive...")
        
        # --- Phase 1: Network Health Check ---

        # The primary goal is to rely solely on the result of 
        # get_public_ip() to determine the overall network health

        # Source of truth for connectivity

        # One full HTTPS request, if successful, the entire network stack 
        # (DNS resolution, routing, and application layer protocols) is functional

        detected_ip = get_public_ip()
        self.detected_ip = detected_ip   # Store for Cloudflare update

        # The Internet is OK if and only if we have a detected IP string.
        internet_ok = bool(detected_ip)

        if internet_ok:
            self.logger.info(f"Internet OK | IP: {detected_ip}") 
            self.failed_ping_count = 0

            # --- Phase 2: Core Task (DNS Update and Google Sheet Update) ---

            try:
                sync_dns(self)
                # print("DNS record synchronized successfully")
                self.logger.info("DNS record synchronized successfully.")
            except (RuntimeError, ValueError, NotImplementedError) as e:
                print("DNS sync failed", exc_info=e)
                # self.logger.error("DNS sync failed", exc_info=e)
                # self.logger.exception("🔥????")
            except Exception as e:
                # Last-resort safeguard for unexpected runtime failures
                print(f"Unexpected failure during DNS sync: {e}")
                # self.logger.exception(f"🔥 Unexpected failure during DNS sync: {e}")

            # Future code
            # Update Google Sheets

            # self.gsheets_service.append_ip_log(
            #     ip_address=self.detected_ip, 
            #     hostname=os.environ.get("HOSTNAME", "local")
            # )
            
            self.gsheets_service.update_status(ip_address=self.detected_ip)

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
        
