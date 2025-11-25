import time
import logging

from .config import Config
from .agent import NetworkWatchdog
from .sanity import run_sanity_checks
from .logger import get_logger, setup_logging


def main_loop(interval: int = 60):
    """Supervisor loop running once per minute"""
    logger = get_logger("main_loop")
    watchdog = NetworkWatchdog()

    # Safe loop for continuous running
    while True:
        try:
            watchdog.run_cycle()
        except Exception as e:
            logger.exception(f"?????????????Fatal error: {e}")

        logger.debug("Preparing to sleep for 60 seconds...")
        time.sleep(interval)
        logger.info("Waking up and starting next cycle immediately\n\n\n")


def main():
    """
    Entry point for the maintenance network application

    Configures logging based on DEBUG_ENABLED and starts the supervisor loop
    """

    if Config.DEBUG_ENABLED:
        setup_logging(level=logging.DEBUG)
    else:
        setup_logging()
    logger = get_logger("main")

    run_sanity_checks()

    logger.info("🚀 Starting network maintenance cycle...")
    # Start the supervisor loop
    main_loop(interval=60)
    #main_loop(interval=10)

if __name__ == "__main__":
    main()
