import os
import pytest
import responses
from datetime import datetime, timezone
from update_dns.utils import is_valid_ip, get_public_ip, to_local_time


# ===================================
# TEST GROUP: IP Address Verification
# ===================================
# Function under test: is_valid_ip()
# ----------------------------------
@pytest.mark.parametrize(
    "ip, expected_result",
    [
        ("8.8.8.8", True),
        ("7.7.7", False),
        ("", False),
    ],
)

def test_is_valid_ip(ip, expected_result):
    result = is_valid_ip(ip)

    assert expected_result is result


# =======================================================
# TEST GROUP: Public IP Fetch (Fallback / Sequence Logic)
# =======================================================
# Function under test: get_public_ip()
# ------------------------------------
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


# ========
# FIXTURES
# ========
@pytest.fixture(autouse=True)
def reset_tz_env(monkeypatch):
    """Automatically resets TZ env var before each test"""
    original_tz = os.getenv("TZ")
    yield
    if original_tz is not None:
        monkeypatch.setenv("TZ", original_tz)
    else:
        monkeypatch.delenv("TZ", raising=False)

# ================================
# TEST GROUP: Timezone Conversions
# ================================
# Function under test: to_local_time()
# ------------------------------------
@pytest.mark.parametrize(
    "env_tz, iso_str, expected_tz, expect_warning",
    [
        ("Europe/Berlin", "2025-09-05T02:33:15.640385Z", "CEST", False), # Valid TZ
        ("UTC", "", "UTC", False), # Valid TZ, no ISO str → fallback to current datetime
        ("Invalid/Zone", "", "UTC", True), # Invalid TZ, no ISO str → fallback to UTC
        ("UTC", "invalid-date", "UTC", True), #Valid TZ, invalid ISO str → fallback to current datetime
    ],
)

def test_to_local_time_with_iso(monkeypatch, capsys, env_tz, iso_str, expected_tz, expect_warning):
    """Test ISO string conversion across multiple timezones"""
    monkeypatch.setenv("TZ", env_tz)
    result = to_local_time(iso_str)
    captured = capsys.readouterr()

    assert expected_tz in result
    assert "\n" in result
    assert len(result.split("\n")) == 2
    # assert ("⚠️ Exception" in captured.out) == expect_warning
    assert ("Exception" in captured.out) == expect_warning

def test_to_local_time_output_format(monkeypatch):
    """Ensure returned format matches 'YYYY-MM-DD\\nHH:MM:SS TZ ±HHMM'"""
    monkeypatch.setenv("TZ", "UTC")
    result = to_local_time("2025-09-05T02:33:15.640385Z")

    date_part, time_part = result.split("\n")
    # Check date formatting
    datetime.strptime(date_part, "%Y-%m-%d")
    # Check time formatting
    time_parts = time_part.split(" ")

    assert len(time_parts) == 3  # ['HH:MM:SS', 'TZ', '±HHMM']
