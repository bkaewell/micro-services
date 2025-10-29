from .watchdog import check_internet, reset_smart_plug
from .cloudflare import update_dns
# from .sheets import log_to_sheets
#from .db import log_metrics

def get_public_ip():
    return True

def run_cycle():
    # Check internet
    internet_ok = check_internet()

    # Reset smart plug if internet is down
    if not internet_ok:
        reset_smart_plug()

    # Get public IP address and update DNS
    current_ip = get_public_ip()
    dns_changed = update_dns(current_ip)

    print("Internet OK . . . . . . . . . .✅")



    # # Update Google Sheets
    # log_to_sheets(ip=current_ip,
    #               internet_ok=internet_ok,
    #               dns_changed=dns_changed)

    # # Optional: log metrics to SQLite
    # log_metrics(ip=current_ip,
    #             internet_ok=internet_ok,
    #             dns_changed=dns_changed)

