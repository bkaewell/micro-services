import os
import gspread
import datetime
import requests

from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials


def update_dns_record(ip: str, 
                      base_url: str, 
                      api_token: str, 
                      zone_id: str, 
                      dns_name: str) -> bool:
    """
    Update the Cloudflare DNS record to the new IP if it has changed

    Returns:
        True if record was updated, False if unchanged
    """

    header = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    data = {
        "type": "A",
        "name": dns_name,
        "content": ip,     # Update to the new IP
        "ttl": 120,
        "proxied": False
    }

    # Get DNS record 
    list_url = f"{base_url}/zones/{zone_id}/dns_records?name={dns_name}"
    resp = requests.get(list_url, headers=header)
    resp.raise_for_status()

    records = resp.json().get("result", [])
    if not records:
        raise ValueError(f"No DNS record found for {dns_name} in zone {zone_id}")

    record_id = records[0]["id"]
    current_ip = records[0]["content"]
    print(f"Current IP for {dns_name}: {current_ip}")

    ip = "100.34.59.228"

    # Update DNS record if IP has changed
    if current_ip != ip:
        update_url = f"{base_url}/zones/{zone_id}/dns_records/{record_id}"
        resp = requests.put(update_url, headers=header, json=data)
        resp.raise_for_status()
        print(f"✅  Updated {dns_name}: {current_ip} → {ip}")
        return True
    else:
        print(f"ℹ️  No update needed for {dns_name}, IP unchanged")
        return False


def upload_ip():
    # Google Sheets upload for IP
    pass

    # maybe only update if the IP address changed? 

def main():
    """
    Main entry point for the microservice
    """
    # Load environment variables from .env file
    load_dotenv()

    cloudflare_base_url    = os.getenv("CLOUDFLARE_BASE_URL")
    cloudflare_api_token   = os.getenv("CLOUDFLARE_API_TOKEN")
    cloudflare_zone_id     = os.getenv("CLOUDFLARE_ZONE_ID")
    cloudflare_record_name = os.getenv("CLOUDFLARE_RECORD_NAME")

    # Validate config
    if not all([cloudflare_base_url, cloudflare_api_token, cloudflare_zone_id, cloudflare_record_name]):
        raise EnvironmentError("Missing required Cloudflare config in .env")

    # Fetch current public IP
    current_ip = requests.get("https://api.ipify.org").text
    print(f"Detected public IP: {current_ip}")

    # Update the DNS record
    update_dns_record(current_ip, 
                      cloudflare_base_url, 
                      cloudflare_api_token, 
                      cloudflare_zone_id, 
                      cloudflare_record_name)


    google_sheet_name = os.getenv("GOOGLE_SHEET_NAME")
    google_worksheet  = os.getenv("GOOGLE_WORKSHEET")
    local_api_key  = os.getenv("GOOGLE_API_KEY_LOCAL")
    docker_api_key = os.getenv("GOOGLE_API_KEY_DOCKER")

    # Validate config
    if not all([google_sheet_name, google_worksheet, local_api_key, docker_api_key]):
        raise EnvironmentError("Missing required Google/Docker config in .env") 

    # Specific location maps from .env file
    location_env = os.getenv("LOCATION_MAP")

    # Convert the string into a dictionary; Use dictionary-based replacement 
    location_map = dict(item.split(":") for item in location_env.split(","))
    print(location_map)

    # Step 2 - google sheets
    #upload_ip(GOOGLE_SHEET_NAME, GOOGLE_WORKSHEET, local_api_key, docker_api_key, location_map)
