"""Comprehensive unit and integration tests for Phase 13 Passenger Details Automation."""

from datetime import date, timedelta
import pytest
from playwright.sync_api import sync_playwright

import config
from browser.irctc_workflow import IRCTCWorkflow
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


# ==================== 1. Passenger Details Input Automation ====================


def test_populate_single_passenger_details(workflow, browser_page):
    """Verify single passenger name, age, gender, and berth choice are populated in DOM."""
    html = """
    <html>
      <body>
        <div id="passenger-section">
          <input placeholder="Passenger Name" data-testid="passenger-name-0" />
          <input placeholder="Age" data-testid="passenger-age-0" />
          <select data-testid="passenger-gender-0">
            <option value="">Select</option>
            <option value="M">Male</option>
            <option value="F">Female</option>
          </select>
          <select data-testid="passenger-berth-0">
            <option value="NONE">No Preference</option>
            <option value="LB">Lower</option>
            <option value="UB">Upper</option>
          </select>
        </div>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    p = Passenger(name="Vikram Singh", age=34, gender="M", berth_preference="LB")
    res = workflow.select_passengers([p])

    assert res.success is True
    assert res.state == BookingState.PASSENGER_SELECTION
    assert workflow.sm.current_state == BookingState.PASSENGER_SELECTION

    # Verify DOM values
    assert browser_page.locator("[data-testid='passenger-name-0']").input_value() == "Vikram Singh"
    assert browser_page.locator("[data-testid='passenger-age-0']").input_value() == "34"
    assert browser_page.locator("[data-testid='passenger-gender-0']").input_value() == "M"
    assert browser_page.locator("[data-testid='passenger-berth-0']").input_value() == "LB"


def test_populate_multiple_passengers_with_add_button(workflow, browser_page):
    """Verify multiple passengers trigger '+ Add Passenger' and populate rows sequentially."""
    html = """
    <html>
      <body>
        <div id="passenger-section">
          <div class="passenger-row" id="row-0">
            <input placeholder="Passenger Name" data-testid="passenger-name-0" />
            <input placeholder="Age" data-testid="passenger-age-0" />
            <select data-testid="passenger-gender-0">
              <option value="M">Male</option>
              <option value="F">Female</option>
            </select>
            <select data-testid="passenger-berth-0">
              <option value="NONE">No Preference</option>
              <option value="LB">Lower</option>
              <option value="MB">Middle</option>
            </select>
          </div>
        </div>
        <button id="add-btn" data-testid="add-passenger-btn" onclick="addRow()">+ Add Passenger</button>
        <script>
          let count = 1;
          function addRow() {
            if (count >= 4) return;
            const container = document.getElementById('passenger-section');
            const row = document.createElement('div');
            row.className = 'passenger-row';
            row.id = 'row-' + count;
            row.innerHTML = `
              <input placeholder="Passenger Name" data-testid="passenger-name-${count}" />
              <input placeholder="Age" data-testid="passenger-age-${count}" />
              <select data-testid="passenger-gender-${count}">
                <option value="M">Male</option>
                <option value="F">Female</option>
              </select>
              <select data-testid="passenger-berth-${count}">
                <option value="NONE">No Preference</option>
                <option value="LB">Lower</option>
                <option value="MB">Middle</option>
              </select>
            `;
            container.appendChild(row);
            count++;
          }
        </script>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    passengers = [
        Passenger(name="Ravi Kumar", age=32, gender="M", berth_preference="LB"),
        Passenger(name="Sunita Kumar", age=29, gender="F", berth_preference="MB"),
        Passenger(name="Aarav Kumar", age=8, gender="M", berth_preference="NONE"),
    ]

    status_messages = []
    workflow.set_status_callback(lambda msg: status_messages.append(msg))

    res = workflow.select_passengers(passengers)
    assert res.success is True
    assert res.state == BookingState.PASSENGER_SELECTION
    assert len(res.details["passengers"]) == 3

    # Check DOM populated for each passenger
    assert browser_page.locator("[data-testid='passenger-name-0']").input_value() == "Ravi Kumar"
    assert browser_page.locator("[data-testid='passenger-name-1']").input_value() == "Sunita Kumar"
    assert browser_page.locator("[data-testid='passenger-name-2']").input_value() == "Aarav Kumar"

    assert browser_page.locator("[data-testid='passenger-age-1']").input_value() == "29"
    assert browser_page.locator("[data-testid='passenger-gender-1']").input_value() == "F"

    # Status messages check
    assert any("Populating passenger 1: Ravi Kumar" in m for m in status_messages)
    assert any("Populating passenger 2: Sunita Kumar" in m for m in status_messages)
    assert any("Populating passenger 3: Aarav Kumar" in m for m in status_messages)


