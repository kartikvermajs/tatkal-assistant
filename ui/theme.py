"""Centralized UI theme and styling for Tatkal Assistant.

Ensures clear, high-contrast, professional visuals across all Windows themes
(including Windows 10/11 Dark Mode) so labels and controls are always crisp and legible.
"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

GLOBAL_STYLESHEET = """
/* Universal text and font defaults */
QWidget {
    color: #1E293B;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #F1F5F9;
    color: #1E293B;
}

/* Ensure ALL labels are crisp and readable */
QLabel {
    color: #1E293B;
    font-size: 13px;
}

/* Group Boxes */
QGroupBox {
    font-weight: bold;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 16px;
    padding-bottom: 10px;
    background-color: #FFFFFF;
    color: #0F172A;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #0F172A;
    font-size: 13px;
    font-weight: bold;
}

/* Form Inputs */
QLineEdit, QComboBox, QDateEdit, QSpinBox {
    padding: 7px 10px;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    background-color: #FFFFFF;
    color: #0F172A;
    font-size: 13px;
    min-height: 22px;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus {
    border: 1.5px solid #2563EB;
}

QLineEdit::placeholder {
    color: #94A3B8;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #0F172A;
    selection-background-color: #DBEAFE;
    selection-color: #1E40AF;
    border: 1px solid #CBD5E1;
    padding: 4px;
}

/* Checkboxes */
QCheckBox {
    color: #1E293B;
    font-size: 12px;
    font-weight: 500;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #94A3B8;
    background-color: #FFFFFF;
}

QCheckBox::indicator:checked {
    background-color: #2563EB;
    border-color: #1D4ED8;
}

/* Buttons */
QPushButton {
    min-height: 36px;
    padding: 6px 14px;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    background-color: #F8FAFC;
    font-size: 12px;
    font-weight: 600;
    color: #1E293B;
}

QPushButton:hover {
    background-color: #E2E8F0;
    border-color: #94A3B8;
}

QPushButton:pressed {
    background-color: #CBD5E1;
}

QPushButton:disabled {
    background-color: #F1F5F9;
    color: #94A3B8;
    border-color: #E2E8F0;
}

/* Utility / Profile Row Buttons */
QPushButton#utilityBtn {
    min-height: 28px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    background-color: #F8FAFC;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    color: #334155;
}

QPushButton#utilityBtn:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
    color: #0F172A;
}

/* Action Buttons: OPEN IRCTC */
QPushButton#openIrctcBtn {
    background-color: #FFFFFF;
    color: #0F172A;
    font-weight: 700;
    border: 1px solid #94A3B8;
    border-radius: 6px;
}

QPushButton#openIrctcBtn:hover {
    background-color: #F8FAFC;
    border-color: #64748B;
}

QPushButton#openIrctcBtn:pressed {
    background-color: #E2E8F0;
}

/* Action Buttons: PREPARE BOOKING (Primary Action) */
QPushButton#prepareBookingBtn {
    background-color: #2563EB;
    color: #FFFFFF;
    font-weight: 700;
    border: 1px solid #1D4ED8;
    border-radius: 6px;
}

QPushButton#prepareBookingBtn:hover {
    background-color: #1D4ED8;
    border-color: #1E40AF;
}

QPushButton#prepareBookingBtn:pressed {
    background-color: #1E40AF;
}

QPushButton#prepareBookingBtn:disabled {
    background-color: #F1F5F9;
    color: #94A3B8;
    border-color: #E2E8F0;
}

/* Action Buttons: CHECKPOINT DONE */
QPushButton#checkpointBtn {
    background-color: #F0FDF4;
    color: #166534;
    font-weight: 700;
    border: 1px solid #86EFAC;
    border-radius: 6px;
}

QPushButton#checkpointBtn:hover {
    background-color: #DCFCE7;
    border-color: #4ADE80;
}

QPushButton#checkpointBtn:pressed {
    background-color: #BBF7D0;
}

QPushButton#checkpointBtn:disabled {
    background-color: #F1F5F9;
    color: #94A3B8;
    border-color: #E2E8F0;
}

/* Action Buttons: STOP AUTOMATION (Destructive Action) */
QPushButton#stopAutomationBtn {
    background-color: #DC2626;
    color: #FFFFFF;
    font-weight: 700;
    border: 1px solid #B91C1C;
    border-radius: 6px;
}

QPushButton#stopAutomationBtn:hover {
    background-color: #B91C1C;
    border-color: #991B1B;
}

QPushButton#stopAutomationBtn:pressed {
    background-color: #991B1B;
}

QPushButton#stopAutomationBtn:disabled {
    background-color: #F1F5F9;
    color: #94A3B8;
    border: 1px solid #E2E8F0;
}

/* Action Buttons: CANCEL (Distinct Secondary Action) */
QPushButton#cancelBtn {
    background-color: #F8FAFC;
    color: #475569;
    font-weight: 600;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
}

QPushButton#cancelBtn:hover {
    background-color: #F1F5F9;
    color: #0F172A;
    border-color: #94A3B8;
}

QPushButton#cancelBtn:pressed {
    background-color: #E2E8F0;
}

/* Tables */
QTableWidget {
    background-color: #FFFFFF;
    color: #0F172A;
    gridline-color: #E2E8F0;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    selection-background-color: #DBEAFE;
    selection-color: #1E40AF;
}

QHeaderView::section {
    background-color: #F8FAFC;
    color: #334155;
    font-weight: 600;
    padding: 8px;
    border: 1px solid #E2E8F0;
}
"""


def setup_application_theme(app: QApplication) -> None:
    """Configure Fusion style and light-mode palette to prevent dark mode contrast bugs."""
    app.setStyle("Fusion")

    # Establish a reliable high-contrast palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F1F5F9"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1E293B"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1E293B"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#DC2626"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#2563EB"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2563EB"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94A3B8"))
    app.setPalette(palette)

    app.setStyleSheet(GLOBAL_STYLESHEET)
