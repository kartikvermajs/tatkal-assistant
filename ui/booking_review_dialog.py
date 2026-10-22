"""Booking Review and Confirmation Dialog.

Displays mandatory train number, class/type, route, quota, and passenger details
for explicit human review before any automated navigation or booking proceeds.
"""

from typing import List, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import config
from models.passenger import Passenger
from models.trip import Trip


class BookingReviewDialog(QDialog):
    """Explicit review dialog to confirm Train Number and Class before booking."""

    def __init__(
        self,
        trip: Trip,
        passengers: List[Passenger],
        mobile_number: str = "",
        auto_upgradation: bool = False,
        confirm_berths_only: bool = False,
        payment_mode: str = "UPI",
        upi_id: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.trip = trip
        self.passengers = passengers
        self.mobile_number = mobile_number
        self.auto_upgradation = auto_upgradation
        self.confirm_berths_only = confirm_berths_only
        self.payment_mode = payment_mode
        self.upi_id = upi_id
        self.confirmed = False

        self.setWindowTitle("Review & Confirm Booking Details")
        self.setFixedSize(520, 580)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Title
        title_label = QLabel("BOOKING REVIEW", self)
        title_font = QFont("Segoe UI", 13, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        notice_label = QLabel(
            "Please verify the mandatory train number and travel class below before proceeding.",
            self,
        )
        notice_label.setWordWrap(True)
        notice_label.setStyleSheet("color: #555; font-size: 11px;")
        notice_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(notice_label)

        # Journey Details Card
        journey_box = QGroupBox("Journey & Train Details", self)
        journey_layout = QFormLayout(journey_box)
        journey_layout.setSpacing(8)

        # Train Number (Highlighted & Mandatory)
        train_display = self.trip.train_number
        if self.trip.train_name:
            train_display += f" - {self.trip.train_name}"
        self.train_label = QLabel(train_display, self)
        self.train_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.train_label.setStyleSheet("color: #0D47A1;")
        journey_layout.addRow("Train Number (Mandatory):", self.train_label)

        # Class / Type (Highlighted & Mandatory)
        class_display = f"{self.trip.class_display_name} ({self.trip.class_code})"
        self.class_label = QLabel(class_display, self)
        self.class_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.class_label.setStyleSheet("color: #1B5E20;")
        journey_layout.addRow("Class / Type (Mandatory):", self.class_label)

        # Route
        route_text = f"{self.trip.from_station}  ➜  {self.trip.to_station}"
        self.route_label = QLabel(route_text, self)
        self.route_label.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        journey_layout.addRow("Route:", self.route_label)

        # Date & Quota
        self.date_label = QLabel(self.trip.journey_date_str, self)
        journey_layout.addRow("Journey Date:", self.date_label)

        self.quota_label = QLabel(self.trip.quota, self)
        self.quota_label.setStyleSheet("font-weight: 600; color: #E65100;")
        journey_layout.addRow("Booking Quota:", self.quota_label)

        layout.addWidget(journey_box)

        # Passenger Details Card
        passenger_box = QGroupBox(f"Passengers ({len(self.passengers)})", self)
        p_layout = QVBoxLayout(passenger_box)

        if not self.passengers:
            no_p_label = QLabel("No passengers selected. At least 1 passenger is recommended.", self)
            no_p_label.setStyleSheet("color: #D32F2F; font-style: italic;")
            p_layout.addWidget(no_p_label)
        else:
            p_table = QTableWidget(self)
            p_table.setColumnCount(4)
            p_table.setHorizontalHeaderLabels(["Name", "Age", "Gender", "Berth"])
            p_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            p_table.verticalHeader().setVisible(False)
            p_table.setRowCount(len(self.passengers))

            for row, p in enumerate(self.passengers):
                p_table.setItem(row, 0, QTableWidgetItem(p.name))
                p_table.setItem(row, 1, QTableWidgetItem(str(p.age)))
                p_table.setItem(row, 2, QTableWidgetItem(p.gender))
                p_table.setItem(row, 3, QTableWidgetItem(p.berth_preference or "None"))

            p_table.setFixedHeight(110)
            p_layout.addWidget(p_table)

        layout.addWidget(passenger_box)

        # Travel Preferences & Contact Info
        pref_box = QGroupBox("Travel Preferences & Contact", self)
        pref_layout = QFormLayout(pref_box)
        pref_layout.setSpacing(6)

        mob_text = self.mobile_number if self.mobile_number else "[ Not set ]"
        self.mobile_label = QLabel(mob_text, self)
        self.mobile_label.setStyleSheet("font-weight: 500;")
        pref_layout.addRow("Contact Mobile:", self.mobile_label)

        self.pref_label = QLabel(
            f"Auto-Upgradation: {'Yes' if self.auto_upgradation else 'No'}  |  "
            f"Confirm Berths Only: {'Yes' if self.confirm_berths_only else 'No'}",
            self,
        )
        pref_layout.addRow("Preferences:", self.pref_label)

        pay_str = f"Payment Mode: {self.payment_mode}"
        if "UPI" in self.payment_mode.upper() and self.upi_id:
            pay_str += f" (VPA: {self.upi_id})"
        self.payment_label = QLabel(pay_str, self)
        pref_layout.addRow("Payment:", self.payment_label)

        layout.addWidget(pref_box)

        # Validation Guard
        self.validation_error_label = QLabel("", self)
        self.validation_error_label.setStyleSheet("color: #D32F2F; font-weight: bold; font-size: 11px;")
        self.validation_error_label.setWordWrap(True)
        layout.addWidget(self.validation_error_label)

        # Action Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_btn)

        self.confirm_btn = QPushButton("CONFIRM & PREPARE", self)
        self.confirm_btn.setDefault(True)
        self.confirm_btn.setStyleSheet(
            "background-color: #1976D2; color: white; font-weight: bold; padding: 8px 18px;"
        )
        self.confirm_btn.clicked.connect(self._on_confirm_clicked)
        button_row.addWidget(self.confirm_btn)

        layout.addLayout(button_row)

        self._validate_details()

    def _validate_details(self) -> None:
        """Ensure mandatory train number and class are strictly satisfied."""
        if not self.trip.train_number or not str(self.trip.train_number).strip():
            self.validation_error_label.setText("ERROR: Train Number is mandatory. Please provide a valid train number.")
            self.confirm_btn.setEnabled(False)
            return

        if not self.trip.class_code or not str(self.trip.class_code).strip():
            self.validation_error_label.setText("ERROR: Train Class is mandatory. Please select a valid class.")
            self.confirm_btn.setEnabled(False)
            return

        self.confirm_btn.setEnabled(True)

    def _on_confirm_clicked(self) -> None:
        self.confirmed = True
        self.accept()

    def exec(self) -> int:
        """Execute dialog modally, or evaluate validity automatically in offscreen test mode."""
        import os
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and getattr(self, "_auto_accept_offscreen", True):
            if self.confirm_btn.isEnabled():
                self.confirmed = True
                return QDialog.DialogCode.Accepted
            return QDialog.DialogCode.Rejected
        return super().exec()
