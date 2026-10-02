"""SQLite schema, upserts, snapshots, office cache."""
import sqlite3
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS awards (
    award_key       TEXT PRIMARY KEY,
    award_id        TEXT,
    recipient_name  TEXT,
    uei             TEXT,
    recipient_id    TEXT,
    agency          TEXT,
    sub_agency      TEXT,
    office_code     TEXT,
    office_name     TEXT,
    award_type      TEXT,
    amount          REAL,
    start_date      TEXT,
    end_date        TEXT,
    last_modified   TEXT,
    description     TEXT,
    naics           TEXT,
    naics_desc      TEXT,
    psc             TEXT,
    psc_desc        TEXT,
    pop_state       TEXT,
    category        TEXT,
    lane            TEXT,
    command         TEXT,
    source          TEXT DEFAULT 'usaspending',
    first_seen      TEXT,
    last_seen       TEXT
);
CREATE TABLE IF NOT EXISTS award_tags (
    award_key TEXT, tag TEXT, PRIMARY KEY (award_key, tag)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started TEXT, finished TEXT, source TEXT,
    fetched INTEGER, inserted INTEGER, updated INTEGER, dropped INTEGER, ok INTEGER
);
CREATE TABLE IF NOT EXISTS award_snapshots (
    award_key TEXT, run_id INTEGER, amount REAL, last_modified TEXT,
    PRIMARY KEY (award_key, run_id)
);
CREATE TABLE IF NOT EXISTS offices (
    prefix TEXT PRIMARY KEY, code TEXT, name TEXT, fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS subawards (
    sub_id TEXT PRIMARY KEY, prime_award_internal_id INTEGER, prime_award_id TEXT,
    prime_recipient TEXT, sub_awardee TEXT, amount REAL, date TEXT, run_id INTEGER
);
CREATE TABLE IF NOT EXISTS opportunities (
    notice_id TEXT PRIMARY KEY, title TEXT, agency TEXT, office TEXT, notice_type TEXT,
    posted TEXT, deadline TEXT, naics TEXT, psc TEXT, url TEXT, run_id INTEGER
);
"""
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_awards_category ON awards(category);
CREATE INDEX IF NOT EXISTS idx_awards_amount ON awards(amount);
CREATE INDEX IF NOT EXISTS idx_awards_office ON awards(office_code);
CREATE INDEX IF NOT EXISTS idx_awards_command ON awards(command);
"""

AWARD_COLS = [
    "award_key", "award_id", "recipient_name", "uei", "recipient_id", "agency", "sub_agency",
    "office_code", "office_name", "award_type", "amount", "start_date", "end_date", "last_modified",
    "description", "naics", "naics_desc", "psc", "psc_desc", "pop_state", "category", "lane", "command", "source",
]


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def connect(path=None):
    conn = sqlite3.connect(path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.executescript(INDEXES)
    return conn


def _migrate(conn):
    """Add columns introduced after v1 to an existing awards table."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(awards)")}
    for col in AWARD_COLS + ["first_seen", "last_seen"]:
        if col not in have:
            kind = "REAL" if col == "amount" else "TEXT"
            conn.execute(f"ALTER TABLE awards ADD COLUMN {col} {kind}")
    conn.commit()


def start_run(conn, source):
    cur = conn.execute("INSERT INTO runs (started, source) VALUES (?, ?)", (now(), source))
    conn.commit()
    return cur.lastrowid


def finish_run(conn, run_id, **counts):
    cols = ", ".join(f"{k}=?" for k in counts)
    conn.execute(f"UPDATE runs SET finished=?, {cols} WHERE run_id=?", (now(), *counts.values(), run_id))
    conn.commit()


def last_successful_run(conn, source=None):
    q = "SELECT * FROM runs WHERE ok=1"
    args = ()
    if source:
        q += " AND source=?"
        args = (source,)
    return conn.execute(q + " ORDER BY run_id DESC LIMIT 1", args).fetchone()


def upsert_award(conn, a, tags, run_id):
    """Insert or update. Returns 'inserted' | 'updated' | 'unchanged'."""
    ts = now()
    existing = conn.execute("SELECT amount, last_modified FROM awards WHERE award_key=?", (a["award_key"],)).fetchone()
    row = {c: a.get(c) for c in AWARD_COLS}
    if existing is None:
        conn.execute(
            f"INSERT INTO awards ({', '.join(AWARD_COLS)}, first_seen, last_seen) "
            f"VALUES ({', '.join(':' + c for c in AWARD_COLS)}, :ts, :ts)",
            {**row, "ts": ts},
        )
        status = "inserted"
    else:
        changed = (existing["amount"] != row["amount"]) or (existing["last_modified"] != row["last_modified"])
        sets = ", ".join(f"{c}=:{c}" for c in AWARD_COLS if c != "award_key")
        conn.execute(f"UPDATE awards SET {sets}, last_seen=:ts WHERE award_key=:award_key", {**row, "ts": ts})
        status = "updated" if changed else "unchanged"
    conn.execute("DELETE FROM award_tags WHERE award_key=?", (a["award_key"],))
    conn.executemany("INSERT OR IGNORE INTO award_tags (award_key, tag) VALUES (?, ?)", [(a["award_key"], t) for t in tags])
    conn.execute(
        "INSERT OR REPLACE INTO award_snapshots (award_key, run_id, amount, last_modified) VALUES (?, ?, ?, ?)",
        (a["award_key"], run_id, row["amount"], row["last_modified"]),
    )
    return status


def get_office(conn, prefix):
    return conn.execute("SELECT code, name FROM offices WHERE prefix=?", (prefix,)).fetchone()


def put_office(conn, prefix, code, name):
    conn.execute("INSERT OR REPLACE INTO offices (prefix, code, name, fetched_at) VALUES (?, ?, ?, ?)", (prefix, code, name, now()))


def upsert_subaward(conn, s, run_id):
    conn.execute(
        "INSERT OR REPLACE INTO subawards (sub_id, prime_award_internal_id, prime_award_id, prime_recipient, "
        "sub_awardee, amount, date, run_id) VALUES (:sub_id, :prime_award_internal_id, :prime_award_id, "
        ":prime_recipient, :sub_awardee, :amount, :date, :run_id)",
        {**s, "run_id": run_id},
    )


def upsert_opportunity(conn, o, run_id):
    conn.execute(
        "INSERT OR REPLACE INTO opportunities (notice_id, title, agency, office, notice_type, posted, deadline, "
        "naics, psc, url, run_id) VALUES (:notice_id, :title, :agency, :office, :notice_type, :posted, :deadline, "
        ":naics, :psc, :url, :run_id)",
        {**o, "run_id": run_id},
    )
