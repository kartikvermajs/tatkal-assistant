"""Passenger management interface and edit dialogs."""

from typing import List, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.db import Database
from models.passenger import (
    Passenger,
    VALID_BERTH_PREFERENCES,
    VALID_GENDERS,
)


class PassengerDialog(QDialog):
    """Dialog to create or edit an individual passenger."""

    def __init__(self, parent: Optional[QWidget] = None, passenger: Optional[Passenger] = None) -> None:
        super().__init__(parent)
        self.passenger = passenger
        self.result_passenger: Optional[Passenger] = None
        self.setWindowTitle("Edit Passenger" if passenger else "Add Passenger")
        self.setFixedSize(360, 280)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        # Name
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Full Name")
        if self.passenger:
            self.name_input.setText(self.passenger.name)
        form_layout.addRow("Name:", self.name_input)

        # Age
        self.age_input = QSpinBox(self)
        self.age_input.setRange(1, 125)
        self.age_input.setValue(self.passenger.age if self.passenger else 30)
        form_layout.addRow("Age:", self.age_input)

        # Gender
        self.gender_combo = QComboBox(self)
        for code, label in VALID_GENDERS.items():
            self.gender_combo.addItem(f"{label} ({code})", code)
        if self.passenger:
            idx = self.gender_combo.findData(self.passenger.gender)
            if idx != -1:
                self.gender_combo.setCurrentIndex(idx)
        form_layout.addRow("Gender:", self.gender_combo)

        # Berth Preference
        self.berth_combo = QComboBox(self)
        for code, label in VALID_BERTH_PREFERENCES.items():
            self.berth_combo.addItem(label, code)
        if self.passenger:
            idx = self.berth_combo.findData(self.passenger.berth_preference)
            if idx != -1:
                self.berth_combo.setCurrentIndex(idx)
        form_layout.addRow("Berth Preference:", self.berth_combo)

        layout.addLayout(form_layout)

        # Error message label
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
        name = self.name_input.text()
        age = self.age_input.value()
        gender = self.gender_combo.currentData()
        berth = self.berth_combo.currentData()
        p_id = self.passenger.id if self.passenger else None

        try:
            p = Passenger(
                name=name,
                age=age,
                gender=gender,
                berth_preference=berth,
                id=p_id,
            )
            self.result_passenger = p
            self.accept()
        except ValueError as exc:
            self.error_label.setText(str(exc))


class PassengerManagerWindow(QDialog):
    """Window to view, add, edit, delete, and select passengers for a trip."""

    def __init__(self, db: Database, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Manage Passengers")
        self.resize(600, 420)
        self.setMinimumSize(540, 360)
        self._init_ui()
        self.load_passengers()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        title_label = QLabel("Saved Passengers", self)
        title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        header_layout.addWidget(title_label)

        self.selection_count_label = QLabel("Selected: 0 / 4 (Max 4 for Tatkal)", self)
        self.selection_count_label.setStyleSheet("color: #1565C0; font-weight: 600;")
        header_layout.addStretch()
        header_layout.addWidget(self.selection_count_label)
        main_layout.addLayout(header_layout)

        # Passenger Table
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Select", "Name", "Age", "Gender", "Berth Preference"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        main_layout.addWidget(self.table)

        # Action Buttons Row
        action_row = QHBoxLayout()

        self.add_btn = QPushButton("Add Passenger", self)
        self.add_btn.clicked.connect(self._on_add_clicked)
        action_row.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Edit", self)
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        action_row.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        action_row.addWidget(self.delete_btn)

        action_row.addStretch()

        self.confirm_btn = QPushButton("Confirm Selection", self)
        self.confirm_btn.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold;")
        self.confirm_btn.clicked.connect(self._on_confirm_selection)
        action_row.addWidget(self.confirm_btn)

        main_layout.addLayout(action_row)

    def load_passengers(self) -> None:
        """Load all passengers from database and update table."""
        all_passengers = self.db.list_passengers()
        selected_passengers = self.db.get_selected_passengers()
        selected_ids = {p.id for p in selected_passengers if p.id is not None}

        self.table.setRowCount(len(all_passengers))
        for row, p in enumerate(all_passengers):
            # Checkbox widget
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            checkbox = QCheckBox(chk_widget)
            checkbox.setChecked(p.id in selected_ids)
            checkbox.setProperty("passenger_id", p.id)
            checkbox.stateChanged.connect(self._update_selection_counter)
            chk_layout.addWidget(checkbox)
            self.table.setCellWidget(row, 0, chk_widget)

            # Name item with passenger object stored
            name_item = QTableWidgetItem(p.name)
            name_item.setData(Qt.ItemDataRole.UserRole, p)
            self.table.setItem(row, 1, name_item)

            # Age
            age_item = QTableWidgetItem(str(p.age))
            age_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, age_item)

            # Gender
            gender_label = VALID_GENDERS.get(p.gender, p.gender)
            gender_item = QTableWidgetItem(gender_label)
            gender_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, gender_item)

            # Berth Preference
            berth_label = VALID_BERTH_PREFERENCES.get(p.berth_preference, p.berth_preference)
            berth_item = QTableWidgetItem(berth_label)
            self.table.setItem(row, 4, berth_item)

        self._update_selection_counter()

    def _get_checkbox_for_row(self, row: int) -> Optional[QCheckBox]:
        widget = self.table.cellWidget(row, 0)
        if widget:
            return widget.findChild(QCheckBox)
        return None

    def get_selected_ids(self) -> List[int]:
        """Return IDs of currently checked passengers."""
        selected_ids: List[int] = []
        for row in range(self.table.rowCount()):
            cb = self._get_checkbox_for_row(row)
            if cb and cb.isChecked():
                p_id = cb.property("passenger_id")
                if p_id is not None:
                    selected_ids.append(int(p_id))
        return selected_ids

    def _update_selection_counter(self) -> None:
        count = len(self.get_selected_ids())
        self.selection_count_label.setText(f"Selected: {count} / 4 (Max 4 for Tatkal)")
        if count > 4:
            self.selection_count_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
        else:
            self.selection_count_label.setStyleSheet("color: #1565C0; font-weight: 600;")

    def _on_add_clicked(self) -> None:
        dialog = PassengerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_passenger:
            self.db.create_passenger(dialog.result_passenger)
            self.load_passengers()

    def _on_edit_clicked(self) -> None:
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "Select Passenger", "Please select a passenger row to edit.")
            return

        name_item = self.table.item(current_row, 1)
        passenger: Optional[Passenger] = name_item.data(Qt.ItemDataRole.UserRole)
        if not passenger:
            return

        dialog = PassengerDialog(self, passenger=passenger)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_passenger:
            self.db.update_passenger(dialog.result_passenger)
            self.load_passengers()

    def _on_delete_clicked(self) -> None:
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "Select Passenger", "Please select a passenger row to delete.")
            return

        name_item = self.table.item(current_row, 1)
        passenger: Optional[Passenger] = name_item.data(Qt.ItemDataRole.UserRole)
        if not passenger or passenger.id is None:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete passenger '{passenger.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.delete_passenger(passenger.id)
            self.load_passengers()

    def _on_confirm_selection(self) -> None:
        selected_ids = self.get_selected_ids()
        if len(selected_ids) > 4:
            QMessageBox.warning(
                self,
                "Selection Limit",
                "IRCTC allows a maximum of 4 passengers per Tatkal booking. Please uncheck extra passengers.",
            )
            return

        self.db.set_selected_passengers(selected_ids)
        self.accept()
