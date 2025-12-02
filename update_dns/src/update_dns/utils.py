import os
import socket
import requests

from datetime import datetime
from zoneinfo import ZoneInfo

from .logger import get_logger

# Define the logger once for the entire module
logger = get_logger("utils")


def is_valid_ip(ip: str) -> bool:
    """
    Validate an IP address using socket

    Args:
        ip: IP address string to validate   

    Returns: 
        True if the IP address is valid, False otherwise
    """

    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except socket.error:
        return False


def get_ip() -> str | None:
    """
    Fetch the external IP address

    Returns: 
        External IP address as a string or None if no service succeeds     
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
            response = requests.get(service, timeout=5)
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


def to_local_time(iso_str: str = None) -> str:
    """
    Convert an ISO8601 string or return the current datetime in the timezone from TZ env var (default UTC),
    formatted as 'YYYY-MM-DD\\nHH:MM:SS TZ ±HHMM'
    
    Args:
        iso_str (str, optional): ISO8601 string to convert (i.e. '2025-09-05T02:33:15.640385Z')
    
    Returns:
        str: Formatted datetime string
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
