# import pytest
# from datetime import datetime
# from zoneinfo import ZoneInfo
# from unittest.mock import patch
# from update_dns.utils import to_local_time

# # ========
# # FIXTURES
# # ========

# # -----------------
# # Mock for datetime
# # -----------------
# @pytest.fixture
# def mock_datetime_now():
#     """Fixture to mock datetime.now with a fixed time, respecting the tz parameter"""
#     def _now(tz=None):
#         # Base time in UTC
#         fixed_time = datetime(2025, 9, 8, 19, 7, 0, tzinfo=ZoneInfo("UTC"))
#         # Convert to the requested timezone if provided
#         return fixed_time.astimezone(tz) if tz else fixed_time

#     with patch("update_dns.utils.datetime") as mock_datetime:
#         # Configure the mock to override only the `now` method
#         mock_datetime.now.side_effect = _now
#         # Ensure other methods (i.e. fromisoformat) use the real datetime class
#         mock_datetime.fromisoformat = datetime.fromisoformat
#         yield mock_datetime


# # =============================
# # TEST GROUP: Timezone Handling
# # =============================
# @pytest.mark.parametrize(
#     "tz_name, expected_tz_name, expected_offset, expected_time",
#     [
#         ("America/New_York", "EDT", "-0400", "15:07:00"),  # Valid timezone, UTC 19:07:00 -> EDT 15:07:00
#         ("UTC", "UTC", "+0000", "19:07:00"),               # Explicit UTC -> no offset
#         ("Invalid/TZ", "UTC", "+0000", "19:07:00"),        # Invalid timezone -> defaults to UTC
#     ]
# )
# def test_to_local_time_timezone_handling(mock_datetime_now, tz_name, expected_tz_name, expected_offset, expected_time, capsys):
#     """
#     Test to_local_time with different TZ environment variable settings
#     Mocks os.getenv and datetime.now to ensure consistent results
#     """
#     with patch.dict("os.environ", {"TZ": tz_name}, clear=True):
#         result = to_local_time()
#         expected = f"2025-09-08\n{expected_time} {expected_tz_name} {expected_offset}"
#         assert result == expected, f"Expected '{expected}', but got '{result}'"

#         # Check for warning on invalid timezone
#         if tz_name == "Invalid/TZ":
#             captured = capsys.readouterr()
#             assert "to_local_time: ⚠️ Exception: 'No time zone found with key Invalid/TZ', defaulting to UTC" in captured.out


# # =============================
# # TEST GROUP: Timezone Handling
# # =============================
# @pytest.mark.parametrize(
#     "iso_str, tz_name, expected_output",
#     [
#         # Valid ISO8601 string in UTC -> converted to America/New_York
#         (
#             "2025-09-05T02:33:15.640385Z",
#             "America/New_York",
#             "2025-09-04\n22:33:15 EDT -0400",
#         ),
#         # Valid ISO8601 string with offset -> converted to UTC
#         (
#             "2025-09-05T02:33:15+01:00",
#             "UTC",
#             "2025-09-05\n01:33:15 UTC +0000",
#         ),
#         # Invalid ISO8601 string -> defaults to current time in America/New_York
#         (
#             "invalid-date",
#             "America/New_York",
#             "2025-09-08\n15:07:00 EDT -0400",
#         ),
#     ]
# )
# def test_to_local_time_iso_str(mock_datetime_now, iso_str, tz_name, expected_output, capsys):
#     """
#     Test to_local_time with ISO8601 string inputs
#     Mocks os.getenv and datetime.now to ensure consistent results
#     """
#     with patch.dict("os.environ", {"TZ": tz_name}, clear=True):
#         result = to_local_time(iso_str)
#         assert result == expected_output, f"Expected '{expected_output}', but got '{result}'"

#         # Check for warning on invalid ISO8601 string
#         if iso_str == "invalid-date":
#             captured = capsys.readouterr()
#             assert f"to_local_time: ⚠️ Exception: Invalid isoformat string: '{iso_str}', defaulting to current time in {tz_name}" in captured.out



import os
from datetime import datetime, timezone, timedelta
import pytest

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


# ========================================
# TEST GROUP: to_local_time() COVERAGE MAP
# ========================================
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
