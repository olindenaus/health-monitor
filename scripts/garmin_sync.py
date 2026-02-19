"""
Sync daily summary data from GarminDB into health.db.

GarminDB source:  ~/HealthData/DBs/garmin_summary.db  (days_summary table)
Target:           data/health.db                       (garmin_daily table)

Run manually or via cron:
    .venv/bin/python scripts/garmin_sync.py
    .venv/bin/python scripts/garmin_sync.py --days 90
"""

import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone, date, timedelta

# --- paths ------------------------------------------------------------------

GARMIN_SUMMARY_DB = Path.home() / "HealthData" / "DBs" / "garmin_summary.db"
GARMIN_MAIN_DB    = Path.home() / "HealthData" / "DBs" / "garmin.db"

# health.db lives two levels up from this script (project root / data /)
HEALTH_DB = Path(__file__).parent.parent / "data" / "health.db"


# --- helpers ----------------------------------------------------------------

def _time_str_to_seconds(t: str) -> int:
    """Convert 'HH:MM:SS.ffffff' or 'HH:MM:SS' to integer seconds."""
    if not t:
        return 0
    try:
        parts = t.split(".")[0].split(":")
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        return h * 3600 + m * 60 + s
    except Exception:
        return 0


def _garmin_conn(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(
            f"GarminDB file not found: {path}\n"
            "Run: garmindb_cli.py --all --download --import --analyze --latest"
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _health_conn() -> sqlite3.Connection:
    HEALTH_DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(HEALTH_DB)
    conn.row_factory = sqlite3.Row
    return conn


# --- core sync --------------------------------------------------------------

def sync(days: int = 30, verbose: bool = True) -> int:
    """
    Pull the last `days` days of summary data from GarminDB and upsert
    into garmin_daily.  Returns the number of rows written.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    now   = datetime.now(timezone.utc).isoformat()

    # -- read from garmin_summary.db -----------------------------------------
    rows_written = 0
    with _garmin_conn(GARMIN_SUMMARY_DB) as gsrc:
        summary_rows = gsrc.execute(
            """
            SELECT
                day,
                steps,
                rhr_avg,
                hr_avg,
                stress_avg,
                sleep_avg,
                rem_sleep_avg,
                calories_active_avg
            FROM days_summary
            WHERE day >= ?
            ORDER BY day
            """,
            (since,),
        ).fetchall()

    if not summary_rows:
        print(f"No GarminDB data found since {since}.")
        return 0

    # -- read sleep detail from garmin.db (if available) --------------------
    # garmin.db.sleep has per-day total_sleep / deep_sleep / rem_sleep
    sleep_by_day: dict = {}
    try:
        with _garmin_conn(GARMIN_MAIN_DB) as gmain:
            for row in gmain.execute(
                "SELECT day, total_sleep, rem_sleep FROM sleep WHERE day >= ?",
                (since,),
            ).fetchall():
                sleep_by_day[row["day"]] = row
    except FileNotFoundError:
        pass  # garmin.db is optional

    # -- upsert into health.db -----------------------------------------------
    with _health_conn() as hdst:
        # Ensure table exists (in case the CLI hasn't been run yet)
        hdst.execute("""
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
            )
        """)

        for row in summary_rows:
            day = row["day"]

            # Prefer detailed sleep from garmin.db, fall back to summary avg
            if day in sleep_by_day:
                sleep_total_sec = _time_str_to_seconds(sleep_by_day[day]["total_sleep"])
                sleep_rem_sec   = _time_str_to_seconds(sleep_by_day[day]["rem_sleep"])
            else:
                sleep_total_sec = _time_str_to_seconds(row["sleep_avg"])
                sleep_rem_sec   = _time_str_to_seconds(row["rem_sleep_avg"])

            hdst.execute(
                """
                INSERT INTO garmin_daily
                    (day, steps, rhr_avg, hr_avg, stress_avg,
                     sleep_total_sec, sleep_rem_sec, calories_active, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(day) DO UPDATE SET
                    steps           = excluded.steps,
                    rhr_avg         = excluded.rhr_avg,
                    hr_avg          = excluded.hr_avg,
                    stress_avg      = excluded.stress_avg,
                    sleep_total_sec = excluded.sleep_total_sec,
                    sleep_rem_sec   = excluded.sleep_rem_sec,
                    calories_active = excluded.calories_active,
                    synced_at       = excluded.synced_at
                """,
                (
                    day,
                    row["steps"],
                    row["rhr_avg"],
                    row["hr_avg"],
                    row["stress_avg"],
                    sleep_total_sec,
                    sleep_rem_sec,
                    row["calories_active_avg"],
                    now,
                ),
            )
            rows_written += 1

            if verbose:
                sleep_h = sleep_total_sec // 3600
                sleep_m = (sleep_total_sec % 3600) // 60
                print(
                    f"  {day}  steps={row['steps'] or '-':>6}  "
                    f"rhr={row['rhr_avg'] or '-'}  "
                    f"stress={row['stress_avg'] or '-':>3}  "
                    f"sleep={sleep_h}h{sleep_m:02d}m"
                )

    return rows_written


# --- CLI entry --------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sync GarminDB data into health.db")
    parser.add_argument(
        "--days", type=int, default=30,
        help="How many days back to sync (default: 30)"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-row output"
    )
    args = parser.parse_args()

    print(f"Syncing last {args.days} days from GarminDB → health.db ...")
    n = sync(days=args.days, verbose=not args.quiet)
    print(f"\nDone — {n} day(s) upserted into garmin_daily.")


if __name__ == "__main__":
    main()
