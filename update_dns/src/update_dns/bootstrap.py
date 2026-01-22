# ─── Project imports ───
from .config import config
from .utils import ping_host
from .logger import get_logger


logger = get_logger("bootstrap")

def validate_runtime_config() -> None:
    """
    Validate runtime configuration and surface misconfiguration early.

    This performs two classes of checks:
    1. Hard invariants that would make the control loop nonsensical.
    2. Soft environmental checks (reachability) that may self-heal.
    """

    _validate_invariants()
    _validate_reachability()

def _validate_invariants() -> None:
    """
    Validate logical invariants of the control loop.

    Violations indicate a configuration that cannot behave correctly
    and should fail fast at startup.
    """

    slow_poll_interval_s = (
        config.CYCLE_INTERVAL_S * config.SLOW_POLL_SCALAR
    )
    min_useful_cache_age_s = slow_poll_interval_s
    assert config.MAX_CACHE_AGE_S >= min_useful_cache_age_s, (
        "MAX_CACHE_AGE_S is shorter than the steady-state polling interval; "
        "cache will expire before it can be reused"
    )

    # Warn-only: DNS propagation may lag control loop expectations
    if config.CLOUDFLARE_MIN_TTL_S > slow_poll_interval_s:
        logger.warning(
            f"Cloudflare minimum TTL ({config.CLOUDFLARE_MIN_TTL_S}s) exceeds " 
            f"slow polling interval ({slow_poll_interval_s}s); "
            f"DNS propagation may lag control-loop updates"
    )

def _validate_reachability() -> None:
    """
    Perform non-fatal reachability checks of local hardware.

    Failures are logged for visibility but do not prevent startup,
    as recovery mechanisms may restore connectivity.
    """
    router_ip = config.Hardware.ROUTER_IP
    plug_ip = config.Hardware.PLUG_IP

    if ping_host(router_ip):
        logger.info(f"Router reachable at startup ({router_ip})")
    else:
        logger.warning(f"Router NOT reachable at startup ({router_ip})")

    if ping_host(plug_ip):
        logger.info(f"Smart plug reachable at startup ({plug_ip})")
    else:
        logger.warning(f"Smart plug NOT reachable at startup ({plug_ip})")
