"""Application settings model with safety guards against credential storage."""

from dataclasses import dataclass
from typing import Any, Dict

PROHIBITED_CREDENTIAL_KEYS = {
    "password",
    "passwd",
    "otp",
    "pin",
    "cvv",
    "cvc",
    "card_number",
    "card",
    "banking",
    "account_number",
    "secret",
    "token",
    "credential",
    "credentials",
}


@dataclass
class ApplicationSettings:
    """Local preferences for Tatkal Assistant desktop application."""

    sound_notification: bool = True
    visual_notification: bool = True
    default_quota: str = "TATKAL"
    default_class: str = "SL"
    theme: str = "light"
    auto_refresh_clock: bool = True
    mobile_number: str = ""
    auto_upgradation: bool = False
    confirm_berths_only: bool = False
    preferred_payment_mode: str = "IRCTC eWallet"
    auto_start_on_opening: bool = False
    upi_id: str = ""

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate settings and ensure no credential fields are present."""
        if not isinstance(self.sound_notification, bool):
            raise ValueError("sound_notification must be a boolean.")
        if not isinstance(self.visual_notification, bool):
            raise ValueError("visual_notification must be a boolean.")
        if not isinstance(self.auto_refresh_clock, bool):
            raise ValueError("auto_refresh_clock must be a boolean.")
        if not isinstance(self.auto_upgradation, bool):
            raise ValueError("auto_upgradation must be a boolean.")
        if not isinstance(self.confirm_berths_only, bool):
            raise ValueError("confirm_berths_only must be a boolean.")

        if self.default_quota not in {"TATKAL", "PREMIUM TATKAL", "GENERAL"}:
            raise ValueError(f"Invalid default quota: {self.default_quota}")
        if self.default_class not in {"SL", "3A", "2A", "1A", "3E", "CC", "EC", "2S"}:
            raise ValueError(f"Invalid default class: {self.default_class}")
        if self.theme not in {"light", "dark", "system"}:
            raise ValueError(f"Invalid theme: {self.theme}")

        valid_modes = {
            "IRCTC EWALLET",
            "EWALLET",
            "UPI",
            "CREDIT CARD",
            "CREDIT_CARD",
            "CARDS_NETBANKING",
        }
        if self.preferred_payment_mode.strip().upper() not in valid_modes:
            raise ValueError(f"Invalid payment mode: {self.preferred_payment_mode}")

        mode_upper = self.preferred_payment_mode.strip().upper()
        if "WALLET" in mode_upper:
            self.preferred_payment_mode = "IRCTC eWallet"
        elif "UPI" in mode_upper:
            self.preferred_payment_mode = "UPI"
        elif "CARD" in mode_upper or "NETBANKING" in mode_upper:
            self.preferred_payment_mode = "Credit Card"

        if not isinstance(self.mobile_number, str):
            raise ValueError("mobile_number must be a string.")
        if self.mobile_number:
            cleaned = self.mobile_number.strip()
            if not cleaned.isdigit() or len(cleaned) != 10:
                raise ValueError("mobile_number must be exactly 10 digits.")

        if not isinstance(self.auto_start_on_opening, bool):
            raise ValueError("auto_start_on_opening must be a boolean.")

        if not isinstance(self.upi_id, str):
            raise ValueError("upi_id must be a string.")
        if self.upi_id:
            import re
            vpa = self.upi_id.strip()
            # UPI VPA format: localpart@bankhandle (e.g. name@okicici, user@upi)
            if not re.match(r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9]+$', vpa):
                raise ValueError("upi_id must be a valid UPI VPA (e.g. name@bankhandle).")

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            "sound_notification": self.sound_notification,
            "visual_notification": self.visual_notification,
            "default_quota": self.default_quota,
            "default_class": self.default_class,
            "theme": self.theme,
            "auto_refresh_clock": self.auto_refresh_clock,
            "mobile_number": self.mobile_number,
            "auto_upgradation": self.auto_upgradation,
            "confirm_berths_only": self.confirm_berths_only,
            "preferred_payment_mode": self.preferred_payment_mode,
            "auto_start_on_opening": self.auto_start_on_opening,
            "upi_id": self.upi_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApplicationSettings":
        """Instantiate ApplicationSettings from dictionary, checking for prohibited credential keys."""
        # Strictly reject any attempt to supply credential fields
        for key in data.keys():
            normalized = key.strip().lower()
            if any(forbidden in normalized for forbidden in PROHIBITED_CREDENTIAL_KEYS):
                raise ValueError(
                    f"Security violation: Storing sensitive credential '{key}' is strictly prohibited."
                )

        return cls(
            sound_notification=bool(data.get("sound_notification", True)),
            visual_notification=bool(data.get("visual_notification", True)),
            default_quota=str(data.get("default_quota", "TATKAL")),
            default_class=str(data.get("default_class", "SL")),
            theme=str(data.get("theme", "light")),
            auto_refresh_clock=bool(data.get("auto_refresh_clock", True)),
            mobile_number=str(data.get("mobile_number", "")),
            auto_upgradation=bool(data.get("auto_upgradation", False)),
            confirm_berths_only=bool(data.get("confirm_berths_only", False)),
            preferred_payment_mode=str(data.get("preferred_payment_mode", "IRCTC eWallet")),
            auto_start_on_opening=bool(data.get("auto_start_on_opening", False)),
            upi_id=str(data.get("upi_id", "")),
        )
