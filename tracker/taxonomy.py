"""Multi-label capability tagger. Ordered taxonomy; first match is the primary tag."""
import re

from . import config

_COMMANDS = [(n, re.compile(rx, re.I)) for n, rx in config.COMMANDS]
_COMPILED = [(tag, [re.compile(p, re.I) for p in pats]) for tag, pats in config.TAXONOMY]


def tag_text(text):
    """Return every matching tag in taxonomy order. Empty list when nothing matches."""
    if not text:
        return []
    return [tag for tag, pats in _COMPILED if any(p.search(text) for p in pats)]


def tag_award(award):
    """Specific tags over description + NAICS + PSC descriptions; generic tags over the
    description only. Returns (primary, [tags]) in taxonomy order."""
    desc = award.get("description") or ""
    full = " | ".join(p for p in [desc, award.get("naics_desc"), award.get("psc_desc")] if p)
    from_full = set(tag_text(full)) - config.GENERAL_TAGS
    from_desc = set(tag_text(desc)) & config.GENERAL_TAGS
    chosen = from_full | from_desc
    tags = [t for t, _ in config.TAXONOMY if t in chosen]
    primary = tags[0] if tags else "Uncategorized"
    return primary, tags or ["Uncategorized"]


def categorize_abstract(text):
    """Backward-compatible single-label helper."""
    tags = tag_text(text)
    return tags[0] if tags else "Uncategorized"


def lane_for(award):
    naics = award.get("naics") or ""
    psc = award.get("psc") or ""
    for name, rule in config.LANES:
        if naics in rule.get("naics", ()) or (psc and psc.startswith(rule.get("psc", ("\0",)))):
            return name
    return "Other"


def command_for(award):
    hay = " ".join(str(award.get(k) or "") for k in ("office_code", "office_name", "award_id", "sub_agency"))
    for name, rx in _COMMANDS:
        if rx.search(hay):
            return name
    return award.get("sub_agency") or "Other"
