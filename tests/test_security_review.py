"""Automated tests for Phase 24: Security Review.

Systematically verifies:
1. No passwords stored in database, models, or configs.
2. No OTP stored or intercepted.
3. No PIN stored or automated.
4. No CVV or card details stored or automated.
5. No credentials sent to external services (zero tracking/telemetry/cloud endpoints).
6. No CAPTCHA bypass or automated solving mechanisms.
7. No anti-bot or fingerprint evasion bypasses.
8. No stealth browser patches or plugins.
9. No proxy rotation or proxy pool networks.
10. No credential harvesting (no keyloggers, clipboard watchers, or form interceptors).
11. No hidden network calls (centralized IRCTC URLs only, local mock testing only).
12. Comprehensive local data persistence documentation in SECURITY.md.
"""

import ast
import os
import re
import sqlite3
import pytest

import config
from core.logger import sanitize_log_message, is_sensitive
from models.settings import ApplicationSettings, PROHIBITED_CREDENTIAL_KEYS


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_all_python_files(include_tests: bool = False):
    """Yield relative paths to all Python files in the project."""
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Exclude virtualenvs, cache, and git
        if any(skip in root for skip in [".venv", "venv", "__pycache__", ".pytest_cache", ".git"]):
            continue
        if not include_tests and "tests" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


# ==================== 1. Local Data & Database Schema Audit ====================


def test_security_documentation_exists_and_covers_all_areas():
    """Verify that SECURITY.md exists and documents all local storage tables and security policies."""
    sec_path = os.path.join(PROJECT_ROOT, "SECURITY.md")
    assert os.path.exists(sec_path), "SECURITY.md must exist in the project root."

    with open(sec_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify key sections
    assert "## 1. Core Security & Compliance Guarantees" in content
    assert "## 2. Local Data Persistence Audit" in content
    assert "Table: `trips`" in content
    assert "Table: `passengers`" in content
    assert "Table: `settings`" in content
    assert "Table: `bookings`" in content
    assert "data/app.log" in content
    assert "data/browser_profile/" in content
    assert "No Password Storage" in content
    assert "No OTP Interception" in content
    assert "No Financial Credentials" in content
    assert "No CAPTCHA Bypass" in content
    assert "No Anti-Bot Bypass" in content
    assert "No Proxy Rotation" in content


def test_sqlite_schema_has_zero_credential_columns():
    """Verify that SQLite schema has no columns for storing passwords, OTPs, PINs, CVVs, or card numbers."""
    schema_path = os.path.join(PROJECT_ROOT, "database", "schema.sql")
    assert os.path.exists(schema_path)

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Parse tables in an in-memory SQLite database
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.executescript(schema_sql)

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]

    assert set(tables) == {"trips", "passengers", "settings", "bookings"}

    forbidden_keywords = {
        "password",
        "passwd",
        "otp",
        "pin",
        "cvv",
        "cvc",
        "card",
        "secret",
        "token",
        "credential",
    }

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = [row[1].lower() for row in cursor.fetchall()]
        for col in columns:
            for kw in forbidden_keywords:
                assert kw not in col, f"Security violation: Table '{table}' contains prohibited column '{col}'."

    conn.close()


