# Security & Local Data Audit

Tatkal Assistant is designed from the ground up as a **strictly local-only**, **human-in-the-loop** Windows desktop application. It acts purely as a workflow accelerator for repetitive browser navigation and form population while leaving all security-sensitive actions—user authentication, CAPTCHA solving, OTP verification, and payment authorization—under direct human control.

---

## 1. Core Security & Compliance Guarantees

| Requirement | Policy | Implementation Verification |
|---|---|---|
| **Local Only** | Zero cloud backends, remote servers, or external AI/LLMs. | All logic executes locally on the user's workstation. Zero network calls outside local mock testing and official IRCTC endpoints. |
| **No Password Storage** | Passwords are never stored on disk, in SQLite, or in configs. | IRCTC login is performed manually by the user directly in the official browser window. |
| **No OTP Interception** | Zero SMS, email, or clipboard reading for OTPs. | Human enters OTPs directly into the official IRCTC portal. |
| **No Financial Credentials** | Zero storage or handling of banking PINs, card CVVs, or card numbers. | User selects payment method in app; enters all authorization credentials directly on official bank/IRCTC gateway. |
| **No CAPTCHA Bypass** | Zero automated solving, OCR, or third-party CAPTCHA APIs. | Browser halts at CAPTCHA checkpoints; user solves visual CAPTCHAs manually. |
| **No Anti-Bot Bypass** | Zero stealth plugins, fingerprint spoofing, or CDP evasions. | Uses standard Chromium via Playwright persistent context with zero stealth flags. |
| **No Proxy Rotation** | Zero proxy networks, IP pools, or proxy rotation logic. | All connections originate directly from the user's standard network interface. |
| **No Telemetry / Analytics** | Zero tracking SDKs, analytics, error reporters, or phone-home pings. | No Sentry, Google Analytics, Mixpanel, Datadog, or external telemetry of any kind. |
| **Emergency Halt** | Immediate abort of automation via UI or keyboard shortcut. | Dedicated `[ STOP AUTOMATION ]` button and global `ESC` key halt Playwright navigation instantly and revert state to `IDLE`. |

---

## 2. Local Data Persistence Audit

All application state is saved **strictly locally** within the application directory (`data/`). No data is ever transmitted to remote databases, cloud sync services, or external APIs.

### 2.1 SQLite Database (`data/tatkal_assistant.db`)

The SQLite database contains exactly four application tables, none of which store sensitive credentials:

#### Table: `trips`
Stores travel journey preferences configured by the user for fast pre-booking setup:
- `id` (INTEGER PRIMARY KEY)
- `from_station` (TEXT NOT NULL): Origin station code (e.g., `NDLS`).
- `to_station` (TEXT NOT NULL): Destination station code (e.g., `CNB`).
- `journey_date` (TEXT NOT NULL): Journey date formatted as `YYYY-MM-DD`.
- `train_number` (TEXT NOT NULL): Explicit mandatory train number (e.g., `12004`).
- `train_name` (TEXT DEFAULT ''): Human-readable train display name.
- `class_code` (TEXT NOT NULL DEFAULT 'SL'): Explicit travel class (e.g., `3A`, `SL`).
- `quota` (TEXT NOT NULL DEFAULT 'TATKAL'): Booking quota (`TATKAL`, `PREMIUM TATKAL`, `GENERAL`).
- `is_active` (INTEGER DEFAULT 0): Active trip marker.
- `created_at` (TIMESTAMP): Record creation timestamp.
- `updated_at` (TIMESTAMP): Last modification timestamp.

#### Table: `passengers`
Stores the passenger master list to automatically fill the passenger form during Tatkal opening:
- `id` (INTEGER PRIMARY KEY)
- `name` (TEXT NOT NULL): Passenger full name.
- `age` (INTEGER NOT NULL): Passenger age.
- `gender` (TEXT NOT NULL): Passenger gender code (`M`, `F`, `T`).
- `berth_preference` (TEXT NOT NULL DEFAULT 'NONE'): Berth preference (`L`, `M`, `U`, `SL`, `SU`, `NONE`).
- `is_selected` (INTEGER DEFAULT 0): Selection state flag.
- `created_at` (TIMESTAMP): Creation timestamp.
- `updated_at` (TIMESTAMP): Last modification timestamp.

