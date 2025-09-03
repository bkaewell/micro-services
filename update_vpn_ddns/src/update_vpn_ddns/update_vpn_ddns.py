import os
import json
import socket
import gspread
import datetime
import requests

from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

def get_public_ip():
    """
    Fetches the system's public IP address using multiple external services

    Returns: the detected IP as a string, or None if all services fail
    """

    # IP HTTPS API services list is ranked by reliability:
    ip_services = [
        "https://api.ipify.org",           # Plain text IPv4
        #"http://ip-api.com/json/",        # JSON with 'query' field
        #"https://ifconfig.me/ip",         # Plain text IPv6
        "https://ipv4.icanhazip.com",      # Plain text IPv4
        #"https://ipecho.net/plain"        # Plain text IPv6
    ]
    
    for service in ip_services:
        try:
            response = requests.get(service, timeout=5)
            if response.status_code == 200:
                ip = response.text.strip()
                print(f"get_public_ip: Detected public IP: {ip} via external API service: {service}")
                return ip
        except requests.RequestException:
            continue  # try the next service
    
    return None


def is_valid_ip(ip):
    """
    Validate the provided IP address using socket

    Returns: True if the IP address is valid/usable, False otherwise
    """

    # Validate with socket to ensure usability
    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except socket.error:
        return False


def update_dns_record(cloudflare_config,
                      detected_ip: str) -> dict:
    """
    Update the Cloudflare DNS record to the detected IP if it has changed

    Returns: True if record was updated, False if unchanged
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
        "content": detected_ip,   # Update to the detected IP if it has changed
        "ttl": 60,                # TTL = Time to Live 
        "proxied": False          # Keep grey cloud
    }

    # Get DNS record 
    dns_records_url = f"{api_base_url}/zones/{zone_id}/dns_records?name={dns_name}"

    resp = requests.get(dns_records_url, headers=header)     # Authenticate with API token
    resp.raise_for_status()
    print(f"update_dns_record: DNS records URL: {dns_records_url}")         #####
    print(f"update_dns_record: DNS records JSON response:\n{json.dumps(resp.json(), indent=2)}")    #####


    records = resp.json().get("result", [])
    if not records:
        raise ValueError(f"update_dns_record: No DNS record found for '{dns_name}' in zone {zone_id}")

    record_id       = records[0]["id"]
    dns_record_ip   = records[0]["content"]
    dns_modified_on = records[0]["modified_on"]
    print(f"update_dns_record: DNS record for '{dns_name}' → {dns_record_ip}")       #####


    # Update DNS record if IP has changed
    if dns_record_ip != detected_ip:
        update_url = f"{api_base_url}/zones/{zone_id}/dns_records/{record_id}"
        resp = requests.put(update_url, headers=header, json=data)
        resp.raise_for_status()
        print(f"update_dns_record: ✅  Updated '{dns_name}': {dns_record_ip} → {detected_ip}")       #####
        #return True
    else:
        print(f"update_dns_record: ℹ️  No update needed for '{dns_name}', IP unchanged")             #####
        #return False
    
    return {
        "dns_name": dns_name,
        "detected_ip": detected_ip,
        "dns_modified_on": dns_modified_on
    }


def upload_ip(google_config,
              dns_name, 
              detected_ip, 
              dns_modified_on):
    """
    Uploads DNS IP and related metadata to Google Sheets
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
        raise FileNotFoundError(f"upload_ip: API key file not found: {api_key_path}")


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
        sheet.update_cell(row_num, ip_col, detected_ip)
        sheet.update_cell(row_num, timestamp_col, timestamp)
        print(f"upload_ip: ✅ Uploaded '{dns_name}' → {detected_ip} at {timestamp}")      #####
    else:
        print(f"upload_ip: ⚠️ DNS '{dns_name}' not found in sheet '{sheet_name}' (worksheet '{worksheet}'); Add it first")


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
        raise EnvironmentError("main: Missing required Cloudflare config in .env")

    # Fetch current public IP
    detected_ip = get_public_ip()
    is_valid = is_valid_ip(detected_ip)

    if is_valid:
        print(f"main: Detected public IP: {detected_ip}")
        # Update the DNS record
        result = update_dns_record(cloudflare_config, 
                                   detected_ip)

        # Validate config
        google_config = {
            "sheet_name"     : os.getenv("GOOGLE_SHEET_NAME"),
            "worksheet"      : os.getenv("GOOGLE_WORKSHEET"),
            "local_api_key"  : os.getenv("GOOGLE_API_KEY_LOCAL"),
            "docker_api_key" : os.getenv("GOOGLE_API_KEY_DOCKER")
        }
        if not all(google_config.values()):
            raise EnvironmentError("main: Missing required Google/Docker config in .env") 

        # Uploads IP data to Google Sheets
        upload_ip(google_config,
                  result["dns_name"],
                  result["detected_ip"],
                  dns_modified_on=result["dns_modified_on"])

    else:
        print("main: ⚠️ Could not fetch a valid public IP; DNS record not updated.")
