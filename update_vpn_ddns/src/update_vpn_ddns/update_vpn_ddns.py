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

    cloudfare_config: dict with keys:
        - api_base_url
        - api_token
        - zone_id
        - dns_name

    ip (str): Current public IP address

    Returns:
        True if record was updated, False if unchanged
    """

    api_base_url = cloudflare_config["api_base_url"]
    api_token    = cloudflare_config["api_token"]
    zone_id      = cloudflare_config["zone_id"]
    dns_name  = cloudflare_config["dns_name"]



    header = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    data = {
        "type": "A",
        "name": dns_name,
        "content": ip,     # Update to the new IP
        "ttl": 120,
        "proxied": False   # Keep grey cloud
    }

    # Get DNS record 
    list_url = f"{api_base_url}/zones/{zone_id}/dns_records?name={dns_name}"
    resp = requests.get(list_url, headers=header)     # Authenticate with API token
    resp.raise_for_status()

    records = resp.json().get("result", [])
    if not records:
        raise ValueError(f"No DNS record found for {dns_name} in zone {zone_id}")

    record_id = records[0]["id"]
    current_ip = records[0]["content"]
    print(f"Current IP for {dns_name}: {current_ip}")

    # Update DNS record if IP has changed
    if current_ip != ip:
        update_url = f"{api_base_url}/zones/{zone_id}/dns_records/{record_id}"
        #resp = requests.put(update_url, headers=header, json=data)
        #resp.raise_for_status()
        print(f"✅  Updated {dns_name}: {current_ip} → {ip}")
        return True
    else:
        print(f"ℹ️  No update needed for {dns_name}, IP unchanged")
        return False


def upload_ip(google_config, 
              location_map):
    """
    Uploads IP information to Google Sheets.

    google_config: dict with keys:
        - sheet_name
        - worksheet
        - api_key_local
        - api_key_docker
    location_map: dict mapping location keys to names
    """

    sheet_name     = google_config["sheet_name"]
    worksheet      = google_config["worksheet"]
    local_api_key  = google_config["local_api_key"]
    docker_api_key = google_config["docker_api_key"]

    # Your existing upload logic here
    print(sheet_name, worksheet, local_api_key, docker_api_key)
    print(location_map)
    

    # # Determine which API key path to use
    # if os.path.exists("/.dockerenv"):  # Running inside Docker
    #     api_key_path = docker_api_key
    # else:  # Running locally
    #     api_key_path = os.path.expanduser(local_api_key)  # Expand `~` in local paths

    # # Ensure the file exists before proceeding
    # if not os.path.exists(api_key_path):
    #     raise FileNotFoundError(f"API key file not found: {api_key_path}")

    # # Authenticate with Google Sheets
    # SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # creds = ServiceAccountCredentials.from_json_keyfile_name(api_key_path, SCOPES)
    # client = gspread.authorize(creds)
    # sheet = client.open(GOOGLE_SHEET_NAME).worksheet(GOOGLE_WORKSHEET)  # Open sheet with the IP address table

    # # Fetch column names dynamically (assuming first row contains column names)
    # headers = sheet.row_values(1)
    # #print("Headers:", headers)

    # # Define column indexes based on headers (originally 0-based, now converted to 1-based)
    # location_col = headers.index("Location") + 1
    # ip_col = headers.index("Public IP Address") + 1
    # timestamp_col = headers.index("Last Updated") + 1
    # #print("location_col=", location_col, "ip_col=", ip_col, "timestamp_col=", timestamp_col)

    # # Retrieve the public IP address of the current device via an external API endpoint
    # #ip = get('https://api.ipify.org').text

    # # Query an external API endpoint to retrieve the client's public IP address and geolocation metadata
    # data = get("http://ip-api.com/json/").json()
    # #print(data)  # Print full response (if needed)
    # location, ip = data.get("city"), data.get("query")
    # timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # # Replace location if it exists in the dictionary mapping, otherwise keep it unchanged
    # location = location_map.get(location, location)

    # # Fetch all location entries from the sheet
    # locations = sheet.col_values(location_col)[1:]  # Exclude first row (header row)
    # #print(locations)

    # if location in locations:
    #     # Find the row number where the location exists
    #     # Convert 0-based index (from 'locations' list) to 1-based row index in Google Sheets
    #     row_num = locations.index(location) + 2 # Offset for the first actual data row start at row 2

    #     # Update the Google Sheet:
    #     sheet.update_cell(row_num, ip_col, ip)
    #     sheet.update_cell(row_num, timestamp_col, timestamp)
    #     print(f"Updated existing location: {location}")
    # else:
    #     # Append a new row if location is not found and update the Google Sheet
    #     sheet.append_row([location, ip, timestamp])
    #     print(f"Added new location: {location}")

    # print(f"Updated Google Sheet: Location={location}, Public IP Address={ip}, Timestamp={timestamp}")




    # maybe only update if the IP address changed? 

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
        "dns_name"  : os.getenv("CLOUDFLARE_DNS_NAME")
    }
    if not all(cloudflare_config.values()):
        raise EnvironmentError("Missing required Cloudflare config in .env")

    # Fetch current public IP
    current_ip = requests.get("https://api.ipify.org").text
    print(f"Detected public IP: {current_ip}")

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

    # Specific location maps from .env file
    location_env = os.getenv("LOCATION_MAP")

    # Convert the string into a dictionary; Use dictionary-based replacement 
    location_map = dict(item.split(":") for item in location_env.split(","))
    print(location_map)

    # Uploads IP information to Google Sheets
    upload_ip(google_config, 
              location_map)
