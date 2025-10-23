import os
import time
import requests

PLUG_IP = "192.168.0.150"   # Shelly plug static IP
#CHECK_INTERVAL = 60         # seconds
CHECK_INTERVAL = 5         # seconds

def internet_is_up():
    return os.system(f"ping -c 1 -W 2 8.8.8.8 > /dev/null 2>&1") == 0

def main():
    print("Starting Internet Watchdog...")
    while True:
        if internet_is_up():
            print("✅ Internet OK")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
