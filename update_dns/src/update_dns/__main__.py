# --- Standard library imports ---
import sys
import time
import logging

# --- Project imports ---
from .config import Config
from .logger import get_logger, setup_logging
from .scheduling_policy import SchedulingPolicy
from .infra_agent import NetworkState, NetworkWatchdog


def main_loop(policy: SchedulingPolicy, watchdog: NetworkWatchdog):
    """
    Supervisor loop for continuous network monitoring and self-healing.

    This function repeatedly executes the `watchdog.run_cycle()` according to
    the schedule defined by `policy`. It handles exceptions, logs detailed
    network state, and enforces timing between cycles.

    Responsibilities:
        - Invoke the network watchdog to check LAN/WAN health.
        - Capture and return the resulting NetworkState for logging and metrics.
        - Handle unexpected exceptions gracefully, mapping them to NetworkState.ERROR.
        - Log the current network state with human-readable labels.
        - Respect the runtime scheduling policy (intervals, drift correction).
        - Sleep for the remaining interval time before the next cycle.

    Args:
        policy: SchedulingPolicy instance controlling loop timing.
        watchdog: NetworkWatchdog instance performing network checks
                  and self-healing actions.

    Notes:
        - NetworkState captures LAN/WAN/Router health and transient issues.
        - Logs include both state and sleep interval for observability.
        - Designed for 24/7 unattended operation with resilient recovery.    """

    logger = get_logger("main_loop")

    state = NetworkState.UNKNOWN

    while True:
        start = time.monotonic()
        
        try:
            state = watchdog.run_cycle()
        except Exception as e:
            logger.exception(f"Unhandled exception during run cycle: {e}")
            state = NetworkState.ERROR

        remaining = policy.next_sleep(time.monotonic() - start)
        #logger.info(f"💤 Scheduling ... {policy.effective_runtime_interval()}")
        logger.info(f"🛜 Network State [{state.label}]")
        logger.info(f"💤 Sleeping ... {remaining:.2f} s\n")
        time.sleep(remaining)

def main():
    """
    Entry point for the network maintenance application.

    Configures logging and starts the supervisor loop.
    """

    # Setup logging policy
    setup_logging(level=getattr(logging, Config.LOG_LEVEL))
    logger = get_logger("main")
    logger.info("🚀 Starting Cloudflare DNS Reconciliation Infra Agent")
    logger.debug(f"Python version: {sys.version}")

    # Policy
    policy = SchedulingPolicy()    

    # Core infra agent
    watchdog = NetworkWatchdog()
    
    main_loop(policy, watchdog)

if __name__ == "__main__":
    main()
