"""Deterministic finite state machine for Tatkal booking workflow."""

from datetime import datetime
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Set, Tuple


class BookingState(Enum):
    """Explicit states of the Tatkal booking lifecycle."""

    IDLE = auto()
    BROWSER_READY = auto()
    USER_LOGIN_REQUIRED = auto()
    USER_LOGGED_IN = auto()
    WAITING_FOR_TATKAL = auto()
    JOURNEY_SELECTION = auto()
    TRAIN_SELECTION = auto()
    PASSENGER_SELECTION = auto()
    REVIEW = auto()
    CAPTCHA_REQUIRED = auto()
    OTP_REQUIRED = auto()
    PAYMENT_REQUIRED = auto()
    BOOKING_CONFIRMATION = auto()
    SUCCESS = auto()
    FAILURE = auto()
    UNKNOWN = auto()


class InvalidStateTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, from_state: BookingState, to_state: BookingState, reason: str = "") -> None:
        self.from_state = from_state
        self.to_state = to_state
        message = f"Illegal transition from '{from_state.name}' to '{to_state.name}'."
        if reason:
            message += f" Reason: {reason}"
        super().__init__(message)


# Strict map of legal transitions
LEGAL_TRANSITIONS: Dict[BookingState, Set[BookingState]] = {
    BookingState.IDLE: {
        BookingState.BROWSER_READY,
        BookingState.FAILURE,
    },
    BookingState.BROWSER_READY: {
        BookingState.USER_LOGIN_REQUIRED,
        BookingState.USER_LOGGED_IN,
        BookingState.FAILURE,
        BookingState.IDLE,
    },
    BookingState.USER_LOGIN_REQUIRED: {
        BookingState.USER_LOGGED_IN,
        BookingState.CAPTCHA_REQUIRED,
        BookingState.OTP_REQUIRED,
        BookingState.FAILURE,
        BookingState.IDLE,
    },
    BookingState.USER_LOGGED_IN: {
        BookingState.WAITING_FOR_TATKAL,
        BookingState.JOURNEY_SELECTION,
        BookingState.USER_LOGIN_REQUIRED,  # session expired
        BookingState.FAILURE,
        BookingState.IDLE,
    },
    BookingState.WAITING_FOR_TATKAL: {
        BookingState.JOURNEY_SELECTION,
        BookingState.USER_LOGIN_REQUIRED,  # session expired
        BookingState.FAILURE,
        BookingState.IDLE,
    },
    BookingState.JOURNEY_SELECTION: {
        BookingState.TRAIN_SELECTION,
        BookingState.USER_LOGIN_REQUIRED,
        BookingState.FAILURE,
        BookingState.IDLE,
    },
    BookingState.TRAIN_SELECTION: {
        BookingState.PASSENGER_SELECTION,
        BookingState.JOURNEY_SELECTION,  # back
        BookingState.USER_LOGIN_REQUIRED,
        BookingState.FAILURE,
        BookingState.IDLE,
    },
    BookingState.PASSENGER_SELECTION: {
        BookingState.REVIEW,
        BookingState.TRAIN_SELECTION,  # back
        BookingState.CAPTCHA_REQUIRED,
        BookingState.USER_LOGIN_REQUIRED,
        BookingState.FAILURE,
        BookingState.IDLE,
    },
    BookingState.REVIEW: {
        BookingState.CAPTCHA_REQUIRED,
        BookingState.OTP_REQUIRED,
        BookingState.PAYMENT_REQUIRED,
        BookingState.PASSENGER_SELECTION,  # back
        BookingState.USER_LOGIN_REQUIRED,
        BookingState.FAILURE,
        BookingState.IDLE,
    },
    BookingState.CAPTCHA_REQUIRED: {
        BookingState.USER_LOGGED_IN,  # if login CAPTCHA
        BookingState.REVIEW,
        BookingState.PAYMENT_REQUIRED,
        BookingState.OTP_REQUIRED,
        BookingState.FAILURE,
        BookingState.IDLE,
    },
    BookingState.OTP_REQUIRED: {
        BookingState.USER_LOGGED_IN,  # if login OTP
        BookingState.REVIEW,
        BookingState.PAYMENT_REQUIRED,
        BookingState.BOOKING_CONFIRMATION,
        BookingState.FAILURE,
        BookingState.IDLE,
    },
    BookingState.PAYMENT_REQUIRED: {
        BookingState.OTP_REQUIRED,  # banking / 2FA OTP
        BookingState.BOOKING_CONFIRMATION,
        BookingState.FAILURE,
        BookingState.UNKNOWN,  # payment state ambiguous
        BookingState.IDLE,  # user cancelled before authorizing
    },
    BookingState.BOOKING_CONFIRMATION: {
        BookingState.SUCCESS,
        BookingState.FAILURE,
        BookingState.UNKNOWN,
        BookingState.IDLE,
    },
    BookingState.SUCCESS: {
        BookingState.IDLE,  # reset for next booking
    },
    BookingState.FAILURE: {
        BookingState.IDLE,  # reset after error
        BookingState.BROWSER_READY,  # retry from browser ready
    },
    BookingState.UNKNOWN: {
        BookingState.IDLE,  # ONLY manual reset allowed after checking IRCTC history
    },
}


