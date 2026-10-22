"""Automated test suite for Phase 20: Application Logging & Privacy Sanitization.

Verifies:
- Creation and persistence of local application log
- Correct timestamp format: YYYY-MM-DD HH:MM:SS <Message>
- Complete sequence of lifecycle and workflow log events:
    Browser started
    IRCTC opened
    Workflow started
    Journey selected
    Train selected
    Passenger selection complete
    CAPTCHA required
    User continued
    Payment stage
    Payment authorization required
- Strict security & privacy redaction:
    Never log passwords
    Never log OTP
    Never log PIN
    Never log CVV
    Never log cookies
    Never log session tokens
    Never log authentication headers
- UI LogViewerDialog integration
"""

from datetime import datetime
import os
import re
from unittest.mock import MagicMock
import pytest

from core.logger import (
    AppLogger,
    get_app_logger,
    is_sensitive,
    log_event,
    sanitize_log_message,
    set_app_logger,
)
from ui.log_viewer_dialog import LogViewerDialog


@pytest.fixture
def temp_logger(tmp_path):
    """Fixture providing an isolated AppLogger writing to a temporary file."""
    log_file = str(tmp_path / "test_app.log")
    logger = AppLogger(log_file=log_file)
    old_logger = get_app_logger()
    set_app_logger(logger)
    yield logger
    set_app_logger(old_logger)


# ==================== 1. Log Format & Timestamp ====================

def test_log_entry_format(temp_logger):
    """Log entry must match 'YYYY-MM-DD HH:MM:SS <Message>'."""
    entry = temp_logger.log("Browser started")

    # Match exact regex format
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (.*)$", entry)
    assert match is not None, f"Entry did not match expected format: {entry}"

    timestamp_str, msg = match.groups()
    assert msg == "Browser started"

    # Verify timestamp parses as valid datetime
    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    assert dt.year >= 2026


