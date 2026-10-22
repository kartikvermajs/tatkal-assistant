"""Automated tests for Phase 21: Mock IRCTC Environment.

Tests the complete BookingStateMachine and IRCTCWorkflow across all lifecycle stages:
- LOGIN -> JOURNEY -> TRAIN -> PASSENGER -> CAPTCHA -> PAYMENT -> SUCCESS
- CAPTCHA interruption (human checkpoint)
- OTP interruption (human checkpoint)
- Payment failure (bank decline)
- Unknown payment result (ambiguous outcome & deadlock lockout)
- Network failure (disconnect/unreachable)
- Train unavailable (not found & quota regret)
"""

from datetime import date, timedelta
import os
import pytest
from playwright.sync_api import sync_playwright

from browser.irctc_workflow import IRCTCWorkflow
from browser.mock_irctc import MockIRCTCServer
import config
from core.booking_state import BookingState, BookingStateMachine
from database.db import Database
from models.passenger import Passenger
from models.trip import Trip


@pytest.fixture(scope="module")
def mock_server():
    """Start local mock IRCTC server for the test module."""
    server = MockIRCTCServer()
    server.start()
    yield server
    server.stop()
    config.reset_irctc_urls()


@pytest.fixture(scope="module")
def browser_instance():
    """Launch headless Chromium browser once for the test module."""
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    yield browser
    browser.close()
    p.stop()


@pytest.fixture
def browser_page(browser_instance):
    """Create a clean headless Chromium page for each test to prevent navigation bleed."""
    page = browser_instance.new_page()
    yield page
    try:
        if not page.is_closed():
            page.close()
    except Exception:
        pass


@pytest.fixture
def workflow(browser_page):
    """Create a fresh IRCTCWorkflow with a clean state machine for each test."""
    sm = BookingStateMachine()
    return IRCTCWorkflow(page=browser_page, state_machine=sm)


@pytest.fixture
def db():
    """Provide a fresh SQLite database instance for booking records."""
    database = Database(":memory:")
    yield database
    database.close()


# ==================== Test 1: Mock Server Lifecycle ====================


def test_mock_server_lifecycle():
    """Verify mock server can be started and stopped cleanly on an OS-assigned port."""
    with MockIRCTCServer() as s:
        assert s.port > 0
        assert s.base_url.startswith("http://127.0.0.1:")
        assert "/nget/train-search" in s.booking_url
        assert "/nget/profile/user-login" in s.login_url


# ==================== Test 2: Successful Booking Flow ====================


