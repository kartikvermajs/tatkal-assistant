"""Global Pytest fixtures for desktop application testing."""

import os
import pytest
from PySide6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    """Shared single QApplication instance for test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
