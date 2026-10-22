"""Unit tests for Phase 2 Configuration Models."""

from datetime import date, timedelta
import pytest

from models import ApplicationSettings, Passenger, Trip


# ==================== Passenger Tests ====================


def test_valid_passenger():
    p = Passenger(name="Ravi Kumar", age=32, gender="M", berth_preference="LB")
    assert p.name == "Ravi Kumar"
    assert p.age == 32
    assert p.gender == "M"
    assert p.berth_preference == "LB"

    p_dict = p.to_dict()
    assert p_dict["name"] == "Ravi Kumar"
    assert p_dict["age"] == 32
    assert p_dict["gender"] == "M"
    assert p_dict["berth_preference"] == "LB"

    p2 = Passenger.from_dict(p_dict)
    assert p2.name == p.name
    assert p2.age == p.age


def test_passenger_name_validation():
    with pytest.raises(ValueError, match="cannot be empty"):
        Passenger(name="   ", age=30, gender="M")

    with pytest.raises(ValueError, match="between 2 and 60 characters"):
        Passenger(name="A", age=30, gender="M")

    with pytest.raises(ValueError, match="between 2 and 60 characters"):
        Passenger(name="A" * 65, age=30, gender="M")


def test_passenger_age_validation():
    with pytest.raises(ValueError, match="must be between 1 and 125"):
        Passenger(name="Sita Devi", age=0, gender="F")

    with pytest.raises(ValueError, match="must be between 1 and 125"):
        Passenger(name="Sita Devi", age=130, gender="F")

    with pytest.raises(ValueError, match="must be an integer"):
        Passenger(name="Sita Devi", age="thirty", gender="F")  # type: ignore


def test_passenger_gender_validation():
    p = Passenger(name="Ananya", age=25, gender="f", berth_preference="SL")
    assert p.gender == "F"

    with pytest.raises(ValueError, match="Invalid gender"):
        Passenger(name="Alex", age=28, gender="Unknown")


def test_passenger_berth_preference_validation():
    p = Passenger(name="Rajesh", age=45, gender="M", berth_preference="None")
    assert p.berth_preference == "NONE"

    with pytest.raises(ValueError, match="Invalid berth preference"):
        Passenger(name="Rajesh", age=45, gender="M", berth_preference="ROOF")


# ==================== Trip Tests ====================


def test_valid_trip():
    tomorrow = date.today() + timedelta(days=1)
    trip = Trip(
        from_station="ndls",
        to_station="lko",
        journey_date=tomorrow,
        train_number="12424",
        train_name="Rajdhani Express",
        class_code="3a",
        quota="tatkal",
    )
    assert trip.from_station == "NDLS"
    assert trip.to_station == "LKO"
    assert trip.train_number == "12424"
    assert trip.class_code == "3A"
    assert trip.quota == "TATKAL"
    assert trip.journey_date_str == tomorrow.isoformat()

    trip_dict = trip.to_dict()
    trip_loaded = Trip.from_dict(trip_dict)
    assert trip_loaded.from_station == "NDLS"
    assert trip_loaded.train_number == "12424"


def test_trip_date_string_parsing():
    tomorrow = date.today() + timedelta(days=1)
    # Test ISO format string
    trip1 = Trip(
        from_station="NDLS",
        to_station="CNB",
        journey_date=tomorrow.strftime("%Y-%m-%d"),
        train_number="12004",
    )
    assert trip1.journey_date == tomorrow

    # Test DD/MM/YYYY format string
    trip2 = Trip(
        from_station="NDLS",
        to_station="CNB",
        journey_date=tomorrow.strftime("%d/%m/%Y"),
        train_number="12004",
    )
    assert trip2.journey_date == tomorrow


def test_trip_past_date_rejected():
    yesterday = date.today() - timedelta(days=1)
    with pytest.raises(ValueError, match="cannot be in the past"):
        Trip(
            from_station="NDLS",
            to_station="CNB",
            journey_date=yesterday,
            train_number="12004",
        )


def test_trip_same_origin_and_destination():
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(ValueError, match="cannot be the same"):
        Trip(
            from_station="NDLS",
            to_station="ndls",
            journey_date=tomorrow,
            train_number="12004",
        )


def test_trip_train_number_validation():
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(ValueError, match="must be 4 or 5 digits"):
        Trip(
            from_station="NDLS",
            to_station="CNB",
            journey_date=tomorrow,
            train_number="12",
        )

    with pytest.raises(ValueError, match="must be 4 or 5 digits"):
        Trip(
            from_station="NDLS",
            to_station="CNB",
            journey_date=tomorrow,
            train_number="123456",
        )

    with pytest.raises(ValueError, match="must be 4 or 5 digits"):
        Trip(
            from_station="NDLS",
            to_station="CNB",
            journey_date=tomorrow,
            train_number="TRAIN",
        )


def test_trip_class_and_quota_validation():
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(ValueError, match="Invalid class code"):
        Trip(
            from_station="NDLS",
            to_station="CNB",
            journey_date=tomorrow,
            train_number="12004",
            class_code="BUSINESS",
        )

    with pytest.raises(ValueError, match="Invalid quota"):
        Trip(
            from_station="NDLS",
            to_station="CNB",
            journey_date=tomorrow,
            train_number="12004",
            quota="DEFENCE",
        )


# ==================== ApplicationSettings Tests ====================


def test_default_settings():
    settings = ApplicationSettings()
    assert settings.sound_notification is True
    assert settings.visual_notification is True
    assert settings.default_quota == "TATKAL"
    assert settings.default_class == "SL"
    assert settings.theme == "light"


def test_settings_serialization():
    settings = ApplicationSettings(
        sound_notification=False,
        default_quota="PREMIUM TATKAL",
        default_class="3A",
    )
    data = settings.to_dict()
    loaded = ApplicationSettings.from_dict(data)
    assert loaded.sound_notification is False
    assert loaded.default_quota == "PREMIUM TATKAL"
    assert loaded.default_class == "3A"


def test_security_credential_storage_strictly_forbidden():
    """Verify that credentials cannot be passed or stored in settings."""
    forbidden_payloads = [
        {"password": "secret_password"},
        {"user_otp": "123456"},
        {"wallet_pin": "9999"},
        {"card_cvv": "123"},
        {"banking_credential": "login"},
    ]
    for payload in forbidden_payloads:
        with pytest.raises(ValueError, match="Security violation: Storing sensitive credential"):
            ApplicationSettings.from_dict(payload)
