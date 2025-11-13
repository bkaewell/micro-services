import os
import time
import requests
from .config import Config
from .logger import get_logger


def check_internet(host: str="8.8.8.8") -> bool:
    """Ping a host (default: Google DNS 8.8.8.8) to verify internet connectivity"""
    return os.system(f"ping -c 1 -W 2 {host} > /dev/null 2>&1") == 0

def reset_smart_plug() -> bool:
    """Toggle smart plug off/on to reset power then wait for devices to reinitialize"""
    logger = get_logger("watchdog")
    ip = Config.Hardware.PLUG_IP
    reboot_delay = Config.Hardware.REBOOT_DELAY
    init_delay = Config.Hardware.INIT_DELAY

    try:
        # Power cycle the smart plug to recover network connectivity
        # After restoring power, allow time for all connected devices 
        # (Optical Network Terminal, Router, APs) to fully initialize 
        # before continuing the main loop
        off_resp = requests.get(f"http://{ip}/relay/0?turn=off", timeout=3)
        time.sleep(reboot_delay)

        on_resp = requests.get(f"http://{ip}/relay/0?turn=on", timeout=3)
        time.sleep(init_delay)

        if off_resp.ok and on_resp.ok:
            logger.info("🔌 Router power restored and downstream devices initializing...")
            return True
        elif not off_resp.ok:
            logger.error(f"❌ Failed to power OFF smart plug (HTTP {off_resp.status_code})")
            return False
        elif not on_resp.ok:
            logger.error(f"❌ Failed to power ON smart plug (HTTP {on_resp.status_code})")
            return False
    
    except Exception as e:
        logger.exception("⚠️ Error communicating with smart plug")
        return False
