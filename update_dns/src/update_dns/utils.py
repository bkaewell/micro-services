# --- Standard library imports ---
import ssl
import time
import socket
from typing import Optional
from dataclasses import dataclass

# --- Third-party imports ---
import requests

# --- Project imports ---
from .config import config
from .logger import get_logger


# Define the logger once for the entire module
logger = get_logger("utils")

@dataclass(frozen=True)
class ReachabilityResult:
    success: bool
    elapsed_ms: float
    error: Optional[str] = None

@dataclass(frozen=True)
class IPResolutionResult:
    ip: str | None
    elapsed_ms: float
    attempts: int
    max_attempts: int
    success: bool

@dataclass(frozen=True)
class DoHLookupResult:
    ip: str | None
    elapsed_ms: float
    success: bool

def ping_host(ip: str, port: int = 80, timeout: float = 1.5) -> ReachabilityResult:
    """
    Check host reachability via a TCP connect probe (Layer 4).

    This probe is intentionally lightweight and ICMP-free to avoid
    elevated privileges and platform-specific behavior.

    Signal strength:
        Weak — used for observability and diagnostics only.
    """

    start = time.monotonic()

    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return ReachabilityResult(
                success=True,
                elapsed_ms=(time.monotonic() - start) * 1000,
            )
    except (OSError, socket.timeout) as e:
        return ReachabilityResult(
            success=False,
            elapsed_ms=(time.monotonic() - start) * 1000,
            error=type(e).__name__,
        )

def verify_wan_reachability(
    host: str = "1.1.1.1",
    port: int = 443,
    timeout: float = 2.0,
) -> ReachabilityResult:
    """
    Confirm true WAN reachability using a TCP + TLS handshake.

    This probe cannot be satisfied by router-local responses and
    therefore represents a strong indicator of upstream connectivity.
    """

    start = time.monotonic()

    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host):
                return ReachabilityResult(
                    success=True,
                    elapsed_ms=(time.monotonic() - start) * 1000,
                )

    except Exception as e:
        return ReachabilityResult(
            success=False,
            elapsed_ms=(time.monotonic() - start) * 1000,
            error=type(e).__name__,
        )

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
    Resolve the current external IPv4 address using prioritized public 
    endpoints, returning a result that reflects confidence in the resolved IP,
    total wall-clock latency, and attempt count; callers are expected to 
    ensure WAN reachability, and failure indicates insufficient confidence 
    rather than definitive network outage.
    """
    start = time.monotonic()
    services = (
        "https://api.ipify.org", 
        "https://ifconfig.me/ip", 
        "https://ipv4.icanhazip.com", 
        "https://ipecho.net/plain", 
    )
    attempts = 0
    max_attempts = len(services)
    timeout = config.API_TIMEOUT_S

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
                    max_attempts=max_attempts,
                    success=True,
                )
            
            logger.warn(f"Invalid IP returned from {url}: {ip!r}")

        except requests.RequestException as e:
            logger.debug(f"IP lookup failed via {url} ({e.__class__.__name__})")

    return IPResolutionResult(
        ip=None,
        elapsed_ms=(time.monotonic() - start) * 1000,
        attempts=attempts,
        max_attempts=max_attempts,
        success=False,
    )

def doh_lookup(hostname : str) -> DoHLookupResult:
    """
    Resolve a hostname to an IPv4 address using Cloudflare DNS-over-HTTPS.

    This function performs an authoritative, non-cached DNS lookup against
    Cloudflare's DoH endpoint and is used to verify public DNS state during
    initialization and recovery paths.

    Invariant:
        - If success is True, ip is guaranteed to be a valid IPv4 string.
        - If success is False, ip will be None.

    Callers may therefore safely assume that a successful result always
    contains a usable IP address and do not need to perform additional
    validation.
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
            timeout=config.API_TIMEOUT_S
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
