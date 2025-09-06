import pytest
from update_vpn_ddns.update_vpn_ddns import is_valid_ip

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
