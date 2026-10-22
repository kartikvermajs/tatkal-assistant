"""Unit tests for Phase 4 Passenger Management GUI."""

import os
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QMessageBox

from database.db import Database
from models.passenger import Passenger
from ui.main_window import MainWindow
from ui.passenger_form import PassengerDialog, PassengerManagerWindow

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


# ==================== PassengerDialog Tests ====================


def test_passenger_dialog_add_valid(qapp):
    dialog = PassengerDialog()
    dialog.name_input.setText("Amit Sharma")
    dialog.age_input.setValue(28)

    idx_m = dialog.gender_combo.findData("M")
    dialog.gender_combo.setCurrentIndex(idx_m)

    idx_lb = dialog.berth_combo.findData("LB")
    dialog.berth_combo.setCurrentIndex(idx_lb)

    dialog.save_btn.click()
    assert dialog.result_passenger is not None
    assert dialog.result_passenger.name == "Amit Sharma"
    assert dialog.result_passenger.age == 28
    assert dialog.result_passenger.gender == "M"
    assert dialog.result_passenger.berth_preference == "LB"
    dialog.close()


def test_passenger_dialog_validation_error(qapp):
    dialog = PassengerDialog()
    # Invalid: empty name
    dialog.name_input.setText("   ")
    dialog.save_btn.click()
    assert dialog.result_passenger is None
    assert "cannot be empty" in dialog.error_label.text()
    dialog.close()


def test_passenger_dialog_edit_mode(qapp):
    p = Passenger(name="Sunita Rao", age=45, gender="F", berth_preference="SL", id=42)
    dialog = PassengerDialog(passenger=p)

    assert dialog.name_input.text() == "Sunita Rao"
    assert dialog.age_input.value() == 45
    assert dialog.gender_combo.currentData() == "F"
    assert dialog.berth_combo.currentData() == "SL"

    # Edit fields
    dialog.age_input.setValue(46)
    dialog.save_btn.click()
    assert dialog.result_passenger is not None
    assert dialog.result_passenger.id == 42
    assert dialog.result_passenger.age == 46
    dialog.close()


# ==================== PassengerManagerWindow Tests ====================


def test_passenger_manager_window_display_and_selection(qapp, db):
    p1 = Passenger(name="Passenger One", age=25, gender="M", berth_preference="LB")
    p2 = Passenger(name="Passenger Two", age=30, gender="F", berth_preference="UB")
    db.create_passenger(p1)
    db.create_passenger(p2)

    manager = PassengerManagerWindow(db)
    assert manager.table.rowCount() == 2

    # Verify rows
    assert manager.table.item(0, 1).text() == "Passenger One"
    assert manager.table.item(1, 1).text() == "Passenger Two"

    # Select p1 checkbox
    cb1 = manager._get_checkbox_for_row(0)
    assert cb1 is not None
    cb1.setChecked(True)

    selected_ids = manager.get_selected_ids()
    assert selected_ids == [p1.id]
    assert "Selected: 1 / 4" in manager.selection_count_label.text()

    # Confirm selection
    manager.confirm_btn.click()
    assert db.get_selected_passengers()[0].id == p1.id
    manager.close()


def test_passenger_manager_max_four_limit(qapp, db, monkeypatch):
    # Add 5 passengers
    for i in range(5):
        db.create_passenger(Passenger(name=f"User {i+1}", age=20 + i, gender="M"))

    manager = PassengerManagerWindow(db)
    # Check all 5
    for row in range(5):
        cb = manager._get_checkbox_for_row(row)
        assert cb is not None
        cb.setChecked(True)

    assert len(manager.get_selected_ids()) == 5
    assert "Selected: 5 / 4" in manager.selection_count_label.text()

    # Attempt to confirm: should trigger warning and not change database
    warning_called = False

    def mock_warning(*args, **kwargs):
        nonlocal warning_called
        warning_called = True

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)
    manager.confirm_btn.click()
    assert warning_called is True
    # Database selection should not have updated to 5
    assert len(db.get_selected_passengers()) == 0
    manager.close()


def test_main_window_passenger_integration(qapp, db):
    p1 = Passenger(name="Kavita", age=27, gender="F", berth_preference="LB")
    db.create_passenger(p1)
    db.set_selected_passengers([p1.id])

    window = MainWindow(db=db)
    assert "[ 1: Kavita (27/F) ]" in window.selected_passengers_label.text()
    assert len(window.selected_passengers) == 1

    # Prepare booking requires journey info AND passenger
    window.from_input.setText("NDLS")
    window.to_input.setText("CNB")
    window.train_number_input.setText("12004")
    window.prepare_booking_btn.click()
    assert "PREPARED: 1 passenger(s) ready" in window.status_label.text()
    window.close()