def test_log_file_persistence(temp_logger):
    """Entries must be written to disk and readable via get_recent_logs."""
    temp_logger.log("Test log line 1")
    temp_logger.log("Test log line 2")

    logs = temp_logger.get_recent_logs()
    assert len(logs) == 2
    assert "Test log line 1" in logs[0]
    assert "Test log line 2" in logs[1]

    # Verify physical file on disk
    assert os.path.exists(temp_logger.log_file)
    with open(temp_logger.log_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Test log line 1" in content
    assert "Test log line 2" in content


# ==================== 2. Lifecycle & Workflow Event Sequence ====================

def test_workflow_lifecycle_events_sequence(temp_logger):
    """Verify logging of complete canonical sequence from Phase 20 prompt."""
    expected_events = [
        "Browser started",
        "IRCTC opened",
        "Workflow started",
        "Journey selected",
        "Train selected",
        "Passenger selection complete",
        "CAPTCHA required",
        "User continued",
        "Payment stage",
        "Payment authorization required",
    ]

    for evt in expected_events:
        temp_logger.log(evt)

    logs = temp_logger.get_recent_logs()
    assert len(logs) == len(expected_events)

    for i, evt in enumerate(expected_events):
        assert evt in logs[i], f"Expected '{evt}' at index {i}, got '{logs[i]}'"


# ==================== 3. Strict Security & Privacy Redaction ====================

def test_never_log_passwords(temp_logger):
    """Passwords must be scrubbed/redacted from log entries."""
    raw = "User entered password=SuperSecretPassword123 during login"
    sanitized = sanitize_log_message(raw)
    assert "SuperSecretPassword123" not in sanitized
    assert "password=[REDACTED]" in sanitized

    entry = temp_logger.log(raw)
    assert "SuperSecretPassword123" not in entry


def test_never_log_otp(temp_logger):
    """OTPs must be scrubbed/redacted from log entries."""
    test_cases = [
        ("Received otp=482910 for authentication", "482910"),
        ("User entered OTP: 654321", "654321"),
        ("Aadhaar OTP 789123 submitted", "789123"),
    ]
    for raw, secret in test_cases:
        sanitized = sanitize_log_message(raw)
        assert secret not in sanitized, f"Found secret OTP '{secret}' in sanitized: {sanitized}"
        assert "[REDACTED]" in sanitized

        entry = temp_logger.log(raw)
        assert secret not in entry


def test_never_log_pin(temp_logger):
    """eWallet and financial PINs must never be logged."""
    test_cases = [
        ("Authorizing payment with eWallet PIN=1234", "1234"),
        ("User entered mpin: 9876", "9876"),
        ("UPI PIN=456789 verified", "456789"),
    ]
    for raw, secret in test_cases:
        sanitized = sanitize_log_message(raw)
        assert secret not in sanitized, f"Found secret PIN '{secret}' in sanitized: {sanitized}"
        assert "[REDACTED]" in sanitized

        entry = temp_logger.log(raw)
        assert secret not in entry


def test_never_log_cvv(temp_logger):
    """Credit/Debit card CVVs must never be logged."""
    test_cases = [
        ("Credit card cvv=891 entered", "891"),
        ("Security code CVC: 456 provided", "456"),
    ]
    for raw, secret in test_cases:
        sanitized = sanitize_log_message(raw)
        assert secret not in sanitized, f"Found secret CVV '{secret}' in sanitized: {sanitized}"
        assert "[REDACTED]" in sanitized

        entry = temp_logger.log(raw)
        assert secret not in entry


def test_never_log_cookies(temp_logger):
    """Cookies and session identifiers must never be logged."""
    raw = "Request headers Cookie: JSESSIONID=ABCD1234EFGH; user_token=xyz"
    sanitized = sanitize_log_message(raw)
    assert "JSESSIONID=ABCD1234EFGH" not in sanitized
    assert "Cookie: [REDACTED]" in sanitized

    entry = temp_logger.log(raw)
    assert "ABCD1234EFGH" not in entry


def test_never_log_session_tokens(temp_logger):
    """Session and auth tokens must never be logged."""
    raw = "Captured session_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    sanitized = sanitize_log_message(raw)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
    assert "session_token=[REDACTED]" in sanitized

    entry = temp_logger.log(raw)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in entry


def test_never_log_authentication_headers(temp_logger):
    """Authorization headers must never be logged."""
    raw = "Outbound HTTP Authorization: Bearer secret_jwt_token_abcdef123456"
    sanitized = sanitize_log_message(raw)
    assert "secret_jwt_token_abcdef123456" not in sanitized
    assert "[REDACTED]" in sanitized

    entry = temp_logger.log(raw)
    assert "secret_jwt_token_abcdef123456" not in entry


# ==================== 4. Listeners & Real-Time Updates ====================

def test_logger_listener_receives_entries(temp_logger):
    """Registered listeners should receive every new log entry."""
    received = []

    def callback(entry: str):
        received.append(entry)

    temp_logger.add_listener(callback)
    temp_logger.log("First event")
    temp_logger.log("Second event")

    assert len(received) == 2
    assert "First event" in received[0]
    assert "Second event" in received[1]

    # Test unregister
    temp_logger.remove_listener(callback)
    temp_logger.log("Third event")
    assert len(received) == 2


# ==================== 5. UI Integration & Dialog ====================

def test_log_viewer_dialog(qapp, temp_logger):
    """LogViewerDialog must load and display log lines in a read-only viewer."""
    temp_logger.log("Browser started")
    temp_logger.log("IRCTC opened")

    dialog = LogViewerDialog()
    dialog.refresh_logs()

    text = dialog.log_text.toPlainText()
    assert "Browser started" in text
    assert "IRCTC opened" in text
    assert dialog.log_text.isReadOnly() is True


def test_main_window_has_view_logs_button(qapp, tmp_path):
    """MainWindow must provide a functional 'View Logs' button."""
    from database.db import Database
    from ui.main_window import MainWindow

    db = Database(str(tmp_path / "test_main_logs.db"))
    window = MainWindow(db)

    assert hasattr(window, "view_logs_btn")
    assert window.view_logs_btn.text() == "View Logs"
