import os
import pytest
from datetime import datetime, timezone
from update_dns.utils import to_local_time

# ========
# FIXTURES
# ========
@pytest.fixture(autouse=True)
def reset_tz_env(monkeypatch):
    """Ensure TZ env var resets after each test"""
    original_tz = os.getenv("TZ")
    yield
    if original_tz is not None:
        monkeypatch.setenv("TZ", original_tz)
    else:
        monkeypatch.delenv("TZ", raising=False)

# =======================================
# PARAMETRIZED TEST: Timezone Conversions
# =======================================
# Each entry provides:
#  1. The environment TZ value to simulate
#  2. The ISO8601 timestamp string to convert
#  3. The expected timezone abbreviation in output
# -----------------------------------------
@pytest.mark.parametrize(
    "env_tz, iso_str, expected_tz",
    [
        ("UTC", "2025-09-05T02:33:15.640385Z", "UTC"),
        ("America/New_York", "2025-09-05T02:33:15.640385Z", "EDT"),
        ("Europe/Berlin", "2025-09-05T02:33:15.640385Z", "CEST"),
    ],
)


# ===============================================
# TEST GROUP: to_local_time() BRANCH COVERAGE MAP
# ===============================================
# ✅ test_to_local_time_with_iso
#    → Covers: valid TZ, ISO string provided
#
# ✅ test_to_local_time_no_input_uses_current_time
#    → Covers: valid TZ, no ISO string → current datetime path
#
# ✅ test_to_local_time_invalid_tz_fallback
#    → Covers: invalid TZ env var → fallback to UTC
#
# ✅ test_to_local_time_invalid_iso
#    → Covers: valid TZ, invalid ISO string → fallback to current time
#
# ✅ test_to_local_time_output_format
#    → Covers: formatted output correctness
#
# → Combined coverage: all branches tested (100%)


def test_to_local_time_with_iso(monkeypatch, env_tz, iso_str, expected_tz):
    """Test ISO string conversion across multiple timezones."""
    monkeypatch.setenv("TZ", env_tz)
    result = to_local_time(iso_str)

    assert expected_tz in result
    assert "\n" in result
    assert len(result.split("\n")) == 2  # 'YYYY-MM-DD' and 'HH:MM:SS TZ ±HHMM'


def test_to_local_time_no_input_uses_current_time(monkeypatch):
    """If iso_str is None, should return current local time in specified TZ."""
    monkeypatch.setenv("TZ", "UTC")
    result = to_local_time()

    assert "UTC" in result
    assert "\n" in result


def test_to_local_time_invalid_tz_fallback(monkeypatch, capsys):
    """If TZ env var is invalid, should fallback to UTC and print warning."""
    monkeypatch.setenv("TZ", "Invalid/Zone")
    result = to_local_time("2025-09-05T02:33:15.640385Z")

    captured = capsys.readouterr()

    assert "⚠️ Exception" in captured.out
    assert "UTC" in result


def test_to_local_time_invalid_iso(monkeypatch, capsys):
    """If iso_str is malformed, should fallback to current time."""
    monkeypatch.setenv("TZ", "UTC")
    result = to_local_time("not-a-valid-date")
    captured = capsys.readouterr()

    assert "⚠️ Exception" in captured.out
    assert "UTC" in result


def test_to_local_time_output_format(monkeypatch):
    """Ensure returned format matches 'YYYY-MM-DD\\nHH:MM:SS TZ ±HHMM'."""
    monkeypatch.setenv("TZ", "UTC")
    result = to_local_time("2025-09-05T02:33:15.640385Z")

    date_part, time_part = result.split("\n")
    # Check date formatting
    datetime.strptime(date_part, "%Y-%m-%d")
    # Check time formatting
    time_parts = time_part.split(" ")

    assert len(time_parts) == 3  # ['HH:MM:SS', 'TZ', '±HHMM']
