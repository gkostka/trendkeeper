"""The SQLite file: price cache, the decision log (append-only) and the open alerts."""
import json
import sqlite3
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    day TEXT NOT NULL, series TEXT NOT NULL, value REAL NOT NULL,
    PRIMARY KEY (day, series)
);
CREATE TABLE IF NOT EXISTS decisions (
    day TEXT NOT NULL, strategy TEXT NOT NULL, run_at TEXT NOT NULL,
    git_commit TEXT NOT NULL, config_hash TEXT NOT NULL, data TEXT NOT NULL,
    PRIMARY KEY (day, strategy)
);
CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decisions
    BEGIN SELECT RAISE(ABORT, 'the decision log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions
    BEGIN SELECT RAISE(ABORT, 'the decision log is append-only'); END;
CREATE TABLE IF NOT EXISTS alerts (
    key TEXT PRIMARY KEY, opened TEXT NOT NULL, detail TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db


def save_prices(db: sqlite3.Connection, px: pd.DataFrame) -> None:
    rows = [(f"{day:%Y-%m-%d}", col, float(v)) for col in px for day, v in px[col].dropna().items()]
    with db:
        db.executemany("INSERT OR REPLACE INTO prices VALUES (?, ?, ?)", rows)


def load_prices(db: sqlite3.Connection) -> pd.DataFrame:
    long = pd.read_sql("SELECT day, series, value FROM prices", db, parse_dates=["day"])
    if long.empty:
        return pd.DataFrame()
    return long.pivot(index="day", columns="series", values="value").sort_index().rename_axis(None, axis=1)


def last_price_day(db: sqlite3.Connection, series: str) -> pd.Timestamp | None:
    (day,) = db.execute("SELECT MAX(day) FROM prices WHERE series = ?", (series,)).fetchone()
    return pd.Timestamp(day) if day else None


def log_decision(db, day, strategy, run_at, git_commit, config_hash, data: dict) -> bool:
    """Writes one day's decision for a strategy; returns False if that day is already logged."""
    with db:
        cur = db.execute("INSERT OR IGNORE INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
                         (f"{day:%Y-%m-%d}", strategy, run_at, git_commit, config_hash, json.dumps(data)))
    return cur.rowcount == 1


def decisions(db, strategy: str, limit: int | None = None) -> list[dict]:
    q = "SELECT day, run_at, git_commit, config_hash, data FROM decisions WHERE strategy = ? ORDER BY day DESC"
    rows = db.execute(q + (f" LIMIT {int(limit)}" if limit else ""), (strategy,)).fetchall()
    return [{"day": d, "run_at": r, "git_commit": c, "config_hash": h, **json.loads(x)} for d, r, c, h, x in rows]


def update_alerts(db, current: dict[str, str], now: str) -> tuple[dict[str, str], dict[str, str]]:
    """Replaces the open alerts with `current` (key -> detail); returns (started, cleared)."""
    before = dict(db.execute("SELECT key, detail FROM alerts").fetchall())
    started = {k: v for k, v in current.items() if k not in before}
    cleared = {k: v for k, v in before.items() if k not in current}
    with db:
        db.executemany("DELETE FROM alerts WHERE key = ?", [(k,) for k in cleared])
        db.executemany("INSERT INTO alerts VALUES (?, ?, ?)", [(k, now, v) for k, v in started.items()])
        db.executemany("UPDATE alerts SET detail = ? WHERE key = ?", [(v, k) for k, v in current.items() if k in before])
    return started, cleared


def open_alerts(db) -> dict[str, tuple[str, str]]:
    return {k: (o, d) for k, o, d in db.execute("SELECT key, opened, detail FROM alerts ORDER BY opened")}
