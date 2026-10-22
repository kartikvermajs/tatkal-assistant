"""Tests for Phase 18: Booking Result Verification & Post-Payment Outcome Handling.

Verifies:
1. When confirmed:
   - STATE = SUCCESS
   - Displays "BOOKING SUCCESSFUL"
   - Displays available confirmation information (PNR, Train, Class, Fare, Berths).
2. Privacy guard:
   - Does not store unnecessary personal or payment information (zero PINs, CVVs, credentials).
3. When ambiguous:
   - STATE = UNKNOWN
   - Displays: "Booking status is uncertain. Verify IRCTC booking history before attempting another booking."
4. Strict Deadlock Safety:
   - Never automatically retries a booking after an uncertain payment state.
   - UI blocks automated re-booking until manual user reset.
"""

from datetime import date
import os
import pytest
from playwright.sync_api import sync_playwright

from browser.irctc_workflow import IRCTCWorkflow
from core.booking_state import BookingState, BookingStateMachine, InvalidStateTransitionError
from database.db import Database
from models.booking import BookingRecord
from models.trip import Trip
from ui.booking_confirmation_dialog import BookingConfirmationDialog
from ui.main_window import MainWindow


@pytest.fixture(scope="module")
def browser_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        yield page
        context.close()
        browser.close()


@pytest.fixture
def workflow(browser_page):
    sm = BookingStateMachine()
    return IRCTCWorkflow(page=browser_page, state_machine=sm)


@pytest.fixture
def sample_trip():
    return Trip(
        from_station="NDLS",
        to_station="LKO",
        journey_date=date(2026, 10, 28),
        train_number="12424",
        class_code="3A",
        quota="TATKAL",
    )


# ==================== 1. Confirmed Booking Outcome (STATE = SUCCESS) ====================


def test_booking_result_confirmed_success(workflow, browser_page, sample_trip):
    """When confirmed, sets STATE = SUCCESS and displays BOOKING SUCCESSFUL with PNR."""
    html = """
    <html>
      <body>
        <div>
          <h2>Booking Confirmation</h2>
          <span data-testid="pnr-number">1234567890</span>
          <span data-testid="txn-id">TXN_IRCTC_100</span>
          <span data-testid="total-fare">₹ 1450.00</span>
          <table data-testid="allocated-passengers">
            <tbody><tr><td>Arun Kumar (28/M) - CNF B2 34 LB</td></tr></tbody>
          </table>
        </div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html;charset=utf-8,{html}")

    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)
    workflow.sm.transition_to(BookingState.REVIEW)
    workflow.sm.transition_to(BookingState.PAYMENT_REQUIRED)
    workflow.sm.transition_to(BookingState.BOOKING_CONFIRMATION)

    res = workflow.verify_booking_result(trip=sample_trip)
    assert res.success is True
    assert res.state == BookingState.SUCCESS
    assert workflow.sm.current_state == BookingState.SUCCESS
    assert "BOOKING SUCCESSFUL" in res.message
    assert res.details["pnr"] == "1234567890"
    assert res.details["transaction_id"] == "TXN_IRCTC_100"
    assert res.details["fare"] == 1450.00


# ==================== 2. Ambiguous Outcome (STATE = UNKNOWN) ====================


def test_booking_result_ambiguous_unknown_exact_message(workflow, browser_page, sample_trip):
    """When ambiguous, sets STATE = UNKNOWN and returns exact required advisory."""
    html = """
    <html>
      <body>
        <h3>504 Gateway Timeout</h3>
        <p>Payment transaction pending postback from bank.</p>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")

    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)
    workflow.sm.transition_to(BookingState.REVIEW)
    workflow.sm.transition_to(BookingState.PAYMENT_REQUIRED)
    workflow.sm.transition_to(BookingState.BOOKING_CONFIRMATION)

    res = workflow.verify_booking_result(trip=sample_trip)
    assert res.success is False
    assert res.state == BookingState.UNKNOWN
    assert workflow.sm.current_state == BookingState.UNKNOWN

    # Exact required display text
    expected_msg = "Booking status is uncertain. Verify IRCTC booking history before attempting another booking."
    assert expected_msg == res.message


# ==================== 3. Deadlock Safety: Never Retry After Uncertain Payment ====================


def test_never_retry_booking_after_uncertain_payment_state():
    """Verify state machine strictly forbids automatic retries from UNKNOWN."""
    sm = BookingStateMachine()
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    sm.transition_to(BookingState.JOURNEY_SELECTION)
    sm.transition_to(BookingState.TRAIN_SELECTION)
    sm.transition_to(BookingState.PASSENGER_SELECTION)
    sm.transition_to(BookingState.REVIEW)
    sm.transition_to(BookingState.PAYMENT_REQUIRED)
    sm.transition_to(BookingState.BOOKING_CONFIRMATION)
    sm.transition_to(BookingState.UNKNOWN)

    # Prohibit retrying booking workflow
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.JOURNEY_SELECTION)

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.TRAIN_SELECTION)

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.PAYMENT_REQUIRED)

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.WAITING_FOR_TATKAL)

    # Only explicit manual reset to IDLE is permitted
    sm.reset(reason="Manual user reset after verifying bank and IRCTC history")
    assert sm.current_state == BookingState.IDLE


# ==================== 4. Privacy: No Unnecessary Personal / Payment Data ====================


