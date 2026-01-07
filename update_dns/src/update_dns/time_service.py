# --- Standard library imports ---
import os
from zoneinfo import ZoneInfo
from datetime import datetime


class TimeService:
    """
    Efficient timezone-aware time utility.
    
    - TZ loaded once during class initialization
    - Provides:
        * now_local()
        * format_local()
        * heartbeat_string()
        * iso_to_local_string()
    """

    def __init__(self):
        tz_name = os.getenv("TZ", "UTC")
        try:
            self.tz = ZoneInfo(tz_name)
        except Exception:
            self.tz = ZoneInfo("UTC")

    # -------------------------
    # Wall clock utilities
    # -------------------------

    def now_local(self):
        """
        Returns:
            datetime: local timezone datetime
            str: formatted "MM/DD/YY @ HH:MM:SS TZ"
        """
        dt = datetime.now(self.tz)
        return dt, self.format_local(dt)

    def format_local(self, dt: datetime) -> str:
        """Format a datetime into the microservice format."""
        return dt.strftime("%m/%d/%y @ %H:%M:%S %Z")

    def heartbeat_string(self, dt: datetime) -> str:
        """Return 'Sat Dec 07 2025' format."""
        return dt.strftime("%a %b %d %Y")

    # -------------------------------
    # ISO8601 conversion utility
    # -------------------------------

    def iso_to_local_string(self, iso_str: str) -> str:
        """
        Convert an ISO8601 timestamp to:
            'MM/DD/YY @ HH:MM:SS TZ'

        Example:
            '2025-09-05T02:33:15.640385Z'
        """
        try:
            # Parse, normalize to UTC if Z is present
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            # Convert to local timezone
            dt_local = dt.astimezone(self.tz)
        except Exception:
            # Fall back: return now, but safely
            dt_local = datetime.now(self.tz)

        return self.format_local(dt_local)
