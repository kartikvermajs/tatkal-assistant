"""Automated tests for Anti-Logout Enhancements:
1. Background Session Keep-Alive Heartbeat (runs every 25s in USER_LOGGED_IN or WAITING_FOR_TATKAL)
2. Pre-Tatkal Login Alarm at T - 90s
3. Session Expiry Fast-Recovery Handler (auto-reopens login modal on https://www.irctc.co.in/nget/train-search)
"""

from datetime import datetime, timedelta, timezone
import time
from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication

from browser.irctc_workflow import IRCTCWorkflow
from core.booking_state import BookingState, BookingStateMachine
from core.clock import TatkalClock
from database.db import Database
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mem_db():
    return Database(":memory:")


# ==================== 1. Keep-Alive Heartbeat Tests ====================


def test_keep_alive_heartbeat_eligible_states():
    """Verify that keep-alive pings only trigger in USER_LOGGED_IN or WAITING_FOR_TATKAL states."""
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.locator.return_value.count.return_value = 0
    mock_page.locator.return_value.first.is_visible.return_value = False

    sm = BookingStateMachine()
    wf = IRCTCWorkflow(page=mock_page, state_machine=sm)

    # In IDLE: keep-alive should NOT trigger unless forced
    assert sm.current_state == BookingState.IDLE
    assert wf.check_and_send_keep_alive(force=False) is False

    # In USER_LOGGED_IN: keep-alive should trigger
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGIN_REQUIRED)
    sm.transition_to(BookingState.USER_LOGGED_IN)
    assert wf.check_and_send_keep_alive(force=True) is True
    assert wf.last_keep_alive_time > 0
    mock_page.evaluate.assert_called()

    # In WAITING_FOR_TATKAL: keep-alive should trigger
    sm.transition_to(BookingState.WAITING_FOR_TATKAL)
    assert wf.check_and_send_keep_alive(force=True) is True


def test_keep_alive_interval_timing():
    """Verify that keep-alive honors the 25-second interval."""
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.locator.return_value.count.return_value = 0
    mock_page.locator.return_value.first.is_visible.return_value = False

    sm = BookingStateMachine()
    wf = IRCTCWorkflow(page=mock_page, state_machine=sm)
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGIN_REQUIRED)
    sm.transition_to(BookingState.USER_LOGGED_IN)

    # First ping at t = 0
    wf.last_keep_alive_time = time.time()
    # Immediate check (0 seconds elapsed < 25s) -> should return False
    assert wf.check_and_send_keep_alive(force=False) is False

    # Simulate 26 seconds elapsed
    wf.last_keep_alive_time = time.time() - 26.0
    assert wf.check_and_send_keep_alive(force=False) is True


# ==================== 2. Session Expiry Fast-Recovery Tests ====================


def test_session_expiry_fast_recovery_handler():
    """Verify handle_session_expired dismisses alert, clicks login, and sets USER_LOGIN_REQUIRED."""
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False

    # Mock dismiss button and login button
    dismiss_button = MagicMock()
    login_button = MagicMock()
    username_field = MagicMock()

    def locator_mock(selector, **kwargs):
        loc = MagicMock()
        if "OK" in selector or "Close" in selector:
            loc.count.return_value = 1
            loc.first = dismiss_button
        elif "LOGIN" in selector or "login-link" in selector:
            loc.count.return_value = 1
            loc.first = login_button
        elif "User Name" in selector or "userId" in selector:
            loc.count.return_value = 1
            loc.first = username_field
            loc.first.is_visible.return_value = True
        else:
            loc.count.return_value = 0
            loc.first.is_visible.return_value = False
        return loc

    mock_page.locator.side_effect = locator_mock

    sm = BookingStateMachine()
    sm.transition_to(BookingState.BROWSER_READY)
    sm.transition_to(BookingState.USER_LOGIN_REQUIRED)
    sm.transition_to(BookingState.USER_LOGGED_IN)

    wf = IRCTCWorkflow(page=mock_page, state_machine=sm)
    assert wf.handle_session_expired() is True

    # Check alert was dismissed
    dismiss_button.click.assert_called()
    # Check state transitioned back to USER_LOGIN_REQUIRED
    assert sm.current_state == BookingState.USER_LOGIN_REQUIRED


# ==================== 3. Pre-Tatkal Login Alarm (T - 90s) Tests ====================


def test_pre_tatkal_login_alarm_fires_at_t_minus_90s(qapp, mem_db, monkeypatch):
    """Verify that the login alarm fires when remaining seconds <= 90s."""
    win = MainWindow(db=mem_db)

    # Mock TatkalClock to return 80 seconds remaining until Tatkal opening
    now_ist = datetime(2026, 10, 22, 10, 58, 40, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    open_dt = datetime(2026, 10, 22, 11, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    monkeypatch.setattr(win.clock, "current_ist", lambda: now_ist)
    monkeypatch.setattr(win.clock, "get_tatkal_opening_datetime", lambda cls, reference_time=None: open_dt)
    monkeypatch.setattr(win.clock, "seconds_until", lambda target, reference_time=None: 80.0)
    monkeypatch.setattr(win.clock, "is_tatkal_open", lambda cls: False)

    # Initial state
    assert win._login_alarm_fired is False

    win._on_timer_tick()

    # Alarm should have fired
    assert win._login_alarm_fired is True
    assert "T - 90s" in win.status_label.text()

    # Second tick within 90s: should not fire alarm again
    win._on_timer_tick()
    assert win._login_alarm_fired is True

    win.close()
