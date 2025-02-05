import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

# Google Sheets setup
GOOGLE_DRIVE_NAME = os.getenv("GOOGLE_DRIVE_NAME")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
CREDENTIALS_FILE = os.getenv("GOOGLE_API_CREDENTIALS")
sheet_id = create_google_sheet_in_folder(GOOGLE_SHEET_NAME, GOOGLE_DRIVE_NAME)
print("Google Sheet created in Shared_Content folder with ID:", sheet_id)
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def authenticate_google_sheets():
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPES)
    client = gspread.authorize(creds)
    return client.open(GOOGLE_SHEET_NAME).sheet1  # Open the first sheet

# Function to scrape streaming service pricing (placeholders)
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
        except Exception as e:
            price_data.append([service, url, "Error", str(e)])

    return price_data

# Function to update Google Sheets with pricing data
def update_google_sheet():
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
    sheet.update("A1", f"Last Run: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Run the script
if __name__ == "__main__":
    update_google_sheet()
