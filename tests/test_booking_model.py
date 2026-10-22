"""Unit tests for BookingRecord model."""

from datetime import date
import json
import pytest

from models.booking import BookingRecord


def test_booking_record_valid_creation():
    rec = BookingRecord(
        train_number="12424",
        class_code="3A",
        quota_code="TATKAL",
        from_station="NDLS",
        to_station="DBRG",
        journey_date=date(2026, 10, 20),
        status="SUCCESS",
        pnr="1234567890",
        train_name="Rajdhani Exp",
        transaction_id="TXN987654",
        total_fare=2450.50,
        passenger_details=json.dumps([{"name": "Alice", "status": "CNF", "berth": "B4 42"}]),
        status_message="Booking confirmed successfully",
    )
    assert rec.train_number == "12424"
    assert rec.class_code == "3A"
    assert rec.quota_code == "TATKAL"
    assert rec.from_station == "NDLS"
    assert rec.to_station == "DBRG"
    assert rec.journey_date_str == "2026-10-20"
    assert rec.status == "SUCCESS"
    assert rec.pnr == "1234567890"
    assert rec.is_confirmed is True
    assert rec.total_fare == 2450.50
    passengers = rec.get_parsed_passengers()
    assert len(passengers) == 1
    assert passengers[0]["name"] == "Alice"


def test_booking_record_invalid_status_raises():
    with pytest.raises(ValueError, match="Invalid booking status"):
        BookingRecord(
            train_number="12424",
            class_code="3A",
            quota_code="TATKAL",
            from_station="NDLS",
            to_station="DBRG",
            journey_date="2026-10-20",
            status="INVALID_STATUS",
        )


def test_booking_record_invalid_pnr_raises():
    with pytest.raises(ValueError, match="PNR must be exactly 10 digits"):
        BookingRecord(
            train_number="12424",
            class_code="3A",
            quota_code="TATKAL",
            from_station="NDLS",
            to_station="DBRG",
            journey_date="2026-10-20",
            status="SUCCESS",
            pnr="12345",  # Too short
        )


def test_booking_record_negative_fare_raises():
    with pytest.raises(ValueError, match="Total fare cannot be negative"):
        BookingRecord(
            train_number="12424",
            class_code="3A",
            quota_code="TATKAL",
            from_station="NDLS",
            to_station="DBRG",
            journey_date="2026-10-20",
            total_fare=-10.0,
        )


def test_booking_record_serialization_roundtrip():
    original = BookingRecord(
        train_number="12004",
        class_code="CC",
        quota_code="TATKAL",
        from_station="NDLS",
        to_station="LKO",
        journey_date="2026-10-22",
        status="UNKNOWN",
        transaction_id="TXN_PENDING",
        total_fare=1150.0,
        status_message="Transaction pending bank confirmation",
    )
    d = original.to_dict()
    restored = BookingRecord.from_dict(d)
    assert restored.train_number == original.train_number
    assert restored.status == "UNKNOWN"
    assert restored.total_fare == 1150.0
    assert restored.is_confirmed is False
