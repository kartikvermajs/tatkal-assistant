"""Playwright browser manager for legitimate user-controlled browsing with local persistence."""

import os
from typing import Optional
from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

import config
from core.logger import log_event

DEFAULT_PROFILE_DIR = os.path.join(config.DATA_DIR, "browser_profile")
IRCTC_HOME_URL = config.IRCTC_BOOKING_URL


def ensure_playwright_browsers_path() -> str:
    """Ensure PLAYWRIGHT_BROWSERS_PATH points to the installed browser cache, avoiding PyInstaller bundled path errors."""
    current_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if current_path and current_path != "0" and os.path.exists(current_path):
        return current_path

    # Standard locations on Windows and other OSes
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright"),
        os.path.expanduser(r"~\AppData\Local\ms-playwright"),
        os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "ms-playwright"),
        os.path.expanduser("~/.cache/ms-playwright"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = path
            return path

    fallback = candidates[0]
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = fallback
    return fallback


class BrowserManager:
    """Manages a standard Chromium browser instance using a local persistent profile.

    Security & Compliance Policy:
    - Browser profile is stored locally only to preserve legitimate standard browser state.
    - NO manual extraction, export, or transmission of cookies.
    - NO extraction, storage, or transmission of session tokens.
    - NO stealth plugins, proxy rotation, or fingerprint spoofing.
    - User completes all authentication and CAPTCHAs manually.
    """

    def __init__(self, user_data_dir: Optional[str] = None) -> None:
        self.user_data_dir = user_data_dir or DEFAULT_PROFILE_DIR
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def is_running(self) -> bool:
        """Check whether the persistent browser context and active page are open."""
        return (
            self._context is not None
            and self._page is not None
            and not self._page.is_closed()
        )

    def start_browser(self, headless: bool = False) -> None:
        """Start a visible Chromium browser with the configured local profile."""
        if self.is_running():
            return

        self.close_browser()

        os.makedirs(self.user_data_dir, exist_ok=True)
        ensure_playwright_browsers_path()
        self._playwright = sync_playwright().start()

        launch_kwargs = {
            "user_data_dir": self.user_data_dir,
            "headless": headless,
            "args": [
                "--start-maximized",
            ],
            "no_viewport": True,
        }

        try:
            self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as exc:
            err_msg = str(exc).lower()
            if "executable doesn't exist" in err_msg or "download new browsers" in err_msg:
                # Fallback to system Chrome or Edge channels if Playwright Chromium binary is missing
                launched = False
                for channel in ("chrome", "msedge"):
                    try:
                        self._context = self._playwright.chromium.launch_persistent_context(
                            channel=channel,
                            **launch_kwargs,
                        )
                        launched = True
                        break
                    except Exception:
                        continue
                if not launched:
                    raise exc
            else:
                raise exc

        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()

        log_event("Browser started")

    def get_page(self) -> Optional[Page]:
        """Return the current active browser page."""
        if self._page is not None and not self._page.is_closed():
            return self._page
        return None

    def open_irctc(
        self,
        url: Optional[str] = None,
        headless: bool = False,
        timeout: float = 30000.0,
    ) -> Page:
        """Launch browser using the local profile and navigate to official IRCTC portal."""
        target_url = url or config.IRCTC_BOOKING_URL
        if not self.is_running():
            self.start_browser(headless=headless)

        page = self.get_page()
        if page is None:
            raise RuntimeError("Failed to create or access browser page.")

        # Navigate to IRCTC home
        page.goto(target_url, timeout=timeout, wait_until="domcontentloaded")
        log_event("IRCTC opened")
        return page

    def stop_automation(self) -> None:
        """Immediately halt active browser navigations and page scripts."""
        if self._page is not None and not self._page.is_closed():
            try:
                self._page.evaluate("window.stop()")
            except Exception:
                pass

    def close_browser(self) -> None:
        """Cleanly close context, pages, and Playwright driver."""
        try:
            if self._page is not None and not self._page.is_closed():
                self._page.close()
        except Exception:
            pass
        finally:
            self._page = None

        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        finally:
            self._context = None

        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._playwright = None

        log_event("Browser closed")
