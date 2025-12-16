# --- Standard library imports ---
import time
import logging

# --- Project imports ---
from .config import Config
from .agent import NetworkWatchdog
from .logger import get_logger, setup_logging


def main_loop(
        watchdog: NetworkWatchdog, 
        interval: int = 60,
    ):
    """
    Supervisor loop running once per interval.
    """

    logger = get_logger("main_loop")

    while True:
        cycle_start = time.monotonic()
        
        # --- Run the Cycle ---
        try:
            watchdog.run_cycle()
        except Exception as e:
            logger.exception(f"Unhandled exception during run cycle: {e}")

        # --- Maintain Fixed Cycle Interval ---
        elapsed = time.monotonic() - cycle_start
        remaining = max(0.0, interval - elapsed)

        logger.info(f"💤 Sleeping ... {remaining:.2f} s\n")
        time.sleep(remaining)

def main():
    """
    Entry point for the network maintenance application.

    Configures logging and starts the supervisor loop.
    """

    # Setup logging policy
    if Config.LOG_LEVEL:
        setup_logging(level=getattr(logging, Config.LOG_LEVEL))
    else:
        setup_logging()
    logger = get_logger("main")

    # Initialize core components
    watchdog = NetworkWatchdog()
    
    # Start loop, passing initialized components
    logger.info("🚀 Starting network maintenance cycle...")
    main_loop(watchdog, Config.CYCLE_INTERVAL)

if __name__ == "__main__":
    main()
