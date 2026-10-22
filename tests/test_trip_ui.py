"""Unit tests for Phase 5 Trip Management GUI and persistence."""

from datetime import date, timedelta
import os
import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from database.db import Database
from models.trip import Trip
from ui.main_window import MainWindow
from ui.trip_form import TripDialog, TripManagerWindow

# Ensure headless execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def db():
    return Database(":memory:")


# ==================== TripDialog Tests ====================


def test_trip_dialog_add_valid(qapp):
    tomorrow = date.today() + timedelta(days=2)
    dialog = TripDialog()
    dialog.from_input.setText("NDLS")
    dialog.to_input.setText("LKO")
    dialog.date_input.setDate(QDate(tomorrow.year, tomorrow.month, tomorrow.day))
    dialog.train_input.setText("12424")

    idx_3a = dialog.class_combo.findData("3A")
    dialog.class_combo.setCurrentIndex(idx_3a)

    dialog.save_btn.click()
    assert dialog.result_trip is not None
    assert dialog.result_trip.from_station == "NDLS"
    assert dialog.result_trip.to_station == "LKO"
    assert dialog.result_trip.journey_date == tomorrow
    assert dialog.result_trip.train_number == "12424"
    assert dialog.result_trip.class_code == "3A"
    dialog.close()


def test_trip_dialog_validation_error(qapp):
    dialog = TripDialog()
    # Same origin and destination
    dialog.from_input.setText("NDLS")
    dialog.to_input.setText("NDLS")
    dialog.train_input.setText("12004")
    dialog.save_btn.click()

    assert dialog.result_trip is None
    assert "cannot be the same" in dialog.error_label.text()
    dialog.close()


def test_trip_dialog_edit_mode(qapp):
    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(
        from_station="NDLS",
        to_station="CNB",
        journey_date=tomorrow,
        train_number="12004",
        class_code="CC",
        id=7,
    )
    dialog = TripDialog(trip=trip)

    assert dialog.from_input.text() == "NDLS"
    assert dialog.to_input.text() == "CNB"
    assert dialog.train_input.text() == "12004"
    assert dialog.class_combo.currentData() == "CC"

    dialog.train_input.setText("12002")
    dialog.save_btn.click()

    assert dialog.result_trip is not None
    assert dialog.result_trip.id == 7
    assert dialog.result_trip.train_number == "12002"
    dialog.close()


# ==================== TripManagerWindow Tests ====================


def test_trip_manager_listing_and_selection(qapp, db):
    tomorrow = date.today() + timedelta(days=1)
    t1 = Trip(from_station="NDLS", to_station="CNB", journey_date=tomorrow, train_number="12004")
    t2 = Trip(from_station="NDLS", to_station="LKO", journey_date=tomorrow, train_number="12424")
    db.create_trip(t1)
    db.create_trip(t2)

    manager = TripManagerWindow(db)
    assert manager.table.rowCount() == 2

    # Select row 0 (which is t2 because ordered by id desc)
    manager.table.selectRow(0)
    manager.select_active_btn.click()

    active = db.get_active_trip()
    assert active is not None
    assert active.id == t2.id
    manager.close()


# ==================== MainWindow Trip Integration & Persistence ====================


def test_main_window_save_and_load_profile(qapp, db):
    window = MainWindow(db=db)
    assert window.active_profile_label.text() == "[ None ]"

    tomorrow = date.today() + timedelta(days=2)
    window.from_input.setText("NDLS")
    window.to_input.setText("BSB")
    window.journey_date_input.setDate(QDate(tomorrow.year, tomorrow.month, tomorrow.day))
    window.train_number_input.setText("22436")

    idx_ec = window.class_combo.findData("EC")
    window.class_combo.setCurrentIndex(idx_ec)

    # Click Save Profile
    window.save_profile_btn.click()
    assert "PROFILE SAVED & ACTIVATED" in window.status_label.text()
    assert "NDLS → BSB" in window.active_profile_label.text()

    # Reopen MainWindow with same DB to test persistence
    window2 = MainWindow(db=db)
    assert "NDLS → BSB (22436)" in window2.active_profile_label.text()
    assert window2.from_input.text() == "NDLS"
    assert window2.to_input.text() == "BSB"
    assert window2.train_number_input.text() == "22436"
    assert window2.class_combo.currentData() == "EC"
    window.close()
    window2.close()
