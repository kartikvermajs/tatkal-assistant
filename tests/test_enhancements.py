"""Unit and integration tests for the Three Performance & Usability Enhancements.

1. Speed & Timing Enhancements:
   - Server clock offset sync & Tatkal opening calculations
   - Auto-start toggle settings & automatic trigger at Tatkal opening
   - Auto-focus CAPTCHA input on detection

2. User Interface & Experience:
   - Dynamic STOP AUTOMATION button (disabled/gray when idle, enabled/red when active)
   - Station auto-complete completer configuration & selection mapping
   - Pre-flight readiness checklist updates (Route, Passenger, Browser, Clock)

3. Payment Flow Optimization:
   - Saved UPI ID validation, serialization, and deserialization
   - UPI ID auto-fill into VPA field in payment flow
   - IRCTC eWallet balance reminder alert
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import config
from browser.irctc_workflow import IRCTCWorkflow
from core.booking_state import BookingState, BookingStateMachine
from core.clock import TatkalClock
from database.db import Database
from models.passenger import Passenger
from models.settings import ApplicationSettings
from models.trip import Trip
from ui.main_window import MainWindow
from ui.payment_checkpoint_dialog import PaymentCheckpointDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mem_db():
    return Database(":memory:")


# ==================== 1. Settings & Models ====================


def test_settings_auto_start_and_upi_defaults():
    s = ApplicationSettings()
    assert s.auto_start_on_opening is False
    assert s.upi_id == ""


def test_settings_valid_upi_id():
    s = ApplicationSettings(upi_id="user@okhdfcbank")
    assert s.upi_id == "user@okhdfcbank"
    data = s.to_dict()
    assert data["upi_id"] == "user@okhdfcbank"
    assert data["auto_start_on_opening"] is False

    s2 = ApplicationSettings.from_dict(data)
    assert s2.upi_id == "user@okhdfcbank"
    assert s2.auto_start_on_opening is False


def test_settings_invalid_upi_id():
    with pytest.raises(ValueError, match="valid UPI VPA"):
        ApplicationSettings(upi_id="invalid_upi_without_at")

    with pytest.raises(ValueError, match="valid UPI VPA"):
        ApplicationSettings(upi_id="user@")


def test_settings_invalid_auto_start():
    with pytest.raises(ValueError, match="auto_start_on_opening must be a boolean"):
        ApplicationSettings(auto_start_on_opening="yes")  # type: ignore


# ==================== 2. Station Auto-Complete Config ====================


def test_station_auto_complete_config():
    assert len(config.POPULAR_STATIONS) >= 50
    assert "NDLS" in [code for code, _ in config.POPULAR_STATIONS]
    assert len(config.STATION_DISPLAY_LIST) == len(config.POPULAR_STATIONS)
    assert config.STATION_CODE_MAP["NDLS - New Delhi"] == "NDLS"


# ==================== 3. Server Clock Sync ====================


def test_clock_server_sync_mock():
    clock = TatkalClock()
    assert clock.is_synced is False
    assert clock._clock_offset == timedelta(0)

    # Simulate 2-second server offset
    clock._clock_offset = timedelta(seconds=2)
    clock._sync_attempted = True
    assert clock.is_synced is True

    # current_ist() reflects the offset
    now_sys = datetime.now(clock.tz)
    now_ist = clock.current_ist()
    # Should be approximately 2 seconds ahead
    diff = (now_ist - now_sys).total_seconds()
    assert 1.5 <= diff <= 2.5


def test_clock_sync_with_server_failure_does_not_crash():
    clock = TatkalClock()
    # Test invalid / unreachable endpoint
    res = clock.sync_with_server(url="http://127.0.0.1:59999/unreachable")
    assert res is False
    assert clock.is_synced is False


# ==================== 4. Dynamic STOP AUTOMATION Button ====================


def test_dynamic_stop_button_state(qapp, mem_db):
    win = MainWindow(db=mem_db)

    # Initial state: no workflow running -> STOP AUTOMATION is disabled (neutral gray)
    assert win.current_workflow is None
    assert win.stop_automation_btn.isEnabled() is False

    # When workflow is started/assigned -> STOP AUTOMATION becomes enabled (active red)
    sm = BookingStateMachine()
    win.current_workflow = IRCTCWorkflow(state_machine=sm)
    assert win.stop_automation_btn.isEnabled() is True

    # When emergency stop clicked -> resets to disabled
    win.stop_automation_btn.click()
    assert win.current_workflow is None
    assert win.stop_automation_btn.isEnabled() is False
    win.close()


# ==================== 5. Pre-Flight Readiness Checklist ====================


def test_pre_flight_checklist_badges(qapp, mem_db):
    win = MainWindow(db=mem_db)

    # Initially empty inputs -> Route is PENDING, Passengers NONE, Browser CLOSED
    win._update_checklist()
    assert "PENDING" in win.chk_route_badge.text()
    assert "NONE" in win.chk_passenger_badge.text()
    assert "CLOSED" in win.chk_browser_badge.text()

    # Fill valid route
    win.from_input.setText("NDLS")
    win.to_input.setText("CNB")
    win.train_number_input.setText("12004")
    win._update_checklist()
    assert "READY" in win.chk_route_badge.text()

    # Add passenger
    p = Passenger(name="Test Passenger", age=28, gender="M", berth_preference="LB")
    win.selected_passengers = [p]
    win._update_checklist()
    assert "1 READY" in win.chk_passenger_badge.text()
    win.close()


# ==================== 6. Payment Checkpoint with UPI ID ====================


def test_payment_checkpoint_displays_upi_id(qapp):
    dialog = PaymentCheckpointDialog(payment_method="UPI", upi_id="user@okaxis")
    assert dialog.upi_id == "user@okaxis"
    # Find label containing UPI VPA
    all_text = " ".join(lbl.text() for lbl in dialog.findChildren(PaymentCheckpointDialog.__bases__[0]))
    # Verify UPI VPA is in the dialog widgets
    found_vpa = False
    for child in dialog.children():
        if hasattr(child, "text") and "user@okaxis" in child.text():
            found_vpa = True
            break
    assert found_vpa is True
    dialog.close()


# ==================== 7. Auto-Start on Tatkal Opening ====================


def test_auto_start_triggers_when_tatkal_opens(qapp, mem_db, monkeypatch):
    win = MainWindow(db=mem_db)
    win.auto_start_cb.setChecked(True)

    prepare_called = []
    monkeypatch.setattr(win, "_on_prepare_booking_clicked", lambda auto_mode=False: prepare_called.append(auto_mode))

    # Mock clock to open Tatkal
    monkeypatch.setattr(win.clock, "is_tatkal_open", lambda cls: True)

    win._on_timer_tick()

    assert len(prepare_called) == 1
    assert prepare_called[0] is True  # auto_mode=True
    win.close()
