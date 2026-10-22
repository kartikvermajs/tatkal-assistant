"""Trip model with validation for Tatkal Assistant."""

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any, Dict, Optional, Union

VALID_CLASSES = {"SL", "3A", "2A", "1A", "3E", "CC", "EC", "2S"}
VALID_QUOTAS = {"TATKAL", "PREMIUM TATKAL", "GENERAL"}


@dataclass
class Trip:
    """Represents a planned journey profile for ticket booking."""

    from_station: str
    to_station: str
    journey_date: Union[date, str]
    train_number: str
    train_name: str = ""
    class_code: str = "SL"
    quota: str = "TATKAL"
    id: Optional[int] = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate trip details according to booking rules."""
        # Validate stations
        if not isinstance(self.from_station, str) or not self.from_station.strip():
            raise ValueError("Origin station cannot be empty.")
        if not isinstance(self.to_station, str) or not self.to_station.strip():
            raise ValueError("Destination station cannot be empty.")

        self.from_station = self.from_station.strip().upper()
        self.to_station = self.to_station.strip().upper()

        if len(self.from_station) < 2 or len(self.from_station) > 50:
            raise ValueError("Origin station must be between 2 and 50 characters.")
        if len(self.to_station) < 2 or len(self.to_station) > 50:
            raise ValueError("Destination station must be between 2 and 50 characters.")

        if self.from_station == self.to_station:
            raise ValueError("Origin and destination stations cannot be the same.")

        # Validate journey date
        if isinstance(self.journey_date, str):
            try:
                # Support YYYY-MM-DD and DD/MM/YYYY
                if "/" in self.journey_date:
                    self.journey_date = datetime.strptime(self.journey_date, "%d/%m/%Y").date()
                else:
                    self.journey_date = date.fromisoformat(self.journey_date)
            except ValueError as exc:
                raise ValueError(f"Invalid journey date format: '{self.journey_date}'. Use YYYY-MM-DD or DD/MM/YYYY.") from exc
        elif not isinstance(self.journey_date, date):
            raise ValueError("Journey date must be a date object or date string.")

        # Ensure journey date is not in the past
        if self.journey_date < date.today():
            raise ValueError("Journey date cannot be in the past.")

        # Validate train number
        if not isinstance(self.train_number, str):
            raise ValueError("Train number must be a string.")
        cleaned_train = self.train_number.strip()
        if not re.fullmatch(r"\d{4,5}", cleaned_train):
            raise ValueError("Train number must be 4 or 5 digits.")
        self.train_number = cleaned_train

        # Validate train name
        if not isinstance(self.train_name, str):
            raise ValueError("Train name must be a string.")
        self.train_name = self.train_name.strip()

        # Validate class code
        cleaned_class = self.class_code.strip().upper()
        if cleaned_class not in VALID_CLASSES:
            valid_classes_str = ", ".join(sorted(VALID_CLASSES))
            raise ValueError(f"Invalid class code '{self.class_code}'. Must be one of: {valid_classes_str}")
        self.class_code = cleaned_class

        # Validate quota
        cleaned_quota = self.quota.strip().upper()
        if cleaned_quota not in VALID_QUOTAS:
            valid_quotas_str = ", ".join(sorted(VALID_QUOTAS))
            raise ValueError(f"Invalid quota '{self.quota}'. Must be one of: {valid_quotas_str}")
        self.quota = cleaned_quota

    @property
    def journey_date_str(self) -> str:
        """Return ISO formatted journey date string (YYYY-MM-DD)."""
        if isinstance(self.journey_date, date):
            return self.journey_date.isoformat()
        return str(self.journey_date)

    @property
    def class_display_name(self) -> str:
        """Return human-readable class name (e.g. 'AC 3 Tier (3A)')."""
        import config
        return config.get_class_display_name(self.class_code)

    def to_dict(self) -> Dict[str, Any]:
        """Convert trip to dictionary representation."""
        return {
            "id": self.id,
            "from_station": self.from_station,
            "to_station": self.to_station,
            "journey_date": self.journey_date_str,
            "train_number": self.train_number,
            "train_name": self.train_name,
            "class_code": self.class_code,
            "quota": self.quota,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Trip":
        """Instantiate a Trip from dictionary data."""
        return cls(
            id=data.get("id"),
            from_station=data["from_station"],
            to_station=data["to_station"],
            journey_date=data["journey_date"],
            train_number=data["train_number"],
            train_name=data.get("train_name", ""),
            class_code=data.get("class_code", "SL"),
            quota=data.get("quota", "TATKAL"),
        )
