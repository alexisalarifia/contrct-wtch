"""All tunables in one place. Override with env vars or a JSON file (CONFIG_JSON=path)."""
import json
import os

DB_PATH = os.environ.get("DB_PATH", "space_contracts.db")
API_BASE = "https://api.usaspending.gov/api/v2"
PAGE_SIZE = 100
MAX_PAGES = int(os.environ.get("MAX_PAGES", "120"))
MAX_RETRIES = 5
WORKERS = int(os.environ.get("WORKERS", "6"))   # concurrent API requests (pages + office lookups)
TIMEOUT = 60
KEEP_ALL = os.environ.get("KEEP_ALL", "0") == "1"           # keep awards that fail the office allowlist
INCLUDE_GRANTS = os.environ.get("INCLUDE_GRANTS", "0") == "1"
INCLUDE_SUBAWARDS = os.environ.get("INCLUDE_SUBAWARDS", "1") == "1"
SUBAWARD_TOP_PRIMES = int(os.environ.get("SUBAWARD_TOP_PRIMES", "50"))
WINDOW_START = os.environ.get("WINDOW_START", "2025-10-01")  # FY26 start
# First run: 1 = only awards that began in the window; 0 (default) = any award with a transaction in it (baseline for change tracking)
NEW_AWARDS_ONLY = os.environ.get("NEW_AWARDS_ONLY", "0") == "1"
WINDOW_END = os.environ.get("WINDOW_END", "2026-12-31")
INCREMENTAL_OVERLAP_DAYS = int(os.environ.get("INCREMENTAL_OVERLAP_DAYS", "7"))  # USAspending posts FPDS data with lag

# Awarding agencies. Space Development Agency is not a subtier; its awards sit under the Air Force.
AGENCIES = [
    {"type": "awarding", "tier": "subtier", "name": "Department of the Air Force"},
    {"type": "awarding", "tier": "toptier", "name": "National Aeronautics and Space Administration"},
    {"type": "awarding", "tier": "subtier", "name": "Missile Defense Agency"},
    {"type": "awarding", "tier": "subtier", "name": "Defense Advanced Research Projects Agency"},
]
CONTRACT_TYPES = ["A", "B", "C", "D"]
GRANT_TYPES = ["02", "03", "04", "05"]

# Source filters. NAICS and PSC are separate requests (filters AND together within one request).
NAICS_CODES = ["336414", "336415", "336419", "517410", "541715"]
PSC_CODES = [["Product", "18"], ["Research and Development"]]

# Codes specific enough to keep an award on their own. Awards matched only by the broad
# R&D codes (NAICS 541715, PSC AC/AJ...) are kept only if the awarding office matches
# OFFICE_ALLOW_RE. Set KEEP_ALL=1 to keep everything the queries return.
SPECIFIC_NAICS = {"336414", "336415", "336419", "517410"}
SPECIFIC_PSC_PREFIXES = ("18", "AR")   # 18xx space vehicles & components; AR = space R&D services

# Matched (case-insensitive) against "<office code> <office name> <sub agency>".
# FA88xx = Space Systems Command, FA25xx = Space Force bases/SSC/Space RCO, FA94xx = AFRL
# Kirtland/Edwards + AFOSR, FA8649/FA8650/FA8750 = AFRL/AFWERX SBIR, HQ08xx = MDA/SDA.
OFFICE_ALLOW_RE = (
    r"AFRL|AFWERX|SPACEWERX|\bSSC\b|\bSDA\b|SPACE|SPC RCO|USSF|SPOC|AFOSR|AEDC|AFNWC|ICBM"
    r"|NASA|NATIONAL AERONAUTICS|MISSILE DEF|\bMDA\b|DARPA|ADVANCED RESEARCH"
    r"|\bFA88\d\d|\bFA25\d\d|\bFA94\d\d|\bFA86(49|50)|\bFA8750|\bHQ08\d\d"
)

