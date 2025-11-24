import os
import time
import requests
from .config import Config
from .logger import get_logger

# Watchdog module specifically designed to monitor the health of a primary system
# (internet connection and DNS service) and trigger a pre-defined recovery action
# (power-cylcing the smart plug) if the primary system stops responding

# Responsible for the self-healing and monitoring of the recovery



# def ping_host(host: str) -> bool:
#     """Return True if host responds to a single ping."""
#     try:
#         result = subprocess.run(
#             ["ping", "-c", "1", "-W", "1", host],
#             stdout=subprocess.DEVNULL,
#             stderr=subprocess.DEVNULL,
#         )
#         return result.returncode == 0
#     except Exception:
#         return False

# More robust ping checking...

# def check_internet() -> bool:
#     """Ping 8.8.8.8 three times fast — only fail if ALL three fail"""
#     for i in range(3):
#         # -c 1 = one packet, -W 2 = 2-second timeout
#         result = subprocess.run(
#             ["ping", "-c", "1", "-W", "2", "8.8.8.8"],
#             stdout=subprocess.DEVNULL,
#             stderr=subprocess.DEVNULL,
#         )
#         if result.returncode == 0:
#             return True
#         time.sleep(1 if i < 2 else 0)  # tiny pause between retries
#     return False


def check_internet(host: str="8.8.8.8") -> bool:
    """Ping a host (default: Google DNS 8.8.8.8) to verify network connectivity"""

    # This check uses ICMP (part of Layer 3/4) and is quick and low-resource
    return os.system(f"ping -c 1 -W 2 {host} > /dev/null 2>&1") == 0

def reset_smart_plug() -> bool:
    """
    Power-cycle the smart plug with response validation and controlled delays. 
    Verifies network recovery in two phases: Local Router and External Host
    """
    logger = get_logger("watchdog")
    router_ip = Config.Hardware.ROUTER_IP
    plug_ip = Config.Hardware.PLUG_IP
    reboot_delay = Config.Hardware.REBOOT_DELAY
    init_delay = Config.Hardware.INIT_DELAY

    # Define a reliable external host (Google DNS) for Layer 3 validation
    EXTERNAL_HOST = "8.8.8.8"

    try:
        # --- Phase 0: Smart Plug Power-Cycle ---
        # (Checks Layer 7 Application & Layer 4 Transport for local control)        

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

        max_attempts = 5

        # --- Phase 1: Verify Router (Local Network Link) ---
        # Checks if the router's Layer 3 (Network) stack is initialized on the LAN side
        logger.info("Attempting to verify router is back online (Local Check)...")
        router_reachable = False
        for attempt in range(max_attempts):
            if check_internet(router_ip):
                logger.info(f"Router is reachable ({attempt + 1}/{max_attempts} attempts)")
                router_reachable = True
                break
            time.sleep(3)
        
        if not router_reachable:
            logger.error(f"Router un-reachable after {max_attempts} attempts post-reset")
            return False

        # --- Phase 2: Verify External Connectivity (WAN Link) ---
        # Checks if the router has established its WAN link and can forward traffic (Layer 3)
        logger.info(f"Attempting to verify external access via {EXTERNAL_HOST} (WAN Check)...")
        for attempt in range(max_attempts):
            # Checking 8.8.8.8 confirms the WAN side is active and traffic is routable.
            if check_internet(EXTERNAL_HOST):
                logger.info(f"✅ External host ({EXTERNAL_HOST}) reachable ({attempt + 1}/{max_attempts} attempts)")
                return True # Success: Both local and external checks passed.
            time.sleep(3)
            
        logger.error(f"External host ({EXTERNAL_HOST}) unreachable after {max_attempts} attempts.")
        return False # Failure: Local network is up, but the ISP/Internet link is not.

    except requests.exceptions.RequestException:
        logger.exception("Network error communicating with smart plug")
        return False
    except Exception:
        logger.exception("Unexpected error during smart plug reset")
        return False
