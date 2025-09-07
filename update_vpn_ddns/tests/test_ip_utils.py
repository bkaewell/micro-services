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
def test_get_public_ip_invalid_version():
    with pytest.raises(ValueError):
        get_public_ip("ipv7")

@responses.activate
def test_get_public_ip_ipv4_success():
    responses.add(responses.GET, "https://api.ipify.org", body="8.8.8.8", status=200)
    assert get_public_ip("ipv4") == "8.8.8.8"

@responses.activate
def test_get_public_ip_ipv4_fallback_success():
    responses.add(responses.GET, "https://api.ipify.org", body="x", status=408)
    responses.add(responses.GET, "https://ifconfig.me/ip", body="8.8.8.8", status=200)
    assert get_public_ip("ipv4") == "8.8.8.8"

@responses.activate
def test_get_public_ip_ipv4_all_fail():
    for url in ["https://api.ipify.org", "https://ifconfig.me/ip"]:
        responses.add(responses.GET, url, body="x", status=408)
    assert get_public_ip("ipv4") is None

@responses.activate
def test_get_public_ip_ipv6_success():
    responses.add(responses.GET, "https://api64.ipify.org", body="2001:4860:4860::8888", status=200)
    assert get_public_ip("ipv6") == "2001:4860:4860::8888"

@responses.activate
def test_get_public_ip_ipv6_all_fail():
    for url in ["https://api64.ipify.org", "https://ifconfig.me"]:
        responses.add(responses.GET, url, body="x", status=408)
    assert get_public_ip("ipv6") is None

