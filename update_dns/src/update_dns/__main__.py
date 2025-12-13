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
    """
    Supervisor loop running once per interval
    """

    logger = get_logger("main_loop")

    if buffer is None:
        buffer = interval * 0.10   # Default 10% margin

    # Compute the threshold for detecting a system suspension/wakeup event for 
    # recovery purposes. If the total elapsed time between cycle completions 
    # exceeds this value, it indicates the OS suspended the process (e.g., 
    # system sleep or hibernation).
    threshold = interval + buffer

    # Track the completion time of the previous cycle
    last_cycle_end = time.monotonic()   # Initialize to start time

    while True:
        # --- Detect System Anomaly BEFORE Running Cycle ---
        current_time = time.monotonic()
        
        # Calculate the total time elapsed since the loop finished its 
        # work/sleep in the prior iteration. Given the low latency, the work 
        # duration is typically less than 0.3 seconds, allowing the system to 
        # sleep for the remaining time (~59 seconds).
        elapsed_since_last_cycle = current_time - last_cycle_end

        if elapsed_since_last_cycle > threshold:
            logger.critical(
                f"Latency spike detected (nominal={interval}s): "
                f"elapsed=({elapsed_since_last_cycle:.1f}s) > "
                f"threshold=({threshold:.1f}s) - forcing service reconnect..."
            )

            # Reconnect services BEFORE each cycle to clear stale connections
            watchdog.gsheets_service.reconnect()

        # --- Run the Cycle ---
        try:
            watchdog.run_cycle()

        except Exception as e:
            logger.exception(f"Unhandled exception during run cycle: {e}")

        # --- Manage Timing and State Update ---
        
        # Calculate the required sleep delay based on the interval and latency 
        # of the current cycle time
        cycle_duration = time.monotonic() - current_time
        sleep_duration = max(0, interval - cycle_duration)
        logger.critical(f"💤 Sleep Duration: {sleep_duration:.2f}s\n\n")
        
        # Update the time marker to the time we finished the current cycle
        last_cycle_end = time.monotonic()
        
        # Sleep for the calculated remaining duration
        time.sleep(sleep_duration)


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
