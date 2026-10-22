"""UI Status System: Visual state indicator for Tatkal Assistant.

Displays the current state of automation clearly on the main GUI across all
canonical stages:
- Browser Ready
- Logged In
- Waiting for Tatkal
- Selecting Train
- Passenger Review
- CAPTCHA Required
- Payment Required
- Booking Successful

Ensures the user never has to guess what the automation is doing with a modern,
clean timeline workflow card layout and local SVG vector icons.
"""

from typing import Dict, List, Optional, Tuple
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.booking_state import BookingState
from ui.icon_provider import get_pixmap

# Step Identifiers
STEP_BROWSER_READY = "browser_ready"
STEP_LOGGED_IN = "logged_in"
STEP_WAITING_FOR_TATKAL = "waiting_for_tatkal"
STEP_SELECTING_TRAIN = "selecting_train"
STEP_PASSENGER_REVIEW = "passenger_review"
STEP_CAPTCHA_REQUIRED = "captcha_required"
STEP_PAYMENT_REQUIRED = "payment_required"
STEP_BOOKING_SUCCESSFUL = "booking_successful"

# Canonical Steps in Sequential Order (as specified in Phase 22)
CANONICAL_STEPS: List[Tuple[str, str]] = [
    (STEP_BROWSER_READY, "Browser Ready"),
    (STEP_LOGGED_IN, "Logged In"),
    (STEP_WAITING_FOR_TATKAL, "Waiting for Tatkal"),
    (STEP_SELECTING_TRAIN, "Selecting Train"),
    (STEP_PASSENGER_REVIEW, "Passenger Review"),
    (STEP_CAPTCHA_REQUIRED, "CAPTCHA Required"),
    (STEP_PAYMENT_REQUIRED, "Payment Required"),
    (STEP_BOOKING_SUCCESSFUL, "Booking Successful"),
]

# Meaningful vector icon mapping for each canonical step
STEP_ICONS: Dict[str, str] = {
    STEP_BROWSER_READY: "globe",
    STEP_LOGGED_IN: "user-check",
    STEP_WAITING_FOR_TATKAL: "clock",
    STEP_SELECTING_TRAIN: "train",
    STEP_PASSENGER_REVIEW: "users",
    STEP_CAPTCHA_REQUIRED: "shield",
    STEP_PAYMENT_REQUIRED: "credit-card",
    STEP_BOOKING_SUCCESSFUL: "check-circle",
}

# State visual styles with high-contrast, theme-safe colors
STEP_STYLES = {
    "pending": {
        "frame_style": "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px;",
        "text_color": "#64748B",
        "icon_color": "#94A3B8",
        "badge_text": "Pending",
        "badge_style": "background-color: #F1F5F9; color: #64748B; border: 1px solid #E2E8F0; border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 600;",
        "symbol": "●",
        "font_weight": "500",
    },
    "active": {
        "frame_style": "background-color: #EFF6FF; border: 1.5px solid #3B82F6; border-radius: 6px;",
        "text_color": "#1D4ED8",
        "icon_color": "#2563EB",
        "badge_text": "Active",
        "badge_style": "background-color: #DBEAFE; color: #1E40AF; border: 1px solid #93C5FD; border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 700;",
        "symbol": "→",
        "font_weight": "700",
    },
    "completed": {
        "frame_style": "background-color: #F0FDF4; border: 1px solid #86EFAC; border-radius: 6px;",
        "text_color": "#15803D",
        "icon_color": "#16A34A",
        "badge_text": "Done",
        "badge_style": "background-color: #DCFCE7; color: #166534; border: 1px solid #86EFAC; border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 600;",
        "symbol": "✓",
        "font_weight": "600",
    },
    "action_required": {
        "frame_style": "background-color: #FFFBEB; border: 1.5px solid #F59E0B; border-radius: 6px;",
        "text_color": "#B45309",
        "icon_color": "#D97706",
        "badge_text": "Action",
        "badge_style": "background-color: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 700;",
        "symbol": "●",
        "font_weight": "700",
    },
    "failed": {
        "frame_style": "background-color: #FEF2F2; border: 1.5px solid #EF4444; border-radius: 6px;",
        "text_color": "#B91C1C",
        "icon_color": "#DC2626",
        "badge_text": "Failed",
        "badge_style": "background-color: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 700;",
        "symbol": "✗",
        "font_weight": "700",
    },
}