# Fields requested from the search endpoint. Sort field must be present.
AWARD_FIELDS = [
    "Award ID", "Recipient Name", "Recipient UEI", "recipient_id", "Description", "Award Amount",
    "Start Date", "End Date", "Last Modified Date", "Awarding Agency", "Awarding Sub Agency",
    "Contract Award Type", "NAICS", "PSC", "Place of Performance State Code", "generated_internal_id",
]
SUBAWARD_FIELDS = [
    "Sub-Award ID", "Sub-Awardee Name", "Sub-Award Amount", "Sub-Award Date",
    "Prime Recipient Name", "Prime Award ID", "prime_award_internal_id",
]

# Multi-label taxonomy, ordered: the first match is the primary tag. Matched against
# description + NAICS description + PSC description, case-insensitive.
TAXONOMY = [
    ("Propulsion", [r"\b(propulsion|rocket (motor|engine)s?|engines?|thrusters?|turbopumps?|solid rocket|liquid rocket|electric propulsion|hall[- ]effect)\b"]),
    ("Launch Services", [r"\b(launch (service|vehicle|provider|mission)s?|nssl|rideshare|launch and early orbit)\b"]),
    ("Guided Missile & Space Vehicle", [r"\b(guided missile|space vehicles?|spacecraft|satellite bus|icbm|sentinel|gbsd|minuteman|strategic deterrent)\b"]),
    ("Human Spaceflight & Exploration", [r"\b(orion|artemis|space launch system|\bsls\b|space station|\biss\b|lunar (lander|gateway|terrain)|human landing|commercial crew|cargo resupply|crew (transport|vehicle)|habitat|exploration upper stage)\b"]),
    ("Hypersonics", [r"\b(hypersonic|scramjet|boost[- ]glide|arrw|hacm)\b"]),
    ("Directed Energy", [r"\b(directed energy|high[- ]energy laser|high[- ]power microwave|laser weapon)\b"]),
    ("EO/IR & RF Sensing", [r"\b(electro[- ]optical|infrared|eo/ir|opir|overhead persistent|radar|synthetic aperture|rf sensing|remote sensing|sensor payload)\b"]),
    ("Electronic Warfare", [r"\b(electronic warfare|jamming|anti[- ]jam|signals intelligence|sigint|spectrum warfare)\b"]),
    ("Space Domain Awareness & Cislunar", [r"\b(space domain awareness|space situational awareness|cislunar|lunar|orbital debris|space surveillance|sda tracking)\b"]),
    ("Satellite Communications", [r"\b(satcom|satellite communications?|optical communications?|laser (link|comm)s?|wideband|protected tactical|milsatcom|gps|pnt|positioning,? navigation)\b"]),
    ("Ground Segment", [r"\b(ground (segment|station|system|control)s?|mission control|telemetry|tt&c|antenna|gateway)\b"]),
    ("In-Space Servicing & Logistics", [r"\b(in[- ]space (servicing|assembly|manufacturing|refuel)|isam|osam|on[- ]orbit (servicing|refuel)|space logistics|isru)\b"]),
    ("Advanced Materials & Manufacturing", [r"\b(inconel|titanium|carbon (composite|fiber)s?|ablative|superalloys?|3d[- ]?print\w*|additive(ly)? manufactur\w*|thermal protection)\b"]),
    ("Avionics & Compute", [r"\b(rad[- ]hard|radiation[- ]hardened|fpgas?|flight software|autonomous navigation|avionics|onboard processing|edge computing|guidance,? navigation)\b"]),
    ("Nuclear & Thermal", [r"\b(nuclear thermal|nuclear electric|fission|radioisotope|rtg|draco)\b"]),
    ("Satellite & Orbital (general)", [r"\b(satellites?|orbital|on[- ]orbit|constellation|tranche|proliferated|leo|geo)\b"]),
    ("Missile Defense", [r"\b(missile defense|interceptors?|ballistic missile|glide phase|ngi|thaad|aegis|layered defense|shield\)|golden dome|homeland defense|missile warning|missile track)\b"]),
    ("Autonomy & AI", [r"\b(artificial intelligence|machine learning|ai/ml|agentic|autonomous|autonomy|swarm|neural|large language)\b"]),
    ("Cyber & Networks", [r"\b(cyber\w*|zero trust|network security|cryptograph\w*|encryption|resilient network)\b"]),
    ("Unmanned Systems", [r"\b(unmanned|uas|uav|drone|tilt[- ]rotor|collaborative combat|loyal wingman)\b"]),
    ("Test & Range Infrastructure", [r"\b(test (range|complex|facility|infrastructure)|range control|wind tunnel|test and training|aedc|arnold engineering)\b"]),
    ("Research & Development (general)", [r"\b(research and development|r&d|basic research|applied research|sbir|sttr|phase (i|ii|iii)\b|prototype)\b"]),
]
# Funding lane derived from NAICS/PSC codes, independent of description text. First match wins.
LANES = [
    ("Space vehicles & parts (NAICS 3364xx)", {"naics": ("336414", "336415", "336419")}),
    ("Satellite telecom (NAICS 517410)", {"naics": ("517410",)}),
    ("Space vehicles & components (PSC 18xx)", {"psc": ("18",)}),
    ("Space R&D services (PSC AR)", {"psc": ("AR",)}),
    ("Defense R&D services (PSC AC)", {"psc": ("AC",)}),
    ("Science & technology R&D (PSC AJ)", {"psc": ("AJ",)}),
    ("Other R&D services (PSC A*)", {"psc": ("A",)}),
    ("Engineering & technical support (PSC R4)", {"psc": ("R4",)}),
    ("Physical sciences R&D (NAICS 541715)", {"naics": ("541715",)}),
]

