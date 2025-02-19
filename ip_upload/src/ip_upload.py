import gspread
from oauth2client.service_account import ServiceAccountCredentials
from requests import get
import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up Google Services API credentials
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH")
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Authenticate with Google Sheets
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_PATH, SCOPES)
client = gspread.authorize(creds)
sheet = client.open(os.getenv("GOOGLE_SHEET_NAME")).sheet1  # Open the first sheet

# Retrieve the public IP address
public_ip = get('https://api.ipify.org').text

# Get the current timestamp
timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Update the Google Sheet:
# Update cell B4 with the public IP and cell C4 with the timestamp
sheet.update(values=[[public_ip]], range_name="B4")
sheet.update(values=[[timestamp]], range_name="C4")

print(f"Updated Google Sheet: public IP={public_ip}, timestamp={timestamp}")