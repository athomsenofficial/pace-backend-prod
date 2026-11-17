"""
Recurring-roster parameter values — the ONE place regulatory numbers live.

Changes when: a DAFI/AFI value is confirmed (fill in `value` AND replace the
`citation` with the exact paragraph/table), or a user-preference default changes.

HARD RULE: never invent regulatory numbers. Every entry in REGULATORY_VALUES
stays `None` until someone confirms it against the current publication and
records the citation. A roster rule whose required parameter resolves to None
refuses to run (HTTP 422) rather than guessing.
"""

PENDING_CITATION = "DAFI 36-2110 — values pending confirmation"

# ----------------------------------------------------------------------------
# Regulatory values (AFI/DAFI-derived). value=None => caller must supply it.
# ----------------------------------------------------------------------------
REGULATORY_VALUES = {
    # deros-retainability
    "deros.window_close_months_before_deros": {"value": None, "citation": PENDING_CITATION},
    "deros.required_retainability_months": {"value": None, "citation": PENDING_CITATION},
    # assignment-retainability
    "assignment.required_retainability_months": {"value": None, "citation": PENDING_CITATION},
    # time-on-station
    "time_on_station.tour_length_months": {"value": None, "citation": PENDING_CITATION},
}

# Per-assignment-type retainability (months), keyed by the upper-cased value of
# the roster's ASSIGNMENT_TYPE column. Intentionally EMPTY until confirmed —
# add entries like {"<TYPE>": <months>} only with a citation in the comment.
ASSIGNMENT_RETAINABILITY_BY_TYPE: dict[str, int] = {}
ASSIGNMENT_RETAINABILITY_BY_TYPE_CITATION = PENDING_CITATION

# ----------------------------------------------------------------------------
# User-preference defaults (NOT regulation) — lookahead windows only.
# ----------------------------------------------------------------------------
PREFERENCE_DEFAULTS = {
    "deros.lookahead_days": 90,
    "dos_window.months": 12,
    "hyt.months": 12,
    "uif.days": 30,
    "time_on_station.days": 120,
}

# ----------------------------------------------------------------------------
# Grade spellings seen in roster exports -> PACE grade codes (config/domain.py).
# Data normalisation only; no policy values here.
# ----------------------------------------------------------------------------
GRADE_ALIASES = {
    "AB": "AB", "AMN": "AMN", "A1C": "A1C", "SRA": "SRA",
    "SSG": "SSG", "SSGT": "SSG", "TSG": "TSG", "TSGT": "TSG",
    "MSG": "MSG", "MSGT": "MSG", "SMS": "SMS", "SMSGT": "SMS",
    "CMS": "CMS", "CMSGT": "CMS",
    "E1": "AB", "E2": "AMN", "E3": "A1C", "E4": "SRA", "E5": "SSG",
    "E6": "TSG", "E7": "MSG", "E8": "SMS", "E9": "CMS",
}


def regulatory_default(key: str):
    return REGULATORY_VALUES[key]["value"]


def regulatory_citation(key: str):
    return REGULATORY_VALUES[key]["citation"]
