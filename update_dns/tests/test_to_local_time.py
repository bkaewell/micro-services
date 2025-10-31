import pytest

from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

from update_dns.utils import to_local_time


@pytest.fixture
def mock_datetime_now():
    """Fixture to mock datetime.now with a fixed time, respecting the tz parameter"""
    def _now(tz=None):
        # Base time in UTC
        fixed_time = datetime(2025, 9, 8, 19, 7, 0, tzinfo=ZoneInfo("UTC"))
        # Convert to the requested timezone if provided
        return fixed_time.astimezone(tz) if tz else fixed_time

    with patch("update_dns.utils.datetime") as mock_datetime:
        # Configure the mock to override only the `now` method
        mock_datetime.now.side_effect = _now
        # Ensure other methods (i.e. fromisoformat) use the real datetime class
        mock_datetime.fromisoformat = datetime.fromisoformat
        yield mock_datetime

@pytest.mark.parametrize(
    "tz_name, expected_tz_name, expected_offset, expected_time",
    [
        ("America/New_York", "EDT", "-0400", "15:07:00"),  # Valid timezone, UTC 19:07:00 -> EDT 15:07:00
        ("UTC", "UTC", "+0000", "19:07:00"),               # Explicit UTC, no offset
        ("Invalid/TZ", "UTC", "+0000", "19:07:00"),        # Invalid timezone, defaults to UTC
    ]
)
def test_to_local_time_timezone_handling(mock_datetime_now, tz_name, expected_tz_name, expected_offset, expected_time, capsys):
    """
    Test to_local_time with different TZ environment variable settings
    Mocks os.getenv and datetime.now to ensure consistent results
    """
    with patch.dict("os.environ", {"TZ": tz_name}, clear=True):
        result = to_local_time()
        expected = f"2025-09-08\n{expected_time} {expected_tz_name} {expected_offset}"
        assert result == expected, f"Expected '{expected}', but got '{result}'"

        # Check for warning on invalid timezone
        if tz_name == "Invalid/TZ":
            captured = capsys.readouterr()
            assert "to_local_time: ⚠️ Exception: 'No time zone found with key Invalid/TZ', defaulting to UTC" in captured.out

@pytest.mark.parametrize(
    "iso_str, tz_name, expected_output",
    [
        # Valid ISO8601 string in UTC, converted to America/New_York
        (
            "2025-09-05T02:33:15.640385Z",
            "America/New_York",
            "2025-09-04\n22:33:15 EDT -0400",
        ),
        # Valid ISO8601 string with offset, converted to UTC
        (
            "2025-09-05T02:33:15+01:00",
            "UTC",
            "2025-09-05\n01:33:15 UTC +0000",
        ),
        # Invalid ISO8601 string, defaults to current time in America/New_York
        (
            "invalid-date",
            "America/New_York",
            "2025-09-08\n15:07:00 EDT -0400",
        ),
    ]
)
def test_to_local_time_iso_str(mock_datetime_now, iso_str, tz_name, expected_output, capsys):
    """
    Test to_local_time with ISO8601 string inputs
    Mocks os.getenv and datetime.now to ensure consistent results
    """
    with patch.dict("os.environ", {"TZ": tz_name}, clear=True):
        result = to_local_time(iso_str)
        assert result == expected_output, f"Expected '{expected_output}', but got '{result}'"

        # Check for warning on invalid ISO8601 string
        if iso_str == "invalid-date":
            captured = capsys.readouterr()
            assert f"to_local_time: ⚠️ Exception: Invalid isoformat string: '{iso_str}', defaulting to current time in {tz_name}" in captured.out
