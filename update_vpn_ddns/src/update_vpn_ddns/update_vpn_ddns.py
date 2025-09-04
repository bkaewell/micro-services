import os
import json
import socket
import gspread
import datetime
import requests

from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials


def is_valid_ip(ip: str,
                version: str = "ipv4") -> bool:
    """
    Validate an IP address (IPv4 or IPv6) using socket

    Args:
        ip: The IP address string to validate
        version: "ipv4" or "ipv6"    

    Returns: 
        True if the IP address is valid, False otherwise
    """

    try:
        if version.lower() == "ipv4":
            socket.inet_pton(socket.AF_INET, ip)
        elif version.lower() == "ipv6":
            socket.inet_pton(socket.AF_INET6, ip)
        else:
            raise ValueError("Invalid IP version. Use 'ipv4' or 'ipv6'.")
        return True
    except (socket.error, ValueError):
        return False


def get_public_ip(version: str = "ipv4") -> str | None:
    """
    Fetches the public address for a given version ("ipv4" or "ipv6")

    Args:
        version: "ipv4" or "ipv6"

    Returns: 
        The detected IP address as a string, or None if all services fail
    """

    # API endpoints (redundant, ranked by reliability)
    ip_services = {
        "ipv4": [
            "https://api.ipify.org",      # outputs plain text    
            "https://ifconfig.me/ip", 
            "https://ipv4.icanhazip.com", 
            "https://ipecho.net/plain", 
        ],
        "ipv6": [
            "https://api64.ipify.org", 
            "https://ifconfig.me", 
            "https://ipv6.icanhazip.com", 
        ],
    }

    services = ip_services.get(version.lower())
    if not services:
        raise ValueError("get_public_ip[{version}]: Invalid IP version, use 'ipv4' or 'ipv6'")
    print(services)

    for service in services:
        try:
            response = requests.get(service, timeout=5)
            if response.status_code == 200:
                ip = response.text.strip()
                if is_valid_ip(ip, version):
                    print(f"get_public_ip[{version}]: {ip} (from {service})")
                    return ip
        except requests.RequestException:
            continue  # try the next service
    return None


def format_cloudflare_timestamp(last_modified_str):
    """
    Convert Cloudflare's UTC 'modified_on' timestamp to America/New_York time

    Returns: str: Converted timestamp as 'YYYY-MM-DD\\nHH:MM:SS'
    """

    last_modified_utc = datetime.datetime.strptime(last_modified_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    last_modified_utc = last_modified_utc.replace(tzinfo=ZoneInfo("UTC"))
    last_modified_nyc = last_modified_utc.astimezone(ZoneInfo("America/New_York"))
    return last_modified_nyc.strftime("%Y-%m-%d\n%H:%M:%S")


def update_dns_record(cloudflare_config,
                      detected_ip: str,
                      version: str = "ipv4") -> dict:
    """
    Update the Cloudflare DNS record ('A' for IPv4, 'AAAA' for IPv6) 
    to the detected IP if it has changed

    Returns: 
        dictionary
    """

    api_base_url = cloudflare_config["api_base_url"]
    api_token    = cloudflare_config["api_token"]
    zone_id      = cloudflare_config["zone_id"]
    dns_name     = cloudflare_config["dns_name"]

    # Add comment here
    record_type = "A" if version.lower() == "ipv4" else "AAAA"

    # Get DNS record 
    dns_records_url = f"{api_base_url}/zones/{zone_id}/dns_records?name={dns_name}"

    # Cloudflare API request: authentication headers + DNS record payload
    header = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type" : "application/json",
    }
    data = {
        "type"   : record_type,   # DNS record type (i.e. A, AAAA)
        "name"   : dns_name,      # DNS record name
        "content": detected_ip,   # Public IP to update
        "ttl"    : 60,            # TTL = Time-to-Live 
        "proxied": False          # Grey cloud (not proxied thru Cloudflare)
    }

    # Authenticate with API token
    resp = requests.get(dns_records_url, headers=header)     
    resp.raise_for_status()
    print(f"update_dns_record: DNS records URL: {dns_records_url}")         #####
    print(f"update_dns_record: DNS records JSON response:\n{json.dumps(resp.json(), indent=2)}")    #####

    # Get DNS metadata
    records = resp.json().get("result", [])
    if not records:
        raise ValueError(f"update_dns_record: No DNS record found for '{dns_name}' in zone {zone_id}")
    record_id         = records[0]["id"]
    dns_record_ip     = records[0]["content"]
    dns_last_modified = records[0]["modified_on"]
    print(f"update_dns_record: DNS record for '{dns_name}' → {dns_record_ip}")       #####

    print(f"******update_dns_record*******: id0={records[0]["id"]}") 
    print(f"******update_dns_record*******: id1={records[1]["id"]}") 

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
        "dns_name"         : dns_name,
        "detected_ip"      : detected_ip,
        "dns_last_modified": format_cloudflare_timestamp(dns_last_modified)
    }


