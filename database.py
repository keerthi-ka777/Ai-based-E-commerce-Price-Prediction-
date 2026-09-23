import sqlite3
from contextlib import contextmanager
from config import DB_PATH

SCHEMA = '''
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product TEXT NOT NULL,
    category TEXT,
    base_price REAL,
    competitor_price REAL,
    discount REAL,
    rating REAL,
    demand_score REAL,
    popularity_index REAL,
    social_trend REAL,
    return_risk REAL,
    weather_impact REAL,
    loyalty_score REAL,
    lifecycle_score REAL,
    predicted_price REAL,
    strategy TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_text TEXT NOT NULL,
    sentiment TEXT,
    score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bundle_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    items TEXT NOT NULL,
    optimized_price REAL,
    discount_percent REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)

def add_prediction(payload):
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO predictions
            (product, category, base_price, competitor_price, discount, rating,
             demand_score, popularity_index, social_trend, return_risk,
             weather_impact, loyalty_score, lifecycle_score, predicted_price, strategy)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                payload["product"], payload.get("category"),
                payload["base_price"], payload["competitor_price"],
                payload["discount"], payload["rating"],
                payload["demand_score"], payload["popularity_index"],
                payload["social_trend"], payload["return_risk"],
                payload["weather_impact"], payload["loyalty_score"],
                payload["lifecycle_score"], payload["predicted_price"],
                payload["strategy"]
            )
        )
        return cur.lastrowid

def recent_predictions(limit=10):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM predictions ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
