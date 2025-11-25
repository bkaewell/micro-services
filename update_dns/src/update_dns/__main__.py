import time
import logging

from .config import Config
from .agent import NetworkWatchdog
from .sanity import run_sanity_checks
from .logger import get_logger, setup_logging


def main_loop(watchdog: NetworkWatchdog, interval: int):
    """Supervisor loop running once per configured interval."""
    # Use the logger instance that was already configured in main()
    logger = get_logger("main_loop") 

    while True:
        try:
            watchdog.run_cycle()
        except Exception as e:
            logger.exception(f"Fatal error: {e}")

        logger.debug(f"Preparing to sleep for {interval} seconds...")
        time.sleep(interval)
        logger.debug("Waking up and starting next cycle immediately\n\n\n")


def main():
    """
    Entry point for the network maintenance application

    Configures logging and starts the supervisor loop
    """
    # ONE-TIME LOGGING SETUP (Always runs first)
    if Config.DEBUG_ENABLED:
        setup_logging(level=logging.DEBUG)
    else:
        setup_logging()
        
    logger = get_logger("main")

    # CONFIGURATION AND SANITY CHECKS (before the loop starts)
    run_sanity_checks()

    # INITIALIZE CORE COMPONENTS
    # Load interval from Config/ENV if applicable (e.g., Config.APP.INTERVAL)
    #cycle_interval = Config.APP.INTERVAL if hasattr(Config.APP, 'INTERVAL') else 60
    watchdog = NetworkWatchdog()
    cycle_interval = 10
    
    logger.info("🚀 Starting network maintenance cycle...")
    
    # START LOOP, PASSING INITIALIZED COMPONENTS
    main_loop(watchdog, cycle_interval)


if __name__ == "__main__":
    main()
