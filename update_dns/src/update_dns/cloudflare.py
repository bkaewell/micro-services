# ─── Standard library imports ───
import os
import json
import time
import requests

# ─── Project imports ───
from .logger import get_logger


class CloudflareDNSProvider:
    """
    Cloudflare DNS actuator.

    Thin, deterministic wrapper around the Cloudflare DNS API.
    Owns:
      - API auth
      - DNS record identity
      - Idempotent mutation primitives
    """
    # ─── Class Constants ───
    CLOUDFLARE_API_BASE_URL: str = "https://api.cloudflare.com/client/v4"

    def __init__(
        self,
        *,
        api_token: str,
        zone_id: str,
        dns_name: str,
        dns_record_id: str,
        ttl: int,
        proxied: bool = False,    # Grey cloud icon (not proxied thru Cloudflare)
        record_type: str = "A",   # Fixed type
        http_timeout_s: float = 5.0,
    ):
        """
        Initializes the client by resolving all config dependencies.
        """

        self.logger = get_logger("cloudflare")

        # ─── Identity & Auth ───
        self.api_token = api_token
        self.zone_id = zone_id
        self.dns_name = dns_name
        self.dns_record_id = dns_record_id

        # ─── Record Parameters ───
        self.ttl = ttl
        self.proxied = proxied
        self.record_type = record_type

        # ─── Transport ───
        self.http_timeout_s = http_timeout_s
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        self._validate_config()
        self.logger.info("Cloudflare DNS provider initialized")

    def _validate_config(self) -> None:
        """
        Validate Cloudflare DNS identity in one authoritative call.
        Fail fast on mismatch or auth errors.
        """
        resp = requests.get(
            f"{CloudflareDNSProvider.CLOUDFLARE_API_BASE_URL}/zones/{self.zone_id}/dns_records/{self.dns_record_id}",
            headers=self.headers,
            timeout=self.http_timeout_s,
        )
        resp.raise_for_status()

        data = resp.json()
        if not data.get("success"):
            raise ValueError(f"Cloudflare API error: {data}")

        record = data.get("result", {})
        if record.get("name") != self.dns_name:
            raise ValueError(
                f"DNS record mismatch: expected {self.dns_name}, "
                f"got {record.get('name')}"
            )
    
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
            f"{CloudflareDNSProvider.CLOUDFLARE_API_BASE_URL}/zones/"
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
                url, headers=self.headers, json=payload, timeout=self.http_timeout_s
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
            f"{CloudflareDNSProvider.CLOUDFLARE_API_BASE_URL}/zones/"
            f"{self.zone_id}/dns_records"
            f"?name={self.dns_name}"
            f"&type={self.record_type}"
        )
        
        try:
            resp = requests.get(
                url, headers=self.headers, timeout=self.http_timeout_s
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
