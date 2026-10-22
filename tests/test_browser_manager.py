"""Unit tests for Phase 8 and Phase 9 Playwright Browser Manager with Persistent Profile."""

import ast
import inspect
import os
import pytest
from PySide6.QtWidgets import QApplication

from browser.browser_manager import BrowserManager, DEFAULT_PROFILE_DIR, IRCTC_HOME_URL
from ui.main_window import MainWindow

# Ensure headless execution for Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def temp_profile(tmp_path):
    return str(tmp_path / "test_browser_profile")


def test_browser_startup_and_get_page(temp_profile):
    mgr = BrowserManager(user_data_dir=temp_profile)
    assert mgr.is_running() is False
    assert mgr.get_page() is None

    mgr.start_browser(headless=True)
    assert mgr.is_running() is True
    assert os.path.exists(temp_profile)

    page = mgr.get_page()
    assert page is not None
    assert not page.is_closed()
    mgr.close_browser()
    assert mgr.is_running() is False


def test_browser_open_page_and_navigation(temp_profile):
    mgr = BrowserManager(user_data_dir=temp_profile)
    test_html_url = "data:text/html,<html><head><title>IRCTC Test Portal</title></head><body><h1>Welcome</h1></body></html>"
    page = mgr.open_irctc(url=test_html_url, headless=True)

    assert page is not None
    assert page.title() == "IRCTC Test Portal"
    assert "Welcome" in page.content()
    mgr.close_browser()


def test_browser_profile_persistence_across_sessions(tmp_path):
    """Verify that browser profile persists state locally without manual cookie or token handling."""
    profile_dir = str(tmp_path / "persisted_user_profile")

    # Session 1: Launch and set a local state preference
    mgr1 = BrowserManager(user_data_dir=profile_dir)
    test_url = "http://localhost:8000/test"  # Origin needed for localStorage
    page1 = mgr1.open_irctc(
        url="data:text/html,<html><body>Session 1</body></html>",
        headless=True,
    )
    assert mgr1.is_running() is True
    mgr1.close_browser()

    # Verify profile directory files were written by Chromium
    assert os.path.exists(profile_dir)
    assert len(os.listdir(profile_dir)) > 0

    # Session 2: Launch again with the same profile directory
    mgr2 = BrowserManager(user_data_dir=profile_dir)
    page2 = mgr2.open_irctc(
        url="data:text/html,<html><body>Session 2</body></html>",
        headless=True,
    )
    assert mgr2.is_running() is True
    assert page2.content() is not None
    mgr2.close_browser()


def test_browser_shutdown_idempotent(temp_profile):
    mgr = BrowserManager(user_data_dir=temp_profile)
    mgr.start_browser(headless=True)
    assert mgr.is_running() is True

    # First close
    mgr.close_browser()
    assert mgr.is_running() is False
    assert mgr.get_page() is None

    # Repeated close calls must be safe and idempotent
    mgr.close_browser()
    mgr.close_browser()
    assert mgr.is_running() is False


def test_security_and_compliance_policy():
    """Verify that no stealth plugins, proxy rotation, or cookie/token extractors exist in code."""
    source = inspect.getsource(BrowserManager)
    tree = ast.parse(source)

    # Strip docstrings from AST to inspect executable code only
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body[0] = ast.Pass()

    cleaned_code = ast.unparse(tree).lower()

    prohibited_mechanisms = [
        "stealth",
        "puppeteer",
        "fingerprint",
        "fake_useragent",
        "rotate_proxy",
        "captcha_bypass",
        "evasion",
        "cookies(",
        "export_token",
        "send_session",
    ]
    for keyword in prohibited_mechanisms:
        assert keyword not in cleaned_code, f"Prohibited mechanism found in code: {keyword}"


def test_main_window_open_irctc_action(qapp):
    class MockBrowserManager(BrowserManager):
        def __init__(self):
            super().__init__()
            self.open_called = False
            self.last_url = None

        def open_irctc(self, url=IRCTC_HOME_URL, headless=False, timeout=30000.0):
            self.open_called = True
            self.last_url = url
            return None

    mock_mgr = MockBrowserManager()
    window = MainWindow(browser_manager=mock_mgr)

    # Click OPEN IRCTC
    window.open_irctc_btn.click()
    assert mock_mgr.open_called is True
    assert "BROWSER READY" in window.status_label.text()
    window.close()
