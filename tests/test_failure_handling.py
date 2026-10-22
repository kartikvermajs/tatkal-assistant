"""Automated test suite for Phase 19: Failure Handling & Graceful Recovery.

Verifies deterministic failure handling for:
- browser crash
- page timeout
- network error
- session expiration
- train unavailable
- quota unavailable
- CAPTCHA
- OTP
- payment failure
- booking success
- unknown booking status

Enforces:
- Human-readable status messages
- No silently ignored exceptions
- Strict non-blind retry policy
- Absolute ban on retries after uncertain payment state
"""

import os
from unittest.mock import MagicMock
import pytest
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright

from core.booking_state import BookingState, BookingStateMachine
from core.failure_handler import (
    FailureDetail,
    FailureType,
    RetryPolicy,
    classify_failure,
    execute_with_limited_retry,
)
from browser.irctc_workflow import IRCTCWorkflow
from models.trip import Trip


@pytest.fixture
def browser_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        yield page
        try:
            if not page.is_closed():
                page.close()
            context.close()
            browser.close()
        except Exception:
            pass


@pytest.fixture
def mock_trip():
    from datetime import date, timedelta
    return Trip(
        from_station="NDLS",
        to_station="MMCT",
        journey_date=date.today() + timedelta(days=1),
        train_number="12952",
        class_code="3A",
        quota="TATKAL",
    )


# ==================== 1. Failure Classification & Human-Readable Messages ====================

def test_classify_browser_crash():
    exc = PlaywrightError("Target page, context or browser has been closed")
    failure = classify_failure(exc, stage="select_train")
    assert failure.failure_type == FailureType.BROWSER_CRASH
    assert failure.message == "Browser closed unexpectedly or crashed during workflow."
    assert failure.is_retryable is False


def test_classify_page_timeout_contextual():
    # Train selection stage
    exc = PlaywrightTimeoutError("Timeout 30000ms exceeded while waiting for selector")
    f_train = classify_failure(exc, stage="train_selection")
    assert f_train.failure_type == FailureType.PAGE_TIMEOUT
    assert f_train.message == "Network timeout while loading train selection."
    assert f_train.is_retryable is True

    # Portal load stage
    f_portal = classify_failure(exc, stage="portal")
    assert f_portal.message == "Network timeout while loading IRCTC portal."
    assert f_portal.is_retryable is True

    # Payment stage (TIMEOUT MUST NOT BE RETRYABLE)
    f_pay = classify_failure(exc, stage="payment")
    assert f_pay.is_retryable is False


def test_classify_network_error():
    exc = PlaywrightError("net::ERR_NAME_NOT_RESOLVED at https://www.irctc.co.in")
    failure = classify_failure(exc, stage="portal")
    assert failure.failure_type == FailureType.NETWORK_ERROR
    assert "Unable to reach IRCTC servers" in failure.message
    assert failure.is_retryable is True


def test_classify_session_expiration():
    exc = "Your session has expired. Please login again."
    failure = classify_failure(exc, stage="review")
    assert failure.failure_type == FailureType.SESSION_EXPIRATION
    assert failure.message == "IRCTC session expired. Please log in again to continue."
    assert failure.is_retryable is False


def test_classify_train_unavailable():
    failure = classify_failure(
        "Train not found on page",
        stage="train_selection",
        context={"train_number": "12952"},
    )
    assert failure.failure_type == FailureType.TRAIN_UNAVAILABLE
    assert failure.message == "Specified train '12952' was not found on results page. Substitution is prohibited."
    assert failure.is_retryable is False


def test_classify_quota_unavailable():
    failure = classify_failure(
        "REGRET / Quota Exhausted: No seats available in Tatkal",
        stage="train_selection",
        context={"train_number": "12952", "class_code": "3A"},
    )
    assert failure.failure_type == FailureType.QUOTA_UNAVAILABLE
    assert failure.message == "Tatkal quota unavailable for train 12952 in class 3A (Regret / No Seats Available)."
    assert failure.is_retryable is False