def upload_ip(google_config,
              dns_name, 
              detected_ip, 
              dns_last_modified):
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

    # Map headers dynamically
    headers = sheet.row_values(1)
    header_map = {h.strip(): idx + 1 for idx, h in enumerate(headers)}

    #required_columns = ["DNS", "IP", "Last Check", "Last Modified (Cloudflare)", "Weekly Uptime (%)", "Overall Uptime (%)"]
    required_columns = ["DNS", "IP", "Last Updated", "Last Modified\n(Cloudflare)", "Weekly\nUptime (%)", "Overall\nUptime (%)", "Weekly\nDowntime (mins)"]

    for col in required_columns:
        if col not in header_map:
            raise ValueError(f"upload_ip: Missing required column '{col}' in worksheet '{worksheet}'")

    # Get DNS list to locate row
    dns_list = sheet.col_values(header_map["DNS"])[1:]  # Exclude header
    now = datetime.datetime.now().strftime("%Y-%m-%d\n%H:%M:%S")

    if dns_name in dns_list:
        # Existing DNS row → update
        row_num = dns_list.index(dns_name) + 2
        updates = {
            "IP"                        : detected_ip,
            #"Last Check"                : now,
            "Last Updated"              : now,            
            "Last Modified\n(Cloudflare)": dns_last_modified,
        }
        # if weekly_uptime is not None:
        #     updates["Weekly Uptime (%)"] = f"{weekly_uptime:.2f}%"
        # if overall_uptime is not None:
        #     updates["Overall Uptime (%)"] = f"{overall_uptime:.2f}%"

        for column, value in updates.items():
            sheet.update_cell(row_num, header_map[column], value)

        print(f"upload_ip: ✅ Updated '{dns_name}' → IP: {detected_ip}, Modified: {dns_last_modified}, Checked: {now}")
    else:
        print(f"upload_ip: ⚠️ DNS '{dns_name}' not found in sheet '{sheet_name}' (worksheet '{worksheet}'); Add it first.")


    # # Get header row to dynamically find column indices
    # headers = sheet.row_values(1)
    # dns_col = headers.index("DNS") + 1
    # ip_col = headers.index("IP") + 1
    # timestamp_col = headers.index("Last Updated") + 1

    # # Get all values from DNS column (excluding header)
    # dns_list = sheet.col_values(dns_col)[1:]

    # if dns_name in dns_list:
    #     # Find row number to update (offset by 2 for header row)
    #     row_num = dns_list.index(dns_name) + 2
    #     timestamp = datetime.datetime.now().strftime("%Y-%m-%d\n%H:%M:%S")
    #     sheet.update_cell(row_num, ip_col, detected_ip)
    #     sheet.update_cell(row_num, timestamp_col, timestamp)
    #     print(f"upload_ip: ✅ Uploaded '{dns_name}' → {detected_ip} at {timestamp}")      #####
    # else:
    #     print(f"upload_ip: ⚠️ DNS '{dns_name}' not found in sheet '{sheet_name}' (worksheet '{worksheet}'); Add it first")


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
    version = "ipv4"
    detected_ip = get_public_ip(version)

    if detected_ip:
        print(f"main: Detected public IP: {detected_ip}")
        # Update the DNS record
        result = update_dns_record(cloudflare_config, 
                                   detected_ip,
                                   version)

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
                  dns_last_modified=result["dns_last_modified"])

    else:
        print("main: ⚠️ Could not fetch a valid public IP; DNS record not updated.")
