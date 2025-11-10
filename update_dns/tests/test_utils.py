import os
import pytest
import responses
from datetime import datetime, timezone
from update_dns.utils import is_valid_ip, get_public_ip, to_local_time


# ===================================
# TEST GROUP: IP Address Verification
# ===================================
# Function: is_valid_ip()
# -----------------------
@pytest.mark.parametrize(
    "ip, expected_result",
    [
        # ✅ Valid IPv4
        ("8.8.8.8", True),

        # ❌ Invalid: incomplete octets
        ("7.7.7", False),
        
        # ❌ Invalid: empty input
        ("", False),
    ],
)

def test_is_valid_ip(ip, expected_result):
    """Verify is_valid_ip() correctly classifies valid/invalid inputs"""
    result = is_valid_ip(ip)

    assert expected_result is result


# =======================================================
# TEST GROUP: Public IP Fetch (Fallback / Sequence Logic)
# =======================================================
# Function: get_public_ip()
# -------------------------
@responses.activate
def test_get_public_ip_success():
    """Primary API service returns valid IP"""
    responses.add(responses.GET, "https://api.ipify.org", body="8.8.8.8", status=200)
    
    assert get_public_ip() == "8.8.8.8"

@responses.activate
def test_get_public_ip_fallback_success():
    """Primary API fails; secondary API returns valid IP"""
    responses.add(responses.GET, "https://api.ipify.org", body="x", status=408)
    responses.add(responses.GET, "https://ifconfig.me/ip", body="8.8.8.8", status=200)
    
    assert get_public_ip() == "8.8.8.8"

@responses.activate
def test_get_public_ip_all_fail():
    """All API services fail → return None"""
    for url in ["https://api.ipify.org", "https://ifconfig.me/ip"]:
        responses.add(responses.GET, url, body="x", status=408)
    
    assert get_public_ip() is None


# ================================
# TEST GROUP: Timezone Conversions
# ================================
# Function: to_local_time()
# -------------------------
@pytest.mark.parametrize(
    "env_tz, iso_str, expected_tz, expect_warning",
    [
        # ✅ Valid TZ + ISO → correct conversion
        ("Europe/Berlin", "2017-06-13T17:07:07.123456Z", "CEST", False), 

        # ✅ Valid TZ, no ISO → fallback to now()
        ("UTC", "", "UTC", False), 

        # ⚠️ Invalid TZ → fallback to UTC
        ("Invalid/Zone", "", "UTC", True), 

        # ⚠️ Invalid ISO → fallback to current time
        ("UTC", "invalid-date", "UTC", True), 
    ],
)

def test_to_local_time(monkeypatch, capsys, env_tz, iso_str, expected_tz, expect_warning):
    """Validate timezone conversion, fallback logic, and output format"""
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setenv("TZ", env_tz)
    result = to_local_time(iso_str)
    captured = capsys.readouterr()

    # Validate logical behavior
    assert expected_tz in result
    assert ("Exception" in captured.out) == expect_warning

    # Validate format consistency
    date_part, time_part = result.split("\n")
    datetime.strptime(date_part, "%Y-%m-%d")   # Check date formatting
    time_parts = time_part.split(" ")   # Check time formatting

    assert len(time_parts) == 3  # ['HH:MM:SS', 'TZ', '±HHMM']
