"""Failure handling and recovery module for Tatkal Assistant.

Provides structured classification, human-readable error descriptions,
deterministic recovery policies, and controlled limited retries for ordinary
page-loading and network issues.

Strict Rules:
- Do not silently ignore exceptions.
- Do not blindly retry.
- Use limited retries ONLY for ordinary page-loading/network problems where appropriate.
- NEVER retry after an uncertain payment state.
- Every error must produce a clear, human-readable status message.
"""

from dataclasses import dataclass, field
from enum import Enum
import re
import time
from typing import Any, Callable, Dict, Optional, TypeVar

from core.booking_state import BookingState


class FailureType(Enum):
    """Categorized failure types for the Tatkal booking workflow."""

    BROWSER_CRASH = "BROWSER_CRASH"
    PAGE_TIMEOUT = "PAGE_TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    SESSION_EXPIRATION = "SESSION_EXPIRATION"
    TRAIN_UNAVAILABLE = "TRAIN_UNAVAILABLE"
    QUOTA_UNAVAILABLE = "QUOTA_UNAVAILABLE"
    CAPTCHA = "CAPTCHA"
    OTP = "OTP"
    PAYMENT_FAILURE = "PAYMENT_FAILURE"
    BOOKING_SUCCESS = "BOOKING_SUCCESS"
    UNKNOWN_BOOKING_STATUS = "UNKNOWN_BOOKING_STATUS"
    USER_ABORT = "USER_ABORT"
    GENERAL_ERROR = "GENERAL_ERROR"


