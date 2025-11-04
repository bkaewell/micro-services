import time

from .agent import run_cycle


# Supervisor loop running once per minute
# def main_loop(interval: int = 60):
def main_loop(interval: int = 5):
    while True:
        run_cycle()
        time.sleep(interval)

if __name__ == "__main__":
    main_loop()
