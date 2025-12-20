import time
import socket
import requests

from typing import Any, Optional, Dict

from .config import Config
from .logger import get_logger


# Define the logger once for the entire module
logger = get_logger("utils")

def is_valid_ip(ip: str) -> bool:
    """
    Validate an IPv4 address using socket.

    Args:
        ip: IPv4 address string to validate.   

    Returns: 
        True if the IPv4 address is valid, False otherwise.
    """

    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except socket.error:
        return False

def get_ip() -> str | None:
    """
    Resolve the current external IPv4 address.

    Tries multiple plaintext IP services in priority order.
    Returns the first valid IP or None if all sources fail. 
    """

    services = (
        "https://api.ipify.org", 
        "https://ifconfig.me/ip", 
        "https://ipv4.icanhazip.com", 
        "https://ipecho.net/plain", 
    )

    timeout = Config.API_TIMEOUT

    for url in services:
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()

            ip = resp.text.strip()
            if is_valid_ip(ip):
                logger.debug(f"🌐 External IP acquired ({url})")
                return ip
            
            logger.warning(f"Invalid IP returned from {url}: {ip!r}")

        except requests.RequestException as e:
            logger.warning(f"IP lookup failed via {url} ({e.__class__.__name__})")
    
    return None

def dns_ready(hostname: str = "api.cloudflare.com") -> bool:
    """
    Returns True if DNS resolution for Cloudflare is functional.

    This is mission-critical DNS for the infra agent.
    """
    try:
        socket.gethostbyname(hostname)
        return True
    except socket.gaierror:
        return False

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

        # Extrac the candidate IP address from the first A-record
        ip = answers[0].get("data")
        logger.debug(f"DoH resolved IP for {hostname}: {ip}")

        if not is_valid_ip(ip):
            logger.warning(
                f"DoH returned invalid IP for {hostname}: {ip!r}"
            )
            return None

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

# ============================================================
# Performance Timing Utilities (optional instrumentation)
# ============================================================

class Timer:
    def __init__(self, logger):
        self.logger = logger
        self.cycle_start = None
        self.lap_start = None

    def start_cycle(self):
        """Call once at the beginning of a run cycle."""
        now = time.perf_counter()  # Recommended clock for benchmarking
        self.cycle_start = now
        self.lap_start = now

    def lap(self, label: str):
        """Measure time since last lap."""
        if self.lap_start is None:
            return

        now = time.perf_counter()
        delta_ms = (now - self.lap_start) * 1000
        self.logger.timing(f"Timing | {label:<32} [{delta_ms:8.1f} ms]")
        self.lap_start = now

    def end_cycle(self):
        """End-to-end duration."""
        if self.cycle_start is None:
            return
        total_ms = (time.perf_counter() - self.cycle_start) * 1000
        self.logger.timing(f"Timing | {'Total run_cycle()':<26} [{total_ms:8.1f} ms]")
        self.cycle_start = None
        self.lap_start = None
