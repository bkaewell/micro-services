
import pytest
from update_vpn_ddns.update_vpn_ddns import is_valid_ip

def test_valid_ipv4():
    assert is_valid_ip("192.168.0.1", "ipv4") is True



