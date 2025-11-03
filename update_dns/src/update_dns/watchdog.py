import os
import time
import requests

# =============== CONFIG ================
PLUG_IP = "192.168.0.150"   # Shelly plug static IP
CHECK_HOST = "8.8.8.8"      # Google DNS (reliable ping target)
REBOOT_DELAY = 3            # seconds
# REBOOT_DELAY = 30            # seconds
# =======================================

def check_internet():
    return os.system(f"ping -c 1 -W 2 {CHECK_HOST} > /dev/null 2>&1") == 0

def reset_smart_plug():
    try:
        requests.get(f"http://{PLUG_IP}/relay/0?turn=off", timeout=3)
        time.sleep(REBOOT_DELAY)
        requests.get(f"http://{PLUG_IP}/relay/0?turn=on", timeout=3)
        print("Router power restored")
    except Exception as e:
        print("Error communicating with plug:", e)

