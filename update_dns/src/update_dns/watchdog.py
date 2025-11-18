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

        # Power-cycle OFF
        off_resp = requests.get(f"http://{plug_ip}/relay/0?turn=off", timeout=3)
        if not off_resp.ok:
            logger.error(f"Failed to power OFF smart plug | HTTP {off_resp.status_code})")
            return False

        logger.info(f"Waiting {reboot_delay}s after power-off...")
        time.sleep(reboot_delay)

        # Power-cycle ON
        on_resp = requests.get(f"http://{plug_ip}/relay/0?turn=on", timeout=3)
        if not on_resp.ok:
            logger.error(f"Failed to power ON smart plug | HTTP {on_resp.status_code})")
            return False        
        
        logger.info(f"Waiting {init_delay}s for network devices to reinitialize...")
        time.sleep(init_delay)

        # Verify the router is back online
        max_attempts = 5
        for attempt in range(max_attempts):
            if check_internet(router_ip):
                logger.info(f"Router is reachable on {attempt + 1}/{max_attempts} attempts")
                return True
            time.sleep(3)

        logger.error(f"Router unreachable after {max_attempts} attempts post-reset")
        return False

    except requests.exceptions.RequestException:
        logger.exception("Network error communicating with smart plug")
        return False
    except Exception:
        logger.exception("Unexpected error during smart plug reset")
        return False
