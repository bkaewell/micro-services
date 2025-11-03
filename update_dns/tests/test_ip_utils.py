import pytest
import responses

from update_dns.utils import is_valid_ip, get_public_ip

# ============================
# Unit Tests for is_valid_ip()
# Purpose: Validate IP address
# ============================

# Google Public DNS
def test_valid_ip_address():
    assert is_valid_ip("8.8.8.8") is True

def test_invalid_ip_address():
    assert is_valid_ip("777.777.777.777") is False


# =================================================================
# Unit Tests for get_public_ip()
# Purpose: Ensure public IP fetching logic works with fallback APIs
# =================================================================
@responses.activate
def test_get_public_ip_success():
    responses.add(responses.GET, "https://api.ipify.org", body="8.8.8.8", status=200)
    assert get_public_ip() == "8.8.8.8"

@responses.activate
def test_get_public_ip_fallback_success():
    responses.add(responses.GET, "https://api.ipify.org", body="x", status=408)
    responses.add(responses.GET, "https://ifconfig.me/ip", body="8.8.8.8", status=200)
    assert get_public_ip() == "8.8.8.8"

@responses.activate
def test_get_public_ip_all_fail():
    for url in ["https://api.ipify.org", "https://ifconfig.me/ip"]:
        responses.add(responses.GET, url, body="x", status=408)
    assert get_public_ip() is None