class BookingStateMachine:
    """Manages state transitions deterministically with audit history and listener callbacks."""

    def __init__(self, initial_state: BookingState = BookingState.IDLE) -> None:
        self._state: BookingState = initial_state
        self._history: List[Tuple[BookingState, str, datetime]] = [
            (initial_state, "Initialization", datetime.now())
        ]
        self._error_message: Optional[str] = None
        self._listeners: List[Callable[[BookingState, BookingState, Optional[str]], None]] = []

    @property
    def current_state(self) -> BookingState:
        """Return the current active state."""
        return self._state

    @property
    def error_message(self) -> Optional[str]:
        """Return the error message if state is FAILURE or UNKNOWN."""
        return self._error_message

    @property
    def history(self) -> List[Tuple[BookingState, str, datetime]]:
        """Return audit history of state transitions."""
        return list(self._history)

    @property
    def is_locked(self) -> bool:
        """Return True if state machine is locked to prevent retries (e.g. UNKNOWN)."""
        return self._state == BookingState.UNKNOWN

    def add_listener(
        self,
        callback: Callable[[BookingState, BookingState, Optional[str]], None],
    ) -> None:
        """Register a callback for state changes: callback(from_state, to_state, reason)."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(
        self,
        callback: Callable[[BookingState, BookingState, Optional[str]], None],
    ) -> None:
        """Unregister a listener callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def can_transition_to(self, target_state: BookingState) -> bool:
        """Check whether transition to target state is legally allowed."""
        allowed = LEGAL_TRANSITIONS.get(self._state, set())
        return target_state in allowed

    def transition_to(self, target_state: BookingState, reason: str = "") -> None:
        """Execute a state transition.

        Raises InvalidStateTransitionError if the transition is illegal.
        """
        if target_state == self._state:
            return  # No-op for identical state

        if not self.can_transition_to(target_state):
            raise InvalidStateTransitionError(self._state, target_state, reason)

        old_state = self._state
        self._state = target_state
        self._history.append((target_state, reason, datetime.now()))

        if target_state not in (BookingState.FAILURE, BookingState.UNKNOWN):
            self._error_message = None
        elif reason:
            self._error_message = reason

        # Notify listeners
        for listener in self._listeners:
            try:
                listener(old_state, target_state, reason)
            except Exception:
                pass

    def fail(self, error_message: str) -> None:
        """Helper to transition to FAILURE with an explanation."""
        self._error_message = error_message
        self.transition_to(BookingState.FAILURE, reason=error_message)

    def set_unknown(self, reason: str) -> None:
        """Helper to transition to UNKNOWN when payment or booking outcome is ambiguous."""
        self._error_message = reason
        self.transition_to(BookingState.UNKNOWN, reason=reason)

    def reset(self, reason: str = "User Reset") -> None:
        """Safely reset the state machine to IDLE."""
        if self._state != BookingState.IDLE:
            self.transition_to(BookingState.IDLE, reason=reason)
