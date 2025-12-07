import os
import socket
import requests

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Optional, Dict

from .config import Config
from .logger import get_logger


# Define the logger once for the entire module
logger = get_logger("utils")


def is_valid_ip(ip: str) -> bool:
    """
    Validate an IP address using socket.

    Args:
        ip: IP address string to validate.   

    Returns: 
        True if the IP address is valid, False otherwise.
    """

    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except socket.error:
        return False


def get_ip() -> str | None:
    """
    Fetch the external IP address.

    Returns: 
        External IP address as a string or None if no service succeeds.  
    """

    # API endpoints (redundant, outputs plain text, ranked by reliability)
    ip_services = [
        "https://api.ipify.org", 
        "https://ifconfig.me/ip", 
        "https://ipv4.icanhazip.com", 
        "https://ipecho.net/plain", 
    ]

    # Try API endpoints in order until one succeeds
    for service in ip_services:
        try:
            response = requests.get(service, timeout=Config.API_TIMEOUT)
            if response.status_code == 200:
                ip = response.text.strip()
                if is_valid_ip(ip):
                    logger.debug(f"🌐 External IP acquired ({service})")
                    return ip
        except requests.RequestException:
            logger.warning(f"Failed to retrieve IP from {service}, proceeding to next service...")
            continue  # Skip on network/timeout error and try next
    
    # No service returned a valid IP
    return None


def doh_lookup(hostname : str) -> Optional[str]:
    """
    Performs a DNS-over-HTTPS (DoH) lookup for a given hostname using 
    Cloudflare's 1.1.1.1 service.

    Validates public DNS IP post-update via non-cached verification layer.

    Args:
        hostname: The Fully Qualified Domain Name (FQDN) to query 
        (e.g., 'vpn.test.io').

    Returns:
        The resolved A-record IP address (str) or None if the lookup fails.
    """
    url = "https://cloudflare-dns.com/dns-query"
    params = {"name": hostname, "type": "A"}
    headers = {"Accept": "application/dns-json"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=Config.API_TIMEOUT)
        resp.raise_for_status()

        data: Dict[str, Any] = resp.json()

        answers = data.get("Answer", [])
        if not answers:
            logger.warning(
                f"DoH query succeeded for {hostname}, but no A-record was returned"
            )
            return None

        # Get the 'data' field (IP address) from the first A-record
        ip = answers[0].get("data")
        logger.debug(f"DoH resolved IP for {hostname}: {ip}")
        return ip 

    except requests.exceptions.Timeout:
        logger.error(f"DoH lookup timed out after {Config.API_TIMEOUT}s for {hostname}")
        return None
    except requests.exceptions.RequestException as e:
        # Catches ConnectionError, HTTPError, TooManyRedirects, etc.
        logger.error(f"DoH request failed for {hostname}: {type(e).__name__} - {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during DoH lookup for {hostname}")
        return None


def to_local_time(iso_str: str = None) -> str:
    """
    Convert an ISO8601 string or return the current datetime in the timezone 
    from TZ env var (default UTC), formatted as 'YYYY-MM-DD\\nHH:MM:SS TZ'.
    
    Args:
        iso_str (str, optional): ISO8601 string to convert 
        (i.e. '2025-09-05T02:33:15.640385Z').
    
    Returns:
        str: Formatted datetime string.
    """

    tz_name = os.getenv("TZ", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception as e:
        logger.warning(f"Invalid TZ '{tz_name}', defaulting to UTC: {e}")
        tz = ZoneInfo("UTC")

    try:
        if iso_str:
            # Parse ISO8601 string to datetime and convert to specified timezone
            dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
            dt = dt.astimezone(tz)
        else:
            # Get current time in the local timezone
            dt = datetime.now(tz)
    except Exception as e:
        logger.warning(f"Failed to convert time '{iso_str}', using now(): {e}")
        dt = datetime.now(tz)

    return dt.strftime("%m/%d/%y @ %H:%M:%S %Z")


def get_local_time(iso_utc_str: str = None):
    """
    Returns a tuple: (aware_datetime_obj, formatted_string)

    formatted_string example:
        "12/07/25 @ 17:57:54 EST"
    """
    tz_name = os.getenv("TZ", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception as e:
        logger.warning(f"Invalid TZ '{tz_name}', defaulting to UTC: {e}")
        tz = ZoneInfo("UTC")

    # --- Convert input or use now() ---
    if iso_utc_str:
        try:
            dt = datetime.fromisoformat(iso_utc_str.replace("Z", "+00:00"))
            dt = dt.astimezone(tz)
        except Exception as e:
            logger.warning(f"Failed to convert time '{iso_utc_str}', using now(): {e}")
            dt = datetime.now(tz)
    else:
        dt = datetime.now(tz)

    formatted = dt.strftime("%m/%d/%y @ %H:%M:%S %Z")
    return dt, formatted



