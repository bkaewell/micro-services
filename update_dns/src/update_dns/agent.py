from .config import Config
from .logger import get_logger
from .cloudflare import sync_dns
from .utils import get_public_ip
from .watchdog import check_internet, reset_smart_plug
# from .sheets import log_to_sheets
#from .db import log_metrics


class NetworkWatchdog:
    """
    Executes a single network maintenance cycle:
    1. Verify internet connectivity
    2. Detect current public IP
    3. Update DNS record (hosted in Cloudflare) to point to the detected public IP
    4. Track consecutive connectivity failures (up to 3 attempts)
    5. Reset smart plug automatically after 3 consecutive failed pings
    """
    
    #def __init__(self, host="8.8.8.8", max_consecutive_failures=3):
    def __init__(self, host="8.8.8.8", max_consecutive_failures=1):
        self.host = host
        self.max_consecutive_failures = max_consecutive_failures
        self.failed_ping_count = 0
        self.logger = get_logger("agent")

        self.detected_ip = ""
        self.dns_last_modified = ""
        self.dns_name = Config.Cloudflare.DNS_NAME

    def run_cycle(self):
        # --- Phase 1: Network Health Check ---
        self.logger.info("💚 Heartbeat alive...")

        internet_ok = check_internet(self.host)
        detected_ip = get_public_ip()

        if internet_ok and detected_ip:
            self.logger.info(f"Internet OK | IP: {detected_ip}") 
            self.failed_ping_count = 0
        else:
            self.failed_ping_count += 1
            self.logger.warning(f"Internet check failed ({self.failed_ping_count}/{self.max_consecutive_failures})")

            if self.failed_ping_count >= self.max_consecutive_failures:
                self.logger.error("Triggering smart plug reset...")
                if not reset_smart_plug():
                    self.logger.error("Smart plug reset failed")
                self.failed_ping_count = 0  # reset counter after attempting recovery
                return False

            return False
        
        # --- Phase 2: DNS Synchronization ---
        try:
            sync_dns(detected_ip)
            # print("✅ DNS record synchronized successfully")
            # self.logger.info("DNS record synchronized successfully.")
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
        # log_to_sheets(ip=detected_ip,
        #               internet_ok=internet_ok,
        #               dns_changed=dns_changed)

        # Optional: log metrics to SQLite
        # log_metrics(ip=detected_ip,
        #             internet_ok=internet_ok,
        #             dns_changed=dns_changed)
        
        return True
