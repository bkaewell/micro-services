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
    logger.info(f"Router IP:                     {Config.Hardware.ROUTER_IP}")
    logger.info(f"Smart Plug IP:                 {Config.Hardware.PLUG_IP}")
    logger.info(f"Cloudflare DNS Name:           {Config.Cloudflare.DNS_NAME}")
    logger.info(f"Cloudflare Zone ID:            {Config.Cloudflare.ZONE_ID}")
    logger.info(f"Running in Docker:             {Config.RUNNING_IN_DOCKER}")
    logger.info(f"Debug Flag:                    {Config.DEBUG_ENABLED}")
    logger.info(f"Watchdog Self-Healing Flag:    {Config.WATCHDOG_ENABLED}")
    #logger.info(f"Google API Key Path:           {creds_path}")
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



# import requests
# from pathlib import Path
# from update_dns.config import Config
# from update_dns.logger import get_logger
# from update_dns.utils import is_valid_ip, check_internet


# def run_sanity_checks() -> None:
#     """
#     Validate .env configuration, network reachability, credentials, and 
#     external dependencies before starting the main supervisor loop.
#     Raises exceptions on fatal issues — warnings for non-critical states.
#     """

#     logger = get_logger("sanity")

#     # ============================================================
#     # 1) --- Cloudflare Validation ---
#     # ============================================================
#     validate_cloudflare_config()

#     # ============================================================
#     # 2) --- Google API Credentials Validation ---
#     # ============================================================
#     validate_google_config()

#     # ============================================================
#     # 3) --- Hardware / Local Network Validation ---
#     # ============================================================
#     validate_router_config()
#     validate_smart_plug_config()
#     validate_delays()

#     # ============================================================
#     # 4) --- System Configuration Validation ---
#     # ============================================================
#     validate_timezone()
#     validate_debug_flag()

#     # ============================================================
#     # All checks passed
#     # ============================================================
#     logger.info("🧩 All sanity checks passed — system is healthy. Starting main loop...")

#     print_summary()


# # ==================================================================
# # Cloudflare
# # ==================================================================
# def validate_cloudflare_config():
#     if not Config.Cloudflare.API_BASE_URL:
#         raise ValueError("❌ Missing CLOUDFLARE_API_BASE_URL")

#     if not Config.Cloudflare.API_TOKEN:
#         raise ValueError("❌ Missing CLOUDFLARE_API_TOKEN")

#     if not Config.Cloudflare.ZONE_ID:
#         raise ValueError("❌ Missing CLOUDFLARE_ZONE_ID")

#     if not Config.Cloudflare.DNS_NAME:
#         raise ValueError("❌ Missing CLOUDFLARE_DNS_NAME")


# # ==================================================================
# # Google
# # ==================================================================
# def validate_google_config():
#     logger = get_logger("sanity")

#     if not Config.Google.SHEET_NAME:
#         raise ValueError("❌ Missing GOOGLE_SHEET_NAME")

#     if not Config.Google.WORKSHEET:
#         raise ValueError("❌ Missing GOOGLE_WORKSHEET")

#     # Docker-aware credential path
#     if Config.RUNNING_IN_DOCKER:
#         creds_path = Path(Config.Google.API_KEY_DOCKER)
#     else:
#         creds_path = Path(Config.Google.API_KEY_LOCAL).expanduser()

#     if not creds_path.exists():
#         raise FileNotFoundError(f"❌ Google API key not found at: {creds_path}")

#     logger.debug(f"Google API key found at: {creds_path}")


# # ==================================================================
# # Hardware
# # ==================================================================
# def validate_router_config():
#     logger = get_logger("sanity")
#     ip = Config.Hardware.ROUTER_IP

#     if not is_valid_ip(ip):
#         raise ValueError(f"❌ Invalid ROUTER_IP: {ip}")

#     if not check_internet(ip):
#         logger.warning(f"⚠️ Router appears unreachable: {ip}")


# def validate_smart_plug_config():
#     logger = get_logger("sanity")
#     ip = Config.Hardware.PLUG_IP

#     if not is_valid_ip(ip):
#         raise ValueError(f"❌ Invalid PLUG_IP: {ip}")

#     try:
#         resp = requests.get(f"http://{ip}/relay/0", timeout=2)
#         if resp.status_code != 200:
#             logger.warning(f"⚠️ Smart plug reachable but returned HTTP {resp.status_code}")
#     except requests.RequestException:
#         logger.warning(f"⚠️ Smart plug not responding at {ip}")


# def validate_delays():
#     if Config.Hardware.REBOOT_DELAY < 1:
#         raise ValueError("❌ REBOOT_DELAY must be a positive integer")

#     if Config.Hardware.INIT_DELAY < 1:
#         raise ValueError("❌ INIT_DELAY must be a positive integer")


# # ==================================================================
# # System
# # ==================================================================
# def validate_timezone():
#     tz = Config.System.TZ
#     if not tz or "/" not in tz:
#         raise ValueError(f"❌ Invalid timezone format: {tz}")


# def validate_debug_flag():
#     # DEBUG_ENABLED already defaults to False if wrong; no error required.
#     raw = str(Config.DEBUG_ENABLED).lower()
#     if raw not in ("true", "false"):
#         # Only warn, do not fail.
#         logger = get_logger("sanity")
#         logger.warning(f"⚠️ DEBUG_ENABLED unusual value: {raw} (expected true/false)")


# # ==================================================================
# # Summary Display
# # ==================================================================
# def print_summary():
#     print("\n================= Configuration Summary =================")
#     print(f"🌐 Cloudflare:")
#     print(f"    Base URL:       {Config.Cloudflare.API_BASE_URL}")
#     print(f"    Zone ID:        {Config.Cloudflare.ZONE_ID}")
#     print(f"    DNS Name:       {Config.Cloudflare.DNS_NAME}")

#     print("\n📊 Google Sheets:")
#     print(f"    Sheet Name:     {Config.Google.SHEET_NAME}")
#     print(f"    Worksheet:      {Config.Google.WORKSHEET}")
#     print(f"    Using Docker?:  {Config.RUNNING_IN_DOCKER}")
#     print(
#         f"    Creds Path:     "
#         f"{Config.Google.API_KEY_DOCKER if Config.RUNNING_IN_DOCKER else Config.Google.API_KEY_LOCAL}"
#     )

#     print("\n💻 Hardware:")
#     print(f"    Router IP:      {Config.Hardware.ROUTER_IP}")
#     print(f"    Smart Plug IP:  {Config.Hardware.PLUG_IP}")
#     print(f"    Reboot Delay:   {Config.Hardware.REBOOT_DELAY} sec")
#     print(f"    Init Delay:     {Config.Hardware.INIT_DELAY} sec")

#     print("\n⚙️ System:")
#     print(f"    Timezone:       {Config.System.TZ}")
#     print(f"    Debug Enabled:  {Config.DEBUG_ENABLED}")
#     print("=========================================================\n")
