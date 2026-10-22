"""Trip profile management interface and edit dialogs."""

from datetime import date
from typing import List, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import config
from database.db import Database
from models.trip import Trip, VALID_CLASSES, VALID_QUOTAS


class TripDialog(QDialog):
    """Dialog to create or edit an individual trip profile."""

    def __init__(self, parent: Optional[QWidget] = None, trip: Optional[Trip] = None) -> None:
        super().__init__(parent)
        self.trip = trip
        self.result_trip: Optional[Trip] = None
        self.setWindowTitle("Edit Trip Profile" if trip else "Add Trip Profile")
        self.setFixedSize(380, 360)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        # From
        self.from_input = QLineEdit(self)
        self.from_input.setPlaceholderText("Origin (e.g. NDLS)")
        if self.trip:
            self.from_input.setText(self.trip.from_station)
        form_layout.addRow("From Station:", self.from_input)

        # To
        self.to_input = QLineEdit(self)
        self.to_input.setPlaceholderText("Destination (e.g. LKO)")
        if self.trip:
            self.to_input.setText(self.trip.to_station)
        form_layout.addRow("To Station:", self.to_input)

        # Journey Date
        self.date_input = QDateEdit(self)
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd/MM/yyyy")
        if self.trip:
            j_date = self.trip.journey_date
            if isinstance(j_date, str):
                j_date = date.fromisoformat(j_date)
            self.date_input.setDate(QDate(j_date.year, j_date.month, j_date.day))
        else:
            self.date_input.setDate(QDate.currentDate().addDays(1))
        form_layout.addRow("Journey Date:", self.date_input)

        # Train Number
        self.train_input = QLineEdit(self)
        self.train_input.setPlaceholderText("e.g. 12424")
        if self.trip:
            self.train_input.setText(self.trip.train_number)
        form_layout.addRow("Train Number:", self.train_input)

        # Train Name (Optional)
        self.train_name_input = QLineEdit(self)
        self.train_name_input.setPlaceholderText("e.g. Rajdhani Express (Optional)")
        if self.trip:
            self.train_name_input.setText(self.trip.train_name)
        form_layout.addRow("Train Name:", self.train_name_input)

        # Class
        self.class_combo = QComboBox(self)
        for code, label in config.AVAILABLE_CLASSES:
            self.class_combo.addItem(label, code)
        if self.trip:
            idx = self.class_combo.findData(self.trip.class_code)
            if idx != -1:
                self.class_combo.setCurrentIndex(idx)
        form_layout.addRow("Class:", self.class_combo)

        # Quota
        self.quota_combo = QComboBox(self)
        for code, label in config.AVAILABLE_QUOTAS:
            self.quota_combo.addItem(label, code)
        if self.trip:
            idx = self.quota_combo.findData(self.trip.quota)
            if idx != -1:
                self.quota_combo.setCurrentIndex(idx)
        form_layout.addRow("Quota:", self.quota_combo)

        layout.addLayout(form_layout)

        # Error label
        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #D32F2F; font-size: 11px;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save", self)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_btn)

        layout.addLayout(button_row)

    def _on_save_clicked(self) -> None:
        qdate = self.date_input.date()
        py_date = date(qdate.year(), qdate.month(), qdate.day())
        trip_id = self.trip.id if self.trip else None

        try:
            t = Trip(
                from_station=self.from_input.text(),
                to_station=self.to_input.text(),
                journey_date=py_date,
                train_number=self.train_input.text(),
                train_name=self.train_name_input.text(),
                class_code=self.class_combo.currentData(),
                quota=self.quota_combo.currentData(),
                id=trip_id,
            )
            self.result_trip = t
            self.accept()
        except ValueError as exc:
            self.error_label.setText(str(exc))


