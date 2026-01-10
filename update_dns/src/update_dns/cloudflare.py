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
        self.logger.info("Cloudflare config OK")

        # Pre-calculated and necessary instance variables
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        self.record_type = "A"  # Fixed type
        self.ttl = 1            # auto → resolves to 60s (30s for Enterprise)
        self.proxied = False    # Grey cloud icon (not proxied thru Cloudflare)

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
    
    def get_dns_record(self) -> dict:
        """
        Fetch the current Cloudflare DNS record for this hostname.
        
        Returns:
            dict: DNS record object from Cloudflare response

        Raises:
            RuntimeError: If the API request fails or response is invalid
        """

        url = (
            f"{self.api_base_url}/zones/"
            f"{self.zone_id}/dns_records"
            f"?name={self.dns_name}"
            f"&type={self.record_type}"
        )
        
        try:
            resp = requests.get(
                url, headers=self.headers, timeout=Config.API_TIMEOUT
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(
                f"Cloudflare GET failed for DNS record "
                f"[{self.dns_name}]"
            ) from e
        
        # Extract the DNS record from the GET response body
        try:
            get_resp_data = resp.json()
        except ValueError as e:
            raise RuntimeError(
                "GET succeeded but response was not valid JSON"
            ) from e

        self.logger.debug(
            f"GET JSON response:\n%s",
            json.dumps(get_resp_data, indent=2),
        )

        records = get_resp_data.get("result") or []
        if not records:
            raise RuntimeError(
                f"GET succeeded but response contained no DNS record"
            )

        # Cloudflare returns a collection; name+type should be unique
        return records[0]
