"""Core automation, state machine, and scheduling services."""

from core.booking_state import (
    BookingState,
    BookingStateMachine,
    InvalidStateTransitionError,
    LEGAL_TRANSITIONS,
)
from core.clock import (
    IST_TZ,
    TatkalClock,
    current_ist,
    default_clock,
    is_tatkal_open,
    seconds_until,
)

from core.failure_handler import (
    FailureDetail,
    FailureType,
    RetryPolicy,
    classify_failure,
    execute_with_limited_retry,
)

from core.logger import (
    AppLogger,
    get_app_logger,
    is_sensitive,
    log_event,
    sanitize_log_message,
    set_app_logger,
)

__all__ = [
    "BookingState",
    "BookingStateMachine",
    "InvalidStateTransitionError",
    "LEGAL_TRANSITIONS",
    "IST_TZ",
    "TatkalClock",
    "current_ist",
    "default_clock",
    "is_tatkal_open",
    "seconds_until",
    "FailureType",
    "FailureDetail",
    "RetryPolicy",
    "classify_failure",
    "execute_with_limited_retry",
    "AppLogger",
    "get_app_logger",
    "set_app_logger",
    "log_event",
    "sanitize_log_message",
    "is_sensitive",
]
