# ─── Standard library imports ───
from dataclasses import dataclass

# ─── Project imports ───
from .config import config
from .utils import ping_host
from .logger import get_logger


logger = get_logger("bootstrap")

from dataclasses import dataclass

@dataclass(frozen=True)
class EnvCapabilities:
    """
    Observed runtime capabilities derived at startup.

    These represent what the system is actually capable of doing,
    not what it is configured to do in theory.
    """
    physical_recovery_available: bool

def bootstrap() -> EnvCapabilities:
    """
    Validate runtime configuration and derive startup capabilities.

    Hard invariant violations raise and abort startup.
    Soft reachability checks are logged and used to gate capabilities.
    """

    _validate_invariants()
    return discover_runtime_capabilities()

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

    # # Warn-only: DNS propagation may lag control loop expectations
    # if config.CLOUDFLARE_MIN_TTL_S > slow_poll_interval_s:
    #     logger.warning(
    #         f"Cloudflare minimum TTL ({config.CLOUDFLARE_MIN_TTL_S}s) exceeds " 
    #         f"slow polling interval ({slow_poll_interval_s}s); "
    #         f"DNS propagation may lag control-loop updates"
    # )

def discover_runtime_capabilities() -> EnvCapabilities:
    """
    Perform non-fatal reachability checks of local hardware.

    Failures are logged for visibility but do not prevent startup,
    as recovery mechanisms may restore connectivity.
    Observations are used to derive runtime capabilities.
    """
    router_ip = config.Hardware.ROUTER_IP
    plug_ip = config.Hardware.PLUG_IP

    lan_reachable = ping_host(router_ip)
    if lan_reachable.success:
        logger.info(f"Router reachable at startup ({router_ip})")
    else:
        logger.warning(f"Router NOT reachable at startup ({router_ip})")

    plug_reachable = ping_host(plug_ip)
    if plug_reachable.success:
        logger.info(f"Smart plug reachable at startup ({plug_ip})")
    else:
        logger.warning(f"Smart plug NOT reachable at startup ({plug_ip})")

    physical_recovery_available = (
        config.ALLOW_PHYSICAL_RECOVERY and plug_reachable.success
    )

    if not physical_recovery_available:
        logger.warn(
            "Physical recovery disabled"
        )

    return EnvCapabilities(
        physical_recovery_available=physical_recovery_available
    )
