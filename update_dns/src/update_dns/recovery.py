import time
import requests

from .config import Config
from .logger import get_logger


logger = get_logger("watchdog")

def trigger_recovery() -> bool:
    """
    Execute a physical network recovery action by power-cycling
    the smart plug connected to the router/modem.

    This function performs NO health checks.
    All validation and escalation decisions are handled upstream
    by the network watchdog state machine.

    Returns:
        True if the power-cycle command sequence completed successfully,
        False otherwise.
    """
    plug_ip = Config.Hardware.PLUG_IP
    reboot_delay = Config.Hardware.REBOOT_DELAY

    try:
        # Power OFF
        off = requests.get(
            f"http://{plug_ip}/relay/0?turn=off", timeout=Config.API_TIMEOUT
        )
        off.raise_for_status()
        logger.info("🔌 Smart plug powered OFF")
        time.sleep(reboot_delay)

        # Power ON
        on = requests.get(
            f"http://{plug_ip}/relay/0?turn=on", timeout=Config.API_TIMEOUT
        )
        on.raise_for_status()
        logger.info("🔌 Smart plug powered ON")
        logger.info("♻️ Recovery sequence completed")
        return True

    except requests.RequestException:
        logger.exception("Failed to communicate with smart plug")
        return False
    except Exception:
        logger.exception("Unexpected error during recovery")
        return False
