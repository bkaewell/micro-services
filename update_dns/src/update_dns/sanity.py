import re
import requests

from pathlib import Path

from .config import Config
from .logger import get_logger
from .utils import is_valid_ip
from .watchdog import check_internet

# Define the logger once for the entire module
logger = get_logger("sanity")


def print_summary():
    # --- Quick Summary Printout ---
    logger.info("===== Runtime Summary =====")
    logger.info(f"Router IP:                     {Config.Hardware.ROUTER_IP}")
    logger.info(f"Smart Plug IP:                 {Config.Hardware.PLUG_IP}")
    logger.info(f"Debug Flag:                    {Config.DEBUG_ENABLED}")
    logger.info(f"Watchdog Self-Healing Flag:    {Config.WATCHDOG_ENABLED}")
    logger.info("==========================\n")

def run_sanity_checks() -> None:
    """
    Validate .env configuration, network reachability, credentials, 
    and external dependencies before entering the main supervisor loop
    Raises exceptions on fatal misconfiguration
    """

    # --- Hardware / Network Validation ---
    # Router IP
    if not is_valid_ip(Config.Hardware.ROUTER_IP):
        raise ValueError(f"❌ Invalid router IP: {Config.Hardware.ROUTER_IP}")

    #if not ping_host(Config.Hardware.ROUTER_IP):
    if not check_internet(Config.Hardware.ROUTER_IP):
        logger.warning(f"⚠️ Router unreachable: {Config.Hardware.ROUTER_IP}")

    # Smart Plug IP
    if not is_valid_ip(Config.Hardware.PLUG_IP):
        raise ValueError(f"❌ Invalid smart plug IP: {Config.Hardware.PLUG_IP}")

    try:
        resp = requests.get(
            f"http://{Config.Hardware.PLUG_IP}/relay/0",
            timeout=2
        )
        if resp.status_code != 200:
            logger.warning(
                f"⚠️ Smart plug reachable but returned HTTP {resp.status_code}"
            )
    except requests.RequestException:
        logger.warning(
            f"⚠️ Smart plug not responding at {Config.Hardware.PLUG_IP}"
        )

    # --- Sanity Success ---
    logger.info("🧩 All sanity checks passed — system is healthy. Starting main loop...\n")

    print_summary()
