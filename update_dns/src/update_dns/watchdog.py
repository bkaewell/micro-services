import os
import time
import requests
from .config import Config
from .logger import get_logger


def check_internet(host: str="8.8.8.8") -> bool:
    """Ping a host (default: Google DNS 8.8.8.8) to verify internet connectivity"""
    return os.system(f"ping -c 1 -W 2 {host} > /dev/null 2>&1") == 0

def reset_smart_plug() -> bool:
    """Power-cycle the smart plug with response validation and controlled delays to allow
    the router and downstream network devices to fully reboot"""
    logger = get_logger("watchdog")
    router_ip = Config.Hardware.ROUTER_IP
    plug_ip = Config.Hardware.PLUG_IP
    reboot_delay = Config.Hardware.REBOOT_DELAY
    init_delay = Config.Hardware.INIT_DELAY

    try:
        # Power-cycle the smart plug with response validation. Each transition (OFF → ON)
        # is verified before continuing and controlled delays allow the Optical Network 
        # Terminal, router and Access Points to complete their boot sequences. This ensures 
        # the main loop only resumes once the network stack is expected to be healthy

        off_resp = requests.get(f"http://{plug_ip}/relay/0?turn=off", timeout=3)
        if not off_resp.ok:
            logger.error(f"❌ Failed to power OFF smart plug | HTTP status: {off_resp.status_code})")
            return False

        logger.info(f"🕒 Waiting {reboot_delay}s for power-down...")
        time.sleep(reboot_delay)

        on_resp = requests.get(f"http://{plug_ip}/relay/0?turn=on", timeout=3)
        if not on_resp.ok:
            logger.error(f"❌ Failed to power ON smart plug | HTTP status: {on_resp.status_code})")
            return False        
        
        logger.info(f"🕒 Waiting {init_delay}s for network devices to come online...")
        time.sleep(init_delay)

        # Verify the router is back online
        for attempt in range(5):
            #if ping_host(router_ip):
            if check_internet(router_ip):
                logger.info(f"🌐 Router reachable after {attempt + 1} checks")
                return True
            time.sleep(3)

        logger.error("🚫 Router not reachable after reset attempt")
        return False

    except requests.exceptions.RequestException:
        logger.exception("⚠️ Network error communicating with smart plug")
        return False
    except Exception:
        logger.exception("⚠️ Unexpected error during smart plug reset")
        return False
