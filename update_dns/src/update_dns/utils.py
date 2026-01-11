# --- Standard library imports ---
import ssl
import time
import socket
from dataclasses import dataclass

# --- Third-party imports ---
import requests

# --- Project imports ---
from .config import Config
from .logger import get_logger


# Define the logger once for the entire module
logger = get_logger("utils")

@dataclass(frozen=True)
class IPResolutionResult:
    ip: str | None
    elapsed_ms: float
    attempts: int
    success: bool

@dataclass(frozen=True)
class DoHLookupResult:
    ip: str | None
    elapsed_ms: float
    success: bool

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

def verify_wan_reachability(
    host: str = "1.1.1.1",
    port: int = 443,
    timeout: float = 2.0,
) -> bool:
    """
    Confirm true WAN reachability via TLS (Transport Layer Security)
    application-layer handshake.

    Requires successful:
      - TCP connection
      - TLS handshake

    Router-local responses cannot satisfy this probe.
    """
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host):
                return True
    except Exception:
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

def get_ip() -> IPResolutionResult:
    """
    Resolve the current external IPv4 address using multiple fallback services.

    Services are queried in priority order until a valid IPv4 address 
    (in plaintext) is returned or all sources fail. The reported latency 
    reflects both network response time and any fallback usage.
    """

    services = (
        "https://api.ipify.org", 
        "https://ifconfig.me/ip", 
        "https://ipv4.icanhazip.com", 
        "https://ipecho.net/plain", 
    )

    timeout = Config.API_TIMEOUT
    start = time.monotonic()
    attempts = 0

    for url in services:
        attempts += 1
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()

            ip = resp.text.strip()
            if is_valid_ip(ip):
                return IPResolutionResult(
                    ip=ip,
                    elapsed_ms=(time.monotonic() - start) * 1000,
                    attempts=attempts,
                    success=True,
                )
            
            logger.debug(f"Invalid IP returned from {url}: {ip!r}")

        except requests.RequestException as e:
            logger.debug(f"IP lookup failed via {url} ({e.__class__.__name__})")
    
    return IPResolutionResult(
        ip=None,
        elapsed_ms=(time.monotonic() - start) * 1000,
        attempts=attempts,
        success=False,
    )

def doh_lookup(hostname : str) -> DoHLookupResult:
    """
    Resolve a hostname to an IPv4 address using Cloudflare DNS-over-HTTPS.

    This is an authoritative, non-cached verification step used to confirm
    public DNS state after updates.

    """
    url = "https://cloudflare-dns.com/dns-query"
    params = {"name": hostname, "type": "A"}
    headers = {"Accept": "application/dns-json"}

    start = time.monotonic()

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
            return DoHLookupResult(
                ip=None,
                success=False,
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

        ip = answers[0].get("data")
        if not ip or not is_valid_ip(ip):
            logger.warning(f"Invalid A-record for {hostname}: {ip!r}")
            return DoHLookupResult(
                ip=None,
                success=False,
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

        logger.debug(f"DoH resolved {hostname} → {ip}")
        return DoHLookupResult(
            ip=ip,
            success=True,
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    except requests.RequestException as e:
        logger.debug(
            f"DoH request failed for {hostname}: {e.__class__.__name__}"
        )
        return DoHLookupResult(
            ip=None,
            success=False,
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

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
