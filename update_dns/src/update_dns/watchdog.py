import os
import time
import requests
from .config import Config

from datetime import datetime



def check_internet(host: str="8.8.8.8") -> bool:
    """Ping a host (default: Google DNS 8.8.8.8) to verify internet connectivity"""
    return os.system(f"ping -c 1 -W 2 {host} > /dev/null 2>&1") == 0


def reset_smart_plug() -> bool:
    """Toggle smart plug off/on to reset power then wait for devices to reinitialize"""
    ip = Config.Hardware.PLUG_IP
    reboot_delay = Config.Hardware.REBOOT_DELAY
    init_delay = Config.Hardware.INIT_DELAY

    try:

        # Power cycle the smart plug to recover network connectivity
        # After restoring power, allow time for all connected devices (ONT, router, APs)
        # to fully initialize before continuing the main loop
        off_resp = requests.get(f"http://{ip}/relay/0?turn=off", timeout=3)
        time.sleep(reboot_delay)

        on_resp = requests.get(f"http://{ip}/relay/0?turn=on", timeout=3)
        time.sleep(init_delay)

        if off_resp.ok and on_resp.ok:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] - watchdog - Router power restored")
            return True
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] - watchdog - ⚠️ Failed to toggle plug state properly")
            return False
    
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] - watchdog - ⚠️ Error communicating with plug:", e)
        return False
