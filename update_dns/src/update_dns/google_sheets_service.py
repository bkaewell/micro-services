import time
import pathlib
import gspread
import requests # For catching ConnectionError

from typing import Optional
from gspread import authorize
from datetime import datetime, timezone
from google.oauth2.service_account import Credentials 

from .logger import get_logger
from .utils import to_local_time
from .cache import GOOGLE_SHEET_ID_FILE


class GSheetsService:
    """
    Standalone service for Google Sheets access with TTL caching and
    Spreadsheet ID persistence. Designed for easy reuse across microservices
    """
    def __init__(self, 
                 config_google
                 ):
        """
        Initializes the service with configuration and sets up internal state.
        """

        # Define the logger once for the entire class
        self.logger = get_logger("google_sheets_service")

        # Configuration
        self.config = config_google

        # Internal State Management
        self.client: Optional[gspread.Client] = None
        self.gsheet_id: Optional[str] = None
        self.worksheet: Optional[gspread.Worksheet] = None


    def get_client(self) -> None:
        """
        Ensures the gspread client is authenticated (Singleton pattern).
        Relies on google-auth for automatic, background token refresh
        """

        # Check 1: If client already exists, return immediately
        if self.client is not None:
            self.logger.info("Using cached gspread client")
            return # self.client is cached

        # Check 2: Client does not exist, perform full, expensive authentication.
        self.logger.info("Client missing. Performing initial, full authentication with Google services")

        try:
            # Create credentials object from dictionary
            creds = Credentials.from_service_account_info(
                self.config.SHEETS_CREDENTIALS,
                scopes=['https://www.googleapis.com/auth/spreadsheets', 
                        'https://www.googleapis.com/auth/drive',
                ]
            )
            # Authorize the client with the credentials object
            self.client = authorize(creds) 
            self.logger.info("New gspread client initialized")
        
        except Exception as e:
            self.logger.error(f"Failed to authenticate gspread client: {e}")
            raise


    def get_worksheet(self) -> gspread.Worksheet:
        """Initializes the worksheet object, using cached ID if available"""
        
        # If the worksheet object is already initialized, return it immediately
        if self.worksheet:
            return self.worksheet
        
        # 1. Ensure client is ready
        self.get_client() 
        client = self.client # Use internal client state
        
        # 2. Get Sheet ID (Persistent Cache)
        if self.gsheet_id is None:
            if GOOGLE_SHEET_ID_FILE.exists():
                self.gsheet_id = GOOGLE_SHEET_ID_FILE.read_text().strip()
                self.logger.info(f"Loaded Spreadsheet ID from cache: {self.gsheet_id}")
            else:
                self.logger.info(f"Spreadsheet ID not cached. Looking up sheet name: '{self.config.SHEET_NAME}'")
                sh = client.open(self.config.SHEET_NAME)
                self.gsheet_id = sh.id
                GOOGLE_SHEET_ID_FILE.write_text(self.gsheet_id)
                self.logger.info(f"Resolved and cached Spreadsheet ID: {self.gsheet_id}")

        # 3. Get Worksheet using cached ID
        sh = client.open_by_key(self.gsheet_id)
        self.worksheet = sh.worksheet(self.config.WORKSHEET)
        self.logger.info(f"Accessed worksheet '{self.config.WORKSHEET}' using cached ID")
        
        return self.worksheet


    def append_ip_log(self, ip_address: str, hostname: str):
        """Public method to append a row to the log sheet"""
        
        try:
            ws = self.get_worksheet() # Access worksheet (triggers auth/TTL/cache checks)
            
            data_for_log = [
                ip_address, 
                hostname, 
                gspread.utils.ISO_8601_OFFSET 
            ]
            ws.append_row(data_for_log, value_input_option='USER_ENTERED')
            self.logger.info(f"Appended IP '{ip_address}' to main log.")
            
        except requests.exceptions.ConnectionError:
            self.logger.error("Gracefully skipping GSheets upload: Connection aborted; Will retry next cycle")
        except Exception as e:
            self.logger.error(f"Fatal error during GSheets write: {e.__class__.__name__}: {e}; Check configuration/scopes")
            raise


    def update_status(
            self, 
            dns_name: str,
            dns_last_modified: str,
            ip_address: str
    ):
        """Public method to perform the test write to A5:D5"""
        
        try:
            ws = self.get_worksheet() # Access worksheet
            
            current_time_utc = datetime.now(timezone.utc).isoformat()
            current_time = to_local_time(current_time_utc)
            test_data = [[dns_name, ip_address, current_time, dns_last_modified]]
            
            ws.update('A5:D5', test_data, value_input_option='USER_ENTERED')
            self.logger.info(f"Test write to A5:D5 complete; Time (UTC): {current_time_utc}")
            
        except requests.exceptions.ConnectionError:
            self.logger.error("Gracefully skipping GSheets status update: Connection aborted; Will retry next cycle")
        except Exception as e:
            self.logger.error(f"Fatal error during GSheets status write: {e.__class__.__name__}: {e}")
            raise
