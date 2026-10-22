def test_environment():
    import PySide6
    import playwright
    import pytest
    assert PySide6 is not None
    assert playwright is not None
    assert pytest is not None
