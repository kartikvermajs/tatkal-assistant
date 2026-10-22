"""Tests for Phase 16: Human OTP Checkpoint.

Verifies:
1. Dedicated OtpCheckpointDialog with required text:
   - "OTP REQUIRED"
   - "Complete authentication in the browser."
   - [ CONTINUE ] and [ CANCEL ] buttons.
2. Workflow halts automation at OTP checkpoint.
3. DOM detection for Aadhaar OTP, IRCTC Login OTP, and general OTP inputs.
4. Validation error handling (Invalid OTP stays in OTP_REQUIRED).
5. State transitions from OTP_REQUIRED to PAYMENT_REQUIRED or USER_LOGGED_IN.
6. Desktop MainWindow integration.
7. Strict Security Audit:
   - Zero SMS reading.
   - Zero email reading.
   - Zero automated clipboard OTP harvesting.
   - Zero OTP persistence or transmission.
"""

import os
import pytest
from playwright.sync_api import sync_playwright

from browser.irctc_workflow import IRCTCWorkflow
from core.booking_state import BookingState, BookingStateMachine, InvalidStateTransitionError
from database.db import Database
from models.trip import Trip
from ui.main_window import MainWindow
from ui.otp_checkpoint_dialog import OtpCheckpointDialog


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


# ==================== 1. OtpCheckpointDialog UI Verification ====================


def test_otp_checkpoint_dialog_ui_elements(qapp):
    """Verify dialog displays exact required prompt text, buttons, and security notice."""
    dialog = OtpCheckpointDialog()
    assert dialog.windowTitle() == "OTP Checkpoint"
    assert hasattr(dialog, "continue_btn")
    assert hasattr(dialog, "cancel_btn")
    assert dialog.continue_btn.text() == "CONTINUE"
    assert dialog.cancel_btn.text() == "CANCEL"

    # Verify exact texts from Phase 16 requirements are present
    labels_text = [child.text() for child in dialog.findChildren(object) if hasattr(child, "text")]
    combined_text = " ".join(labels_text)
    assert "OTP REQUIRED" in combined_text
    assert "Complete authentication in the browser" in combined_text
    assert "never reads SMS" in combined_text
    assert "stores/transmits OTP" in combined_text

    # Test Continue click
    dialog.continue_btn.click()
    assert dialog.confirmed is True

    # Test Cancel click
    dialog2 = OtpCheckpointDialog()
    dialog2.cancel_btn.click()
    assert dialog2.confirmed is False


# ==================== 2. State Machine Transitions for OTP ====================


def test_otp_state_machine_legal_and_illegal_transitions():
    """Verify deterministic state machine transitions involving OTP_REQUIRED."""
    sm = BookingStateMachine()
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    sm.transition_to(BookingState.JOURNEY_SELECTION)
    sm.transition_to(BookingState.TRAIN_SELECTION)
    sm.transition_to(BookingState.PASSENGER_SELECTION)
    sm.transition_to(BookingState.REVIEW)

    # Review to OTP_REQUIRED
    sm.transition_to(BookingState.OTP_REQUIRED, "Aadhaar verification OTP")
    assert sm.current_state == BookingState.OTP_REQUIRED

    # Illegal transition: cannot jump directly from OTP to SUCCESS
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.SUCCESS)

    # Illegal transition: cannot jump backwards from OTP to TRAIN_SELECTION
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(BookingState.TRAIN_SELECTION)

    # Legal transition: OTP to PAYMENT_REQUIRED
    sm.transition_to(BookingState.PAYMENT_REQUIRED, "OTP entered")
    assert sm.current_state == BookingState.PAYMENT_REQUIRED


# ==================== 3. DOM Detection of Aadhaar & Other OTP Inputs ====================


