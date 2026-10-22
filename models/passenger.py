"""Passenger model with validation for Tatkal Assistant."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

VALID_GENDERS = {"M": "Male", "F": "Female", "T": "Transgender"}
VALID_BERTH_PREFERENCES = {
    "NONE": "No Preference",
    "LB": "Lower",
    "MB": "Middle",
    "UB": "Upper",
    "SL": "Side Lower",
    "SU": "Side Upper",
    "WS": "Window Side",
    "CB": "Cabin",
    "CP": "Coupe",
}


@dataclass
class Passenger:
    """Represents a passenger profile for ticket booking."""

    name: str
    age: int
    gender: str
    berth_preference: str = "NONE"
    id: Optional[int] = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate passenger fields according to booking rules."""
        # Validate name
        if not isinstance(self.name, str):
            raise ValueError("Passenger name must be a string.")
        cleaned_name = self.name.strip()
        if not cleaned_name:
            raise ValueError("Passenger name cannot be empty.")
        if len(cleaned_name) < 2 or len(cleaned_name) > 60:
            raise ValueError("Passenger name must be between 2 and 60 characters.")
        self.name = cleaned_name

        # Validate age
        if not isinstance(self.age, int) or isinstance(self.age, bool):
            raise ValueError("Passenger age must be an integer.")
        if self.age < 1 or self.age > 125:
            raise ValueError("Passenger age must be between 1 and 125.")

        # Validate gender
        if not isinstance(self.gender, str):
            raise ValueError("Passenger gender must be a string.")
        cleaned_gender = self.gender.strip().upper()
        if cleaned_gender not in VALID_GENDERS:
            valid_keys = ", ".join(VALID_GENDERS.keys())
            raise ValueError(f"Invalid gender '{self.gender}'. Must be one of: {valid_keys}")
        self.gender = cleaned_gender

        # Validate berth preference
        if not isinstance(self.berth_preference, str):
            raise ValueError("Berth preference must be a string.")
        cleaned_berth = self.berth_preference.strip().upper()
        if cleaned_berth not in VALID_BERTH_PREFERENCES:
            valid_berths = ", ".join(VALID_BERTH_PREFERENCES.keys())
            raise ValueError(
                f"Invalid berth preference '{self.berth_preference}'. Must be one of: {valid_berths}"
            )
        self.berth_preference = cleaned_berth

    @property
    def gender_display(self) -> str:
        """Return human-readable gender name."""
        return VALID_GENDERS.get(self.gender, self.gender)

    @property
    def berth_display(self) -> str:
        """Return human-readable berth preference."""
        return VALID_BERTH_PREFERENCES.get(self.berth_preference, self.berth_preference)

    def to_dict(self) -> Dict[str, Any]:
        """Convert passenger to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "gender": self.gender,
            "berth_preference": self.berth_preference,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Passenger":
        """Instantiate a Passenger from dictionary data."""
        return cls(
            id=data.get("id"),
            name=data["name"],
            age=int(data["age"]),
            gender=data["gender"],
            berth_preference=data.get("berth_preference", "NONE"),
        )
