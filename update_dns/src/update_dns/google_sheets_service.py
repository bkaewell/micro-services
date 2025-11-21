import time
import pathlib
import gspread
import requests # For catching ConnectionError

from typing import Optional
from gspread import authorize
from datetime import datetime, timezone
from google.oauth2.service_account import Credentials 

# Assume Config and logger are imported/defined elsewhere or passed in init
# from .config import Config 
# from .logger import get_logger 

# --- Module-Level Persistent Cache Setup (Shared by all instances) ---
CACHE_DIR = pathlib.Path.home() / ".cache" / "update_dns"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
ID_CACHE_FILE = CACHE_DIR / 'google_sheet_id.txt'
# Note: In a true library, you'd pass the cache path in init.

class GSheetsService:
    """
    Standalone service for Google Sheets access with TTL caching and
    Spreadsheet ID persistence. Designed for easy reuse across microservices.
    """
    
    def __init__(self, config_google, ttl_seconds: int = 3600, sheet_name: str = None, worksheet_name: str = None, logger_instance=None):
        """
        Initializes the service with configuration and sets up internal state.
        """
        self._config = config_google
        self._logger = logger_instance if logger_instance else logging.getLogger(__name__) # Use standard logger if none provided
        
        # Internal State Management
        self._client: Optional[gspread.Client] = None
        self._last_auth_time: float = 0.0
        self._gsheet_id: Optional[str] = None
        self._worksheet: Optional[gspread.Worksheet] = None
        
        # Configuration
        self._ttl_seconds: int = ttl_seconds
        self._sheet_name: str = sheet_name
        self._worksheet_name: str = worksheet_name


    def _get_client(self) -> None:
        """Ensures the gspread client is authenticated (TTL enforced)."""
        current_time = time.time()
        
        if self._client is not None and (current_time - self._last_auth_time) < self._ttl_seconds:
            self._logger.info(f"Using cached gspread client (TTL remaining: {self._ttl_seconds - (current_time - self._last_auth_time):.0f}s).")
            return

        self._logger.info("TTL expired or client missing. Re-authenticating with Google services.")
        
        try:
            creds = Credentials.from_service_account_info(
                self._config.SHEETS_CREDENTIALS,
                scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            )
            self._client = authorize(creds) 
            self._last_auth_time = current_time
            self._logger.info("New gspread client initialized and TTL reset (1 hour)")
        
        except Exception as e:
            self._logger.error(f"Failed to authenticate gspread client: {e}")
            raise

    def _get_worksheet(self) -> gspread.Worksheet:
        """Initializes the worksheet object, using cached ID if available."""
        
        # If the worksheet object is already initialized, return it immediately
        if self._worksheet:
            return self._worksheet
        
        # 1. Ensure client is ready
        self._get_client() 
        client = self._client # Use internal client state
        
        # 2. Get Sheet ID (Persistent Cache)
        if self._gsheet_id is None:
            if ID_CACHE_FILE.exists():
                self._gsheet_id = ID_CACHE_FILE.read_text().strip()
                self._logger.info(f"Loaded Spreadsheet ID from cache: {self._gsheet_id}")
            else:
                self._logger.info(f"Spreadsheet ID not cached. Looking up sheet name: '{self._sheet_name}'")
                sh = client.open(self._sheet_name)
                self._gsheet_id = sh.id
                ID_CACHE_FILE.write_text(self._gsheet_id)
                self._logger.info(f"Resolved and cached Spreadsheet ID: {self._gsheet_id}")

        # 3. Get Worksheet
        sh = client.open_by_key(self._gsheet_id)
        self._worksheet = sh.worksheet(self._worksheet_name)
        self._logger.info(f"Accessed worksheet '{self._worksheet_name}' using cached ID.")
        
        return self._worksheet

    def append_ip_log(self, ip_address: str, hostname: str):
        """Public method to append a row to the log sheet."""
        
        try:
            ws = self._get_worksheet() # Access worksheet (triggers auth/TTL/cache checks)
            
            data_for_log = [
                ip_address, 
                hostname, 
                gspread.utils.ISO_8601_OFFSET 
            ]
            ws.append_row(data_for_log, value_input_option='USER_ENTERED')
            self._logger.info(f"Appended IP '{ip_address}' to main log.")
            
        except requests.exceptions.ConnectionError:
            self._logger.error("❌ Gracefully skipping GSheets upload: Connection aborted. Will retry next cycle.")
        except Exception as e:
            self._logger.error(f"⚠️ Fatal error during GSheets write: {e.__class__.__name__}: {e}. Check configuration/scopes.")
            raise

    def update_status(self, ip_address: str):
        """Public method to perform the test write to B4:C4."""
        
        try:
            ws = self._get_worksheet() # Access worksheet
            
            current_time_utc = datetime.now(timezone.utc).isoformat() 
            test_data = [["STATUS_OK", current_time_utc]]
            
            ws.update('B4:C4', test_data, value_input_option='USER_ENTERED')
            self._logger.info(f"Test write to B4:C4 complete. Status: STATUS_OK, Time: {current_time_utc}")
            
        except requests.exceptions.ConnectionError:
            self._logger.error("❌ Gracefully skipping GSheets status update: Connection aborted. Will retry next cycle.")
        except Exception as e:
            self._logger.error(f"⚠️ Fatal error during GSheets status write: {e.__class__.__name__}: {e}.")
            raise