# Backward compatibility string styles
STYLE_PENDING = "color: #475569; font-weight: 500; font-size: 11px;"
STYLE_ACTIVE = "color: #1D4ED8; font-weight: bold; font-size: 11px;"
STYLE_COMPLETED = "color: #15803D; font-weight: 600; font-size: 11px;"
STYLE_ACTION_REQUIRED = "color: #C2410C; font-weight: bold; font-size: 11px;"
STYLE_FAILED = "color: #B91C1C; font-weight: bold; font-size: 11px;"


class WorkflowStepItem(QFrame):
    """Modern card item representing one step in the automation timeline."""

    def __init__(self, step_id: str, step_name: str, icon_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.step_id = step_id
        self.step_name = step_name
        self.icon_name = icon_name
        self.setObjectName("workflowStepItem")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        # Vector Icon Label
        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(16, 16)
        layout.addWidget(self.icon_label)

        # Step Text Label (e.g. "●  Browser Ready" or "✓  Browser Ready")
        self.label = QLabel(f"●  {self.step_name}", self)
        self.label.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self.label)
        layout.addStretch()

        # Status Pill Badge on the right
        self.badge = QLabel("Pending", self)
        self.badge.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.badge)

    def set_visual_state(self, state: str) -> None:
        style = STEP_STYLES.get(state, STEP_STYLES["pending"])

        # Update text with symbol (●, ✓, →, ✗) while preserving full step_name
        self.label.setText(f"{style['symbol']}  {self.step_name}")
        self.label.setStyleSheet(
            f"color: {style['text_color']}; font-weight: {style['font_weight']}; font-size: 11px; border: none; background: transparent;"
        )

        # Update card container style
        self.setStyleSheet(f"QFrame#workflowStepItem {{ {style['frame_style']} }}")

        # Update vector icon pixmap
        pm = get_pixmap(self.icon_name, color=style["icon_color"], size=16)
        self.icon_label.setPixmap(pm)

        # Update status badge pill
        self.badge.setText(style.get("badge_text", "Pending"))
        self.badge.setStyleSheet(style.get("badge_style", ""))


