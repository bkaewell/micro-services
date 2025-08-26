import os
import gspread
import datetime
import requests

from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials


def update_dns_record(cloudflare_config,
                      ip: str) -> bool:
    """
    Update the Cloudflare DNS record to the new IP if it has changed

    Returns:
        True if record was updated, False if unchanged
    """

    api_base_url = cloudflare_config["api_base_url"]
    api_token    = cloudflare_config["api_token"]
    zone_id      = cloudflare_config["zone_id"]
    dns_name     = cloudflare_config["dns_name"]

    header = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    data = {
        "type": "A",
        "name": dns_name,
        "content": ip,     # Update to the new IP
        "ttl": 60,         # Time to Live 
        "proxied": False   # Keep grey cloud
    }

    # Get DNS record 
    list_url = f"{api_base_url}/zones/{zone_id}/dns_records?name={dns_name}"

    resp = requests.get(list_url, headers=header)     # Authenticate with API token
    resp.raise_for_status()
    #print(f"List URL: {list_url}")
    #print(f"JSON resp: {resp.json()}")

    records = resp.json().get("result", [])
    if not records:
        raise ValueError(f"No DNS record found for {dns_name} in zone {zone_id}")

    record_id = records[0]["id"]
    current_ip = records[0]["content"]
    #print(f"Current IP for {dns_name}: {current_ip}")

    # Update DNS record if IP has changed
    if current_ip != ip:
        update_url = f"{api_base_url}/zones/{zone_id}/dns_records/{record_id}"
        resp = requests.put(update_url, headers=header, json=data)
        resp.raise_for_status()
        #print(f"✅  Updated {dns_name}: {current_ip} → {ip}")
        return True
    else:
        #print(f"ℹ️  No update needed for {dns_name}, IP unchanged")
        return False


def upload_ip(google_config,
              dns_name,
              ip):
    """
    Uploads IP information to Google Sheets
    """

    sheet_name     = google_config["sheet_name"]
    worksheet      = google_config["worksheet"]
    local_api_key  = google_config["local_api_key"]
    docker_api_key = google_config["docker_api_key"]

    # Determine which API key path to use
    if os.path.exists("/.dockerenv"):  # Running inside Docker
        api_key_path = docker_api_key
    else:  # Running locally
        api_key_path = os.path.expanduser(local_api_key)
    
    if not os.path.exists(api_key_path):
        raise FileNotFoundError(f"API key file not found: {api_key_path}")


    # Authenticate with Google Sheets
    SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(api_key_path, SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open(sheet_name).worksheet(worksheet)

    # Get header row to dynamically find column indices
    headers = sheet.row_values(1)
    dns_col = headers.index("DNS") + 1
    ip_col = headers.index("IP") + 1
    timestamp_col = headers.index("Last Updated") + 1

    # Get all values from DNS column (excluding header)
    dns_list = sheet.col_values(dns_col)[1:]

    if dns_name in dns_list:
        # Find row number to update (offset by 2 for header row)
        row_num = dns_list.index(dns_name) + 2
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.update_cell(row_num, ip_col, ip)
        sheet.update_cell(row_num, timestamp_col, timestamp)
        #print(f"✅ Uploaded IP {ip} for DNS '{dns_name}' at {timestamp}")
    else:
        print(f"⚠️ DNS name '{dns_name}' not found in sheet — add it first")


def main():
    """
    Main entry point for the microservice
    """
    # Load environment variables from .env file
    load_dotenv()

    # Validate config
    cloudflare_config = {
        "api_base_url" : os.getenv("CLOUDFLARE_API_BASE_URL"),
        "api_token"    : os.getenv("CLOUDFLARE_API_TOKEN"),
        "zone_id"      : os.getenv("CLOUDFLARE_ZONE_ID"),
        "dns_name"     : os.getenv("CLOUDFLARE_DNS_NAME")
    }
    if not all(cloudflare_config.values()):
        raise EnvironmentError("Missing required Cloudflare config in .env")

    # Fetch current public IP
    current_ip = requests.get("https://api.ipify.org").text
    #print(f"Detected public IP: {current_ip}")

    # Update the DNS record
    update_dns_record(cloudflare_config,
                      current_ip)

    # Validate config
    google_config = {
        "sheet_name"     : os.getenv("GOOGLE_SHEET_NAME"),
        "worksheet"      : os.getenv("GOOGLE_WORKSHEET"),
        "local_api_key"  : os.getenv("GOOGLE_API_KEY_LOCAL"),
        "docker_api_key" : os.getenv("GOOGLE_API_KEY_DOCKER")
    }
    if not all(google_config.values()):
        raise EnvironmentError("Missing required Google/Docker config in .env") 

    # Uploads IP information to Google Sheets
    upload_ip(google_config,
              cloudflare_config["dns_name"],
              current_ip)
