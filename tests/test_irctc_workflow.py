"""Unit tests for Phase 11 IRCTC Workflow Abstraction."""

from datetime import date, timedelta
import pytest
from playwright.sync_api import sync_playwright

from browser.irctc_workflow import IRCTCWorkflow, WorkflowStepResult
from core.booking_state import BookingState, BookingStateMachine
from models.passenger import Passenger
from models.trip import Trip


@pytest.fixture(scope="module")
def browser_page():
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("data:text/html,<html><head><title>IRCTC Mock</title></head><body><h1>IRCTC</h1></body></html>")
    yield page
    page.close()
    browser.close()
    p.stop()


@pytest.fixture
def workflow(browser_page):
    sm = BookingStateMachine()
    return IRCTCWorkflow(page=browser_page, state_machine=sm)


# ==================== Step-by-Step Flow Tests ====================


def test_open_booking_page(workflow):
    res = workflow.open_booking_page(url="data:text/html,<html><body>Booking</body></html>")
    assert res.success is True
    assert res.state == BookingState.BROWSER_READY
    assert workflow.sm.current_state == BookingState.BROWSER_READY


def test_check_login_status_not_logged_in(workflow):
    workflow.open_booking_page(url="data:text/html,<html><body>No Login</body></html>")
    res = workflow.check_login_status()
    assert res.success is True
    assert res.state == BookingState.USER_LOGIN_REQUIRED
    assert workflow.sm.current_state == BookingState.USER_LOGIN_REQUIRED


def test_check_login_status_logged_in(workflow, browser_page):
    browser_page.goto("data:text/html,<html><body><button>Logout</button></body></html>")
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    res = workflow.check_login_status()
    assert res.success is True
    assert res.state == BookingState.USER_LOGGED_IN
    assert workflow.sm.current_state == BookingState.USER_LOGGED_IN


def test_complete_booking_workflow_stages(workflow):
    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(from_station="NDLS", to_station="CNB", journey_date=tomorrow, train_number="12004", class_code="3A")
    passengers = [Passenger(name="Ravi Kumar", age=30, gender="M", berth_preference="LB")]

    # 1. Open
    workflow.open_booking_page(url="data:text/html,<html><body>IRCTC</body></html>")
    assert workflow.sm.current_state == BookingState.BROWSER_READY

    # 2. Login
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)

    # 3. Journey Selection
    res_journey = workflow.select_journey(trip)
    assert res_journey.success is True
    assert workflow.sm.current_state == BookingState.JOURNEY_SELECTION

    # 4. Quota Selection
    res_quota = workflow.select_quota("TATKAL")
    assert res_quota.success is True

    # 5. Train Selection
    res_train = workflow.select_train(trip.train_number)
    assert res_train.success is True
    assert workflow.sm.current_state == BookingState.TRAIN_SELECTION

    # 6. Class Selection
    res_class = workflow.select_class(trip.class_code)
    assert res_class.success is True

    # 7. Passenger Selection
    res_passengers = workflow.select_passengers(passengers)
    assert res_passengers.success is True
    assert workflow.sm.current_state == BookingState.PASSENGER_SELECTION

    # 8. Review
    res_review = workflow.review_booking()
    assert res_review.success is True
    assert workflow.sm.current_state == BookingState.REVIEW

    # 9. Human CAPTCHA Checkpoint
    res_captcha = workflow.wait_for_human_captcha()
    assert res_captcha.success is True
    assert workflow.sm.current_state == BookingState.CAPTCHA_REQUIRED

    # 10. Payment
    res_payment = workflow.open_payment("IRCTC eWallet")
    assert res_payment.success is True
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED

    # 11. Payment Authorization
    res_auth = workflow.wait_for_payment_authorization()
    assert res_auth.success is True
    assert workflow.sm.current_state == BookingState.PAYMENT_REQUIRED

    # 12. Confirmation & Success
    res_confirm = workflow.verify_booking_result(is_confirmed=True, pnr="2456789123")
    assert res_confirm.success is True
    assert res_confirm.state == BookingState.SUCCESS
    assert workflow.sm.current_state == BookingState.SUCCESS
    assert res_confirm.details["pnr"] == "2456789123"


# ==================== Unexpected State & Failure Tests ====================


def test_select_passengers_over_limit_fails(workflow):
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    too_many = [Passenger(name=f"User {i}", age=20 + i, gender="M") for i in range(5)]
    res = workflow.select_passengers(too_many)

    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert workflow.sm.current_state == BookingState.FAILURE
    assert "max 4 passengers" in res.message


def test_select_passengers_empty_fails(workflow):
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)

    res = workflow.select_passengers([])
    assert res.success is False
    assert res.state == BookingState.FAILURE
    assert workflow.sm.current_state == BookingState.FAILURE


def test_ambiguous_payment_result_transitions_to_unknown(workflow):
    # Reach payment required state
    workflow.sm.transition_to(BookingState.BROWSER_READY)
    workflow.sm.transition_to(BookingState.USER_LOGGED_IN)
    workflow.sm.transition_to(BookingState.JOURNEY_SELECTION)
    workflow.sm.transition_to(BookingState.TRAIN_SELECTION)
    workflow.sm.transition_to(BookingState.PASSENGER_SELECTION)
    workflow.sm.transition_to(BookingState.REVIEW)
    workflow.sm.transition_to(BookingState.PAYMENT_REQUIRED)

    # Outcome is neither confirmed nor rejected (ambiguous gateway timeout)
    res = workflow.verify_booking_result(is_confirmed=None)
    assert res.success is False
    assert res.state == BookingState.UNKNOWN
    assert workflow.sm.current_state == BookingState.UNKNOWN
    assert "uncertain" in res.message
