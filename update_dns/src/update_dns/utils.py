# --- Standard library imports ---
import os
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

def ping_host(ip: str, timeout: float = 1.0) -> bool:
    """
    Check Layer 3 reachability to an IP address.

    Used to distinguish:
    - LAN health (router reachability)
    - WAN health (external routing)
    """
    # This check uses ICMP (part of Layer 3/4) and is quick and low-resource
    return os.system(f"ping -c 1 -W 2 {ip} > /dev/null 2>&1") == 0

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
