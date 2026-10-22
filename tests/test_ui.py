"""Tests for Phase 1 Desktop Application UI."""

import os
import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

# Ensure offscreen rendering for headless testing environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_main_window_initialization(qapp):
    from ui.main_window import MainWindow

    window = MainWindow()
    assert window.windowTitle() == "Tatkal Assistant"
    assert window.from_input.text() == ""
    assert window.to_input.text() == ""
    assert window.train_number_input.text() == ""
    assert window.journey_date_input.date() >= QDate.currentDate()
    assert window.class_combo.currentData() == "SL"
    assert window.quota_combo.currentData() == "TATKAL"
    assert window.selected_passengers_label.text() == "[ None ]"
    import re
    assert re.match(r"^\d{2}:\d{2}:\d{2}$", window.current_ist_label.text())
    assert window.opening_time_label.text() == "11:00:00"
    assert re.match(r"^\d{2}:\d{2}:\d{2}$", window.remaining_time_label.text())
    assert window.status_label.text() == "READY"
    window.close()


def test_journey_inputs(qapp):
    from ui.main_window import MainWindow

    window = MainWindow()
    window.from_input.setText("NDLS")
    window.to_input.setText("CNB")
    window.train_number_input.setText("12004")

    assert window.from_input.text() == "NDLS"
    assert window.to_input.text() == "CNB"
    assert window.train_number_input.text() == "12004"

    # Select another class (e.g. 3A)
    idx_3a = window.class_combo.findData("3A")
    assert idx_3a != -1
    window.class_combo.setCurrentIndex(idx_3a)
    assert window.class_combo.currentData() == "3A"

    # Select Premium Tatkal
    idx_pt = window.quota_combo.findData("PREMIUM TATKAL")
    assert idx_pt != -1
    window.quota_combo.setCurrentIndex(idx_pt)
    assert window.quota_combo.currentData() == "PREMIUM TATKAL"
    window.close()


def test_button_clicks_and_status(qapp, monkeypatch):
    from models.passenger import Passenger
    from ui.booking_review_dialog import BookingReviewDialog
    from ui.main_window import MainWindow
    from ui.passenger_form import PassengerManagerWindow

    # Prevent modal dialogs from blocking test
    monkeypatch.setattr(PassengerManagerWindow, "exec", lambda self: PassengerManagerWindow.DialogCode.Accepted)
    monkeypatch.setattr(BookingReviewDialog, "exec", lambda self: BookingReviewDialog.DialogCode.Accepted)

    window = MainWindow()

    # Manage passengers click
    window.manage_passengers_btn.click()
    assert "PASSENGER" in window.status_label.text()

    # Open IRCTC click (mock open_irctc to avoid launching browser during UI button test)
    monkeypatch.setattr(window.browser_manager, "open_irctc", lambda **kwargs: None)
    window.open_irctc_btn.click()
    assert "BROWSER READY" in window.status_label.text()

    # Prepare booking without inputs
    window.prepare_booking_btn.click()
    assert "PENDING" in window.status_label.text()

    # Prepare booking with journey inputs but no passenger
    window.from_input.setText("NDLS")
    window.to_input.setText("LKO")
    window.train_number_input.setText("12424")
    window.prepare_booking_btn.click()
    assert "PENDING" in window.status_label.text()

    # With passenger selected
    window.selected_passengers = [Passenger(name="Test User", age=30, gender="M")]
    window.prepare_booking_btn.click()
    assert "PREPARED" in window.status_label.text()

    # Cancel click resets
    window.cancel_btn.click()
    assert window.status_label.text() == "READY"
    window.close()
