"""SAM.gov contract opportunities (solicitations, sources sought). Needs SAM_API_KEY (free at api.sam.gov).

Returns normalized opportunity dicts; [] with a warning on any failure.
"""
import logging
from datetime import date, timedelta

import requests

from tracker import config

log = logging.getLogger("sources.sam")
URL = "https://api.sam.gov/opportunities/v2/search"
NOTICE_TYPES = "o,k,r,p"  # solicitation, combined synopsis, sources sought, presolicitation


def normalize(item):
    return {
        "notice_id": item.get("noticeId"),
        "title": item.get("title"),
        "agency": item.get("department") or item.get("fullParentPathName", "").split(".")[0],
        "office": item.get("office") or item.get("fullParentPathName"),
        "notice_type": item.get("type"),
        "posted": item.get("postedDate"),
        "deadline": item.get("responseDeadLine"),
        "naics": item.get("naicsCode"),
        "psc": item.get("classificationCode"),
        "url": item.get("uiLink"),
    }


def fetch(api_key=None, posted_from=None, posted_to=None, naics=None, limit=100, max_pages=10, session=None):
    api_key = api_key or config.SAM_API_KEY
    if not api_key:
        log.info("SAM_API_KEY not set, skipping SAM.gov")
        return []
    s = session or requests.Session()
    posted_to = posted_to or date.today()
    posted_from = posted_from or (posted_to - timedelta(days=30))
    fmt = lambda d: d.strftime("%m/%d/%Y") if hasattr(d, "strftime") else d
    out = []
    for code in naics or config.SAM_NAICS:
        for page in range(max_pages):
            params = {
                "api_key": api_key, "limit": limit, "offset": page * limit, "ptype": NOTICE_TYPES,
                "postedFrom": fmt(posted_from), "postedTo": fmt(posted_to), "ncode": code,
            }
            try:
                r = s.get(URL, params=params, timeout=config.TIMEOUT)
            except requests.exceptions.RequestException as exc:
                log.warning("sam.gov network error: %s", exc)
                return out
            if r.status_code != 200:
                log.warning("sam.gov HTTP %s for NAICS %s: %s", r.status_code, code, r.text[:200])
                return out
            data = r.json()
            items = data.get("opportunitiesData") or []
            out.extend(normalize(i) for i in items if i.get("noticeId"))
            if len(items) < limit:
                break
    log.info("sam.gov: %d opportunities", len(out))
    return out
