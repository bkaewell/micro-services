import requests

from .config import Config
from .logger import get_logger

def sync_dns(ip_address: str):

    logger = get_logger("cloudflare")

    api_base_url = Config.Cloudflare.API_BASE_URL
    api_token = Config.Cloudflare.API_TOKEN
    zone_id = Config.Cloudflare.ZONE_ID
    dns_name = Config.Cloudflare.DNS_NAME
    record_type = "A"

    #######################################    
    # PERFORM THIS CHECK IN CONFIG CLASS???
    #######################################
    #if not all([zone_id, dns_name, api_token, detected_ip]):
    #   raise ValueError("update_dns_record: ⚠️ Missing required configuration or IP")

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type" : "application/json",
    }

    list_url = f"{api_base_url}/zones/{zone_id}/dns_records?name={dns_name}&type={record_type}"
    try:
        resp = requests.get(list_url, headers=headers, timeout=5)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"update_dns_record: ⚠️ Failed to fetch DNS record: {e}")
    # print(f"update_dns_record: DNS records URL: {list_url}")
    logger.info("Entering Cloudflare script...")


    return True
