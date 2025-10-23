import os
import time
import requests

# ---------------- CONFIG ----------------
PLUG_IP = "192.168.0.150"   # Shelly plug static IP
CHECK_HOST = "8.8.8.8"      # reliable ping target
#CHECK_INTERVAL = 60         # seconds
CHECK_INTERVAL = 5         # seconds
REBOOT_DELAY = 3            # seconds
# ---------------------------------------

def internet_is_up():
    return os.system(f"ping -c 1 -W 2 {CHECK_HOST} > /dev/null 2>&1") == 0

def reboot_plug():
    print("❌ Internet DOWN — rebooting router...")
    try:
        requests.get(f"http://{PLUG_IP}/relay/0?turn=off", timeout=3)
        time.sleep(REBOOT_DELAY)
        requests.get(f"http://{PLUG_IP}/relay/0?turn=on", timeout=3)
        print("Router power restored.")
    except Exception as e:
        print("Error communicating with plug:", e)

def main():
    print("Starting Internet Watchdog...")
    while True:
        if internet_is_up():
            print("✅ Internet UP")
        else:
            reboot_plug()
            # wait a bit to allow devices to come back online
            #time.sleep(60)
            time.sleep(CHECK_INTERVAL)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
