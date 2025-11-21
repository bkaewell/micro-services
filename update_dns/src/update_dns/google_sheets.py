import time
import pathlib
import gspread
import requests

from .config import Config
from gspread import authorize
from .logger import get_logger
from google.oauth2.service_account import Credentials 


logger = get_logger("google_sheets")

# Cache Setup 
if pathlib.Path("/.dockerenv").exists():
    cache_dir = pathlib.Path("/data/cache")
else:
    cache_dir = pathlib.Path.home() / ".cache" / "update_dns"

cache_dir.mkdir(parents=True, exist_ok=True)
id_cache_file = cache_dir / 'google_sheet_id.txt'


def get_gspread_client(self) -> None:
    """
    Ensures the gspread client is authenticated and available in self.gspread_client.
    Re-authenticates only if the Time-to-Live (TTL) has expired. Returns None
    """
    
    current_time = time.time()
    
    # Check TTL cache
    delta = current_time - self.last_auth_time
    if self.gspread_client is not None and delta < self.ttl_seconds:
        logger.info(f"Using cached gspread client (TTL remaining: {self.ttl_seconds - delta:.0f}s)")
        return   # self.gspread_client is cached

    # TTL expired or first run: perform full authentication
    logger.info("TTL expired or client missing; Re-authenticating with Google services")
    
    try:
        # Create credentials object from dictionary
        creds = Credentials.from_service_account_info(
            Config.Google.SHEETS_CREDENTIALS,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive', 
            ]
        )

        # Authorize the gspread client with the credentials object
        self.gspread_client = authorize(creds) 
        
        self.last_auth_time = current_time
        logger.info("New gspread client initialized and TTL reset (1 hour)")
        return   # self.gspread_client is now authorized
    
    except Exception as e:
        logger.error(f"Failed to authenticate gspread client: {e}")
        raise

def get_worksheet(self) -> gspread.Worksheet:
    """Resolves and caches the Spreadsheet ID, then returns the worksheet object."""
    
    if self.gsheet_id is None:
        if id_cache_file.exists():
            self.gsheet_id = id_cache_file.read_text().strip()
            logger.info(f"Loaded Spreadsheet ID from cache: {self.gsheet_id}")
        else:
            logger.info(f"Spreadsheet ID not cached. Looking up sheet name: '{Config.Google.SHEET_NAME}'")
            sh = self.gspread_client.open(Config.Google.SHEET_NAME)
            self.gsheet_id = sh.id
            id_cache_file.write_text(self.gsheet_id)
            logger.info(f"Resolved and cached Spreadsheet ID: {self.gsheet_id}")

    # Access Worksheet using cached ID
    sh = self.gspread_client.open_by_key(self.gsheet_id)
    ws = sh.worksheet(Config.Google.WORKSHEET)
    logger.info(f"Accessed worksheet '{Config.Google.WORKSHEET}' using cached ID.")
    return ws

def upload_ip(self):
    """ Executes the Google Sheets portion of the agent cycle """
    try:
        get_gspread_client(self)
        ws = get_worksheet(self)
        headers = ws.row_values(1)
        #logger.info(f"Headers: {headers}")

        from datetime import datetime, timezone
        from .utils import to_local_time
        current_time = to_local_time(datetime.now(timezone.utc).isoformat())

        test_data = [[self.detected_ip, current_time]]
        ws.update('B4:C4', test_data)
        logger.info(f"{test_data}")

    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ Gracefully skipping GSheets upload: Connection aborted ({e.__class__.__name__}). Will retry next cycle.")

    except Exception as e:
        logger.error(f"⚠️ Non-network error during GSheets upload: {e.__class__.__name__}: {e}. Skipping upload.")


# def get_gspread_client(self) -> gspread.Client:
#     """Returns the cached client, re-authenticating only if the TTL has expired"""
    
#     current_time = time.time()
    
#     # Check Time-to-Live (TTL) Cache
#     if self.gspread_client is not None and (current_time - self.last_auth_time) < self.ttl_seconds:
#         logger.info(f"Using cached gspread client (TTL remaining: {self.ttl_seconds - (current_time - self.last_auth_time):.0f}s).")
#         return self.gspread_client

#     # TTL Expired or First Run: Perform Full Authentication
#     logger.info("TTL expired or client missing. Re-authenticating with Google services.")
    
#     try:
#         # Create Credentials Object from Dictionary
#         creds = Credentials.from_service_account_info(
#             Config.Google.SHEETS_CREDENTIALS,
#             scopes=[
#                 'https://www.googleapis.com/auth/spreadsheets',
#                 'https://www.googleapis.com/auth/drive', 
#             ]
#         )

#         # Authorize the gspread client with the Credentials object
#         self.gspread_client = authorize(creds) 
        
#         self.last_auth_time = current_time
#         logger.info("New gspread client initialized and TTL reset (1 hour)")
#         return self.gspread_client
    
#     except Exception as e:
#         logger.error(f"Failed to authenticate gspread client: {e}")
#         raise

# def get_worksheet(self, gc: gspread.Client) -> gspread.Worksheet:
#     """Resolves and caches the Spreadsheet ID, then returns the worksheet object."""
    
#     if self.gsheet_id is None:
#         if id_cache_file.exists():
#             self.gsheet_id = id_cache_file.read_text().strip()
#             logger.info(f"Loaded Spreadsheet ID from cache: {self.gsheet_id}")
#         else:
#             logger.info(f"Spreadsheet ID not cached. Looking up sheet name: '{Config.Google.SHEET_NAME}'")
#             sh = gc.open(Config.Google.SHEET_NAME)
#             self.gsheet_id = sh.id
#             id_cache_file.write_text(self.gsheet_id)
#             logger.info(f"Resolved and cached Spreadsheet ID: {self.gsheet_id}")

#     # Access Worksheet using cached ID
#     sh = gc.open_by_key(self.gsheet_id)
#     ws = sh.worksheet(Config.Google.WORKSHEET)
#     logger.info(f"Accessed worksheet '{Config.Google.WORKSHEET}' using cached ID.")
#     return ws

# def upload_ip(self):
#     """ <DOCSTRINGS> """
#     gc = get_gspread_client(self)
#     ws = get_worksheet(self, gc)
#     headers = ws.row_values(1)
#     #logger.info(f"Headers: {headers}")

#     from datetime import datetime, timezone
#     from .utils import to_local_time
#     current_time = to_local_time(datetime.now(timezone.utc).isoformat())

#     test_data = [[self.detected_ip, current_time]]
#     ws.update('B4:C4', test_data)
#     logger.info(f"{test_data}")
