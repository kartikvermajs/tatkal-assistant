"""Unit tests for Phase 10 Booking State Machine."""

import pytest

from core.booking_state import (
    BookingState,
    BookingStateMachine,
    InvalidStateTransitionError,
)


@pytest.fixture
def sm():
    return BookingStateMachine()


# ==================== Initialization and Happy Path ====================


def test_initial_state(sm):
    assert sm.current_state == BookingState.IDLE
    assert len(sm.history) == 1
    assert sm.history[0][0] == BookingState.IDLE


def test_standard_happy_path(sm):
    # IDLE -> BROWSER_READY
    sm.transition_to(BookingState.BROWSER_READY, "Browser started")
    assert sm.current_state == BookingState.BROWSER_READY

    # BROWSER_READY -> USER_LOGIN_REQUIRED
    sm.transition_to(BookingState.USER_LOGIN_REQUIRED, "User needs to login")
    assert sm.current_state == BookingState.USER_LOGIN_REQUIRED

    # USER_LOGIN_REQUIRED -> USER_LOGGED_IN
    sm.transition_to(BookingState.USER_LOGGED_IN, "User authenticated")
    assert sm.current_state == BookingState.USER_LOGGED_IN

    # USER_LOGGED_IN -> WAITING_FOR_TATKAL
    sm.transition_to(BookingState.WAITING_FOR_TATKAL, "Waiting for 11:00")
    assert sm.current_state == BookingState.WAITING_FOR_TATKAL

    # WAITING_FOR_TATKAL -> JOURNEY_SELECTION
    sm.transition_to(BookingState.JOURNEY_SELECTION, "Tatkal opened")
    assert sm.current_state == BookingState.JOURNEY_SELECTION

    # JOURNEY_SELECTION -> TRAIN_SELECTION
    sm.transition_to(BookingState.TRAIN_SELECTION, "Origin and destination selected")
    assert sm.current_state == BookingState.TRAIN_SELECTION

    # TRAIN_SELECTION -> PASSENGER_SELECTION
    sm.transition_to(BookingState.PASSENGER_SELECTION, "Train and class selected")
    assert sm.current_state == BookingState.PASSENGER_SELECTION

    # PASSENGER_SELECTION -> REVIEW
    sm.transition_to(BookingState.REVIEW, "Passengers selected")
    assert sm.current_state == BookingState.REVIEW

    # REVIEW -> CAPTCHA_REQUIRED
    sm.transition_to(BookingState.CAPTCHA_REQUIRED, "Human CAPTCHA checkpoint")
    assert sm.current_state == BookingState.CAPTCHA_REQUIRED

    # CAPTCHA_REQUIRED -> PAYMENT_REQUIRED
    sm.transition_to(BookingState.PAYMENT_REQUIRED, "User solved CAPTCHA")
    assert sm.current_state == BookingState.PAYMENT_REQUIRED

    # PAYMENT_REQUIRED -> BOOKING_CONFIRMATION
    sm.transition_to(BookingState.BOOKING_CONFIRMATION, "User authorized payment")
    assert sm.current_state == BookingState.BOOKING_CONFIRMATION

    # BOOKING_CONFIRMATION -> SUCCESS
    sm.transition_to(BookingState.SUCCESS, "PNR generated")
    assert sm.current_state == BookingState.SUCCESS

    # SUCCESS -> IDLE (Reset)
    sm.reset()
    assert sm.current_state == BookingState.IDLE


# ==================== Alternative Valid Transitions ====================


def test_existing_session_path(sm):
    # Already logged in from previous profile
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN, "Active session detected")
    assert sm.current_state == BookingState.USER_LOGGED_IN


def test_immediate_tatkal_open_path(sm):
    # Logged in when Tatkal is already open skips WAITING_FOR_TATKAL
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    sm.transition_to(BookingState.JOURNEY_SELECTION, "Tatkal already open")
    assert sm.current_state == BookingState.JOURNEY_SELECTION


