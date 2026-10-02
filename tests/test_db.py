import json
import os

from tracker import db, report, taxonomy, usaspending as usa

HERE = os.path.dirname(__file__)


def _award(key, amount, lm="2026-01-01 00:00:00"):
    return {"award_key": key, "award_id": key[:6], "recipient_name": "ACME", "amount": amount, "last_modified": lm,
            "description": "SATELLITE", "category": "Satellite & Orbital (general)", "source": "usaspending"}


def test_upsert_snapshot_and_diff(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    r1 = db.start_run(conn, "usaspending")
    assert db.upsert_award(conn, _award("A1", 100), ["Satellite & Orbital (general)"], r1) == "inserted"
    assert db.upsert_award(conn, _award("A2", 50), ["Satellite & Orbital (general)"], r1) == "inserted"
    db.finish_run(conn, r1, fetched=2, inserted=2, updated=0, dropped=0, ok=1)
    r2 = db.start_run(conn, "usaspending")
    assert db.upsert_award(conn, _award("A1", 100), ["Satellite & Orbital (general)"], r2) == "unchanged"
    assert db.upsert_award(conn, _award("A2", 75, "2026-02-01 00:00:00"), ["Satellite & Orbital (general)"], r2) == "updated"
    assert db.upsert_award(conn, _award("A3", 10), ["Propulsion"], r2) == "inserted"
    db.finish_run(conn, r2, fetched=3, inserted=1, updated=1, dropped=0, ok=1)
    assert conn.execute("SELECT COUNT(*) FROM award_snapshots").fetchone()[0] == 5
    out = report.diff(conn)
    assert "New awards: 1" in out and "Amount changes: 1" in out and "A2" in out
    # incremental run that re-fetches only A2 (unchanged) must not report the baseline as new
    r3 = db.start_run(conn, "usaspending")
    db.upsert_award(conn, _award("A2", 75, "2026-02-01 00:00:00"), ["Satellite & Orbital (general)"], r3)
    db.finish_run(conn, r3, fetched=1, inserted=0, updated=0, dropped=0, ok=1)
    assert "no changes" in report.diff(conn)
    # a later run touching only A1 with a new amount: 0 new, 1 change vs A1's latest earlier snapshot (run 2)
    r4 = db.start_run(conn, "usaspending")
    db.upsert_award(conn, _award("A1", 120, "2026-03-01 00:00:00"), ["Satellite & Orbital (general)"], r4)
    db.finish_run(conn, r4, fetched=1, inserted=0, updated=1, dropped=0, ok=1)
    out = report.diff(conn)
    assert "New awards: 0" in out and "Amount changes: 1" in out and "A1" in out and "+20" in out
    assert "Satellite" in report.summary(conn)
    assert db.last_successful_run(conn)["run_id"] == r4


def test_migrate_v1_schema(tmp_path):
    import sqlite3
    path = str(tmp_path / "v1.db")
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE awards (award_key TEXT PRIMARY KEY, award_id TEXT, recipient_name TEXT, agency TEXT, sub_agency TEXT, awarding_office TEXT, amount REAL, start_date TEXT, description TEXT, category TEXT, ingested_at TEXT)")
    c.execute("INSERT INTO awards (award_key, award_id, amount) VALUES ('X', 'FA1234', 1)")
    c.commit(); c.close()
    conn = db.connect(path)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(awards)")}
    assert {"naics", "office_name", "last_seen"} <= cols
    assert conn.execute("SELECT amount FROM awards WHERE award_key='X'").fetchone()[0] == 1


def test_normalize_award_fixture():
    with open(os.path.join(HERE, "fixtures", "usaspending_award.json")) as fh:
        item = json.load(fh)
    a = usa.normalize_award(item)
    assert a["award_key"] == "CONT_AWD_FA821920C0006_9700_-NONE-_-NONE-"
    assert a["naics"] == "336414" and a["amount"] > 1e9
    assert taxonomy.tag_award(a)[0] == "Guided Missile & Space Vehicle"