class TripManagerWindow(QDialog):
    """Dialog to list, create, edit, delete, and select trip booking profiles."""

    def __init__(self, db: Database, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = db
        self.selected_trip: Optional[Trip] = None
        self.setWindowTitle("Manage Trip Profiles")
        self.resize(650, 420)
        self.setMinimumSize(580, 360)
        self._init_ui()
        self.load_trips()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        title_label = QLabel("Saved Booking Profiles", self)
        title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        header_layout.addWidget(title_label)

        self.active_status_label = QLabel("", self)
        self.active_status_label.setStyleSheet("color: #2E7D32; font-weight: 600;")
        header_layout.addStretch()
        header_layout.addWidget(self.active_status_label)
        main_layout.addLayout(header_layout)

        # Profiles Table
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Route", "Date", "Train", "Class", "Quota", "Active"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        main_layout.addWidget(self.table)

        # Action Buttons
        action_row = QHBoxLayout()

        self.add_btn = QPushButton("Add Profile", self)
        self.add_btn.clicked.connect(self._on_add_clicked)
        action_row.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Edit Profile", self)
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        action_row.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        action_row.addWidget(self.delete_btn)

        action_row.addStretch()

        self.select_active_btn = QPushButton("Select Profile", self)
        self.select_active_btn.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold;")
        self.select_active_btn.clicked.connect(self._on_select_active_clicked)
        action_row.addWidget(self.select_active_btn)

        main_layout.addLayout(action_row)

    def load_trips(self) -> None:
        """Load all trip profiles from database and populate table."""
        all_trips = self.db.list_trips()
        active_trip = self.db.get_active_trip()
        active_id = active_trip.id if active_trip else None

        if active_trip:
            self.active_status_label.setText(
                f"Active: {active_trip.from_station} → {active_trip.to_station} ({active_trip.train_number})"
            )
        else:
            self.active_status_label.setText("Active: [ None ]")

        self.table.setRowCount(len(all_trips))
        for row, trip in enumerate(all_trips):
            # Route
            route_text = f"{trip.from_station} → {trip.to_station}"
            route_item = QTableWidgetItem(route_text)
            route_item.setData(Qt.ItemDataRole.UserRole, trip)
            self.table.setItem(row, 0, route_item)

            # Date
            date_item = QTableWidgetItem(trip.journey_date_str)
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, date_item)

            # Train
            train_display = f"{trip.train_number}" + (f" ({trip.train_name})" if trip.train_name else "")
            train_item = QTableWidgetItem(train_display)
            self.table.setItem(row, 2, train_item)

            # Class
            class_item = QTableWidgetItem(trip.class_code)
            class_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, class_item)

            # Quota
            quota_item = QTableWidgetItem(trip.quota)
            quota_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, quota_item)

            # Active indicator
            is_active = (trip.id == active_id)
            active_item = QTableWidgetItem("● ACTIVE" if is_active else "")
            active_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_active:
                active_item.setForeground(Qt.GlobalColor.darkGreen)
            self.table.setItem(row, 5, active_item)

    def _get_selected_row_trip(self) -> Optional[Trip]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_add_clicked(self) -> None:
        dialog = TripDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_trip:
            new_trip = self.db.create_trip(dialog.result_trip)
            # If it's the only trip, set it active
            if len(self.db.list_trips()) == 1 and new_trip.id is not None:
                self.db.set_active_trip(new_trip.id)
            self.load_trips()

    def _on_edit_clicked(self) -> None:
        trip = self._get_selected_row_trip()
        if not trip:
            QMessageBox.information(self, "Select Profile", "Please select a trip profile to edit.")
            return

        dialog = TripDialog(self, trip=trip)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_trip:
            self.db.update_trip(dialog.result_trip)
            self.load_trips()

    def _on_delete_clicked(self) -> None:
        trip = self._get_selected_row_trip()
        if not trip or trip.id is None:
            QMessageBox.information(self, "Select Profile", "Please select a trip profile to delete.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete profile '{trip.from_station} → {trip.to_station}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            # If deleted trip was active, clear active
            active = self.db.get_active_trip()
            if active and active.id == trip.id:
                self.db.set_active_trip(None)
            self.db.delete_trip(trip.id)
            self.load_trips()

    def _on_select_active_clicked(self) -> None:
        trip = self._get_selected_row_trip()
        if not trip or trip.id is None:
            QMessageBox.information(self, "Select Profile", "Please select a profile to activate.")
            return

        self.db.set_active_trip(trip.id)
        self.selected_trip = trip
        self.accept()