def test_step_back_navigation(sm):
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    sm.transition_to(BookingState.JOURNEY_SELECTION)
    sm.transition_to(BookingState.TRAIN_SELECTION)

    # Step back from TRAIN_SELECTION to JOURNEY_SELECTION
    sm.transition_to(BookingState.JOURNEY_SELECTION, "Back to journey")
    assert sm.current_state == BookingState.JOURNEY_SELECTION


def test_otp_checkpoints(sm):
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGIN_REQUIRED)
    # Login OTP checkpoint
    sm.transition_to(BookingState.OTP_REQUIRED, "Aadhaar / Login OTP")
    sm.transition_to(BookingState.USER_LOGGED_IN, "OTP validated by human")
    assert sm.current_state == BookingState.USER_LOGGED_IN


# ==================== Failure Handling ====================


def test_failure_transition(sm):
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    sm.transition_to(BookingState.JOURNEY_SELECTION)

    # Fail during journey selection
    sm.fail("Train station not found on IRCTC")
    assert sm.current_state == BookingState.FAILURE
    assert sm.error_message == "Train station not found on IRCTC"

    # Reset from failure
    sm.reset()
    assert sm.current_state == BookingState.IDLE
    assert sm.error_message is None


# ==================== Ambiguous / UNKNOWN Payment State ====================


def test_unknown_payment_state_cannot_retry_automatically(sm):
    """Verify that an ambiguous payment state cannot transition back to booking automation."""
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    sm.transition_to(BookingState.JOURNEY_SELECTION)
    sm.transition_to(BookingState.TRAIN_SELECTION)
    sm.transition_to(BookingState.PASSENGER_SELECTION)
    sm.transition_to(BookingState.REVIEW)
    sm.transition_to(BookingState.PAYMENT_REQUIRED)

    # Ambiguous outcome during payment
    sm.set_unknown("Payment gateway timed out without confirmation")
    assert sm.current_state == BookingState.UNKNOWN
    assert sm.error_message == "Payment gateway timed out without confirmation"

    # MUST NOT be able to jump to automation or retry booking
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.JOURNEY_SELECTION)

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.PAYMENT_REQUIRED)

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.BOOKING_CONFIRMATION)

    # Only manual reset allowed after verifying IRCTC history
    sm.reset("User verified IRCTC history")
    assert sm.current_state == BookingState.IDLE


# ==================== Strictly Invalid Transitions ====================


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        (BookingState.IDLE, BookingState.SUCCESS),
        (BookingState.IDLE, BookingState.PAYMENT_REQUIRED),
        (BookingState.IDLE, BookingState.BOOKING_CONFIRMATION),
        (BookingState.BROWSER_READY, BookingState.BOOKING_CONFIRMATION),
        (BookingState.JOURNEY_SELECTION, BookingState.SUCCESS),
        (BookingState.CAPTCHA_REQUIRED, BookingState.SUCCESS),
        (BookingState.SUCCESS, BookingState.PAYMENT_REQUIRED),
    ],
)
def test_illegal_transitions_raise_error(from_state, to_state):
    # Set up state machine in from_state
    sm = BookingStateMachine(initial_state=from_state)
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(to_state)


# ==================== Listener Callbacks & History ====================


def test_listener_callback(sm):
    transitions = []

    def on_change(old_state, new_state, reason):
        transitions.append((old_state, new_state, reason))

    sm.add_listener(on_change)
    sm.transition_to(BookingState.BROWSER_READY, "Start")
    sm.transition_to(BookingState.USER_LOGGED_IN, "Logged in")

    assert len(transitions) == 2
    assert transitions[0] == (BookingState.IDLE, BookingState.BROWSER_READY, "Start")
    assert transitions[1] == (BookingState.BROWSER_READY, BookingState.USER_LOGGED_IN, "Logged in")

    # Unregister listener
    sm.remove_listener(on_change)
    sm.transition_to(BookingState.JOURNEY_SELECTION)
    assert len(transitions) == 2  # No new callback
