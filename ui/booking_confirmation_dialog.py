"""Booking Confirmation and Post-Booking Reconciliation Dialog.

Displays outcome of booking attempts: confirmed tickets (with PNR, coach/berth, fare),
explicit failures, or ambiguous outcomes with strict deadlock safety warnings.
"""

import json
import os
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
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
from models.booking import BookingRecord


class BookingConfirmationDialog(QDialog):
    """Dialog displaying ticket confirmation details, failure notices, or deadlock warnings."""

    def __init__(
        self,
        booking: BookingRecord,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.booking = booking
        self.setWindowTitle("Booking Result & Reconciliation")
        self.setFixedSize(540, 600)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 1. Header Banner based on status
        header_banner = QLabel(self)
        header_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        header_banner.setFont(header_font)
        header_banner.setWordWrap(True)

        if self.booking.status == "SUCCESS":
            header_banner.setText("✔ BOOKING SUCCESSFUL - TICKET CONFIRMED")
            header_banner.setStyleSheet(
                "background-color: #E8F5E9; color: #2E7D32; padding: 12px; border-radius: 6px; border: 1px solid #A5D6A7;"
            )
        elif self.booking.status == "FAILURE":
            header_banner.setText("✖ BOOKING FAILED / REJECTED")
            header_banner.setStyleSheet(
                "background-color: #FFEBEE; color: #C62828; padding: 12px; border-radius: 6px; border: 1px solid #FFCDD2;"
            )
        else:
            header_banner.setText("⚠ Booking status is uncertain. Verify IRCTC booking history before attempting another booking.")
            header_banner.setStyleSheet(
                "background-color: #FFF3E0; color: #E65100; padding: 12px; border-radius: 6px; border: 1px solid #FFE0B2;"
            )

        layout.addWidget(header_banner)

        # 2. Status details
        if self.booking.status == "SUCCESS":
            self._build_success_ui(layout)
        elif self.booking.status == "FAILURE":
            self._build_failure_ui(layout)
        else:
            self._build_unknown_ui(layout)

        layout.addStretch()

        # 3. Action Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()

        if self.booking.pnr:
            copy_pnr_btn = QPushButton("Copy PNR", self)
            copy_pnr_btn.clicked.connect(self._on_copy_pnr_clicked)
            button_row.addWidget(copy_pnr_btn)

        close_btn = QPushButton("Done", self)
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold; padding: 8px 18px;")
        button_row.addWidget(close_btn)

        layout.addLayout(button_row)

    def _build_success_ui(self, layout: QVBoxLayout) -> None:
        """Construct UI widgets for confirmed booking with PNR and berth allocations."""
        # PNR Display Box
        pnr_group = QGroupBox("Booking Reference", self)
        pnr_layout = QHBoxLayout(pnr_group)
        pnr_layout.setContentsMargins(15, 12, 15, 12)

        pnr_title = QLabel("PNR Number:", self)
        pnr_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.pnr_val = QLabel(self.booking.pnr or "N/A", self)
        self.pnr_val.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self.pnr_val.setStyleSheet("color: #1565C0; letter-spacing: 2px;")

        pnr_layout.addWidget(pnr_title)
        pnr_layout.addWidget(self.pnr_val)
        pnr_layout.addStretch()

        layout.addWidget(pnr_group)

        # Journey Overview
        journey_group = QGroupBox("Journey Summary", self)
        form = QFormLayout(journey_group)
        form.setContentsMargins(15, 12, 15, 12)
        form.setSpacing(8)

        form.addRow("Train:", QLabel(f"{self.booking.train_number} {self.booking.train_name}".strip()))
        class_name = config.get_class_display_name(self.booking.class_code)
        form.addRow("Class & Quota:", QLabel(f"{class_name} ({self.booking.class_code}) / {self.booking.quota_code}"))
        form.addRow("Route:", QLabel(f"{self.booking.from_station} → {self.booking.to_station}"))
        form.addRow("Date:", QLabel(self.booking.journey_date_str))

        if self.booking.total_fare > 0:
            form.addRow("Total Fare:", QLabel(f"₹ {self.booking.total_fare:.2f}"))
        if self.booking.transaction_id:
            form.addRow("Transaction ID:", QLabel(self.booking.transaction_id))

        layout.addWidget(journey_group)

        # Passengers Allocations Table if available
        passengers = self.booking.get_parsed_passengers()
        if passengers:
            passenger_group = QGroupBox("Allocated Passengers", self)
            p_layout = QVBoxLayout(passenger_group)
            p_layout.setContentsMargins(10, 10, 10, 10)

            table = QTableWidget(len(passengers), 2, self)
            table.setHorizontalHeaderLabels(["Passenger", "Status / Berth"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

            for i, p in enumerate(passengers):
                name = p.get("name") or p.get("row") or f"Passenger {i+1}"
                status = p.get("status") or p.get("berth") or "CNF"
                table.setItem(i, 0, QTableWidgetItem(str(name)))
                table.setItem(i, 1, QTableWidgetItem(str(status)))

            p_layout.addWidget(table)
            layout.addWidget(passenger_group)

    def _build_failure_ui(self, layout: QVBoxLayout) -> None:
        """Construct UI widgets for explicit booking failure."""
        fail_group = QGroupBox("Failure Details", self)
        form = QFormLayout(fail_group)
        form.setContentsMargins(15, 15, 15, 15)
        form.setSpacing(10)

        reason = self.booking.status_message or "Ticket was not booked by IRCTC."
        reason_label = QLabel(reason, self)
        reason_label.setWordWrap(True)
        reason_label.setStyleSheet("color: #C62828; font-weight: bold;")
        form.addRow("Reason:", reason_label)

        form.addRow("Train:", QLabel(f"{self.booking.train_number} ({self.booking.class_code})"))
        form.addRow("Route:", QLabel(f"{self.booking.from_station} → {self.booking.to_station}"))
        form.addRow("Date:", QLabel(self.booking.journey_date_str))

        advice = QLabel(
            "Please check if seats are available in the desired class and quota, "
            "or review your payment credentials before trying again.",
            self,
        )
        advice.setWordWrap(True)
        form.addRow("Advice:", advice)

        layout.addWidget(fail_group)

    def _build_unknown_ui(self, layout: QVBoxLayout) -> None:
        """Construct UI widgets for ambiguous payment outcome with strict safety warnings."""
        unknown_group = QGroupBox("Critical Advisory: Do Not Retry", self)
        unknown_group.setStyleSheet("QGroupBox { border-color: #E65100; font-weight: bold; }")
        vbox = QVBoxLayout(unknown_group)
        vbox.setContentsMargins(15, 15, 15, 15)
        vbox.setSpacing(10)

        warn_text = QLabel(
            "<b>DO NOT SUBMIT ANOTHER PAYMENT OR RETRY BOOKING IMMEDIATELY.</b><br><br>"
            "Your payment authorization was initiated, but IRCTC did not confirm ticket generation "
            "due to a gateway timeout, pending status, or disconnected session.<br><br>"
            "Money may have been deducted from your bank or UPI account.",
            self,
        )
        warn_text.setWordWrap(True)
        warn_text.setStyleSheet("color: #BF360C; font-size: 13px;")
        vbox.addWidget(warn_text)

        checklist = QLabel(
            "<b>Required Steps Before Taking Any Further Action:</b><br>"
            "1. Open the IRCTC browser tab and navigate to <b>'Booked Ticket History'</b>.<br>"
            "2. Check your netbanking or UPI app to see if any transaction was debited.<br>"
            "3. If funds were debited but no ticket appears, IRCTC will process an automatic refund (3-5 business days).<br>"
            "4. Only attempt a new booking after confirming no ticket was generated.",
            self,
        )
        checklist.setWordWrap(True)
        checklist.setStyleSheet("background-color: #FFFDE7; padding: 10px; border-radius: 4px; border: 1px solid #FFF59D;")
        vbox.addWidget(checklist)

        layout.addWidget(unknown_group)

    def _on_copy_pnr_clicked(self) -> None:
        """Copy 10-digit PNR to system clipboard."""
        if self.booking.pnr:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(self.booking.pnr)

    def exec(self) -> int:
        """Execute dialog modally or auto-accept in headless test environment."""
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and getattr(self, "_auto_accept_offscreen", True):
            return QDialog.DialogCode.Accepted
        return super().exec()
