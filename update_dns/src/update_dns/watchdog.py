import os
import time
import requests
from .config import Config


# def check_internet(host: str = None) -> bool:
#     """Ping a host to verify internet connectivity"""
#     CHECK_HOST = "8.8.8.8" # Google DNS (reliable ping target)
#     target = host or CHECK_HOST
#     return os.system(f"ping -c 1 -W 2 {target} > /dev/null 2>&1") == 0


def check_internet(host: str="8.8.8.8") -> bool:
    """Ping a host (default: Google DNS 8.8.8.8) to verify internet connectivity"""
    return os.system(f"ping -c 1 -W 2 {host} > /dev/null 2>&1") == 0

def reset_smart_plug() -> bool:
    """Toggle smart plug off/on to reset power"""
    ip = Config.Hardware.PLUG_IP
    delay = Config.Hardware.REBOOT_DELAY
    try:
        off_resp = requests.get(f"http://{ip}/relay/0?turn=off", timeout=3)
        time.sleep(delay)
        on_resp = requests.get(f"http://{ip}/relay/0?turn=on", timeout=3)

        if off_resp.ok and on_resp.ok:
            print("Router power restored")
            return True
        else:
            print("Failed to toggle plug state properly")
            return False
    
    except Exception as e:
        print("Error communicating with plug:", e)
        return False
