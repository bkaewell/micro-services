import time

from .agent import NetworkWatchdog
from .logger import setup_logging, get_logger


def main_loop(interval: int = 60):
    """Supervisor loop running once per minute"""
    logger = get_logger("main_loop")
    watchdog = NetworkWatchdog()

    # Safe loop for continuous running
    while True:
        try:
            watchdog.run_cycle()
        except Exception as e:
            logger.exception(f"🔥 Fatal error: {e}")
        time.sleep(interval)

def main():
    """Entry point for the maintenance network application"""

    # Configure global logger once
    setup_logging()  
    logger = get_logger("main")
    logger.info("🚀 Starting network maintenance cycle...")

    # Start the supervisor loop
    #main_loop(interval=60)
    main_loop(interval=10)

if __name__ == "__main__":
    main()
