import os
import time
import requests

# =============== CONFIG ================
PLUG_IP = "192.168.0.150"   # Shelly plug static IP
CHECK_HOST = "8.8.8.8"      # Google DNS (reliable ping target)
REBOOT_DELAY = 3            # seconds
# REBOOT_DELAY = 30            # seconds
# =======================================

def check_internet(host: str = None) -> bool:
    # Ping a host to verify internet connectivity
    target = host or CHECK_HOST
    return os.system(f"ping -c 1 -W 2 {target} > /dev/null 2>&1") == 0

def reset_smart_plug() -> bool:
    try:
        off_resp = requests.get(f"http://{PLUG_IP}/relay/0?turn=off", timeout=3)
        time.sleep(REBOOT_DELAY)
        on_resp = requests.get(f"http://{PLUG_IP}/relay/0?turn=on", timeout=3)

        if off_resp.ok and on_resp.ok:
            print("Router power restored")
            return True
        else:
            print("Failed to toggle plug state properly")
            return False
    
    except Exception as e:
        print("Error communicating with plug:", e)
        return False
