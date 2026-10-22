"""Tests for Phase 15: Payment & Confirmation Stage / Post-Booking Reconciliation.

Verifies:
1. PNR extraction, transaction ID, fare, and passenger allocation extraction.
2. Explicit failure detection.
3. Ambiguous / gateway timeout handling transitioning to UNKNOWN.
4. Deadlock safety: no automatic retry permitted from UNKNOWN state.
5. Confirmation and History dialogs in desktop UI.
6. Centralized IRCTC URLs and security compliance.
"""

from datetime import date
import os
import pytest
from playwright.sync_api import sync_playwright

import config
from browser.irctc_workflow import IRCTCWorkflow
from core.booking_state import BookingState, BookingStateMachine, InvalidStateTransitionError
from database.db import Database
from models.booking import BookingRecord
from models.passenger import Passenger
from models.trip import Trip
from ui.booking_confirmation_dialog import BookingConfirmationDialog
from ui.booking_history_dialog import BookingHistoryDialog
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
        journey_date=date(2026, 10, 25),
        train_number="12424",
        class_code="3A",
        quota="TATKAL",
    )


# ==================== 1. Page DOM Confirmation Verification ====================


def test_verify_booking_result_confirmed_dom(workflow, browser_page, sample_trip):
    """Detects 10-digit PNR, Txn ID, Total Fare, and passenger table from confirmed page."""
    html = """
    <html>
      <body>
        <div class="ticket-container">
          <h2>Booking Confirmation</h2>
          <div data-testid="pnr-number">2345678901</div>
          <div data-testid="txn-id">TXN998877</div>
          <div data-testid="total-fare">₹ 1850.00</div>
          <table data-testid="allocated-passengers">
            <tbody>
              <tr><td>Rohan Sharma (32/M)</td><td>CNF B3 21 LB</td></tr>
            </tbody>
          </table>
        </div>
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
    assert res.success is True
    assert res.state == BookingState.SUCCESS
    assert workflow.sm.current_state == BookingState.SUCCESS
    assert res.details["pnr"] == "2345678901"
    assert res.details["transaction_id"] == "TXN998877"
    assert res.details["fare"] == 1850.00
    assert len(res.details["passengers"]) == 1


def test_verify_booking_result_regex_pnr_text(workflow, browser_page, sample_trip):
    """Detects 10-digit PNR from plain page text without dedicated testids."""
    html = """
    <html>
      <body>
        <div>
          <p>Congratulations! Your ticket has been booked.</p>
          <p>PNR No: 9876543210</p>
          <p>Txn ID: IRCTC_123456</p>
          <p>Total Fare: ₹ 890.50</p>
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
    assert res.details["pnr"] == "9876543210"
    assert res.details["transaction_id"] == "IRCTC_123456"
    assert res.details["fare"] == 890.50


# ==================== 2. Explicit Failure Detection ====================


def test_verify_booking_result_explicit_failure(workflow, browser_page, sample_trip):
    """Detects explicit payment failure and transitions to FAILURE."""
    html = """
    <html>
      <body>
        <div class="alert alert-danger" data-testid="booking-failure">
          Payment Failed: Insufficient funds in bank account.
        </div>
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
    assert res.state == BookingState.FAILURE
    assert workflow.sm.current_state == BookingState.FAILURE
    assert "Insufficient funds" in res.message


def test_verify_booking_result_regret_quota_exhausted(workflow, browser_page, sample_trip):
    """Detects quota exhaustion / regret failure message."""
    html = """
    <html>
      <body>
        <h2>REGRET / Quota Exhausted</h2>
        <p>No seats available in Tatkal quota.</p>
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
    assert res.state == BookingState.FAILURE


# ==================== 3. Ambiguous Payment & Deadlock Safety ====================


