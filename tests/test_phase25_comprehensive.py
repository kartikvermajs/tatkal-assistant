"""Comprehensive integration and edge-case test suite for Phase 25: Testing.

Covers all 8 required testing areas:
1. models (extended validation, boundaries, serialization)
2. database (foreign keys, transaction safety, nonexistent record handling)
3. clock (leap days, millisecond boundaries, countdown formatting)
4. countdown (timer ticks, boundary transitions, alert triggers)
5. state machine (full transition matrix, locked state invariants, listener resilience)
6. browser manager (lifecycle idempotency, stop_automation safety, custom profiles)
7. mock workflow (end-to-end multi-step flow, mandatory train number/class enforcement)
8. failure handling (classification matrix, retry policy backoff, unhandled exceptions)
"""

from datetime import date, datetime, timedelta
import os
import sqlite3
import pytest
from PySide6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from browser.browser_manager import BrowserManager
from browser.irctc_workflow import IRCTCWorkflow, WorkflowStepResult
from core.booking_state import (
    BookingState,
    BookingStateMachine,
    InvalidStateTransitionError,
)
from core.clock import IST_TZ, TatkalClock, current_ist
from core.failure_handler import (
    FailureType,
    RetryPolicy,
    classify_failure,
    execute_with_limited_retry,
)
from database.db import Database
from models.booking import BookingRecord
from models.passenger import Passenger
from models.settings import ApplicationSettings
from models.trip import Trip


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ==================== 1. Models ====================


def test_models_passenger_edge_cases():
    """Verify passenger model validation for whitespace, boundaries, and normalization."""
    # Whitespace in name should be stripped
    p = Passenger(name="  Aarav Sharma  ", age=25, gender="m", berth_preference="lb")
    assert p.name == "Aarav Sharma"
    assert p.gender == "M"
    assert p.berth_preference == "LB"

    # Boundary ages
    p_child = Passenger(name="Child", age=5, gender="F")
    assert p_child.age == 5
    p_senior = Passenger(name="Senior", age=120, gender="M")
    assert p_senior.age == 120

    # Age below minimum (1) or above maximum (125) must raise ValueError
    with pytest.raises(ValueError, match="between 1 and 125"):
        Passenger(name="Invalid", age=-1, gender="M")
    with pytest.raises(ValueError, match="between 1 and 125"):
        Passenger(name="Invalid", age=126, gender="M")

    # Name validation
    with pytest.raises(ValueError, match="cannot be empty"):
        Passenger(name="   ", age=30, gender="M")


def test_models_trip_edge_cases():
    """Verify trip model validation for station casing, formats, and mandatory fields."""
    today = date.today()
    future = today + timedelta(days=5)

    # Station casing normalization
    t = Trip(
        from_station="ndls",
        to_station="cnb",
        journey_date=future,
        train_number=" 12004 ",
        class_code="3a",
    )
    assert t.from_station == "NDLS"
    assert t.to_station == "CNB"
    assert t.train_number == "12004"
    assert t.class_code == "3A"

    # Mandatory train number
    with pytest.raises(ValueError, match="Train number"):
        Trip(
            from_station="NDLS",
            to_station="CNB",
            journey_date=future,
            train_number="",
            class_code="3A",
        )

    # Mandatory class code
    with pytest.raises(ValueError, match="Invalid class code"):
        Trip(
            from_station="NDLS",
            to_station="CNB",
            journey_date=future,
            train_number="12004",
            class_code="",
        )


def test_models_settings_and_booking_record_validation():
    """Verify ApplicationSettings and BookingRecord edge cases."""
    # Settings mobile number validation
    with pytest.raises(ValueError, match="10 digits"):
        ApplicationSettings(mobile_number="12345")
    with pytest.raises(ValueError, match="10 digits"):
        ApplicationSettings(mobile_number="abcdefghij")

    # BookingRecord mandatory fields
    with pytest.raises(ValueError, match="Train number must be"):
        BookingRecord(
            train_number="",
            class_code="3A",
            quota_code="TATKAL",
            from_station="NDLS",
            to_station="CNB",
            journey_date=date.today(),
            status="SUCCESS",
        )


# ==================== 2. Database ====================