def test_privacy_no_unnecessary_personal_payment_data(sample_trip):
    """Verify that BookingRecord does not store credentials, PINs, CVVs, or unnecessary personal info."""
    rec = BookingRecord(
        train_number=sample_trip.train_number,
        class_code=sample_trip.class_code,
        quota_code=sample_trip.quota,
        from_station=sample_trip.from_station,
        to_station=sample_trip.to_station,
        journey_date=sample_trip.journey_date,
        status="SUCCESS",
        pnr="1234567890",
        total_fare=1250.0,
    )
    rec_dict = rec.to_dict()

    forbidden_fields = [
        "pin", "wallet_pin", "ewallet_pin", "cvv", "cvc",
        "card_number", "password", "otp", "aadhaar_number",
        "banking_password", "account_number",
    ]
    for field in forbidden_fields:
        assert field not in rec_dict, f"Privacy violation: sensitive field '{field}' found in BookingRecord."


# ==================== 5. UI Dialog Displays ====================


def test_confirmation_dialog_displays_booking_successful(qapp, sample_trip):
    """Verify BookingConfirmationDialog renders BOOKING SUCCESSFUL for confirmed bookings."""
    rec = BookingRecord(
        train_number=sample_trip.train_number,
        class_code=sample_trip.class_code,
        quota_code=sample_trip.quota,
        from_station=sample_trip.from_station,
        to_station=sample_trip.to_station,
        journey_date=sample_trip.journey_date,
        status="SUCCESS",
        pnr="1234567890",
        total_fare=1250.0,
    )
    dialog = BookingConfirmationDialog(rec)
    all_texts = " ".join([child.text() for child in dialog.findChildren(object) if hasattr(child, "text")])
    assert "BOOKING SUCCESSFUL" in all_texts
    assert "1234567890" in all_texts
    dialog.close()


def test_confirmation_dialog_displays_uncertain_advisory(qapp, sample_trip):
    """Verify BookingConfirmationDialog renders exact uncertain advisory text for UNKNOWN bookings."""
    rec = BookingRecord(
        train_number=sample_trip.train_number,
        class_code=sample_trip.class_code,
        quota_code=sample_trip.quota,
        from_station=sample_trip.from_station,
        to_station=sample_trip.to_station,
        journey_date=sample_trip.journey_date,
        status="UNKNOWN",
        status_message="Booking status is uncertain. Verify IRCTC booking history before attempting another booking.",
    )
    dialog = BookingConfirmationDialog(rec)
    all_texts = " ".join([child.text() for child in dialog.findChildren(object) if hasattr(child, "text")])
    assert "Booking status is uncertain. Verify IRCTC booking history before attempting another booking." in all_texts
    assert "DO NOT SUBMIT ANOTHER PAYMENT OR RETRY" in all_texts
    dialog.close()


# ==================== 6. Main Window Outcome Display Integration ====================


def test_main_window_displays_booking_successful(qapp, browser_page, sample_trip):
    """Verify MainWindow displays BOOKING SUCCESSFUL on confirmation."""
    db = Database(":memory:")
    db.create_trip(sample_trip)
    db.set_active_trip(1)

    window = MainWindow(db=db)
    window.load_active_trip()

    html = "<html><body><div data-testid='pnr-number'>1234567890</div></body></html>"
    browser_page.goto(f"data:text/html;charset=utf-8,{html}")

    sm = BookingStateMachine()
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    sm.transition_to(BookingState.JOURNEY_SELECTION)
    sm.transition_to(BookingState.TRAIN_SELECTION)
    sm.transition_to(BookingState.PASSENGER_SELECTION)
    sm.transition_to(BookingState.REVIEW)
    sm.transition_to(BookingState.PAYMENT_REQUIRED)

    wf = IRCTCWorkflow(page=browser_page, state_machine=sm)
    window.current_workflow = wf
    window.checkpoint_btn.setEnabled(True)
    window.checkpoint_btn.click()

    assert "BOOKING SUCCESSFUL" in window.status_label.text()
    assert sm.current_state == BookingState.SUCCESS
    window.close()


def test_main_window_displays_uncertain_status_and_blocks_retry(qapp, browser_page, sample_trip):
    """Verify MainWindow displays exact uncertain message and disables retry."""
    db = Database(":memory:")
    window = MainWindow(db=db)

    html = "<html><body><h3>504 Gateway Timeout</h3></body></html>"
    browser_page.goto(f"data:text/html,{html}")

    sm = BookingStateMachine()
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    sm.transition_to(BookingState.JOURNEY_SELECTION)
    sm.transition_to(BookingState.TRAIN_SELECTION)
    sm.transition_to(BookingState.PASSENGER_SELECTION)
    sm.transition_to(BookingState.REVIEW)
    sm.transition_to(BookingState.PAYMENT_REQUIRED)

    wf = IRCTCWorkflow(page=browser_page, state_machine=sm)
    window.current_workflow = wf
    window.checkpoint_btn.setEnabled(True)
    window.checkpoint_btn.click()

    assert sm.current_state == BookingState.UNKNOWN
    assert "Booking status is uncertain. Verify IRCTC booking history before attempting another booking." in window.status_label.text()
    # Retry is blocked
    assert window.prepare_booking_btn.isEnabled() is False
    window.close()