def test_classify_captcha_checkpoint():
    f_req = classify_failure("captcha verification required", stage="captcha")
    assert f_req.failure_type == FailureType.CAPTCHA

    f_cancel = classify_failure("captcha cancelled by user", stage="captcha")
    assert f_cancel.message == "CAPTCHA entry cancelled by user."

    f_timeout = classify_failure("captcha timeout", stage="captcha")
    assert f_timeout.message == "Timeout waiting for human CAPTCHA completion."


def test_classify_otp_checkpoint():
    f_req = classify_failure("otp required", stage="otp")
    assert f_req.failure_type == FailureType.OTP

    f_cancel = classify_failure("otp cancelled by user", stage="otp")
    assert f_cancel.message == "OTP authentication cancelled by user."

    f_invalid = classify_failure("invalid otp entered", stage="otp")
    assert f_invalid.message == "Invalid or incorrect OTP entered in browser."


def test_classify_payment_failure():
    exc = PlaywrightError("Payment failed: Transaction declined by issuing bank")
    failure = classify_failure(exc, stage="payment")
    assert failure.failure_type == FailureType.PAYMENT_FAILURE
    assert failure.message == "Payment failed or was declined by bank/gateway."
    assert failure.is_retryable is False


def test_classify_booking_success():
    failure = classify_failure(
        "Booking Confirmed PNR 1234567890",
        stage="confirmation",
        context={"pnr": "1234567890"},
    )
    assert failure.failure_type == FailureType.BOOKING_SUCCESS
    assert failure.message == "BOOKING SUCCESSFUL: Booking confirmed! PNR: 1234567890"


def test_classify_unknown_booking_status():
    failure = classify_failure(
        "Payment deducted but booking status is uncertain",
        stage="confirmation",
    )
    assert failure.failure_type == FailureType.UNKNOWN_BOOKING_STATUS
    assert failure.message == "Booking status is uncertain. Verify IRCTC booking history before attempting another booking."
    assert failure.is_retryable is False


# ==================== 2. Strict Retry Policy Enforcement ====================

def test_retry_policy_allows_limited_retries_for_network_and_timeout():
    policy = RetryPolicy(max_retries=2, retry_delay_seconds=0.01)

    timeout_fail = classify_failure(PlaywrightTimeoutError("Timeout"), stage="portal")
    assert policy.can_retry(timeout_fail, attempt=0, current_state=BookingState.IDLE) is True
    assert policy.can_retry(timeout_fail, attempt=1, current_state=BookingState.IDLE) is True
    assert policy.can_retry(timeout_fail, attempt=2, current_state=BookingState.IDLE) is False  # max reached


def test_retry_policy_strictly_forbids_retry_after_uncertain_payment():
    policy = RetryPolicy(max_retries=2)
    unknown_fail = classify_failure("booking status is uncertain", stage="confirmation")

    # MUST NEVER RETRY
    assert policy.can_retry(unknown_fail, attempt=0, current_state=BookingState.UNKNOWN) is False
    assert policy.can_retry(unknown_fail, attempt=0, current_state=BookingState.PAYMENT_REQUIRED) is False
    assert policy.can_retry(unknown_fail, attempt=0, current_state=BookingState.BOOKING_CONFIRMATION) is False


def test_retry_policy_strictly_forbids_retry_on_payment_failure():
    policy = RetryPolicy(max_retries=2)
    pay_fail = classify_failure("Payment Failed: Card expired", stage="payment")
    assert policy.can_retry(pay_fail, attempt=0, current_state=BookingState.PAYMENT_REQUIRED) is False


def test_retry_policy_strictly_forbids_retry_for_business_rejections():
    policy = RetryPolicy(max_retries=2)
    train_fail = classify_failure("Train not found", stage="train_selection")
    quota_fail = classify_failure("REGRET", stage="train_selection")
    session_fail = classify_failure("session expired", stage="journey_selection")

    assert policy.can_retry(train_fail, attempt=0, current_state=BookingState.TRAIN_SELECTION) is False
    assert policy.can_retry(quota_fail, attempt=0, current_state=BookingState.TRAIN_SELECTION) is False
    assert policy.can_retry(session_fail, attempt=0, current_state=BookingState.JOURNEY_SELECTION) is False


