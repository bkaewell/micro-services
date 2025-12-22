# --- Standard library imports ---
import sys
import time
import logging

# --- Project imports ---
from .config import Config
from .infra_agent import NetworkWatchdog
from .logger import get_logger, setup_logging
from .scheduling_policy import SchedulingPolicy


def main_loop(policy: SchedulingPolicy, watchdog: NetworkWatchdog):
    """
    Supervisor loop running once per interval.
    """

    logger = get_logger("main_loop")

    while True:
        start = time.monotonic()
        
        try:
            state = watchdog.run_cycle()
        except Exception as e:
            logger.exception(f"Unhandled exception during run cycle: {e}")

        remaining = policy.next_sleep(time.monotonic() - start)
        #logger.info(f"💤 Scheduling ... {policy.effective_runtime_interval()}")
        logger.info(f"🛜 State [{state}]")
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
