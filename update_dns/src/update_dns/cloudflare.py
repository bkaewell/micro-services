import json
import requests

from .config import Config
from .logger import get_logger
from .cache import get_cloudflare_ip, update_cloudflare_ip

def sync_dns(self):

    logger = get_logger("cloudflare")

    # Get IP from local cache
    cached_ip = get_cloudflare_ip()
    logger.info(f"cached_ip={cached_ip}")



    # Case A: Initial Run (No Cache File Exists)
    # On the very first run, get_cloudflare_ip() will return "". This ensures:

    # The comparison (detected_ip == cached_ip) is False

    # The Cloudflare API is queried to find the record_id and the existing IP

    # If the existing Cloudflare IP does not match the detected IP (which is likely if the IP is dynamic), the PUT request runs

    # Crucially: After the successful PUT request, you must call update_cloudflare_ip(detected_ip) to create the cache file

    # Case B: Subsequent Runs (IP Has Changed)
    # get_cloudflare_ip() returns the old IP from the file

    # If detected_ip != old_ip, the PUT request runs

    # Crucially: After the successful PUT request, you call update_cloudflare_ip(detected_ip)





    # Update local cache (only on successful HTTP PUT)
    update_cloudflare_ip(self.detected_ip)
    logger.info(f"self.detected_ip={self.detected_ip}")

