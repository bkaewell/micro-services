import json
import requests

from .config import Config
from .logger import get_logger
from .cache import get_cloudflare_ip, update_cloudflare_ip

# Define the logger once for the entire module
logger = get_logger("cloudflare")


def sync_dns(self):

    logger = get_logger("cloudflare")    # Keep here or use agent's NetworkWatchdog's class member 'self' ??
    logger.info("Entering Cloudflare script...")


    # Get IP from local cache
    cached_ip = get_cloudflare_ip()
    logger.info(f"cached_ip={cached_ip}")

    if cached_ip != self.detected_ip:
        logger.info("Cached IP does NOT match detected IP")
        logger.critical(f" ... {self.config_cloudflare}")

        api_base_url = self.config_cloudflare.API_BASE_URL
        api_token = self.config_cloudflare.API_TOKEN
        zone_id = self.config_cloudflare.ZONE_ID
        dns_name = self.config_cloudflare.DNS_NAME
        record_type = "A"   # Assume IPv4

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type" : "application/json",
        }

        # COLLECTION RESOURCE ENDPOINT (Read Operation)
        # Used with GET to query the collection of DNS records, filtered by name and type
        # Purpose: Extract the unique 'record_id' needed for the update operation
        list_url = f"{api_base_url}/zones/{zone_id}/dns_records?name={dns_name}&type={record_type}"
        try:
            resp = requests.get(list_url, headers=headers, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            #raise RuntimeError(f"Failed to fetch DNS record: {e}")
            logger.error("Failed to fetch DNS record: {e}")

        # print(f"update_dns_record: DNS records URL: {list_url}")
        logger.info(f"DNS records URL: {list_url}")


        data = resp.json()
        logger.info("DNS records JSON response:\n%s", json.dumps(data, indent=2))

        records = data.get("result") or []
        if not records:
            raise RuntimeError(f"No DNS record found for {dns_name} ({record_type})")

        record = records[0]  # The Cloudflare API returns a list; we take the first
        record_id = record.get("id")
        dns_record_ip = record.get("content")
        dns_last_modified = record.get("modified_on")
        logger.info(
            "record_id=%s dns_record_ip=%s dns_last_modified=%s",
            record_id, dns_record_ip, dns_last_modified
        )

        # SINGLE RESOURCE ENDPOINT (Update Operation)
        # Used with PUT/PATCH to target a specific resource using its unique identifier
        # Requires the 'record_id' discovered in the preceding GET request
        update_url = f"{api_base_url}/zones/{zone_id}/dns_records/{record_id}"

        payload = {
            "type": record_type,
            "name": dns_name,
            "content": self.detected_ip,
            "ttl": 60,   # Time-to-Live 
            "proxied": False,   # Grey cloud (not proxied thru Cloudflare)
        }

        try:
            resp = requests.put(update_url, headers=headers, json=payload, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to update DNS record: {e}")

        logger.info(f"Updated '{dns_name}': {dns_record_ip} → {self.detected_ip}")

        # Update local cache (only on successful HTTP PUT)
        if resp.ok:
            update_cloudflare_ip(self.detected_ip)
            logger.info(f"Updated cached IP | {self.detected_ip}")

        # UPDATE SELF class member variable to pass to Google Sheets??????????????????

    else:
        logger.info("IP unchanged, skipping...")
        logger.info("Cached IP does match detected IP, skipping...")
        # UPDATE SELF class member variable to pass to Google Sheets??????????????????

        ####################################################################
        # Does heartbeat (1 min) help verify internet health by updating google sheet with a timestamp
        # once per minute????
        ####################################################################






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

    return True
