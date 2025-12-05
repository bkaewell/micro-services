import os
import json
import requests

from dotenv import load_dotenv

from .logger import get_logger
from .cache import get_cloudflare_ip, update_cloudflare_ip


class CloudflareClient:
    """Handles all communication and logic specific to the Cloudflare DNS API"""
    
    def __init__(self):
        """Initializes the client by resolving all config dependencies from os.environ"""

        # Define the logger once for the entire class
        self.logger = get_logger("cloudflare")

        # Load .env 
        load_dotenv()

        # Configuration
        self.api_base_url = os.getenv("CLOUDFLARE_API_BASE_URL")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
        self.dns_name = os.getenv("CLOUDFLARE_DNS_NAME")

        # Add checks here to ensure values are not None and raise an error if they are
        required_vars = [
            self.api_base_url, 
            self.api_token, 
            self.zone_id, 
            self.dns_name
        ]

        if not all(required_vars):
            raise EnvironmentError(
                "Missing required Cloudflare environment variables in .env file "
                "(API_BASE_URL, API_TOKEN, ZONE_ID, DNS_NAME)"
            )

        # Pre-calculated and necessary instance variables
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        self.record_type = "A"   # Fixed type

        #ttl: TTL
        #(default: 1)
        #Time To Live (TTL) of the DNS record in seconds. Setting to 1 means 'automatic'. 
        #Value must be between 60 and 86400, with the minimum reduced to 30 for Enterprise zones.
        self.ttl = 1            # Time-to-Live
        #self.ttl = 60            # Time-to-Live
        self.proxied = False     # Grey cloud icon (not proxied thru Cloudflare)


    # Private helper for URL construction
    def _build_resource_url(
        self,
        is_collection: bool = True, 
        record_id: str = None
    ) -> str:
        """
        Constructs the appropriate Cloudflare DNS resource URL based on the operation type

        Args:
            is_collection: True for the List/Collection endpoint (GET) 
                           False for the Single Resource endpoint (PUT/PATCH/DELETE)
            record_id: The unique ID of the target record (required if is_collection is False)

        Returns:
            The complete, correctly formatted API endpoint URL
        """

        # Common Base Path for all DNS record operations within the zone
        base_path = (
            f"{self.api_base_url}/zones/"
            f"{self.zone_id}/dns_records"
        )

        if is_collection:
            # Collection Resource Endpoint (GET operation)
            # Hardcoded filters for the specific DNS name and type
            filters = (
                f"?name={self.dns_name}"
                f"&type={self.record_type}"
            )
            return base_path + filters
            
        else:
            # Single Resource Endpoint (PUT/PATCH/DELETE operation)
            if not record_id:
                raise ValueError("record_id must be provided for single resource operations")
                    
            # Append the unique resource ID to the path
            return base_path + f"/{record_id}"


    def get_dns_record_info(self) -> dict:
        """
        Fetch the live Cloudflare DNS record (ID, IP, modified_on)
        
        Raises:
            RuntimeError: If the Cloudflare API request fails or returns no records
        """
        is_collection = True
        list_url = self._build_resource_url(is_collection)
        self.logger.debug(f"Initiating record pull → {list_url}")
        
        try:
            resp = requests.get(list_url, headers=self.headers, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"API GET request failed for {self.dns_name}: {e}")

        get_resp_data = resp.json()
        self.logger.debug(f"Live JSON received:\n{json.dumps(get_resp_data, indent=2)}")
        
        # Extract results (collection/list format)
        records_list = get_resp_data.get("result") or []
        
        if not records_list:
            raise RuntimeError(f"No DNS record found for {self.dns_name} ({self.record_type})")

        # Return the first (and only) matching record object
        return records_list[0]


    def update_dns_record(self, record_id: str, new_ip: str) -> dict:
        """
        Executes the PUT request to update the DNS record
        
        Returns:
            The updated DNS record object from the PUT response body
        Raises:
            RuntimeError: If the API PUT request fails
        """
        is_collection = False
        update_url = self._build_resource_url(is_collection, record_id)

        payload = {
            "type": self.record_type,
            "name": self.dns_name,
            "content": new_ip, 
            "ttl": self.ttl,
            "proxied": self.proxied,
        }
        
        try:
            resp = requests.put(update_url, headers=self.headers, json=payload, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"API PUT failed for record {record_id}: {e}")

        # Efficiency: Extract the new record from the PUT response body
        put_resp_data = resp.json()
        new_dns_record = put_resp_data.get("result")
        self.logger.debug(f"PUTTT JSON response:\n{json.dumps(put_resp_data, indent=2)}")

        if not new_dns_record:
            self.logger.warning("Successful PUT but response body was incomplete.")
            return {} 

        return new_dns_record


    # --- Orchestrator Method (Control Flow) ---
    def sync_dns(self, cached_ip: str, detected_ip: str) -> dict | None:
        """
        Orchestrates the DNS synchronization
        
        Returns:
            dict: The new DNS record info (with 'modified_on') if updated
            None: If the IP was unchanged (skipped), indicating no API interaction occurred
        Raises:
            RuntimeError: If any Cloudflare API operation fails
        """
        
        # Local cache check (rate limiting / early exit, fast filter)
        if cached_ip == detected_ip:
            self.logger.debug("🐾 🌤️  DNS OK | IP unchanged")
            return None 

        self.logger.debug(f"IP change detected | {cached_ip} → {detected_ip} | Updating DNS...")

        # Live Cloudflare GET (integrity check)
        try:
            live_dns_record = self.get_dns_record_info()
            live_dns_id = live_dns_record.get("id")
            live_dns_ip = live_dns_record.get("content")   # Live IP from Cloudflare
            self.logger.debug(f"Cloudflare record | id={live_dns_id} | ip={live_dns_ip}")

        except RuntimeError as e:
            raise RuntimeError(f"Failed to fetch DNS record info: {e}") 


        # Integrity check and final decision
        if live_dns_ip == detected_ip:

            # Cache was stale, but Cloudflare was already correct
            self.logger.warning("Stale cache corrected | Cloudflare already on latest IP")
            
            # Update cache
            update_cloudflare_ip(detected_ip)
            self.logger.info(f"Cache updated | {cached_ip} → {get_cloudflare_ip()}")

            # Cloudflare processes the request as a no-op (no actual change is 
            # made to the database)
            return None
        
        # PUT update (only if detected IP is different than live Cloudflare IP)
        try:
            new_dns_record = self.update_dns_record(
                record_id=live_dns_id, 
                new_ip=detected_ip
            )
            
        except RuntimeError as e:
            raise RuntimeError(f"Failed to update DNS record: {e}")

        # Success and cleanup
        if new_dns_record:
            self.logger.info(f"🐾 🌤️  DNS updated | {live_dns_ip} → {detected_ip} | {self.dns_name}")
            # Return the full updated DNS record info      
            return new_dns_record 

        return {} # Should never occur under normal flow

# For reference:

# DNS records JSON response:
# {
#   "result": [
#     {
#       "id": "******",
#       "name": "vpn.",
#       "type": "A",
#       "content": "101.34.48.69",
#       "proxiable": true,
#       "proxied": false,
#       "ttl": 60,
#       "settings": {},
#       "meta": {},
#       "comment": null,
#       "tags": [],
#       "created_on": "2025-08-26T02:33:04.952328Z",
#       "modified_on": "2025-11-25T02:13:54.401647Z"
#     }
#   ],
#   "success": true,
#   "errors": [],
#   "messages": [],
#   "result_info": {
#     "page": 1,
#     "per_page": 100,
#     "count": 1,
#     "total_count": 1,
#     "total_pages": 1
#   }
# }

