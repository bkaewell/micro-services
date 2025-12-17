# --- Standard library imports ---
import os
import json
import requests

# --- Third-party imports ---
from dotenv import load_dotenv

# --- Project imports ---
from .config import Config
from .logger import get_logger


class CloudflareClient:
    """
    Handles all communication and logic specific to the Cloudflare DNS API.
    """
    
    def __init__(self):
        """
        Initializes the client by resolving all config dependencies.
        """

        self.logger = get_logger("cloudflare")

        # Load .env 
        load_dotenv()

        # Configuration
        self.api_base_url = os.getenv("CLOUDFLARE_API_BASE_URL")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
        self.dns_name = os.getenv("CLOUDFLARE_DNS_NAME")
        self.dns_record_id = os.getenv("CLOUDFLARE_DNS_RECORD_ID")
        self.validate_cloudflare()
        self.logger.info("🐾🌤️  Cloudflare config OK")


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

    def validate_cloudflare(self) -> None:
        """
        Validate a Cloudflare DNS configuration in one request.
        """
        resp = requests.get(f"{self.api_base_url}/zones/{self.zone_id}/dns_records/{self.dns_record_id}",
                            headers={"Authorization": f"Bearer {self.api_token}"})
        data = resp.json()
        if (
            not resp.ok 
            or not data.get("success") 
            or data["result"]["name"] != self.dns_name
        ):
            raise ValueError(f"Cloudflare config invalid: {data}")
    
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
            resp = requests.get(list_url, headers=self.headers, timeout=Config.API_TIMEOUT)
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


    def update_dns(self, new_ip: str) -> dict:
        """
        Update the DNS record to point to the provided IP address.

        Returns:
            dict: Updated DNS record from Cloudflare response

        Raises:
            RuntimeError: If the API request fails or response is invalid
        """

        url = (
            f"{self.api_base_url}/zones/"
            f"{self.zone_id}/dns_records/"
            f"{self.dns_record_id}"
        )

        payload = {
            "type": self.record_type,
            "name": self.dns_name,
            "content": new_ip, 
            "ttl": self.ttl,
            "proxied": self.proxied,
        }
        
        try:
            resp = requests.put(
                url, headers=self.headers, json=payload, timeout=Config.API_TIMEOUT
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(
                f"Cloudflare PUT failed for DNS record " 
                f"[{self.dns_record_id}] → {new_ip}"
                ) from e

        # Extract the new record from the PUT response body
        try:
            put_resp_data = resp.json()
        except ValueError as e:
            raise RuntimeError(
                "PUT succeeded but response was not valid JSON"
            ) from e
        
        self.logger.debug(
            f"PUT JSON response:\n%s",
            json.dumps(put_resp_data, indent=2),
        )

        new_dns_record = put_resp_data.get("result")
        if not new_dns_record:
            raise RuntimeError(
                "PUT succeeded but response contained no DNS record"
            )

        return new_dns_record