def test_execute_with_limited_retry_succeeds_after_transient_failure():
    policy = RetryPolicy(max_retries=2, retry_delay_seconds=0.01)
    call_count = 0

    def flaky_network_action(attempt: int):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise PlaywrightError("net::ERR_CONNECTION_RESET")
        return "SUCCESS"

    result = execute_with_limited_retry(
        flaky_network_action,
        stage="portal",
        policy=policy,
        current_state=BookingState.IDLE,
    )
    assert result == "SUCCESS"
    assert call_count == 2


def test_execute_with_limited_retry_raises_when_retries_exhausted():
    policy = RetryPolicy(max_retries=2, retry_delay_seconds=0.01)

    def continuously_failing_action(attempt: int):
        raise PlaywrightTimeoutError("Timeout on train page")

    with pytest.raises(RuntimeError) as exc_info:
        execute_with_limited_retry(
            continuously_failing_action,
            stage="train_selection",
            policy=policy,
            current_state=BookingState.TRAIN_SELECTION,
        )

    assert "Network timeout while loading train selection." in str(exc_info.value)


# ==================== 3. Browser & Page Failure Scenarios ====================

def test_workflow_detects_browser_crash(browser_page, mock_trip):
    """When the browser is unexpectedly closed, workflow reports crash and transitions to FAILURE."""
    sm = BookingStateMachine()
    workflow = IRCTCWorkflow(page=browser_page, state_machine=sm)

    # Close browser page to simulate sudden crash/user close
    browser_page.close()

    res = workflow.select_train(mock_trip.train_number)
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert sm.current_state == BookingState.FAILURE
    assert res.message == "Browser closed unexpectedly or crashed during workflow."


def test_workflow_detects_session_expiration(browser_page, mock_trip):
    """When IRCTC session expires on page, workflow reports session expired."""
    html = """
    <html>
      <body>
        <div id="session-expired" class="alert alert-danger">
          Your session has expired. Please login again to continue.
        </div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html;charset=utf-8,{html}")

    sm = BookingStateMachine()
    workflow = IRCTCWorkflow(page=browser_page, state_machine=sm)
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)

    res = workflow.select_train(mock_trip.train_number)
    assert res.success is False
    assert "IRCTC session expired. Please log in again to continue." in res.message


def test_workflow_detects_train_unavailable(browser_page, mock_trip):
    """When configured train is not present, workflow halts with prohibited substitution error."""
    html = """
    <html>
      <body>
        <div class="train-item">12951 - TEJAS RAJDHANI</div>
        <div class="train-item">12953 - AUGUST KRANTI</div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html;charset=utf-8,{html}")

    sm = BookingStateMachine()
    workflow = IRCTCWorkflow(page=browser_page, state_machine=sm)
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)

    res = workflow.select_train("12952")
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert res.message == "Specified train '12952' was not found on results page. Substitution is prohibited."


def test_workflow_detects_quota_regret(browser_page, mock_trip):
    """When Tatkal quota is regret/exhausted, workflow fails with clear quota unavailable message."""
    html = """
    <html>
      <body>
        <div class="class-item" data-class="3A">
          <span class="avl-regret">REGRET / No Seats Available</span>
        </div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html;charset=utf-8,{html}")

    sm = BookingStateMachine()
    workflow = IRCTCWorkflow(page=browser_page, state_machine=sm)
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    res = workflow.select_class("3A", train_number=mock_trip.train_number)
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert res.message == "Tatkal quota unavailable for train 12952 in class 3A (Regret / No Seats Available)."


def test_workflow_detects_payment_failure_page(browser_page):
    """When payment gateway displays failure, detect_checkpoints stops with payment failed error."""
    html = """
    <html>
      <body>
        <div data-testid="payment-failure" class="alert-danger">
          Payment Failed: Transaction was declined by bank.
        </div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html;charset=utf-8,{html}")

    sm = BookingStateMachine()
    workflow = IRCTCWorkflow(page=browser_page, state_machine=sm)
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)
    workflow.sm.transition_to(BookingState.REVIEW)

    res = workflow.detect_checkpoints()
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert res.message == "Payment failed or was declined by bank/gateway."


