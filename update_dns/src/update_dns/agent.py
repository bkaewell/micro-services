from .watchdog import check_internet, reset_smart_plug
from .utils import get_public_ip
from .cloudflare import sync_dns
# from .sheets import log_to_sheets
#from .db import log_metrics


def run_cycle():
    """
    Executes a single network maintenance cycle:
    1. Verify internet connectivity
    2. Detect current public IP
    3. Update DNS record (hosted in Cloudflare) to point to the detected public IP
    4. Reset smart plug if connectivity fails
    """

    # --- Phase 1: Network Health Check ---
    internet_ok = check_internet()
    detected_ip = get_public_ip()

    if not internet_ok or not detected_ip:
        #logger.warning("No valid internet connection or public IP. Initiating fallback procedure.")
        print("No valid internet connection or public IP")
        #with suppress(Exception):
        reset_smart_plug()
        return
    
    #logger.info(f"Detected public IP: {detected_ip}")
    print(f"Detected public IP: {detected_ip}")

    # --- Phase 2: DNS Synchronization ---
    try:
        sync_dns(detected_ip)
        print("DNS record synchronized successfully")
        #logger.info("DNS record synchronized successfully.")
    except (RuntimeError, ValueError, NotImplementedError) as e:
        print("DNS sync failed", exc_info=e)
        #logger.error("DNS sync failed", exc_info=e)
    except Exception as e:
        # Last-resort safeguard for unexpected runtime failures
        #logger.exception(f"Unexpected failure during DNS sync: {e}")
        print(f"Unexpected failure during DNS sync: {e}")




    # # Update Google Sheets
    # log_to_sheets(ip=detected_ip,
    #               internet_ok=internet_ok,
    #               dns_changed=dns_changed)

    # # Optional: log metrics to SQLite
    # log_metrics(ip=detected_ip,
    #             internet_ok=internet_ok,
    #             dns_changed=dns_changed)

