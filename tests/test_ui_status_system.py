"""Automated tests for Phase 22: UI Status System.

Verifies:
- Main GUI displays the current state clearly across all 8 canonical stages:
  ● Browser Ready
  ● Logged In
  ● Waiting for Tatkal
  ● Selecting Train
  ● Passenger Review
  ● CAPTCHA Required
  ● Payment Required
  ● Booking Successful
- Visual state updates (pending, active, completed, action_required, failed)
- Integration with BookingStateMachine and IRCTCWorkflow
- Window reset and cancel behaviors
"""

import os
import pytest
from PySide6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from core.booking_state import BookingState, BookingStateMachine
from ui.main_window import MainWindow
from ui.status_panel import (
    CANONICAL_STEPS,
    StatusPanel,
    STEP_BROWSER_READY,
    STEP_LOGGED_IN,
    STEP_WAITING_FOR_TATKAL,
    STEP_SELECTING_TRAIN,
    STEP_PASSENGER_REVIEW,
    STEP_CAPTCHA_REQUIRED,
    STEP_PAYMENT_REQUIRED,
    STEP_BOOKING_SUCCESSFUL,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def status_panel(qapp):
    panel = StatusPanel()
    yield panel
    panel.close()


@pytest.fixture
def main_window(qapp):
    win = MainWindow()
    yield win
    win.close()


# ==================== StatusPanel Unit Tests ====================


def test_status_panel_initialization(status_panel):
    """Verify that all 8 canonical steps are present and initialized to pending."""
    expected_steps = [
        "Browser Ready",
        "Logged In",
        "Waiting for Tatkal",
        "Selecting Train",
        "Passenger Review",
        "CAPTCHA Required",
        "Payment Required",
        "Booking Successful",
    ]

    assert len(status_panel.step_labels) == 8
    for step_id, step_name in CANONICAL_STEPS:
        assert step_id in status_panel.step_labels
        assert step_name in expected_steps
        lbl = status_panel.step_labels[step_id]
        assert "●" in lbl.text()
        assert step_name in lbl.text()
        assert status_panel.get_step_state(step_id) == "pending"

    assert status_panel.get_status_text() == "READY"


def test_status_panel_step_visual_states(status_panel):
    """Verify setting each visual state modifies label content and style."""
    # Active state
    status_panel.set_step_state(STEP_BROWSER_READY, "active")
    assert status_panel.get_step_state(STEP_BROWSER_READY) == "active"
    assert "Browser Ready" in status_panel.step_labels[STEP_BROWSER_READY].text()

    # Completed state
    status_panel.set_step_state(STEP_BROWSER_READY, "completed")
    assert status_panel.get_step_state(STEP_BROWSER_READY) == "completed"
    assert "✓" in status_panel.step_labels[STEP_BROWSER_READY].text()

    # Action required (human checkpoint)
    status_panel.set_step_state(STEP_CAPTCHA_REQUIRED, "action_required")
    assert status_panel.get_step_state(STEP_CAPTCHA_REQUIRED) == "action_required"
    assert "CAPTCHA Required" in status_panel.step_labels[STEP_CAPTCHA_REQUIRED].text()

    # Failed state
    status_panel.set_step_state(STEP_SELECTING_TRAIN, "failed")
    assert status_panel.get_step_state(STEP_SELECTING_TRAIN) == "failed"
    assert "✗" in status_panel.step_labels[STEP_SELECTING_TRAIN].text()

    # Reset
    status_panel.reset()
    assert status_panel.get_step_state(STEP_BROWSER_READY) == "pending"
    assert status_panel.get_step_state(STEP_CAPTCHA_REQUIRED) == "pending"
    assert status_panel.get_step_state(STEP_SELECTING_TRAIN) == "pending"
    assert status_panel.get_status_text() == "READY"


def test_status_panel_booking_state_transitions(status_panel):
    """Verify automatic step progression mapping across the full booking lifecycle."""
    # 1. Browser Ready
    status_panel.update_for_booking_state(BookingState.BROWSER_READY)
    assert status_panel.get_step_state(STEP_BROWSER_READY) == "active"
    assert status_panel.get_step_state(STEP_LOGGED_IN) == "pending"

    # 2. Login Required
    status_panel.update_for_booking_state(BookingState.USER_LOGIN_REQUIRED)
    assert status_panel.get_step_state(STEP_BROWSER_READY) == "completed"
    assert status_panel.get_step_state(STEP_LOGGED_IN) == "action_required"

    # 3. Logged In
    status_panel.update_for_booking_state(BookingState.USER_LOGGED_IN)
    assert status_panel.get_step_state(STEP_BROWSER_READY) == "completed"
    assert status_panel.get_step_state(STEP_LOGGED_IN) == "completed"

    # 4. Waiting for Tatkal
    status_panel.update_for_booking_state(BookingState.WAITING_FOR_TATKAL)
    assert status_panel.get_step_state(STEP_WAITING_FOR_TATKAL) == "active"

    # 5. Selecting Train
    status_panel.update_for_booking_state(BookingState.TRAIN_SELECTION)
    assert status_panel.get_step_state(STEP_WAITING_FOR_TATKAL) == "completed"
    assert status_panel.get_step_state(STEP_SELECTING_TRAIN) == "active"

    # 6. Passenger Review
    status_panel.update_for_booking_state(BookingState.REVIEW)
    assert status_panel.get_step_state(STEP_SELECTING_TRAIN) == "completed"
    assert status_panel.get_step_state(STEP_PASSENGER_REVIEW) == "active"

    # 7. CAPTCHA Required
    status_panel.update_for_booking_state(BookingState.CAPTCHA_REQUIRED)
    assert status_panel.get_step_state(STEP_PASSENGER_REVIEW) == "completed"
    assert status_panel.get_step_state(STEP_CAPTCHA_REQUIRED) == "action_required"

    # 8. Payment Required
    status_panel.update_for_booking_state(BookingState.PAYMENT_REQUIRED)
    assert status_panel.get_step_state(STEP_CAPTCHA_REQUIRED) == "completed"
    assert status_panel.get_step_state(STEP_PAYMENT_REQUIRED) == "action_required"

    # 9. Booking Confirmation
    status_panel.update_for_booking_state(BookingState.BOOKING_CONFIRMATION)
    assert status_panel.get_step_state(STEP_PAYMENT_REQUIRED) == "completed"
    assert status_panel.get_step_state(STEP_BOOKING_SUCCESSFUL) == "active"

    # 10. Success (All completed!)
    status_panel.update_for_booking_state(BookingState.SUCCESS)
    for step_id, _ in CANONICAL_STEPS:
        assert status_panel.get_step_state(step_id) == "completed"


def test_status_panel_failure_state(status_panel):
    """Verify that a failure state flags the active step as failed."""
    status_panel.update_for_booking_state(BookingState.TRAIN_SELECTION)
    assert status_panel.get_step_state(STEP_SELECTING_TRAIN) == "active"

    status_panel.update_for_booking_state(BookingState.FAILURE, message="Train 99999 not found")
    assert status_panel.get_step_state(STEP_SELECTING_TRAIN) == "failed"
    assert "FAILED" in status_panel.get_status_text().upper()


def test_status_panel_unknown_state(status_panel):
    """Verify that an ambiguous outcome flags the confirmation step as uncertain."""
    status_panel.update_for_booking_state(BookingState.PAYMENT_REQUIRED)
    status_panel.update_for_booking_state(BookingState.UNKNOWN, message="Status uncertain")
    assert status_panel.get_step_state(STEP_BOOKING_SUCCESSFUL) == "failed"
    assert "UNCERTAIN" in status_panel.get_status_text().upper()


# ==================== MainWindow Integration Tests ====================


def test_main_window_has_status_panel(main_window):
    """Verify MainWindow integrates the StatusPanel with all 8 canonical steps."""
    assert hasattr(main_window, "status_panel")
    assert isinstance(main_window.status_panel, StatusPanel)
    assert main_window.status_label is main_window.status_panel.status_label

    for step_id, step_name in CANONICAL_STEPS:
        assert step_id in main_window.status_panel.step_labels
        lbl = main_window.status_panel.step_labels[step_id]
        assert step_name in lbl.text()


def test_main_window_open_irctc_updates_status(main_window, monkeypatch):
    """Verify clicking OPEN IRCTC updates Browser Ready step."""
    monkeypatch.setattr(main_window.browser_manager, "open_irctc", lambda **kwargs: None)
    main_window.open_irctc_btn.click()

    assert main_window.status_panel.get_step_state(STEP_BROWSER_READY) == "completed"
    assert "BROWSER READY" in main_window.status_label.text()


def test_main_window_cancel_resets_status(main_window, monkeypatch):
    """Verify clicking CANCEL resets all status steps back to pending and READY."""
    main_window.status_panel.set_step_state(STEP_BROWSER_READY, "completed")
    main_window.status_panel.set_step_state(STEP_SELECTING_TRAIN, "active")

    main_window.cancel_btn.click()
    assert main_window.status_panel.get_step_state(STEP_BROWSER_READY) == "pending"
    assert main_window.status_panel.get_step_state(STEP_SELECTING_TRAIN) == "pending"
    assert main_window.status_label.text() == "READY"


def test_main_window_state_machine_listener(main_window):
    """Verify that firing state machine transitions updates MainWindow status panel."""
    # Simulate a transition to CAPTCHA_REQUIRED
    main_window._on_state_machine_transition(
        from_state=BookingState.REVIEW,
        to_state=BookingState.CAPTCHA_REQUIRED,
        reason="Human CAPTCHA Required",
    )
    assert main_window.status_panel.get_step_state(STEP_CAPTCHA_REQUIRED) == "action_required"
    assert "CAPTCHA" in main_window.status_label.text()

    # Simulate transition to SUCCESS
    main_window._on_state_machine_transition(
        from_state=BookingState.BOOKING_CONFIRMATION,
        to_state=BookingState.SUCCESS,
        reason="Booking confirmed, PNR: 2345678901",
    )
    assert main_window.status_panel.get_step_state(STEP_BOOKING_SUCCESSFUL) == "completed"
    assert "SUCCESSFUL" in main_window.status_label.text().upper()
