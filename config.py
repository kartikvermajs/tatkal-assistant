import os
import sys

APP_NAME = "Tatkal Assistant"
APP_VERSION = "0.1.0"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_LOG_FILE = os.path.join(DATA_DIR, "app.log")

DEFAULT_IRCTC_BASE_URL = "https://www.irctc.co.in/nget/"
DEFAULT_IRCTC_BOOKING_URL = "https://www.irctc.co.in/nget/train-search"
DEFAULT_IRCTC_LOGIN_URL = "https://www.irctc.co.in/nget/profile/user-login"

# Centralized IRCTC URLs
IRCTC_BASE_URL = DEFAULT_IRCTC_BASE_URL
IRCTC_BOOKING_URL = DEFAULT_IRCTC_BOOKING_URL
IRCTC_LOGIN_URL = DEFAULT_IRCTC_LOGIN_URL


def set_irctc_urls(base_url: str) -> None:
    """Redirect centralized IRCTC URLs to a base URL (e.g. for mock testing)."""
    global IRCTC_BASE_URL, IRCTC_BOOKING_URL, IRCTC_LOGIN_URL
    clean_base = base_url.rstrip("/")
    IRCTC_BASE_URL = f"{clean_base}/nget/"
    IRCTC_BOOKING_URL = f"{clean_base}/nget/train-search"
    IRCTC_LOGIN_URL = f"{clean_base}/nget/profile/user-login"


def reset_irctc_urls() -> None:
    """Reset centralized IRCTC URLs to default live endpoints."""
    global IRCTC_BASE_URL, IRCTC_BOOKING_URL, IRCTC_LOGIN_URL
    IRCTC_BASE_URL = DEFAULT_IRCTC_BASE_URL
    IRCTC_BOOKING_URL = DEFAULT_IRCTC_BOOKING_URL
    IRCTC_LOGIN_URL = DEFAULT_IRCTC_LOGIN_URL

# IRCTC Tatkal Windows
DEFAULT_TATKAL_AC_OPENING = "10:00:00"
DEFAULT_TATKAL_NON_AC_OPENING = "11:00:00"

# Mandatory Train Classes with Human-Readable Names and Codes
AVAILABLE_CLASSES = [
    ("SL", "Sleeper (SL)"),
    ("3A", "AC 3 Tier (3A)"),
    ("2A", "AC 2 Tier (2A)"),
    ("1A", "AC First Class (1A)"),
    ("3E", "AC 3 Economy (3E)"),
    ("CC", "Chair Car (CC)"),
    ("EC", "Executive Chair Car (EC)"),
    ("2S", "Second Sitting (2S)"),
]

AVAILABLE_QUOTAS = [
    ("TATKAL", "Tatkal"),
    ("PREMIUM TATKAL", "Premium Tatkal"),
    ("GENERAL", "General"),
]

# Payment Preference Configuration (Optimized for IRCTC eWallet per Phase 17)
PAYMENT_PREFERENCES = [
    ("IRCTC eWallet", "IRCTC eWallet"),
    ("UPI", "BHIM / UPI"),
    ("Credit Card", "Credit Card / Payment Gateway"),
]
DEFAULT_PAYMENT_MODE = "IRCTC eWallet"

CLASS_NAME_TO_CODE = {name: code for code, name in AVAILABLE_CLASSES}
CLASS_CODE_TO_NAME = {code: name for code, name in AVAILABLE_CLASSES}


def get_class_display_name(code: str) -> str:
    """Return human-readable class name for a given class code (e.g. '3A' -> 'AC 3 Tier (3A)')."""
    return CLASS_CODE_TO_NAME.get(code.strip().upper(), code)


def get_class_code(name_or_code: str) -> str:
    """Return IRCTC class code given a human-readable name or code."""
    cleaned = name_or_code.strip()
    if cleaned in CLASS_NAME_TO_CODE:
        return CLASS_NAME_TO_CODE[cleaned]
    upper = cleaned.upper()
    if upper in CLASS_CODE_TO_NAME:
        return upper
    raise ValueError(f"Unknown class '{name_or_code}'.")


