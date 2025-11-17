import time

from .agent import NetworkWatchdog
from .logger import setup_logging, get_logger


# Supervisor loop running once per minute
# def main_loop(interval: int = 60):
def main_loop(interval: int = 60):
    watchdog = NetworkWatchdog()

    # Safe loop for continuous running
    while True:
        try:
            watchdog.run_cycle()
        except Exception as e:
            logger.exception(f"Fatal error: {e}")
        time.sleep(interval)

def main():
    # Configure global logger once
    setup_logging()  
    logger = get_logger("main")
    logger.info("🚀 Starting network maintenance cycle...")

    #main_loop(interval=60)
    main_loop(interval=5)

if __name__ == "__main__":
    main()