def test_active_sqlite_database_has_zero_credential_columns():
    """Verify that the active SQLite database on disk has no credential columns."""
    db_path = os.path.join(PROJECT_ROOT, "data", "tatkal_assistant.db")
    if not os.path.exists(db_path):
        pytest.skip("data/tatkal_assistant.db not yet created.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]

    forbidden_keywords = {
        "password",
        "passwd",
        "otp",
        "pin",
        "cvv",
        "cvc",
        "card",
        "secret",
        "token",
        "credential",
    }

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = [row[1].lower() for row in cursor.fetchall()]
        for col in columns:
            for kw in forbidden_keywords:
                assert kw not in col, f"Prohibited column '{col}' found in live database table '{table}'."

    conn.close()


def test_settings_model_strictly_rejects_credential_keys():
    """Verify ApplicationSettings strictly raises ValueError when attempting to store any credential key."""
    for forbidden in PROHIBITED_CREDENTIAL_KEYS:
        with pytest.raises(ValueError, match="Security violation"):
            ApplicationSettings.from_dict({forbidden: "secret_value_123"})

        with pytest.raises(ValueError, match="Security violation"):
            ApplicationSettings.from_dict({f"user_{forbidden}": "secret_value_123"})


# ==================== 2. Prohibited Libraries & Stealth Bypass Audit ====================


def test_no_prohibited_libraries_or_imports_in_source_code():
    """Verify that no prohibited third-party libraries for stealth, CAPTCHA bypass,
    or remote telemetry are imported anywhere in the production source code.
    """
    prohibited_modules = {
        # OCR / CAPTCHA bypass
        "pytesseract",
        "easyocr",
        "2captcha",
        "anticaptcha",
        "capmonster",
        "deathbycaptcha",
        "cv2",
        # Anti-bot / stealth
        "playwright_stealth",
        "undetected_chromedriver",
        "selenium",
        "selenium_stealth",
        # Telemetry / tracking / cloud
        "sentry_sdk",
        "datadog",
        "mixpanel",
        "segment",
        "telemetry",
        "google.analytics",
        # Remote HTTP libraries outside standard Playwright & local mock server
        "requests",
        "httpx",
        "aiohttp",
        "urllib3",
    }

    violations = []
    for py_file in get_all_python_files(include_tests=False):
        with open(py_file, "r", encoding="utf-8") as f:
            content = f.read()

        try:
            tree = ast.parse(content, filename=py_file)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prohibited in prohibited_modules:
                        if alias.name == prohibited or alias.name.startswith(f"{prohibited}."):
                            violations.append((py_file, node.lineno, f"import {alias.name}"))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for prohibited in prohibited_modules:
                        if node.module == prohibited or node.module.startswith(f"{prohibited}."):
                            violations.append((py_file, node.lineno, f"from {node.module} import ..."))

    assert len(violations) == 0, f"Found prohibited imports in production code: {violations}"


def test_browser_manager_uses_zero_stealth_or_evasion_flags():
    """Verify BrowserManager uses standard Chromium launch parameters without stealth evasion flags."""
    bm_file = os.path.join(PROJECT_ROOT, "browser", "browser_manager.py")
    with open(bm_file, "r", encoding="utf-8") as f:
        content = f.read()

    prohibited_stealth_flags = [
        "--disable-blink-features=AutomationControlled",
        "excludeSwitches",
        "--enable-automation",
        "navigator.webdriver",
        "playwright_stealth",
        "stealth_sync",
        "--proxy-server",
        "rotate_proxy",
    ]

    for flag in prohibited_stealth_flags:
        assert flag.lower() not in content.lower(), (
            f"Prohibited anti-bot or stealth flag '{flag}' found in browser_manager.py"
        )


def test_no_proxy_rotation_logic_in_browser_or_core():
    """Verify that no proxy rotation or proxy pool logic exists."""
    for py_file in get_all_python_files(include_tests=False):
        with open(py_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "proxy_pool" not in content.lower()
        assert "rotate_proxy" not in content.lower()
        assert "proxy_rotation" not in content.lower()


# ==================== 3. Human-in-the-Loop Verification ====================


def test_workflow_has_human_captcha_checkpoint_and_no_solver():
    """Verify that IRCTCWorkflow halts at CAPTCHA for human input and does not attempt automated solving."""
    wf_file = os.path.join(PROJECT_ROOT, "browser", "irctc_workflow.py")
    with open(wf_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "def wait_for_human_captcha" in content
    assert "CAPTCHA encountered. Complete the CAPTCHA in the browser." in content

    # Verify no solver functions exist
    assert "solve_captcha" not in content.lower()
    assert "ocr_captcha" not in content.lower()
    assert "bypass_captcha" not in content.lower()


def test_workflow_has_human_otp_checkpoint_and_no_interception():
    """Verify that IRCTCWorkflow halts for human OTP entry and never intercepts SMS, email, or clipboard."""
    wf_file = os.path.join(PROJECT_ROOT, "browser", "irctc_workflow.py")
    with open(wf_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "def wait_for_human_otp" in content
    assert "OTP REQUIRED" in content

    # Verify no automated OTP interception logic exists
    assert "read_sms" not in content.lower()
    assert "intercept_otp" not in content.lower()
    assert "read_clipboard" not in content.lower()
    assert "qclipboard" not in content.lower()


def test_workflow_has_human_payment_authorization_and_no_credential_storage():
    """Verify payment workflow halts for human authorization and stores zero PINs or CVVs."""
    wf_file = os.path.join(PROJECT_ROOT, "browser", "irctc_workflow.py")
    with open(wf_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "def wait_for_payment_authorization" in content
    assert "Never automated" in content
    assert "Enter eWallet PIN / CVV / Banking OTP directly into the browser window." in content

    # Verify no auto-fill for banking PIN or CVV
    assert "auto_fill_cvv" not in content.lower()
    assert "auto_fill_pin" not in content.lower()
    assert "store_pin" not in content.lower()


# ==================== 4. Network Endpoints & Centralization Audit ====================


def test_no_external_endpoints_in_production_code_outside_centralized_config():
    """Verify that production code contains zero hardcoded external domains outside config.py and local host."""
    url_pattern = re.compile(r"https?://([a-zA-Z0-9.-]+)")
    allowed_domains = {
        "www.irctc.co.in",
        "irctc.co.in",
        "localhost",
        "127.0.0.1",
        "www.w3.org",  # Standard XML/HTML namespace
    }

    violations = []
    for py_file in get_all_python_files(include_tests=False):
        rel_file = os.path.relpath(py_file, PROJECT_ROOT)
        with open(py_file, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                # Allow comments or docstrings if any, but check all URLs found
                for match in url_pattern.finditer(line):
                    domain = match.group(1).lower()
                    if domain not in allowed_domains:
                        violations.append((rel_file, lineno, match.group(0)))

    assert len(violations) == 0, f"Found unauthorized external endpoints: {violations}"


def test_centralized_irctc_urls_in_config():
    """Verify all official IRCTC URLs reside in config.py and match standard endpoints."""
    assert config.IRCTC_BASE_URL.startswith("https://www.irctc.co.in")
    assert config.IRCTC_BOOKING_URL.startswith("https://www.irctc.co.in")
    assert config.IRCTC_LOGIN_URL.startswith("https://www.irctc.co.in")


# ==================== 5. Log Sanitization & Sensitive Data Redaction ====================


def test_log_sanitizer_redacts_passwords_otps_pins_cvvs_and_tokens():
    """Verify that sanitize_log_message successfully redacts all sensitive credential patterns."""
    raw_samples = [
        ("User login password=SecretPassword123!", "password=[REDACTED]"),
        ("Received otp 482910 from service", "[REDACTED]"),
        ("OTP: 9582", "otp=[REDACTED]"),
        ("eWallet pin 1234 entered", "[REDACTED]"),
        ("CVV: 789", "cvv=[REDACTED]"),
        ("Cookie: session_id=xyz123456789; auth=token", "Cookie: [REDACTED]"),
        ("Authorization: Bearer my_jwt_token_123456789", "Bearer [REDACTED]"),
    ]

    for raw, expected_redaction in raw_samples:
        clean = sanitize_log_message(raw)
        assert expected_redaction in clean or "[REDACTED]" in clean
        assert "SecretPassword123!" not in clean
        assert "482910" not in clean
        assert "my_jwt_token_123456789" not in clean


def test_live_application_log_has_zero_credential_leaks():
    """Verify that the existing data/app.log file on disk contains zero unredacted credential leaks."""
    log_file = os.path.join(PROJECT_ROOT, "data", "app.log")
    if not os.path.exists(log_file):
        pytest.skip("data/app.log not yet created.")

    leak_patterns = [
        re.compile(r"(?i)\bpassword\s*[:=]\s*(?!\[REDACTED\])[^\s,;]+"),
        re.compile(r"(?i)\botp\s*[:=]\s*(?!\[REDACTED\])\d{4,8}"),
        re.compile(r"(?i)\bpin\s*[:=]\s*(?!\[REDACTED\])\d{4,6}"),
        re.compile(r"(?i)\bcvv\s*[:=]\s*(?!\[REDACTED\])\d{3,4}"),
    ]

    with open(log_file, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            for pat in leak_patterns:
                assert not pat.search(line), f"Credential leak found in app.log at line {lineno}: {line.strip()}"
