from PySide6.QtCore import QDate, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
import threading
from typing import Any, List, Optional

import config
from browser.browser_manager import BrowserManager
from browser.irctc_workflow import IRCTCWorkflow
from core.booking_state import BookingState
from core.clock import TatkalClock
from database.db import Database
from models.passenger import Passenger
from models.settings import ApplicationSettings
from models.trip import Trip
from services.notification_service import NotificationService
from core.logger import log_event
from ui.booking_confirmation_dialog import BookingConfirmationDialog
from ui.booking_history_dialog import BookingHistoryDialog
from ui.booking_review_dialog import BookingReviewDialog
from ui.icon_provider import get_icon
from ui.log_viewer_dialog import LogViewerDialog
from ui.otp_checkpoint_dialog import OtpCheckpointDialog
from ui.passenger_form import PassengerManagerWindow
from ui.payment_checkpoint_dialog import PaymentCheckpointDialog
from ui.status_card import StatusCard
from ui.status_panel import (
    StatusPanel,
    STEP_BROWSER_READY,
    STEP_LOGGED_IN,
    STEP_WAITING_FOR_TATKAL,
    STEP_SELECTING_TRAIN,
    STEP_PASSENGER_REVIEW,
    STEP_CAPTCHA_REQUIRED,
    STEP_PAYMENT_REQUIRED,
    STEP_BOOKING_SUCCESSFUL,
)
from ui.theme import GLOBAL_STYLESHEET
from ui.trip_form import TripManagerWindow


