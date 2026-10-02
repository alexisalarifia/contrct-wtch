"""Orchestrates a run: fetch -> office lookup -> tag -> upsert -> snapshots -> verify."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from . import config, db, taxonomy, usaspending as usa, verify

log = logging.getLogger("tracker.runner")
OFFICE_RE = re.compile(config.OFFICE_ALLOW_RE, re.I)


def _base_filters(award_types, tp):
    return {"agencies": config.AGENCIES, "award_type_codes": award_types, "time_period": tp}


def _time_period(conn):
    """First run: new awards in the window. Later runs: anything modified since the last good run."""
    last = db.last_successful_run(conn, source="usaspending")
    if last and last["finished"]:
        since = datetime.strptime(last["finished"], "%Y-%m-%d %H:%M:%S") - timedelta(days=config.INCREMENTAL_OVERLAP_DAYS)
        log.info("incremental: awards modified since %s", since.date())
        return usa.time_period(since.strftime("%Y-%m-%d"), config.WINDOW_END, "last_modified_date"), True
    mode = "new_awards_only" if config.NEW_AWARDS_ONLY else None
    log.info("first run: %s %s..%s", "new awards" if mode else "awards with activity", config.WINDOW_START, config.WINDOW_END)
    return usa.time_period(config.WINDOW_START, config.WINDOW_END, mode), False


def fetch_awards(conn):
    """Union of the NAICS-filtered and PSC-filtered queries. Marks which awards matched a code filter."""
    tp, incremental = _time_period(conn)
    seen = {}
    queries = [
        ("naics", {**_base_filters(config.CONTRACT_TYPES, tp), "naics_codes": {"require": config.NAICS_CODES}}),
        ("psc", {**_base_filters(config.CONTRACT_TYPES, tp), "psc_codes": {"require": config.PSC_CODES}}),
    ]
    if config.INCLUDE_GRANTS:
        queries.append(("grants", _base_filters(config.GRANT_TYPES, tp)))
    def one(q):
        label, filters = q
        total = usa.count_awards(filters)
        items = list(usa.search_awards(filters, total=total))
        keys = {i.get("generated_internal_id") for i in items}
        log.info("query %s: %d of %d awards fetched (%d unique)%s", label, len(items), total, len(keys),
                 "" if len(keys) >= total else " (short: paging drift or MAX_PAGES; next run catches up)")
        return items
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        for items in pool.map(one, queries):
            for item in items:
                a = usa.normalize_award(item)
                seen.setdefault(a["award_key"], a)
    return list(seen.values()), incremental


def specific_code(a):
    naics = a.get("naics") or ""
    psc = a.get("psc") or ""
    return naics in config.SPECIFIC_NAICS or psc.startswith(config.SPECIFIC_PSC_PREFIXES)


def _prefix(a):
    return (a.get("award_id") or "")[:6]


def resolve_offices(conn, awards):
    """Office (code, name) per PIID prefix: from the offices cache, else one detail call per
    unseen prefix, fetched concurrently. Returns {prefix: (code, name)}."""
    cache = {}
    sample = {}
    for a in awards:
        if a.get("source", "usaspending") != "usaspending":
            continue
        pfx = _prefix(a)
        if pfx in cache or pfx in sample:
            continue
        row = db.get_office(conn, pfx)
        if row:
            cache[pfx] = (row["code"], row["name"])
        else:
            sample[pfx] = a["award_key"]

    def one(item):
        pfx, key = item
        try:
            return pfx, usa.office_for(key)
        except Exception as exc:  # noqa: BLE001
            log.warning("office lookup failed for %s: %s", key, exc)
            return pfx, (None, None)
    if sample:
        log.info("resolving %d new office prefixes", len(sample))
        with ThreadPoolExecutor(max_workers=config.WORKERS) as pool:
            for pfx, (code, name) in pool.map(one, sample.items()):
                db.put_office(conn, pfx, code, name)
                cache[pfx] = (code, name)
        conn.commit()
    return cache


def keep(a):
    if config.KEEP_ALL or a.get("source", "usaspending") != "usaspending" or specific_code(a):
        return True
    hay = " ".join(str(a.get(k) or "") for k in ("office_code", "office_name", "sub_agency"))
    return bool(OFFICE_RE.search(hay))


def load_awards(conn, awards, run_id):
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "dropped": 0}
    offices = resolve_offices(conn, awards)
    for a in awards:
        if a.get("source", "usaspending") == "usaspending":
            a["office_code"], a["office_name"] = offices.get(_prefix(a), (None, None))
        if not keep(a):
            counts["dropped"] += 1
            continue
        a["category"], tags = taxonomy.tag_award(a)
        a["lane"] = taxonomy.lane_for(a)
        a["command"] = taxonomy.command_for(a)
        counts[db.upsert_award(conn, a, tags, run_id)] += 1
    conn.commit()
    return counts


def fetch_subawards(conn, run_id):
    if not config.INCLUDE_SUBAWARDS:
        return 0
    primes = [r["award_id"] for r in conn.execute(
        "SELECT award_id FROM awards WHERE source='usaspending' ORDER BY amount DESC LIMIT ?", (config.SUBAWARD_TOP_PRIMES,))]
    if not primes:
        return 0
    filters = {
        "agencies": config.AGENCIES, "award_type_codes": config.CONTRACT_TYPES,
        "time_period": usa.time_period(config.WINDOW_START, config.WINDOW_END),
        "award_ids": primes,
    }
    n = 0
    try:
        for item in usa.search_subawards(filters, max_pages=20):
            db.upsert_subaward(conn, usa.normalize_subaward(item), run_id)
            n += 1
    except Exception as exc:  # noqa: BLE001
        log.warning("subaward fetch failed: %s", exc)
    conn.commit()
    log.info("subawards: %d", n)
    return n


def run(sources=("usaspending",)):
    conn = db.connect()
    rc = 0
    for source in sources:
        run_id = db.start_run(conn, source)
        try:
            if source == "usaspending":
                awards, _ = fetch_awards(conn)
            elif source == "sbir":
                from sources import sbir
                awards = sbir.fetch()
            elif source == "sam":
                from sources import sam
                opps = sam.fetch()
                for o in opps:
                    db.upsert_opportunity(conn, o, run_id)
                conn.commit()
                db.finish_run(conn, run_id, fetched=len(opps), inserted=len(opps), updated=0, dropped=0, ok=1)
                log.info("sam: %d opportunities stored", len(opps))
                continue
            else:
                raise ValueError(f"unknown source {source}")
            log.info("%s: fetched %d awards", source, len(awards))
            counts = load_awards(conn, awards, run_id)
            log.info("%s: %s", source, counts)
            if source == "usaspending":
                fetch_subawards(conn, run_id)
            ok, _ = verify.verify(conn, run_id, len(awards), counts["inserted"], counts["updated"])
            db.finish_run(conn, run_id, fetched=len(awards), inserted=counts["inserted"], updated=counts["updated"], dropped=counts["dropped"], ok=int(ok))
            rc |= 0 if ok else 1
        except Exception as exc:  # noqa: BLE001
            log.exception("%s run failed: %s", source, exc)
            db.finish_run(conn, run_id, fetched=0, inserted=0, updated=0, dropped=0, ok=0)
            rc |= 2
    conn.close()
    log.info("done. database: %s", config.DB_PATH)
    return rc


def retag():
    """Re-run the tagger and lane over every stored award. No network. Use after editing config.TAXONOMY."""
    conn = db.connect()
    rows = conn.execute("SELECT award_key, description, naics, naics_desc, psc, psc_desc, office_code, office_name, award_id, sub_agency FROM awards").fetchall()
    changed = 0
    for r in rows:
        a = dict(r)
        primary, tags = taxonomy.tag_award(a)
        lane = taxonomy.lane_for(a)
        cmd = taxonomy.command_for(a)
        old = conn.execute("SELECT category, lane, command FROM awards WHERE award_key=?", (a["award_key"],)).fetchone()
        conn.execute("UPDATE awards SET category=?, lane=?, command=? WHERE award_key=?", (primary, lane, cmd, a["award_key"]))
        conn.execute("DELETE FROM award_tags WHERE award_key=?", (a["award_key"],))
        conn.executemany("INSERT OR IGNORE INTO award_tags (award_key, tag) VALUES (?, ?)", [(a["award_key"], t) for t in tags])
        if (old["category"], old["lane"], old["command"]) != (primary, lane, cmd):
            changed += 1
    conn.commit()
    conn.close()
    log.info("retagged %d awards, %d changed category or lane", len(rows), changed)
    return 0
