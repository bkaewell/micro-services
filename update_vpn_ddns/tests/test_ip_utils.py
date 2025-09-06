import pytest
import responses

from update_vpn_ddns.update_vpn_ddns import is_valid_ip
from update_vpn_ddns.update_vpn_ddns import get_public_ip

# ==============================================================
# Unit Tests for is_valid_ip()
# Purpose: Validate IPv4 and IPv6 addresses and version handling
# ==============================================================

# Google Public DNS
def test_valid_ipv4():
    assert is_valid_ip("8.8.8.8", "ipv4") is True

def test_invalid_ipv4():
    assert is_valid_ip("777.777.777.777", "ipv4") is False

# Google Public DNS
def test_valid_ipv6():
    assert is_valid_ip("2001:4860:4860::8888", "ipv6") is True

def test_invalid_ipv6():
    assert is_valid_ip("8.8.8.8", "ipv6") is False

def test_invalid_ip_version():
    assert is_valid_ip("8.8.8.8", "ipv7") is False


# =================================================================
# Unit Tests for get_public_ip()
# Purpose: Ensure public IP fetching logic works with fallback APIs
# =================================================================
@responses.activate
def test_get_public_ip_ipv4():
    responses.add(responses.GET, "https://api.ipify.org", body="8.8.8.8", status=200)
    ip = get_public_ip("ipv4")
    assert ip == "8.8.8.8"

