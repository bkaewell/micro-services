import os
import json
import requests

from dotenv import load_dotenv
from .utils import get_public_ip, to_local_time, upload_ip

def update_dns_record(cloudflare_config: dict,
                      detected_ip: str,
                      version: str = "ipv4") -> dict:
    """
    Update Cloudflare DNS record if the detected IP differs from the current record

    Args:
        cloudflare_config: Configuration for Cloudflare API (i.e. token, zone ID, DNS name)
        detected_ip: Detected public IP address from ISP
        version: "ipv4" (default) or "ipv6"

    Returns:
        Dict with DNS name, detected IP, and last modified time (formatted)
    """
    version = version.lower()
    if version not in ("ipv4", "ipv6"):
        print(f"update_dns_record: ⚠️ Invalid version '{version}', defaulting to IPv4")
        version = "ipv4"
    
    record_type = "A" if version.lower() == "ipv4" else "AAAA"

    api_base_url = cloudflare_config["api_base_url"]
    api_token    = cloudflare_config["api_token"]
    zone_id      = cloudflare_config["zone_id"]
    dns_name     = cloudflare_config["dns_name"]

    if not all([zone_id, dns_name, api_token, detected_ip]):
        raise ValueError("update_dns_record: ⚠️ Missing required configuration or IP")

    header = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type" : "application/json",
    }

    list_url = f"{api_base_url}/zones/{zone_id}/dns_records?name={dns_name}&type={record_type}"
    try:
        resp = requests.get(list_url, headers=header, timeout=5)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"update_dns_record: ⚠️ Failed to fetch DNS record: {e}")
    print(f"update_dns_record: DNS records URL: {list_url}")         #####

    data = resp.json()
    records = data.get("result", [])
    if not records:
        raise RuntimeError(f"update_dns_record: ⚠️ No DNS record found for {dns_name} ({record_type})")
    print(f"update_dns_record: DNS records JSON response:\n{json.dumps(data, indent=2)}")    #####

    # Find the record that matches the desired type (A or AAAA)
    record = next((r for r in records if r["type"] == record_type), None)
    if not record:
        raise RuntimeError(f"update_dns_record: ⚠️ No {record_type} record found for {dns_name}")

    record_id = record["id"]
    dns_record_ip = record["content"]
    dns_last_modified = record["modified_on"]

    # Update DNS record if IP has changed
    if dns_record_ip != detected_ip:
        update_url = f"{api_base_url}/zones/{zone_id}/dns_records/{record_id}"
        data = {
            "type": record_type, 
            "name": dns_name, 
            "content": detected_ip, 
            "ttl": 60,   # Time-to-Live 
            "proxied": False # Grey cloud (not proxied thru Cloudflare)
        }
        try:
            resp = requests.put(update_url, headers=header, json=data, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"update_dns_record: Failed to update DNS record: {e}")

        print(f"update_dns_record: ✅  Updated '{dns_name}': {dns_record_ip} → {detected_ip}")       #####
    else:
        print(f"update_dns_record: ℹ️  No update needed for '{dns_name}', IP unchanged")             #####
    
    return {
        "dns_name": dns_name,
        "detected_ip": detected_ip,
        "dns_last_modified": to_local_time(dns_last_modified),
    }


def main():
    """
    Main entry point for the microservice
    """

    load_dotenv()
    cloudflare_config = {
        "api_base_url" : os.getenv("CLOUDFLARE_API_BASE_URL"),
        "api_token": os.getenv("CLOUDFLARE_API_TOKEN"),
        "zone_id": os.getenv("CLOUDFLARE_ZONE_ID"),
        "dns_name": os.getenv("CLOUDFLARE_DNS_NAME"),
    }

    google_config = {
        "sheet_name": os.getenv("GOOGLE_SHEET_NAME"),
        "worksheet": os.getenv("GOOGLE_WORKSHEET"),
        "local_api_key": os.getenv("GOOGLE_API_KEY_LOCAL"),
        "docker_api_key": os.getenv("GOOGLE_API_KEY_DOCKER")
    }

    version = "ipv4"
    detected_ip = get_public_ip(version)

    if detected_ip:
        print(f"main: Detected public IP: {detected_ip}")
        try:
            result = update_dns_record(cloudflare_config, detected_ip, version)
            upload_ip(
                google_config,
                result["dns_name"],
                result["detected_ip"],
                result["dns_last_modified"],
            )
        except (RuntimeError, ValueError, NotImplementedError) as e:
            print(f"main: ⚠️ Failed to update DNS or upload to Google Sheets: {e}")
    else:
        print("main: ⚠️ Could not fetch a valid public IP; DNS record not updated.")