# Command/organization derived from office code + name + sub agency. First match wins.
# USAspending has no Space Force subtier, so this is how Space Force gets broken out.
COMMANDS = [
    ("Space Force / SDA", r"\bHQ0850|SPACE DEV(ELOPMENT)? AGENCY|\bFA2401"),   # not "SDA AND COMBAT POWER", that is SSC
    ("Space Force / SSC", r"\bFA88\d\d|\bSSC\b|SPACE SYSTEMS"),
    ("Space Force / Space RCO", r"SPC RCO|SPACE RCO|RAPID CAP"),
    ("Space Force / other", r"\bFA25\d\d|USSF|SPOC|SPACE FORCE|SPACE LAUNCH DELTA|\bSLD\b"),
    ("AFRL / AFWERX / SBIR", r"AFRL|AFWERX|SPACEWERX|SBIR|\bFA86(49|50)|\bFA8750|\bFA94(5\d|51|53)"),
    ("AFOSR", r"AFOSR|\bFA9550"),
    ("AFNWC (nuclear/ICBM)", r"AFNWC|ICBM|\bFA82(19|99)"),
    ("AFTC / AEDC (test)", r"AFTC|AEDC|ARNOLD|\bFA93\d\d|\bFA91\d\d"),
    ("AFLCMC", r"AFLCMC|\bFA8[567]\d\d"),
    ("MDA", r"MISSILE DEF|\bMDA\b|\bHQ0147"),
    ("DARPA", r"DARPA|ADVANCED RESEARCH PROJECTS|\bHR00"),
    ("NASA", r"NASA|NATIONAL AERONAUTICS|^80|^NN|^NAS"),
]

# Generic tags are matched on the award description only, never on NAICS/PSC text,
# otherwise every R&D-coded award gets tagged R&D.
GENERAL_TAGS = {"Satellite & Orbital (general)", "Research & Development (general)"}
TAG_NAMES = [t for t, _ in TAXONOMY] + ["Uncategorized"]

# SBIR / SAM (optional sources)
SBIR_ENABLED = os.environ.get("SBIR_ENABLED", "0") == "1"
SBIR_KEYWORDS = os.environ.get("SBIR_KEYWORDS", "satellite,spacecraft,propulsion,launch,orbit").split(",")
SAM_API_KEY = os.environ.get("SAM_API_KEY")
SAM_NAICS = NAICS_CODES


def _apply_overrides():
    path = os.environ.get("CONFIG_JSON")
    if not path:
        return
    with open(path) as fh:
        for key, val in json.load(fh).items():
            if key.isupper():
                globals()[key] = val


_apply_overrides()
