import gspread
from oauth2client.service_account import ServiceAccountCredentials
from requests import get
import datetime
import os
from dotenv import load_dotenv

# Dictionary-based replacement
location_map = {
    "Warminster": "Ivyland",
    "Los Angeles": "Hollywood",
    "New York": "Manhattan"
}

# Load environment variables from .env file
load_dotenv()

# Google Sheets config from .env file
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH") 

# Authenticate with Google Sheets
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_PATH, SCOPES)
client = gspread.authorize(creds)
sheet = client.open(GOOGLE_SHEET_NAME).worksheet("ip_monitor")  # Open sheet with the IP address table

# Fetch column names dynamically
headers = sheet.row_values(1)  # Assuming first row contains column names

# Define column indexes based on headers
location_col = headers.index("Location") + 1
ip_col = headers.index("Public IP Address") + 1
timestamp_col = headers.index("Last Updated") + 1
print("location_col=", location_col, "ip_col=", ip_col, "timestamp_col=", timestamp_col)

# Retrieve the public IP address of the current device via an external API endpoint
# public_ip = get('https://api.ipify.org').text

# Query an external API endpoint to retrieve the client's public IP address and geolocation metadata
data = get("http://ip-api.com/json/").json()
#print(data)  # Print full response (if needed)
location, public_ip = data.get("city"), data.get("query")
timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Replace location if it exists in the mapping, otherwise keep it unchanged
location = location_map.get(location, location)

# Fetch all location values from the sheet
locations = sheet.col_values(location_col)[1:]  # Exclude header row
print(locations)

if location in locations:
    # Find the row number where the location exists
    row_num = locations.index(location) + 2  # Offset for 1-based indexing and header row
    print("row_num=", row_num, "location=", location)
    sheet.update_cell(row_num, ip_col, public_ip)
    sheet.update_cell(row_num, timestamp_col, timestamp)
    print(f"Updated existing location: {location}")
else:
    # Append a new row if location is not found
    sheet.append_row([location, public_ip, timestamp])
    print(f"Added new location: {location}")


# Update the Google Sheet:
# Update the cells of the location and public IP of the current device
#sheet.update(values=[[location]], range_name="A6")
#sheet.update(values=[[public_ip]], range_name="B6")
#sheet.update(values=[[timestamp]], range_name="C6")

print(f"Updated Google Sheet: location={location}, public IP={public_ip}, timestamp={timestamp}")