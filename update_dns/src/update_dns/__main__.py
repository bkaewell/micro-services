import time

from .agent import NetworkWatchdog
from .logger import setup_logging, get_logger


# Supervisor loop running once per minute
# def main_loop(interval: int = 60):
def main_loop(interval: int = 60):
    watchdog = NetworkWatchdog()

    while True:
        watchdog.run_cycle()
        time.sleep(interval)

def main():
    setup_logging()
    logger = get_logger("main")
    logger.info("🚀 Starting network maintenance cycle...")
    main_loop(interval=60)

if __name__ == "__main__":
    main()