class StatusPanel(QGroupBox):
    """Visual Status System widget displaying real-time automation state progression."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Automation Status", parent)
        self._step_states: Dict[str, str] = {step_id: "pending" for step_id, _ in CANONICAL_STEPS}
        self.step_widgets: Dict[str, WorkflowStepItem] = {}
        self.step_labels: Dict[str, QLabel] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        panel_layout = QVBoxLayout(self)
        panel_layout.setContentsMargins(12, 8, 12, 10)
        panel_layout.setSpacing(8)

        # Primary status summary row with modern status badge
        summary_row = QHBoxLayout()
        summary_title = QLabel("Current Status:", self)
        summary_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        summary_title.setStyleSheet("color: #334155; font-weight: 700;")
        summary_row.addWidget(summary_title)

        self.status_label = QLabel("READY", self)
        self.status_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.status_label.setStyleSheet(
            "color: #15803D; background-color: #DCFCE7; padding: 3px 8px; border-radius: 4px; border: 1px solid #86EFAC; font-weight: 700;"
        )
        summary_row.addWidget(self.status_label)
        summary_row.addStretch()
        panel_layout.addLayout(summary_row)

        # 2-Column Grid for the 8 Canonical Steps with modern workflow cards
        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)

        # First column: Steps 0 to 3, Second column: Steps 4 to 7
        for idx, (step_id, step_name) in enumerate(CANONICAL_STEPS):
            icon_name = STEP_ICONS.get(step_id, "circle")
            item = WorkflowStepItem(step_id, step_name, icon_name, self)
            self.step_widgets[step_id] = item
            self.step_labels[step_id] = item.label  # Backward-compatible direct label reference

            row = idx % 4
            col = idx // 4
            grid.addWidget(item, row, col)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        panel_layout.addLayout(grid)

        # Apply initial pending states
        for step_id, _ in CANONICAL_STEPS:
            self.set_step_state(step_id, "pending")

    def set_step_state(self, step_id: str, state: str) -> None:
        """Update visual state of a specific canonical step.

        Allowed states: 'pending', 'active', 'completed', 'action_required', 'failed'.
        """
        if step_id not in self.step_widgets:
            return

        self._step_states[step_id] = state
        self.step_widgets[step_id].set_visual_state(state)

    def get_step_state(self, step_id: str) -> str:
        """Return the current visual state of a specific step."""
        return self._step_states.get(step_id, "pending")

    def set_status_text(self, message: str, color: Optional[str] = None) -> None:
        """Update the primary status text and optional color."""
        self.status_label.setText(message)
        if color:
            self.status_label.setStyleSheet(f"color: {color}; font-weight: bold; padding: 4px 10px; border-radius: 5px;")
        elif "ERROR" in message.upper() or "FAILED" in message.upper():
            self.status_label.setStyleSheet(
                "color: #B91C1C; font-weight: bold; background-color: #FEE2E2; padding: 4px 10px; border-radius: 5px; border: 1px solid #FCA5A5;"
            )
        elif "REQUIRED" in message.upper() or "CHECKPOINT" in message.upper():
            self.status_label.setStyleSheet(
                "color: #C2410C; font-weight: bold; background-color: #FFEDD5; padding: 4px 10px; border-radius: 5px; border: 1px solid #FDBA74;"
            )
        elif "READY" in message.upper() or "SUCCESS" in message.upper():
            self.status_label.setStyleSheet(
                "color: #15803D; font-weight: bold; background-color: #DCFCE7; padding: 4px 10px; border-radius: 5px; border: 1px solid #86EFAC;"
            )
        else:
            self.status_label.setStyleSheet(
                "color: #1D4ED8; font-weight: bold; background-color: #DBEAFE; padding: 4px 10px; border-radius: 5px; border: 1px solid #93C5FD;"
            )

    def get_status_text(self) -> str:
        """Return the primary status text."""
        return self.status_label.text()

    def update_for_booking_state(self, state: BookingState, message: Optional[str] = None) -> None:
        """Automatically synchronize all 8 visual status steps with a BookingState."""
        if state == BookingState.IDLE:
            self.reset()
            if message:
                self.set_status_text(message)
            return

        if state == BookingState.BROWSER_READY:
            self.set_step_state(STEP_BROWSER_READY, "active")
            for sid, _ in CANONICAL_STEPS[1:]:
                self.set_step_state(sid, "pending")
            self.set_status_text(message or "BROWSER READY (Complete login manually)")

        elif state == BookingState.USER_LOGIN_REQUIRED:
            self.set_step_state(STEP_BROWSER_READY, "completed")
            self.set_step_state(STEP_LOGGED_IN, "action_required")
            for sid, _ in CANONICAL_STEPS[2:]:
                self.set_step_state(sid, "pending")
            self.set_status_text(message or "LOGIN REQUIRED (Log in to IRCTC in browser)")

        elif state == BookingState.USER_LOGGED_IN:
            self.set_step_state(STEP_BROWSER_READY, "completed")
            self.set_step_state(STEP_LOGGED_IN, "completed")
            for sid, _ in CANONICAL_STEPS[2:]:
                self.set_step_state(sid, "pending")
            self.set_status_text(message or "USER LOGGED IN")

        elif state == BookingState.WAITING_FOR_TATKAL:
            self.set_step_state(STEP_BROWSER_READY, "completed")
            self.set_step_state(STEP_LOGGED_IN, "completed")
            self.set_step_state(STEP_WAITING_FOR_TATKAL, "active")
            for sid, _ in CANONICAL_STEPS[3:]:
                self.set_step_state(sid, "pending")
            self.set_status_text(message or "WAITING FOR TATKAL OPENING")

        elif state in (BookingState.JOURNEY_SELECTION, BookingState.TRAIN_SELECTION):
            self.set_step_state(STEP_BROWSER_READY, "completed")
            self.set_step_state(STEP_LOGGED_IN, "completed")
            self.set_step_state(STEP_WAITING_FOR_TATKAL, "completed")
            self.set_step_state(STEP_SELECTING_TRAIN, "active")
            for sid, _ in CANONICAL_STEPS[4:]:
                self.set_step_state(sid, "pending")
            self.set_status_text(message or "SELECTING TRAIN & CLASS")

        elif state in (BookingState.PASSENGER_SELECTION, BookingState.REVIEW):
            self.set_step_state(STEP_BROWSER_READY, "completed")
            self.set_step_state(STEP_LOGGED_IN, "completed")
            self.set_step_state(STEP_WAITING_FOR_TATKAL, "completed")
            self.set_step_state(STEP_SELECTING_TRAIN, "completed")
            self.set_step_state(STEP_PASSENGER_REVIEW, "active")
            for sid, _ in CANONICAL_STEPS[5:]:
                self.set_step_state(sid, "pending")
            self.set_status_text(message or "PASSENGER DETAILS & REVIEW")

        elif state == BookingState.CAPTCHA_REQUIRED:
            self.set_step_state(STEP_BROWSER_READY, "completed")
            self.set_step_state(STEP_LOGGED_IN, "completed")
            self.set_step_state(STEP_WAITING_FOR_TATKAL, "completed")
            self.set_step_state(STEP_SELECTING_TRAIN, "completed")
            self.set_step_state(STEP_PASSENGER_REVIEW, "completed")
            self.set_step_state(STEP_CAPTCHA_REQUIRED, "action_required")
            self.set_step_state(STEP_PAYMENT_REQUIRED, "pending")
            self.set_step_state(STEP_BOOKING_SUCCESSFUL, "pending")
            self.set_status_text(message or "CAPTCHA REQUIRED (Solve in browser)")

        elif state == BookingState.OTP_REQUIRED:
            self.set_step_state(STEP_BROWSER_READY, "completed")
            self.set_step_state(STEP_LOGGED_IN, "completed")
            self.set_step_state(STEP_WAITING_FOR_TATKAL, "completed")
            self.set_step_state(STEP_SELECTING_TRAIN, "completed")
            self.set_step_state(STEP_PASSENGER_REVIEW, "completed")
            self.set_step_state(STEP_CAPTCHA_REQUIRED, "completed")
            self.set_step_state(STEP_PAYMENT_REQUIRED, "action_required")
            self.set_step_state(STEP_BOOKING_SUCCESSFUL, "pending")
            self.set_status_text(message or "OTP REQUIRED (Enter in browser)")

        elif state == BookingState.PAYMENT_REQUIRED:
            self.set_step_state(STEP_BROWSER_READY, "completed")
            self.set_step_state(STEP_LOGGED_IN, "completed")
            self.set_step_state(STEP_WAITING_FOR_TATKAL, "completed")
            self.set_step_state(STEP_SELECTING_TRAIN, "completed")
            self.set_step_state(STEP_PASSENGER_REVIEW, "completed")
            self.set_step_state(STEP_CAPTCHA_REQUIRED, "completed")
            self.set_step_state(STEP_PAYMENT_REQUIRED, "action_required")
            self.set_step_state(STEP_BOOKING_SUCCESSFUL, "pending")
            self.set_status_text(message or "PAYMENT AUTHORIZATION REQUIRED (Complete in browser)")

        elif state == BookingState.BOOKING_CONFIRMATION:
            self.set_step_state(STEP_BROWSER_READY, "completed")
            self.set_step_state(STEP_LOGGED_IN, "completed")
            self.set_step_state(STEP_WAITING_FOR_TATKAL, "completed")
            self.set_step_state(STEP_SELECTING_TRAIN, "completed")
            self.set_step_state(STEP_PASSENGER_REVIEW, "completed")
            self.set_step_state(STEP_CAPTCHA_REQUIRED, "completed")
            self.set_step_state(STEP_PAYMENT_REQUIRED, "completed")
            self.set_step_state(STEP_BOOKING_SUCCESSFUL, "active")
            self.set_status_text(message or "BOOKING CONFIRMATION (Checking outcome)")

        elif state == BookingState.SUCCESS:
            for sid, _ in CANONICAL_STEPS:
                self.set_step_state(sid, "completed")
            if message and "SUCCESS" not in message.upper():
                self.set_status_text(f"BOOKING SUCCESSFUL: {message}")
            else:
                self.set_status_text(message or "BOOKING SUCCESSFUL")

        elif state == BookingState.FAILURE:
            # Mark the currently active or last step as failed
            active_found = False
            for sid, _ in reversed(CANONICAL_STEPS):
                if self._step_states[sid] in ("active", "action_required"):
                    self.set_step_state(sid, "failed")
                    active_found = True
                    break
            if not active_found:
                self.set_step_state(STEP_SELECTING_TRAIN, "failed")
            if message and "FAIL" not in message.upper():
                self.set_status_text(f"FAILED: {message}")
            else:
                self.set_status_text(message or "BOOKING FAILED")

        elif state == BookingState.UNKNOWN:
            self.set_step_state(STEP_BOOKING_SUCCESSFUL, "failed")
            self.set_status_text(message or "STATUS UNCERTAIN (Verify IRCTC history before retrying)")

    def reset(self) -> None:
        """Reset all steps to pending and status to READY."""
        for step_id, _ in CANONICAL_STEPS:
            self.set_step_state(step_id, "pending")
        self.set_status_text("READY")
