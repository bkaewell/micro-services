import os
import time
import json
import gspread
import requests

from typing import Optional
from dotenv import load_dotenv
from google.auth import exceptions as auth_exceptions

from .logger import get_logger
from .cache import GOOGLE_SHEET_ID_FILE


class GSheetsService:
    """
    Standalone service for Google Sheets access with TTL caching and
    Spreadsheet ID persistence. Designed for easy reuse across microservices
    """

    # Set a robust timeout constant for all external API requests
    TIMEOUT_SECONDS = 15

    def __init__(self):
        """
        Initializes the service with configuration and sets up internal state
        """

        # Define the logger once for the entire class
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
            self.gsheet_creds,
            self.gsheet_dns 
        ]

        if not all(required_vars):
            raise EnvironmentError(
                "Missing required Google environment variables in .env file "
                "(GOOGLE_SHEET_NAME, GOOGLE_WORKSHEET, " \
                "GOOGLE_SHEETS_CREDENTIALS, CLOUDFLARE_DNS_NAME)"
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
        Applies timeout using set_timeout() method.
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

            client.set_timeout(self.TIMEOUT_SECONDS)
            self.client = client
            self.logger.info(f"New gspread client initialized with {self.TIMEOUT_SECONDS}s timeout")
            return self.client
        
        except Exception as e:
            self.logger.error(f"Failed to authenticate gspread client: {e}")
            raise


    def get_client(self) -> gspread.Client:
        """Returns the existing client or creates a new one"""
        if self.client is None:
            return self._create_client()
        return self.client


    def get_worksheet(self) -> gspread.Worksheet:
        """Initializes the worksheet object, using cached ID if available"""
        
        # If the worksheet object is already initialized, return it immediately (Cache Hit)
        if self.worksheet:
            return self.worksheet
        
        # # Verify client integrity and is ready
        # self.get_client()   # Will NOT force a new client here unless one doesn't exist
        # client = self.client # Use internal client state

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


    def reconnect(self):
        """
        Forces the GSheets service to destroy its current client and authentication
        session, then rebuilds it; Used to clear stale TCP connections and expired 
        OAuth tokens after long periods of inactivity
        """
        self.logger.critical("GSheets Service: Forcing full reconnect after system anomaly!")

        # Explicitly destroy the old client/connection state
        self.client = None

        # Rebuild the client immediately (with timeout applied)
        try:
            self._create_client() # Calls the function that always creates a new client
        except Exception as e:
            # If client creation fails (i.e. bad credentials), log and stop
            # self.logger.error(f"FATAL: Reconnect failed during client creation: {e}")
            # self.logger.fatal(f"Reconnect failed during client creation: {e}")
            self.logger.error(f"Reconnect failed during client creation: {e}")            
            raise # Re-raise this fatal error

        # Reset the worksheet state (Crucial for clearing stale connection pointers)
        self.worksheet = None

        # Call get_worksheet() to preload and test the new connection chain
        try:
            self.get_worksheet()
            self.logger.critical("GSheets Service: Reconnection successful")
        except Exception as e:
            # If opening the sheet fails (i.e. API is still down), log gracefully
            self.logger.error(
                f"Failed to restore worksheet after client reconnection. "
                f"Will retry on next cycle. Error: {e.__class__.__name__}"
            )
            # Do not raise here; let the next run_cycle handle the temp failure


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
        ):
            """
            Uses the persistently stored target_row to efficiently perform partial updates.
            """
            try:
                # Verify the target row is found/established (only runs heavy logic once)
                target_row = self._ensure_target_row()
                ws = self.get_worksheet()
                
                updates = []
                
                # Update Column B (IP), Column C (Last Updated Time), and Column A (DNS Name)
                if ip_address is not None:
                    updates.append(gspread.Cell(target_row, 1, self.gsheet_dns)) # A: DNS
                    updates.append(gspread.Cell(target_row, 2, ip_address))      # B: IP
                    updates.append(gspread.Cell(target_row, 3, current_time))    # C: Last Updated
                    # self.logger.info(
                    #     f"📄 Sheet updated | dns={self.gsheet_dns} | ip={ip_address} "
                    #     f"| time={current_time}"
                    # )


                # Update Column D (Last Modified) - Only updated on actual IP change
                if dns_last_modified is not None:
                    updates.append(gspread.Cell(target_row, 4, dns_last_modified)) # D: Last Modified
                    # self.logger.info(
                    #     f"📄 Sheet updated | dns={self.gsheet_dns} | "
                    #     f"last_modified={dns_last_modified}"
                    # )
                
                if updates:
                    ws.update_cells(updates, value_input_option='USER_ENTERED')

                    # self.logger.info(
                    #     f"📄 Sheet updated | dns={self.gsheet_dns} | ip={ip_address} "
                    #     f"| time={current_time} | last_modified={dns_last_modified}"
                    # )

                    #self.logger.info(f"Updated persistent row {target_row} for {self.gsheet_dns}")

            # --- EXCEPTION HANDLING ---
            # Catch network failures and Google API/authorization errors (high-level)
            except(
                requests.RequestException,   # Network and HTTP/API
                gspread.exceptions.APIError, # Google Sheets
                auth_exceptions.RefreshError # OAuth Access Token Renewal
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



    # """
    # Standalone service for Google Sheets access with TTL caching and
    # Spreadsheet ID persistence. Designed for easy reuse across microservices
    # """
    # def __init__(self):
    #     """
    #     Initializes the service with configuration and sets up internal state
    #     """

    #     # Define the logger once for the entire class
    #     self.logger = get_logger("google_sheets_service")

    #     # Load .env
    #     load_dotenv()

    #     # Configuration
    #     self.gsheet_name = os.getenv("GOOGLE_SHEET_NAME")
    #     self.gsheet_worksheet = os.getenv("GOOGLE_WORKSHEET")
    #     self.gsheet_creds = json.loads(os.getenv("GOOGLE_SHEETS_CREDENTIALS"))
    #     self.gsheet_dns = os.getenv("CLOUDFLARE_DNS_NAME")

    #     # Add checks here to ensure values are not None and raise an error if they are
    #     required_vars = [
    #         self.gsheet_name, 
    #         self.gsheet_worksheet, 
    #         self.gsheet_creds,
    #         self.gsheet_dns 
    #     ]

    #     if not all(required_vars):
    #         raise EnvironmentError(
    #             "Missing required Google environment variables in .env file "
    #             "(GOOGLE_SHEET_NAME, GOOGLE_WORKSHEET, " \
    #             "GOOGLE_SHEETS_CREDENTIALS, CLOUDFLARE_DNS_NAME)"
    #         )

    #     # Internal State Management
    #     self.client: Optional[gspread.Client] = None
    #     self.gsheet_id: Optional[str] = None
    #     self.worksheet: Optional[gspread.Worksheet] = None
    #     self.target_row = None


    # def get_client(self, force_new: bool = False) -> None:
    #     """
    #     Ensures the gspread client is authenticated (Singleton pattern)
    #     Relies on google-auth for automatic, background token refresh

    #     Args:
    #         force_new: If True (usually triggered by a system anomaly), 
    #                    forces the destruction of the existing client
    #                    and performs a full (expensive) re-auth
    #     """

    #     # Check 1: If client already exists AND we are not forcing a 
    #     # new connection, return immediately
    #     if self.client is not None and not force_new:
    #         self.logger.info("Using cached gspread client")
    #         return # self.client is cached

    #     # Check 2: Client does not exist OR we are focing re-authentication
    #     if force_new:
    #         self.logger.warning("Forcing client re-authentication due to system anomaly")
    #     else:
    #         self.logger.info("Client missing; Performing initial, full authentication with Google services")

    #     # Google Services Authentication logic
    #     try:
    #         # Create credentials object from dictionary
    #         creds = Credentials.from_service_account_info(
    #             self.gsheet_creds,
    #             scopes=[
    #                 'https://www.googleapis.com/auth/spreadsheets', 
    #                 'https://www.googleapis.com/auth/drive',
    #             ]
    #         )
    #         # Authorize the client with the credentials object
    #         self.client = authorize(creds) 
    #         self.logger.info("New gspread client initialized")
        
    #     except Exception as e:
    #         self.logger.error(f"Failed to authenticate gspread client: {e}")
    #         raise


    # def get_worksheet(self) -> gspread.Worksheet:
    #     """Initializes the worksheet object, using cached ID if available"""
        
    #     # If the worksheet object is already initialized, return it immediately
    #     if self.worksheet:
    #         return self.worksheet
        
    #     # Verify client integrity and is ready
    #     self.get_client()   # Will NOT force a new client here unless one doesn't exist
    #     client = self.client # Use internal client state
        
    #     # Spreadsheet ID caching (minimizes API calls)
    #     if self.gsheet_id is None:
    #         # Check 1: Local file cache
    #         if GOOGLE_SHEET_ID_FILE.exists():
    #             self.gsheet_id = GOOGLE_SHEET_ID_FILE.read_text().strip()
    #             self.logger.info(f"Loaded Spreadsheet ID from cache: {self.gsheet_id}")
    #         # Check 2: API lookup and write
    #         else:
    #             self.logger.info(f"Spreadsheet ID not cached; Looking up sheet name: '{self.gsheet_name}'")
    #             sh = client.open(self.gsheet_name)
    #             self.gsheet_id = sh.id
    #             GOOGLE_SHEET_ID_FILE.write_text(self.gsheet_id)
    #             self.logger.info(f"Resolved and cached Spreadsheet ID: {self.gsheet_id}")

    #     # Get Worksheet using cached ID
    #     sh = client.open_by_key(self.gsheet_id)   # Most efficient way to access spreadsheet
    #     self.worksheet = sh.worksheet(self.gsheet_worksheet)
    #     self.logger.info(f"Accessed worksheet '{self.gsheet_worksheet}' using cached ID")
        
    #     return self.worksheet


    # def reconnect(self):
    #     """
    #     Forces the GSheets service to destroy its current client and authentication
    #     session, then rebuilds it; Used to clear stale TCP connections and expired 
    #     OAuth tokens after long periods of inactivity
    #     """
    #     self.logger.critical("GSheets Service: Forcing full reconnect after system anomaly!")

    #     # Force the client to be rebuilt
    #     self.get_client(force_new=True)

    #     # Reset the worksheet state - this ensures the next call to get_worksheet()
    #     # will perform a fresh API lookup (open_by_key) using the new client,
    #     # which also helps clear connection state
    #     self.worksheet = None


    #     # Call get_worksheet() now to preload the fresh worksheet object
    #     try:
    #         self.get_worksheet()
    #         self.logger.critical("GSheets Service: Reconnection successful")
    #     except Exception as e:
    #         self.logger.error(f"Failed to restore worksheet after reconnection: {e}")
    #         # Do not raise here; let the next run_cycle handle the failure via its main try/except


    # def _ensure_target_row(self) -> int:
    #     """
    #     Calculates and stores the target row index (1-based) if not already set.
    #     This operation is only performed once per agent lifetime.
    #     """
    #     if self.target_row is not None:
    #         return self.target_row

    #     ws = self.get_worksheet()
    #     dns_name = self.gsheet_dns
        
    #     try:
    #         # Search for the DNS name; Returns Cell object or None
    #         cell = ws.find(dns_name, in_column=1)

    #         # --- Found ---
    #         if cell:
    #             self.target_row = cell.row
    #             self.logger.info(f"DNS '{dns_name}' detected at persistent row {self.target_row}.")
    #             return self.target_row

    #         # --- Not Found (cell is None) ---
    #         self.logger.info(f"DNS '{dns_name}' not found; appending new row...")
            
    #         # Append the new row data.
    #         ws.append_row([dns_name, None, None, None])
            
    #         # Rerun the search *without* a range limit to find the new cell.
    #         self.logger.warning("Rerunning search to find newly appended row.")
    #         new_cell = ws.find(dns_name, in_column=1) 
            
    #         if new_cell:
    #             self.target_row = new_cell.row
    #             self.logger.info(f"DNS '{dns_name}' successfully appended at row {self.target_row}.")
    #             return self.target_row
            
    #         # Critical fallback if second find fails
    #         self.logger.error("Failed to find appended DNS row. Cannot update sheet.")
    #         raise Exception("Failed to establish sheet row for DNS key.")

    #     except gspread.exceptions.GSpreadException as e:
    #         self.logger.error(f"Critical GSpread error during row establishment: {e.__class__.__name__}")
    #         raise


    # def update_status(
    #         self, 
    #         ip_address: str,
    #         current_time: time,
    #         dns_last_modified: str
    #     ):
    #         """
    #         Uses the persistently stored target_row to efficiently perform partial updates.
    #         """
    #         try:
    #             # Verify the target row is found/established (only runs heavy logic once)
    #             target_row = self._ensure_target_row()
    #             ws = self.get_worksheet()
                
    #             updates = []
                
    #             # Update Column B (IP), Column C (Last Updated Time), and Column A (DNS Name)
    #             if ip_address is not None:
    #                 updates.append(gspread.Cell(target_row, 1, self.gsheet_dns)) # A: DNS
    #                 updates.append(gspread.Cell(target_row, 2, ip_address))      # B: IP
    #                 updates.append(gspread.Cell(target_row, 3, current_time))    # C: Last Updated
                    
    #             # Update Column D (Last Modified) - Only updated on actual IP change
    #             if dns_last_modified is not None:
    #                 updates.append(gspread.Cell(target_row, 4, dns_last_modified)) # D: Last Modified
                
    #             if updates:
    #                 ws.update_cells(updates, value_input_option='USER_ENTERED')
    #                 self.logger.info(f"Updated persistent row {target_row} for {self.gsheet_dns}")

    #         # --- EXCEPTION HANDLING ---
    #         # Catch network failures and Google API/authorization errors (high-level)
    #         except(
    #             requests.RequestException,   # Network and HTTP/API
    #             gspread.exceptions.APIError, # Google Sheets
    #             auth_exceptions.RefreshError # OAuth Access Token Renewal
    #         ) as e:
    #             self.logger.error(
    #                 f"Gracefully skipping GSheets status update: " 
    #                 f"Connection aborted or API/Auth issue; "
    #                 f"Will retry next cycle ({e.__class__.__name__}: {e})"
    #             )
            
    #         # The crucial safety net for truly unexpected system failures
    #         except Exception as e:
    #             self.logger.error(
    #                 f"Fatal error during GSheets status write: "
    #                 f"{e.__class__.__name__}: {e}"
    #             )
    #             raise # Re-raise to crash the process and ensure the scheduler sees the failure









    # def _find_or_append_row(
    #         self, 
    #         ws: gspread.Worksheet, 
    #         dns_name: str
    #     ) -> int:
    #     """
    #     Searches Column 1 ('DNS') for the dns_name; if found, returns the row index (1-based)
    #     If not found, appends the DNS name to a new row and returns the new index
    #     """
    #     # Search Optimization: Limit the search range to populated rows (i.e. A2:A100)
    #     # This prevents scanning thousands of empty cells
    #     search_range = 'A2:A100'

    #     try:
    #         # Attempt to find the DNS name in the first column. Returns Cell object or None
    #         cell = ws.find(dns_name, in_column=1, range=search_range)

    #         # Check if the cell was found
    #         if cell:
    #             self.logger.debug(f"DNS '{dns_name}' found at row {cell.row}")
    #             return cell.row

    #         # Cell not found (Cell is None)
    #         self.logger.info(f"DNS '{dns_name}' not found; appending new row...")
            
    #         # Append the new row data containing the DNS key
    #         # We must then immediately find the cell we just wrote to get its row index
    #         ws.append_row([dns_name, None, None, None])
            
    #         self.logger.warning("Rerunning search to find newly appended row")

    #         # Rerun the search without a range limit this time to find the new cell
    #         # This is the simplest way to get the new row index without complex API parsing
    #         new_cell = ws.find(dns_name, in_column=1) 

    #         # This check is defensive, but should always succeed if append_row worked
    #         if new_cell:
    #             new_row_index = new_cell.row
    #             self.logger.info(f"DNS '{dns_name}' successfully appended at row {new_row_index}.")
    #             return new_row_index
            
    #         # Critical fallback if second find fails (highly unlikely)
    #         self.logger.error("Failed to find appended DNS row; Cannot update sheet")
    #         raise Exception("Failed to establish sheet row for DNS key")            


    #         # # The new row index is the current number of rows in the worksheet
    #         # new_row_index = ws.row_count 
    #         # self.logger.info(f"DNS '{dns_name}' successfully appended at row {new_row_index}")
    #         # return new_row_index

    #     # Handle actual GSpread API errors (Auth, Rate Limit, etc.)
    #     except gspread.exceptions.GSpreadException as e:
    #          # Re-raise to be caught by the outer robust exception block in update_status
    #         self.logger.error(f"Critical GSpread error during search/append for '{dns_name}': {e.__class__.__name__}")
    #         raise



        # # Search for the DNS name in the first column (A)
        # try:
        #     # If successful, returns the Cell object
        #     cell = ws.find(dns_name, in_column=1) 
            
        #     # Execution reaches here ONLY if the cell was found
        #     self.logger.debug(f"DNS '{dns_name}' found at row {cell.row}")
        #     return cell.row
        
        # # Handle GSpread exception raised when cell is NOT found (i.e. APIError 404)
        # except gspread.exceptions.GSpreadException as e:
        #     # Note: We assume that a failure in ws.find() that reaches this block 
        #     # and is not a critical Auth/Network issue (caught higher up) 
        #     # is the 'Cell Not Found' case (which was sunsetted)

        #     self.logger.info(f"DNS '{dns_name}' not found; Appending new row...")
            
        #     # Append the new row data
        #     ws.append_row([dns_name, None, None, None])
            
        #     # The new row index is the current number of rows in the worksheet
        #     new_row_index = ws.row_count 

        #     self.logger.info(f"DNS '{dns_name}' successfully appended at row {new_row_index}")
        #     return new_row_index





    # def update_status(
    #         self, 
    #         dns_name: str,
    #         ip_address: str,
    #         current_time: time,
    #         dns_last_modified: str
    # ):
    #     """
    #     Dynamically locates the row for the given dns_name and performs partial updates
    #     """
        
    #     try:
    #         # Access worksheet
    #         ws = self.get_worksheet()

    #         # Find the correct row for this DNS name
    #         target_row = self._find_or_append_row(ws, dns_name)

    #         # Data array structure: [DNS, IP, Last Updated, Last Modified]
    #         # The DNS field is always present because it is the key
    #         update_data = [dns_name, ip_address, current_time, dns_last_modified]

    #         # Determine the full range for the update (i.e. A2:D2)
    #         # Rowcol_to_a1 converts (row, col) to A1 notation
    #         # We want the range from Column A (1) to Column D (4) in the target row
    #         start_range = rowcol_to_a1(target_row, 1) # i.e. A2
    #         end_range = rowcol_to_a1(target_row, 4)   # i.e. D2
    #         full_range = f"{start_range}:{end_range}"

    #         # Handle partial updates (the most efficient path)
            
    #         # Always update IP and Last Updated time (Heartbeat)
    #         # The update_cells method is much faster than update() for individual cells
            
    #         # Note: We must update the cell values directly, NOT the range, 
    #         # to avoid overwriting unrelated data (like Uptime columns)
            
    #         updates = []
            
    #         # Update Column B (IP) and Column C (Last Updated)
    #         if ip_address is not None:
    #             updates.append(gspread.Cell(target_row, 2, ip_address))
    #             updates.append(gspread.Cell(target_row, 3, current_time))
                
    #         # Update Column D (Last Modified) - Only updated on IP change
    #         if dns_last_modified is not None:
    #             updates.append(gspread.Cell(target_row, 4, dns_last_modified))
            
    #         if updates:
    #             ws.update_cells(updates, value_input_option='USER_ENTERED')
    #             self.logger.info(f"Dynamically updated row {target_row} for {dns_name} in range {full_range}")
    #             self.logger.info(f"dns={dns_name}, ip={ip_address}, time={current_time}, dns_last_modified={dns_last_modified}")



    #         # # Perform updates
    #         # if ip_address is not None:
    #         #     ws.update('A5:C5', test_data, value_input_option='USER_ENTERED')
    #         #     self.logger.info(f"Test write to A5:C5 complete; Time: {current_time}")

    #         # if dns_last_modified is not None:
    #         #     ws.update('A6:D6', test_data, value_input_option='USER_ENTERED')
    #         #     self.logger.info(f"Test write to A5:D5 complete; Time: {current_time}")

    #     # Catch network failures and Google API/authorization errors (high-level)
    #     except(
    #         # Network and HTTP/API failures (i.e. Timeout, Connection Reset, 4xx/5xx responses)
    #         requests.RequestException,
    #         # Google Sheets specific errors (i.e. Permission Denied, Invalid Range)          
    #         gspread.exceptions.APIError,
    #         # Failure to renew OAuth access token
    #         auth_exceptions.RefreshError
    #     ) as e:
    #         self.logger.error(
    #             f"Gracefully skipping GSheets status update: " 
    #             f"Connection aborted or API/Auth issue; "
    #             f"Will retry next cycle ({e.__class__.__name__}: {e})"
    #         )

    #     # The crucial safety net for truly unexpected system failures
    #     except Exception as e:
    #         self.logger.error(
    #             f"Fatal error during GSheets status write: "
    #             f"{e.__class__.__name__}: {e}"
    #         )
    #         raise # Re-raise to crash the process and ensure the scheduler sees the failure
