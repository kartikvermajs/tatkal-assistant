"""Unit tests for Phase 6 Accurate IST Clock."""

from datetime import date, datetime, time, timedelta
import pytest

from core.clock import (
    IST_TZ,
    TatkalClock,
    current_ist,
    is_tatkal_open,
    seconds_until,
)


@pytest.fixture
def clock():
    return TatkalClock()


# ==================== Timezone and Initialization Tests ====================


def test_ist_timezone_awareness(clock):
    now = clock.current_ist()
    assert now.tzinfo is not None
    # UTC offset for IST is +5 hours 30 minutes
    assert now.utcoffset() == timedelta(hours=5, minutes=30)


def test_ac_vs_non_ac_classification(clock):
    # AC classes
    for ac in ["1A", "2A", "3A", "3E", "CC", "EC", "3a", "cc"]:
        assert clock.is_ac_class(ac) is True
        assert clock.get_opening_time_of_day(ac) == time(10, 0, 0)

    # Non-AC classes
    for non_ac in ["SL", "2S", "sl", "2s"]:
        assert clock.is_ac_class(non_ac) is False
        assert clock.get_opening_time_of_day(non_ac) == time(11, 0, 0)


# ==================== Before Opening Tests ====================


def test_before_opening_ac(clock):
    # AC opens at 10:00:00. Test at 09:59:45
    test_dt = datetime(2026, 10, 16, 9, 59, 45, tzinfo=IST_TZ)
    clock.set_mock_time(test_dt)

    assert clock.is_tatkal_open("3A") is False

    open_dt = clock.get_tatkal_opening_datetime("3A")
    remaining = clock.seconds_until(open_dt)
    assert remaining == 15.0
    assert clock.format_remaining(remaining) == "00:00:15"


def test_before_opening_non_ac(clock):
    # Non-AC opens at 11:00:00. Test at 10:59:42
    test_dt = datetime(2026, 10, 16, 10, 59, 42, tzinfo=IST_TZ)
    clock.set_mock_time(test_dt)

    assert clock.is_tatkal_open("SL") is False

    open_dt = clock.get_tatkal_opening_datetime("SL")
    remaining = clock.seconds_until(open_dt)
    assert remaining == 18.0
    assert clock.format_remaining(remaining) == "00:00:18"


# ==================== Exactly Opening Tests ====================


def test_exactly_opening_ac(clock):
    # Exactly 10:00:00.000 IST
    test_dt = datetime(2026, 10, 16, 10, 0, 0, 0, tzinfo=IST_TZ)
    clock.set_mock_time(test_dt)

    assert clock.is_tatkal_open("3A") is True

    open_dt = clock.get_tatkal_opening_datetime("3A")
    remaining = clock.seconds_until(open_dt)
    assert remaining == 0.0
    assert clock.format_remaining(remaining) == "00:00:00"


def test_exactly_opening_non_ac(clock):
    # Exactly 11:00:00.000 IST
    test_dt = datetime(2026, 10, 16, 11, 0, 0, 0, tzinfo=IST_TZ)
    clock.set_mock_time(test_dt)

    assert clock.is_tatkal_open("SL") is True

    open_dt = clock.get_tatkal_opening_datetime("SL")
    remaining = clock.seconds_until(open_dt)
    assert remaining == 0.0
    assert clock.format_remaining(remaining) == "00:00:00"


# ==================== After Opening Tests ====================


def test_after_opening_ac(clock):
    # 10:05:30 IST (after AC opening)
    test_dt = datetime(2026, 10, 16, 10, 5, 30, tzinfo=IST_TZ)
    clock.set_mock_time(test_dt)

    assert clock.is_tatkal_open("3A") is True

    open_dt = clock.get_tatkal_opening_datetime("3A")
    assert clock.seconds_until(open_dt) == 0.0


def test_after_opening_non_ac(clock):
    # 11:00:05 IST (5 seconds after Non-AC opening)
    test_dt = datetime(2026, 10, 16, 11, 0, 5, tzinfo=IST_TZ)
    clock.set_mock_time(test_dt)

    assert clock.is_tatkal_open("SL") is True

    open_dt = clock.get_tatkal_opening_datetime("SL")
    assert clock.seconds_until(open_dt) == 0.0


# ==================== Midnight & Date Boundary Tests ====================


def test_midnight_transition_before(clock):
    # Test at 23:59:50 on day 1
    day1_night = datetime(2026, 10, 16, 23, 59, 50, tzinfo=IST_TZ)
    clock.set_mock_time(day1_night)

    # Tatkal opening for tomorrow (Oct 17, 10:00 AM)
    target_date = date(2026, 10, 17)
    open_dt = clock.get_tatkal_opening_datetime("3A", target_date=target_date)

    assert clock.is_tatkal_open("3A", target_date=target_date) is False

    # 10 seconds to midnight + 10 hours = 10s + 36000s = 36010s
    remaining = clock.seconds_until(open_dt)
    assert remaining == 36010.0
    # 10 hours and 10 seconds -> 10:00:10
    assert clock.format_remaining(remaining) == "10:00:10"


def test_midnight_transition_after(clock):
    # Test at 00:00:05 on day 2
    day2_morning = datetime(2026, 10, 17, 0, 0, 5, tzinfo=IST_TZ)
    clock.set_mock_time(day2_morning)

    # Opening today at 11:00:00
    open_dt = clock.get_tatkal_opening_datetime("SL")
    assert clock.is_tatkal_open("SL") is False

    # 11 hours - 5 seconds = 39600 - 5 = 39595s
    remaining = clock.seconds_until(open_dt)
    assert remaining == 39595.0
    # 10:59:55
    assert clock.format_remaining(remaining) == "10:59:55"


def test_convenience_functions():
    test_dt = datetime(2026, 10, 16, 10, 30, 0, tzinfo=IST_TZ)
    # AC is open at 10:30, Non-AC is not open yet
    assert is_tatkal_open("3A", reference_time=test_dt) is True
    assert is_tatkal_open("SL", reference_time=test_dt) is False
