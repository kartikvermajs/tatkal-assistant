"""Local Mock IRCTC HTTP Server for offline testing and verification.

Models the complete IRCTC Tatkal booking workflow:
LOGIN -> JOURNEY -> TRAIN -> PASSENGER -> CAPTCHA -> PAYMENT -> SUCCESS

Allows end-to-end verification of the BookingStateMachine and IRCTCWorkflow
without interacting with live IRCTC infrastructure.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse


class MockIRCTCRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler providing mock IRCTC pages and checkpoints."""

    @property
    def mock(self) -> "MockIRCTCServer":
        return getattr(self.server, "mock", None)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard HTTP server request logging in console."""
        pass

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 1. Network drop test
        if path == "/network-drop":
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
            except Exception:
                pass
            return

        # 2. Portal / Train Search (matches config.IRCTC_BOOKING_URL /train-search)
        if path in ("/", "/nget", "/nget/", "/nget/train-search", "/train-search"):
            self._handle_journey_search(query)
            return

        # 3. User Login Page (matches config.IRCTC_LOGIN_URL /user-login)
        if path in ("/nget/profile/user-login", "/login"):
            self._handle_login_page(query)
            return

        # 4. Logout Action
        if path == "/logout":
            if self.mock is not None:
                self.mock.logged_in = False
            self._send_redirect("/nget/train-search")
            return

        # 5. Passenger Form
        if path in ("/passenger", "/nget/booking"):
            self._handle_passenger_page()
            return

        # 6. Booking Review
        if path == "/review":
            self._handle_review_page()
            return

        # 7. CAPTCHA Checkpoint
        if path == "/captcha":
            self._handle_captcha_page()
            return

        # 8. OTP Checkpoint
        if path == "/otp":
            self._handle_otp_page()
            return

        # 9. Payment Stage
        if path == "/payment":
            self._handle_payment_page()
            return

        # 10. Confirmation / Success
        if path == "/success":
            self._handle_success_page()
            return

        # 11. Payment Failure
        if path == "/payment-failure":
            self._handle_payment_failure_page()
            return

        # 12. Payment Unknown / Ambiguous
        if path == "/payment-unknown":
            self._handle_payment_unknown_page()
            return

        # 13. Quota Regret / Unavailable
        if path == "/quota-regret":
            self._handle_quota_regret_page()
            return

        # Default 404
        self._send_html("<html><body><h1>404 Not Found</h1></body></html>", status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/login", "/nget/profile/user-login"):
            if self.mock is not None:
                self.mock.logged_in = True
            self._send_redirect("/nget/train-search")
            return

        if path in ("/passenger-submit", "/passenger"):
            if self.mock and self.mock.captcha_required:
                self._send_redirect("/captcha")
            elif self.mock and self.mock.otp_required:
                self._send_redirect("/otp")
            else:
                self._send_redirect("/payment")
            return

        if path == "/captcha-submit":
            if self.mock and self.mock.otp_required:
                self._send_redirect("/otp")
            else:
                self._send_redirect("/payment")
            return

        if path == "/otp-submit":
            self._send_redirect("/payment")
            return

        if path == "/payment-submit":
            outcome = (self.mock.payment_outcome if self.mock else "SUCCESS").upper()
            if outcome == "SUCCESS":
                self._send_redirect("/success")
            elif outcome == "FAILURE":
                self._send_redirect("/payment-failure")
            else:
                self._send_redirect("/payment-unknown")
            return

        self._send_redirect("/nget/train-search")

    # ==================== Page Renderers ====================

    def _handle_journey_search(self, query: Dict[str, List[str]]) -> None:
        mock = self.mock
        is_logged_in = (mock.logged_in if mock else True) or ("logged_in" in query and query["logged_in"][0] == "1")
        has_regret = (mock.regret_mode if mock else False) or ("regret" in query and query["regret"][0] == "1")

        auth_header = (
            """<div class="user-bar">
                <span>Welcome, <strong>Authorized User</strong></span>
                <a href="/logout" data-testid="logout-btn" class="btn-link">Logout</a>
            </div>"""
            if is_logged_in
            else """<div class="user-bar">
                <a href="/nget/profile/user-login" data-testid="login-link" class="btn-link">Login</a>
            </div>"""
        )

        trains_html = ""
        if has_regret:
            trains_html = """
            <div class="train-item" data-train="12004">
                <h3>12004 - LUCKNOW SHATABDI</h3>
                <div class="avl-regret" data-testid="quota-unavailable">
                    <strong>WL REGRET</strong> - No Seats Available for Tatkal Quota
                </div>
            </div>
            """
        elif mock and mock.custom_trains is not None:
            for t in mock.custom_trains:
                tnum = t.get("number", "00000")
                tname = t.get("name", "SPECIAL")
                classes = t.get("classes", ["3A", "SL"])
                buttons = "".join(f'<button type="button" class="class-item" data-class="{c}">{c}</button> ' for c in classes)
                trains_html += f"""
                <div class="train-item" data-train="{tnum}">
                    <h3>{tnum} - {tname}</h3>
                    <div class="classes">{buttons}</div>
                    <a href="/passenger" class="btn-book" data-testid="book-train-{tnum}">Book Now</a>
                </div>
                """
        else:
            trains_html = """
            <div class="train-item" data-train="12004">
                <h3>12004 - LUCKNOW SHATABDI</h3>
                <div class="classes">
                    <button type="button" class="class-item" data-class="3A">3A (AC 3 Tier)</button>
                    <button type="button" class="class-item" data-class="2A">2A (AC 2 Tier)</button>
                    <button type="button" class="class-item" data-class="1A">1A (AC First Class)</button>
                    <button type="button" class="class-item" data-class="SL">SL (Sleeper)</button>
                    <button type="button" class="class-item" data-class="CC">CC (Chair Car)</button>
                    <button type="button" class="class-item" data-class="EC">EC (Executive Chair Car)</button>
                    <button type="button" class="class-item" data-class="2S">2S (Second Sitting)</button>
                </div>
                <div style="margin-top: 10px;">
                    <a href="/passenger" class="btn-book" data-testid="book-train-12004">Book Now</a>
                </div>
            </div>

            <div class="train-item" data-train="12952">
                <h3>12952 - MUMBAI RAJDHANI</h3>
                <div class="classes">
                    <button type="button" class="class-item" data-class="3A">3A (AC 3 Tier)</button>
                    <button type="button" class="class-item" data-class="2A">2A (AC 2 Tier)</button>
                    <button type="button" class="class-item" data-class="1A">1A (AC First Class)</button>
                </div>
                <div style="margin-top: 10px;">
                    <a href="/passenger" class="btn-book" data-testid="book-train-12952">Book Now</a>
                </div>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock Portal - Train Search</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f4f6f9; color: #222; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #fb792b; padding-bottom: 10px; margin-bottom: 20px; }}
        .logo {{ font-size: 24px; font-weight: bold; color: #213d77; }}
        .user-bar {{ font-size: 14px; }}
        .card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 15px; }}
        input, select {{ width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }}
        .train-item {{ background: #fff; border: 1px solid #e0e0e0; border-left: 4px solid #213d77; padding: 15px; margin-bottom: 15px; border-radius: 4px; }}
        .classes button {{ background: #eef2f8; border: 1px solid #b8c8dc; padding: 6px 12px; margin-right: 6px; margin-top: 6px; border-radius: 4px; cursor: pointer; }}
        .classes button:hover {{ background: #213d77; color: white; }}
        .btn-book {{ display: inline-block; background: #fb792b; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-weight: bold; }}
        .btn-link {{ color: #213d77; text-decoration: none; margin-left: 10px; font-weight: bold; }}
        .avl-regret {{ background: #ffebee; color: #c62828; padding: 10px; border-radius: 4px; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">IRCTC Mock Portal</div>
        {auth_header}
    </div>

    <div class="card">
        <h2>Book Your Ticket</h2>
        <div class="grid">
            <div>
                <label>From</label>
                <input id="origin" name="origin" placeholder="From Station" data-testid="origin" value="NDLS" />
            </div>
            <div>
                <label>To</label>
                <input id="destination" name="destination" placeholder="To Station" data-testid="destination" value="CNB" />
            </div>
            <div>
                <label>Journey Date</label>
                <input id="journeyDate" name="journeyDate" placeholder="Date (DD-MM-YYYY)" data-testid="date" value="17-10-2026" />
            </div>
            <div>
                <label>Quota</label>
                <select id="journeyQuota" name="quota" data-testid="quota">
                    <option value="TATKAL" selected>Tatkal</option>
                    <option value="GENERAL">General</option>
                    <option value="PREMIUM TATKAL">Premium Tatkal</option>
                </select>
            </div>
        </div>
    </div>

    <h2>Available Trains</h2>
    <div class="train-list" data-testid="train-list">
        {trains_html}
    </div>
</body>
</html>"""
        self._send_html(html)

    def _handle_login_page(self, query: Dict[str, List[str]]) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock - User Login</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px auto; max-width: 400px; background: #f4f6f9; }
        .card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h2 { color: #213d77; margin-top: 0; }
        .field { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: 500; }
        input { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
        button { width: 100%; background: #fb792b; color: white; border: none; padding: 10px; font-weight: bold; border-radius: 4px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Sign In to IRCTC</h2>
        <form method="POST" action="/login">
            <div class="field">
                <label>Username</label>
                <input id="userId" name="userId" placeholder="User Name" data-testid="username" />
            </div>
            <div class="field">
                <label>Password</label>
                <input id="pwd" name="pwd" type="password" placeholder="Password" data-testid="password" />
            </div>
            <button type="submit" data-testid="login-submit">Sign In</button>
        </form>
    </div>
</body>
</html>"""
        self._send_html(html)

    def _handle_passenger_page(self) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock - Passenger Details</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f4f6f9; }
        .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }
        .passenger-row { display: grid; grid-template-columns: 2fr 1fr 1fr 1.5fr; gap: 10px; margin-bottom: 10px; }
        input, select { padding: 8px; border: 1px solid #ccc; border-radius: 4px; width: 100%; box-sizing: border-box; }
        .btn-continue { background: #fb792b; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 4px; cursor: pointer; font-size: 16px; }
        .btn-add { background: #eef2f8; border: 1px solid #b8c8dc; padding: 6px 12px; border-radius: 4px; cursor: pointer; margin-bottom: 15px; }
        .section-title { color: #213d77; border-bottom: 1px solid #eee; padding-bottom: 6px; }
    </style>
</head>
<body>
    <div class="card">
        <h2 class="section-title">Passenger Details (Max 4 for Tatkal)</h2>
        <form method="POST" action="/passenger-submit">
            <div id="passengers-container">
                <div class="passenger-row" id="row-0">
                    <input data-testid="passenger-name-0" name="pname_0" placeholder="Passenger Name" />
                    <input data-testid="passenger-age-0" name="page_0" placeholder="Age" />
                    <select data-testid="passenger-gender-0" name="pgender_0">
                        <option value="M">Male</option>
                        <option value="F">Female</option>
                        <option value="T">Transgender</option>
                    </select>
                    <select data-testid="passenger-berth-0" name="pberth_0">
                        <option value="NONE">No Preference</option>
                        <option value="LB">Lower</option>
                        <option value="MB">Middle</option>
                        <option value="UB">Upper</option>
                        <option value="SL">Side Lower</option>
                        <option value="SU">Side Upper</option>
                    </select>
                </div>

                <div class="passenger-row" id="row-1">
                    <input data-testid="passenger-name-1" name="pname_1" placeholder="Passenger Name" />
                    <input data-testid="passenger-age-1" name="page_1" placeholder="Age" />
                    <select data-testid="passenger-gender-1" name="pgender_1">
                        <option value="M">Male</option>
                        <option value="F">Female</option>
                        <option value="T">Transgender</option>
                    </select>
                    <select data-testid="passenger-berth-1" name="pberth_1">
                        <option value="NONE">No Preference</option>
                        <option value="LB">Lower</option>
                        <option value="MB">Middle</option>
                        <option value="UB">Upper</option>
                        <option value="SL">Side Lower</option>
                        <option value="SU">Side Upper</option>
                    </select>
                </div>

                <div class="passenger-row" id="row-2">
                    <input data-testid="passenger-name-2" name="pname_2" placeholder="Passenger Name" />
                    <input data-testid="passenger-age-2" name="page_2" placeholder="Age" />
                    <select data-testid="passenger-gender-2" name="pgender_2">
                        <option value="M">Male</option>
                        <option value="F">Female</option>
                        <option value="T">Transgender</option>
                    </select>
                    <select data-testid="passenger-berth-2" name="pberth_2">
                        <option value="NONE">No Preference</option>
                        <option value="LB">Lower</option>
                        <option value="MB">Middle</option>
                        <option value="UB">Upper</option>
                        <option value="SL">Side Lower</option>
                        <option value="SU">Side Upper</option>
                    </select>
                </div>

                <div class="passenger-row" id="row-3">
                    <input data-testid="passenger-name-3" name="pname_3" placeholder="Passenger Name" />
                    <input data-testid="passenger-age-3" name="page_3" placeholder="Age" />
                    <select data-testid="passenger-gender-3" name="pgender_3">
                        <option value="M">Male</option>
                        <option value="F">Female</option>
                        <option value="T">Transgender</option>
                    </select>
                    <select data-testid="passenger-berth-3" name="pberth_3">
                        <option value="NONE">No Preference</option>
                        <option value="LB">Lower</option>
                        <option value="MB">Middle</option>
                        <option value="UB">Upper</option>
                        <option value="SL">Side Lower</option>
                        <option value="SU">Side Upper</option>
                    </select>
                </div>
            </div>

            <button type="button" class="btn-add" data-testid="add-passenger-btn">+ Add Passenger</button>

            <h3 class="section-title">Contact Information</h3>
            <div style="max-width: 300px; margin-bottom: 15px;">
                <label>Mobile Number</label>
                <input id="mobileNumber" data-testid="mobile-number" name="mobile" placeholder="Mobile Number" value="9876543210" />
            </div>

            <h3 class="section-title">Other Preferences</h3>
            <div style="margin-bottom: 15px;">
                <label><input type="checkbox" id="autoUpgradation" data-testid="auto-upgradation" /> Consider for Auto Upgradation</label><br/>
                <label><input type="checkbox" id="confirmBerths" data-testid="confirm-berths" /> Book only if confirm berths are allotted</label>
            </div>

            <h3 class="section-title">Payment Mode Preference</h3>
            <div style="margin-bottom: 20px;">
                <label><input type="radio" name="pay_pref" value="IRCTC_EWALLET" data-testid="pay-ewallet" checked /> IRCTC eWallet</label><br/>
                <label><input type="radio" name="pay_pref" value="2" data-testid="pay-upi" /> Pay through BHIM/UPI</label><br/>
                <label><input type="radio" name="pay_pref" value="1" data-testid="pay-cards" /> Pay through Credit & Debit Cards / Net Banking</label>
            </div>

            <button type="submit" data-testid="continue-btn" class="btn-continue">Continue</button>
        </form>
    </div>
</body>
</html>"""
        self._send_html(html)

    def _handle_review_page(self) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock - Booking Review</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f4f6f9; }
        .card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); max-width: 600px; }
        h2 { color: #213d77; }
        .btn-continue { background: #fb792b; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 4px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Review Booking</h2>
        <p><strong>Train:</strong> 12004 - LUCKNOW SHATABDI</p>
        <p><strong>Class:</strong> AC 3 Tier (3A)</p>
        <p><strong>Quota:</strong> Tatkal</p>
        <p><strong>Journey:</strong> NDLS &rarr; CNB</p>
        <p><strong>Passengers:</strong> 1 Adult</p>
        <form method="POST" action="/passenger-submit">
            <button type="submit" data-testid="continue-btn" class="btn-continue">Continue to Checkpoint</button>
        </form>
    </div>
</body>
</html>"""
        self._send_html(html)

    def _handle_captcha_page(self) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock - CAPTCHA Verification</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 30px auto; max-width: 450px; background: #f4f6f9; }
        .card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h2 { color: #213d77; margin-top: 0; }
        .captcha-box { display: flex; align-items: center; gap: 15px; margin: 15px 0; }
        input { padding: 8px; border: 1px solid #ccc; border-radius: 4px; width: 100%; box-sizing: border-box; }
        button { width: 100%; background: #fb792b; color: white; border: none; padding: 10px; font-weight: bold; border-radius: 4px; cursor: pointer; }
        .notice { font-size: 13px; color: #555; background: #fff3e0; padding: 8px; border-radius: 4px; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Security Verification</h2>
        <div class="notice">Human verification required. Automation will pause.</div>
        <form method="POST" action="/captcha-submit">
            <div class="captcha-box">
                <img class="captcha-img" id="captcha-img" data-testid="captcha-img"
                     src="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='130' height='40'><rect width='100%' height='100%' fill='%23e0e0e0'/><text x='15' y='28' font-size='22' font-family='monospace' font-weight='bold' fill='%23213d77'>8N7KP</text></svg>"
                     alt="CAPTCHA Image" />
            </div>
            <div style="margin-bottom: 15px;">
                <label>Enter Captcha</label>
                <input id="nlpAnswer" data-testid="captcha-input" placeholder="Enter Captcha text" />
            </div>
            <button type="submit" data-testid="captcha-submit-btn">Verify and Proceed</button>
        </form>
    </div>
</body>
</html>"""
        self._send_html(html)

    def _handle_otp_page(self) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock - OTP Authentication</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 30px auto; max-width: 450px; background: #f4f6f9; }
        .card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h2 { color: #213d77; margin-top: 0; }
        input { padding: 8px; border: 1px solid #ccc; border-radius: 4px; width: 100%; box-sizing: border-box; }
        button { width: 100%; background: #fb792b; color: white; border: none; padding: 10px; font-weight: bold; border-radius: 4px; cursor: pointer; }
        .notice { font-size: 13px; color: #555; background: #e3f2fd; padding: 8px; border-radius: 4px; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Enter OTP</h2>
        <div class="notice">One Time Password sent to your mobile. Enter OTP directly in browser.</div>
        <form method="POST" action="/otp-submit">
            <div style="margin-bottom: 15px;">
                <label>Enter Aadhaar / Transaction OTP</label>
                <input id="otp" data-testid="otp-input" placeholder="Enter OTP" />
            </div>
            <button type="submit" data-testid="otp-submit-btn">Submit OTP</button>
        </form>
    </div>
</body>
</html>"""
        self._send_html(html)

    def _handle_payment_page(self) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock - Payment Gateway</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px auto; max-width: 600px; background: #f4f6f9; }
        .card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h2 { color: #213d77; margin-top: 0; }
        .auth-box { background: #fff8e1; border: 1px solid #ffe082; padding: 15px; border-radius: 6px; margin: 15px 0; }
        .btn-pay { width: 100%; background: #2e7d32; color: white; border: none; padding: 12px; font-size: 16px; font-weight: bold; border-radius: 4px; cursor: pointer; }
        .btn-pay:hover { background: #1b5e20; }
        .sim-links { margin-top: 15px; font-size: 13px; text-align: center; }
        .sim-links a { color: #c62828; text-decoration: none; margin: 0 8px; }
    </style>
</head>
<body>
    <div class="card" id="payment-gateways" data-testid="payment-options">
        <h2>Payment Stage</h2>
        <div>
            <label><input type="radio" name="pay_cat" value="IRCTC_EWALLET" data-testid="pay-ewallet" checked /> IRCTC eWallet</label><br/>
            <label><input type="radio" name="pay_cat" value="2" data-testid="pay-upi" /> BHIM/UPI</label><br/>
            <label><input type="radio" name="pay_cat" value="1" data-testid="pay-cards" /> Credit / Debit Card</label>
        </div>

        <div class="auth-box">
            <h3 style="margin-top:0; color:#b78103;">Payment Authorization Required</h3>
            <p>Enter your eWallet PIN / Banking OTP to authorize the transaction directly.</p>
            <input type="password" id="pin" placeholder="Enter PIN / CVV" style="width:100%; padding:8px; border:1px solid #ccc; border-radius:4px; box-sizing:border-box;" />
        </div>

        <form method="POST" action="/payment-submit">
            <button type="submit" id="pay-btn" class="btn-pay" data-testid="pay-submit-btn">Authorize & Pay ₹ 1245.00</button>
        </form>

        <div class="sim-links">
            Simulate Outcomes:
            <a href="/payment-failure" id="link-fail" data-testid="simulate-failure">Simulate Failure</a> |
            <a href="/payment-unknown" id="link-unknown" data-testid="simulate-unknown">Simulate Uncertain</a>
        </div>
    </div>
</body>
</html>"""
        self._send_html(html)

    def _handle_success_page(self) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock - Booking Confirmation</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 30px auto; max-width: 600px; background: #f4f6f9; }
        .card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-top: 5px solid #2e7d32; }
        h1 { color: #2e7d32; margin-top: 0; font-size: 22px; }
        .pnr-box { background: #e8f5e9; border: 1px dashed #2e7d32; padding: 15px; border-radius: 6px; margin: 15px 0; }
        .pnr-bold { font-size: 24px; font-weight: bold; color: #1b5e20; letter-spacing: 2px; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { border: 1px solid #e0e0e0; padding: 8px; text-align: left; font-size: 14px; }
        th { background: #f5f5f5; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Booking Successful</h1>
        <p>Congratulations! Your Tatkal ticket has been successfully booked.</p>

        <div class="pnr-box">
            <div>PNR Number</div>
            <div class="pnr-bold" data-testid="pnr-number">2345678901</div>
        </div>

        <p>Transaction ID: <strong data-testid="txn-id">TXN100987654</strong></p>
        <p>Total Fare: <strong data-testid="total-fare">₹ 1245.00</strong></p>
        <p>Train: <strong>12004 - LUCKNOW SHATABDI</strong> | Class: <strong>3A</strong></p>

        <h3>Passenger Allocation Details</h3>
        <table data-testid="allocated-passengers" class="passenger-table">
            <thead>
                <tr>
                    <th>Passenger Name</th>
                    <th>Booking Status</th>
                    <th>Coach / Berth</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Ravi Kumar</td>
                    <td>Confirmed (CNF)</td>
                    <td>B1, 23 (Lower)</td>
                </tr>
            </tbody>
        </table>
    </div>
</body>
</html>"""
        self._send_html(html)

    def _handle_payment_failure_page(self) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock - Transaction Failed</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 30px auto; max-width: 550px; background: #f4f6f9; }
        .card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-top: 5px solid #c62828; }
        h1 { color: #c62828; margin-top: 0; }
        .alert-danger { background: #ffebee; color: #b71c1c; padding: 12px; border-radius: 4px; font-weight: 500; margin: 15px 0; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Payment Failed</h1>
        <div class="alert-danger" data-testid="payment-failure">
            Payment Failed: Transaction declined by bank / Insufficient funds
        </div>
        <p>Your bank transaction was declined. Your account was not debited.</p>
        <p>Please return to journey selection or try an alternate payment method.</p>
    </div>
</body>
</html>"""
        self._send_html(html)

    def _handle_payment_unknown_page(self) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock - Status Pending</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 30px auto; max-width: 550px; background: #f4f6f9; }
        .card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-top: 5px solid #f57f17; }
        h1 { color: #f57f17; margin-top: 0; }
        .alert-warning { background: #fffde7; color: #f57f17; padding: 12px; border-radius: 4px; font-weight: 500; margin: 15px 0; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Transaction Processing Pending</h1>
        <div class="alert-warning" data-testid="payment-uncertain">
            Status Uncertain: Transaction is awaiting bank gateway settlement.
        </div>
        <p>Do not rebook immediately. Verify booking history in your IRCTC profile before attempting another transaction.</p>
    </div>
</body>
</html>"""
        self._send_html(html)

    def _handle_quota_regret_page(self) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IRCTC Mock - Train Search (Regret)</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f4f6f9; }
        .train-item { background: white; border-left: 4px solid #c62828; padding: 15px; border-radius: 4px; }
        .avl-regret { color: #c62828; font-weight: bold; margin-top: 10px; }
    </style>
</head>
<body>
    <h2>Train Search Results</h2>
    <div class="train-item" data-train="12004">
        <h3>12004 - LUCKNOW SHATABDI</h3>
        <div class="avl-regret" data-testid="quota-unavailable">
            WL REGRET / No Seats Available
        </div>
    </div>
</body>
</html>"""
        self._send_html(html)


class MockIRCTCServer:
    """Threaded HTTP server providing mock IRCTC pages and checkpoints."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self._requested_port = port
        self.port = port
        self.logged_in = True
        self.captcha_required = True
        self.otp_required = False
        self.payment_outcome = "SUCCESS"  # "SUCCESS", "FAILURE", or "UNKNOWN"
        self.regret_mode = False
        self.custom_trains: Optional[List[Dict[str, Any]]] = None

        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def booking_url(self) -> str:
        return f"{self.base_url}/nget/train-search"

    @property
    def login_url(self) -> str:
        return f"{self.base_url}/nget/profile/user-login"

    @property
    def passenger_url(self) -> str:
        return f"{self.base_url}/passenger"

    @property
    def captcha_url(self) -> str:
        return f"{self.base_url}/captcha"

    @property
    def otp_url(self) -> str:
        return f"{self.base_url}/otp"

    @property
    def payment_url(self) -> str:
        return f"{self.base_url}/payment"

    @property
    def success_url(self) -> str:
        return f"{self.base_url}/success"

    @property
    def payment_failure_url(self) -> str:
        return f"{self.base_url}/payment-failure"

    @property
    def payment_unknown_url(self) -> str:
        return f"{self.base_url}/payment-unknown"

    @property
    def quota_regret_url(self) -> str:
        return f"{self.base_url}/quota-regret"

    @property
    def network_drop_url(self) -> str:
        return f"{self.base_url}/network-drop"

    def start(self) -> None:
        """Start the mock server on a background daemon thread."""
        if self._server is not None:
            return

        handler_cls = MockIRCTCRequestHandler
        self._server = ThreadingHTTPServer((self.host, self._requested_port), handler_cls)
        # Link server reference to handler instance
        self._server.mock = self  # type: ignore[attr-defined]
        self.port = self._server.server_address[1]

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Shut down the HTTP server and release port."""
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            finally:
                self._server = None
                self._thread = None

    def __enter__(self) -> "MockIRCTCServer":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()


def main() -> None:
    """CLI entrypoint to run the mock IRCTC server standalone for manual testing."""
    import argparse
    import time

    parser = argparse.ArgumentParser(description="IRCTC Mock Booking Site")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    args = parser.parse_args()

    server = MockIRCTCServer(host=args.host, port=args.port)
    server.start()

    print("=" * 65)
    print("IRCTC Mock Booking Site Running!")
    print(f"Base URL:      {server.base_url}")
    print(f"Portal/Search: {server.booking_url}")
    print(f"User Login:    {server.login_url}")
    print(f"Passenger:     {server.passenger_url}")
    print(f"CAPTCHA:       {server.captcha_url}")
    print(f"OTP:           {server.otp_url}")
    print(f"Payment:       {server.payment_url}")
    print(f"Success:       {server.success_url}")
    print(f"Payment Fail:  {server.payment_failure_url}")
    print(f"Unknown State: {server.payment_unknown_url}")
    print(f"Quota Regret:  {server.quota_regret_url}")
    print("=" * 65)
    print("Press Ctrl+C to terminate the mock server.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping IRCTC Mock Server...")
        server.stop()
        print("Server stopped cleanly.")


if __name__ == "__main__":
    main()
