import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime
from dotenv import load_dotenv
import os
import logging

# Load .env file
load_dotenv()

#Linux environment variables
LOG_DIR = os.getenv("LOG_DIR")
#LOG_DIR = os.path.expanduser("~/automated_scripts/logs/")
os.makedirs(LOG_DIR, exist_ok=True)  # Ensure the logs directory exists

# Set up logging
log_filename = f"streaming_price_tracker_{datetime.datetime.now().strftime('%Y-%m-%d')}.log"
LOG_FILE = os.path.join(LOG_DIR, log_filename)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logging.info("Script started.")


# Google Sheets setup
GOOGLE_DRIVE_NAME = os.getenv("GOOGLE_DRIVE_NAME")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
CREDENTIALS_FILE = os.getenv("GOOGLE_API_CREDENTIALS")
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
#sheet_id = create_google_sheet_in_folder(GOOGLE_SHEET_NAME, GOOGLE_DRIVE_NAME)
#print("Google Sheet created in Shared_Content folder with ID:", sheet_id)

# Authenticate Google Sheets
def authenticate_google_sheets():
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPES)
        client = gspread.authorize(creds)
        logging.info("Google Sheets authentication successful.")
        return client.open(GOOGLE_SHEET_NAME).sheet1  # Open the first sheet
    except Exception as e:
        logging.error(f"Google Sheets authentication failed: {e}", exc_info=True)
        raise

# Scrape streaming service pricing
def scrape_streaming_prices():
    services = {
        "Netflix": "https://www.netflix.com/signup/planform",
        "Disney+": "https://www.disneyplus.com/welcome",
        "HBO Max": "https://www.max.com",
        "Spotify": "https://www.spotify.com/us/premium/",
        "YouTube TV": "https://tv.youtube.com/",
        "YouTube Premium": "https://www.youtube.com/premium",
        "Apple+": "https://tv.apple.com/"
    }

    price_data = []
    for service, url in services.items():
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")

            if "netflix" in url:
                price = soup.find("div", class_="some-class").text.strip()  # Update this selector
            elif "disneyplus" in url:
                price = soup.find("span", class_="some-class").text.strip()
            else:
                price = "Check manually"  # Placeholder if scraping is inconsistent

            price_data.append([service, url, price, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            logging.info(f"Successfully scraped {service}: {price}")

        except Exception as e:
            price_data.append([service, url, "Error", str(e)])
            logging.error(f"Error scraping {service}: {e}", exc_info=True)

    return price_data

# Update Google Sheet with pricing data
def update_google_sheet():
    try:
        sheet = authenticate_google_sheets()
        data = scrape_streaming_prices()

        existing_data = sheet.get_all_values()
        df = pd.DataFrame(existing_data[1:], columns=existing_data[0]) if existing_data else pd.DataFrame()

        updated_rows = []
        for row in data:
            service, url, new_price, last_checked = row
            old_price = None
            price_changed = False

            if not df.empty and service in df["Service"].values:
                old_price = df.loc[df["Service"] == service, "Price"].values[0]
                if old_price != new_price:
                    price_changed = True
                    df.loc[df["Service"] == service, "Old Price"] = old_price  # Store old price

            updated_rows.append([service, url, new_price, old_price if price_changed else "", last_checked])

        # Update Google Sheet
        sheet.clear()
        sheet.append_row(["Service", "URL", "Price", "Old Price", "Last Checked"])
        for row in updated_rows:
            sheet.append_row(row)

        # Track last update timestamp
        last_run_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.update("A1", f"Last Run: {last_run_timestamp}")
        logging.info(f"Google Sheet updated successfully at {last_run_timestamp}")

    except Exception as e:
        logging.error(f"Failed to update Google Sheet: {e}", exc_info=True)
        raise

# Run the script
if __name__ == "__main__":
    logging.info("Starting update process.")
    update_google_sheet()
    logging.info("Script execution finished.")
    