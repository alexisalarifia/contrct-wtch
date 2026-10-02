"""SBIR.gov award abstracts. Returns normalized award dicts with source='sbir'.

The API is behind a WAF that blocks some datacenter IPs (403). On any failure this returns []
and logs a warning so the main pipeline keeps going. Enable with SBIR_ENABLED=1.
"""
import logging

import requests

from tracker import config

log = logging.getLogger("sources.sbir")
URL = "https://api.www.sbir.gov/public/api/awards"


def normalize(item):
    contract = item.get("contract") or item.get("contract_number") or ""
    agency = item.get("agency") or ""
    key = f"SBIR_{agency}_{contract or item.get('award_title', '')[:40]}_{item.get('award_year', '')}"
    return {
        "award_key": key.replace(" ", "_"),
        "award_id": contract or key,
        "recipient_name": item.get("firm") or "UNKNOWN",
        "uei": item.get("uei"),
        "recipient_id": None,
        "agency": agency,
        "sub_agency": item.get("branch"),
        "award_type": f"SBIR {item.get('program', '')} Phase {item.get('phase', '')}".strip(),
        "amount": float(item.get("award_amount") or 0.0),
        "start_date": item.get("proposal_award_date") or (f"{item['award_year']}-01-01" if item.get("award_year") else None),
        "end_date": item.get("contract_end_date"),
        "last_modified": None,
        "description": " ".join(x for x in [item.get("award_title"), item.get("abstract")] if x),
        "naics": None, "naics_desc": None, "psc": None, "psc_desc": None,
        "pop_state": item.get("state"),
        "source": "sbir",
    }


def fetch(keywords=None, agency="DOD", rows=100, max_pages=10, session=None):
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", "Mozilla/5.0 contrct-wtch/0.2")
    out = []
    for kw in keywords or config.SBIR_KEYWORDS:
        for page in range(max_pages):
            try:
                r = s.get(URL, params={"agency": agency, "keyword": kw, "rows": rows, "start": page * rows}, timeout=config.TIMEOUT)
            except requests.exceptions.RequestException as exc:
                log.warning("sbir.gov network error: %s", exc)
                return out
            if r.status_code != 200:
                log.warning("sbir.gov HTTP %s for keyword %r (API blocks some IPs; run from your own machine)", r.status_code, kw)
                return out
            data = r.json()
            items = data if isinstance(data, list) else data.get("results") or data.get("awards") or []
            if not items:
                break
            out.extend(normalize(i) for i in items)
            if len(items) < rows:
                break
    log.info("sbir.gov: %d awards", len(out))
    return out
