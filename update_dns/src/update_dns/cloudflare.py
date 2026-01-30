# ─── Standard library imports ───
import os
import json
import time
import requests

# ─── Third-party imports ───
from dotenv import load_dotenv

# ─── Project imports ───
from .config import config
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
        self.proxied = False    # Grey cloud icon (not proxied thru Cloudflare)
        self.ttl = config.CLOUDFLARE_MIN_TTL_S


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
    
    def update_dns(self, new_ip: str) -> tuple[dict, float]:
        """
        Update the Cloudflare DNS record to point to the provided IP address.

        Performs a synchronous PUT against the Cloudflare API and validates
        the response payload. On success, returns the updated DNS record and
        the total operation latency.

        Args:
            new_ip (str): IPv4 address to publish for the DNS record.

        Returns:
            tuple[dict, float]:
                - dict: Updated DNS record as returned by Cloudflare ("result" field)
                - float: End-to-end operation latency in milliseconds

        Raises:
            RuntimeError:
                - If the Cloudflare API request fails (network error, timeout, non-2xx)
                - If the response payload is invalid or missing the DNS record
        """

        start = time.monotonic()
        resp = None

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
                url, headers=self.headers, json=payload, timeout=config.API_TIMEOUT_S
            )
            resp.raise_for_status()

            # Extract the new record from the PUT response body
            put_resp_data = resp.json()
            new_dns_record = put_resp_data.get("result")
            if not new_dns_record:
                raise RuntimeError(
                    "PUT succeeded but response contained no DNS record"
                )

            elapsed_ms = (time.monotonic() - start) * 1000
            return new_dns_record, elapsed_ms

        except requests.RequestException as e:
            elapsed_ms = (time.monotonic() - start) * 1000

            raise RuntimeError(
                f"Cloudflare PUT failed for DNS record " 
                f"[{self.dns_record_id}] → {new_ip} "
                f"(elapsed={elapsed_ms:.1f}ms)"
            ) from e

        except ValueError as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            raise RuntimeError(
                f"PUT succeeded but response was not valid JSON "
                f"(elapsed={elapsed_ms:.1f}ms)"
            ) from e
        
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
                url, headers=self.headers, timeout=config.API_TIMEOUT_S
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
