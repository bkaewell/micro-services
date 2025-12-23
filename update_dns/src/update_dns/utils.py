# --- Standard library imports ---
import time
import socket
from typing import Optional

# --- Third-party imports ---
import requests

# --- Project imports ---
from .config import Config
from .logger import get_logger


# Define the logger once for the entire module
logger = get_logger("utils")

def ping_host(ip: str, port: int = 80, timeout: float = 1.0) -> bool:
    """
    Check host reachability efficiently and cross-platform.

    Performs a TCP connection (Layer 4) to the given IP/hostname and port, 
    avoiding ICMP so no admin privileges are required.  

    Conceptually, this function helps distinguish:
      - LAN health (router reachability)
      - WAN health (external routing)

    Args:
        ip: IP address or hostname to check.
        port: TCP port to attempt (default 80).
        timeout: Seconds before giving up.

    Returns:
        True if the host is reachable, False otherwise.
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False

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


# def get_ip() -> tuple[str | None, float]:
#     start = time.monotonic()
#     ip = _get_ip_internal()   # your existing logic
#     elapsed_ms = (time.monotonic() - start) * 1000
#     return ip, elapsed_ms


def doh_lookup(hostname : str) -> Optional[str]:
    """
    Resolve a hostname to an IPv4 address using Cloudflare DNS-over-HTTPS.

    This is an authoritative, non-cached verification step used to confirm
    public DNS state after updates.

    Returns:
        IPv4 address as a string, or None if resolution fails.
    """
    url = "https://cloudflare-dns.com/dns-query"
    params = {"name": hostname, "type": "A"}
    headers = {"Accept": "application/dns-json"}

    try:
        resp = requests.get(
            url, 
            params=params, 
            headers=headers, 
            timeout=Config.API_TIMEOUT
        )
        resp.raise_for_status()

        answers = resp.json().get("Answer", [])
        if not answers:
            logger.warning(f"No A-record returned for {hostname}")
            return None

        ip = answers[0].get("data")
        if not ip or not is_valid_ip(ip):
            logger.warning(f"Invalid A-record for {hostname}: {ip!r}")
            return None

        logger.debug(f"DoH resolved {hostname} → {ip}")
        return ip

    except requests.RequestException as e:
        logger.debug(
            f"DoH request failed for {hostname}: {e.__class__.__name__}"
        )
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
        self.logger.timing(f"Timing | {label:<34} [{delta_ms:8.1f} ms]")
        self.lap_start = now

    def end_cycle(self):
        """End-to-end duration."""
        if self.cycle_start is None:
            return
        total_ms = (time.perf_counter() - self.cycle_start) * 1000
        self.logger.timing(f"Timing | {'Total run_cycle()':<28} [{total_ms:8.1f} ms]")
        self.cycle_start = None
        self.lap_start = None