def test_populate_contact_and_travel_preferences(workflow, browser_page):
    """Verify contact mobile number, auto-upgradation, confirm berths, and payment mode options."""
    html = """
    <html>
      <body>
        <input placeholder="Passenger Name" data-testid="passenger-name-0" />
        <input placeholder="Age" data-testid="passenger-age-0" />
        <select data-testid="passenger-gender-0"><option value="M">Male</option></select>
        <select data-testid="passenger-berth-0"><option value="NONE">No</option></select>

        <input placeholder="Mobile Number" data-testid="mobile-number" />
        <input type="checkbox" id="autoUpgradation" data-testid="auto-upgradation" />
        <input type="checkbox" id="confirmBerths" data-testid="confirm-berths" />
        <input type="radio" name="payment" value="2" data-testid="pay-upi" />
        <input type="radio" name="payment" value="1" data-testid="pay-cards" />
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    p = Passenger(name="Devendra", age=40, gender="M")
    res = workflow.select_passengers(
        [p],
        mobile_number="9876543210",
        auto_upgradation=True,
        confirm_berths_only=True,
        payment_mode="UPI",
    )

    assert res.success is True
    assert browser_page.locator("[data-testid='mobile-number']").input_value() == "9876543210"
    assert browser_page.locator("[data-testid='auto-upgradation']").is_checked() is True
    assert browser_page.locator("[data-testid='confirm-berths']").is_checked() is True
    assert browser_page.locator("[data-testid='pay-upi']").is_checked() is True


# ==================== 2. Safety & Error Guards ====================


def test_passenger_tatkal_max_limit_enforced(workflow):
    """Attempting to provide more than 4 passengers must fail immediately."""
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    passengers = [Passenger(name=f"Person {i}", age=25 + i, gender="M") for i in range(5)]
    res = workflow.select_passengers(passengers)

    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert workflow.sm.current_state == BookingState.FAILURE
    assert "max 4 passengers" in res.message


def test_passenger_empty_list_fails(workflow):
    """Attempting to provide 0 passengers must fail immediately."""
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    res = workflow.select_passengers([])

    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert "No passengers provided" in res.message


def test_unexpected_error_page_aborts_passenger_entry(workflow, browser_page):
    """If an error page is encountered, passenger automation must stop immediately without clicking."""
    html = "<html><head><title>500 Internal Server Error</title></head><body>Error</body></html>"
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    p = Passenger(name="Test User", age=25, gender="M")
    res = workflow.select_passengers([p])

    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert "error page encountered" in res.message


# ==================== 3. Composite prepare_journey Integration ====================


def test_prepare_journey_composite_flow(workflow, browser_page):
    """Verify prepare_journey executes journey, train, class, and passengers up to review."""
    html = """
    <html>
      <body>
        <input placeholder="From*" />
        <input placeholder="To*" />
        <input placeholder="Date" />
        <div class="train-item"><h3>12424</h3></div>
        <div class="class-item"><button data-class="3A">3A</button></div>
        <input placeholder="Passenger Name" data-testid="passenger-name-0" />
        <input placeholder="Age" data-testid="passenger-age-0" />
        <select data-testid="passenger-gender-0"><option value="M">Male</option></select>
        <select data-testid="passenger-berth-0"><option value="LB">Lower</option></select>
      </body>
    </html>
    """
    browser_page.goto(f"data:text/html,{html}")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)

    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(from_station="NDLS", to_station="LKO", journey_date=tomorrow, train_number="12424", class_code="3A")
    passengers = [Passenger(name="Deepak", age=31, gender="M", berth_preference="LB")]

    res = workflow.prepare_journey(
        trip=trip,
        passengers=passengers,
        mobile_number="9876543210",
        auto_upgradation=True,
    )

    assert res.success is True
    assert res.state == BookingState.REVIEW
    assert workflow.sm.current_state == BookingState.REVIEW
    assert res.details["train_number"] == "12424"
    assert res.details["class_code"] == "3A"
    assert len(res.details["passengers"]) == 1


# ==================== 4. Booking Review Dialog Display ====================


def test_booking_review_dialog_displays_preferences(qapp):
    """BookingReviewDialog must display contact mobile and travel preferences."""
    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(from_station="NDLS", to_station="CNB", journey_date=tomorrow, train_number="12004", class_code="CC")
    passengers = [Passenger(name="Meena", age=26, gender="F", berth_preference="WS")]

    dialog = BookingReviewDialog(
        trip=trip,
        passengers=passengers,
        mobile_number="9123456780",
        auto_upgradation=True,
        confirm_berths_only=True,
        payment_mode="UPI",
    )

    assert dialog.mobile_label.text() == "9123456780"
    assert "Auto-Upgradation: Yes" in dialog.pref_label.text()
    assert "Confirm Berths Only: Yes" in dialog.pref_label.text()
    assert "Payment Mode: UPI" in dialog.payment_label.text()
    assert dialog.confirm_btn.isEnabled() is True
    dialog.close()
