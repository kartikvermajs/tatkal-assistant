"""Comprehensive unit and integration tests for Phase 12 Journey Preparation."""

import ast
from datetime import date, timedelta
import glob
import os
import pytest
from playwright.sync_api import sync_playwright

import config
from browser.irctc_workflow import IRCTCWorkflow, WorkflowStepResult
from core.booking_state import BookingState, BookingStateMachine
from models.passenger import Passenger
from models.trip import Trip
from ui.booking_review_dialog import BookingReviewDialog


@pytest.fixture(scope="module")
def browser_page():
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    yield page
    page.close()
    browser.close()
    p.stop()


@pytest.fixture
def workflow(browser_page):
    sm = BookingStateMachine()
    return IRCTCWorkflow(page=browser_page, state_machine=sm)


# ==================== 1. Centralized IRCTC URLs ====================


def test_centralized_irctc_urls_in_config():
    """Ensure all IRCTC URLs reside in config.py and are not duplicated or hardcoded elsewhere."""
    assert hasattr(config, "IRCTC_BASE_URL")
    assert hasattr(config, "IRCTC_BOOKING_URL")
    assert hasattr(config, "IRCTC_LOGIN_URL")
    assert config.IRCTC_BASE_URL.startswith("https://www.irctc.co.in/")
    assert config.IRCTC_BOOKING_URL.startswith("https://www.irctc.co.in/")
    assert config.IRCTC_LOGIN_URL.startswith("https://www.irctc.co.in/")

    # Scan project source files (excluding config.py and tests) for hardcoded irctc URLs
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for root, _, files in os.walk(project_root):
        if ".venv" in root or "__pycache__" in root or "tests" in root:
            continue
        for file in files:
            if file.endswith(".py") and file != "config.py":
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    # Check for hardcoded literal URL string "https://www.irctc.co.in"
                    assert "https://www.irctc.co.in" not in content, (
                        f"Hardcoded IRCTC URL found in {file_path}. All URLs must be imported from config.py"
                    )


def test_open_booking_page_uses_centralized_config_url():
    """Verify open_booking_page uses config.IRCTC_BOOKING_URL when url is None."""
    navigated_urls = []

    class MockPage:
        def __init__(self):
            self.url = config.IRCTC_BOOKING_URL

        def is_closed(self):
            return False

        def goto(self, url, **kwargs):
            navigated_urls.append(url)

    mock_page = MockPage()
    wf = IRCTCWorkflow(page=mock_page)
    res = wf.open_booking_page()
    assert res.success is True
    assert navigated_urls == [config.IRCTC_BOOKING_URL]


# ==================== 2. Mandatory Train Number ====================


def test_select_journey_missing_train_number_fails(workflow):
    """select_journey must fail immediately if train number is missing."""
    tomorrow = date.today() + timedelta(days=1)
    # Trip bypasses init validation for testing workflow defense
    trip = Trip(from_station="NDLS", to_station="CNB", journey_date=tomorrow, train_number="12424", class_code="3A")
    trip.train_number = ""

    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    res = workflow.select_journey(trip)

    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert workflow.sm.current_state == BookingState.FAILURE
    assert "Train number is mandatory" in res.message


def test_select_train_empty_fails(workflow):
    """select_train must fail immediately if train_number is empty."""
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)

    res = workflow.select_train("")
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert "Train number is mandatory" in res.message


def test_select_train_not_found_on_page_fails_without_substitution(workflow, browser_page):
    """If specified train is not in the search results, stop and fail. Never substitute."""
    # Render mock search results containing trains 12004 and 12555, but NOT 12424
    html = """
    <html>
      <body>
        <div class="train-item"><h3>12004 - Shatabdi Express</h3></div>
        <div class="train-item"><h3>12555 - Gorakhdham Express</h3></div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)

    res = workflow.select_train("12424")
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert "Specified train '12424' was not found on results page. Substitution is prohibited." in res.message


def test_select_train_found_on_page_succeeds(workflow, browser_page):
    """When the specified train is found on the page, select it successfully."""
    html = """
    <html>
      <body>
        <div class="train-item"><h3>12424 - Rajdhani Express</h3></div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)

    res = workflow.select_train("12424")
    assert res.success is True
    assert res.state == BookingState.TRAIN_SELECTION
    assert res.details["train_number"] == "12424"


# ==================== 3. Mandatory Train Class / Type ====================


def test_human_readable_class_mapping():
    """Verify human-readable train class names and internal IRCTC codes."""
    expected_mappings = [
        ("Sleeper (SL)", "SL"),
        ("AC 3 Tier (3A)", "3A"),
        ("AC 2 Tier (2A)", "2A"),
        ("AC First Class (1A)", "1A"),
        ("Chair Car (CC)", "CC"),
        ("Executive Chair Car (EC)", "EC"),
        ("Second Sitting (2S)", "2S"),
    ]
    for human_name, code in expected_mappings:
        assert config.get_class_code(human_name) == code
        assert config.get_class_display_name(code) == human_name

    # Codes also map to themselves via get_class_code
    for _, code in expected_mappings:
        assert config.get_class_code(code) == code


def test_select_journey_missing_class_fails(workflow):
    """select_journey must fail immediately if class code is missing."""
    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(from_station="NDLS", to_station="CNB", journey_date=tomorrow, train_number="12424", class_code="3A")
    trip.class_code = ""

    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    res = workflow.select_journey(trip)

    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert "Train class/type is mandatory" in res.message


