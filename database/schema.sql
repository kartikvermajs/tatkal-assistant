-- SQLite Schema for Tatkal Assistant
-- Local persistence only. No credentials, passwords, OTPs, PINs, or CVVs are ever stored.

CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_station TEXT NOT NULL,
    to_station TEXT NOT NULL,
    journey_date TEXT NOT NULL,
    train_number TEXT NOT NULL,
    train_name TEXT DEFAULT '',
    class_code TEXT NOT NULL DEFAULT 'SL',
    quota TEXT NOT NULL DEFAULT 'TATKAL',
    is_active INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS passengers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    gender TEXT NOT NULL,
    berth_preference TEXT NOT NULL DEFAULT 'NONE',
    is_selected INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER REFERENCES trips(id) ON DELETE SET NULL,
    pnr TEXT DEFAULT '',
    train_number TEXT NOT NULL,
    train_name TEXT DEFAULT '',
    class_code TEXT NOT NULL DEFAULT 'SL',
    quota_code TEXT NOT NULL DEFAULT 'TATKAL',
    from_station TEXT NOT NULL,
    to_station TEXT NOT NULL,
    journey_date TEXT NOT NULL,
    status TEXT NOT NULL,
    transaction_id TEXT DEFAULT '',
    total_fare REAL DEFAULT 0.0,
    passenger_details TEXT DEFAULT '',
    status_message TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

