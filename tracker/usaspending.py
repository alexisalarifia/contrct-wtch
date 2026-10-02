"""USAspending v2 client: backoff, paging, award search, award detail, subawards."""
import logging
import time

import requests

from . import config

log = logging.getLogger("tracker.usaspending")
SEARCH = config.API_BASE + "/search/spending_by_award/"
_session = requests.Session()
_session.headers["User-Agent"] = "contrct-wtch/0.2 (+https://github.com/alexisalarifia/contrct-wtch)"


def _request(method, url, **kw):
    """Exponential backoff on network errors, 429 and 5xx. Honors Retry-After."""
    delay = 2
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = _session.request(method, url, timeout=config.TIMEOUT, **kw)
        except requests.exceptions.RequestException as exc:
            log.warning("attempt %d/%d network error: %s", attempt, config.MAX_RETRIES, exc)
        else:
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                ra = resp.headers.get("Retry-After")
                wait = int(ra) if ra and ra.isdigit() else delay
                log.warning("attempt %d/%d HTTP %s, retry in %ss", attempt, config.MAX_RETRIES, resp.status_code, wait)
                time.sleep(wait)
                delay *= 2
                continue
            raise RuntimeError(f"HTTP {resp.status_code} from {url}: {resp.text[:300]}")
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"USAspending API failed after {config.MAX_RETRIES} attempts: {url}")


def _paged(payload, max_pages=None):
    max_pages = max_pages or config.MAX_PAGES
    for page in range(1, max_pages + 1):
        data = _request("POST", SEARCH, json={**payload, "page": page})
        results = data.get("results", [])
        yield from results
        if not data.get("page_metadata", {}).get("hasNext") or not results:
            return
    log.warning("hit MAX_PAGES=%d, results truncated", max_pages)


def time_period(start, end, date_type=None):
    tp = {"start_date": start, "end_date": end}
    if date_type:
        tp["date_type"] = date_type
    return [tp]


def search_awards(filters, fields=None, sort="Award Amount", max_pages=None):
    fields = list(fields or config.AWARD_FIELDS)
    if sort not in fields:
        fields.append(sort)
    payload = {"filters": filters, "fields": fields, "limit": config.PAGE_SIZE, "sort": sort, "order": "desc"}
    return _paged(payload, max_pages)


def count_awards(filters, bucket="contracts"):
    """Total matching awards via the count endpoint (search pages don't report totals)."""
    try:
        d = _request("POST", config.API_BASE + "/search/spending_by_award_count/", json={"filters": filters})
        return int((d.get("results") or {}).get(bucket) or 0)
    except Exception as exc:  # noqa: BLE001
        log.warning("count endpoint failed: %s", exc)
        return -1


def search_subawards(filters, max_pages=None):
    payload = {
        "filters": filters, "fields": config.SUBAWARD_FIELDS, "limit": config.PAGE_SIZE,
        "sort": "Sub-Award Amount", "order": "desc", "subawards": True,
    }
    return _paged(payload, max_pages)


def award_detail(generated_internal_id):
    return _request("GET", f"{config.API_BASE}/awards/{generated_internal_id}/")


def office_for(generated_internal_id):
    """Awarding office (code, name) from the detail endpoint; search endpoint returns null."""
    d = award_detail(generated_internal_id)
    ag = d.get("awarding_agency") or {}
    name = ag.get("office_agency_name") or ""
    code = name.split()[0] if name else None
    return code, name.strip()


def normalize_award(item, source="usaspending"):
    naics = item.get("NAICS") or {}
    psc = item.get("PSC") or {}
    return {
        "award_key": item.get("generated_internal_id") or item.get("Award ID"),
        "award_id": item.get("Award ID") or "UNKNOWN",
        "recipient_name": item.get("Recipient Name") or "UNKNOWN",
        "uei": item.get("Recipient UEI"),
        "recipient_id": item.get("recipient_id"),
        "agency": item.get("Awarding Agency"),
        "sub_agency": item.get("Awarding Sub Agency"),
        "award_type": item.get("Contract Award Type"),
        "amount": float(item.get("Award Amount") or 0.0),
        "start_date": item.get("Start Date"),
        "end_date": item.get("End Date"),
        "last_modified": item.get("Last Modified Date"),
        "description": item.get("Description") or "",
        "naics": naics.get("code") if isinstance(naics, dict) else naics,
        "naics_desc": naics.get("description") if isinstance(naics, dict) else None,
        "psc": psc.get("code") if isinstance(psc, dict) else psc,
        "psc_desc": psc.get("description") if isinstance(psc, dict) else None,
        "pop_state": item.get("Place of Performance State Code"),
        "source": source,
    }


def normalize_subaward(item):
    return {
        "sub_id": item.get("Sub-Award ID") or item.get("internal_id"),
        "prime_award_internal_id": item.get("prime_award_internal_id"),
        "prime_award_id": item.get("Prime Award ID"),
        "prime_recipient": item.get("Prime Recipient Name"),
        "sub_awardee": item.get("Sub-Awardee Name"),
        "amount": float(item.get("Sub-Award Amount") or 0.0),
        "date": item.get("Sub-Award Date"),
    }
