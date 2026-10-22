"""Booking record model for post-booking reconciliation and persistence."""

from dataclasses import dataclass
from datetime import date, datetime
import json
import re
from typing import Any, Dict, List, Optional, Union

VALID_STATUSES = {"SUCCESS", "FAILURE", "UNKNOWN"}


@dataclass
class BookingRecord:
    """Represents a recorded ticket booking attempt and outcome."""

    train_number: str
    class_code: str
    quota_code: str
    from_station: str
    to_station: str
    journey_date: Union[date, str]
    status: str = "SUCCESS"  # "SUCCESS", "FAILURE", "UNKNOWN"
    pnr: str = ""
    train_name: str = ""
    transaction_id: str = ""
    total_fare: float = 0.0
    passenger_details: str = ""  # JSON string or formatted text
    status_message: str = ""
    trip_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate booking record properties."""
        # Validate train number
        if not isinstance(self.train_number, str):
            raise ValueError("Train number must be a string.")
        cleaned_train = self.train_number.strip()
        if not re.fullmatch(r"\d{4,5}", cleaned_train):
            raise ValueError("Train number must be 4 or 5 digits.")
        self.train_number = cleaned_train

        # Validate class code
        cleaned_class = self.class_code.strip().upper()
        if not cleaned_class:
            raise ValueError("Class code cannot be empty.")
        self.class_code = cleaned_class

        # Validate quota code
        cleaned_quota = self.quota_code.strip().upper()
        if not cleaned_quota:
            raise ValueError("Quota code cannot be empty.")
        self.quota_code = cleaned_quota

        # Validate stations
        if not self.from_station.strip():
            raise ValueError("Origin station cannot be empty.")
        if not self.to_station.strip():
            raise ValueError("Destination station cannot be empty.")
        self.from_station = self.from_station.strip().upper()
        self.to_station = self.to_station.strip().upper()

        # Validate status
        cleaned_status = self.status.strip().upper()
        if cleaned_status not in VALID_STATUSES:
            valid_statuses_str = ", ".join(sorted(VALID_STATUSES))
            raise ValueError(f"Invalid booking status '{self.status}'. Must be one of: {valid_statuses_str}")
        self.status = cleaned_status

        # Validate PNR if status is SUCCESS
        if self.pnr:
            cleaned_pnr = self.pnr.strip().replace(" ", "").replace("-", "")
            if not re.fullmatch(r"\d{10}", cleaned_pnr):
                raise ValueError("PNR must be exactly 10 digits.")
            self.pnr = cleaned_pnr
        elif self.status == "SUCCESS":
            # For SUCCESS status, a PNR is typically expected
            pass

        # Validate journey date
        if isinstance(self.journey_date, str):
            try:
                if "/" in self.journey_date:
                    self.journey_date = datetime.strptime(self.journey_date, "%d/%m/%Y").date()
                else:
                    self.journey_date = date.fromisoformat(self.journey_date)
            except ValueError as exc:
                raise ValueError(f"Invalid journey date format: '{self.journey_date}'.") from exc
        elif not isinstance(self.journey_date, date):
            raise ValueError("Journey date must be a date object or date string.")

        # Ensure fare is non-negative
        if self.total_fare < 0:
            raise ValueError("Total fare cannot be negative.")

    @property
    def journey_date_str(self) -> str:
        """Return ISO formatted journey date string (YYYY-MM-DD)."""
        if isinstance(self.journey_date, date):
            return self.journey_date.isoformat()
        return str(self.journey_date)

    @property
    def is_confirmed(self) -> bool:
        """True if the ticket was successfully booked and confirmed."""
        return self.status == "SUCCESS" and bool(self.pnr)

    def get_parsed_passengers(self) -> List[Dict[str, Any]]:
        """Return passenger details parsed from JSON if possible."""
        if not self.passenger_details:
            return []
        try:
            parsed = json.loads(self.passenger_details)
            if isinstance(parsed, list):
                return parsed
            return []
        except Exception:
            return []

    def to_dict(self) -> Dict[str, Any]:
        """Convert booking record to dictionary representation."""
        return {
            "id": self.id,
            "trip_id": self.trip_id,
            "pnr": self.pnr,
            "train_number": self.train_number,
            "train_name": self.train_name,
            "class_code": self.class_code,
            "quota_code": self.quota_code,
            "from_station": self.from_station,
            "to_station": self.to_station,
            "journey_date": self.journey_date_str,
            "status": self.status,
            "transaction_id": self.transaction_id,
            "total_fare": self.total_fare,
            "passenger_details": self.passenger_details,
            "status_message": self.status_message,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BookingRecord":
        """Instantiate a BookingRecord from dictionary data."""
        return cls(
            id=data.get("id"),
            trip_id=data.get("trip_id"),
            pnr=data.get("pnr", ""),
            train_number=data["train_number"],
            train_name=data.get("train_name", ""),
            class_code=data.get("class_code", "SL"),
            quota_code=data.get("quota_code", "TATKAL"),
            from_station=data["from_station"],
            to_station=data["to_station"],
            journey_date=data["journey_date"],
            status=data.get("status", "SUCCESS"),
            transaction_id=data.get("transaction_id", ""),
            total_fare=float(data.get("total_fare", 0.0)),
            passenger_details=data.get("passenger_details", ""),
            status_message=data.get("status_message", ""),
            created_at=data.get("created_at"),
        )
