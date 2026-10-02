"""Summary and diff reports over the database."""


def _money(x):
    return f"${x:,.0f}" if x is not None else "-"


def _table(rows, headers, widths):
    out = ["".join(h.ljust(w) if i == 0 else h.rjust(w) for i, (h, w) in enumerate(zip(headers, widths)))]
    out.append("-" * sum(widths))
    for r in rows:
        out.append("".join(str(c)[:w - 1].ljust(w) if i == 0 else str(c).rjust(w) for i, (c, w) in enumerate(zip(r, widths))))
    return "\n".join(out)


def summary(conn, top=5):
    parts = []
    rows = conn.execute(
        "SELECT t.tag, COUNT(*), SUM(a.amount) FROM award_tags t JOIN awards a USING (award_key) "
        "GROUP BY t.tag ORDER BY COUNT(*) DESC"
    ).fetchall()
    parts.append("Awards per tag (multi-label; an award can appear under several)")
    parts.append(_table([(r[0], r[1], _money(r[2])) for r in rows], ["Tag", "Count", "Total $"], [38, 7, 22]))

    rows = conn.execute("SELECT category, COUNT(*), SUM(amount) FROM awards GROUP BY category ORDER BY COUNT(*) DESC").fetchall()
    parts.append("\nAwards per primary category")
    parts.append(_table([(r[0], r[1], _money(r[2])) for r in rows], ["Category", "Count", "Total $"], [38, 7, 22]))

    rows = conn.execute("SELECT lane, COUNT(*), SUM(amount) FROM awards GROUP BY lane ORDER BY COUNT(*) DESC").fetchall()
    parts.append("\nAwards per funding lane (from NAICS/PSC codes)")
    parts.append(_table([(r[0], r[1], _money(r[2])) for r in rows], ["Lane", "Count", "Total $"], [44, 7, 22]))

    rows = conn.execute(
        "SELECT substr(description,1,70), COUNT(*), SUM(amount), MIN(sub_agency) FROM awards GROUP BY 1 HAVING COUNT(*) > 3 ORDER BY COUNT(*) DESC LIMIT ?", (top * 2,)
    ).fetchall()
    parts.append(f"\nTop {top * 2} programs (identical descriptions, >3 awards)")
    parts.append(_table([(f"{r[0]} [{(r[3] or '')[:4]}]", r[1], _money(r[2])) for r in rows], ["Program", "Awards", "Total $"], [60, 8, 22]))

    rows = conn.execute(
        "SELECT award_id, recipient_name, amount, category, office_name, substr(description,1,80) FROM awards ORDER BY amount DESC LIMIT ?", (top,)
    ).fetchall()
    parts.append(f"\nTop {top} highest-value awards")
    for r in rows:
        parts.append(f"{r[0]:<16}{r[1][:36]:<38}{_money(r[2]):>18}  {r[3]}")
        parts.append(f"    office: {r[4] or '?'}\n    {r[5]}")

    rows = conn.execute(
        "SELECT recipient_name, COUNT(*), SUM(amount) FROM awards GROUP BY recipient_name ORDER BY SUM(amount) DESC LIMIT ?", (top * 2,)
    ).fetchall()
    parts.append(f"\nTop {top * 2} recipients by obligated $")
    parts.append(_table([(r[0], r[1], _money(r[2])) for r in rows], ["Recipient", "Awards", "Total $"], [40, 8, 22]))

    rows = conn.execute(
        "SELECT COALESCE(office_name, sub_agency, '?'), COUNT(*), SUM(amount) FROM awards GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT ?", (top * 2,)
    ).fetchall()
    parts.append(f"\nTop {top * 2} awarding offices")
    parts.append(_table([(r[0], r[1], _money(r[2])) for r in rows], ["Office", "Awards", "Total $"], [44, 8, 22]))

    n_sub = conn.execute("SELECT COUNT(*) FROM subawards").fetchone()[0]
    n_opp = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    parts.append(f"\nsubawards: {n_sub}   opportunities (SAM): {n_opp}")
    return "\n".join(parts)


def diff(conn, run_id=None, prev_run_id=None):
    """New awards (no snapshot in any earlier run) and amount changes vs each award's latest earlier snapshot."""
    if run_id is None:
        row = conn.execute("SELECT run_id FROM runs WHERE ok=1 ORDER BY run_id DESC LIMIT 1").fetchone()
        if not row:
            return "no successful runs yet"
        run_id = row["run_id"]
    floor = prev_run_id if prev_run_id is not None else 0
    earlier = conn.execute("SELECT COUNT(*) FROM award_snapshots WHERE run_id < ? AND run_id > ?", (run_id, floor)).fetchone()[0]
    if not earlier:
        return f"run {run_id}: no earlier snapshots to diff against"
    parts = [f"Changes in run {run_id} vs earlier runs" + (f" since run {prev_run_id}" if prev_run_id else "")]
    new = conn.execute(
        "SELECT a.award_id, a.recipient_name, s.amount, a.category FROM award_snapshots s JOIN awards a USING (award_key) "
        "WHERE s.run_id=? AND NOT EXISTS (SELECT 1 FROM award_snapshots p WHERE p.award_key=s.award_key AND p.run_id < s.run_id AND p.run_id > ?) "
        "ORDER BY s.amount DESC",
        (run_id, floor),
    ).fetchall()
    parts.append(f"\nNew awards: {len(new)}")
    for r in new[:25]:
        parts.append(f"  {r[0]:<16}{r[1][:36]:<38}{_money(r[2]):>18}  {r[3]}")
    changed = conn.execute(
        "SELECT a.award_id, a.recipient_name, p.amount, c.amount FROM award_snapshots c "
        "JOIN award_snapshots p ON p.award_key=c.award_key AND p.run_id = "
        "  (SELECT MAX(run_id) FROM award_snapshots x WHERE x.award_key=c.award_key AND x.run_id < c.run_id AND x.run_id > ?) "
        "JOIN awards a ON a.award_key=c.award_key WHERE c.run_id=? AND c.amount != p.amount "
        "ORDER BY ABS(c.amount - p.amount) DESC",
        (floor, run_id),
    ).fetchall()
    parts.append(f"\nAmount changes: {len(changed)}")
    for r in changed[:25]:
        delta = r[3] - r[2]
        pct = (delta / r[2] * 100) if r[2] else float("inf")
        parts.append(f"  {r[0]:<16}{r[1][:36]:<38}{_money(r[2]):>18} -> {_money(r[3]):>18}  ({delta:+,.0f}, {pct:+.1f}%)")
    if not new and not changed:
        parts.append("\nno changes")
    return "\n".join(parts)
