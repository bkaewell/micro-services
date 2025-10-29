import time

from .network_autopilot import run_cycle

#CHECK_INTERVAL = 60 # seconds
CHECK_INTERVAL = 5 # seconds


def main_loop():
    while True:
        run_cycle()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main_loop()
