import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "health.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT    NOT NULL,
                tag       TEXT    NOT NULL,
                category  TEXT,
                value     TEXT,
                notes     TEXT,
                source    TEXT    NOT NULL DEFAULT 'cli'
            );

            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_tag       ON events(tag);

            CREATE TABLE IF NOT EXISTS garmin_daily (
                day             TEXT PRIMARY KEY,
                steps           INTEGER,
                rhr_avg         REAL,
                hr_avg          REAL,
                stress_avg      INTEGER,
                sleep_total_sec INTEGER,
                sleep_rem_sec   INTEGER,
                calories_active INTEGER,
                synced_at       TEXT NOT NULL
            );
        """)


def insert_event(
    tag: str,
    category: Optional[str] = None,
    value: Optional[str] = None,
    notes: Optional[str] = None,
    source: str = "cli",
    timestamp: Optional[str] = None,
) -> int:
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO events (timestamp, tag, category, value, notes, source) VALUES (?, ?, ?, ?, ?, ?)",
            (ts, tag, category, value, notes, source),
        )
        return cur.lastrowid


def query_events(
    tag: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50,
) -> list:
    clauses = []
    params: list = []

    if tag:
        clauses.append("tag = ?")
        params.append(tag)
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    with get_conn() as conn:
        return conn.execute(
            f"SELECT * FROM events {where} ORDER BY timestamp DESC LIMIT ?",
            params,
        ).fetchall()
