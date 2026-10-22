"""Unit tests for Phase 3 SQLite Database operations."""

from datetime import date, timedelta
import pytest

from database.db import Database
from models.passenger import Passenger
from models.settings import ApplicationSettings
from models.trip import Trip


@pytest.fixture
def db():
    """Create an in-memory SQLite database instance for isolated testing."""
    return Database(":memory:")


# ==================== Trip DB Tests ====================


def test_create_and_load_trip(db):
    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(
        from_station="NDLS",
        to_station="CNB",
        journey_date=tomorrow,
        train_number="12004",
        train_name="Shatabdi Express",
        class_code="CC",
        quota="TATKAL",
    )
    created = db.create_trip(trip)
    assert created.id is not None
    assert created.id > 0

    loaded = db.load_trip(created.id)
    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.from_station == "NDLS"
    assert loaded.to_station == "CNB"
    assert loaded.journey_date == tomorrow
    assert loaded.train_number == "12004"
    assert loaded.train_name == "Shatabdi Express"
    assert loaded.class_code == "CC"
    assert loaded.quota == "TATKAL"


def test_update_trip(db):
    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(
        from_station="NDLS",
        to_station="LKO",
        journey_date=tomorrow,
        train_number="12424",
        class_code="3A",
    )
    db.create_trip(trip)

    # Modify trip
    trip.train_number = "12420"
    trip.class_code = "2A"
    trip.quota = "PREMIUM TATKAL"
    success = db.update_trip(trip)
    assert success is True

    loaded = db.load_trip(trip.id)
    assert loaded.train_number == "12420"
    assert loaded.class_code == "2A"
    assert loaded.quota == "PREMIUM TATKAL"


def test_delete_trip(db):
    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(
        from_station="NDLS",
        to_station="LKO",
        journey_date=tomorrow,
        train_number="12424",
    )
    db.create_trip(trip)
    trip_id = trip.id

    assert db.delete_trip(trip_id) is True
    assert db.load_trip(trip_id) is None
    # Deleting non-existent returns False
    assert db.delete_trip(trip_id) is False


def test_list_trips(db):
    tomorrow = date.today() + timedelta(days=1)
    trip1 = Trip(from_station="NDLS", to_station="CNB", journey_date=tomorrow, train_number="12004")
    trip2 = Trip(from_station="NDLS", to_station="LKO", journey_date=tomorrow, train_number="12424")
    db.create_trip(trip1)
    db.create_trip(trip2)

    trips = db.list_trips()
    assert len(trips) == 2
    # Ordered by id desc
    assert trips[0].id == trip2.id
    assert trips[1].id == trip1.id


# ==================== Passenger DB Tests ====================


def test_create_and_load_passenger(db):
    p = Passenger(name="Vikram Singh", age=35, gender="M", berth_preference="LB")
    created = db.create_passenger(p)
    assert created.id is not None
    assert created.id > 0

    loaded = db.load_passenger(created.id)
    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.name == "Vikram Singh"
    assert loaded.age == 35
    assert loaded.gender == "M"
    assert loaded.berth_preference == "LB"


def test_update_passenger(db):
    p = Passenger(name="Sunita Sharma", age=40, gender="F", berth_preference="MB")
    db.create_passenger(p)

    p.age = 41
    p.berth_preference = "SL"
    success = db.update_passenger(p)
    assert success is True

    loaded = db.load_passenger(p.id)
    assert loaded.age == 41
    assert loaded.berth_preference == "SL"


def test_delete_passenger(db):
    p = Passenger(name="Rohan Gupta", age=22, gender="M")
    db.create_passenger(p)
    p_id = p.id

    assert db.delete_passenger(p_id) is True
    assert db.load_passenger(p_id) is None
    assert db.delete_passenger(p_id) is False


def test_list_passengers(db):
    p1 = Passenger(name="Person A", age=25, gender="M")
    p2 = Passenger(name="Person B", age=30, gender="F")
    db.create_passenger(p1)
    db.create_passenger(p2)

    passengers = db.list_passengers()
    assert len(passengers) == 2
    assert passengers[0].name == "Person A"
    assert passengers[1].name == "Person B"


# ==================== Settings DB Tests ====================


def test_settings_save_and_load(db):
    settings = ApplicationSettings(
        sound_notification=False,
        visual_notification=True,
        default_quota="PREMIUM TATKAL",
        default_class="2A",
    )
    db.save_settings(settings)

    loaded = db.load_settings()
    assert loaded.sound_notification is False
    assert loaded.visual_notification is True
    assert loaded.default_quota == "PREMIUM TATKAL"
    assert loaded.default_class == "2A"


def test_sql_injection_safety(db):
    """Verify that inputs with SQL syntax are safely treated as parameters."""
    injection_name = "O'Connor'); DROP TABLE passengers;--"
    p = Passenger(name=injection_name, age=29, gender="M")
    db.create_passenger(p)

    loaded = db.load_passenger(p.id)
    assert loaded is not None
    assert loaded.name == injection_name

    # Ensure table was not dropped
    passengers = db.list_passengers()
    assert len(passengers) == 1


def test_file_based_db_persistence(tmp_path):
    """Verify persistence across separate connections to a file-based SQLite database."""
    db_file = str(tmp_path / "test_persisted.db")
    db1 = Database(db_file)
    p = Passenger(name="Persisted User", age=28, gender="F")
    db1.create_passenger(p)
    p_id = p.id

    # Reopen database with a new instance
    db2 = Database(db_file)
    loaded = db2.load_passenger(p_id)
    assert loaded is not None
    assert loaded.name == "Persisted User"
    assert loaded.age == 28
