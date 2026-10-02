"""Space & defense contract tracker: USAspending -> SQLite with taxonomy tagging.

Pulls Department of the Air Force contract awards from the USAspending API,
tags each award with a NewSpace capability category, and loads it into
space_contracts.db. Safe to re-run: existing awards are skipped.
"""
import json
import logging
import os
import re
import sqlite3
import sys
import time

import requests

API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
DB_PATH = os.environ.get("DB_PATH", "space_contracts.db")
MAX_PAGES = int(os.environ.get("MAX_PAGES", "10"))     # 100 awards per page
MAX_RETRIES = 5
PAGE_SIZE = 100
TIMEOUT = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")


# 1. Database setup
def setup_database(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS awards (
            award_key      TEXT PRIMARY KEY,   -- USAspending generated_internal_id (globally unique)
            award_id       TEXT,               -- PIID as displayed
            recipient_name TEXT,
            agency         TEXT,
            sub_agency     TEXT,
            awarding_office TEXT,
            amount         REAL,
            start_date     TEXT,
            description    TEXT,
            category       TEXT,
            ingested_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_awards_category ON awards(category)")
    conn.commit()
    return conn


# 2. NLP categorization engine
# Ordered taxonomy: first matching category wins, most specific first.
TAXONOMY = [
    ("Propulsion & Launch", [r"\b(propulsion|rocket|engines?|thrusters?|thrust|turbopumps?|launch vehicle)\b"]),
    ("Advanced Materials", [r"\b(inconel|titanium|carbon composites?|ablative|superalloys?|3d[- ]?print\w*|additive(ly)? manufactur\w*)\b"]),
    ("Avionics & Compute", [r"\b(rad[- ]hard|radiation[- ]hardened|fpgas?|flight software|autonomous navigation|avionics)\b"]),
    ("Space Infrastructure", [r"\b(optical communications?|laser links?|orbital|satellites?|satcom|isru|spacecraft|on[- ]orbit)\b"]),
]
_COMPILED = [(cat, [re.compile(p, re.I) for p in pats]) for cat, pats in TAXONOMY]


def categorize_abstract(text):
    if not text:
        return "Uncategorized"
    for category, patterns in _COMPILED:
        if any(p.search(text) for p in patterns):
            return category
    return "Uncategorized"


# 3. USAspending extractor with exponential backoff
def _post_with_backoff(payload):
    delay = 2
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, json=payload, timeout=TIMEOUT)
        except requests.exceptions.RequestException as exc:
            log.warning("attempt %d/%d network error: %s", attempt, MAX_RETRIES, exc)
        else:
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                retry_after = resp.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else delay
                log.warning("attempt %d/%d HTTP %s, retrying in %ss", attempt, MAX_RETRIES, resp.status_code, wait)
                time.sleep(wait)
                delay *= 2
                continue
            resp.raise_for_status()
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"USAspending API failed after {MAX_RETRIES} attempts")


def fetch_usaspending_awards(max_pages=MAX_PAGES):
    log.info("Fetching Air Force contract awards from USAspending (up to %d pages)", max_pages)
    base_payload = {
        "filters": {
            "agencies": [{"type": "awarding", "tier": "subtier", "name": "Department of the Air Force"}],
            "award_type_codes": ["A", "B", "C", "D"],
            "time_period": [{"start_date": "2026-01-01", "end_date": "2026-12-31"}],
        },
        "fields": [
            "Award ID", "Recipient Name", "Description", "Award Amount", "Start Date",
            "Awarding Agency", "Awarding Sub Agency", "Awarding Office Name", "generated_internal_id",
        ],
        "sort": "Award Amount",
        "order": "desc",
        "limit": PAGE_SIZE,
    }
    awards = []
    for page in range(1, max_pages + 1):
        data = _post_with_backoff({**base_payload, "page": page})
        results = data.get("results", [])
        for item in results:
            awards.append({
                "award_key": item.get("generated_internal_id") or item.get("Award ID"),
                "award_id": item.get("Award ID", "UNKNOWN"),
                "recipient_name": item.get("Recipient Name", "UNKNOWN"),
                "agency": item.get("Awarding Agency", "Department of Defense"),
                "sub_agency": item.get("Awarding Sub Agency", "Department of the Air Force"),
                "awarding_office": item.get("Awarding Office Name"),
                "amount": item.get("Award Amount") or 0.0,
                "start_date": item.get("Start Date"),
                "description": item.get("Description") or "",
            })
        log.info("page %d: %d awards", page, len(results))
        if not data.get("page_metadata", {}).get("hasNext"):
            break
    return awards


# 4. Load with duplicate skipping
def load_awards(conn, awards):
    inserted = skipped = 0
    cur = conn.cursor()
    for a in awards:
        a["category"] = categorize_abstract(a["description"])
        cur.execute(
            """
            INSERT OR IGNORE INTO awards
                (award_key, award_id, recipient_name, agency, sub_agency, awarding_office,
                 amount, start_date, description, category)
            VALUES (:award_key, :award_id, :recipient_name, :agency, :sub_agency, :awarding_office,
                    :amount, :start_date, :description, :category)
            """,
            a,
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1
    conn.commit()
    return inserted, skipped


# 5. Automated verification
def verify(conn, fetched, inserted):
    problems = []
    total = conn.execute("SELECT COUNT(*) FROM awards").fetchone()[0]
    if total < inserted:
        problems.append(f"row count {total} < inserted {inserted}")
    null_keys = conn.execute("SELECT COUNT(*) FROM awards WHERE award_key IS NULL OR award_key=''").fetchone()[0]
    if null_keys:
        problems.append(f"{null_keys} rows with empty award_key")
    bad_cat = conn.execute(
        "SELECT COUNT(*) FROM awards WHERE category NOT IN (%s)"
        % ",".join("?" * (len(TAXONOMY) + 1)),
        [c for c, _ in TAXONOMY] + ["Uncategorized"],
    ).fetchone()[0]
    if bad_cat:
        problems.append(f"{bad_cat} rows with unknown category")
    neg = conn.execute("SELECT COUNT(*) FROM awards WHERE amount < 0").fetchone()[0]
    if neg:
        log.info("note: %d awards have negative amounts (deobligations), kept as-is", neg)
    if fetched and inserted == 0:
        log.info("verification: nothing new (all %d fetched awards already present)", fetched)
    if problems:
        for p in problems:
            log.error("verification FAILED: %s", p)
        return False
    log.info("verification passed: %d rows in awards table", total)
    return True


def run_pipeline():
    conn = setup_database()
    awards = fetch_usaspending_awards()
    log.info("Extracted %d awards", len(awards))
    inserted, skipped = load_awards(conn, awards)
    log.info("Loaded %d new, skipped %d duplicates", inserted, skipped)
    ok = verify(conn, len(awards), inserted)
    conn.close()
    log.info("Pipeline complete. Database: %s", DB_PATH)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run_pipeline())
