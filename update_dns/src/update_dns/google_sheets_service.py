import os
import time
import json
import pathlib
import gspread
import requests # For catching ConnectionError

from typing import Optional
from gspread import authorize
from dotenv import load_dotenv
from datetime import datetime, timezone
from google.oauth2.service_account import Credentials 
from google.auth import exceptions as auth_exceptions

from .logger import get_logger
from .utils import to_local_time
from .cache import GOOGLE_SHEET_ID_FILE


class GSheetsService:
    """
    Standalone service for Google Sheets access with TTL caching and
    Spreadsheet ID persistence. Designed for easy reuse across microservices
    """
    def __init__(self):
        """
        Initializes the service with configuration and sets up internal state
        """

        # Define the logger once for the entire class
        self.logger = get_logger("google_sheets_service")

        # Load .env
        load_dotenv()

        # Configuration
        self.gsheet_name = os.getenv("GOOGLE_SHEET_NAME")
        self.gsheet_worksheet = os.getenv("GOOGLE_WORKSHEET")
        self.gsheet_creds = json.loads(os.getenv("GOOGLE_SHEETS_CREDENTIALS"))


        # Internal State Management
        self.client: Optional[gspread.Client] = None
        self.gsheet_id: Optional[str] = None
        self.worksheet: Optional[gspread.Worksheet] = None


    def get_client(self, force_new: bool = False) -> None:
        """
        Ensures the gspread client is authenticated (Singleton pattern)
        Relies on google-auth for automatic, background token refresh

        Args:
            force_new: If True (usually triggered by a system anomaly), 
                       forces the destruction of the existing client
                       and performs a full (expensive) re-auth
        """

        # Check 1: If client already exists AND we are not forcing a 
        # new connection, return immediately
        if self.client is not None and not force_new:
            self.logger.info("Using cached gspread client")
            return # self.client is cached

        # Check 2: Client does not exist OR we are focing re-authentication
        if force_new:
            self.logger.warning("Forcing client re-authentication due to system anomaly")
        else:
            self.logger.info("Client missing; Performing initial, full authentication with Google services")

        # Google Services Authentication logic
        try:
            # Create credentials object from dictionary
            creds = Credentials.from_service_account_info(
                self.gsheet_creds,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets', 
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
        
        # Verify client integrity and is ready
        self.get_client()   # Will NOT force a new client here unless one doesn't exist
        client = self.client # Use internal client state
        
        # Spreadsheet ID caching (minimizes API calls)
        if self.gsheet_id is None:
            # Check 1: Local file cache
            if GOOGLE_SHEET_ID_FILE.exists():
                self.gsheet_id = GOOGLE_SHEET_ID_FILE.read_text().strip()
                self.logger.info(f"Loaded Spreadsheet ID from cache: {self.gsheet_id}")
            # Check 2: API lookup and write
            else:
                self.logger.info(f"Spreadsheet ID not cached; Looking up sheet name: '{self.gsheet_name}'")
                sh = client.open(self.gsheet_name)
                self.gsheet_id = sh.id
                GOOGLE_SHEET_ID_FILE.write_text(self.gsheet_id)
                self.logger.info(f"Resolved and cached Spreadsheet ID: {self.gsheet_id}")

        # Get Worksheet using cached ID
        sh = client.open_by_key(self.gsheet_id)   # Most efficient way to access spreadsheet
        self.worksheet = sh.worksheet(self.gsheet_worksheet)
        self.logger.info(f"Accessed worksheet '{self.gsheet_worksheet}' using cached ID")
        
        return self.worksheet


    def reconnect(self):
        """
        Forces the GSheets service to destroy its current client and authentication
        session, then rebuilds it; Used to clear stale TCP connections and expired 
        OAuth tokens after long periods of inactivity
        """
        self.logger.critical("GSheets Service: Forcing full reconnect after system anomaly!")

        # Force the client to be rebuilt
        self.get_client(force_new=True)

        # Reset the worksheet state - this ensures the next call to get_worksheet()
        # will perform a fresh API lookup (open_by_key) using the new client,
        # which also helps clear connection state
        self.worksheet = None


        # Call get_worksheet() now to preload the fresh worksheet object
        try:
            self.get_worksheet()
            self.logger.critical("GSheets Service: Reconnection successful")
        except Exception as e:
            self.logger.error(f"Failed to restore worksheet after reconnection: {e}")
            # Do not raise here; let the next run_cycle handle the failure via its main try/except


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
            ip_address: str,
            current_time: time,
            dns_last_modified: str
    ):
        """Public method to perform the test write to A5:D5"""
        
        try:
            ws = self.get_worksheet() # Access worksheet
            test_data = [[dns_name, ip_address, current_time, dns_last_modified]]
            
            # Perform updates
            if ip_address is not None:
                ws.update('A5:C5', test_data, value_input_option='USER_ENTERED')
                self.logger.info(f"Test write to A5:C5 complete; Time: {current_time}")

            if dns_last_modified is not None:
                ws.update('A6:D6', test_data, value_input_option='USER_ENTERED')
                self.logger.info(f"Test write to A5:D5 complete; Time: {current_time}")

        # Catch network failures and Google API/authorization errors (high-level)
        except(
            # Network and HTTP/API failures (i.e. Timeout, Connection Reset, 4xx/5xx responses)
            requests.RequestException,
            # Google Sheets specific errors (i.e. Permission Denied, Invalid Range)          
            gspread.exceptions.APIError,
            # Failure to renew OAuth access token
            auth_exceptions.RefreshError
        ) as e:
            self.logger.error(
                f"Gracefully skipping GSheets status update: " 
                f"Connection aborted or API/Auth issue; "
                f"Will retry next cycle ({e.__class__.__name__}: {e})"
            )

        # The crucial safety net for truly unexpected system failures
        except Exception as e:
            self.logger.error(
                f"Fatal error during GSheets status write: "
                f"{e.__class__.__name__}: {e}"
            )
            raise # Re-raise to crash the process and ensure the scheduler sees the failure