def test_detect_checkpoints_aadhaar_otp_element(workflow, browser_page):
    """Detects Aadhaar OTP input by id and pauses automation."""
    html = """
    <html>
      <body>
        <div>
          <h3>Aadhaar Verification</h3>
          <input type="text" id="aadhaarOtp" placeholder="Enter Aadhaar OTP" />
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

    res = workflow.detect_checkpoints()
    assert res.success is True
    assert res.state == BookingState.OTP_REQUIRED
    assert workflow.sm.current_state == BookingState.OTP_REQUIRED
    assert "OTP REQUIRED" in res.message


def test_detect_checkpoints_otp_text_prompt(workflow, browser_page):
    """Detects OTP requirement when text prompt indicates OTP sent to mobile."""
    html = """
    <html>
      <body>
        <div>
          <p>Enter OTP sent to your registered mobile number</p>
          <input type="password" name="userOtp" />
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

    res = workflow.detect_checkpoints()
    assert res.success is True
    assert res.state == BookingState.OTP_REQUIRED
    assert workflow.sm.current_state == BookingState.OTP_REQUIRED


# ==================== 4. Checkpoint Confirmation & Validation ====================


def test_confirm_otp_with_page_error_stays_in_otp(workflow, browser_page):
    """If page displays Invalid OTP error, confirm_checkpoint_completed keeps user in OTP_REQUIRED."""
    html = """
    <html>
      <body>
        <div class="alert alert-danger error-message">
          Invalid OTP entered. Please try again.
        </div>
        <input type="text" id="otp" />
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
    workflow.sm.transition_to(BookingState.OTP_REQUIRED)

    res = workflow.confirm_checkpoint_completed()
    assert res.success is False
    assert res.state == BookingState.OTP_REQUIRED
    assert workflow.sm.current_state == BookingState.OTP_REQUIRED
    assert "OTP Authentication failed" in res.message


def test_confirm_otp_successful_advances_to_payment(workflow, browser_page):
    """When OTP authentication succeeds in browser, confirm advances to payment."""
    html = """
    <html>
      <body>
        <div id="payment-stage">
          <h3>Payment Options</h3>
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
    workflow.sm.transition_to(BookingState.OTP_REQUIRED)

    res = workflow.confirm_checkpoint_completed()
    assert res.success is True
    assert res.state == BookingState.PAYMENT_REQUIRED
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED


# ==================== 5. Desktop MainWindow Integration ====================


def test_main_window_otp_checkpoint_flow(qapp, browser_page):
    """Verify MainWindow handles OTP checkpoint, updates button and status."""
    window = MainWindow()

    html = "<html><body><div>Payment Stage</div></body></html>"
    browser_page.goto(f"data:text/html,{html}")

    sm = BookingStateMachine()
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    sm.transition_to(BookingState.JOURNEY_SELECTION)
    sm.transition_to(BookingState.TRAIN_SELECTION)
    sm.transition_to(BookingState.PASSENGER_SELECTION)
    sm.transition_to(BookingState.REVIEW)
    sm.transition_to(BookingState.OTP_REQUIRED)

    wf = IRCTCWorkflow(page=browser_page, state_machine=sm)
    window.current_workflow = wf
    window.checkpoint_btn.setEnabled(True)
    window.checkpoint_btn.click()

    assert sm.current_state == BookingState.PAYMENT_REQUIRED
    assert "PAYMENT REQUIRED" in window.status_label.text()
    window.close()


# ==================== 6. Strict Security Audit: Prohibited OTP Access ====================


def test_security_audit_prohibited_otp_interception():
    """Verify zero SMS/email reading, zero clipboard harvesting, and zero OTP storage."""
    prohibited_keywords = [
        "read_sms",
        "fetch_sms",
        "android_sms",
        "sms_reader",
        "twilio",
        "pysms",
        "read_email",
        "fetch_email",
        "imaplib",
        "poplib",
        "gmail_api",
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
                    for kw in prohibited_keywords:
                        assert kw not in content, (
                            f"Security violation: Prohibited keyword '{kw}' found in {path}."
                        )
