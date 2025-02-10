import gspread
from oauth2client.service_account import ServiceAccountCredentials
from requests import get
import datetime
import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logging setup
LOG_DIR = os.getenv("LOG_DIR", ".")
os.makedirs(LOG_DIR, exist_ok=True)  # Ensure logs directory exists
log_filename = os.path.join(LOG_DIR, f"streaming_ip_tracker_{datetime.datetime.now().strftime('%Y-%m-%d')}.log")

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.info("Script started.")

# Google Sheets API setup
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
CREDENTIALS_FILE = os.getenv("GOOGLE_API_CREDENTIALS")
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

"""
Authenticate with Google Sheets API and return the sheet object.
"""
def authenticate_google_sheets():
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPES)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1  # Open the first sheet
        logging.info("Google Sheets authentication successful.")
        return sheet
    except Exception as e:
        logging.error(f"Google Sheets authentication failed: {str(e)}", exc_info=True)
        raise

"""
Retrieve the public IP address using api.ipify.org.
"""
def get_public_ip():
    try:
        ip = get('https://api.ipify.org').text
        logging.info(f"Public IP retrieved: {ip}")
        return ip
    except Exception as e:
        logging.error(f"Failed to retrieve public IP: {str(e)}", exc_info=True)
        return "ERROR"

"""
Update appropriate cell with the extracted public IP address and timestamp
"""
def update_google_sheet():
    try:
        sheet = authenticate_google_sheets()
        public_ip = get_public_ip()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Update Google Sheets
        sheet.update([[public_ip]], "B4")
        sheet.update([[timestamp]], "C4")

        logging.info(f"Google Sheet updated: B4 = {public_ip}, C4 = {timestamp}")
        print(f"Updated Google Sheet: B4 = {public_ip}, C4 = {timestamp}")
    except Exception as e:
        logging.error(f"Failed to update Google Sheet: {str(e)}", exc_info=True)
        raise

# Run the script
if __name__ == "__main__":
    logging.info("Starting IP extraction and update process.")
    update_google_sheet()
    logging.info("Script execution finished.")