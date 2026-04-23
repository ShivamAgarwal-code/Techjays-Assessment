"""SQLite database schema and query helpers."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent / 'data' / 'restaurant.db'


def get_connection(db_path=None):
    db_path = db_path or DEFAULT_DB_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn):
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS historical_covers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        hour INTEGER NOT NULL,
        covers INTEGER NOT NULL,
        day_of_week INTEGER NOT NULL,
        month INTEGER NOT NULL,
        is_holiday INTEGER DEFAULT 0,
        event_name TEXT,
        weather TEXT,
        UNIQUE(date, hour)
    );

    CREATE TABLE IF NOT EXISTS coefficients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        coeff_type TEXT NOT NULL,
        coeff_key TEXT NOT NULL,
        value REAL NOT NULL,
        updated_at TEXT NOT NULL,
        update_count INTEGER DEFAULT 0,
        UNIQUE(coeff_type, coeff_key)
    );

    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        hour INTEGER NOT NULL,
        predicted_covers INTEGER NOT NULL,
        actual_covers INTEGER,
        created_at TEXT NOT NULL,
        UNIQUE(date, hour)
    );

    CREATE TABLE IF NOT EXISTS corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        hour INTEGER,
        predicted_value REAL NOT NULL,
        actual_value REAL NOT NULL,
        reason TEXT,
        applied_at TEXT NOT NULL,
        coefficients_updated TEXT
    );

    CREATE TABLE IF NOT EXISTS menu_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        category TEXT NOT NULL,
        popularity_weight REAL NOT NULL,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_item_id INTEGER NOT NULL REFERENCES menu_items(id),
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
        quantity_grams REAL NOT NULL,
        UNIQUE(menu_item_id, ingredient_id)
    );

    CREATE TABLE IF NOT EXISTS ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        unit TEXT NOT NULL,
        shelf_life_days INTEGER NOT NULL,
        supplier_lead_time_days INTEGER NOT NULL,
        min_order_quantity REAL NOT NULL,
        cost_per_unit REAL NOT NULL,
        current_stock REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS staff_roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        station TEXT,
        covers_per_staff REAL NOT NULL,
        min_on_shift INTEGER NOT NULL,
        max_on_shift INTEGER NOT NULL,
        hourly_rate REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS staff_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        hour INTEGER NOT NULL,
        role TEXT NOT NULL,
        station TEXT,
        staff_count INTEGER NOT NULL,
        predicted_covers INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS ingredient_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_date TEXT NOT NULL,
        delivery_date TEXT NOT NULL,
        needed_by_date TEXT NOT NULL,
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
        quantity REAL NOT NULL,
        estimated_cost REAL NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_covers_date ON historical_covers(date);
    CREATE INDEX IF NOT EXISTS idx_coefficients_type ON coefficients(coeff_type, coeff_key);
    CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(date);
    """)

    conn.commit()


# --- Coefficient helpers ---

def load_coefficients(conn):
    """Load all coefficients into a nested dict: {coeff_type: {coeff_key: value}}."""
    rows = conn.execute("SELECT coeff_type, coeff_key, value FROM coefficients").fetchall()
    coeffs = {}
    for row in rows:
        coeffs.setdefault(row['coeff_type'], {})[row['coeff_key']] = row['value']
    return coeffs


def get_coefficient(conn, coeff_type, coeff_key):
    row = conn.execute(
        "SELECT value, update_count FROM coefficients WHERE coeff_type=? AND coeff_key=?",
        (coeff_type, coeff_key)
    ).fetchone()
    return dict(row) if row else None


def save_coefficient(conn, coeff_type, coeff_key, value, update_count):
    conn.execute("""
        INSERT INTO coefficients (coeff_type, coeff_key, value, updated_at, update_count)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(coeff_type, coeff_key)
        DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, update_count=excluded.update_count
    """, (coeff_type, coeff_key, value, datetime.now().isoformat(), update_count))
    conn.commit()


# --- Prediction helpers ---

def save_prediction(conn, date_str, hourly_covers):
    now = datetime.now().isoformat()
    for hour, covers in hourly_covers.items():
        conn.execute("""
            INSERT INTO predictions (date, hour, predicted_covers, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, hour) DO UPDATE SET predicted_covers=excluded.predicted_covers, created_at=excluded.created_at
        """, (date_str, hour, covers, now))
    conn.commit()


def save_correction(conn, date_str, hour, predicted, actual, reason, coefficients_updated):
    conn.execute("""
        INSERT INTO corrections (date, hour, predicted_value, actual_value, reason, applied_at, coefficients_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (date_str, hour, predicted, actual, reason, datetime.now().isoformat(),
          json.dumps(coefficients_updated)))
    conn.commit()


def get_historical_covers(conn, date_str):
    """Get hourly covers for a specific date."""
    rows = conn.execute(
        "SELECT hour, covers FROM historical_covers WHERE date=? ORDER BY hour",
        (date_str,)
    ).fetchall()
    return {row['hour']: row['covers'] for row in rows}


def get_recent_daily_totals(conn, before_date, days=90):
    """Get daily totals for the last N days before a given date."""
    rows = conn.execute("""
        SELECT date, SUM(covers) as daily_total, weather, event_name
        FROM historical_covers
        WHERE date < ?
        GROUP BY date
        ORDER BY date DESC
        LIMIT ?
    """, (before_date, days)).fetchall()
    return [dict(r) for r in rows]


def get_all_staff_roles(conn):
    rows = conn.execute("SELECT * FROM staff_roles").fetchall()
    return [dict(r) for r in rows]


def get_all_menu_items(conn):
    rows = conn.execute("SELECT * FROM menu_items WHERE active=1").fetchall()
    return [dict(r) for r in rows]


def get_all_ingredients(conn):
    rows = conn.execute("SELECT * FROM ingredients").fetchall()
    return {r['id']: dict(r) for r in rows}


def get_recipes_by_menu_item(conn):
    rows = conn.execute("SELECT * FROM recipes").fetchall()
    recipes = {}
    for r in rows:
        recipes.setdefault(r['menu_item_id'], []).append(dict(r))
    return recipes


def get_corrections_history(conn, limit=20):
    rows = conn.execute("""
        SELECT * FROM corrections ORDER BY applied_at DESC LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_predictions_history(conn, limit=20):
    rows = conn.execute("""
        SELECT p.date, p.hour, p.predicted_covers, p.actual_covers, p.created_at
        FROM predictions p ORDER BY p.date DESC, p.hour LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]
