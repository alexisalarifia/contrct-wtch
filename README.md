# contrct-wtch

Watch em !

A tracker for US space and defense contract awards. Pulls from the USAspending API,
keeps a SQLite database that updates in place, tags each award with capability
categories and a funding lane, and reports what changed between runs.

## Quick start

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python pipeline.py run          # first run: FY26 baseline, ~20 s, ~9k awards (WORKERS=6 concurrent requests)
python pipeline.py summary      # commands, tags, lanes, programs, top awards, recipients, offices
python pipeline.py summary --command "Space Force"   # SSC, SDA, Space RCO and other Space Force offices only
python pipeline.py run          # later: only awards modified since the last run
python pipeline.py diff         # new awards and amount changes since the previous run
python pipeline.py retag        # re-apply edited taxonomy to stored awards, no network
python pipeline.py report       # writes report.html; open it in any browser
```

`report.html` is a single self-contained file: tiles, obligated dollars by command and
by capability tag, what changed since the previous run, a searchable award table with
command filters, top recipients and programs. Nothing is hosted; share the file if you
want someone else to see it.

Database: `space_contracts.db` (override with `DB_PATH`). No external tools needed;
`sqlite3` is optional.

## What it pulls

Contract awards (types A-D) from the Department of the Air Force (which includes Space
Force, Space Systems Command, Space Development Agency, AFRL and AFWERX/SpaceWERX), NASA,
the Missile Defense Agency and DARPA, in two server-side filtered queries:

- NAICS 336414, 336415, 336419 (guided missile & space vehicles), 517410 (satellite
  telecom), 541715 (physical sciences R&D)
- PSC 18xx (space vehicles & components) and all R&D service codes

Awards matched only by the broad R&D codes are kept only when the awarding office is on
the allowlist (AFRL, SSC, SDA, Space Force, AFNWC, AEDC, NASA, MDA, DARPA, ...). The
office comes from the award detail endpoint, since the search endpoint returns it empty,
and is cached per contracting-office prefix in the `offices` table. `KEEP_ALL=1`
disables the allowlist.

First run: every matching award with a transaction since `WINDOW_START` (default
2025-10-01, FY26). Set `NEW_AWARDS_ONLY=1` to restrict to awards that started in the
window. Later runs: anything modified since the last successful run, minus a 7-day
overlap. Each run snapshots every fetched award's amount in `award_snapshots`, which is
what `diff` reads.

Subawards for the top 50 primes land in `subawards` (`INCLUDE_SUBAWARDS=0` to skip).
Grants (NASA, AFOSR) with `INCLUDE_GRANTS=1`.

## Space Force

USAspending has no Space Force sub-agency; its awards sit under the Department of the Air
Force. The tracker derives a `command` column from the contracting office (FA88xx = Space
Systems Command, HQ0850 = Space Development Agency, FA25xx = Space Force bases and Space
RCO, plus AFRL, AFNWC, AFTC/AEDC, AFLCMC, NASA, MDA, DARPA). `summary --command 'Space
Force'` restricts every table to it. Rules live in `COMMANDS` in `tracker/config.py`.

## Tagging

`tracker/config.py` holds two taggers you can edit without touching code:

- `TAXONOMY`: ordered regex capability tags (Propulsion, Launch Services, Missile
  Defense, Hypersonics, Satellite Communications, Human Spaceflight, Autonomy & AI, ...).
  Multi-label: every match is stored in `award_tags`; the first is the `category`.
  Specific tags match on description + NAICS + PSC text; the two "(general)" tags match
  on the description only.
- `LANES`: a single funding lane from NAICS/PSC codes, stored in `lane`.

Descriptions in USAspending are one-line contract titles, so expect a large
Uncategorized bucket. The MDA SHIELD IDIQ alone contributes ~2,400 identical awards.

## Scheduled runs

`.github/workflows/watch.yml` runs the pipeline every Monday (and on demand from the
Actions tab). The database is carried between runs in the Actions cache, so each run's
job summary page shows the diff since the previous week plus the full and Space Force
summaries, and the database and `report.html` are attached as artifacts. Add a `SAM_API_KEY` repository
secret to include SAM.gov opportunities. `ci.yml` runs the tests on every push.

## Optional sources

- SBIR.gov award abstracts: `python pipeline.py run --source sbir` (set
  `SBIR_ENABLED=1`, `SBIR_KEYWORDS=satellite,propulsion`). Rows get `source='sbir'`.
- SAM.gov opportunities (solicitations, sources sought): `python pipeline.py run
  --source sam` with a free key in `SAM_API_KEY`. Rows land in `opportunities`.

Both APIs block some cloud IP ranges; run them from your own machine. Both fail soft.

## Config

Every knob is an env var or a JSON file via `CONFIG_JSON=path` whose uppercase keys
override `tracker/config.py`. Main ones: `DB_PATH`, `MAX_PAGES` (100 awards per page),
`WINDOW_START`, `WINDOW_END`, `NEW_AWARDS_ONLY`, `KEEP_ALL`, `INCLUDE_GRANTS`,
`INCLUDE_SUBAWARDS`, `SUBAWARD_TOP_PRIMES`, `SBIR_ENABLED`, `SAM_API_KEY`.

## Layout

```
pipeline.py            CLI: run | summary | diff | retag | report
tracker/html.py        report.html generator (template in tracker/templates/)
tracker/config.py      agencies, codes, allowlist, taxonomy, lanes
tracker/usaspending.py API client: backoff, paging, counts, award detail, subawards
tracker/db.py          schema + v1 migration, upsert, snapshots, office cache
tracker/taxonomy.py    multi-label tagger and lane
tracker/runner.py      fetch -> office -> keep -> tag -> upsert -> verify
tracker/report.py      summary and diff
sources/sbir.py        SBIR.gov
sources/sam.py         SAM.gov
tests/                 offline tests: python -m pytest tests
```

## Verification

Each run checks row counts, empty keys, unknown categories, untagged awards and that
snapshots were written, and records the result in `runs.ok`. Exit code is non-zero
when a check fails.