def test_select_class_empty_fails(workflow):
    """select_class must fail immediately if class_code is empty."""
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    res = workflow.select_class("")
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert "Train class/type is mandatory" in res.message


def test_select_class_not_found_on_page_fails(workflow, browser_page):
    """If specified class is not available under the train, fail without default substitution."""
    html = """
    <html>
      <body>
        <div class="train-item">
          <h3>12424</h3>
          <div class="class-item"><button>SL</button></div>
          <div class="class-item"><button>2A</button></div>
        </div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    # 3A is requested but only SL and 2A exist
    res = workflow.select_class("3A")
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert "AC 3 Tier (3A)" in res.message
    assert "not found" in res.message


def test_select_class_found_on_page_succeeds(workflow, browser_page):
    """When specified class is available, select it."""
    html = """
    <html>
      <body>
        <div class="train-item">
          <h3>12424</h3>
          <div class="class-item"><button data-class="3A">3A</button></div>
        </div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    res = workflow.select_class("3A")
    assert res.success is True
    assert res.details["class_code"] == "3A"
    assert res.details["class_name"] == "AC 3 Tier (3A)"


# ==================== 4. Status Updates & Field Population ====================


def test_journey_prep_emits_status_updates(workflow, browser_page):
    """Status updates 'Selecting journey...', 'Selecting train...', 'Selecting class...' must be emitted."""
    status_history = []
    workflow.set_status_callback(lambda msg: status_history.append(msg))

    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(from_station="NDLS", to_station="LKO", journey_date=tomorrow, train_number="12424", class_code="3A")
    passengers = [Passenger(name="Asha Devi", age=50, gender="F")]

    html = """
    <html>
      <body>
        <input placeholder="From*" />
        <input placeholder="To*" />
        <input placeholder="Journey Date" />
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)

    res = workflow.prepare_journey(trip, passengers)
    assert res.success is True

    # Verify key status updates were emitted
    assert any("Selecting journey..." in s for s in status_history)
    assert any("Selecting train 12424..." in s for s in status_history)
    assert any("Selecting class AC 3 Tier (3A) (3A)..." in s for s in status_history)


def test_select_journey_populates_visible_fields(workflow, browser_page):
    """Verify journey inputs on the page are populated visible to the user."""
    html = """
    <html>
      <body>
        <input id="origin" placeholder="From*" />
        <input id="destination" placeholder="To*" />
        <input id="journeyDate" placeholder="Date" />
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)

    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(from_station="NDLS", to_station="CNB", journey_date=tomorrow, train_number="12004", class_code="CC")

    res = workflow.select_journey(trip)
    assert res.success is True

    # Inspect field values in browser DOM
    assert browser_page.locator("#origin").input_value() == "NDLS"
    assert browser_page.locator("#destination").input_value() == "CNB"
    assert browser_page.locator("#journeyDate").input_value() == tomorrow.isoformat()


def test_select_journey_on_error_page_stops(workflow, browser_page):
    """If page is in an unexpected error state, automation stops immediately."""
    html = "<html><head><title>500 Internal Error</title></head><body><h1>Server Error</h1></body></html>"
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)

    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(from_station="NDLS", to_station="CNB", journey_date=tomorrow, train_number="12004", class_code="CC")

    res = workflow.select_journey(trip)
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert "error page encountered" in res.message


# ==================== 5. Booking Review & Confirmation ====================


def test_review_booking_displays_train_and_class(workflow):
    """review_booking must return and display train number and human-readable class name."""
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)

    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(from_station="NDLS", to_station="LKO", journey_date=tomorrow, train_number="12424", class_code="3A")
    passengers = [Passenger(name="Amit Shah", age=45, gender="M")]

    res = workflow.review_booking(trip=trip, passengers=passengers)
    assert res.success is True
    assert res.state == BookingState.REVIEW
    assert "12424" in res.message
    assert "AC 3 Tier (3A)" in res.message
    assert res.details["train_number"] == "12424"
    assert res.details["class_code"] == "3A"
    assert res.details["class_name"] == "AC 3 Tier (3A)"


def test_booking_review_dialog_display(qapp):
    """Test that BookingReviewDialog displays train number, class human name, and details."""
    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(from_station="NDLS", to_station="LKO", journey_date=tomorrow, train_number="12424", class_code="3A")
    passengers = [Passenger(name="Amit Shah", age=45, gender="M", berth_preference="LB")]

    dialog = BookingReviewDialog(trip=trip, passengers=passengers)
    assert dialog.train_label.text() == "12424"
    assert "AC 3 Tier (3A) (3A)" in dialog.class_label.text()
    assert dialog.confirm_btn.isEnabled() is True
    dialog.close()


def test_booking_review_dialog_blocks_if_train_number_missing(qapp):
    """BookingReviewDialog must disable confirm button if train number is missing."""
    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(from_station="NDLS", to_station="LKO", journey_date=tomorrow, train_number="12424", class_code="3A")
    trip.train_number = ""

    dialog = BookingReviewDialog(trip=trip, passengers=[])
    assert dialog.confirm_btn.isEnabled() is False
    assert "Train Number is mandatory" in dialog.validation_error_label.text()
    dialog.close()