def test_mock_successful_booking(mock_server, browser_page, workflow, db):
    """Complete end-to-end booking flow:
    LOGIN -> JOURNEY -> TRAIN -> PASSENGER -> CAPTCHA -> PAYMENT -> SUCCESS
    """
    mock_server.logged_in = True
    mock_server.captcha_required = True
    mock_server.otp_required = False
    mock_server.payment_outcome = "SUCCESS"
    mock_server.regret_mode = False

    config.set_irctc_urls(mock_server.base_url)

    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(
        from_station="NDLS",
        to_station="CNB",
        journey_date=tomorrow,
        train_number="12004",
        train_name="LUCKNOW SHATABDI",
        class_code="3A",
        quota="TATKAL",
    )
    passengers = [
        Passenger(name="Ravi Kumar", age=30, gender="M", berth_preference="LB"),
        Passenger(name="Pooja Verma", age=28, gender="F", berth_preference="MB"),
    ]

    # 1. Open Portal
    res_open = workflow.open_booking_page()
    assert res_open.success is True
    assert workflow.sm.current_state == BookingState.BROWSER_READY

    # 2. Check Login Status (user is logged in)
    res_login = workflow.check_login_status()
    assert res_login.success is True
    assert workflow.sm.current_state == BookingState.USER_LOGGED_IN

    # 3. Journey Selection
    res_journey = workflow.select_journey(trip)
    assert res_journey.success is True
    assert workflow.sm.current_state == BookingState.JOURNEY_SELECTION

    # 4. Quota Selection
    res_quota = workflow.select_quota(trip.quota)
    assert res_quota.success is True

    # 5. Train Selection (mandatory exact train number)
    res_train = workflow.select_train(trip.train_number)
    assert res_train.success is True
    assert workflow.sm.current_state == BookingState.TRAIN_SELECTION

    # 6. Class Selection (mandatory exact class)
    res_class = workflow.select_class(trip.class_code, train_number=trip.train_number)
    assert res_class.success is True

    # Navigate to passenger entry page
    browser_page.goto(mock_server.passenger_url)

    # 7. Passenger Details Entry
    res_pass = workflow.select_passengers(
        passengers,
        mobile_number="9876543210",
        auto_upgradation=True,
        confirm_berths_only=True,
        payment_mode="IRCTC eWallet",
    )
    assert res_pass.success is True
    assert workflow.sm.current_state == BookingState.PASSENGER_SELECTION

    # 8. Proceed to Review / Checkpoint
    res_review = workflow.proceed_to_review()
    assert res_review.success is True
    assert workflow.sm.current_state == BookingState.REVIEW

    # Navigate to CAPTCHA checkpoint
    browser_page.goto(mock_server.captcha_url)

    # 9. CAPTCHA Checkpoint (Human in the loop)
    res_check = workflow.detect_checkpoints()
    assert res_check.success is True
    assert workflow.sm.current_state == BookingState.CAPTCHA_REQUIRED

    # Human completes CAPTCHA in browser -> click Verify / continue
    browser_page.goto(mock_server.payment_url)
    res_cont = workflow.confirm_checkpoint_completed()
    assert res_cont.success is True
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED

    # 10. Payment Authorization (Human in the loop)
    res_pay = workflow.open_payment("IRCTC eWallet")
    assert res_pay.success is True
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED

    # Human authorizes payment in browser -> navigates to success page
    browser_page.goto(mock_server.success_url)
    workflow.sm.transition_to(BookingState.BOOKING_CONFIRMATION)

    # 11. Confirmation Reconciliation
    res_confirm = workflow.verify_booking_result()
    assert res_confirm.success is True
    assert workflow.sm.current_state == BookingState.SUCCESS
    assert res_confirm.details["pnr"] == "2345678901"
    assert res_confirm.details["transaction_id"] == "TXN100987654"
    assert res_confirm.details["fare"] == 1245.00

    # 12. Save to database
    record = workflow.save_booking_result(db, trip, res_confirm)
    assert record.id is not None
    assert record.pnr == "2345678901"
    assert record.status == "SUCCESS"


# ==================== Test 3: CAPTCHA Interruption ====================


def test_mock_captcha_interruption(mock_server, browser_page, workflow):
    """Verify that encountering a CAPTCHA pauses automation and transitions strictly
    to CAPTCHA_REQUIRED, never attempting automated bypass.
    """
    browser_page.goto(mock_server.captcha_url)
    workflow.sm = BookingStateMachine(initial_state=BookingState.REVIEW)

    res = workflow.detect_checkpoints()
    assert res.success is True
    assert res.state == BookingState.CAPTCHA_REQUIRED
    assert workflow.sm.current_state == BookingState.CAPTCHA_REQUIRED
    assert "CAPTCHA" in res.message

    # Simulating human solving CAPTCHA
    browser_page.goto(mock_server.payment_url)
    res_resume = workflow.confirm_checkpoint_completed()
    assert res_resume.success is True
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED


# ==================== Test 4: OTP Interruption ====================


def test_mock_otp_interruption(mock_server, browser_page, workflow):
    """Verify that encountering an OTP input pauses automation and transitions strictly
    to OTP_REQUIRED, never reading or intercepting OTP.
    """
    browser_page.goto(mock_server.otp_url)
    workflow.sm = BookingStateMachine(initial_state=BookingState.REVIEW)

    res = workflow.detect_checkpoints()
    assert res.success is True
    assert res.state == BookingState.OTP_REQUIRED
    assert workflow.sm.current_state == BookingState.OTP_REQUIRED
    assert "OTP" in res.message

    # Simulating human entering OTP
    browser_page.goto(mock_server.payment_url)
    res_resume = workflow.confirm_checkpoint_completed()
    assert res_resume.success is True
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED


# ==================== Test 5: Payment Failure ====================


