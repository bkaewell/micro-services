# --- Project imports ---
from .config import config
from .utils import ping_host
from .logger import get_logger


logger = get_logger("bootstrap")

def validate_runtime_config() -> None:
    """
    Perform lightweight, non-fatal validation of runtime configuration.

    Verifies reachability of critical local devices to surface
    misconfiguration early. Failures are logged but do not
    prevent startup.
    """
    router_ip = config.Hardware.ROUTER_IP
    plug_ip = config.Hardware.PLUG_IP

    if ping_host(router_ip):
        logger.info("Router reachable at startup")
    else:
        logger.warning("Router NOT reachable at startup")

    if ping_host(plug_ip):
        logger.info("Smart plug reachable at startup")
    else:
        logger.warning("Smart plug NOT reachable at startup")
