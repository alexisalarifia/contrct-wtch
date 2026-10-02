"""Self-contained HTML dashboard built from the database. No server, no external data."""
import json
import os
from datetime import datetime, timezone

from . import config

TEMPLATE = os.path.join(os.path.dirname(__file__), "templates", "report.html")


def _rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args)]


def collect(conn, top=25):
    runs = _rows(conn, "SELECT run_id, started, finished, source, fetched, inserted, updated, dropped, ok FROM runs ORDER BY run_id DESC LIMIT 10")
    last = runs[0] if runs else None
    totals = conn.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM awards").fetchone()
    sf = conn.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM awards WHERE command LIKE 'Space Force%'").fetchone()
    commands = _rows(conn, "SELECT command AS name, COUNT(*) AS n, SUM(amount) AS amount FROM awards GROUP BY 1 ORDER BY 3 DESC")
    tags = _rows(conn, "SELECT t.tag AS name, COUNT(*) AS n, SUM(a.amount) AS amount FROM award_tags t JOIN awards a USING (award_key) GROUP BY 1 ORDER BY 3 DESC")
    lanes = _rows(conn, "SELECT lane AS name, COUNT(*) AS n, SUM(amount) AS amount FROM awards GROUP BY 1 ORDER BY 3 DESC")
    awards = _rows(conn,
        "SELECT award_id, recipient_name, amount, category, command, COALESCE(office_name, sub_agency) AS office, "
        "start_date, end_date, substr(description,1,160) AS description FROM awards ORDER BY amount DESC LIMIT ?", (top * 8,))
    recipients = _rows(conn, "SELECT recipient_name AS name, COUNT(*) AS n, SUM(amount) AS amount FROM awards GROUP BY 1 ORDER BY 3 DESC LIMIT ?", (top,))
    programs = _rows(conn, "SELECT substr(description,1,90) AS name, COUNT(*) AS n, SUM(amount) AS amount, MIN(command) AS command FROM awards GROUP BY 1 HAVING COUNT(*) > 3 ORDER BY 2 DESC LIMIT 15")
    # diff vs each award's latest earlier snapshot (same logic as report.diff)
    new, changed = [], []
    if last and last["ok"]:
        rid = last["run_id"]
        new = _rows(conn,
            "SELECT a.award_id, a.recipient_name, s.amount, a.category, a.command FROM award_snapshots s JOIN awards a USING (award_key) "
            "WHERE s.run_id=? AND NOT EXISTS (SELECT 1 FROM award_snapshots p WHERE p.award_key=s.award_key AND p.run_id < s.run_id) "
            "AND EXISTS (SELECT 1 FROM award_snapshots q WHERE q.run_id < ?) ORDER BY s.amount DESC LIMIT 50", (rid, rid))
        changed = _rows(conn,
            "SELECT a.award_id, a.recipient_name, p.amount AS before, c.amount AS after, a.command FROM award_snapshots c "
            "JOIN award_snapshots p ON p.award_key=c.award_key AND p.run_id=(SELECT MAX(run_id) FROM award_snapshots x WHERE x.award_key=c.award_key AND x.run_id<c.run_id) "
            "JOIN awards a ON a.award_key=c.award_key WHERE c.run_id=? AND c.amount != p.amount ORDER BY ABS(c.amount-p.amount) DESC LIMIT 50", (rid,))
    opps = _rows(conn, "SELECT title, agency, notice_type, posted, deadline, naics, url FROM opportunities ORDER BY posted DESC LIMIT 50")
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "window_start": config.WINDOW_START,
        "last_run": last,
        "runs": runs,
        "totals": {"awards": totals[0], "amount": totals[1], "sf_awards": sf[0], "sf_amount": sf[1]},
        "commands": commands, "tags": tags, "lanes": lanes, "awards": awards,
        "recipients": recipients, "programs": programs, "new": new, "changed": changed, "opportunities": opps,
    }


def render(conn, out_path="report.html", top=25):
    data = collect(conn, top)
    with open(TEMPLATE, encoding="utf-8") as fh:
        html = fh.read()
    payload = json.dumps(data, default=str).replace("</", "<\\/")
    html = html.replace("__DATA__", payload)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path, data