def test_mock_payment_failure(mock_server, browser_page, workflow):
    """Verify that encountering an explicit payment failure in browser cleanly
    transitions state machine to FAILURE.
    """
    browser_page.goto(mock_server.payment_failure_url)
    workflow.sm = BookingStateMachine(initial_state=BookingState.BOOKING_CONFIRMATION)

    res = workflow.verify_booking_result()
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert workflow.sm.current_state == BookingState.FAILURE
    assert "Payment Failed" in res.message or "Booking rejected" in res.message


# ==================== Test 6: Unknown Payment Result & Deadlock Lockout ====================


def test_mock_unknown_payment_result(mock_server, browser_page, workflow):
    """Verify that an ambiguous payment outcome transitions strictly to UNKNOWN
    and locks the state machine to prevent double bookings.
    """
    browser_page.goto(mock_server.payment_unknown_url)
    workflow.sm = BookingStateMachine(initial_state=BookingState.BOOKING_CONFIRMATION)

    res = workflow.verify_booking_result()
    assert res.success is False
    assert res.state == BookingState.UNKNOWN
    assert workflow.sm.current_state == BookingState.UNKNOWN
    assert workflow.sm.is_locked is True  # Deadlock protection active!

    # Attempting to retry while locked MUST fail
    with pytest.raises(Exception):
        workflow.sm.transition_to(BookingState.BROWSER_READY)


# ==================== Test 7: Network Failure ====================


def test_mock_network_failure(mock_server, browser_page, workflow):
    """Verify that unreachable server or connection failure is safely caught,
    classified, and transitions cleanly to FAILURE.
    """
    # Navigate to a non-existent port
    res = workflow.open_booking_page(url="http://127.0.0.1:59999/down", max_retries=0)
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert workflow.sm.current_state == BookingState.FAILURE
    assert "Network connection error" in res.message or "Failed to connect" in res.message or "closed" in res.message.lower()


# ==================== Test 8: Train Unavailable (Not Found) ====================


def test_mock_train_unavailable_not_found(mock_server, browser_page, workflow):
    """Verify that if the configured train number is not found on the page,
    automation stops immediately and does NOT select another train.
    """
    browser_page.goto(mock_server.booking_url)
    workflow.sm = BookingStateMachine(initial_state=BookingState.JOURNEY_SELECTION)

    # Train 99999 does not exist on the page
    res = workflow.select_train("99999")
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert "99999" in res.message and "not found" in res.message.lower()
    assert "substitution is prohibited" in res.message.lower()


# ==================== Test 9: Train Unavailable (Quota Regret) ====================


def test_mock_train_unavailable_quota_regret(mock_server, browser_page, workflow):
    """Verify that if seats are unavailable (WL REGRET), the workflow halts immediately
    and reports quota regret failure.
    """
    browser_page.goto(mock_server.quota_regret_url)
    workflow.sm = BookingStateMachine(initial_state=BookingState.TRAIN_SELECTION)

    res = workflow.select_class("3A", train_number="12004")
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert workflow.sm.current_state == BookingState.FAILURE
    assert "REGRET" in res.message.upper() or "regret" in res.message.lower()


# ==================== Test 10: Login Required Flow ====================


def test_mock_login_status_detection(mock_server, browser_page, workflow):
    """Verify detection of logged-in vs login-required states on mock pages."""
    # When logged out
    mock_server.logged_in = False
    browser_page.goto(mock_server.booking_url)
    workflow.sm = BookingStateMachine(initial_state=BookingState.BROWSER_READY)

    res_not_logged = workflow.check_login_status()
    assert res_not_logged.success is True
    assert res_not_logged.state == BookingState.USER_LOGIN_REQUIRED
    assert workflow.sm.current_state == BookingState.USER_LOGIN_REQUIRED

    # When logged in
    mock_server.logged_in = True
    browser_page.goto(mock_server.booking_url)
    workflow.sm = BookingStateMachine(initial_state=BookingState.BROWSER_READY)

    res_logged = workflow.check_login_status()
    assert res_logged.success is True
    assert res_logged.state == BookingState.USER_LOGGED_IN
    assert workflow.sm.current_state == BookingState.USER_LOGGED_IN
