"""Database unit tests for bookings table CRUD operations."""

from datetime import date
import pytest

from database.db import Database
from models.booking import BookingRecord


@pytest.fixture
def db():
    return Database(":memory:")


def test_create_and_load_booking(db):
    rec = BookingRecord(
        train_number="12424",
        class_code="3A",
        quota_code="TATKAL",
        from_station="NDLS",
        to_station="DBRG",
        journey_date=date(2026, 10, 20),
        status="SUCCESS",
        pnr="1234567890",
        train_name="Rajdhani",
        transaction_id="TXN112233",
        total_fare=2500.0,
        status_message="Confirmed",
    )
    saved = db.create_booking(rec)
    assert saved.id is not None

    loaded = db.load_booking(saved.id)
    assert loaded is not None
    assert loaded.id == saved.id
    assert loaded.train_number == "12424"
    assert loaded.pnr == "1234567890"
    assert loaded.total_fare == 2500.0
    assert loaded.status == "SUCCESS"


def test_list_bookings_order(db):
    b1 = BookingRecord(
        train_number="12004",
        class_code="CC",
        quota_code="TATKAL",
        from_station="NDLS",
        to_station="LKO",
        journey_date="2026-10-21",
        status="FAILURE",
        status_message="Payment timed out",
    )
    b2 = BookingRecord(
        train_number="12424",
        class_code="3A",
        quota_code="TATKAL",
        from_station="NDLS",
        to_station="DBRG",
        journey_date="2026-10-22",
        status="SUCCESS",
        pnr="9876543210",
    )
    db.create_booking(b1)
    db.create_booking(b2)

    bookings = db.list_bookings()
    assert len(bookings) == 2
    # Latest first
    assert bookings[0].train_number == "12424"
    assert bookings[1].train_number == "12004"


def test_get_booking_by_pnr(db):
    rec = BookingRecord(
        train_number="12424",
        class_code="3A",
        quota_code="TATKAL",
        from_station="NDLS",
        to_station="DBRG",
        journey_date="2026-10-20",
        status="SUCCESS",
        pnr="1122334455",
    )
    db.create_booking(rec)

    found = db.get_booking_by_pnr("1122334455")
    assert found is not None
    assert found.train_number == "12424"

    not_found = db.get_booking_by_pnr("9999999999")
    assert not_found is None


def test_get_latest_booking(db):
    assert db.get_latest_booking() is None

    b1 = BookingRecord(
        train_number="12004",
        class_code="CC",
        quota_code="TATKAL",
        from_station="NDLS",
        to_station="LKO",
        journey_date="2026-10-21",
        status="UNKNOWN",
    )
    db.create_booking(b1)
    latest = db.get_latest_booking()
    assert latest is not None
    assert latest.train_number == "12004"
    assert latest.status == "UNKNOWN"


def test_update_and_delete_booking(db):
    rec = BookingRecord(
        train_number="12004",
        class_code="CC",
        quota_code="TATKAL",
        from_station="NDLS",
        to_station="LKO",
        journey_date="2026-10-21",
        status="UNKNOWN",
    )
    saved = db.create_booking(rec)

    saved.status = "SUCCESS"
    saved.pnr = "5566778899"
    saved.total_fare = 1200.0
    updated = db.update_booking(saved)
    assert updated is True

    reloaded = db.load_booking(saved.id)
    assert reloaded.status == "SUCCESS"
    assert reloaded.pnr == "5566778899"
    assert reloaded.total_fare == 1200.0

    deleted = db.delete_booking(saved.id)
    assert deleted is True
    assert db.load_booking(saved.id) is None
