"""Post-run sanity checks. Returns (ok, [problems])."""
import logging

from . import config

log = logging.getLogger("tracker.verify")


def verify(conn, run_id, fetched, inserted, updated):
    problems = []
    total = conn.execute("SELECT COUNT(*) FROM awards").fetchone()[0]
    if total < inserted:
        problems.append(f"awards rows {total} < inserted {inserted}")
    bad_key = conn.execute("SELECT COUNT(*) FROM awards WHERE award_key IS NULL OR award_key=''").fetchone()[0]
    if bad_key:
        problems.append(f"{bad_key} awards with empty award_key")
    placeholders = ",".join("?" * len(config.TAG_NAMES))
    bad_cat = conn.execute(f"SELECT COUNT(*) FROM awards WHERE category NOT IN ({placeholders})", config.TAG_NAMES).fetchone()[0]
    if bad_cat:
        problems.append(f"{bad_cat} awards with unknown category")
    untagged = conn.execute("SELECT COUNT(*) FROM awards a WHERE NOT EXISTS (SELECT 1 FROM award_tags t WHERE t.award_key=a.award_key)").fetchone()[0]
    if untagged:
        problems.append(f"{untagged} awards with no rows in award_tags")
    snaps = conn.execute("SELECT COUNT(*) FROM award_snapshots WHERE run_id=?", (run_id,)).fetchone()[0]
    if fetched and snaps == 0:
        problems.append("no snapshots written this run")
    neg = conn.execute("SELECT COUNT(*) FROM awards WHERE amount < 0").fetchone()[0]
    if neg:
        log.info("note: %d awards with negative amounts (deobligations), kept", neg)
    if fetched and inserted == 0 and updated == 0:
        log.info("nothing new: all %d fetched awards already current", fetched)
    for p in problems:
        log.error("verification FAILED: %s", p)
    if not problems:
        log.info("verification passed: %d awards, %d snapshots this run", total, snaps)
    return not problems, problems