# Popular Indian Railway Stations for auto-complete (code, name)
POPULAR_STATIONS = [
    ("NDLS", "New Delhi"),
    ("DEE", "Delhi Sarai Rohilla"),
    ("DLI", "Old Delhi"),
    ("ANND", "Anand Vihar Terminal"),
    ("CNB", "Kanpur Central"),
    ("LKO", "Lucknow"),
    ("LJN", "Lucknow Junction"),
    ("AGC", "Agra Cantt"),
    ("AF", "Agra Fort"),
    ("JP", "Jaipur"),
    ("AII", "Ajmer"),
    ("UDZ", "Udaipur"),
    ("JU", "Jodhpur"),
    ("KOTA", "Kota"),
    ("BCT", "Mumbai Central"),
    ("CSMT", "Mumbai CST"),
    ("LTT", "Lokmanya Tilak Terminus"),
    ("BVI", "Borivali"),
    ("PNVL", "Panvel"),
    ("PUNE", "Pune"),
    ("NGP", "Nagpur"),
    ("HWH", "Howrah"),
    ("KOAA", "Kolkata"),
    ("SDAH", "Sealdah"),
    ("MAS", "Chennai Central"),
    ("MS", "Chennai Egmore"),
    ("SBC", "Bengaluru City"),
    ("YPR", "Yesvantpur"),
    ("SC", "Secunderabad"),
    ("HYB", "Hyderabad"),
    ("TVC", "Trivandrum Central"),
    ("ERS", "Ernakulam"),
    ("CLT", "Kozhikode"),
    ("CBE", "Coimbatore"),
    ("MDU", "Madurai"),
    ("VSKP", "Visakhapatnam"),
    ("TPTY", "Tirupati"),
    ("BBS", "Bhubaneswar"),
    ("PURI", "Puri"),
    ("RNC", "Ranchi"),
    ("PNBE", "Patna"),
    ("DNR", "Danapur"),
    ("GKP", "Gorakhpur"),
    ("BSB", "Varanasi"),
    ("MUV", "Manduadih"),
    ("ALD", "Prayagraj"),
    ("BPL", "Bhopal"),
    ("JBP", "Jabalpur"),
    ("INDB", "Indore"),
    ("ADI", "Ahmedabad"),
    ("BRC", "Vadodara"),
    ("ST", "Surat"),
    ("RJT", "Rajkot"),
    ("GWL", "Gwalior"),
    ("DDN", "Dehradun"),
    ("HW", "Haridwar"),
    ("CDG", "Chandigarh"),
    ("ASR", "Amritsar"),
    ("LDH", "Ludhiana"),
    ("JAT", "Jammu Tawi"),
    ("UMB", "Ambala Cantt"),
    ("RE", "Bareilly"),
    ("MB", "Moradabad"),
    ("MFP", "Muzaffarpur"),
    ("DBG", "Darbhanga"),
    ("GHY", "Guwahati"),
    ("DGR", "Dibrugarh"),
    ("NJP", "New Jalpaiguri"),
    ("RJPB", "Rajendra Nagar"),
    ("MGS", "Mughal Sarai"),
    ("GCT", "Ghaziabad"),
    ("MTJ", "Mathura"),
    ("SRE", "Saharanpur"),
    ("RWL", "Ratlam"),
    ("AWR", "Ajmer"),
    ("ETW", "Etawah"),
    ("TDL", "Tundla"),
    ("GZB", "Ghaziabad"),
    ("CNB", "Kanpur Central"),
]

# Station lookup helpers for QCompleter
STATION_DISPLAY_LIST = [f"{code} - {name}" for code, name in POPULAR_STATIONS]
STATION_CODE_MAP = {f"{code} - {name}": code for code, name in POPULAR_STATIONS}

