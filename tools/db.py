"""
tools/db.py

SQLite persistence layer for price history and purchase decisions.
All data lives in data/gift_agent.db — lightweight, no setup required.
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "gift_agent.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS price_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                asin        TEXT NOT NULL,
                price       REAL,
                all_time_low  REAL,
                all_time_high REAL,
                fetched_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS purchase_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id    TEXT NOT NULL,
                asin            TEXT NOT NULL,
                product_name    TEXT,
                purchase_price  REAL,
                decision_reason TEXT,
                actioned_at     TEXT NOT NULL,
                status          TEXT DEFAULT 'pending_review'
            );

            CREATE INDEX IF NOT EXISTS idx_price_history_asin
                ON price_history(asin);

            CREATE INDEX IF NOT EXISTS idx_price_history_fetched
                ON price_history(fetched_at);
        """)
    logger.info(f"Database initialized at {DB_PATH}")


def upsert_price_record(data: dict):
    """Insert a new price snapshot for an ASIN."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO price_history (asin, price, all_time_low, all_time_high, fetched_at)
            VALUES (:asin, :current_price, :all_time_low, :all_time_high, :fetched_at)
            """,
            data,
        )


def get_last_fetched(asin: str) -> Optional[datetime]:
    """Return the datetime of the most recent fetch for this ASIN, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT fetched_at FROM price_history WHERE asin = ? ORDER BY fetched_at DESC LIMIT 1",
            (asin,),
        ).fetchone()
    if row:
        try:
            return datetime.fromisoformat(row["fetched_at"])
        except ValueError:
            return None
    return None


def get_price_history(asin: str, days: int = 90) -> list[dict]:
    """Return price snapshots for an ASIN over the last N days."""
    cutoff = datetime.utcnow().isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT asin, price, all_time_low, all_time_high, fetched_at
            FROM price_history
            WHERE asin = ?
              AND fetched_at >= datetime('now', ?)
            ORDER BY fetched_at ASC
            """,
            (asin, f"-{days} days"),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_price(asin: str) -> Optional[dict]:
    """Return the most recent price snapshot for an ASIN."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT asin, price, all_time_low, all_time_high, fetched_at
            FROM price_history
            WHERE asin = ?
            ORDER BY fetched_at DESC
            LIMIT 1
            """,
            (asin,),
        ).fetchone()
    return dict(row) if row else None


def log_purchase_decision(
    recipient_id: str,
    asin: str,
    product_name: str,
    purchase_price: float,
    decision_reason: str,
    status: str = "pending_review",
):
    """Record a purchase recommendation or action."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO purchase_log
              (recipient_id, asin, product_name, purchase_price, decision_reason, actioned_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recipient_id,
                asin,
                product_name,
                purchase_price,
                decision_reason,
                datetime.utcnow().isoformat(),
                status,
            ),
        )
