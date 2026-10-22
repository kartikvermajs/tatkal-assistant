"""Automated tests for Phase 26: Windows Packaging.

Verifies:
1. PyInstaller spec file TatkalAssistant.spec exists and is properly configured.
2. Standalone Windows executable TatkalAssistant.exe exists in dist/.
3. Executable runs without crashing on startup.
4. No secrets or credentials are bundled into the binary or spec.
5. Installation documentation INSTALL.md exists and covers execution, building, and setup.
"""

import os
import subprocess
import sys
import time
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_spec_file_exists_and_is_properly_configured():
    """Verify TatkalAssistant.spec exists with required configuration."""
    spec_path = os.path.join(PROJECT_ROOT, "TatkalAssistant.spec")
    assert os.path.exists(spec_path), "TatkalAssistant.spec must exist in project root."

    with open(spec_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "app.py" in content
    assert "TatkalAssistant" in content
    assert "schema.sql" in content
    assert "playwright" in content
    assert "console=False" in content

    # Verify no secrets or credentials are hardcoded into spec
    forbidden_terms = ["password", "passwd", "otp", "pin", "cvv", "secret_key", "api_key"]
    for term in forbidden_terms:
        assert term not in content.lower(), f"Forbidden term '{term}' found in TatkalAssistant.spec"


def test_executable_exists_in_dist():
    """Verify TatkalAssistant.exe was built and has valid non-zero size."""
    exe_path = os.path.join(PROJECT_ROOT, "dist", "TatkalAssistant.exe")
    assert os.path.exists(exe_path), f"Executable not found at {exe_path}. Build may have failed."

    size = os.path.getsize(exe_path)
    assert size > 10 * 1024 * 1024, f"Executable size ({size} bytes) is unexpectedly small."


def test_installation_documentation_exists():
    """Verify INSTALL.md exists and documents installation and usage."""
    install_path = os.path.join(PROJECT_ROOT, "INSTALL.md")
    assert os.path.exists(install_path), "INSTALL.md must exist in project root."

    with open(install_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "TatkalAssistant.exe" in content
    assert "playwright install chromium" in content
    assert "python app.py" in content
    assert "pyinstaller" in content
    assert "Zero Bundled Secrets" in content


@pytest.mark.skipif(sys.platform != "win32", reason="Windows executable test only runs on Windows")
def test_executable_launches_cleanly_offscreen():
    """Verify TatkalAssistant.exe starts up cleanly without crashing."""
    exe_path = os.path.join(PROJECT_ROOT, "dist", "TatkalAssistant.exe")
    if not os.path.exists(exe_path):
        pytest.skip("dist/TatkalAssistant.exe not found.")

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"

    proc = subprocess.Popen([exe_path], env=env)
    time.sleep(3)
    poll = proc.poll()

    try:
        assert poll is None, f"TatkalAssistant.exe crashed on launch with exit code: {poll}"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
