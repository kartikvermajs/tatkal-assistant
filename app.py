"""Entry point for the Tatkal Assistant desktop application."""

import sys
from PySide6.QtWidgets import QApplication

from browser.browser_manager import ensure_playwright_browsers_path
from ui.main_window import MainWindow
from ui.theme import setup_application_theme


def main() -> int:
    """Initialize and run the desktop application."""
    ensure_playwright_browsers_path()
    app = QApplication(sys.argv)
    setup_application_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
