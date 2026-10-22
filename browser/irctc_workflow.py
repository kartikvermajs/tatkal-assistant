"""IRCTC Workflow Abstraction layer.

Coordinates browser page navigation with the deterministic BookingStateMachine.
Stops immediately on unexpected page states; never blindly clicks or retries.
Keeps authentication, CAPTCHA, OTP, and financial authorization strictly under human control.
Strictly requires explicit Train Number and Class before preparation and review.
All IRCTC URLs are centralized in config.py.
"""

from dataclasses import dataclass
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse
from playwright.sync_api import Locator, Page

import config
from core.booking_state import BookingState, BookingStateMachine
from core.failure_handler import FailureType, RetryPolicy, classify_failure
from core.logger import log_event
from models.booking import BookingRecord
from models.passenger import Passenger
from models.trip import Trip


@dataclass
class WorkflowStepResult:
    """Represents the outcome of an individual workflow step."""

    success: bool
    state: BookingState
    message: str
    details: Optional[Dict[str, Any]] = None


class IRCTCWorkflow:
    """High-level abstraction for the IRCTC booking workflow."""

    def __init__(
        self,
        page: Optional[Page] = None,
        state_machine: Optional[BookingStateMachine] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.page = page
        self.sm = state_machine or BookingStateMachine()
        self.status_callback = status_callback
        self._aborted = False
        self.payment_mode: Optional[str] = None
        self.upi_id: str = ""

    @property
    def is_aborted(self) -> bool:
        """Return True if workflow was halted by emergency stop."""
        return self._aborted

    def abort(self, reason: str = "Emergency stop triggered by user") -> None:
        """Immediately abort all ongoing automation actions and reset state to IDLE."""
        self._aborted = True
        if self.page is not None and not self.page.is_closed():
            try:
                self.page.evaluate("window.stop()")
            except Exception:
                pass
        if self.sm.current_state != BookingState.IDLE:
            self.sm.reset(reason=reason)
        self._update_status(f"STOPPED: {reason}")

    def set_page(self, page: Page) -> None:
        """Update active Playwright page."""
        self.page = page

    def set_status_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Set or update callback for progress status messages."""
        self.status_callback = callback

    def _update_status(self, message: str) -> None:
        """Notify status listener if configured."""
        if self.status_callback is not None:
            try:
                self.status_callback(message)
            except Exception:
                pass

    def _ensure_page(self) -> Page:
        if self.page is None or self.page.is_closed():
            raise RuntimeError("Browser closed unexpectedly or crashed during workflow.")
        return self.page

    def check_session_expired(self) -> bool:
        """Inspect page to determine if IRCTC session has expired."""
        try:
            page = self._ensure_page()
            sel_loc = page.locator("#session-expired, .session-expired-msg, [data-testid='session-expired']")
            if sel_loc.count() > 0 and sel_loc.first.is_visible():
                return True
            txt_loc = page.locator("div.alert-danger:has-text('Session'), div:has-text('Session Expired'), div:has-text('session has expired'), div:has-text('Token Expired'), p:has-text('session has expired')")
            if txt_loc.count() > 0 and txt_loc.first.is_visible():
                return True
            return False
        except Exception:
            return False

    # ==================== Step 1: Open Portal ====================

    def open_booking_page(self, url: Optional[str] = None, max_retries: int = 2) -> WorkflowStepResult:
        """Navigate to IRCTC using centralized configuration and ensure page is ready.

        Uses controlled limited retries for ordinary network/page timeouts.
        """
        target_url = url or config.IRCTC_BOOKING_URL
        attempt = 0
        policy = RetryPolicy(max_retries=max_retries, retry_delay_seconds=1.0)

        while True:
            try:
                page = self._ensure_page()
                self._update_status(f"Loading portal: {target_url}...")
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

                # Ensure we are on a valid IRCTC page or local test mock
                current_url = page.url
                base_netloc = urlparse(config.IRCTC_BASE_URL).netloc
                is_valid_url = (
                    base_netloc in current_url
                    or "localhost" in current_url
                    or "127.0.0.1" in current_url
                    or target_url.startswith("data:")
                    or target_url.startswith("http://localhost")
                    or target_url.startswith("http://127.0.0.1")
                )
                if not is_valid_url:
                    reason = f"Unexpected URL navigated: {current_url}"
                    self.sm.fail(reason)
                    return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

                self.sm.transition_to(BookingState.BROWSER_READY, "Booking page opened")
                msg = "IRCTC portal loaded successfully."
                self._update_status(msg)
                log_event("IRCTC opened")
                return WorkflowStepResult(
                    success=True,
                    state=BookingState.BROWSER_READY,
                    message=msg,
                )
            except Exception as exc:
                attempt += 1
                failure = classify_failure(exc, stage="portal")
                if policy.can_retry(failure, attempt=attempt, current_state=self.sm.current_state):
                    self._update_status(f"Page load timed out (attempt {attempt}/{max_retries}). Retrying in 1s...")
                    time.sleep(policy.retry_delay_seconds)
                    continue

                self.sm.fail(failure.message)
                self._update_status(f"FAILED: {failure.message}")
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

    # ==================== Step 2: Check Login ====================

    def check_login_status(self) -> WorkflowStepResult:
        """Inspect page to determine if user is logged in or if login is required."""
        try:
            page = self._ensure_page()

            # Inspect elements to detect logged-in state (e.g., Logout button or user greeting)
            has_logout = (
                page.locator("text=/logout/i").count() > 0
                or page.locator("a:has-text('Logout')").count() > 0
            )

            if has_logout:
                self.sm.transition_to(BookingState.USER_LOGGED_IN, "Active user login detected")
                msg = "User is already logged in."
                self._update_status(msg)
                return WorkflowStepResult(
                    success=True,
                    state=BookingState.USER_LOGGED_IN,
                    message=msg,
                )
            else:
                self.sm.transition_to(BookingState.USER_LOGIN_REQUIRED, "User login required")
                msg = "Manual user login required in browser."
                self._update_status(msg)
                return WorkflowStepResult(
                    success=True,
                    state=BookingState.USER_LOGIN_REQUIRED,
                    message=msg,
                )
        except Exception as exc:
            reason = f"Error checking login state: {exc}"
            self.sm.fail(reason)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

    # ==================== Step 3: Journey Preparation ====================

    def select_journey(self, trip: Trip) -> WorkflowStepResult:
        """Prepare journey details (origin, destination, date).
        
        Mandatory preconditions:
        - Train Number must be explicitly specified (mandatory).
        - Class / Type must be explicitly specified (mandatory).
        - Origin and Destination must be valid.
        """
        try:
            page = self._ensure_page()

            # Strict requirement: Train number must be explicitly specified
            if not trip.train_number or not str(trip.train_number).strip():
                reason = "Train number is mandatory. Cannot continue booking without a specified train number."
                self.sm.fail(reason)
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            # Strict requirement: Class / type must be explicitly specified
            if not trip.class_code or not str(trip.class_code).strip():
                reason = "Train class/type is mandatory. Cannot continue booking without a specified class."
                self.sm.fail(reason)
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            self._update_status("Selecting journey...")

            # Verification: page must not be showing an error page
            if "error" in page.title().lower():
                reason = "Unexpected error page encountered while preparing journey."
                self.sm.fail(reason)
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            if self.check_session_expired():
                reason = "IRCTC session expired. Please log in again to continue."
                if self.sm.can_transition_to(BookingState.USER_LOGIN_REQUIRED):
                    self.sm.transition_to(BookingState.USER_LOGIN_REQUIRED, reason)
                else:
                    self.sm.fail(reason)
                self._update_status(f"SESSION EXPIRED: {reason}")
                return WorkflowStepResult(success=False, state=self.sm.current_state, message=reason)

            # Check if journey form inputs exist on the page (supports both live IRCTC and mocks)
            origin_loc = page.locator("input[placeholder*='From' i], input#origin, p-autocomplete[id*='origin'] input, input[name='origin'], input[data-testid='origin']")
            dest_loc = page.locator("input[placeholder*='To' i], input#destination, p-autocomplete[id*='destination'] input, input[name='destination'], input[data-testid='destination']")
            date_loc = page.locator("input[placeholder*='Date' i], input#journeyDate, p-calendar input, input[name='journeyDate'], input[data-testid='date']")

            # If the page explicitly has search inputs, populate them visible to the user
            if origin_loc.count() > 0:
                origin_loc.first.fill(trip.from_station)
            if dest_loc.count() > 0:
                dest_loc.first.fill(trip.to_station)
            if date_loc.count() > 0:
                # Fill formatted date
                date_loc.first.fill(trip.journey_date_str)

            if self.sm.current_state != BookingState.JOURNEY_SELECTION:
                self.sm.transition_to(BookingState.JOURNEY_SELECTION, f"Selecting {trip.from_station} -> {trip.to_station}")

            msg = f"Journey set to {trip.from_station} -> {trip.to_station} on {trip.journey_date_str}."
            self._update_status(msg)
            log_event("Journey selected")
            return WorkflowStepResult(
                success=True,
                state=BookingState.JOURNEY_SELECTION,
                message=msg,
                details=trip.to_dict(),
            )
        except Exception as exc:
            failure = classify_failure(exc, stage="journey_selection", context={"train_number": trip.train_number if trip else ""})
            self.sm.fail(failure.message)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

    def select_quota(self, quota: str) -> WorkflowStepResult:
        """Select booking quota."""
        try:
            page = self._ensure_page()
            cleaned_quota = quota.strip().upper()
            self._update_status(f"Selecting quota: {cleaned_quota}...")

            quota_loc = page.locator("p-dropdown[id*='journeyQuota'], #journeyQuota, select[name='quota'], [data-testid='quota']")
            if quota_loc.count() > 0:
                # If select/dropdown element exists, select it
                try:
                    quota_loc.first.select_option(value=cleaned_quota)
                except Exception:
                    pass

            return WorkflowStepResult(
                success=True,
                state=self.sm.current_state,
                message=f"Quota selected: {cleaned_quota}",
                details={"quota": cleaned_quota},
            )
        except Exception as exc:
            failure = classify_failure(exc, stage="quota_selection")
            self.sm.fail(failure.message)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

    def select_train(self, train_number: str) -> WorkflowStepResult:
        """Locate configured train on the results page.

        Strict Rules:
        - Train number is mandatory.
        - Never automatically select another train.
        - Never select the first available train.
        - Never infer a train from stations.
        - If the specified train is not found, stop and report failure immediately.
        """
        try:
            page = self._ensure_page()

            if not train_number or not str(train_number).strip():
                reason = "Train number is mandatory. Cannot continue booking without a specified train number."
                self.sm.fail(reason)
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            cleaned_train = str(train_number).strip()

            if self.check_session_expired():
                reason = "IRCTC session expired. Please log in again to continue."
                if self.sm.can_transition_to(BookingState.USER_LOGIN_REQUIRED):
                    self.sm.transition_to(BookingState.USER_LOGIN_REQUIRED, reason)
                else:
                    self.sm.fail(reason)
                self._update_status(f"SESSION EXPIRED: {reason}")
                return WorkflowStepResult(success=False, state=self.sm.current_state, message=reason)

            self._update_status(f"Selecting train {cleaned_train}...")

            # Check if train results list is present on the page
            has_train_list = (
                page.locator(".train-item, [data-train], .form-group, .train-heading, app-train-list").count() > 0
            )

            if has_train_list:
                # Search specifically for elements containing the exact train number
                train_match = page.locator(f":text-matches('(^|\\D){re.escape(cleaned_train)}(\\D|$)')")
                if train_match.count() == 0:
                    # Specifically check plain text as fallback
                    train_match = page.locator(f"text={cleaned_train}")

                if train_match.count() == 0:
                    # Specified train was NOT found on the page!
                    # NEVER select first train, NEVER substitute. Stop immediately!
                    failure = classify_failure(
                        f"Train {cleaned_train} not found",
                        stage="train_selection",
                        context={"train_number": cleaned_train},
                    )
                    self.sm.fail(failure.message)
                    self._update_status(f"ERROR: {failure.message}")
                    return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

            self.sm.transition_to(BookingState.TRAIN_SELECTION, f"Locating train {cleaned_train}")
            msg = f"Train {cleaned_train} selected."
            self._update_status(msg)
            log_event("Train selected")
            return WorkflowStepResult(
                success=True,
                state=BookingState.TRAIN_SELECTION,
                message=msg,
                details={"train_number": cleaned_train},
            )
        except Exception as exc:
            failure = classify_failure(exc, stage="train_selection", context={"train_number": train_number})
            self.sm.fail(failure.message)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

    def select_class(self, class_code: str, train_number: Optional[str] = None) -> WorkflowStepResult:
        """Select travel class on the train.

        Strict Rules:
        - Class/type is mandatory.
        - Never assume a class automatically.
        - Never select the first available class.
        - If class is not found, stop and report failure immediately.
        """
        try:
            page = self._ensure_page()

            if not class_code or not str(class_code).strip():
                reason = "Train class/type is mandatory. Cannot continue booking without a specified class."
                self.sm.fail(reason)
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            cleaned_class = str(class_code).strip().upper()
            display_name = config.get_class_display_name(cleaned_class)

            if self.check_session_expired():
                reason = "IRCTC session expired. Please log in again to continue."
                if self.sm.can_transition_to(BookingState.USER_LOGIN_REQUIRED):
                    self.sm.transition_to(BookingState.USER_LOGIN_REQUIRED, reason)
                else:
                    self.sm.fail(reason)
                self._update_status(f"SESSION EXPIRED: {reason}")
                return WorkflowStepResult(success=False, state=self.sm.current_state, message=reason)

            self._update_status(f"Selecting class {display_name} ({cleaned_class})...")

            # Check for quota unavailability / regret
            quota_err = page.locator(
                ".avl-regret, "
                "[data-testid='quota-unavailable'], "
                ".alert-danger:has-text('REGRET'), "
                ".alert-danger:has-text('No Seats Available'), "
                "span.avl-regret, "
                "div.avl-regret, "
                "div:has-text('WL REGRET')"
            )
            if quota_err.count() > 0 and quota_err.first.is_visible():
                failure = classify_failure(
                    "quota regret unavailable",
                    stage="train_selection",
                    context={"train_number": train_number, "class_code": cleaned_class},
                )
                self.sm.fail(failure.message)
                self._update_status(f"ERROR: {failure.message}")
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

            # Check if class options are present on the page
            has_class_options = (
                page.locator("[data-class], .class-item, button:has-text('SL'), button:has-text('3A'), button:has-text('2A')").count() > 0
            )

            if has_class_options:

                # Look specifically for the configured class code
                class_match = page.locator(f"[data-class='{cleaned_class}'], button:has-text('{cleaned_class}'), div:has-text('{cleaned_class}')")
                if class_match.count() == 0:
                    reason = f"Specified class '{display_name}' ({cleaned_class}) was not found on page. Default or substitute selection is prohibited."
                    self.sm.fail(reason)
                    self._update_status(f"ERROR: {reason}")
                    return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)
                try:
                    class_match.first.click()
                except Exception:
                    pass

            msg = f"Class {display_name} ({cleaned_class}) selected."
            self._update_status(msg)
            return WorkflowStepResult(
                success=True,
                state=self.sm.current_state,
                message=msg,
                details={"class_code": cleaned_class, "class_name": display_name},
            )
        except Exception as exc:
            failure = classify_failure(exc, stage="train_selection", context={"train_number": train_number, "class_code": class_code})
            self.sm.fail(failure.message)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

    def select_passengers(
        self,
        passengers: List[Passenger],
        mobile_number: Optional[str] = None,
        auto_upgradation: bool = False,
        confirm_berths_only: bool = False,
        payment_mode: Optional[str] = None,
    ) -> WorkflowStepResult:
        """Populate passenger details into IRCTC passenger form.

        Strict Rules:
        - Must have at least 1 and at most 4 passengers (Tatkal limit).
        - Populates Name, Age, Gender, and Berth Preference from local profile.
        - Sequentially adds passenger rows if multiple passengers.
        - Configures contact mobile number and travel preferences.
        - Stops immediately on error or page structure mismatch.
        """
        try:
            page = self._ensure_page()

            if not passengers:
                reason = "No passengers provided for booking."
                self.sm.fail(reason)
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            if len(passengers) > 4:
                reason = f"Tatkal allows max 4 passengers ({len(passengers)} provided)."
                self.sm.fail(reason)
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            # Check if page is in an error state
            if "error" in page.title().lower():
                reason = "Unexpected error page encountered before entering passenger details."
                self.sm.fail(reason)
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            self._update_status(f"Starting passenger details entry ({len(passengers)} passenger(s))...")

            # Check if passenger form is present on the page
            # Supports various IRCTC / mock element patterns
            name_inputs = page.locator(
                "input[placeholder*='Passenger Name' i], "
                "p-autocomplete[formcontrolname='passengerName'] input, "
                "input[name*='name' i], "
                "input[data-testid*='passenger-name']"
            )
            has_passenger_form = name_inputs.count() > 0

            if has_passenger_form:
                for idx, p in enumerate(passengers):
                    # For 2nd, 3rd, 4th passenger: click '+ Add Passenger' if needed
                    if idx > 0:
                        current_count = name_inputs.count()
                        if current_count <= idx:
                            add_btn = page.locator(
                                "a:has-text('Add Passenger'), "
                                "button:has-text('Add Passenger'), "
                                "span:has-text('Add Passenger'), "
                                "[data-testid='add-passenger-btn']"
                            )
                            if add_btn.count() > 0:
                                self._update_status(f"Adding passenger row {idx + 1}...")
                                add_btn.first.click()
                                page.wait_for_timeout(100)

                    self._update_status(f"Populating passenger {idx + 1}: {p.name} ({p.age}/{p.gender_display})...")

                    # Fill Name
                    name_field = page.locator(f"[data-testid='passenger-name-{idx}']")
                    if name_field.count() == 0:
                        all_names = page.locator(
                            "input[placeholder*='Passenger Name' i], "
                            "p-autocomplete[formcontrolname='passengerName'] input, "
                            "input[name*='name' i]"
                        )
                        if all_names.count() > idx:
                            name_field = all_names.nth(idx)
                        elif all_names.count() > 0 and idx == 0:
                            name_field = all_names.first
                        else:
                            name_field = None
                    else:
                        name_field = name_field.first

                    if name_field is not None and name_field.count() > 0:
                        name_field.fill(p.name)

                    # Fill Age
                    age_field = page.locator(f"[data-testid='passenger-age-{idx}']")
                    if age_field.count() == 0:
                        all_ages = page.locator(
                            "input[placeholder*='Age' i], "
                            "input[formcontrolname='passengerAge'], "
                            "input[name*='age' i]"
                        )
                        if all_ages.count() > idx:
                            age_field = all_ages.nth(idx)
                        elif all_ages.count() > 0 and idx == 0:
                            age_field = all_ages.first
                        else:
                            age_field = None
                    else:
                        age_field = age_field.first

                    if age_field is not None and age_field.count() > 0:
                        age_field.fill(str(p.age))

                    # Select Gender
                    gender_field = page.locator(f"[data-testid='passenger-gender-{idx}']")
                    if gender_field.count() == 0:
                        all_genders = page.locator(
                            "select[formcontrolname='passengerGender'], "
                            "select[placeholder*='Gender' i], "
                            "select[name*='gender' i]"
                        )
                        if all_genders.count() > idx:
                            gender_field = all_genders.nth(idx)
                        elif all_genders.count() > 0 and idx == 0:
                            gender_field = all_genders.first
                        else:
                            gender_field = None
                    else:
                        gender_field = gender_field.first

                    if gender_field is not None and gender_field.count() > 0:
                        try:
                            gender_field.select_option(value=p.gender)
                        except Exception:
                            try:
                                gender_field.select_option(label=p.gender_display)
                            except Exception:
                                pass

                    # Select Berth Preference
                    if p.berth_preference and p.berth_preference != "NONE":
                        berth_field = page.locator(f"[data-testid='passenger-berth-{idx}']")
                        if berth_field.count() == 0:
                            all_berths = page.locator(
                                "select[formcontrolname='passengerBerthChoice'], "
                                "select[placeholder*='Berth' i], "
                                "select[name*='berth' i]"
                            )
                            if all_berths.count() > idx:
                                berth_field = all_berths.nth(idx)
                            elif all_berths.count() > 0 and idx == 0:
                                berth_field = all_berths.first
                            else:
                                berth_field = None
                        else:
                            berth_field = berth_field.first

                        if berth_field is not None and berth_field.count() > 0:
                            try:
                                berth_field.select_option(value=p.berth_preference)
                            except Exception:
                                try:
                                    berth_field.select_option(label=p.berth_display)
                                except Exception:
                                    pass

                # Contact Mobile Number
                if mobile_number:
                    self._update_status(f"Setting contact mobile number: {mobile_number}...")
                    mobile_input = page.locator(
                        "input[placeholder*='Mobile Number' i], "
                        "input[formcontrolname='mobileNumber'], "
                        "input#mobileNumber, "
                        "[data-testid='mobile-number']"
                    )
                    if mobile_input.count() > 0:
                        mobile_input.first.fill(mobile_number)

                # Travel Preferences
                if auto_upgradation:
                    auto_cb = page.locator(
                        "input#autoUpgradation, "
                        "input[formcontrolname='autoUpgradation'], "
                        "label:has-text('Auto Upgradation') input, "
                        "[data-testid='auto-upgradation']"
                    )
                    if auto_cb.count() > 0:
                        try:
                            auto_cb.first.check()
                        except Exception:
                            pass

                if confirm_berths_only:
                    confirm_cb = page.locator(
                        "input#confirmBerths, "
                        "input[formcontrolname='confirmBerths'], "
                        "label:has-text('confirm berths') input, "
                        "[data-testid='confirm-berths']"
                    )
                    if confirm_cb.count() > 0:
                        try:
                            confirm_cb.first.check()
                        except Exception:
                            pass

                if payment_mode:
                    if payment_mode.upper() == "UPI":
                        upi_radio = page.locator(
                            "input[value='2'], "
                            "label:has-text('BHIM/UPI') input, "
                            "[data-testid='pay-upi']"
                        )
                        if upi_radio.count() > 0:
                            try:
                                upi_radio.first.check()
                            except Exception:
                                pass
                    else:
                        card_radio = page.locator(
                            "input[value='1'], "
                            "label:has-text('Credit') input, "
                            "[data-testid='pay-cards']"
                        )
                        if card_radio.count() > 0:
                            try:
                                card_radio.first.check()
                            except Exception:
                                pass

            self.sm.transition_to(BookingState.PASSENGER_SELECTION, f"Populated {len(passengers)} passengers")
            msg = f"{len(passengers)} passenger(s) populated successfully."
            self._update_status(msg)
            log_event("Passenger selection complete")
            return WorkflowStepResult(
                success=True,
                state=BookingState.PASSENGER_SELECTION,
                message=msg,
                details={
                    "passengers": [p.to_dict() for p in passengers],
                    "mobile_number": mobile_number,
                    "auto_upgradation": auto_upgradation,
                    "confirm_berths_only": confirm_berths_only,
                    "payment_mode": payment_mode,
                },
            )
        except Exception as exc:
            reason = f"Error during passenger selection: {exc}"
            self.sm.fail(reason)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

    def review_booking(
        self,
        trip: Optional[Trip] = None,
        passengers: Optional[List[Passenger]] = None,
    ) -> WorkflowStepResult:
        """Review booking summary before checkpoints.

        Strict Rules:
        - Both Train Number and Class/Type must be explicitly confirmed.
        - Selected train number and class must be displayed in the review.
        """
        try:
            self._ensure_page()

            # Enforce that trip (if provided) has mandatory train number and class
            if trip is not None:
                if not trip.train_number or not str(trip.train_number).strip():
                    reason = "Booking review failed: Train number is mandatory before proceeding."
                    self.sm.fail(reason)
                    return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

                if not trip.class_code or not str(trip.class_code).strip():
                    reason = "Booking review failed: Class/type is mandatory before proceeding."
                    self.sm.fail(reason)
                    return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            self.sm.transition_to(BookingState.REVIEW, "Booking review stage")
            self._update_status("Booking review stage reached. Please verify journey details.")

            details: Dict[str, Any] = {}
            if trip is not None:
                details.update({
                    "train_number": trip.train_number,
                    "train_name": trip.train_name,
                    "class_code": trip.class_code,
                    "class_name": config.get_class_display_name(trip.class_code),
                    "from_station": trip.from_station,
                    "to_station": trip.to_station,
                    "journey_date": trip.journey_date_str,
                    "quota": trip.quota,
                })
            if passengers is not None:
                details["passengers"] = [p.to_dict() for p in passengers]

            msg = "Booking review stage reached. Train and class confirmed."
            if trip is not None:
                msg = (
                    f"Booking Review: Train {trip.train_number}, "
                    f"Class {config.get_class_display_name(trip.class_code)} ({trip.class_code}), "
                    f"{trip.from_station} -> {trip.to_station} on {trip.journey_date_str}."
                )

            return WorkflowStepResult(
                success=True,
                state=BookingState.REVIEW,
                message=msg,
                details=details,
            )
        except Exception as exc:
            reason = f"Error in review stage: {exc}"
            self.sm.fail(reason)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

    def prepare_journey(
        self,
        trip: Trip,
        passengers: Optional[List[Passenger]] = None,
        mobile_number: Optional[str] = None,
        auto_upgradation: bool = False,
        confirm_berths_only: bool = False,
        payment_mode: Optional[str] = None,
        upi_id: str = "",
    ) -> WorkflowStepResult:
        """Composite execution of Journey Preparation and Passenger Automation.

        Executes:
        1. Journey selection (validates origin, destination, date, train number, and class).
        2. Quota selection.
        3. Train selection (exact train number required, no substitution).
        4. Class selection (exact class code required, no default).
        5. Passenger population (if provided, with contact number and preferences).
        6. Booking review (confirming train number, class, and passengers).
        """
        if self._aborted:
            return WorkflowStepResult(success=False, state=BookingState.IDLE, message="Workflow aborted by user.")

        if payment_mode:
            self.payment_mode = payment_mode
        if upi_id:
            self.upi_id = upi_id

        log_event("Workflow started")
        # Step 1: Journey
        res_journey = self.select_journey(trip)
        if not res_journey.success:
            return res_journey

        # Step 2: Quota
        res_quota = self.select_quota(trip.quota)
        if not res_quota.success:
            return res_quota

        # Step 3: Train
        res_train = self.select_train(trip.train_number)
        if not res_train.success:
            return res_train

        # Step 4: Class
        res_class = self.select_class(trip.class_code, train_number=trip.train_number)
        if not res_class.success:
            return res_class

        # Step 5: Passengers (optional during initial journey prep)
        if passengers:
            res_pass = self.select_passengers(
                passengers,
                mobile_number=mobile_number,
                auto_upgradation=auto_upgradation,
                confirm_berths_only=confirm_berths_only,
                payment_mode=payment_mode,
            )
            if not res_pass.success:
                return res_pass

        # Step 6: Review
        res_review = self.review_booking(trip=trip, passengers=passengers)
        return res_review

    # ==================== Step 4: Review, Human Checkpoints & Authorization ====================

    def proceed_to_review(self) -> WorkflowStepResult:
        """Progress from passenger selection to booking review stage on IRCTC portal."""
        try:
            page = self._ensure_page()
            self._update_status("Progressing to review stage...")

            # Locate continue / review button on passenger form
            continue_btn = page.locator(
                "button:has-text('Continue'), "
                "button:has-text('Review Booking'), "
                "button[type='submit']:has-text('Continue'), "
                "[data-testid='continue-btn']"
            )
            if continue_btn.count() > 0:
                continue_btn.first.click()
                page.wait_for_timeout(200)

            # Check if page is in an error state
            if "error" in page.title().lower() or page.locator(".alert-danger, .error-msg").count() > 0:
                reason = "Error page or validation failure encountered when moving to review."
                self.sm.fail(reason)
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            self.sm.transition_to(BookingState.REVIEW, "Progressed to review stage")
            msg = "Booking review stage reached."
            self._update_status(msg)
            return WorkflowStepResult(success=True, state=BookingState.REVIEW, message=msg)
        except Exception as exc:
            failure = classify_failure(exc, stage="review")
            self.sm.fail(failure.message)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

    def detect_checkpoints(self) -> WorkflowStepResult:
        """Inspect page elements to detect active human checkpoints (CAPTCHA, OTP, or Payment)."""
        try:
            page = self._ensure_page()

            # Check session expiration
            if self.check_session_expired():
                reason = "IRCTC session expired. Please log in again to continue."
                if self.sm.can_transition_to(BookingState.USER_LOGIN_REQUIRED):
                    self.sm.transition_to(BookingState.USER_LOGIN_REQUIRED, reason)
                else:
                    self.sm.fail(reason)
                self._update_status(f"SESSION EXPIRED: {reason}")
                return WorkflowStepResult(success=False, state=self.sm.current_state, message=reason)

            # Check explicit payment failure indicators on page
            payment_fail_loc = page.locator(
                "[data-testid='payment-failure'], "
                ".payment-failed, "
                ".alert-danger:has-text('Payment'), "
                ".alert-danger:has-text('Transaction'), "
                "div:has-text('Payment Failed'), "
                "div:has-text('Transaction Failed')"
            )
            if payment_fail_loc.count() > 0 and payment_fail_loc.first.is_visible():
                reason = "Payment failed or was declined by bank/gateway."
                self.sm.fail(reason)
                self._update_status(f"FAILED: {reason}")
                return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

            # 1. Check CAPTCHA
            has_captcha = (
                page.locator(
                    "img.captcha-img, "
                    "#captcha-img, "
                    "input[placeholder*='Captcha' i], "
                    "input#nlpAnswer, "
                    "[data-testid='captcha-img'], "
                    "[data-testid='captcha-input']"
                ).count() > 0
            )
            if has_captcha:
                return self.wait_for_human_captcha()

            # 2. Check OTP (Aadhaar OTP, Login OTP, Transaction OTP)
            has_otp = (
                page.locator(
                    "input[placeholder*='OTP' i], "
                    "input#otp, "
                    "input#aadhaarOtp, "
                    "input#loginOtp, "
                    "input[name*='otp' i], "
                    "input[formcontrolname*='otp' i], "
                    "[data-testid='otp-input']"
                ).count() > 0
                or (
                    page.locator("text=/Enter (Aadhaar )?OTP/i, text=/OTP sent to/i, text=/One Time Password/i").count() > 0
                    and page.locator("input[type='text'], input[type='number'], input[type='password']").count() > 0
                )
            )
            if has_otp:
                return self.wait_for_human_otp()

            # 3. Check Payment Stage
            has_payment = (
                page.locator(
                    "#payment-gateways, "
                    "app-payment, "
                    "[data-testid='payment-options'], "
                    "button:has-text('Pay & Book')"
                ).count() > 0
                or "payment" in page.url.lower()
            )
            if has_payment:
                return self.open_payment()

            return WorkflowStepResult(
                success=True,
                state=self.sm.current_state,
                message=f"Current state is {self.sm.current_state.name}.",
            )
        except Exception as exc:
            failure = classify_failure(exc, stage="checkpoints")
            self.sm.fail(failure.message)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

    def wait_for_human_captcha(self) -> WorkflowStepResult:
        """Human CAPTCHA Checkpoint: Pauses automation for user to solve CAPTCHA manually."""
        try:
            self._ensure_page()
            self.sm.transition_to(BookingState.CAPTCHA_REQUIRED, "Human CAPTCHA checkpoint")
            msg = "CAPTCHA encountered. Complete the CAPTCHA in the browser."
            self._update_status(msg)
            log_event("CAPTCHA required")

            # Auto-focus CAPTCHA input field to save user a click (1-2 seconds)
            try:
                page = self.page
                captcha_input = page.locator(
                    "input[placeholder*='Captcha' i], "
                    "input#nlpAnswer, "
                    "input#captcha, "
                    "[data-testid='captcha-input'], "
                    "input[name*='captcha' i]"
                ).first
                if captcha_input.count() > 0:
                    captcha_input.focus(timeout=2000)
            except Exception:
                pass  # Best-effort: don't fail the checkpoint if focus fails

            return WorkflowStepResult(
                success=True,
                state=BookingState.CAPTCHA_REQUIRED,
                message=msg,
            )
        except Exception as exc:
            reason = f"Error at CAPTCHA stage: {exc}"
            self.sm.fail(reason)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

    def wait_for_human_otp(self) -> WorkflowStepResult:
        """Human OTP Checkpoint: Pauses automation for user to complete OTP authentication."""
        try:
            self._ensure_page()
            if self.sm.current_state != BookingState.OTP_REQUIRED:
                self.sm.transition_to(BookingState.OTP_REQUIRED, "Human OTP checkpoint")
            msg = "OTP REQUIRED: OTP authentication required. Complete in the browser."
            self._update_status(msg)
            log_event("OTP required")
            return WorkflowStepResult(
                success=True,
                state=BookingState.OTP_REQUIRED,
                message=msg,
            )
        except Exception as exc:
            reason = f"Error at OTP stage: {exc}"
            self.sm.fail(reason)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

    def confirm_checkpoint_completed(self) -> WorkflowStepResult:
        """Transition state machine after human user completes a checkpoint in browser."""
        try:
            self._ensure_page()
            log_event("User continued")
            curr = self.sm.current_state

            if curr == BookingState.CAPTCHA_REQUIRED:
                # After solving CAPTCHA, IRCTC typically advances to Payment or OTP
                page = self._ensure_page()
                has_otp = False
                if page is not None and hasattr(page, "locator"):
                    has_otp = page.locator(
                        "input[placeholder*='OTP' i], "
                        "input#otp, "
                        "input#aadhaarOtp, "
                        "input#loginOtp, "
                        "[data-testid='otp-input']"
                    ).count() > 0
                if has_otp:
                    return self.wait_for_human_otp()
                else:
                    return self.open_payment()

            elif curr == BookingState.OTP_REQUIRED:
                # After human enters OTP in browser, verify outcome and transition
                page = self._ensure_page()
                err_loc = page.locator(".error-message:has-text('OTP'), .alert-danger:has-text('OTP'), div:has-text('Invalid OTP'), div:has-text('Incorrect OTP')")
                if err_loc.count() > 0 and err_loc.first.is_visible():
                    err_msg = err_loc.first.inner_text().strip()
                    msg = f"OTP Authentication failed: {err_msg}. Please re-enter in browser."
                    self._update_status(msg)
                    return WorkflowStepResult(success=False, state=BookingState.OTP_REQUIRED, message=msg)

                # If login OTP
                if "login" in page.url.lower() or page.locator("a:has-text('Logout'), span:has-text('Welcome')").count() > 0:
                    self.sm.transition_to(BookingState.USER_LOGGED_IN, "OTP authentication completed for login")
                    msg = "Login OTP verified successfully."
                    self._update_status(msg)
                    return WorkflowStepResult(success=True, state=BookingState.USER_LOGGED_IN, message=msg)

                # If booking / payment OTP, advance to Payment
                return self.open_payment()

            elif curr == BookingState.PAYMENT_REQUIRED:
                # After payment authorization in browser, advance to confirmation check
                self.sm.transition_to(BookingState.BOOKING_CONFIRMATION, "Payment authorized by user")
                msg = "Payment authorization submitted. Checking confirmation outcome."
                self._update_status(msg)
                return WorkflowStepResult(success=True, state=BookingState.BOOKING_CONFIRMATION, message=msg)

            else:
                return WorkflowStepResult(
                    success=True,
                    state=curr,
                    message=f"No active checkpoint pending in state {curr.name}.",
                )
        except Exception as exc:
            reason = f"Error confirming checkpoint: {exc}"
            self.sm.fail(reason)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=reason)

    def open_payment(self, payment_method: Optional[str] = None, upi_id: Optional[str] = None) -> WorkflowStepResult:
        """Navigate to the payment selection stage and select payment category.

        Optimized for IRCTC eWallet per Phase 17 specifications.
        Halts immediately when final payment authorization is required.
        """
        try:
            page = self._ensure_page()
            actual_method = payment_method or self.payment_mode or "IRCTC eWallet"
            actual_vpa = upi_id if upi_id is not None else self.upi_id

            if self.sm.current_state != BookingState.PAYMENT_REQUIRED:
                self.sm.transition_to(BookingState.PAYMENT_REQUIRED, f"Payment stage: {actual_method}")
            log_event("Payment stage")

            # Select payment category on page if present
            method_upper = actual_method.upper()

            # 1. IRCTC eWallet (Primary / Optimized)
            if "WALLET" in method_upper or "EWALLET" in method_upper:
                wallet_loc = page.locator(
                    "input[value='IRCTC_EWALLET'], "
                    "input[value*='ewallet' i], "
                    "label:has-text('IRCTC eWallet'), "
                    "label:has-text('eWallet'), "
                    "[data-testid='pay-ewallet'], "
                    "[data-testid='pay-wallet']"
                )
                if wallet_loc.count() > 0:
                    try:
                        wallet_loc.first.click()
                    except Exception:
                        pass

            # 2. BHIM / UPI
            elif "UPI" in method_upper:
                upi_btn = page.locator(
                    "input[value='2'], "
                    "label:has-text('BHIM/UPI'), "
                    "[data-testid='pay-upi'], "
                    "label:has-text('UPI')"
                )
                if upi_btn.count() > 0:
                    try:
                        upi_btn.first.click()
                    except Exception:
                        pass

                # Auto-fill user's saved UPI ID into the VPA input
                if actual_vpa:
                    try:
                        vpa_input = page.locator(
                            "input[placeholder*='vpa' i], "
                            "input[placeholder*='upi' i], "
                            "input#vpa, "
                            "input[name*='vpa' i], "
                            "[data-testid='vpa-input']"
                        ).first
                        if vpa_input.count() > 0:
                            vpa_input.fill(actual_vpa)
                    except Exception:
                        pass

            # 3. Credit Card / Payment Gateway
            elif "CARD" in method_upper or "NETBANKING" in method_upper:
                card_btn = page.locator(
                    "input[value='1'], "
                    "label:has-text('Credit Card'), "
                    "label:has-text('Multiple Payment Service'), "
                    "[data-testid='pay-cards']"
                )
                if card_btn.count() > 0:
                    try:
                        card_btn.first.click()
                    except Exception:
                        pass

            return self.wait_for_payment_authorization(actual_method)

        except Exception as exc:
            failure = classify_failure(exc, stage="payment")
            self.sm.fail(failure.message)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

    def wait_for_payment_authorization(self, payment_method: str = "IRCTC eWallet") -> WorkflowStepResult:
        """Stop automation at payment authorization checkpoint.

        Strictly enforces that human user enters eWallet PIN, card CVV, or banking OTP.
        Never automates financial authorization.
        """
        try:
            self._ensure_page()
            if self.sm.current_state != BookingState.PAYMENT_REQUIRED:
                self.sm.transition_to(BookingState.PAYMENT_REQUIRED, f"Payment authorization: {payment_method}")

            msg = (
                f"PAYMENT AUTHORIZATION REQUIRED ({payment_method}): "
                "Complete the payment in the browser (Never automated). "
                "Enter eWallet PIN / CVV / Banking OTP directly into the browser window."
            )
            self._update_status(msg)
            log_event("Payment authorization required")
            return WorkflowStepResult(
                success=True,
                state=BookingState.PAYMENT_REQUIRED,
                message=msg,
                details={"payment_method": payment_method},
            )
        except Exception as exc:
            failure = classify_failure(exc, stage="payment_authorization")
            self.sm.fail(failure.message)
            return WorkflowStepResult(success=False, state=BookingState.FAILURE, message=failure.message)

    # ==================== Step 5: Booking Confirmation ====================

    def verify_booking_result(
        self,
        is_confirmed: Optional[bool] = None,
        pnr: Optional[str] = None,
        trip: Optional[Trip] = None,
    ) -> WorkflowStepResult:
        """Verify the booking confirmation outcome from the browser or inspect page DOM.

        If ambiguous or uncertain, strictly sets UNKNOWN to prevent accidental re-bookings.
        """
        try:
            page = self._ensure_page()
            if self.sm.current_state != BookingState.BOOKING_CONFIRMATION:
                self.sm.transition_to(BookingState.BOOKING_CONFIRMATION, "Evaluating booking outcome")

            # 1. Direct explicit confirmation override
            if is_confirmed is True:
                confirmed_pnr = pnr or ""
                self.sm.transition_to(BookingState.SUCCESS, f"Booking successful, PNR: {confirmed_pnr}")
                msg = f"BOOKING SUCCESSFUL (PNR: {confirmed_pnr})" if confirmed_pnr else "BOOKING SUCCESSFUL"
                self._update_status(msg)
                return WorkflowStepResult(
                    success=True,
                    state=BookingState.SUCCESS,
                    message=msg,
                    details={"pnr": confirmed_pnr, "status": "SUCCESS"},
                )
            elif is_confirmed is False:
                reason = "Booking failed or rejected by IRCTC."
                self.sm.fail(reason)
                self._update_status(f"FAILED: {reason}")
                return WorkflowStepResult(
                    success=False,
                    state=BookingState.FAILURE,
                    message=reason,
                    details={"status": "FAILURE"},
                )

            # 2. Inspect active page content when is_confirmed is None
            if hasattr(page, "wait_for_selector"):
                try:
                    page.wait_for_selector(
                        "[data-testid='pnr-number'], #pnr, .pnr-bold, [data-testid='booking-failure'], .error-message",
                        timeout=1500,
                    )
                except Exception:
                    pass

            page_text = ""
            try:
                page_text = page.inner_text("body")
            except Exception:
                pass

            # A. Check for explicit failure messages first
            # Check explicit failure selectors first (they contain the full detailed error message)
            failure_loc = page.locator("[data-testid='booking-failure'], .error-message, .alert-danger")
            if failure_loc.count() > 0 and failure_loc.first.is_visible():
                fail_text = failure_loc.first.inner_text().strip()
                if fail_text:
                    reason = f"Booking rejected: {fail_text}."
                    self.sm.fail(reason)
                    self._update_status(f"FAILED: {reason}")
                    return WorkflowStepResult(
                        success=False,
                        state=BookingState.FAILURE,
                        message=reason,
                        details={"status": "FAILURE", "reason": fail_text},
                    )

            failure_patterns = [
                r"Payment\s+Failed",
                r"Transaction\s+Failed",
                r"Booking\s+Failed",
                r"Payment\s+Declined",
                r"Quota\s+Exhausted",
                r"\bREGRET\b",
                r"Session\s+Expired",
                r"Bank\s+transaction\s+cancelled",
                r"Payment\s+timed?\s*out",
                r"Ticket\s+not\s+booked",
                r"No\s+Seats\s+Available",
                r"Transaction\s+declined",
            ]
            for pat in failure_patterns:
                line_pat = rf"([^\n\r]*(?:{pat})[^\n\r]*)"
                match = re.search(line_pat, page_text, re.IGNORECASE)
                if match:
                    found_msg = match.group(1).strip()
                    reason = f"Booking rejected: {found_msg}."
                    self.sm.fail(reason)
                    self._update_status(f"FAILED: {reason}")
                    return WorkflowStepResult(
                        success=False,
                        state=BookingState.FAILURE,
                        message=reason,
                        details={"status": "FAILURE", "reason": found_msg},
                    )

            # B. Check for explicit success / 10-digit PNR
            extracted_pnr = pnr or ""
            if not extracted_pnr:
                pnr_loc = page.locator("[data-testid='pnr-number'], #pnr, .pnr-bold")
                if pnr_loc.count() > 0:
                    cand = pnr_loc.first.inner_text().strip()
                    m = re.search(r"\b\d{10}\b", cand)
                    if m:
                        extracted_pnr = m.group(0)

            if not extracted_pnr:
                m = re.search(r"(?:PNR\s*(?:No\.?|Number)?[\s:]*|pnr\b[^0-9]{0,10})(\d{10})\b", page_text, re.IGNORECASE)
                if m:
                    extracted_pnr = m.group(1)

            # Check for transaction ID
            txn_id = ""
            txn_loc = page.locator("[data-testid='txn-id'], [data-testid='transaction-id'], #txnId, #transactionId")
            if txn_loc.count() > 0:
                txn_id = txn_loc.first.inner_text().strip()
            if not txn_id:
                m_txn = re.search(r"(?:Transaction|Txn)\s*(?:ID|No\.?|Number)?[\s:]*([A-Za-z0-9_-]+)", page_text, re.IGNORECASE)
                if m_txn:
                    txn_id = m_txn.group(1).strip()

            # Check for fare
            fare = 0.0
            fare_loc = page.locator("[data-testid='total-fare'], #totalFare")
            if fare_loc.count() > 0:
                m_fare = re.search(r"([0-9]+(?:\.[0-9]{2})?)", fare_loc.first.inner_text())
                if m_fare:
                    fare = float(m_fare.group(1))
            if fare == 0.0:
                m_fare = re.search(r"(?:Total Fare|Amount Paid|Ticket Fare)[^\d]*([0-9]+(?:\.[0-9]{2})?)", page_text, re.IGNORECASE)
                if m_fare:
                    fare = float(m_fare.group(1))

            # Check for allocated passengers
            passengers_info = []
            pass_rows = page.locator("[data-testid='allocated-passengers'] tr, table.passenger-table tbody tr")
            if pass_rows.count() > 0:
                for i in range(pass_rows.count()):
                    row_txt = pass_rows.nth(i).inner_text().strip()
                    if row_txt:
                        passengers_info.append({"row": row_txt})

            if extracted_pnr:
                self.sm.transition_to(BookingState.SUCCESS, f"Booking successful, PNR: {extracted_pnr}")
                msg = f"BOOKING SUCCESSFUL: Booking confirmed! PNR: {extracted_pnr}"
                self._update_status(msg)
                return WorkflowStepResult(
                    success=True,
                    state=BookingState.SUCCESS,
                    message=msg,
                    details={
                        "status": "SUCCESS",
                        "pnr": extracted_pnr,
                        "transaction_id": txn_id,
                        "fare": fare,
                        "passengers": passengers_info,
                    },
                )

            # C. Ambiguous / Unknown Outcome
            reason = "Booking status is uncertain. Verify IRCTC booking history before attempting another booking."
            self.sm.set_unknown(reason)
            self._update_status(f"STATUS UNCERTAIN: {reason}")
            return WorkflowStepResult(
                success=False,
                state=BookingState.UNKNOWN,
                message=reason,
                details={
                    "status": "UNKNOWN",
                    "transaction_id": txn_id,
                    "fare": fare,
                },
            )

        except Exception as exc:
            reason = "Booking status is uncertain. Verify IRCTC booking history before attempting another booking."
            self.sm.set_unknown(reason)
            return WorkflowStepResult(success=False, state=BookingState.UNKNOWN, message=reason)

    def save_booking_result(
        self,
        db: Any,
        trip: Trip,
        step_result: WorkflowStepResult,
    ) -> BookingRecord:
        """Create and persist a BookingRecord in the local SQLite database."""
        details = step_result.details or {}
        pnr = details.get("pnr") or ""
        txn_id = details.get("transaction_id") or ""
        fare = float(details.get("fare") or details.get("total_fare") or 0.0)
        passengers = details.get("passengers") or ""
        if isinstance(passengers, (list, dict)):
            passengers = json.dumps(passengers)

        record = BookingRecord(
            trip_id=trip.id,
            pnr=pnr,
            train_number=trip.train_number,
            train_name=trip.train_name,
            class_code=trip.class_code,
            quota_code=trip.quota,
            from_station=trip.from_station,
            to_station=trip.to_station,
            journey_date=trip.journey_date,
            status=step_result.state.name,
            transaction_id=txn_id,
            total_fare=fare,
            passenger_details=passengers,
            status_message=step_result.message,
        )
        return db.create_booking(record)

