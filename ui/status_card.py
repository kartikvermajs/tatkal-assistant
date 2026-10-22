"""Modern Status Card component for Pre-Flight Readiness Checklist."""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.icon_provider import get_pixmap


class StatusCard(QFrame):
    """Compact modern card showing readiness state with local vector icon,
    title, status indicator, and clear color hierarchy.
    """

    VARIANT_STYLES = {
        "ready": {
            "border": "#86EFAC",
            "bg": "#F0FDF4",
            "badge_bg": "#DCFCE7",
            "badge_border": "#86EFAC",
            "badge_text": "#166534",
            "icon_color": "#16A34A",
            "dot_color": "#16A34A",
        },
        "pending": {
            "border": "#FECACA",
            "bg": "#FEF2F2",
            "badge_bg": "#FEE2E2",
            "badge_border": "#FCA5A5",
            "badge_text": "#991B1B",
            "icon_color": "#DC2626",
            "dot_color": "#DC2626",
        },
        "warning": {
            "border": "#FDE047",
            "bg": "#FEFCE8",
            "badge_bg": "#FEF9C3",
            "badge_border": "#FDE047",
            "badge_text": "#854D0E",
            "icon_color": "#D97706",
            "dot_color": "#D97706",
        },
        "neutral": {
            "border": "#CBD5E1",
            "bg": "#F8FAFC",
            "badge_bg": "#F1F5F9",
            "badge_border": "#CBD5E1",
            "badge_text": "#475569",
            "icon_color": "#64748B",
            "dot_color": "#64748B",
        },
        "info": {
            "border": "#93C5FD",
            "bg": "#EFF6FF",
            "badge_bg": "#DBEAFE",
            "badge_border": "#93C5FD",
            "badge_text": "#1E40AF",
            "icon_color": "#2563EB",
            "dot_color": "#2563EB",
        },
    }

    def __init__(
        self,
        title: str,
        icon_name: str,
        initial_status: str = "PENDING",
        variant: str = "pending",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.icon_name = icon_name
        self._current_variant = variant

        self.setObjectName("statusCard")
        self._init_ui()
        self.set_status(initial_status, variant)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Header row: [Icon]  Title          [Status Dot]
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(18, 18)
        header_row.addWidget(self.icon_label)

        self.title_label = QLabel(self.title, self)
        self.title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #475569; font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;")
        header_row.addWidget(self.title_label)

        header_row.addStretch()

        self.dot_label = QLabel(self)
        self.dot_label.setFixedSize(8, 8)
        header_row.addWidget(self.dot_label)

        layout.addLayout(header_row)

        # Status text badge: e.g. "Route: PENDING" or "Route: READY"
        self.badge_label = QLabel(self)
        self.badge_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.badge_label)

    def set_status(self, text: str, variant: Optional[str] = None) -> None:
        """Update card state text and visual styling."""
        if variant is None:
            txt_upper = text.upper()
            if "READY" in txt_upper or "SYNCED" in txt_upper:
                variant = "ready"
            elif "PENDING" in txt_upper or "NONE" in txt_upper or "ERROR" in txt_upper:
                variant = "pending"
            elif "CLOSED" in txt_upper or "WARNING" in txt_upper:
                variant = "warning"
            else:
                variant = "neutral"

        self._current_variant = variant
        style = self.VARIANT_STYLES.get(variant, self.VARIANT_STYLES["neutral"])

        # Update badge text
        self.badge_label.setText(text)

        # Update card frame stylesheet
        self.setStyleSheet(
            f"QFrame#statusCard {{ "
            f"background-color: {style['bg']}; "
            f"border: 1px solid {style['border']}; "
            f"border-radius: 8px; "
            f"}}"
        )

        # Update badge label stylesheet
        self.badge_label.setStyleSheet(
            f"background-color: {style['badge_bg']}; "
            f"color: {style['badge_text']}; "
            f"border: 1px solid {style['badge_border']}; "
            f"border-radius: 5px; "
            f"padding: 3px 6px; "
            f"font-weight: 700; "
            f"font-size: 11px;"
        )

        # Update dot indicator
        self.dot_label.setStyleSheet(
            f"background-color: {style['dot_color']}; "
            f"border-radius: 4px; "
            f"min-width: 8px; max-width: 8px; "
            f"min-height: 8px; max-height: 8px;"
        )

        # Update icon pixmap
        pm = get_pixmap(self.icon_name, color=style["icon_color"], size=18)
        self.icon_label.setPixmap(pm)

    def text(self) -> str:
        """Forward text() to badge_label for full backward compatibility."""
        return self.badge_label.text()

    def setText(self, text: str) -> None:
        """Forward setText() to set_status for full backward compatibility."""
        self.set_status(text)
