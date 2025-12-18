# --- Standard library imports ---
import os
import time
import json
import gspread
import requests

# --- Third-party imports ---
from typing import Optional
from dotenv import load_dotenv
from google.auth.exceptions import TransportError
from google.auth import exceptions as auth_exceptions

# --- Project imports ---
from .config import Config
from .logger import get_logger
from .cache import GOOGLE_SHEET_ID_FILE


class GSheetsService:
    """
    Standalone service for Google Sheets access with TTL caching and
    Spreadsheet ID persistence. Designed for easy reuse across microservices.
    """

    def __init__(self):
        """
        Initializes the service with configuration and sets up internal state.
        """

        self.logger = get_logger("gsheets")

        # Load .env
        load_dotenv()

        # Configuration
        self.gsheet_name = os.getenv("GOOGLE_SHEET_NAME")
        self.gsheet_worksheet = os.getenv("GOOGLE_WORKSHEET")
        self.gsheet_creds = json.loads(os.getenv("GOOGLE_SHEETS_CREDENTIALS"))
        self.gsheet_dns = os.getenv("CLOUDFLARE_DNS_NAME")

        # Add checks here to ensure values are not None and raise an error if they are
        required_vars = [
            self.gsheet_name, 
            self.gsheet_worksheet, 
            self.gsheet_creds
        ]

        if not all(required_vars):
            raise EnvironmentError(
                "Missing required Google environment variables in .env file "
                "(GOOGLE_SHEET_NAME, GOOGLE_WORKSHEET, " \
                "GOOGLE_SHEETS_CREDENTIALS)"
            )

        # Internal State Management
        self.client: Optional[gspread.Client] = None
        self.gsheet_id: Optional[str] = None
        self.worksheet: Optional[gspread.Worksheet] = None
        self.target_row = None

        self._create_client()

    def _create_client(self) -> gspread.Client:
        """
        Creates and returns a new gspread client configured with credentials.
        """

        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets', 
            'https://www.googleapis.com/auth/drive',
        ]

        try:
            # Create client using the service account credentials
            client = gspread.service_account_from_dict(
                self.gsheet_creds,
                SCOPES
            )

            client.set_timeout(Config.API_TIMEOUT)
            self.client = client
            self.logger.info(
                f"New gspread client initialized with GSheets JSON creds"
            )
            return self.client
        
        except Exception as e:
            self.logger.error(f"Failed to authenticate gspread client: {e}")
            raise


    def get_client(self) -> gspread.Client:
        """
        Returns the existing client or creates a new one.
        """
        if self.client is None:
            return self._create_client()
        return self.client


    def get_worksheet(self) -> gspread.Worksheet:
        """
        Initializes the worksheet object, using cached ID if available.
        """
        
        # If the worksheet object is already initialized, return it immediately (Cache Hit)
        if self.worksheet:
            return self.worksheet
        
        # Get the authenticated client instance. This will either return the
        # cached client or create a new one with the timeout
        client = self.get_client() 

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
        # Use the client to open the sheet by key (most efficient API method)
        sh = client.open_by_key(self.gsheet_id)
        self.worksheet = sh.worksheet(self.gsheet_worksheet)
        self.logger.info(f"Accessed worksheet '{self.gsheet_worksheet}' using cached ID")
        
        return self.worksheet

    def _ensure_target_row(self) -> int:
        """
        Calculates and stores the target row index (1-based) if not already set.
        This operation is only performed once per agent lifetime.
        """
        if self.target_row is not None:
            return self.target_row

        ws = self.get_worksheet()
        dns_name = self.gsheet_dns
        
        try:
            # Search for the DNS name; Returns Cell object or None
            cell = ws.find(dns_name, in_column=1)

            # --- Found ---
            if cell:
                self.target_row = cell.row
                self.logger.info(f"DNS '{dns_name}' detected at persistent row {self.target_row}.")
                return self.target_row

            # --- Not Found (cell is None) ---
            self.logger.info(f"DNS '{dns_name}' not found; appending new row...")
            
            # Append the new row data.
            ws.append_row([dns_name, None, None, None])
            
            # Rerun the search *without* a range limit to find the new cell.
            self.logger.warning("Rerunning search to find newly appended row.")
            new_cell = ws.find(dns_name, in_column=1) 
            
            if new_cell:
                self.target_row = new_cell.row
                self.logger.info(f"DNS '{dns_name}' successfully appended at row {self.target_row}.")
                return self.target_row
            
            # Critical fallback if second find fails
            self.logger.error("Failed to find appended DNS row. Cannot update sheet.")
            raise Exception("Failed to establish sheet row for DNS key.")

        except gspread.exceptions.GSpreadException as e:
            self.logger.error(f"Critical GSpread error during row establishment: {e.__class__.__name__}")
            raise


    def update_status(
            self, 
            ip_address: str,
            current_time: time,
            dns_last_modified: str
        ) -> bool:
            """
            Uses the persistently stored target_row to efficiently perform partial updates.
            """
            try:
                # Verify the target row is found/established (only runs heavy logic once)
                target_row = self._ensure_target_row()
                ws = self.get_worksheet()
                
                updates = []
                
                # Heartbeat update:
                # Only touch Column C (Last Updated)
                if current_time is not None:
                    updates.append(gspread.Cell(target_row, 3, current_time))    # C: Last Updated

                # IP change update:
                # Only update Column B (IP Address) and Column D (Last Modified)
                if dns_last_modified is not None:
                    updates.append(gspread.Cell(target_row, 2, ip_address))        # B: IP
                    updates.append(gspread.Cell(target_row, 4, dns_last_modified)) # D: Last Modified
                
                if updates:
                    ws.update_cells(updates, value_input_option='USER_ENTERED')
                    return True
                    #self.logger.info(f"Updated persistent row {target_row} for {self.gsheet_dns}")

            # --- EXCEPTION HANDLING ---
            # Catch network failures and Google API/authorization errors (high-level)
            except(
                requests.RequestException,   # Network and HTTP/API
                gspread.exceptions.APIError, # Google Sheets
                auth_exceptions.RefreshError, # OAuth Access Token Renewal
                TransportError,
            ) as e:
                self.logger.error(
                    f"Skipping GSheets update due to network/API error: " 
                    f"{e.__class__.__name__}: {e}"
                )
                return False
            
            # The crucial safety net for truly unexpected system failures
            except Exception as e:
                self.logger.error(
                    f"Fatal error during GSheets status write: "
                    f"{e.__class__.__name__}: {e}"
                )
                raise # Re-raise to crash the process and ensure the scheduler sees the failure

