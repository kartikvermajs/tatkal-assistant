"""Accurate timezone-aware IST clock service for Tatkal booking windows."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Set
import zoneinfo

import config

try:
    IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
except Exception:  # Fallback if IANA database is unavailable
    IST_TZ = timezone(timedelta(hours=5, minutes=30), name="IST")

AC_CLASSES: Set[str] = {"1A", "2A", "3A", "3E", "CC", "EC"}
NON_AC_CLASSES: Set[str] = {"SL", "2S"}

TATKAL_OPENING_AC = time(10, 0, 0)
TATKAL_OPENING_NON_AC = time(11, 0, 0)


class TatkalClock:
    """Provides IST time tracking, Tatkal window calculations, and countdowns."""

    def __init__(self, tz: Optional[timezone] = None) -> None:
        self.tz = tz or IST_TZ
        self._mock_time: Optional[datetime] = None
        self._clock_offset: timedelta = timedelta(0)
        self._sync_attempted: bool = False

    def sync_with_server(self, url: Optional[str] = None) -> bool:
        """Sync local clock with IRCTC server time via HTTP Date header.

        Computes offset between local system clock and server clock.
        Best-effort: returns False on any network/parse failure without crashing.
        """
        try:
            import urllib.request
            from email.utils import parsedate_to_datetime

            target_url = url or config.IRCTC_BASE_URL
            req = urllib.request.Request(target_url, method="HEAD")
            req.add_header("User-Agent", "TatkalAssistant/0.1")
            with urllib.request.urlopen(req, timeout=5) as resp:
                date_header = resp.headers.get("Date")
                if date_header:
                    server_utc = parsedate_to_datetime(date_header)
                    local_utc = datetime.now(timezone.utc)
                    self._clock_offset = server_utc - local_utc
                    self._sync_attempted = True
                    return True
        except Exception:
            pass
        self._sync_attempted = True
        return False

    @property
    def is_synced(self) -> bool:
        """Return True if clock offset has been successfully computed from server."""
        return self._sync_attempted and self._clock_offset != timedelta(0)

    def set_mock_time(self, mock_dt: Optional[datetime]) -> None:
        """Inject a mock IST datetime for deterministic unit testing."""
        if mock_dt is not None:
            if mock_dt.tzinfo is None:
                self._mock_time = mock_dt.replace(tzinfo=self.tz)
            else:
                self._mock_time = mock_dt.astimezone(self.tz)
        else:
            self._mock_time = None

    def clear_mock_time(self) -> None:
        """Clear mock time and revert to real system clock."""
        self._mock_time = None

    def current_ist(self, reference_time: Optional[datetime] = None) -> datetime:
        """Return the current timezone-aware IST datetime.

        If clock sync has been performed, applies the server clock offset
        for higher accuracy during critical Tatkal opening windows.
        """
        if reference_time is not None:
            if reference_time.tzinfo is None:
                return reference_time.replace(tzinfo=self.tz)
            return reference_time.astimezone(self.tz)
        if self._mock_time is not None:
            return self._mock_time
        return (datetime.now(self.tz) + self._clock_offset)

    def is_ac_class(self, class_code: str) -> bool:
        """Check whether train class is AC (10:00 IST Tatkal opening)."""
        return class_code.strip().upper() in AC_CLASSES

    def get_opening_time_of_day(self, class_code: str) -> time:
        """Return the Tatkal opening time (10:00 for AC, 11:00 for Non-AC)."""
        return TATKAL_OPENING_AC if self.is_ac_class(class_code) else TATKAL_OPENING_NON_AC

    def get_tatkal_opening_datetime(
        self,
        class_code: str,
        target_date: Optional[date] = None,
        reference_time: Optional[datetime] = None,
    ) -> datetime:
        """Calculate the timezone-aware Tatkal opening datetime for a given class and date."""
        now = self.current_ist(reference_time)
        day = target_date or now.date()
        open_time = self.get_opening_time_of_day(class_code)
        return datetime.combine(day, open_time, tzinfo=self.tz)

    def seconds_until(
        self,
        target_time: datetime,
        reference_time: Optional[datetime] = None,
    ) -> float:
        """Calculate remaining seconds until target timezone-aware datetime.

        Returns 0.0 if target is already passed.
        """
        now = self.current_ist(reference_time)
        if target_time.tzinfo is None:
            target = target_time.replace(tzinfo=self.tz)
        else:
            target = target_time.astimezone(self.tz)

        delta = (target - now).total_seconds()
        return max(0.0, delta)

    def is_tatkal_open(
        self,
        class_code: str,
        reference_time: Optional[datetime] = None,
        target_date: Optional[date] = None,
    ) -> bool:
        """Determine if Tatkal booking window is currently open using datetime comparison.

        Does not perform string comparison; compares timezone-aware datetime objects directly.
        """
        now = self.current_ist(reference_time)
        opening_dt = self.get_tatkal_opening_datetime(class_code, target_date=target_date, reference_time=now)
        return now >= opening_dt

    @staticmethod
    def format_time(dt: datetime) -> str:
        """Format datetime to HH:MM:SS string."""
        return dt.strftime("%H:%M:%S")

    @staticmethod
    def format_remaining(seconds: float) -> str:
        """Format remaining seconds as HH:MM:SS string."""
        total_secs = int(max(0.0, seconds))
        hours = total_secs // 3600
        minutes = (total_secs % 3600) // 60
        secs = total_secs % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# Default singleton instance for easy import
default_clock = TatkalClock()


# Module-level convenience functions using default_clock
def current_ist(reference_time: Optional[datetime] = None) -> datetime:
    return default_clock.current_ist(reference_time)


def seconds_until(target_time: datetime, reference_time: Optional[datetime] = None) -> float:
    return default_clock.seconds_until(target_time, reference_time)


def is_tatkal_open(
    class_code: str,
    reference_time: Optional[datetime] = None,
    target_date: Optional[date] = None,
) -> bool:
    return default_clock.is_tatkal_open(class_code, reference_time, target_date)
