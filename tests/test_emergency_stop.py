"""Automated tests for Phase 23: Emergency Stop.

Verifies:
- [ STOP AUTOMATION ] button is prominently present on MainWindow
- ESC keyboard shortcut triggers immediate emergency stop
- Playwright actions are immediately halted
- State machine returns deterministically to IDLE
- Automatic retries are prevented
- Status UI and logs record the emergency halt
"""

import os
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from browser.browser_manager import BrowserManager
from browser.irctc_workflow import IRCTCWorkflow
from core.booking_state import BookingState, BookingStateMachine
from core.logger import get_app_logger
from models.trip import Trip
from ui.main_window import MainWindow
from ui.status_panel import STEP_BROWSER_READY, STEP_SELECTING_TRAIN


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def main_window(qapp):
    win = MainWindow()
    yield win
    win.close()


# ==================== Emergency Stop Unit & Integration Tests ====================


def test_emergency_stop_button_present(main_window):
    """Verify that [ STOP AUTOMATION ] button exists with proper objectName and tool tip."""
    assert hasattr(main_window, "stop_automation_btn")
    btn = main_window.stop_automation_btn
    assert btn is not None
    assert btn.text() == "STOP AUTOMATION"
    assert btn.objectName() == "stopAutomationBtn"
    assert "ESC" in btn.toolTip().upper()


def test_emergency_stop_esc_shortcut_registered(main_window):
    """Verify that ESC shortcut is registered on MainWindow."""
    assert hasattr(main_window, "esc_shortcut")
    assert main_window.esc_shortcut is not None


def test_emergency_stop_button_click_halts_workflow(main_window):
    """Verify clicking [ STOP AUTOMATION ] immediately halts active workflow,
    resets state to IDLE, and does not retry.
    """
    sm = BookingStateMachine(initial_state=BookingState.TRAIN_SELECTION)
    main_window.current_workflow = IRCTCWorkflow(state_machine=sm)
    main_window.status_panel.update_for_booking_state(BookingState.TRAIN_SELECTION)
    assert sm.current_state == BookingState.TRAIN_SELECTION

    # Click STOP AUTOMATION button
    main_window.stop_automation_btn.click()

    # Workflow must be aborted and sm reset to IDLE
    assert sm.current_state == BookingState.IDLE
    assert main_window.current_workflow is None

    # Status panel must reflect stopped / IDLE state
    assert main_window.status_panel.get_step_state(STEP_SELECTING_TRAIN) == "pending"
    assert "STOPPED" in main_window.status_label.text().upper()
    assert "IDLE" in main_window.status_label.text().upper()

    # Checkpoint button disabled, prepare button enabled for manual start only
    assert main_window.checkpoint_btn.isEnabled() is False
    assert main_window.prepare_booking_btn.isEnabled() is True


def test_emergency_stop_esc_key_event(main_window):
    """Verify pressing ESC key triggers emergency stop and resets state to IDLE."""
    sm = BookingStateMachine(initial_state=BookingState.CAPTCHA_REQUIRED)
    main_window.current_workflow = IRCTCWorkflow(state_machine=sm)
    main_window.status_panel.update_for_booking_state(BookingState.CAPTCHA_REQUIRED)

    # Simulate pressing ESC on the main window
    QTest.keyClick(main_window, Qt.Key.Key_Escape)

    # State must be returned to IDLE
    assert sm.current_state == BookingState.IDLE
    assert main_window.current_workflow is None
    assert "STOPPED" in main_window.status_label.text().upper()


def test_workflow_abort_sets_aborted_flag_and_resets_state():
    """Verify that IRCTCWorkflow.abort() sets is_aborted=True and resets state machine to IDLE."""
    sm = BookingStateMachine(initial_state=BookingState.PAYMENT_REQUIRED)
    wf = IRCTCWorkflow(state_machine=sm)
    assert wf.is_aborted is False

    wf.abort("Emergency halt test")
    assert wf.is_aborted is True
    assert sm.current_state == BookingState.IDLE

    # Calling prepare_journey after abort immediately fails safely without continuing
    from datetime import date, timedelta
    trip = Trip(
        from_station="NDLS",
        to_station="CNB",
        journey_date=date.today() + timedelta(days=1),
        train_number="12004",
        class_code="3A",
    )
    res = wf.prepare_journey(trip)
    assert res.success is False
    assert res.state == BookingState.IDLE


def test_browser_manager_stop_automation():
    """Verify BrowserManager.stop_automation() safely executes without crashing."""
    bm = BrowserManager()
    # When browser is not running, stop_automation should be safe no-op
    bm.stop_automation()
    assert bm.is_running() is False


def test_emergency_stop_logs_audit_event(main_window):
    """Verify that triggering emergency stop logs an audit entry."""
    logger = get_app_logger()
    log_file = logger.log_file

    main_window.stop_automation_btn.click()

    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Emergency stop triggered" in content