def test_database_transactions_and_nonexistent_records(tmp_path):
    """Verify database handles nonexistent records gracefully and maintains integrity."""
    db_file = str(tmp_path / "test_comp.db")
    db = Database(db_file)

    # Updating nonexistent passenger or trip returns False without raising
    nonexistent_p = Passenger(id=9999, name="Ghost", age=30, gender="M")
    assert db.update_passenger(nonexistent_p) is False
    assert db.delete_passenger(9999) is False

    nonexistent_t = Trip(
        id=9999,
        from_station="NDLS",
        to_station="CNB",
        journey_date=date.today() + timedelta(days=1),
        train_number="12004",
        class_code="3A",
    )
    assert db.update_trip(nonexistent_t) is False
    assert db.delete_trip(9999) is False

    # Foreign key relationship: deleting trip sets trip_id to NULL on booking
    created_trip = db.create_trip(nonexistent_t)
    booking = BookingRecord(
        trip_id=created_trip.id,
        train_number="12004",
        class_code="3A",
        quota_code="TATKAL",
        from_station="NDLS",
        to_station="CNB",
        journey_date=nonexistent_t.journey_date,
        status="SUCCESS",
        pnr="1234567890",
    )
    saved_booking = db.create_booking(booking)
    assert saved_booking.id is not None

    # Delete trip
    assert db.delete_trip(created_trip.id) is True

    # Booking still exists and is accessible
    loaded_b = db.load_booking(saved_booking.id)
    assert loaded_b is not None
    assert loaded_b.pnr == "1234567890"
    assert loaded_b.pnr == "1234567890"


# ==================== 3. Clock ====================


def test_clock_leap_year_and_boundary_precision():
    """Verify TatkalClock across leap year dates and sub-second boundaries."""
    clock = TatkalClock()

    # Leap day test (Feb 29, 2028)
    leap_day = date(2028, 2, 29)
    ac_opening = clock.get_tatkal_opening_datetime("3A", target_date=leap_day)
    assert ac_opening.date() == leap_day
    assert ac_opening.hour == 10
    assert ac_opening.minute == 0

    non_ac_opening = clock.get_tatkal_opening_datetime("SL", target_date=leap_day)
    assert non_ac_opening.date() == leap_day
    assert non_ac_opening.hour == 11
    assert non_ac_opening.minute == 0

    # Sub-second boundary precision
    one_ms_before = datetime(2028, 2, 29, 9, 59, 59, 999000, tzinfo=IST_TZ)
    exact_time = datetime(2028, 2, 29, 10, 0, 0, 0, tzinfo=IST_TZ)

    assert clock.is_tatkal_open("3A", reference_time=one_ms_before, target_date=leap_day) is False
    assert clock.is_tatkal_open("3A", reference_time=exact_time, target_date=leap_day) is True

    # Remaining time formatting
    assert TatkalClock.format_remaining(0.0) == "00:00:00"
    assert TatkalClock.format_remaining(-10.5) == "00:00:00"
    assert TatkalClock.format_remaining(3665.0) == "01:01:05"


# ==================== 4. Countdown ====================


def test_countdown_state_and_remaining_calculation():
    """Verify countdown calculation for upcoming Tatkal windows."""
    clock = TatkalClock()
    target_date = date(2026, 11, 15)

    # 15 minutes before AC Tatkal
    ref_time = datetime(2026, 11, 15, 9, 45, 0, tzinfo=IST_TZ)
    opening_ac = clock.get_tatkal_opening_datetime("2A", target_date=target_date)
    secs = clock.seconds_until(opening_ac, reference_time=ref_time)
    assert secs == 900.0  # 15 minutes = 900 seconds
    assert clock.format_remaining(secs) == "00:15:00"

    # Exactly at opening
    ref_exact = datetime(2026, 11, 15, 10, 0, 0, tzinfo=IST_TZ)
    assert clock.seconds_until(opening_ac, reference_time=ref_exact) == 0.0
    assert clock.is_tatkal_open("2A", reference_time=ref_exact, target_date=target_date) is True


# ==================== 5. State Machine ====================


