import time
import logging

from .config import Config
from .agent import NetworkWatchdog
from .sanity import run_sanity_checks
from .logger import get_logger, setup_logging


def main_loop(
        watchdog: NetworkWatchdog, 
        interval: int = 60,
        buffer: float | None = None,
    ):
    """Supervisor loop running once per interval (seconds)"""

    # Use the logger instance that was already configured in main()
    logger = get_logger("main_loop")

    if buffer is None:
        buffer = interval * 0.10   # default 10% margin

    # Compute the threshold for detecting excessive sleep;
    # Actual sleep longer than this indicates a possible system anomaly
    threshold = interval + buffer

    while True:
        try:
            watchdog.run_cycle()
        except Exception as e:
            logger.exception(f"Unhandled exception during cycle: {e}")

        # Monitor the actual sleep time
        start = time.monotonic()
        time.sleep(interval)
        elapsed = time.monotonic() - start

        if elapsed > threshold:
            logger.warning(
                f"Sleep interval anomaly: actual sleep exceeded threshold " 
                f"({elapsed:.3f}s > {threshold:.3f}s)\n\n"
            )

            # Reconnect external services that rely on persistent connections/tokens
            # Rebuild the GSheets connection/auth
            watchdog.gsheets_service.reconnect()


def main():
    """
    Entry point for the network maintenance application

    Configures logging and starts the supervisor loop
    """
    # One-time logging setup
    if Config.DEBUG_ENABLED:
        setup_logging(level=logging.DEBUG)
    else:
        setup_logging()
    
    logger = get_logger("main")

    # Basic sanity checks
    run_sanity_checks()

    # Initialize core components
    watchdog = NetworkWatchdog()
    cycle_interval = Config.CYCLE_INTERVAL
    buffer = cycle_interval * 0.10   # default 10% margin for production
    
    # Start loop, passing initialized components
    logger.info("🚀 Starting network maintenance cycle...")
    main_loop(watchdog, cycle_interval, buffer)


if __name__ == "__main__":
    main()
