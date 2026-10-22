"""Local SQLite database manager for Tatkal Assistant."""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Generator, List, Optional

import config
from models.booking import BookingRecord
from models.passenger import Passenger
from models.settings import ApplicationSettings
from models.trip import Trip

DEFAULT_DB_PATH = os.path.join(config.DATA_DIR, "tatkal_assistant.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

FALLBACK_SCHEMA_SQL = """
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
"""


class Database:
    """Manages local SQLite database operations with parameterized queries."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self._is_memory = (self.db_path == ":memory:")
        self._mem_conn: Optional[sqlite3.Connection] = None

        if self._is_memory:
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
        else:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)

        self._init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a transactional connection context."""
        if self._is_memory and self._mem_conn is not None:
            try:
                yield self._mem_conn
                self._mem_conn.commit()
            except Exception:
                self._mem_conn.rollback()
                raise
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_db(self) -> None:
        """Initialize database tables using schema.sql or embedded fallback."""
        if os.path.exists(SCHEMA_PATH):
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                schema_sql = f.read()
        else:
            schema_sql = FALLBACK_SCHEMA_SQL
        with self.get_connection() as conn:
            conn.executescript(schema_sql)

    def close(self) -> None:
        """Close database connection if persistent."""
        if self._mem_conn is not None:
            self._mem_conn.close()
            self._mem_conn = None

    # ---------------- Trip Operations ----------------

    def create_trip(self, trip: Trip) -> Trip:
        """Insert a new trip using parameterized SQL."""
        query = """
            INSERT INTO trips (from_station, to_station, journey_date, train_number, train_name, class_code, quota)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            trip.from_station,
            trip.to_station,
            trip.journey_date_str,
            trip.train_number,
            trip.train_name,
            trip.class_code,
            trip.quota,
        )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            trip.id = cursor.lastrowid
        return trip

    def update_trip(self, trip: Trip) -> bool:
        """Update an existing trip using parameterized SQL."""
        if trip.id is None:
            raise ValueError("Trip id cannot be None when updating.")
        query = """
            UPDATE trips
            SET from_station = ?, to_station = ?, journey_date = ?, train_number = ?,
                train_name = ?, class_code = ?, quota = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        params = (
            trip.from_station,
            trip.to_station,
            trip.journey_date_str,
            trip.train_number,
            trip.train_name,
            trip.class_code,
            trip.quota,
            trip.id,
        )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.rowcount > 0

    def delete_trip(self, trip_id: int) -> bool:
        """Delete a trip by id using parameterized SQL."""
        query = "DELETE FROM trips WHERE id = ?"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (trip_id,))
            return cursor.rowcount > 0

    def load_trip(self, trip_id: int) -> Optional[Trip]:
        """Load a single trip by id using parameterized SQL."""
        query = """
            SELECT id, from_station, to_station, journey_date, train_number, train_name, class_code, quota
            FROM trips
            WHERE id = ?
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (trip_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return Trip(
                id=row["id"],
                from_station=row["from_station"],
                to_station=row["to_station"],
                journey_date=row["journey_date"],
                train_number=row["train_number"],
                train_name=row["train_name"],
                class_code=row["class_code"],
                quota=row["quota"],
            )

    def list_trips(self) -> List[Trip]:
        """List all saved trips ordered by id descending."""
        query = """
            SELECT id, from_station, to_station, journey_date, train_number, train_name, class_code, quota
            FROM trips
            ORDER BY id DESC
        """
        trips: List[Trip] = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            for row in cursor.fetchall():
                trips.append(
                    Trip(
                        id=row["id"],
                        from_station=row["from_station"],
                        to_station=row["to_station"],
                        journey_date=row["journey_date"],
                        train_number=row["train_number"],
                        train_name=row["train_name"],
                        class_code=row["class_code"],
                        quota=row["quota"],
                    )
                )
        return trips

    def get_active_trip(self) -> Optional[Trip]:
        """Load the currently active trip profile, if any."""
        query = """
            SELECT id, from_station, to_station, journey_date, train_number, train_name, class_code, quota
            FROM trips
            WHERE is_active = 1
            LIMIT 1
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            if row is None:
                return None
            return Trip(
                id=row["id"],
                from_station=row["from_station"],
                to_station=row["to_station"],
                journey_date=row["journey_date"],
                train_number=row["train_number"],
                train_name=row["train_name"],
                class_code=row["class_code"],
                quota=row["quota"],
            )

    def set_active_trip(self, trip_id: Optional[int]) -> None:
        """Mark a trip profile as active, clearing active status from all others."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE trips SET is_active = 0")
            if trip_id is not None:
                cursor.execute("UPDATE trips SET is_active = 1 WHERE id = ?", (trip_id,))

    # ---------------- Passenger Operations ----------------

    def create_passenger(self, passenger: Passenger) -> Passenger:
        """Insert a new passenger using parameterized SQL."""
        query = """
            INSERT INTO passengers (name, age, gender, berth_preference)
            VALUES (?, ?, ?, ?)
        """
        params = (
            passenger.name,
            passenger.age,
            passenger.gender,
            passenger.berth_preference,
        )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            passenger.id = cursor.lastrowid
        return passenger

    def update_passenger(self, passenger: Passenger) -> bool:
        """Update an existing passenger using parameterized SQL."""
        if passenger.id is None:
            raise ValueError("Passenger id cannot be None when updating.")
        query = """
            UPDATE passengers
            SET name = ?, age = ?, gender = ?, berth_preference = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        params = (
            passenger.name,
            passenger.age,
            passenger.gender,
            passenger.berth_preference,
            passenger.id,
        )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.rowcount > 0

    def delete_passenger(self, passenger_id: int) -> bool:
        """Delete a passenger by id using parameterized SQL."""
        query = "DELETE FROM passengers WHERE id = ?"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (passenger_id,))
            return cursor.rowcount > 0

    def load_passenger(self, passenger_id: int) -> Optional[Passenger]:
        """Load a single passenger by id using parameterized SQL."""
        query = "SELECT id, name, age, gender, berth_preference FROM passengers WHERE id = ?"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (passenger_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return Passenger(
                id=row["id"],
                name=row["name"],
                age=row["age"],
                gender=row["gender"],
                berth_preference=row["berth_preference"],
            )

    def list_passengers(self) -> List[Passenger]:
        """List all saved passengers ordered by id ascending."""
        query = "SELECT id, name, age, gender, berth_preference FROM passengers ORDER BY id ASC"
        passengers: List[Passenger] = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            for row in cursor.fetchall():
                passengers.append(
                    Passenger(
                        id=row["id"],
                        name=row["name"],
                        age=row["age"],
                        gender=row["gender"],
                        berth_preference=row["berth_preference"],
                    )
                )
        return passengers

    def get_selected_passengers(self) -> List[Passenger]:
        """List passengers currently marked as selected for booking."""
        query = "SELECT id, name, age, gender, berth_preference FROM passengers WHERE is_selected = 1 ORDER BY id ASC"
        passengers: List[Passenger] = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            for row in cursor.fetchall():
                passengers.append(
                    Passenger(
                        id=row["id"],
                        name=row["name"],
                        age=row["age"],
                        gender=row["gender"],
                        berth_preference=row["berth_preference"],
                    )
                )
        return passengers

    def set_selected_passengers(self, selected_ids: List[int]) -> None:
        """Update selected state for passengers using parameterized SQL."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE passengers SET is_selected = 0")
            if selected_ids:
                placeholders = ", ".join("?" for _ in selected_ids)
                cursor.execute(
                    f"UPDATE passengers SET is_selected = 1 WHERE id IN ({placeholders})",
                    tuple(selected_ids),
                )

    # ---------------- Settings Operations ----------------

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a setting value by key."""
        query = "SELECT value FROM settings WHERE key = ?"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (key,))
            row = cursor.fetchone()
            if row is None:
                return default
            return str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        """Store or update a setting value using parameterized SQL."""
        query = "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (key, str(value)))

    def load_settings(self) -> ApplicationSettings:
        """Load all application settings into ApplicationSettings instance."""
        query = "SELECT key, value FROM settings"
        data = {}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            for row in cursor.fetchall():
                k, v = row["key"], row["value"]
                if v.lower() in ("true", "false"):
                    data[k] = v.lower() == "true"
                else:
                    data[k] = v
        return ApplicationSettings.from_dict(data)

    def save_settings(self, settings: ApplicationSettings) -> None:
        """Save ApplicationSettings to database."""
        for k, v in settings.to_dict().items():
            self.set_setting(k, str(v))

    # ---------------- Booking Operations ----------------

    def create_booking(self, booking: BookingRecord) -> BookingRecord:
        """Insert a new booking record using parameterized SQL."""
        query = """
            INSERT INTO bookings (
                trip_id, pnr, train_number, train_name, class_code, quota_code,
                from_station, to_station, journey_date, status, transaction_id,
                total_fare, passenger_details, status_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            booking.trip_id,
            booking.pnr,
            booking.train_number,
            booking.train_name,
            booking.class_code,
            booking.quota_code,
            booking.from_station,
            booking.to_station,
            booking.journey_date_str,
            booking.status,
            booking.transaction_id,
            booking.total_fare,
            booking.passenger_details,
            booking.status_message,
        )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            booking.id = cursor.lastrowid
        return booking

    def update_booking(self, booking: BookingRecord) -> bool:
        """Update an existing booking record using parameterized SQL."""
        if booking.id is None:
            raise ValueError("Booking id cannot be None when updating.")
        query = """
            UPDATE bookings
            SET trip_id = ?, pnr = ?, train_number = ?, train_name = ?, class_code = ?,
                quota_code = ?, from_station = ?, to_station = ?, journey_date = ?,
                status = ?, transaction_id = ?, total_fare = ?, passenger_details = ?,
                status_message = ?
            WHERE id = ?
        """
        params = (
            booking.trip_id,
            booking.pnr,
            booking.train_number,
            booking.train_name,
            booking.class_code,
            booking.quota_code,
            booking.from_station,
            booking.to_station,
            booking.journey_date_str,
            booking.status,
            booking.transaction_id,
            booking.total_fare,
            booking.passenger_details,
            booking.status_message,
            booking.id,
        )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.rowcount > 0

    def delete_booking(self, booking_id: int) -> bool:
        """Delete a booking record by id using parameterized SQL."""
        query = "DELETE FROM bookings WHERE id = ?"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (booking_id,))
            return cursor.rowcount > 0

    def load_booking(self, booking_id: int) -> Optional[BookingRecord]:
        """Load a single booking record by id using parameterized SQL."""
        query = """
            SELECT id, trip_id, pnr, train_number, train_name, class_code, quota_code,
                   from_station, to_station, journey_date, status, transaction_id,
                   total_fare, passenger_details, status_message, created_at
            FROM bookings
            WHERE id = ?
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (booking_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return BookingRecord(
                id=row["id"],
                trip_id=row["trip_id"],
                pnr=row["pnr"] or "",
                train_number=row["train_number"],
                train_name=row["train_name"] or "",
                class_code=row["class_code"],
                quota_code=row["quota_code"],
                from_station=row["from_station"],
                to_station=row["to_station"],
                journey_date=row["journey_date"],
                status=row["status"],
                transaction_id=row["transaction_id"] or "",
                total_fare=float(row["total_fare"] or 0.0),
                passenger_details=row["passenger_details"] or "",
                status_message=row["status_message"] or "",
                created_at=row["created_at"],
            )

    def list_bookings(self) -> List[BookingRecord]:
        """List all saved bookings ordered by id descending."""
        query = """
            SELECT id, trip_id, pnr, train_number, train_name, class_code, quota_code,
                   from_station, to_station, journey_date, status, transaction_id,
                   total_fare, passenger_details, status_message, created_at
            FROM bookings
            ORDER BY id DESC
        """
        records: List[BookingRecord] = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            for row in cursor.fetchall():
                records.append(
                    BookingRecord(
                        id=row["id"],
                        trip_id=row["trip_id"],
                        pnr=row["pnr"] or "",
                        train_number=row["train_number"],
                        train_name=row["train_name"] or "",
                        class_code=row["class_code"],
                        quota_code=row["quota_code"],
                        from_station=row["from_station"],
                        to_station=row["to_station"],
                        journey_date=row["journey_date"],
                        status=row["status"],
                        transaction_id=row["transaction_id"] or "",
                        total_fare=float(row["total_fare"] or 0.0),
                        passenger_details=row["passenger_details"] or "",
                        status_message=row["status_message"] or "",
                        created_at=row["created_at"],
                    )
                )
        return records

    def get_booking_by_pnr(self, pnr: str) -> Optional[BookingRecord]:
        """Find a booking record by its 10-digit PNR."""
        query = """
            SELECT id, trip_id, pnr, train_number, train_name, class_code, quota_code,
                   from_station, to_station, journey_date, status, transaction_id,
                   total_fare, passenger_details, status_message, created_at
            FROM bookings
            WHERE pnr = ?
            LIMIT 1
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (pnr.strip(),))
            row = cursor.fetchone()
            if row is None:
                return None
            return BookingRecord(
                id=row["id"],
                trip_id=row["trip_id"],
                pnr=row["pnr"] or "",
                train_number=row["train_number"],
                train_name=row["train_name"] or "",
                class_code=row["class_code"],
                quota_code=row["quota_code"],
                from_station=row["from_station"],
                to_station=row["to_station"],
                journey_date=row["journey_date"],
                status=row["status"],
                transaction_id=row["transaction_id"] or "",
                total_fare=float(row["total_fare"] or 0.0),
                passenger_details=row["passenger_details"] or "",
                status_message=row["status_message"] or "",
                created_at=row["created_at"],
            )

    def get_latest_booking(self) -> Optional[BookingRecord]:
        """Retrieve the most recent booking record."""
        query = """
            SELECT id, trip_id, pnr, train_number, train_name, class_code, quota_code,
                   from_station, to_station, journey_date, status, transaction_id,
                   total_fare, passenger_details, status_message, created_at
            FROM bookings
            ORDER BY id DESC
            LIMIT 1
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            if row is None:
                return None
            return BookingRecord(
                id=row["id"],
                trip_id=row["trip_id"],
                pnr=row["pnr"] or "",
                train_number=row["train_number"],
                train_name=row["train_name"] or "",
                class_code=row["class_code"],
                quota_code=row["quota_code"],
                from_station=row["from_station"],
                to_station=row["to_station"],
                journey_date=row["journey_date"],
                status=row["status"],
                transaction_id=row["transaction_id"] or "",
                total_fare=float(row["total_fare"] or 0.0),
                passenger_details=row["passenger_details"] or "",
                status_message=row["status_message"] or "",
                created_at=row["created_at"],
            )

