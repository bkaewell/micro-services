import os
import json
import requests

from .logger import get_logger
from .utils import to_local_time
from .cache import get_cloudflare_ip, update_cloudflare_ip


class CloudflareClient:
    """Handles all communication and logic specific to the Cloudflare DNS API"""
    
    def __init__(self):
        """Initializes the client by resolving all config dependencies from os.environ"""

        # Define the logger once for the entire class
        self.logger = get_logger("cloudflare")

        # Read required Cloudflare environment variables from .env
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
        self.ttl = 60            # Time-to-Live
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