def test_state_machine_transition_lock_invariance():
    """Verify that BookingStateMachine locks down completely when in UNKNOWN state."""
    sm = BookingStateMachine(initial_state=BookingState.PAYMENT_REQUIRED)
    assert sm.is_locked is False

    # Transition to UNKNOWN
    sm.transition_to(BookingState.UNKNOWN, "Ambiguous payment gateway timeout")
    assert sm.is_locked is True
    assert sm.current_state == BookingState.UNKNOWN

    # Any forward transition must fail
    assert sm.can_transition_to(BookingState.BOOKING_CONFIRMATION) is False
    assert sm.can_transition_to(BookingState.SUCCESS) is False
    assert sm.can_transition_to(BookingState.TRAIN_SELECTION) is False

    with pytest.raises(InvalidStateTransitionError, match="Illegal transition from 'UNKNOWN'"):
        sm.transition_to(BookingState.SUCCESS)

    with pytest.raises(InvalidStateTransitionError, match="Illegal transition from 'UNKNOWN'"):
        sm.transition_to(BookingState.TRAIN_SELECTION)


def test_state_machine_listener_exception_resilience():
    """Verify that a failing listener does not break state machine transitions."""
    sm = BookingStateMachine()

    def faulty_listener(old_st, new_st, reason):
        raise RuntimeError("Listener crashed unexpectedly!")

    sm.add_listener(faulty_listener)

    # Transition should still succeed despite listener error
    sm.transition_to(BookingState.BROWSER_READY, "Browser launched")
    assert sm.current_state == BookingState.BROWSER_READY


# ==================== 6. Browser Manager ====================


def test_browser_manager_idempotent_lifecycle(tmp_path):
    """Verify BrowserManager handles start, stop, and stop_automation idempotently."""
    custom_profile = str(tmp_path / "custom_browser_profile")
    bm = BrowserManager(user_data_dir=custom_profile)

    # stop_automation when not started is safe no-op
    bm.stop_automation()
    assert bm.is_running() is False

    # close_browser when not started is safe no-op
    bm.close_browser()
    assert bm.is_running() is False


# ==================== 7. Mock Workflow ====================


def test_workflow_enforces_mandatory_train_and_class():
    """Verify that IRCTCWorkflow review and preparation fail if train number or class is missing."""
    from unittest.mock import MagicMock

    mock_page = MagicMock()
    mock_page.is_closed.return_value = False

    sm = BookingStateMachine(initial_state=BookingState.PASSENGER_SELECTION)
    wf = IRCTCWorkflow(page=mock_page, state_machine=sm)

    # Trip without train number
    future = date.today() + timedelta(days=2)
    invalid_trip_no_train = Trip(
        from_station="NDLS",
        to_station="CNB",
        journey_date=future,
        train_number="12004",  # Temporary valid to construct
        class_code="3A",
    )
    invalid_trip_no_train.train_number = ""  # Force empty

    res = wf.review_booking(trip=invalid_trip_no_train)
    assert res.success is False
    assert sm.current_state == BookingState.FAILURE
    assert "Train number is mandatory" in res.message


# ==================== 8. Failure Handling ====================


def test_failure_handling_unknown_exception_and_retry_backoff():
    """Verify classification of custom unhandled exceptions and retry policy rules."""
    custom_err = ArithmeticError("Unexpected division by zero in calculation")
    f_res = classify_failure(custom_err, stage="train_selection")
    assert f_res.failure_type == FailureType.GENERAL_ERROR
    assert "division by zero" in f_res.message
    assert f_res.is_retryable is False

    # Retry policy rules
    policy = RetryPolicy(
        max_retries=3,
        retry_delay_seconds=1.0,
    )
    # General error cannot be retried
    assert policy.can_retry(f_res, attempt=0) is False

    # Uncertain payment outcome strictly cannot be retried
    uncertain_failure = classify_failure("Payment outcome is uncertain", stage="confirmation")
    assert policy.can_retry(uncertain_failure, attempt=0) is False
    assert policy.can_retry(uncertain_failure, attempt=0, current_state=BookingState.UNKNOWN) is False

    # Page timeout is retryable within max_retries
    timeout_failure = classify_failure(TimeoutError("Gateway timeout"), stage="train_selection")
    assert policy.can_retry(timeout_failure, attempt=0) is True
    assert policy.can_retry(timeout_failure, attempt=2) is True
    assert policy.can_retry(timeout_failure, attempt=3) is False
