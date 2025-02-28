import gspread
from oauth2client.service_account import ServiceAccountCredentials
from requests import get
import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Specific location maps from .env file
location_env = os.getenv("LOCATION_MAP")

# Convert the string into a dictionary; Use dictionary-based replacement 
location_map = dict(item.split(":") for item in location_env.split(","))
#print(location_map)

# Google Sheets config from .env file
GOOGLE_SHEET_NAME   = os.getenv("GOOGLE_SHEET_NAME")
GOOGLE_WORKSHEET = os.getenv("GOOGLE_WORKSHEET")
GOOGLE_API_KEY_FILE = os.getenv("GOOGLE_API_KEY_FILE")

# Expand `~` to full home directory path
GOOGLE_API_KEY_FILE = os.path.expanduser(GOOGLE_API_KEY_FILE)

# Ensure file exists before proceeding
if not os.path.exists(GOOGLE_API_KEY_FILE):
    raise FileNotFoundError(f"API key file not found: {GOOGLE_API_KEY_FILE}")

# Authenticate with Google Sheets
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_API_KEY_FILE, SCOPES)
client = gspread.authorize(creds)
sheet = client.open(GOOGLE_SHEET_NAME).worksheet(GOOGLE_WORKSHEET)  # Open sheet with the IP address table

# Fetch column names dynamically (assuming first row contains column names)
headers = sheet.row_values(1)
#print("Headers:", headers)

# Define column indexes based on headers (originally 0-based, now converted to 1-based)
location_col = headers.index("Location") + 1
ip_col = headers.index("Public IP Address") + 1
timestamp_col = headers.index("Last Updated") + 1
#print("location_col=", location_col, "ip_col=", ip_col, "timestamp_col=", timestamp_col)

# Retrieve the public IP address of the current device via an external API endpoint
#ip = get('https://api.ipify.org').text

# Query an external API endpoint to retrieve the client's public IP address and geolocation metadata
data = get("http://ip-api.com/json/").json()
#print(data)  # Print full response (if needed)
location, ip = data.get("city"), data.get("query")
timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Replace location if it exists in the dictionary mapping, otherwise keep it unchanged
location = location_map.get(location, location)

# Fetch all location entries from the sheet
locations = sheet.col_values(location_col)[1:]  # Exclude first row (header row)
#print(locations)

if location in locations:
    # Find the row number where the location exists
    # Convert 0-based index (from 'locations' list) to 1-based row index in Google Sheets
    row_num = locations.index(location) + 2 # Offset for the first actual data row start at row 2

    # Update the Google Sheet:
    sheet.update_cell(row_num, ip_col, ip)
    sheet.update_cell(row_num, timestamp_col, timestamp)
    print(f"Updated existing location: {location}")
else:
    # Append a new row if location is not found and update the Google Sheet
    sheet.append_row([location, ip, timestamp])
    print(f"Added new location: {location}")

print(f"Updated Google Sheet: Location={location}, Public IP Address={ip}, Timestamp={timestamp}")
