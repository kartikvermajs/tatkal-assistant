"""Booking History Dialog for viewing and reconciling past ticket booking records."""

import os
from typing import List, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.db import Database
from models.booking import BookingRecord
from ui.booking_confirmation_dialog import BookingConfirmationDialog


class BookingHistoryDialog(QDialog):
    """Dialog allowing users to inspect past booking attempts and reconciliation records."""

    def __init__(
        self,
        db: Database,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.bookings: List[BookingRecord] = []
        self.setWindowTitle("Booking History & Audit Records")
        self.setMinimumSize(720, 480)
        self._init_ui()
        self.refresh_table()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header Title
        title = QLabel("PAST BOOKING RECORDS", self)
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(title)

        # Table
        self.table = QTableWidget(self)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Date", "PNR", "Train", "Class", "Route", "Status", "Fare (₹)"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(self._on_view_details_clicked)

        layout.addWidget(self.table)

        # Button Row
        button_row = QHBoxLayout()

        self.view_details_btn = QPushButton("View Details", self)
        self.view_details_btn.clicked.connect(self._on_view_details_clicked)
        button_row.addWidget(self.view_details_btn)

        self.delete_btn = QPushButton("Delete Record", self)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        button_row.addWidget(self.delete_btn)

        button_row.addStretch()

        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)

        layout.addLayout(button_row)

    def refresh_table(self) -> None:
        """Query database for booking records and populate table."""
        self.bookings = self.db.list_bookings()
        self.table.setRowCount(len(self.bookings))

        for row, b in enumerate(self.bookings):
            date_item = QTableWidgetItem(b.journey_date_str)
            pnr_item = QTableWidgetItem(b.pnr or "-")
            train_item = QTableWidgetItem(b.train_number)
            class_item = QTableWidgetItem(b.class_code)
            route_item = QTableWidgetItem(f"{b.from_station} → {b.to_station}")
            status_item = QTableWidgetItem(b.status)
            fare_item = QTableWidgetItem(f"{b.total_fare:.2f}" if b.total_fare > 0 else "-")

            # Center alignment
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            pnr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            train_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            class_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fare_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # Styling status
            if b.status == "SUCCESS":
                status_item.setForeground(QColor("#2E7D32"))
                status_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            elif b.status == "FAILURE":
                status_item.setForeground(QColor("#C62828"))
                status_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            else:
                status_item.setForeground(QColor("#E65100"))
                status_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

            self.table.setItem(row, 0, date_item)
            self.table.setItem(row, 1, pnr_item)
            self.table.setItem(row, 2, train_item)
            self.table.setItem(row, 3, class_item)
            self.table.setItem(row, 4, route_item)
            self.table.setItem(row, 5, status_item)
            self.table.setItem(row, 6, fare_item)

    def _get_selected_booking(self) -> Optional[BookingRecord]:
        curr = self.table.currentRow()
        if 0 <= curr < len(self.bookings):
            return self.bookings[curr]
        return None

    def _on_view_details_clicked(self) -> None:
        booking = self._get_selected_booking()
        if booking is None:
            return
        dialog = BookingConfirmationDialog(booking, self)
        dialog.exec()

    def _on_delete_clicked(self) -> None:
        booking = self._get_selected_booking()
        if booking is None or booking.id is None:
            return

        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            reply = QMessageBox.question(
                self,
                "Delete Booking Record",
                f"Are you sure you want to delete this record (Train {booking.train_number}, PNR: {booking.pnr or 'N/A'})?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.db.delete_booking(booking.id)
        self.refresh_table()

    def exec(self) -> int:
        """Execute dialog modally or auto-accept in headless test environment."""
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and getattr(self, "_auto_accept_offscreen", True):
            return QDialog.DialogCode.Accepted
        return super().exec()