class MainWindow(QMainWindow):
    """Primary desktop interface for Tatkal Assistant."""

    def __init__(
        self,
        db: Optional[Database] = None,
        clock: Optional[TatkalClock] = None,
        notification_service: Optional[NotificationService] = None,
        browser_manager: Optional[BrowserManager] = None,
    ) -> None:
        super().__init__()
        self.db = db if db is not None else Database()
        self.clock = clock if clock is not None else TatkalClock()
        self.notification_service = (
            notification_service if notification_service is not None else NotificationService()
        )
        self.browser_manager = (
            browser_manager if browser_manager is not None else BrowserManager()
        )
        self.selected_passengers: List[Passenger] = []
        self.active_trip: Optional[Trip] = None
        self._current_workflow: Optional[IRCTCWorkflow] = None
        self._opening_alert_fired = False
        self._ewallet_reminder_fired = False
        self._login_alarm_fired = False
        self._auto_start_triggered = False
        self.settings: ApplicationSettings = self.db.load_settings()
        self.setWindowTitle(config.APP_NAME)
        self.setMinimumSize(560, 720)
        self.resize(760, 840)
        self._init_ui()
        self._apply_styles()
        self.load_active_trip()
        self.refresh_selected_passengers()
        self.update_clock_display()
        self._start_clock_sync()
        self._update_checklist()
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._on_timer_tick)
        self.timer.start()

    @property
    def current_workflow(self) -> Optional[IRCTCWorkflow]:
        return self._current_workflow

    @current_workflow.setter
    def current_workflow(self, wf: Optional[IRCTCWorkflow]) -> None:
        self._current_workflow = wf
        if hasattr(self, "stop_automation_btn"):
            is_active = wf is not None
            self.stop_automation_btn.setEnabled(is_active)
            icon_color = "#FFFFFF" if is_active else "#94A3B8"
            self.stop_automation_btn.setIcon(get_icon("stop", icon_color, size=16))

    def _init_ui(self) -> None:
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(20, 16, 20, 20)
        main_layout.setSpacing(12)

        scroll_area.setWidget(container)
        self.setCentralWidget(scroll_area)

        # Helper to guarantee explicit high-contrast form labels across all Windows display modes
        def _make_field_label(text: str) -> QLabel:
            lbl = QLabel(text, self)
            lbl.setStyleSheet("color: #334155; font-weight: 600; font-size: 13px;")
            return lbl

        # Header Title
        title_label = QLabel("TATKAL ASSISTANT", self)
        title_font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #0F172A; font-weight: 800; font-size: 18px; letter-spacing: 1px; padding: 2px 0;")
        main_layout.addWidget(title_label)

        # ---------------- Journey Section ----------------
        journey_group = QGroupBox("Journey Details", self)
        journey_layout = QVBoxLayout(journey_group)
        journey_layout.setContentsMargins(15, 14, 15, 14)
        journey_layout.setSpacing(10)

        # Profile Selection Row
        profile_row = QHBoxLayout()
        profile_row.addWidget(_make_field_label("Profile:"))
        self.active_profile_label = QLabel("[ None ]", self)
        self.active_profile_label.setStyleSheet("color: #1565C0; font-weight: 600;")
        profile_row.addWidget(self.active_profile_label)
        profile_row.addStretch()

        self.save_profile_btn = QPushButton("Save Profile", self)
        self.save_profile_btn.setObjectName("utilityBtn")
        self.save_profile_btn.setIcon(get_icon("save", "#334155", size=13))
        self.save_profile_btn.setIconSize(QSize(13, 13))
        self.save_profile_btn.clicked.connect(self._on_save_profile_clicked)
        profile_row.addWidget(self.save_profile_btn)

        self.manage_profiles_btn = QPushButton("Manage Profiles", self)
        self.manage_profiles_btn.setObjectName("utilityBtn")
        self.manage_profiles_btn.setIcon(get_icon("list", "#334155", size=13))
        self.manage_profiles_btn.setIconSize(QSize(13, 13))
        self.manage_profiles_btn.clicked.connect(self._on_manage_profiles_clicked)
        profile_row.addWidget(self.manage_profiles_btn)

        self.booking_history_btn = QPushButton("Booking History", self)
        self.booking_history_btn.setObjectName("utilityBtn")
        self.booking_history_btn.setIcon(get_icon("history", "#334155", size=13))
        self.booking_history_btn.setIconSize(QSize(13, 13))
        self.booking_history_btn.clicked.connect(self._on_booking_history_clicked)
        profile_row.addWidget(self.booking_history_btn)

        self.view_logs_btn = QPushButton("View Logs", self)
        self.view_logs_btn.setObjectName("utilityBtn")
        self.view_logs_btn.setIcon(get_icon("file-text", "#334155", size=13))
        self.view_logs_btn.setIconSize(QSize(13, 13))
        self.view_logs_btn.clicked.connect(self._on_view_logs_clicked)
        profile_row.addWidget(self.view_logs_btn)

        journey_layout.addLayout(profile_row)

        # Form fields in a balanced 2-column grid
        form_grid = QGridLayout()
        form_grid.setHorizontalSpacing(14)
        form_grid.setVerticalSpacing(8)

        # Row 0: From & To
        self.from_input = QLineEdit(self)
        self.from_input.setPlaceholderText("Station code or name (e.g. NDLS)")
        self.station_completer_from = QCompleter(config.STATION_DISPLAY_LIST, self)
        self.station_completer_from.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.station_completer_from.setFilterMode(Qt.MatchFlag.MatchContains)
        self.from_input.setCompleter(self.station_completer_from)
        self.station_completer_from.activated.connect(
            lambda text: self.from_input.setText(config.STATION_CODE_MAP.get(text, text.split(" - ")[0].strip()))
        )
        self.from_input.textChanged.connect(lambda _: self._update_checklist())
        form_grid.addWidget(_make_field_label("From:"), 0, 0)
        form_grid.addWidget(self.from_input, 0, 1)

        self.to_input = QLineEdit(self)
        self.to_input.setPlaceholderText("Station code or name (e.g. LKO)")
        self.station_completer_to = QCompleter(config.STATION_DISPLAY_LIST, self)
        self.station_completer_to.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.station_completer_to.setFilterMode(Qt.MatchFlag.MatchContains)
        self.to_input.setCompleter(self.station_completer_to)
        self.station_completer_to.activated.connect(
            lambda text: self.to_input.setText(config.STATION_CODE_MAP.get(text, text.split(" - ")[0].strip()))
        )
        self.to_input.textChanged.connect(lambda _: self._update_checklist())
        form_grid.addWidget(_make_field_label("To:"), 0, 2)
        form_grid.addWidget(self.to_input, 0, 3)

        # Row 1: Journey Date & Train Number
        self.journey_date_input = QDateEdit(self)
        self.journey_date_input.setCalendarPopup(True)
        self.journey_date_input.setDisplayFormat("dd/MM/yyyy")
        self.journey_date_input.setDate(QDate.currentDate().addDays(1))
        form_grid.addWidget(_make_field_label("Date:"), 1, 0)
        form_grid.addWidget(self.journey_date_input, 1, 1)

        self.train_number_input = QLineEdit(self)
        self.train_number_input.setPlaceholderText("e.g. 12424")
        self.train_number_input.textChanged.connect(lambda _: self._update_checklist())
        form_grid.addWidget(_make_field_label("Train No:"), 1, 2)
        form_grid.addWidget(self.train_number_input, 1, 3)

        # Row 2: Class & Quota
        self.class_combo = QComboBox(self)
        for code, name in config.AVAILABLE_CLASSES:
            self.class_combo.addItem(name, code)
        self.class_combo.currentIndexChanged.connect(self.update_clock_display)
        self.class_combo.currentIndexChanged.connect(lambda _: self._update_checklist())
        form_grid.addWidget(_make_field_label("Class:"), 2, 0)
        form_grid.addWidget(self.class_combo, 2, 1)

        self.quota_combo = QComboBox(self)
        for code, name in config.AVAILABLE_QUOTAS:
            self.quota_combo.addItem(name, code)
        form_grid.addWidget(_make_field_label("Quota:"), 2, 2)
        form_grid.addWidget(self.quota_combo, 2, 3)

        # Row 3: UPI ID (VPA) spanning full width
        self.upi_id_input = QLineEdit(self)
        self.upi_id_input.setPlaceholderText("UPI VPA for auto-fill (e.g. name@okhdfcbank)")
        self.upi_id_input.setText(self.settings.upi_id)
        self.upi_id_input.textChanged.connect(self._on_upi_id_changed)
        form_grid.addWidget(_make_field_label("UPI ID:"), 3, 0)
        form_grid.addWidget(self.upi_id_input, 3, 1, 1, 3)

        form_grid.setColumnStretch(1, 1)
        form_grid.setColumnStretch(3, 1)

        journey_layout.addLayout(form_grid)

        main_layout.addWidget(journey_group)

        # ---------------- Passenger Section ----------------
        passenger_group = QGroupBox("Passenger", self)
        passenger_layout = QVBoxLayout(passenger_group)
        passenger_layout.setContentsMargins(12, 8, 12, 10)
        passenger_layout.setSpacing(6)

        self.manage_passengers_btn = QPushButton("Manage Passengers", self)
        self.manage_passengers_btn.setObjectName("utilityBtn")
        self.manage_passengers_btn.setIcon(get_icon("users", "#334155", size=14))
        self.manage_passengers_btn.setIconSize(QSize(14, 14))
        self.manage_passengers_btn.clicked.connect(self._on_manage_passengers_clicked)
        passenger_layout.addWidget(self.manage_passengers_btn)

        selected_row = QHBoxLayout()
        selected_title = QLabel("Selected:", self)
        selected_title.setStyleSheet("color: #334155; font-weight: 600; font-size: 13px;")
        self.selected_passengers_label = QLabel("[ None ]", self)
        self.selected_passengers_label.setStyleSheet("color: #666; font-weight: 500;")
        selected_row.addWidget(selected_title)
        selected_row.addWidget(self.selected_passengers_label)
        selected_row.addStretch()
        passenger_layout.addLayout(selected_row)

        main_layout.addWidget(passenger_group)

        # ---------------- Tatkal Timer Section ----------------
        timer_group = QGroupBox("Tatkal Timer", self)
        timer_layout = QFormLayout(timer_group)
        timer_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        timer_layout.setContentsMargins(12, 8, 12, 10)
        timer_layout.setSpacing(6)

        self.current_ist_label = QLabel("--:--:--", self)
        self.current_ist_label.setFont(QFont("Consolas", 12))
        self.current_ist_label.setStyleSheet("color: #0F172A; font-weight: 700; font-size: 13px;")
        timer_layout.addRow(_make_field_label("Current IST:"), self.current_ist_label)

        self.opening_time_label = QLabel(config.DEFAULT_TATKAL_NON_AC_OPENING, self)
        self.opening_time_label.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self.opening_time_label.setStyleSheet("color: #0284C7; font-weight: 700; font-size: 13px;")
        timer_layout.addRow(_make_field_label("Opening:"), self.opening_time_label)

        self.remaining_time_label = QLabel("--:--:--", self)
        self.remaining_time_label.setFont(QFont("Consolas", 12))
        self.remaining_time_label.setStyleSheet("color: #B45309; font-weight: 700; font-size: 13px;")
        timer_layout.addRow(_make_field_label("Remaining:"), self.remaining_time_label)

        # Notification Alerts & Auto-Start Checkboxes
        alerts_row = QHBoxLayout()
        alerts_row.setSpacing(14)
        self.sound_alert_cb = QCheckBox("Sound Alert", self)
        self.sound_alert_cb.setStyleSheet("color: #334155; font-weight: 500;")
        self.sound_alert_cb.setChecked(self.settings.sound_notification)
        self.sound_alert_cb.toggled.connect(self._on_notification_setting_toggled)
        alerts_row.addWidget(self.sound_alert_cb)

        self.visual_alert_cb = QCheckBox("Visual Alert", self)
        self.visual_alert_cb.setStyleSheet("color: #334155; font-weight: 500;")
        self.visual_alert_cb.setChecked(self.settings.visual_notification)
        self.visual_alert_cb.toggled.connect(self._on_notification_setting_toggled)
        alerts_row.addWidget(self.visual_alert_cb)

        self.auto_start_cb = QCheckBox("Auto-Start on Opening", self)
        self.auto_start_cb.setStyleSheet("color: #0284C7; font-weight: 600;")
        self.auto_start_cb.setToolTip("Automatically initiate booking preparation as soon as Tatkal window opens")
        self.auto_start_cb.setChecked(self.settings.auto_start_on_opening)
        self.auto_start_cb.toggled.connect(self._on_auto_start_toggled)
        alerts_row.addWidget(self.auto_start_cb)

        alerts_row.addStretch()

        timer_layout.addRow(_make_field_label("Alerts & Auto:"), alerts_row)

        main_layout.addWidget(timer_group)

        # ---------------- Pre-Flight Readiness Checklist ----------------
        checklist_group = QGroupBox("Pre-Flight Readiness Checklist", self)
        checklist_layout = QHBoxLayout(checklist_group)
        checklist_layout.setContentsMargins(12, 8, 12, 10)
        checklist_layout.setSpacing(10)

        self.chk_route_card = StatusCard("Route", "train", "PENDING", variant="pending", parent=self)
        self.chk_passenger_card = StatusCard("Passengers", "users", "NONE", variant="pending", parent=self)
        self.chk_browser_card = StatusCard("Browser", "globe", "CLOSED", variant="warning", parent=self)
        self.chk_clock_card = StatusCard("Clock", "clock", "LOCAL IST", variant="neutral", parent=self)

        for card in (self.chk_route_card, self.chk_passenger_card, self.chk_browser_card, self.chk_clock_card):
            checklist_layout.addWidget(card, stretch=1)

        # Backward-compatible references for unit test assertions
        self.chk_route_badge = self.chk_route_card.badge_label
        self.chk_passenger_badge = self.chk_passenger_card.badge_label
        self.chk_browser_badge = self.chk_browser_card.badge_label
        self.chk_clock_badge = self.chk_clock_card.badge_label

        main_layout.addWidget(checklist_group)

        # ---------------- Status Section (Phase 22 Visual Status System) ----------------
        self.status_panel = StatusPanel(self)
        self.status_label = self.status_panel.status_label  # Backward-compatible reference
        main_layout.addWidget(self.status_panel)

        # ---------------- Action Buttons ----------------
        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.open_irctc_btn = QPushButton("OPEN IRCTC", self)
        self.open_irctc_btn.setObjectName("openIrctcBtn")
        self.open_irctc_btn.setIcon(get_icon("globe", "#0F172A", size=16))
        self.open_irctc_btn.setIconSize(QSize(16, 16))
        self.open_irctc_btn.setToolTip("Open IRCTC website in browser")
        self.open_irctc_btn.clicked.connect(self._on_open_irctc_clicked)
        button_row.addWidget(self.open_irctc_btn, stretch=1)

        self.prepare_booking_btn = QPushButton("PREPARE BOOKING", self)
        self.prepare_booking_btn.setObjectName("prepareBookingBtn")
        self.prepare_booking_btn.setIcon(get_icon("play", "#FFFFFF", size=16))
        self.prepare_booking_btn.setIconSize(QSize(16, 16))
        self.prepare_booking_btn.setToolTip("Prepare and start booking automation for active trip profile")
        self.prepare_booking_btn.clicked.connect(self._on_prepare_booking_clicked)
        button_row.addWidget(self.prepare_booking_btn, stretch=1)

        self.checkpoint_btn = QPushButton("CHECKPOINT DONE", self)
        self.checkpoint_btn.setObjectName("checkpointBtn")
        self.checkpoint_btn.setIcon(get_icon("check", "#94A3B8", size=16))
        self.checkpoint_btn.setIconSize(QSize(16, 16))
        self.checkpoint_btn.setEnabled(False)
        self.checkpoint_btn.setToolTip("Confirm manual checkpoint completion (e.g. CAPTCHA or 2FA)")
        self.checkpoint_btn.clicked.connect(self._on_checkpoint_clicked)
        button_row.addWidget(self.checkpoint_btn, stretch=1)

        self.stop_automation_btn = QPushButton("STOP AUTOMATION", self)
        self.stop_automation_btn.setObjectName("stopAutomationBtn")
        self.stop_automation_btn.setIcon(get_icon("stop", "#94A3B8", size=16))
        self.stop_automation_btn.setIconSize(QSize(16, 16))
        self.stop_automation_btn.setToolTip("Immediately stop automation (ESC)")
        self.stop_automation_btn.setEnabled(False)
        self.stop_automation_btn.clicked.connect(self._on_stop_automation_clicked)
        button_row.addWidget(self.stop_automation_btn, stretch=1)

        self.cancel_btn = QPushButton("CANCEL", self)
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setIcon(get_icon("x", "#475569", size=16))
        self.cancel_btn.setIconSize(QSize(16, 16))
        self.cancel_btn.setToolTip("Reset automation to idle state")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        button_row.addWidget(self.cancel_btn, stretch=1)

        main_layout.addLayout(button_row)

        # Keyboard Shortcut: ESC triggers Emergency Stop immediately
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.esc_shortcut.activated.connect(self._on_stop_automation_clicked)

    def _apply_styles(self) -> None:
        """Apply a clean, native-feeling stylesheet."""
        self.setStyleSheet(GLOBAL_STYLESHEET)

    def refresh_selected_passengers(self) -> None:
        """Query database for selected passengers and update display."""
        self.selected_passengers = self.db.get_selected_passengers()
        count = len(self.selected_passengers)
        if count == 0:
            self.selected_passengers_label.setText("[ None ]")
            self.selected_passengers_label.setToolTip("No passengers selected.")
            self.selected_passengers_label.setStyleSheet("color: #666; font-weight: 500;")
        elif count == 1:
            p = self.selected_passengers[0]
            display_text = f"[ 1: {p.name} ({p.age}/{p.gender}) ]"
            self.selected_passengers_label.setText(display_text)
            self.selected_passengers_label.setToolTip(f"{p.name}, Age: {p.age}, Gender: {p.gender}, Berth: {p.berth_preference}")
            self.selected_passengers_label.setStyleSheet("color: #1565C0; font-weight: bold;")
        else:
            names = ", ".join(p.name for p in self.selected_passengers)
            display_text = f"[ {count} Selected: {names} ]"
            self.selected_passengers_label.setText(display_text)
            tooltips = "\n".join(f"{p.name} ({p.age}/{p.gender}, Berth: {p.berth_preference})" for p in self.selected_passengers)
            self.selected_passengers_label.setToolTip(tooltips)
            self.selected_passengers_label.setStyleSheet("color: #1565C0; font-weight: bold;")
        self._update_checklist()

    def load_active_trip(self) -> None:
        """Query database for active trip profile and populate journey fields."""
        self.active_trip = self.db.get_active_trip()
        if self.active_trip:
            self.from_input.setText(self.active_trip.from_station)
            self.to_input.setText(self.active_trip.to_station)

            j_date = self.active_trip.journey_date
            if isinstance(j_date, str):
                from datetime import date
                j_date = date.fromisoformat(j_date)
            self.journey_date_input.setDate(QDate(j_date.year, j_date.month, j_date.day))

            self.train_number_input.setText(self.active_trip.train_number)

            idx_class = self.class_combo.findData(self.active_trip.class_code)
            if idx_class != -1:
                self.class_combo.setCurrentIndex(idx_class)

            idx_quota = self.quota_combo.findData(self.active_trip.quota)
            if idx_quota != -1:
                self.quota_combo.setCurrentIndex(idx_quota)

            self.active_profile_label.setText(
                f"[ {self.active_trip.from_station} → {self.active_trip.to_station} ({self.active_trip.train_number}) ]"
            )
        else:
            self.active_profile_label.setText("[ None ]")
        self._update_checklist()

    def update_clock_display(self) -> None:
        """Update current IST, Tatkal opening time, and remaining countdown labels."""
        now = self.clock.current_ist()
        self.current_ist_label.setText(self.clock.format_time(now))

        selected_class = self.class_combo.currentData() or "SL"
        open_time = self.clock.get_opening_time_of_day(selected_class)
        self.opening_time_label.setText(open_time.strftime("%H:%M:%S"))

        open_dt = self.clock.get_tatkal_opening_datetime(selected_class, reference_time=now)
        remaining = self.clock.seconds_until(open_dt, reference_time=now)
        self.remaining_time_label.setText(self.clock.format_remaining(remaining))

    def _start_clock_sync(self) -> None:
        """Attempt non-blocking server clock sync in a background thread."""
        def _sync_worker():
            try:
                self.clock.sync_with_server()
            except Exception:
                pass
        threading.Thread(target=_sync_worker, daemon=True).start()

    def _update_checklist(self) -> None:
        """Update pre-flight checklist cards based on current readiness."""
        # 1. Route card
        from_st = self.from_input.text().strip()
        to_st = self.to_input.text().strip()
        train_no = self.train_number_input.text().strip()
        cls_code = self.class_combo.currentData()
        has_route = bool(from_st and to_st and train_no and cls_code and (from_st.upper() != to_st.upper()))
        if has_route:
            self.chk_route_card.set_status("READY", variant="ready")
        else:
            self.chk_route_card.set_status("PENDING", variant="pending")

        # 2. Passenger card
        p_count = len(self.selected_passengers)
        if p_count > 0:
            self.chk_passenger_card.set_status(f"{p_count} READY", variant="ready")
        else:
            self.chk_passenger_card.set_status("NONE", variant="pending")

        # 3. Browser card
        browser_active = self.browser_manager.is_running()
        if browser_active:
            self.chk_browser_card.set_status("READY", variant="ready")
        else:
            self.chk_browser_card.set_status("CLOSED", variant="warning")

        # 4. Clock card
        if self.clock.is_synced:
            self.chk_clock_card.set_status("SYNCED", variant="ready")
        else:
            self.chk_clock_card.set_status("LOCAL IST", variant="neutral")

    def _on_upi_id_changed(self, text: str) -> None:
        self.settings.upi_id = text.strip()
        try:
            self.settings.validate()
            self.db.save_settings(self.settings)
        except ValueError:
            pass

    def _on_auto_start_toggled(self, checked: bool) -> None:
        self.settings.auto_start_on_opening = checked
        self.db.save_settings(self.settings)

    def _on_timer_tick(self) -> None:
        """Periodic clock update, checklist refresh, eWallet reminder, and Tatkal opening detection."""
        self.update_clock_display()
        self._update_checklist()
        selected_class = self.class_combo.currentData() or "SL"

        # eWallet balance reminder ~10 minutes before opening (remaining <= 600s)
        now = self.clock.current_ist()
        open_dt = self.clock.get_tatkal_opening_datetime(selected_class, reference_time=now)
        rem_secs = self.clock.seconds_until(open_dt, reference_time=now)
        if 0 < rem_secs <= 600 and not self._ewallet_reminder_fired:
            if "WALLET" in (self.settings.preferred_payment_mode or "").upper():
                self._ewallet_reminder_fired = True
                self.notification_service.play_sound()
                self.status_label.setText("REMINDER: Verify IRCTC eWallet balance before opening")
                self.status_label.setStyleSheet("color: #0284C7; font-weight: bold;")

        # Pre-Tatkal Login Alarm at T - 90s (optimal login window to prevent session timeout)
        if 0 < rem_secs <= 90:
            if not self._login_alarm_fired:
                self._login_alarm_fired = True
                is_logged_in = False
                if self.browser_manager.is_running():
                    page = self.browser_manager.get_page()
                    if page:
                        try:
                            is_logged_in = (
                                page.locator("a:has-text('Logout'), span:has-text('Welcome')").count() > 0
                            )
                        except Exception:
                            is_logged_in = False

                if is_logged_in:
                    self.status_label.setText("SESSION ACTIVE (T - 90s): Keep-alive heartbeat protecting session")
                    self.status_label.setStyleSheet("color: #166534; font-weight: bold;")
                    if self.current_workflow:
                        self.current_workflow.send_keep_alive_ping()
                else:
                    self.status_label.setText("LOGIN RECOMMENDED (T - 90s): Open login & sign in for Tatkal")
                    self.status_label.setStyleSheet("color: #D97706; font-weight: bold;")
                    if self.browser_manager.is_running():
                        page = self.browser_manager.get_page()
                        if page:
                            if self.current_workflow is None:
                                self.current_workflow = IRCTCWorkflow(page=page, status_callback=self._update_workflow_status)
                                self.current_workflow.sm.add_listener(self._on_state_machine_transition)
                            self.current_workflow.open_login_modal()

                self.notification_service.trigger_checkpoint_alert(
                    "LOGIN RECOMMENDED (T - 90s)",
                    parent_widget=self,
                    sound=self.sound_alert_cb.isChecked(),
                    visual=self.visual_alert_cb.isChecked(),
                )
        elif rem_secs > 90:
            self._login_alarm_fired = False

        # Background Session Keep-Alive Heartbeat (runs every 25s while in USER_LOGGED_IN or WAITING_FOR_TATKAL state)
        if self.browser_manager.is_running():
            page = self.browser_manager.get_page()
            if page:
                if self.current_workflow is None:
                    try:
                        has_login = page.locator("a:has-text('Logout'), span:has-text('Welcome')").count() > 0
                        if has_login:
                            self.current_workflow = IRCTCWorkflow(page=page, status_callback=self._update_workflow_status)
                            self.current_workflow.sm.add_listener(self._on_state_machine_transition)
                            if self.clock.is_tatkal_open(selected_class):
                                self.current_workflow.sm.transition_to(BookingState.USER_LOGGED_IN, "User logged in")
                            else:
                                self.current_workflow.sm.transition_to(BookingState.WAITING_FOR_TATKAL, "Waiting for Tatkal")
                    except Exception:
                        pass

                if self.current_workflow is not None:
                    self.current_workflow.check_and_send_keep_alive(force=False)

        if self.clock.is_tatkal_open(selected_class):
            if not self._opening_alert_fired:
                self._opening_alert_fired = True
                self.status_label.setText("TATKAL OPEN")
                self.status_label.setStyleSheet("color: #2E7D32; font-size: 12px; font-weight: bold;")
                self.notification_service.trigger_opening_alert(
                    parent_widget=self,
                    sound=self.sound_alert_cb.isChecked(),
                    visual=self.visual_alert_cb.isChecked(),
                )

                # Auto-start booking preparation if enabled
                if self.auto_start_cb.isChecked() and not self._auto_start_triggered and self.current_workflow is None:
                    self._auto_start_triggered = True
                    self._on_prepare_booking_clicked(auto_mode=True)
        else:
            self._opening_alert_fired = False
            self._auto_start_triggered = False
            if self.status_label.text() == "TATKAL OPEN":
                self.status_label.setText("READY")
                self.status_label.setStyleSheet("color: #2E7D32; font-size: 10px; font-weight: bold;")

    def _on_notification_setting_toggled(self) -> None:
        """Persist updated notification preferences."""
        self.settings.sound_notification = self.sound_alert_cb.isChecked()
        self.settings.visual_notification = self.visual_alert_cb.isChecked()
        self.db.save_settings(self.settings)

    # ---------------- Button Handlers ----------------
    def _on_manage_profiles_clicked(self) -> None:
        dialog = TripManagerWindow(self.db, self)
        if dialog.exec() == TripManagerWindow.DialogCode.Accepted:
            self.load_active_trip()
            if self.active_trip:
                self.status_label.setText(
                    f"ACTIVE PROFILE: {self.active_trip.from_station} → {self.active_trip.to_station}"
                )
                self.status_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
        else:
            self.load_active_trip()

    def _on_save_profile_clicked(self) -> None:
        from_st = self.from_input.text().strip()
        to_st = self.to_input.text().strip()
        qdate = self.journey_date_input.date()
        from datetime import date
        py_date = date(qdate.year(), qdate.month(), qdate.day())
        train_no = self.train_number_input.text().strip()
        cls_code = self.class_combo.currentData()
        quota_code = self.quota_combo.currentData()

        try:
            trip = Trip(
                from_station=from_st,
                to_station=to_st,
                journey_date=py_date,
                train_number=train_no,
                class_code=cls_code,
                quota=quota_code,
            )
            saved = self.db.create_trip(trip)
            self.db.set_active_trip(saved.id)
            self.load_active_trip()
            self.status_label.setText(f"PROFILE SAVED & ACTIVATED ({saved.from_station} → {saved.to_station})")
            self.status_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
        except ValueError as exc:
            self.status_label.setText(f"PROFILE ERROR: {exc}")
            self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
    def _on_manage_passengers_clicked(self) -> None:
        dialog = PassengerManagerWindow(self.db, self)
        if dialog.exec() == PassengerManagerWindow.DialogCode.Accepted:
            self.refresh_selected_passengers()
            count = len(self.selected_passengers)
            self.status_label.setText(f"PASSENGERS UPDATED ({count} selected)")
            self.status_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
        else:
            self.refresh_selected_passengers()

    def _on_state_machine_transition(
        self,
        from_state: BookingState,
        to_state: BookingState,
        reason: Optional[str] = None,
    ) -> None:
        """Synchronize UI status panel with state machine transitions in real time."""
        self.status_panel.update_for_booking_state(to_state, message=reason)
        QApplication.processEvents()

    def _on_open_irctc_clicked(self) -> None:
        self.status_label.setText("OPENING IRCTC...")
        self.status_label.setStyleSheet("color: #0288D1; font-weight: bold;")
        self.status_panel.set_step_state(STEP_BROWSER_READY, "active")
        QApplication.processEvents()

        try:
            self.browser_manager.open_irctc(headless=False)
            self.status_panel.set_step_state(STEP_BROWSER_READY, "completed")
            self.status_label.setText("BROWSER READY (Complete login manually)")
            self.status_label.setStyleSheet("color: #1565C0; font-weight: bold;")
        except Exception as exc:
            self.status_panel.set_step_state(STEP_BROWSER_READY, "failed")
            self.status_label.setText(f"BROWSER ERROR: {exc}")
            self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
        self._update_checklist()

    def _update_workflow_status(self, message: str) -> None:
        """Update status label during workflow steps."""
        self.status_panel.set_status_text(message)
        msg_upper = message.upper()
        if "TRAIN" in msg_upper:
            self.status_panel.set_step_state(STEP_SELECTING_TRAIN, "active")
        elif "PASSENGER" in msg_upper:
            self.status_panel.set_step_state(STEP_PASSENGER_REVIEW, "active")
        elif "CAPTCHA" in msg_upper:
            self.status_panel.set_step_state(STEP_CAPTCHA_REQUIRED, "action_required")
        elif "PAYMENT" in msg_upper:
            self.status_panel.set_step_state(STEP_PAYMENT_REQUIRED, "action_required")
        elif "SUCCESS" in msg_upper or "CONFIRM" in msg_upper:
            self.status_panel.set_step_state(STEP_BOOKING_SUCCESSFUL, "completed")
        QApplication.processEvents()

    def _on_prepare_booking_clicked(self, checked: bool = False, auto_mode: bool = False) -> None:
        from_st = self.from_input.text().strip()
        to_st = self.to_input.text().strip()
        train_no = self.train_number_input.text().strip()
        cls_code = self.class_combo.currentData()
        quota_code = self.quota_combo.currentData()
        qdate = self.journey_date_input.date()
        from datetime import date
        py_date = date(qdate.year(), qdate.month(), qdate.day())

        # Strict Requirement: Train Number is Always Required
        if not train_no:
            self.status_label.setText("PREPARATION PENDING (Train number is mandatory)")
            self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
            return

        # Strict Requirement: Train Class / Type is Always Required
        if not cls_code:
            self.status_label.setText("PREPARATION PENDING (Train class is mandatory)")
            self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
            return

        # Station validations
        if not from_st or not to_st:
            self.status_label.setText("PREPARATION PENDING (Enter Journey Details)")
            self.status_label.setStyleSheet("color: #F57C00; font-weight: bold;")
            return

        if from_st.upper() == to_st.upper():
            self.status_label.setText("PREPARATION ERROR (Origin & Destination cannot be same)")
            self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
            return

        if not self.selected_passengers:
            self.status_label.setText("PREPARATION PENDING (Select at least 1 passenger)")
            self.status_label.setStyleSheet("color: #F57C00; font-weight: bold;")
            return

        try:
            trip = Trip(
                from_station=from_st,
                to_station=to_st,
                journey_date=py_date,
                train_number=train_no,
                class_code=cls_code,
                quota=quota_code,
            )
        except ValueError as exc:
            self.status_label.setText(f"PREPARATION ERROR: {exc}")
            self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
            return

        # Review & Confirmation Dialog (bypassed only in explicit auto-start mode to save 3-5 seconds)
        if not auto_mode:
            dialog = BookingReviewDialog(
                trip=trip,
                passengers=self.selected_passengers,
                mobile_number=self.settings.mobile_number,
                auto_upgradation=self.settings.auto_upgradation,
                confirm_berths_only=self.settings.confirm_berths_only,
                payment_mode=self.settings.preferred_payment_mode,
                upi_id=self.settings.upi_id,
                parent=self,
            )
            from PySide6.QtWidgets import QDialog
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.status_label.setText("PREPARATION CANCELLED")
                self.status_label.setStyleSheet("color: #666; font-weight: bold;")
                return

        # Execute journey preparation with desktop status updates
        self._update_workflow_status("Selecting journey...")
        self._update_workflow_status(f"Selecting train {trip.train_number}...")
        self._update_workflow_status(f"Selecting class {trip.class_display_name} ({trip.class_code})...")
        self._update_workflow_status(f"Populating {len(self.selected_passengers)} passenger(s)...")

        # If browser is open, drive workflow on active page
        if self.browser_manager.is_running():
            page = self.browser_manager.get_page()
            if page:
                self.stop_automation_btn.setEnabled(True)
                self.current_workflow = IRCTCWorkflow(page=page, status_callback=self._update_workflow_status)
                self.current_workflow.sm.add_listener(self._on_state_machine_transition)
                res = self.current_workflow.prepare_journey(
                    trip=trip,
                    passengers=self.selected_passengers,
                    mobile_number=self.settings.mobile_number,
                    auto_upgradation=self.settings.auto_upgradation,
                    confirm_berths_only=self.settings.confirm_berths_only,
                    payment_mode=self.settings.preferred_payment_mode,
                    upi_id=self.settings.upi_id,
                )
                if not res.success:
                    self.stop_automation_btn.setEnabled(False)
                    self.status_label.setText(f"PREPARATION FAILED: {res.message}")
                    self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
                    return

                # Detect active human checkpoints on the page
                cp_res = self.current_workflow.detect_checkpoints()
                if cp_res.state in {BookingState.CAPTCHA_REQUIRED, BookingState.OTP_REQUIRED, BookingState.PAYMENT_REQUIRED}:
                    self.checkpoint_btn.setEnabled(True)
                    if cp_res.state == BookingState.OTP_REQUIRED:
                        self.checkpoint_btn.setText("OTP ENTERED - CONTINUE")
                    elif cp_res.state == BookingState.PAYMENT_REQUIRED:
                        self.checkpoint_btn.setText("PAYMENT COMPLETED")
                        self.checkpoint_btn.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold;")
                        self.status_label.setText("PAYMENT REQUIRED: PAYMENT AUTHORIZATION REQUIRED (Complete in browser)")
                        self.status_label.setStyleSheet("color: #1565C0; font-weight: bold;")
                    else:
                        self.checkpoint_btn.setText("CHECKPOINT DONE")
                        self.checkpoint_btn.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold;")
                    self.notification_service.trigger_checkpoint_alert(
                        cp_res.state.name,
                        parent_widget=self,
                        sound=self.sound_alert_cb.isChecked(),
                        visual=self.visual_alert_cb.isChecked(),
                    )
                    return

        self.status_label.setText(
            f"PREPARED: {len(self.selected_passengers)} passenger(s) ready (Train {trip.train_number}, {trip.class_code})"
        )
        self.status_label.setStyleSheet("color: #2E7D32; font-weight: bold;")

    def _on_checkpoint_clicked(self) -> None:
        """Handle human checkpoint completion by advancing the workflow."""
        if self.current_workflow is not None:
            curr_state = self.current_workflow.sm.current_state
            if curr_state == BookingState.OTP_REQUIRED:
                dialog = OtpCheckpointDialog(self)
                if dialog.exec() != OtpCheckpointDialog.DialogCode.Accepted:
                    self._on_cancel_clicked(message="OTP authentication cancelled by user.")
                    return
            elif curr_state == BookingState.PAYMENT_REQUIRED:
                method = self.settings.preferred_payment_mode or "IRCTC eWallet"
                dialog = PaymentCheckpointDialog(
                    payment_method=method,
                    upi_id=self.settings.upi_id,
                    parent=self,
                )
                if dialog.exec() != PaymentCheckpointDialog.DialogCode.Accepted:
                    self._on_cancel_clicked(message="Payment authorization cancelled by user.")
                    return

            res = self.current_workflow.confirm_checkpoint_completed()
            if not res.success:
                self.status_label.setText(f"CHECKPOINT ERROR: {res.message}")
                self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
                return

            if res.state == BookingState.CAPTCHA_REQUIRED:
                self.status_label.setText("CAPTCHA REQUIRED (Solve in browser)")
                self.status_label.setStyleSheet("color: #E65100; font-weight: bold;")
                self.checkpoint_btn.setEnabled(True)
                self.checkpoint_btn.setText("CHECKPOINT DONE")
            elif res.state == BookingState.OTP_REQUIRED:
                self.status_label.setText("OTP REQUIRED (Enter directly in browser)")
                self.status_label.setStyleSheet("color: #E65100; font-weight: bold;")
                self.checkpoint_btn.setEnabled(True)
                self.checkpoint_btn.setText("OTP ENTERED - CONTINUE")
            elif res.state == BookingState.PAYMENT_REQUIRED:
                self.status_label.setText("PAYMENT REQUIRED: PAYMENT AUTHORIZATION REQUIRED (Complete in browser)")
                self.status_label.setStyleSheet("color: #1565C0; font-weight: bold;")
                self.checkpoint_btn.setEnabled(True)
                self.checkpoint_btn.setText("PAYMENT COMPLETED")
                self.checkpoint_btn.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold;")
            elif res.state == BookingState.BOOKING_CONFIRMATION:
                self.status_label.setText("BOOKING CONFIRMATION (Checking outcome)")
                self.status_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
                self.checkpoint_btn.setEnabled(False)
                self.checkpoint_btn.setText("CHECKPOINT DONE")
                self.checkpoint_btn.setStyleSheet("")
                self.stop_automation_btn.setEnabled(False)
                QApplication.processEvents()

                # Verify booking outcome
                trip = self.active_trip
                if trip is None:
                    try:
                        qdate = self.journey_date_input.date()
                        from datetime import date
                        trip = Trip(
                            from_station=self.from_input.text().strip(),
                            to_station=self.to_input.text().strip(),
                            journey_date=date(qdate.year(), qdate.month(), qdate.day()),
                            train_number=self.train_number_input.text().strip(),
                            class_code=self.class_combo.currentData() or "SL",
                            quota=self.quota_combo.currentData() or "TATKAL",
                        )
                    except Exception:
                        pass

                conf_res = self.current_workflow.verify_booking_result(trip=trip)
                saved_record = None
                if trip is not None:
                    saved_record = self.current_workflow.save_booking_result(self.db, trip, conf_res)

                if conf_res.state == BookingState.SUCCESS:
                    pnr_str = conf_res.details.get("pnr") if conf_res.details else ""
                    self.status_label.setText(f"BOOKING SUCCESSFUL: BOOKING CONFIRMED (PNR: {pnr_str})")
                    self.status_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
                    self.notification_service.trigger_opening_alert(
                        parent_widget=self,
                        sound=self.sound_alert_cb.isChecked(),
                        visual=self.visual_alert_cb.isChecked(),
                    )
                    if saved_record is not None:
                        dialog = BookingConfirmationDialog(saved_record, self)
                        dialog.exec()
                elif conf_res.state == BookingState.FAILURE:
                    self.status_label.setText(f"BOOKING FAILED: {conf_res.message}")
                    self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
                    if saved_record is not None:
                        dialog = BookingConfirmationDialog(saved_record, self)
                        dialog.exec()
                elif conf_res.state == BookingState.UNKNOWN:
                    self.status_label.setText("STATUS UNCERTAIN: Booking status is uncertain. Verify IRCTC booking history before attempting another booking.")
                    self.status_label.setStyleSheet("color: #E65100; font-weight: bold;")
                    # Deadlock protection: user must not retry until manual cancel/reset
                    self.prepare_booking_btn.setEnabled(False)
                    if saved_record is not None:
                        dialog = BookingConfirmationDialog(saved_record, self)
                        dialog.exec()
            else:
                self.status_label.setText(f"STATE: {res.state.name}")
                self.checkpoint_btn.setEnabled(False)
                self.checkpoint_btn.setStyleSheet("")
        else:
            self.status_label.setText("READY")
            self.checkpoint_btn.setEnabled(False)
            self.checkpoint_btn.setStyleSheet("")
            self.stop_automation_btn.setEnabled(False)

    def _on_booking_history_clicked(self) -> None:
        """Display dialog with past booking history and reconciliation status."""
        dialog = BookingHistoryDialog(self.db, self)
        dialog.exec()

    def _on_view_logs_clicked(self) -> None:
        """Display dialog with local application audit logs."""
        dialog = LogViewerDialog(self)
        dialog.exec()

    def _on_cancel_clicked(self, checked_or_message: Any = None, message: Optional[str] = None) -> None:
        log_event("User cancelled")
        if self.current_workflow is not None:
            self.current_workflow.sm.reset()
            self.current_workflow = None
        self.checkpoint_btn.setEnabled(False)
        self.checkpoint_btn.setText("CHECKPOINT DONE")
        self.checkpoint_btn.setStyleSheet("")
        self.prepare_booking_btn.setEnabled(True)
        self.stop_automation_btn.setEnabled(False)

        if isinstance(checked_or_message, str):
            final_msg = checked_or_message
        elif isinstance(message, str):
            final_msg = message
        else:
            final_msg = "READY"

        self.status_panel.reset()
        if final_msg != "READY":
            self.status_label.setText(final_msg)
            self.status_label.setStyleSheet("color: #666; font-weight: bold;")
        self._update_checklist()

    def _on_stop_automation_clicked(self) -> None:
        """Emergency Stop: Immediately halt all automation, stop Playwright, reset to IDLE."""
        log_event("Emergency stop triggered")

        # 1. Stop active Playwright actions
        if self.browser_manager is not None:
            self.browser_manager.stop_automation()

        if self.current_workflow is not None:
            self.current_workflow.abort("Emergency stop triggered by user")
            self.current_workflow = None

        # 2. Return state to IDLE & reset visual status panel
        self.status_panel.reset()
        self.status_label.setText("STOPPED: Automation halted by user (State: IDLE)")
        self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")

        # 3. Disable automated retries & reset action buttons
        self.checkpoint_btn.setEnabled(False)
        self.checkpoint_btn.setText("CHECKPOINT DONE")
        self.checkpoint_btn.setStyleSheet("")
        self.prepare_booking_btn.setEnabled(True)
        self.stop_automation_btn.setEnabled(False)
        self._update_checklist()
        QApplication.processEvents()

    def keyPressEvent(self, event) -> None:
        """Handle ESC shortcut anywhere on MainWindow."""
        if event.key() == Qt.Key.Key_Escape:
            self._on_stop_automation_clicked()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """Ensure browser is cleanly shut down when closing main window."""
        self.timer.stop()
        self.browser_manager.close_browser()
        event.accept()
