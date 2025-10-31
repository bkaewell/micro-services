from .watchdog import check_internet, reset_smart_plug
from .cloudflare import sync_dns
# from .sheets import log_to_sheets
#from .db import log_metrics

def get_public_ip():
    return True

def run_cycle():

    #print("agent::run_cycle - Starting check_internet()...")
    # Check internet
    internet_status = check_internet()
    #print(f"agent::run_cycle - Leaving check_internet()...inter_ok={internet_status}")


    # Reset smart plug if internet is down
    if not internet_status:
        #print("agent::run_cycle - Starting reset_smart_plug() ❌ Internet DOWN...")
        reset_smart_plug()
        #print("agent::run_cycle - Leaving reset_smart_plug() ❌ Internet DOWN...")


    # Get public IP address and sync DNS
    current_ip = get_public_ip()
    dns_changed = sync_dns(current_ip)

    print("Internet OK . . . . . . . . . .✅")



    # # Update Google Sheets
    # log_to_sheets(ip=current_ip,
    #               internet_status=internet_status,
    #               dns_changed=dns_changed)

    # # Optional: log metrics to SQLite
    # log_metrics(ip=current_ip,
    #             internet_status=internet_status,
    #             dns_changed=dns_changed)