# ==================== 4. MainWindow UI Failure & Cancellation Tests ====================

def test_main_window_user_cancels_otp_displays_human_message(qapp, tmp_path, monkeypatch):
    """Cancelling OTP checkpoint updates UI with human-readable cancellation message."""
    from database.db import Database
    from ui.main_window import MainWindow
    from ui.otp_checkpoint_dialog import OtpCheckpointDialog
    from PySide6.QtWidgets import QDialog

    db = Database(str(tmp_path / "test_ui.db"))
    window = MainWindow(db)

    # Mock workflow in OTP_REQUIRED state
    sm = BookingStateMachine()
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGIN_REQUIRED)
    sm.transition_to(BookingState.OTP_REQUIRED)
    window.current_workflow = MagicMock()
    window.current_workflow.sm = sm

    # Mock user clicking CANCEL on OtpCheckpointDialog
    monkeypatch.setattr(OtpCheckpointDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    window._on_checkpoint_clicked()
    assert "OTP authentication cancelled by user." in window.status_label.text()
    assert window.prepare_booking_btn.isEnabled() is True


def test_main_window_user_cancels_payment_displays_human_message(qapp, tmp_path, monkeypatch):
    """Cancelling Payment checkpoint updates UI with human-readable cancellation message."""
    from database.db import Database
    from ui.main_window import MainWindow
    from ui.payment_checkpoint_dialog import PaymentCheckpointDialog
    from PySide6.QtWidgets import QDialog

    db = Database(str(tmp_path / "test_ui_pay.db"))
    window = MainWindow(db)

    sm = BookingStateMachine()
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGIN_REQUIRED)
    sm.transition_to(BookingState.OTP_REQUIRED)
    sm.transition_to(BookingState.PAYMENT_REQUIRED)
    window.current_workflow = MagicMock()
    window.current_workflow.sm = sm

    monkeypatch.setattr(PaymentCheckpointDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    window._on_checkpoint_clicked()
    assert "Payment authorization cancelled by user." in window.status_label.text()
    assert window.prepare_booking_btn.isEnabled() is True


def test_main_window_uncertain_outcome_deadlock_lockout(qapp, tmp_path, monkeypatch):
    """When booking outcome is uncertain, MainWindow displays exact message and strictly disables retry."""
    from database.db import Database
    from ui.main_window import MainWindow
    from ui.booking_confirmation_dialog import BookingConfirmationDialog
    from browser.irctc_workflow import WorkflowStepResult

    db = Database(str(tmp_path / "test_ui_deadlock.db"))
    window = MainWindow(db)

    sm = BookingStateMachine()
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGIN_REQUIRED)
    sm.transition_to(BookingState.OTP_REQUIRED)
    sm.transition_to(BookingState.PAYMENT_REQUIRED)
    window.current_workflow = MagicMock()
    window.current_workflow.sm = sm

    # Transition to confirmation check
    window.current_workflow.confirm_checkpoint_completed.return_value = WorkflowStepResult(
        success=True,
        state=BookingState.BOOKING_CONFIRMATION,
        message="Payment authorized by user",
    )
    # Verification returns UNKNOWN
    window.current_workflow.verify_booking_result.return_value = WorkflowStepResult(
        success=False,
        state=BookingState.UNKNOWN,
        message="Booking status is uncertain. Verify IRCTC booking history before attempting another booking.",
    )
    window.current_workflow.save_booking_result.return_value = None

    monkeypatch.setattr(BookingConfirmationDialog, "exec", lambda self: None)

    window._on_checkpoint_clicked()

    # Verify status label displays the exact uncertain message
    assert "Booking status is uncertain. Verify IRCTC booking history before attempting another booking." in window.status_label.text()
    # Verify retry lockout: prepare_booking_btn MUST BE DISABLED
    assert window.prepare_booking_btn.isEnabled() is False

