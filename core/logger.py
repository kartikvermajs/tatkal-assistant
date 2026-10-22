"""Local application logger with strict privacy and credential sanitization.

Provides append-only local disk logging formatted with timestamps:
  YYYY-MM-DD HH:MM:SS <Message>

Strict Security & Privacy Policies:
Never log:
- passwords
- OTP
- PIN
- CVV
- cookies
- session tokens
- authentication headers
"""

from datetime import datetime
import os
from pathlib import Path
import re
import threading
from typing import Callable, List, Optional

import config
from core.clock import current_ist

# Regex patterns for defense-in-depth sanitization of sensitive data
_SENSITIVE_PATTERNS = [
    # Passwords
    (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
    # OTP (4 to 8 digit OTP codes or explicit OTP keys)
    (re.compile(r"(?i)\b(otp|one[ -]?time[ -]?password)\b\s*[:=]?\s*\d{4,8}"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)(?<=otp\s)\b\d{4,8}\b"), "[REDACTED]"),
    # PIN (eWallet PIN, MPIN, UPI PIN)
    (re.compile(r"(?i)\b(pin|mpin|ewallet[ -]?pin|upi[ -]?pin)\b\s*[:=]?\s*\d{4,6}"), r"\1=[REDACTED]"),
    # CVV / CVC
    (re.compile(r"(?i)\b(cvv|cvc|security[ -]?code)\b\s*[:=]?\s*\d{3,4}"), r"\1=[REDACTED]"),
    # Cookies / Set-Cookie headers
    (re.compile(r"(?i)(cookie|set-cookie)\s*:\s*[^\r\n]+"), r"\1: [REDACTED]"),
    # Session tokens / JWT
    (re.compile(r"(?i)(token|session_?token|auth_?token|jwt)\s*[:=]\s*[A-Za-z0-9_\-\.]{12,}"), r"\1=[REDACTED]"),
    # Authentication / Authorization headers
    (re.compile(r"(?i)(authorization|proxy-authorization)\s*:\s*[^\r\n]+"), r"\1: [REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.]{12,}"), "Bearer [REDACTED]"),
]


def sanitize_log_message(message: str) -> str:
    """Scrub passwords, OTP, PIN, CVV, cookies, session tokens, and auth headers from message."""
    if not message:
        return ""
    sanitized = str(message)
    for pattern, replacement in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def is_sensitive(message: str) -> bool:
    """Check whether a raw message matches any sensitive credential patterns."""
    if not message:
        return False
    msg_str = str(message)
    for pattern, _ in _SENSITIVE_PATTERNS:
        if pattern.search(msg_str):
            return True
    return False


class AppLogger:
    """Local file-based application logger with timestamped entries and thread safety."""

    def __init__(self, log_file: Optional[str] = None) -> None:
        self.log_file = log_file or config.DEFAULT_LOG_FILE
        self._lock = threading.Lock()
        self._listeners: List[Callable[[str], None]] = []
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        """Create parent directory for log file if it does not exist."""
        try:
            parent = os.path.dirname(os.path.abspath(self.log_file))
            if parent:
                os.makedirs(parent, exist_ok=True)
        except Exception:
            pass

    def add_listener(self, callback: Callable[[str], None]) -> None:
        """Register listener for new log entries (e.g. for live GUI display)."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str], None]) -> None:
        """Unregister listener callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def log(self, message: str) -> str:
        """Sanitize message, append timestamped line to local log file, and notify listeners.

        Format:
            YYYY-MM-DD HH:MM:SS <Message>
        """
        clean_msg = sanitize_log_message(message).strip()
        timestamp = current_ist().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{timestamp} {clean_msg}"

        with self._lock:
            try:
                self._ensure_log_dir()
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
            except Exception:
                pass

        for listener in list(self._listeners):
            try:
                listener(entry)
            except Exception:
                pass

        return entry

    def get_recent_logs(self, limit: int = 100) -> List[str]:
        """Read the last `limit` lines from the local log file."""
        with self._lock:
            if not os.path.exists(self.log_file):
                return []
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                return [line.strip() for line in lines[-limit:] if line.strip()]
            except Exception:
                return []

    def clear(self) -> None:
        """Empty the local log file."""
        with self._lock:
            if os.path.exists(self.log_file):
                try:
                    with open(self.log_file, "w", encoding="utf-8"):
                        pass
                except Exception:
                    pass


# Global default logger instance
_default_logger: Optional[AppLogger] = None


def get_app_logger() -> AppLogger:
    """Return the global default AppLogger instance."""
    global _default_logger
    if _default_logger is None:
        _default_logger = AppLogger()
    return _default_logger


def set_app_logger(logger: AppLogger) -> None:
    """Override the global default AppLogger instance (useful for tests)."""
    global _default_logger
    _default_logger = logger


def log_event(message: str) -> str:
    """Convenience helper to record an application event to the default log file."""
    return get_app_logger().log(message)
