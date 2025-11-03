import os
import socket
import gspread
import requests

from datetime import datetime
from zoneinfo import ZoneInfo
from oauth2client.service_account import ServiceAccountCredentials


def is_valid_ip(ip: str) -> bool:
    """
    Validate an IP address using socket

    Args:
        ip: IP address string to validate   

    Returns: 
        True if the IP address is valid, False otherwise
    """

    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except socket.error:
        return False


def get_public_ip() -> str | None:
    """
    Fetch the public IP address (IPv4)

    Returns: 
        Public IP address as a string or None if no service succeeds     
    """

    # API endpoints (redundant, outputs plain text, ranked by reliability)
    ip_services = [
        "https://api.ipify.org", 
        "https://ifconfig.me/ip", 
        "https://ipv4.icanhazip.com", 
        "https://ipecho.net/plain", 
    ]

    # Try API endpoints in order until one succeeds
    for service in ip_services:
        try:
            response = requests.get(service, timeout=5)
            if response.status_code == 200:
                ip = response.text.strip()
                if is_valid_ip(ip):
                    print(f"get_public_ip: {ip} (from {service})")
                    return ip
        except requests.RequestException:
            continue  # Skip on network/timeout error and try next
    
    # No service returned a valid IP
    return None


def to_local_time(iso_str: str = None) -> str:
    """
    Convert an ISO8601 string or return the current datetime in the timezone from TZ env var (default UTC),
    formatted as 'YYYY-MM-DD\\nHH:MM:SS TZ ±HHMM'
    
    Args:
        iso_str (str, optional): ISO8601 string to convert (i.e. '2025-09-05T02:33:15.640385Z')
    
    Returns:
        str: Formatted datetime string
    """

    tz_name = os.getenv("TZ", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception as e:
        print(f"to_local_time: ⚠️ Exception: {e}, defaulting to UTC")
        tz = ZoneInfo("UTC")

    try:
        if iso_str:
            # Parse ISO8601 string to datetime and convert to specified timezone
            dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
            dt = dt.astimezone(tz)
        else:
            # Get current time in the local timezone
            dt = datetime.now(tz)
    except Exception as e:
        print(f"to_local_time: ⚠️ Exception: {e}, defaulting to current time in {tz_name}")
        dt = datetime.now(tz)

    return dt.strftime("%Y-%m-%d\n%H:%M:%S %Z %z")


def upload_ip(google_config: dict, 
              dns_name: str, 
              detected_ip: str, 
              dns_last_modified: str) -> None:
    """
    Uploads DNS IP and related metadata to Google Sheets

    Args:
        google_config: Configuration for Google Sheets API (i.e. credentials path, spreadsheet ID, worksheet name)
        dns_name: DNS name to update
        detected_ip: Detected public IP address
        dns_last_modified: Last modified time from Cloudflare (formatted string)
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
    #now = datetime.datetime.now().strftime("%Y-%m-%d\n%H:%M:%S %Z %z")
    #now = get_now_local().strftime("%Y-%m-%d\n%H:%M:%S %Z %z")
    now = to_local_time()

    if dns_name in dns_list:
        # Existing DNS row → update
        row_num = dns_list.index(dns_name) + 2
        updates = {
            "IP"                         : detected_ip,
            #"Last Check"                : now,
            "Last Updated"               : now,            
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
        # Currently, upload_ip raises NotImplementedError for new DNS names. If you want to append new rows, implement the else block:
        #sheet.append_row([dns_name, detected_ip, now, dns_last_modified, "", "", ""])



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