@dataclass
class FailureDetail:
    """Structured representation of a failure occurrence."""

    failure_type: FailureType
    message: str
    is_retryable: bool
    stage: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    original_exception: Optional[Exception] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert failure detail to dictionary."""
        return {
            "failure_type": self.failure_type.value,
            "message": self.message,
            "is_retryable": self.is_retryable,
            "stage": self.stage,
            "details": self.details,
            "exception": str(self.original_exception) if self.original_exception else None,
        }


def classify_failure(
    exc_or_reason: Any,
    stage: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> FailureDetail:
    """Analyze an exception or error string and return a structured FailureDetail.

    Every error produces a human-readable status suitable for user presentation.
    """
    ctx = context or {}
    raw_str = str(exc_or_reason) if exc_or_reason is not None else ""
    orig_exc = exc_or_reason if isinstance(exc_or_reason, Exception) else None

    # Helper: extract context fields
    train_no = str(ctx.get("train_number") or "").strip()
    cls_code = str(ctx.get("class_code") or "").strip()
    pnr = str(ctx.get("pnr") or "").strip()

    # 1. Browser Crash / Disconnection
    is_closed_msg = (
        "browser has been closed" in raw_str.lower()
        or "target page, context or browser has been closed" in raw_str.lower()
        or "browser page is not available or has been closed" in raw_str.lower()
        or "browser closed unexpectedly" in raw_str.lower()
        or "crashed" in raw_str.lower()
        or "connection closed" in raw_str.lower()
        or "targetclosederror" in raw_str.lower()
    )
    if is_closed_msg:
        return FailureDetail(
            failure_type=FailureType.BROWSER_CRASH,
            message="Browser closed unexpectedly or crashed during workflow.",
            is_retryable=False,
            stage=stage,
            details=ctx,
            original_exception=orig_exc,
        )

    # 2. Unknown / Uncertain booking outcome (NEVER RETRY)
    is_uncertain = (
        "uncertain" in raw_str.lower()
        or "ambiguous" in raw_str.lower()
        or "booking status is uncertain" in raw_str.lower()
    )
    if is_uncertain:
        return FailureDetail(
            failure_type=FailureType.UNKNOWN_BOOKING_STATUS,
            message="Booking status is uncertain. Verify IRCTC booking history before attempting another booking.",
            is_retryable=False,
            stage=stage or "confirmation",
            details=ctx,
            original_exception=orig_exc,
        )

    # 3. Booking Success
    is_success = (
        "booking confirmed" in raw_str.lower()
        or "booking successful" in raw_str.lower()
        or "success" in raw_str.lower()
    ) and ("pnr" in raw_str.lower() or bool(pnr))
    if is_success:
        confirmed_pnr = pnr
        if not confirmed_pnr:
            m = re.search(r"\b\d{10}\b", raw_str)
            if m:
                confirmed_pnr = m.group(0)
        msg = f"BOOKING SUCCESSFUL: Booking confirmed! PNR: {confirmed_pnr}" if confirmed_pnr else "BOOKING SUCCESSFUL"
        return FailureDetail(
            failure_type=FailureType.BOOKING_SUCCESS,
            message=msg,
            is_retryable=False,
            stage=stage or "confirmation",
            details={"pnr": confirmed_pnr, **ctx},
            original_exception=orig_exc,
        )

    # 4. Payment Failure (NEVER RETRY)
    is_payment_fail = (
        "payment failed" in raw_str.lower()
        or "payment declined" in raw_str.lower()
        or "transaction failed" in raw_str.lower()
        or "transaction declined" in raw_str.lower()
        or "bank transaction cancelled" in raw_str.lower()
        or (stage in ("payment", "payment_authorization") and "declined" in raw_str.lower())
    )
    if is_payment_fail:
        return FailureDetail(
            failure_type=FailureType.PAYMENT_FAILURE,
            message="Payment failed or was declined by bank/gateway.",
            is_retryable=False,
            stage=stage or "payment",
            details=ctx,
            original_exception=orig_exc,
        )

    # 5. Session Expiration
    is_session_expired = (
        "session expired" in raw_str.lower()
        or "session has expired" in raw_str.lower()
        or "token expired" in raw_str.lower()
        or "your session has expired" in raw_str.lower()
    )
    if is_session_expired:
        return FailureDetail(
            failure_type=FailureType.SESSION_EXPIRATION,
            message="IRCTC session expired. Please log in again to continue.",
            is_retryable=False,
            stage=stage,
            details=ctx,
            original_exception=orig_exc,
        )

    # 6. Quota Unavailable
    is_quota_unavailable = (
        "quota" in raw_str.lower() and ("unavailable" in raw_str.lower() or "exhausted" in raw_str.lower())
        or "regret" in raw_str.lower()
        or "no seats available" in raw_str.lower()
        or "tatkal booking not started" in raw_str.lower()
        or "wl regret" in raw_str.lower()
    )
    if is_quota_unavailable:
        if train_no and cls_code:
            msg = f"Tatkal quota unavailable for train {train_no} in class {cls_code} (Regret / No Seats Available)."
        elif train_no:
            msg = f"Tatkal quota unavailable for train {train_no} (Regret / No Seats Available)."
        else:
            msg = "Tatkal quota unavailable for selected train/class (Regret / No Seats Available)."
        return FailureDetail(
            failure_type=FailureType.QUOTA_UNAVAILABLE,
            message=msg,
            is_retryable=False,
            stage=stage or "train_selection",
            details=ctx,
            original_exception=orig_exc,
        )

    # 7. Train Unavailable
    is_train_unavailable = (
        ("train" in raw_str.lower() or "train_number" in raw_str.lower())
        and ("not found" in raw_str.lower() or "unavailable" in raw_str.lower() or "prohibited" in raw_str.lower())
    )
    if is_train_unavailable:
        if train_no:
            msg = f"Specified train '{train_no}' was not found on results page. Substitution is prohibited."
        else:
            msg = "Specified train was not found on results page. Substitution is prohibited."
        return FailureDetail(
            failure_type=FailureType.TRAIN_UNAVAILABLE,
            message=msg,
            is_retryable=False,
            stage=stage or "train_selection",
            details=ctx,
            original_exception=orig_exc,
        )

    # 8. CAPTCHA Checkpoint / Cancellation
    is_captcha = "captcha" in raw_str.lower()
    if is_captcha:
        if "cancel" in raw_str.lower():
            msg = "CAPTCHA entry cancelled by user."
        elif "timeout" in raw_str.lower():
            msg = "Timeout waiting for human CAPTCHA completion."
        else:
            msg = "CAPTCHA verification required in browser."
        return FailureDetail(
            failure_type=FailureType.CAPTCHA,
            message=msg,
            is_retryable=False,
            stage=stage or "captcha",
            details=ctx,
            original_exception=orig_exc,
        )

    # 9. OTP Checkpoint / Cancellation
    is_otp = "otp" in raw_str.lower()
    if is_otp:
        if "cancel" in raw_str.lower():
            msg = "OTP authentication cancelled by user."
        elif "timeout" in raw_str.lower():
            msg = "Timeout waiting for human OTP entry."
        elif "invalid" in raw_str.lower() or "incorrect" in raw_str.lower():
            msg = "Invalid or incorrect OTP entered in browser."
        else:
            msg = "OTP authentication required in browser."
        return FailureDetail(
            failure_type=FailureType.OTP,
            message=msg,
            is_retryable=False,
            stage=stage or "otp",
            details=ctx,
            original_exception=orig_exc,
        )

    # 10. Page Timeout
    is_timeout = (
        "timeout" in raw_str.lower()
        or "timed out" in raw_str.lower()
        or (orig_exc is not None and "timeout" in orig_exc.__class__.__name__.lower())
    )
    if is_timeout:
        # Contextual human-readable timeout messages
        if stage in ("train_selection", "select_train"):
            msg = "Network timeout while loading train selection."
        elif stage in ("journey_selection", "select_journey"):
            msg = "Network timeout while loading journey search."
        elif stage in ("portal", "open_booking_page"):
            msg = "Network timeout while loading IRCTC portal."
        elif stage in ("passenger_selection", "select_passengers"):
            msg = "Network timeout while loading passenger details form."
        elif stage in ("payment", "payment_authorization"):
            msg = "Timeout waiting for payment gateway response."
        else:
            msg = "Page operation timed out while waiting for IRCTC servers."

        # Limited retry only allowed for ordinary page-loading / network problems pre-payment
        is_retryable = stage not in ("payment", "payment_authorization", "confirmation", "unknown")
        return FailureDetail(
            failure_type=FailureType.PAGE_TIMEOUT,
            message=msg,
            is_retryable=is_retryable,
            stage=stage,
            details=ctx,
            original_exception=orig_exc,
        )

    # 11. Network Error
    is_network_err = (
        "net::err_" in raw_str.lower()
        or "connectionrefused" in raw_str.lower()
        or "connectionreset" in raw_str.lower()
        or "econnrefused" in raw_str.lower()
        or "enotfound" in raw_str.lower()
        or "dns" in raw_str.lower()
        or "name_not_resolved" in raw_str.lower()
        or "internet_disconnected" in raw_str.lower()
    )
    if is_network_err:
        msg = "Network connection error: Unable to reach IRCTC servers. Please check your internet connection."
        is_retryable = stage not in ("payment", "payment_authorization", "confirmation", "unknown")
        return FailureDetail(
            failure_type=FailureType.NETWORK_ERROR,
            message=msg,
            is_retryable=is_retryable,
            stage=stage,
            details=ctx,
            original_exception=orig_exc,
        )

    # 12. User Abort
    if "cancelled by user" in raw_str.lower() or "user cancelled" in raw_str.lower():
        return FailureDetail(
            failure_type=FailureType.USER_ABORT,
            message="Operation cancelled by user.",
            is_retryable=False,
            stage=stage,
            details=ctx,
            original_exception=orig_exc,
        )

    # 13. General Fallback
    fallback_msg = f"Unexpected error during {stage or 'workflow'}: {raw_str}"
    return FailureDetail(
        failure_type=FailureType.GENERAL_ERROR,
        message=fallback_msg,
        is_retryable=False,
        stage=stage,
        details=ctx,
        original_exception=orig_exc,
    )


@dataclass
class RetryPolicy:
    """Manages strict retry logic.

    Permits limited retries ONLY for ordinary page loading/network problems.
    NEVER retries after uncertain payment states, payment failures, or business logic rejections.
    """

    max_retries: int = 2
    retry_delay_seconds: float = 1.0

    def can_retry(
        self,
        failure: FailureDetail,
        attempt: int,
        current_state: Optional[BookingState] = None,
    ) -> bool:
        """Evaluate if an operation is strictly eligible for retry."""
        # 1. Absolute ban on retrying uncertain payment states
        if failure.failure_type == FailureType.UNKNOWN_BOOKING_STATUS:
            return False

        # 2. Absolute ban on retrying payment failures
        if failure.failure_type == FailureType.PAYMENT_FAILURE:
            return False

        # 3. Absolute ban if current state is payment, confirmation, or unknown
        if current_state in (
            BookingState.PAYMENT_REQUIRED,
            BookingState.BOOKING_CONFIRMATION,
            BookingState.UNKNOWN,
            BookingState.SUCCESS,
        ):
            return False

        # 4. Only ordinary page-loading and network issues qualify
        if failure.failure_type not in (FailureType.PAGE_TIMEOUT, FailureType.NETWORK_ERROR):
            return False

        # 5. Check retry limit
        return failure.is_retryable and attempt < self.max_retries


T = TypeVar("T")


def execute_with_limited_retry(
    action: Callable[[int], T],
    stage: str = "",
    context: Optional[Dict[str, Any]] = None,
    policy: Optional[RetryPolicy] = None,
    on_retry: Optional[Callable[[int, FailureDetail], None]] = None,
    current_state: Optional[BookingState] = None,
) -> T:
    """Execute an action with controlled, limited retries for ordinary page/network problems.

    Raises RuntimeError with human-readable error description on failure.
    """
    retry_policy = policy or RetryPolicy()
    attempt = 0

    while True:
        try:
            return action(attempt)
        except Exception as exc:
            attempt += 1
            failure = classify_failure(exc, stage=stage, context=context)

            if retry_policy.can_retry(failure, attempt=attempt, current_state=current_state):
                if on_retry is not None:
                    try:
                        on_retry(attempt, failure)
                    except Exception:
                        pass
                if retry_policy.retry_delay_seconds > 0:
                    time.sleep(retry_policy.retry_delay_seconds)
                continue

            # Non-retryable or retries exhausted
            raise RuntimeError(failure.message) from exc