#### Table: `settings`
Stores desktop application preferences:
- `key` (TEXT PRIMARY KEY): Configuration key.
- `value` (TEXT NOT NULL): Configuration value.
- **Safety Enforcement**: [`ApplicationSettings`](file:///c:/DRIVE-D/Project/tatkal-automation/models/settings.py) strictly validates all keys against `PROHIBITED_CREDENTIAL_KEYS` (`password`, `otp`, `pin`, `cvv`, `cvc`, `card_number`, `token`, `secret`, `credential`). Attempting to persist any credential field raises a `ValueError`.

#### Table: `bookings`
Stores local booking history and reconciliation status:
- `id` (INTEGER PRIMARY KEY)
- `trip_id` (INTEGER REFERENCES trips(id)): Associated trip ID.
- `pnr` (TEXT DEFAULT ''): 10-digit Passenger Name Record (PNR) number upon confirmation.
- `train_number` (TEXT NOT NULL): Booked train number.
- `train_name` (TEXT DEFAULT ''): Booked train name.
- `class_code` (TEXT NOT NULL): Travel class code.
- `quota_code` (TEXT NOT NULL): Quota code.
- `from_station` (TEXT NOT NULL): Origin station.
- `to_station` (TEXT NOT NULL): Destination station.
- `journey_date` (TEXT NOT NULL): Journey date.
- `status` (TEXT NOT NULL): Booking status (`BOOKING_SUCCESS`, `FAILURE`, `UNKNOWN`).
- `transaction_id` (TEXT DEFAULT ''): IRCTC transaction ID.
- `total_fare` (REAL DEFAULT 0.0): Total fare amount in INR.
- `passenger_details` (TEXT DEFAULT ''): Serialized JSON list of booked passenger names and berths.
- `status_message` (TEXT DEFAULT ''): Terminal status description.
- `created_at` (TIMESTAMP): Booking record timestamp.

---

### 2.2 Local Application Logs (`data/app.log`)

Application events are recorded locally using timestamped lines:
```text
YYYY-MM-DD HH:MM:SS <Message>
```
- **Sanitization Engine**: Built into [`core/logger.py`](file:///c:/DRIVE-D/Project/tatkal-automation/core/logger.py), the `sanitize_log_message()` function intercepts all log messages before disk writing using regular expression masks:
  - Passwords: `password=[REDACTED]`
  - OTPs: `otp=[REDACTED]`
  - PINs: `pin=[REDACTED]`
  - CVVs: `cvv=[REDACTED]`
  - Tokens: `token=[REDACTED]`
  - Cookies: `cookie: [REDACTED]`
  - Authorization headers: `Bearer [REDACTED]`
- **Audit Verification**: Live scans of `data/app.log` verify zero sensitive credential leaks.

---

### 2.3 Browser User Data Directory (`data/browser_profile/`)

- A standard Chromium persistent profile folder managed directly by Playwright (`launch_persistent_context`).
- Stored exclusively on local disk.
- Used to keep legitimate browser session cookies and site preferences intact between runs without re-login where supported by IRCTC.
- **Zero Token Extraction**: The application never dumps, inspects, exports, or transmits session cookies or tokens from the browser context.

---

## 3. Network Architecture & External Endpoints

The application enforces strict URL centralization in [`config.py`](file:///c:/DRIVE-D/Project/tatkal-automation/config.py):
- `IRCTC_BASE_URL`: `https://www.irctc.co.in`
- `IRCTC_BOOKING_URL`: `https://www.irctc.co.in/nget/train-search`
- `IRCTC_LOGIN_URL`: `https://www.irctc.co.in/nget/train-search`

**Zero Hidden Connections**:
- Codebase-wide scans confirm zero hardcoded third-party domains.
- Local testing uses an isolated built-in mock server running strictly on `127.0.0.1` / `localhost`.
- No remote telemetry, background pings, analytics servers, or remote update checks.

---

## 4. Human Checkpoint Design Summary

1. **Authentication (Login)**: Performed by user in visible Chromium browser window.
2. **CAPTCHA Checkpoint**: Automation yields execution immediately when visual or text CAPTCHAs are detected. Resumes only when user confirms completion.
3. **OTP Checkpoint**: When Aadhaar or mobile OTP challenges appear, automation halts. The user types the OTP received on their phone directly into the browser.
4. **Payment Authorization**: The application selects payment category (e.g., IRCTC eWallet, UPI, NetBanking) but **never** automates transaction authorization. The user enters eWallet PIN, UPI PIN, or bank OTP directly into the payment gateway.
5. **Deadlock / Unknown Safeguard**: If payment status is uncertain or verification hangs, the state machine transitions to `UNKNOWN` and locks transitions (`sm.is_locked = True`) to prevent double charges or accidental retries.
