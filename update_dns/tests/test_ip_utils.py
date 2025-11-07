import pytest
import responses
from update_dns.utils import is_valid_ip, get_public_ip

# -------------------------------
# PARAMETRIZED TEST: IP Addresses
# -------------------------------
@pytest.mark.parametrize(
    "ip, expected_result",
    [
        ("8.8.8.8", True),
        ("7.7.7", False),
    ],
)

# ===================================
# TEST GROUP: IP Address Verification
# ===================================
def test_is_valid_ip(ip, expected_result):
    result = is_valid_ip(ip)

    assert expected_result is result


# =======================================================
# TEST GROUP: Public IP Fetch (Fallback / Sequence Logic)
# =======================================================
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