def test_verify_booking_result_ambiguous_page(workflow, browser_page, sample_trip):
    """When payment outcome is ambiguous, transitions strictly to UNKNOWN."""
    html = """
    <html>
      <body>
        <h3>504 Gateway Timeout</h3>
        <p>Transaction status pending bank verification.</p>
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
    assert "uncertain" in res.message.lower()


def test_deadlock_prevention_from_unknown_state():
    """Verify that no automated re-booking transition is allowed from UNKNOWN state."""
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

    # Attempts to re-enter workflow must fail
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.WAITING_FOR_TATKAL)

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.JOURNEY_SELECTION)

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.PAYMENT_REQUIRED)

    # Only manual reset to IDLE is permitted
    sm.reset()
    assert sm.current_state == BookingState.IDLE


# ==================== 4. Workflow Persistence ====================


def test_save_booking_result_in_database(workflow, sample_trip):
    """save_booking_result creates a persistent record in local SQLite."""
    db = Database(":memory:")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)
    workflow.sm.transition_to(BookingState.REVIEW)
    workflow.sm.transition_to(BookingState.PAYMENT_REQUIRED)
    workflow.sm.transition_to(BookingState.BOOKING_CONFIRMATION)

    step_res = workflow.verify_booking_result(is_confirmed=True, pnr="5544332211")
    step_res.details["transaction_id"] = "TXN_OK"
    step_res.details["fare"] = 2100.0

    record = workflow.save_booking_result(db, sample_trip, step_res)
    assert record.id is not None
    assert record.pnr == "5544332211"
    assert record.total_fare == 2100.0
    assert record.status == "SUCCESS"

    db_rec = db.load_booking(record.id)
    assert db_rec.train_number == sample_trip.train_number


# ==================== 5. UI Dialogs Verification ====================


def test_booking_confirmation_dialog_success(qapp, sample_trip):
    rec = BookingRecord(
        train_number=sample_trip.train_number,
        class_code=sample_trip.class_code,
        quota_code=sample_trip.quota,
        from_station=sample_trip.from_station,
        to_station=sample_trip.to_station,
        journey_date=sample_trip.journey_date,
        status="SUCCESS",
        pnr="1234567890",
        total_fare=1500.0,
    )
    dialog = BookingConfirmationDialog(rec)
    res = dialog.exec()
    assert res == BookingConfirmationDialog.DialogCode.Accepted
    dialog.close()


def test_booking_confirmation_dialog_unknown_advisory(qapp, sample_trip):
    rec = BookingRecord(
        train_number=sample_trip.train_number,
        class_code=sample_trip.class_code,
        quota_code=sample_trip.quota,
        from_station=sample_trip.from_station,
        to_station=sample_trip.to_station,
        journey_date=sample_trip.journey_date,
        status="UNKNOWN",
        status_message="Timeout waiting for bank response",
    )
    dialog = BookingConfirmationDialog(rec)
    res = dialog.exec()
    assert res == BookingConfirmationDialog.DialogCode.Accepted
    dialog.close()


def test_booking_history_dialog(qapp, sample_trip):
    db = Database(":memory:")
    rec = BookingRecord(
        train_number=sample_trip.train_number,
        class_code=sample_trip.class_code,
        quota_code=sample_trip.quota,
        from_station=sample_trip.from_station,
        to_station=sample_trip.to_station,
        journey_date=sample_trip.journey_date,
        status="SUCCESS",
        pnr="9988776655",
    )
    db.create_booking(rec)

    dialog = BookingHistoryDialog(db)
    assert dialog.table.rowCount() == 1
    dialog.table.selectRow(0)
    dialog._on_view_details_clicked()
    dialog._on_delete_clicked()
    assert dialog.table.rowCount() == 0
    dialog.close()


# ==================== 6. Main Window Integration ====================


def test_main_window_booking_history_button(qapp):
    """Main window has a functional Booking History button."""
    window = MainWindow()
    assert hasattr(window, "booking_history_btn")
    window.booking_history_btn.click()
    window.close()


def test_main_window_checkpoint_confirmation_flow(qapp, browser_page, sample_trip):
    """Verify MainWindow handles checkpoint at PAYMENT_REQUIRED, inspects result, and manages deadlock."""
    db = Database(":memory:")
    db.create_trip(sample_trip)
    db.set_active_trip(1)

    window = MainWindow(db=db)
    window.load_active_trip()

    # Confirmed page
    html = """
    <html><body><div data-testid="pnr-number">1234567890</div></body></html>
    """
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

    assert "BOOKING CONFIRMED" in window.status_label.text()
    assert sm.current_state == BookingState.SUCCESS

    # Verify saved in database
    latest = db.get_latest_booking()
    assert latest is not None
    assert latest.pnr == "1234567890"

    window.close()


def test_main_window_unknown_deadlock_disables_prepare(qapp, browser_page, sample_trip):
    """Verify that an UNKNOWN outcome disables prepare_booking_btn to prevent duplicate booking."""
    db = Database(":memory:")
    window = MainWindow(db=db)

    # Ambiguous page with timeout
    html = "<html><body>504 Gateway Timeout</body></html>"
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

    assert "STATUS UNCERTAIN" in window.status_label.text()
    assert sm.current_state == BookingState.UNKNOWN
    # Deadlock safety: prepare_booking_btn is disabled
    assert window.prepare_booking_btn.isEnabled() is False

    # Clicking cancel resets and re-enables prepare_booking_btn
    window.cancel_btn.click()
    assert window.prepare_booking_btn.isEnabled() is True
    assert sm.current_state == BookingState.IDLE

    window.close()


# ==================== 7. Centralized URL Scan ====================


def test_security_audit_centralized_irctc_urls():
    """Verify zero hardcoded IRCTC URLs exist outside config.py."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for root, _, files in os.walk(project_root):
        if ".venv" in root or "__pycache__" in root or "tests" in root:
            continue
        for file in files:
            if file.endswith(".py") and file != "config.py":
                path = os.path.join(root, file)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    assert "irctc.co.in" not in content, (
                        f"Centralization violation: hardcoded IRCTC URL found in {path}. "
                        "All IRCTC URLs must be centralized in config.py."
                    )
