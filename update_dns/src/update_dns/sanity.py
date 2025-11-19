import re
import requests

from pathlib import Path
from update_dns.config import Config
from update_dns.logger import get_logger
from update_dns.utils import is_valid_ip
from update_dns.watchdog import check_internet

logger = get_logger("sanity")

def print_summary():
    # --- Quick Summary Printout ---
    logger.info("===== Runtime Summary =====")
    logger.info(f"Router IP:              {Config.Hardware.ROUTER_IP}")
    logger.info(f"Smart Plug IP:          {Config.Hardware.PLUG_IP}")
    logger.info(f"Cloudflare DNS Name:    {Config.Cloudflare.DNS_NAME}")
    logger.info(f"Cloudflare Zone ID:     {Config.Cloudflare.ZONE_ID}")
    logger.info(f"Running in Docker:      {Config.RUNNING_IN_DOCKER}")
    logger.info(f"Google API Key Path:    {creds_path}")
    logger.info("==========================\n")

def run_sanity_checks() -> None:
    """
    Validate .env configuration, network reachability, credentials, 
    and external dependencies before entering the main supervisor loop.
    Raises exceptions on fatal misconfiguration.
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

    # --- Cloudflare Validation ---
    if not Config.Cloudflare.API_TOKEN:
        raise ValueError("❌ Missing CLOUDFLARE_API_TOKEN in .env")
    

    # --- Zone ID --- (Cloudflare Zone IDs are always 32-character lowercase hex
    zone = Config.Cloudflare.ZONE_ID
    if not zone:
        raise ValueError("❌ Missing CLOUDFLARE_ZONE_ID in .env")
    if not re.fullmatch(r"[a-f0-9]{32}", zone):
        raise ValueError(f"❌ Invalid Cloudflare Zone ID format: {zone}")


    if not Config.Cloudflare.DNS_NAME:
        raise ValueError("❌ Missing CLOUDFLARE_DNS_NAME in .env")
    




    # Determine path depending on Docker vs local
    creds_path = (
        Path(Config.Google.API_KEY_DOCKER)
        if Config.RUNNING_IN_DOCKER
        else Path(Config.Google.API_KEY_LOCAL).expanduser()
    )

    if not creds_path.exists():
        raise FileNotFoundError(
            f"❌ Google API key not found at: {creds_path}"
        )

    # --- Sanity Success ---
    logger.info("🧩 All sanity checks passed — system is healthy. Starting main loop...\n")

    print_summary()