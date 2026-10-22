"""Log viewer dialog for displaying local application logs."""

import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import config
from core.logger import get_app_logger


class LogViewerDialog(QDialog):
    """Native dialog for viewing sanitized local application logs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Application Logs - Tatkal Assistant")
        self.resize(750, 480)
        self._init_ui()
        self.refresh_logs()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header = QLabel("Local Application Audit Log", self)
        header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(header)

        sub = QLabel(f"File: {config.DEFAULT_LOG_FILE}", self)
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet("color: #666;")
        layout.addWidget(sub)

        # Monospace Text Viewer
        self.log_text = QTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet(
            "background-color: #1E1E1E; color: #D4D4D4; border: 1px solid #333; padding: 10px;"
        )
        layout.addWidget(self.log_text)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.refresh_btn = QPushButton("Refresh", self)
        self.refresh_btn.clicked.connect(self.refresh_logs)
        btn_row.addWidget(self.refresh_btn)

        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)

        layout.addLayout(btn_row)

    def refresh_logs(self) -> None:
        """Reload and display recent log entries from the local file."""
        logs = get_app_logger().get_recent_logs(limit=200)
        if logs:
            self.log_text.setPlainText("\n".join(logs))
        else:
            self.log_text.setPlainText("[ No log entries recorded yet ]")
        # Scroll to bottom
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    def exec(self) -> int:
        """Override to auto-accept in headless test environment."""
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return QDialog.DialogCode.Accepted
        return super().exec()
