from .watchdog import check_internet, reset_smart_plug
from .cloudflare import sync_dns
from .utils import get_public_ip
# from .sheets import log_to_sheets
#from .db import log_metrics


def run_cycle():
    """
    Executes a single network maintenance cycle:
    1. Verify internet connectivity
    2. Detect current public IP
    3. Sync DNS to the detected public IP if connection is valid
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




    if internet_ok and detected_ip:
        print(f"main: Detected public IP: {detected_ip}")
        try:
            # Update DNS record
            sync_dns(detected_ip)
        except (RuntimeError, ValueError, NotImplementedError) as e:
            print(f"main: ⚠️ Failed to update DNS or upload to Google Sheets: {e}")
    else:
        print("main: ⚠️ Could not fetch a valid public IP; DNS record not updated.")
        # Reset smart plug if internet is down
        reset_smart_plug()


    # # Update Google Sheets
    # log_to_sheets(ip=detected_ip,
    #               internet_ok=internet_ok,
    #               dns_changed=dns_changed)

    # # Optional: log metrics to SQLite
    # log_metrics(ip=detected_ip,
    #             internet_ok=internet_ok,
    #             dns_changed=dns_changed)

