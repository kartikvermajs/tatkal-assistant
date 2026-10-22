"""Unit tests for Phase 7 Tatkal Countdown and Notification System."""

from datetime import datetime
import os
import pytest
from PySide6.QtWidgets import QApplication

from core.clock import IST_TZ, TatkalClock
from database.db import Database
from services.notification_service import NotificationService
from ui.main_window import MainWindow

# Ensure headless execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"


class MockNotificationService(NotificationService):
    """Mock notification service to inspect alert triggers during testing."""

    def __init__(self) -> None:
        super().__init__()
        self.sound_played = False
        self.alert_triggered = False
        self.last_sound_arg = None
        self.last_visual_arg = None

    def play_sound(self) -> None:
        self.sound_played = True

    def trigger_opening_alert(self, parent_widget=None, sound=True, visual=True) -> None:
        self.alert_triggered = True
        self.last_sound_arg = sound
        self.last_visual_arg = visual
        if sound:
            self.play_sound()


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def test_env():
    db = Database(":memory:")
    clock = TatkalClock()
    notifier = MockNotificationService()
    return db, clock, notifier


def test_countdown_ticking_before_opening(qapp, test_env):
    db, clock, notifier = test_env
    # 2 seconds before Non-AC opening
    before_dt = datetime(2026, 10, 16, 10, 59, 58, tzinfo=IST_TZ)
    clock.set_mock_time(before_dt)

    window = MainWindow(db=db, clock=clock, notification_service=notifier)

    # Initial tick
    window._on_timer_tick()
    assert window.current_ist_label.text() == "10:59:58"
    assert window.opening_time_label.text() == "11:00:00"
    assert window.remaining_time_label.text() == "00:00:02"
    assert window.status_label.text() != "TATKAL OPEN"
    assert notifier.alert_triggered is False
    window.close()


def test_countdown_triggers_tatkal_open_alert(qapp, test_env):
    db, clock, notifier = test_env
    # Before opening
    clock.set_mock_time(datetime(2026, 10, 16, 10, 59, 59, tzinfo=IST_TZ))
    window = MainWindow(db=db, clock=clock, notification_service=notifier)
    window._on_timer_tick()
    assert notifier.alert_triggered is False

    # Advance clock to exactly opening
    clock.set_mock_time(datetime(2026, 10, 16, 11, 0, 0, tzinfo=IST_TZ))
    window._on_timer_tick()

    assert window.status_label.text() == "TATKAL OPEN"
    assert notifier.alert_triggered is True
    assert notifier.sound_played is True
    assert window.remaining_time_label.text() == "00:00:00"
    window.close()


def test_notification_toggle_and_persistence(qapp, test_env):
    db, clock, notifier = test_env
    window = MainWindow(db=db, clock=clock, notification_service=notifier)

    assert window.sound_alert_cb.isChecked() is True
    assert window.visual_alert_cb.isChecked() is True

    # Disable sound alert
    window.sound_alert_cb.setChecked(False)

    # Trigger opening alert with sound disabled
    clock.set_mock_time(datetime(2026, 10, 16, 11, 0, 0, tzinfo=IST_TZ))
    window._on_timer_tick()

    assert notifier.last_sound_arg is False
    assert notifier.last_visual_arg is True

    # Verify settings persisted in SQLite
    reloaded_settings = db.load_settings()
    assert reloaded_settings.sound_notification is False
    assert reloaded_settings.visual_notification is True
    window.close()


def test_ac_tatkal_opening_countdown(qapp, test_env):
    db, clock, notifier = test_env
    # 3 seconds before AC opening (10:00:00)
    clock.set_mock_time(datetime(2026, 10, 16, 9, 59, 57, tzinfo=IST_TZ))

    window = MainWindow(db=db, clock=clock, notification_service=notifier)
    idx_3a = window.class_combo.findData("3A")
    window.class_combo.setCurrentIndex(idx_3a)

    window._on_timer_tick()
    assert window.opening_time_label.text() == "10:00:00"
    assert window.remaining_time_label.text() == "00:00:03"
    assert window.status_label.text() != "TATKAL OPEN"

    # Advance to 10:00:00
    clock.set_mock_time(datetime(2026, 10, 16, 10, 0, 0, tzinfo=IST_TZ))
    window._on_timer_tick()
    assert window.status_label.text() == "TATKAL OPEN"
    assert notifier.alert_triggered is True
    window.close()
