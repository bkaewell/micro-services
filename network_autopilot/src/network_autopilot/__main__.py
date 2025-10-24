import time
from network_autopilot import network_autopilot

CHECK_INTERVAL = 60 #seconds

def main_loop():
    while True:
        network_autopilot.run_cycle()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main_loop()
