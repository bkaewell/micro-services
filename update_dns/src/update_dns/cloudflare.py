import json
import requests

from .config import Config
from .logger import get_logger
from .utils import to_local_time
from .cache import get_cloudflare_ip, update_cloudflare_ip

# Define the logger once for the entire module
logger = get_logger("cloudflare")


def sync_dns(self):
    """ 
    Add Doc Strings
    """
    logger = get_logger("cloudflare")
    logger.info("Entering Cloudflare script...")

    # Get IP from local cache
    cached_ip = get_cloudflare_ip()
    logger.info(f"cached_ip={cached_ip}")

    if cached_ip != self.detected_ip:
        logger.info("Cached IP does NOT match detected IP")

        api_base_url = self.config_cloudflare.API_BASE_URL
        api_token = self.config_cloudflare.API_TOKEN
        zone_id = self.config_cloudflare.ZONE_ID
        dns_name = self.config_cloudflare.DNS_NAME
        record_type = "A"   # Assume IPv4

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type" : "application/json",
        }

        # Collection Resource Endpoint (Read Operation)
        # Used with GET to query a list of DNS records filtered by name and type
        # Purpose: Extract the unique 'record_id' from the first record in the list
        list_url = f"{api_base_url}/zones/{zone_id}/dns_records?name={dns_name}&type={record_type}"
        try:
            resp = requests.get(list_url, headers=headers, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            #raise RuntimeError(f"Failed to fetch DNS record: {e}")
            logger.error("Failed to fetch DNS record: {e}")

        # print(f"update_dns_record: DNS records URL: {list_url}")
        logger.info(f"DNS records URL: {list_url}")


        get_resp_data = resp.json()
        logger.info("DNS records JSON response:\n%s", json.dumps(get_resp_data, indent=2))

        records_list = get_resp_data.get("result") or []
        if not records_list:
            raise RuntimeError(f"No DNS record found for {dns_name} ({record_type})")

        # Get the first (and only) DNS record object from the list
        current_dns_record = records_list[0]         

        record_id = current_dns_record.get("id")
        dns_record_ip = current_dns_record.get("content")
        #dns_last_modified = current_dns_record.get("modified_on")

        # Single Resource Endpoint (Update Operation)
        # Used with PUT to modify the specific DNS record identified by 'record_id'
        update_url = f"{api_base_url}/zones/{zone_id}/dns_records/{record_id}"

        payload = {
            "type": record_type,
            "name": dns_name,
            "content": self.detected_ip,
            "ttl": 60,   # Time-to-Live 
            "proxied": False,   # Grey cloud (not proxied thru Cloudflare)
        }

        try:
            # Execute the PUT request
            resp = requests.put(update_url, headers=headers, json=payload, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to update DNS record: {e}")

        logger.info(f"Updated '{dns_name}': {dns_record_ip} → {self.detected_ip}")

        # Update cache and Network Watchdog class (only on successful HTTP PUT)
        if resp.ok:
            # The PUT response body contains the newly updated dns record
            put_resp_data = resp.json()

             # The 'result' field contains the single, updated record object directly
            new_dns_record = put_resp_data.get("result")

            if new_dns_record:
                # Extract the newly created 'modified_on' timestamp
                new_dns_modified_on = new_dns_record.get("modified_on")
                
                # Update the class member variable
                self.dns_last_modified = to_local_time(new_dns_modified_on)
                logger.info(f"DNS Update Successful | New modified_on: {self.dns_last_modified}")
            else:
                logger.warning("Successful PUT but could not extract new modified_on timestamp from response")
                # Use current time as default
                self.dns_last_modified = to_local_time()

            update_cloudflare_ip(self.detected_ip)
            logger.info(f"Updated cached IP | {self.detected_ip}")

    else:
        logger.info("IP unchanged, skipping...")
        logger.info("Cached IP matches detected IP, skipping...")

    return True
