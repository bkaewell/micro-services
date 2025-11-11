import time

from .agent import NetworkWatchdog


# Supervisor loop running once per minute
# def main_loop(interval: int = 60):
def main_loop(interval: int = 5):
    
    watchdog = NetworkWatchdog()

    while True:
        watchdog.run_cycle()
        time.sleep(interval)

if __name__ == "__main__":
    main_loop()
