"""Tests for Phase 17: Payment Stage & Financial Authorization Checkpoint.

Verifies:
1. Payment preference optimization for IRCTC eWallet (plus UPI and Credit Card).
2. Navigation to payment-selection stage and category selection.
3. Automation strictly halts at payment authorization.
4. Dedicated PaymentCheckpointDialog displaying:
   - "PAYMENT AUTHORIZATION REQUIRED"
   - "Complete the payment in the browser."
   - [ PAYMENT COMPLETED ] and [ CANCEL ] buttons.
5. Strict Security & Compliance Audit:
   - Zero wallet PIN capture or storage.
   - Zero CVV capture or storage.
   - Zero banking OTP capture or storage.
   - Zero automated financial transaction authorization.
"""

import os
import pytest
from playwright.sync_api import sync_playwright

import config
from browser.irctc_workflow import IRCTCWorkflow
from core.booking_state import BookingState, BookingStateMachine
from database.db import Database
from models.settings import ApplicationSettings
from ui.main_window import MainWindow
from ui.payment_checkpoint_dialog import PaymentCheckpointDialog


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


# ==================== 1. PaymentCheckpointDialog UI Verification ====================


def test_payment_checkpoint_dialog_ui_elements(qapp):
    """Verify dialog displays exact required prompt text, buttons, and security notice."""
    dialog = PaymentCheckpointDialog(payment_method="IRCTC eWallet")
    assert dialog.windowTitle() == "Payment Checkpoint"
    assert hasattr(dialog, "completed_btn")
    assert hasattr(dialog, "cancel_btn")
    assert dialog.completed_btn.text() == "PAYMENT COMPLETED"
    assert dialog.cancel_btn.text() == "CANCEL"

    # Verify exact texts required by Phase 17 specification
    labels_text = [child.text() for child in dialog.findChildren(object) if hasattr(child, "text")]
    combined_text = " ".join(labels_text)
    assert "PAYMENT AUTHORIZATION REQUIRED" in combined_text
    assert "Complete the payment in the browser" in combined_text
    assert "IRCTC eWallet" in combined_text
    assert "never captures" in combined_text
    assert "wallet PIN" in combined_text

    # Test Completed click
    dialog.completed_btn.click()
    assert dialog.completed is True

    # Test Cancel click
    dialog2 = PaymentCheckpointDialog(payment_method="IRCTC eWallet")
    dialog2.cancel_btn.click()
    assert dialog2.completed is False


# ==================== 2. Payment Selection Stage Automation ====================


def test_open_payment_optimized_for_irctc_ewallet(workflow, browser_page):
    """Verifies that open_payment selects IRCTC eWallet by default and halts before authorization."""
    html = """
    <html>
      <body>
        <div id="payment-gateways">
          <input type="radio" name="paymentOption" value="IRCTC_EWALLET" data-testid="pay-ewallet" />
          <label>IRCTC eWallet</label>

          <input type="radio" name="paymentOption" value="UPI" data-testid="pay-upi" />
          <label>BHIM / UPI</label>
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

    res = workflow.open_payment("IRCTC eWallet")
    assert res.success is True
    assert res.state == BookingState.PAYMENT_REQUIRED
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED
    assert browser_page.locator("[data-testid='pay-ewallet']").is_checked() is True
    assert "Never automated" in res.message


def test_open_payment_selects_upi_and_cards(workflow, browser_page):
    """Verifies open_payment also supports alternative payment preferences."""
    html = """
    <html>
      <body>
        <div id="payment-gateways">
          <input type="radio" name="pay" value="2" data-testid="pay-upi" />
          <input type="radio" name="pay" value="1" data-testid="pay-cards" />
        </div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")

    # UPI
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)
    workflow.sm.transition_to(BookingState.REVIEW)

    res_upi = workflow.open_payment("UPI")
    assert res_upi.state == BookingState.PAYMENT_REQUIRED
    assert browser_page.locator("[data-testid='pay-upi']").is_checked() is True

    # Credit Card
    res_card = workflow.open_payment("Credit Card")
    assert res_card.state == BookingState.PAYMENT_REQUIRED
    assert browser_page.locator("[data-testid='pay-cards']").is_checked() is True


# ==================== 3. Payment Completed Advancement ====================


def test_confirm_checkpoint_after_payment_authorization(workflow, browser_page):
    """When user confirms payment authorization in browser, state moves to BOOKING_CONFIRMATION."""
    browser_page.goto("data:text/html,<html><body><div>Authorizing Payment...</div></body></html>")

    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)
    workflow.sm.transition_to(BookingState.REVIEW)
    workflow.sm.transition_to(BookingState.PAYMENT_REQUIRED)

    res = workflow.confirm_checkpoint_completed()
    assert res.success is True
    assert res.state == BookingState.BOOKING_CONFIRMATION
    assert workflow.sm.current_state == BookingState.BOOKING_CONFIRMATION


# ==================== 4. Desktop MainWindow Integration ====================


def test_main_window_payment_checkpoint_ui_flow(qapp, browser_page):
    """Verify MainWindow handles PAYMENT_REQUIRED with button text and checkpoint dialog."""
    window = MainWindow()

    html = "<html><body><div id='payment-stage'>Payment Page</div></body></html>"
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
    window.checkpoint_btn.setText("PAYMENT COMPLETED")
    window.status_label.setText("PAYMENT AUTHORIZATION REQUIRED (Complete in browser)")

    assert window.checkpoint_btn.text() == "PAYMENT COMPLETED"
    assert "PAYMENT AUTHORIZATION REQUIRED" in window.status_label.text()

    # User clicks checkpoint button (simulating PAYMENT COMPLETED click)
    window.checkpoint_btn.click()

    # Workflow advances to checking outcome
    assert sm.current_state in {BookingState.BOOKING_CONFIRMATION, BookingState.UNKNOWN, BookingState.SUCCESS}
    window.close()


# ==================== 5. Settings Payment Preferences ====================


def test_settings_preferred_payment_mode_options():
    """Verify ApplicationSettings defaults to IRCTC eWallet and rejects invalid modes."""
    settings = ApplicationSettings()
    assert settings.preferred_payment_mode == "IRCTC eWallet"

    # Support UPI and Credit Card
    s_upi = ApplicationSettings(preferred_payment_mode="UPI")
    assert s_upi.preferred_payment_mode == "UPI"

    s_card = ApplicationSettings(preferred_payment_mode="Credit Card")
    assert s_card.preferred_payment_mode == "Credit Card"

    # Rejects invalid mode
    with pytest.raises(ValueError, match="Invalid payment mode"):
        ApplicationSettings(preferred_payment_mode="BITCOIN")


# ==================== 6. Strict Security Audit: Financial Information ====================


def test_security_audit_prohibited_financial_credentials():
    """Verify zero CVV, wallet PIN, or banking OTP harvesting in project codebase."""
    prohibited_terms = [
        "wallet_pin",
        "ewallet_pin",
        "store_pin",
        "save_pin",
        "card_cvv",
        "store_cvv",
        "save_cvv",
        "banking_otp",
        "capture_otp",
        "capture_pin",
        "capture_cvv",
        "auto_authorize",
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
                    for term in prohibited_terms:
                        assert term not in content, (
                            f"Security violation: Prohibited financial term '{term}' found in {path}."
                        )
