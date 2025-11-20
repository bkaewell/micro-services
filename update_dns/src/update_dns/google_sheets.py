import time
import pathlib
import gspread

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


def get_gspread_client(self) -> gspread.Client:
    """Returns the cached client, re-authenticating only if the TTL has expired"""
    
    current_time = time.time()
    
    # Check Time-to-Live (TTL) Cache
    if self.gspread_client is not None and (current_time - self.last_auth_time) < self.ttl_seconds:
        logger.info(f"Using cached gspread client (TTL remaining: {self.ttl_seconds - (current_time - self.last_auth_time):.0f}s).")
        return self.gspread_client

    # TTL Expired or First Run: Perform Full Authentication
    logger.info("TTL expired or client missing. Re-authenticating with Google services.")
    
    try:
        # Create Credentials Object from Dictionary
        creds = Credentials.from_service_account_info(
            Config.Google.SHEETS_CREDENTIALS,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive', 
            ]
        )

        # Authorize the gspread client with the Credentials object
        self.gspread_client = authorize(creds) 
        
        self.last_auth_time = current_time
        logger.info("New gspread client initialized and TTL reset (1 hour)")
        return self.gspread_client
    
    except Exception as e:
        logger.error(f"Failed to authenticate gspread client: {e}")
        raise

def upload_ip(self):
    """ <DOCSTRINGS> """
    gc = get_gspread_client(self)

