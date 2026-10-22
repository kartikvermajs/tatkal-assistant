# Installation & Deployment Guide

This guide details how to install, configure, build, and run **Tatkal Assistant** on Windows.

---

## 1. Running the Pre-Packaged Executable (`TatkalAssistant.exe`)

Tatkal Assistant is packaged into a standalone Windows binary that runs without requiring Python to be installed.

### Prerequisites
- **Operating System**: Windows 10 or Windows 11 (64-bit).
- **Playwright Chromium**: The application automates an official Chromium browser. If running on a clean machine where Playwright browsers have never been installed, install Chromium once:
  ```powershell
  # If PowerShell/terminal is available
  playwright install chromium
  ```
  *(Or copy the standard `%LOCALAPPDATA%\ms-playwright` folder from an existing setup).*

### Quick Start
1. Locate `dist\TatkalAssistant.exe`.
2. Double-click `TatkalAssistant.exe` to launch.
3. On first launch, the application automatically initializes:
   - `data\tatkal_assistant.db` (Local SQLite database with tables for trips, passengers, settings, bookings)
   - `data\app.log` (Local sanitizing audit log)
   - `data\browser_profile\` (Standard Chromium user data directory for session persistence)

---

## 2. Running from Source Code

If you prefer to run or develop from the Python source code:

### Step 1: Install Python
Ensure Python 3.12+ (64-bit) is installed and added to your `PATH`.

### Step 2: Clone or Extract the Project
Open a terminal in the project directory:
```powershell
cd C:\DRIVE-D\Project\tatkal-automation
```

### Step 3: Create & Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 4: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 5: Install Playwright Chromium Browser
```powershell
playwright install chromium
```

### Step 6: Launch the Application
```powershell
python app.py
```

---

## 3. Building the Windows Executable (`TatkalAssistant.exe`)

To rebuild the standalone executable from source using PyInstaller:

### Step 1: Install PyInstaller
```powershell
pip install pyinstaller>=6.0.0
```

### Step 2: Run PyInstaller with Spec File
```powershell
pyinstaller TatkalAssistant.spec --noconfirm --clean
```

The resulting standalone executable will be located in:
```text
dist\TatkalAssistant.exe
```

---

## 4. Verification & Testing

To execute the automated test suite across all 26 test suites (256+ tests):
```powershell
pytest -v
```

To run a headless smoke test on the entry point:
```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -c "import app; print('App OK')"
```

---

## 5. Security & Credential Isolation

- **Zero Bundled Secrets**: The compiled `TatkalAssistant.exe` contains zero API keys, secrets, or default IRCTC credentials.
- **Local Persistence Only**: All passenger profiles, trips, settings, and logs reside strictly in the local `data\` directory on your PC.
- **No Cloud Services**: The application does not communicate with any external backend, cloud database, or telemetry endpoint.
