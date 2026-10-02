# contrct-wtch
Watch em ! 

## Space & defense contract tracker

Pulls Department of the Air Force contract awards from the USAspending API,
tags each with a NewSpace capability category, and loads them into
`space_contracts.db` (SQLite). Re-runs skip awards already stored.

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python pipeline.py            # MAX_PAGES=10 by default (100 awards/page)
```

Summary query:

```
sqlite3 space_contracts.db "SELECT category, COUNT(*), SUM(amount) FROM awards GROUP BY 1 ORDER BY 2 DESC"
sqlite3 space_contracts.db "SELECT award_id, recipient_name, amount FROM awards ORDER BY amount DESC LIMIT 3"
```
