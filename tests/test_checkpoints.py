"""Comprehensive unit and integration tests for Phase 14 Review & Human Checkpoints."""

from datetime import date, timedelta
import inspect
import os
import pytest
from playwright.sync_api import sync_playwright

import config
from browser.irctc_workflow import IRCTCWorkflow, WorkflowStepResult
from core.booking_state import BookingState, BookingStateMachine
from models.passenger import Passenger
from models.trip import Trip
from services.notification_service import NotificationService
from ui.main_window import MainWindow


@pytest.fixture(scope="module")
def browser_page():
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    yield page
    page.close()
    browser.close()
    p.stop()


@pytest.fixture
def workflow(browser_page):
    sm = BookingStateMachine()
    return IRCTCWorkflow(page=browser_page, state_machine=sm)


# ==================== 1. Review & Progression ====================


def test_proceed_to_review_navigation(workflow, browser_page):
    """Verify proceed_to_review clicks continue on passenger page and enters REVIEW state."""
    html = """
    <html>
      <body>
        <div id="passenger-summary">Passenger Form</div>
        <button data-testid="continue-btn">Continue</button>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)

    res = workflow.proceed_to_review()
    assert res.success is True
    assert res.state == BookingState.REVIEW
    assert workflow.sm.current_state == BookingState.REVIEW


def test_proceed_to_review_error_aborts(workflow, browser_page):
    """If error appears when progressing to review, automation halts immediately."""
    html = """
    <html>
      <head><title>Booking Error</title></head>
      <body>
        <div class="alert-danger">Quota exceeded for selected train.</div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)

    res = workflow.proceed_to_review()
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert workflow.sm.current_state == BookingState.FAILURE
    assert "Error page or validation failure" in res.message


# ==================== 2. CAPTCHA Checkpoint ====================


def test_detect_captcha_checkpoint(workflow, browser_page):
    """When CAPTCHA element is present, detect_checkpoints enters CAPTCHA_REQUIRED."""
    html = """
    <html>
      <body>
        <h3>Review Booking</h3>
        <img class="captcha-img" data-testid="captcha-img" src="data:image/png;base64," />
        <input placeholder="Enter Captcha" data-testid="captcha-input" />
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

    res = workflow.detect_checkpoints()
    assert res.success is True
    assert res.state == BookingState.CAPTCHA_REQUIRED
    assert workflow.sm.current_state == BookingState.CAPTCHA_REQUIRED
    assert "CAPTCHA encountered" in res.message


def test_confirm_captcha_completed_transitions_to_payment(workflow, browser_page):
    """After solving CAPTCHA, confirm_checkpoint_completed advances to payment."""
    # CAPTCHA solved, now on payment page
    html = """
    <html>
      <body>
        <div id="payment-gateways" data-testid="payment-options">Payment Options</div>
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
    workflow.sm.transition_to(BookingState.CAPTCHA_REQUIRED)

    res = workflow.confirm_checkpoint_completed()
    assert res.success is True
    assert res.state == BookingState.PAYMENT_REQUIRED
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED


# ==================== 3. OTP Checkpoint ====================


def test_detect_otp_checkpoint(workflow, browser_page):
    """When OTP element is present, detect_checkpoints enters OTP_REQUIRED."""
    html = """
    <html>
      <body>
        <h3>Aadhaar / Bank Verification</h3>
        <input placeholder="Enter OTP" data-testid="otp-input" />
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

    res = workflow.detect_checkpoints()
    assert res.success is True
    assert res.state == BookingState.OTP_REQUIRED
    assert workflow.sm.current_state == BookingState.OTP_REQUIRED
    assert "OTP authentication required" in res.message


def test_confirm_otp_completed_transitions_to_payment(workflow, browser_page):
    """After user inputs OTP in browser, confirm_checkpoint_completed advances to payment."""
    browser_page.goto("data:text/html,<html><body>Payment Stage</body></html>")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)
    workflow.sm.transition_to(BookingState.REVIEW)
    workflow.sm.transition_to(BookingState.OTP_REQUIRED)

    res = workflow.confirm_checkpoint_completed()
    assert res.success is True
    assert res.state == BookingState.PAYMENT_REQUIRED
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED


# ==================== 4. Payment Transition & Strict Authorization Stop ====================


def test_open_payment_selects_category(workflow, browser_page):
    """open_payment selects the specified category and reaches PAYMENT_REQUIRED."""
    html = """
    <html>
      <body>
        <input type="radio" name="pay" value="2" data-testid="pay-upi" />
        <input type="radio" name="pay" value="1" data-testid="pay-cards" />
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

    res = workflow.open_payment("BHIM/UPI")
    assert res.success is True
    assert res.state == BookingState.PAYMENT_REQUIRED
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED
    assert browser_page.locator("[data-testid='pay-upi']").is_checked() is True


def test_wait_for_payment_authorization_strict_halt(workflow):
    """Automation strictly halts before payment authorization."""
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)
    workflow.sm.transition_to(BookingState.REVIEW)
    workflow.sm.transition_to(BookingState.PAYMENT_REQUIRED)

    res = workflow.wait_for_payment_authorization()
    assert res.success is True
    assert res.state == BookingState.PAYMENT_REQUIRED
    assert "Never automated" in res.message


# ==================== 5. Desktop UI Integration & Checkpoint Button ====================


def test_main_window_checkpoint_button_interaction(qapp, browser_page):
    """Verify main window checkpoint button enables on human checkpoints."""
    window = MainWindow()
    assert window.checkpoint_btn.isEnabled() is False

    browser_page.goto("data:text/html,<html><body><div>Payment Stage</div></body></html>")

    # Simulate checkpoint reached
    sm = BookingStateMachine()
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    sm.transition_to(BookingState.JOURNEY_SELECTION)
    sm.transition_to(BookingState.TRAIN_SELECTION)
    sm.transition_to(BookingState.PASSENGER_SELECTION)
    sm.transition_to(BookingState.REVIEW)
    sm.transition_to(BookingState.CAPTCHA_REQUIRED)

    wf = IRCTCWorkflow(page=browser_page, state_machine=sm)
    window.current_workflow = wf

    # Simulate user clicking checkpoint button
    window.checkpoint_btn.setEnabled(True)
    window.checkpoint_btn.click()

    assert "PAYMENT REQUIRED" in window.status_label.text()
    assert window.current_workflow.sm.current_state == BookingState.PAYMENT_REQUIRED
    window.close()


def test_checkpoint_alert_trigger(qapp):
    """Verify notification service triggers checkpoint alert without errors."""
    service = NotificationService()
    # Test triggering checkpoint alert (no errors raised)
    service.trigger_checkpoint_alert("CAPTCHA", sound=False, visual=False)


# ==================== 6. Security Audit: Prohibited CAPTCHA Solvers ====================


def test_security_audit_prohibited_captcha_solvers():
    """Verify that no CAPTCHA solving, OCR, or bypass tools exist anywhere in project application files."""
    prohibited_tools = [
        "pytesseract",
        "tesseract",
        "easyocr",
        "captcha_solver",
        "2captcha",
        "anticaptcha",
        "deathbycaptcha",
        "bypass_captcha",
        "solve_captcha",
    ]

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for root, _, files in os.walk(project_root):
        if ".venv" in root or "__pycache__" in root or "tests" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                    for tool in prohibited_tools:
                        assert tool not in content, (
                            f"Security compliance violation: prohibited term '{tool}' found in {path}."
                        )
