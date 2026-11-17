"""
Retention and BTZ roster runs — every window, threshold and code map.

Runs served (one alpha-roster upload per session, see routers/roster_runs.py):
  1. DOS / Reenlistment Decision Roster      (DAFI 36-2606)
  2. DEROS Option Roster                     (DAFI 36-2110)
  3. RE Code Management Roster               (DAFI 36-2606)
  4. SrA BTZ Quarterly Eligibility Roster    (DAFI 36-2502)

Changes when: the owner confirms (or corrects) a value against the CURRENT
publication. Every value below came from the owner's spec text
(docs/specs/01-retention-runs-spec.md, docs/specs/02-btz-quarterly-spec.md) or
the owner's decisions (docs/specs/00-decisions-and-data.md). NONE has been
checked against the publication by PACE — each carries a citation AND the
VERIFY note. Change the value here only; the run code reads nothing else.

Deliberately separate from config/domain.py RE_CODES, which the MEL uses and
must not change.
"""

VERIFY = "Verify against the current publication."
LOCAL_PREFERENCE = "Local preference (not a regulatory value)."

PUB_REENLISTMENT = "DAFI 36-2606"
PUB_ASSIGNMENTS = "DAFI 36-2110"
PUB_PROMOTIONS = "DAFI 36-2502 (spec cites AFI 36-2502, 26 Sep 2024)"

# =============================================================================
# Footers — exact text from each spec
# =============================================================================
RETENTION_FOOTER = (
    "Screening aid only. MPF and commander determine eligibility per DAFI 36-2606 and DAFI 36-2110."
)
BTZ_FOOTER = "Screening aid only. MPF verifies eligibility and quotas per AFI 36-2502."

# =============================================================================
# Data conventions of the alpha-roster export (owner, 00-decisions)
# =============================================================================
# Year 3888 marks an indefinite date (officers' DOS, some TSG-CMS ETS/DOS).
# Any year at or above this threshold = "indefinite", never a real date and
# never a DATA ISSUE. Indefinite DEROS: blank or year >= threshold.
INDEFINITE_YEAR_THRESHOLD = 3000
# UIF_CODE values that mean "no UIF". Spec 1: "any UIF code = REVIEW".
# NOTE: the MEL (board_filter) only treats codes > 1 as an issue; these runs
# follow the owner's spec and treat every non-blank, non-zero code as a UIF.
UIF_NONE_VALUES = ("", "0")

# =============================================================================
# RUN 1 — DOS / Reenlistment Decision
# =============================================================================
# Spec 1 Run 1: "DOS within DOS_WINDOW_MONTHS (default 12)". Local preference.
DOS_WINDOW_MONTHS = 12
# Spec 1 Run 1: action-by date = DOS minus 120 days ("reenlistment must be
# projected with the MPF by then or the member is projected for separation").
# DAFI 36-2606 — paragraph not given in the owner's spec. VERIFY.
REENLISTMENT_ACTION_DAYS_BEFORE_DOS = 120
# Spec 1: "Show remaining months under the 48-month per-enlistment extension
# cap (Chapter 6)". DAFI 36-2606 Chapter 6. VERIFY.
EXTENSION_CAP_MONTHS = 48
# Spec 1: first-term CJR window is months 35-43 of a 4-year enlistment or
# 59-67 of a 6-year enlistment. DAFI 36-2606 Table 3.1. VERIFY.
CJR_WINDOWS_BY_TERM_MONTHS = {48: (35, 43), 72: (59, 67)}
# Spec 1: "a CJR is required to reenlist" (first-term) — DAFI 36-2606 para 3.1.1.
CJR_REQUIRED_CITATION = "DAFI 36-2606 para 3.1.1"
# Spec 1: "A UIF blocks a CJR for first-termers" — DAFI 36-2606 para 3.4.1.
UIF_BLOCKS_CJR_CITATION = "DAFI 36-2606 para 3.4.1"
# Spec 1: RE code that means "first-term selected" (has a CJR).
CJR_SELECTED_RE_CODE = "1R"
# Spec 1 extension-history heuristic (fallback ONLY when ETS is blank, first-
# termers only): months DOE->DOS. 48 = 4-year no extension; 49-71 = 4-year plus
# (n-48) extended; 72 = 6-year no extension OR 4-year plus 24 (ambiguous);
# 73+ = extended. Owner decision: where ETS is present, pending extension
# months = months(ETS -> DOS) instead.
FOUR_YEAR_TERM_MONTHS = 48
SIX_YEAR_TERM_MONTHS = 72
# Spec 1: extensions need a service-directed reason. DAFI 36-2606 Table 6.2
# (Rule 12 PCS retainability, Rule 13 command sponsorship, Rule 14 overseas
# tour extension). VERIFY rule numbers.
EXTENSION_REASON_NOTE = (
    "Extension needs a service-directed reason (DAFI 36-2606 Table 6.2: Rule 12 PCS retainability, "
    "Rule 13 command sponsorship, Rule 14 overseas tour extension)."
)
# Spec 1: "RE 3B cannot extend."
RE_CODES_CANNOT_EXTEND = ("3B",)
# Spec 1 HYT: "if DOS equals HYT, or RE is 2T/2U/2V, classify HYT/RETIREMENT".
# "No reenlistment or extension may run past the month after HYT" —
# DAFI 36-2606 para 5.11.11. VERIFY.
HYT_RE_CODES = ("2T", "2U", "2V")
HYT_LIMIT_CITATION = "DAFI 36-2606 para 5.11.11"
# Owner decision (00-decisions): RE 1J ("elects separation") -> REVIEW, not ELIGIBLE.
REVIEW_RE_CODES = {"1J": "member elected separation — confirm intent"}
# Spec 1: 1M = not yet SRP considered -> status "ELIGIBLE - NOT YET SRP CONSIDERED".
NOT_YET_SRP_CONSIDERED_RE_CODES = ("1M",)

# Run 1 statuses, most decisive first (used to pick the status when a member
# has several reasons; every reason is still listed).
STATUS_HYT = "HYT/RETIREMENT"
STATUS_INELIGIBLE = "INELIGIBLE"
STATUS_INELIGIBLE_WAIVABLE = "INELIGIBLE - WAIVABLE"
STATUS_REVIEW = "REVIEW"
STATUS_ELIGIBLE_NYSC = "ELIGIBLE - NOT YET SRP CONSIDERED"
STATUS_ELIGIBLE = "ELIGIBLE"
STATUS_PRECEDENCE = (
    STATUS_HYT, STATUS_INELIGIBLE, STATUS_INELIGIBLE_WAIVABLE,
    STATUS_REVIEW, STATUS_ELIGIBLE_NYSC, STATUS_ELIGIBLE,
)

# =============================================================================
# Reenlistment RE code map — DAFI 36-2606 Tables 5.2-5.5 (waivers Table 5.6)
# -----------------------------------------------------------------------------
# Definitions are the owner's spec wording. Codes the spec lists WITHOUT a
# definition use RE_DEFINITION_UNVERIFIED (owner decision: never invent text).
# Any code not in this map => REVIEW (never a silent pass).
# =============================================================================
RE_TABLES_CITATION = "DAFI 36-2606 Tables 5.2-5.5"
RE_WAIVER_CITATION = "DAFI 36-2606 Table 5.6"
RE_DEFINITION_UNVERIFIED = "Verify definition in DAFI 36-2606 Table 5.x"
RE_WAIVER_AUTHORITY_UNVERIFIED = "Verify waiver authority in DAFI 36-2606 Table 5.6"

RE_CLASS_ELIGIBLE = "ELIGIBLE"
RE_CLASS_BARRED = "BARRED"
RE_CLASS_INELIGIBLE_WAIVABLE = "INELIGIBLE - WAIVER POSSIBLE"
RE_CLASS_INELIGIBLE = "INELIGIBLE"

_SERIES_CLASS = {
    "1": RE_CLASS_ELIGIBLE,
    "2": RE_CLASS_BARRED,
    "3": RE_CLASS_INELIGIBLE_WAIVABLE,
    "4": RE_CLASS_INELIGIBLE,
}

# code -> spec definition (None = spec gave no definition)
_RE_SPEC_DEFINITIONS = {
    # 1-series: eligible
    "1A": "Waived", "1J": "Selected/elects separation", "1K": None,
    "1M": "Not yet SRP considered", "1P": None, "1Q": None, "1R": "First-term selected",
    # 2-series: barred
    "2A": "AFPC denied", "2B": None, "2C": None, "2D": None, "2E": None, "2F": None,
    "2G": "Drug ADAPT", "2H": "Alcohol ADAPT", "2I": "Non-citizen initial enlistment",
    "2J": "Under investigation", "2K": "Notified of involuntary separation",
    "2L": "Charges pending", "2M": "Serving court-martial sentence", "2N": None,
    "2P": "AWOL/deserter", "2Q": "Medical", "2R": "Age 62", "2S": "Age 62",
    "2T": "Within 23 months of HYT", "2U": "Within 23 months of HYT",
    "2V": "Retirement applied/approved", "2W": None, "2X": "Non-selected",
    # 3-series: ineligible, waiver possible
    "3A": None, "3B": "Needs SRP consideration", "3C": "First-term not yet SRP considered",
    "3D": "Refused PCS/TDY retainability", "3E": "Refused training retainability", "3F": None,
    "3I": "SRP selected but no CJR", "3K": None, "3Q": None, "3S": None, "3V": None,
    # 4-series: ineligible
    "4A": None, "4C": None, "4D": None, "4E": "Grade/TIG", "4F": "Lost time 5+ days",
    "4G": "Skill level not commensurate with grade", "4H": "Article 15 suspended punishment",
    "4I": "Control roster", "4J": "Fitness", "4K": "MEB/PEB pending", "4L": None, "4M": None,
    "4N": "Civil conviction",
}

# Spec 1: "Waivable per Table 5.6: 4F, 4K, 4N (unit CC), 4E (via AFPC)."
RE_4_SERIES_WAIVERS = {"4F": "Unit CC", "4K": "Unit CC", "4N": "Unit CC", "4E": "AFPC"}


def _build_re_map() -> dict:
    out = {}
    for code, definition in _RE_SPEC_DEFINITIONS.items():
        series = code[0]
        eligibility_class = _SERIES_CLASS[series]
        if series == "1":
            waivable, authority = None, "N/A (eligible series)"
        elif series == "2":
            waivable, authority = False, "Not waivable (barred)"
        elif series == "3":
            waivable, authority = True, RE_WAIVER_AUTHORITY_UNVERIFIED
        else:
            waivable = code in RE_4_SERIES_WAIVERS
            authority = RE_4_SERIES_WAIVERS.get(code, "Not waivable")
        out[code] = {
            "series": series,
            "definition": definition or RE_DEFINITION_UNVERIFIED,
            "definition_verified_in_spec": definition is not None,
            "eligibility_class": eligibility_class,
            "waivable": waivable,
            "waiver_authority": authority,
            "citation": RE_WAIVER_CITATION if code in RE_4_SERIES_WAIVERS else RE_TABLES_CITATION,
        }
    return out


REENLISTMENT_RE_CODES = _build_re_map()

# =============================================================================
# RUN 2 — DEROS Option
# =============================================================================
# Spec 1 Run 2: "within DEROS_WINDOW_MONTHS (default 12) of DEROS". Local preference.
DEROS_WINDOW_MONTHS = 12
# Spec 1 Run 2: overseas-to-CONUS retainability, "default 12, verify against
# DAFI 36-2110 Table 6.4", counted month/year from the DEROS month (para 6.28.2).
OS_TO_CONUS_RETAINABILITY_MONTHS = 12
OS_TO_CONUS_RETAINABILITY_CITATION = "DAFI 36-2110 Table 6.4; counted from the DEROS month per para 6.28.2"
# Spec 1 Run 2 notes column — DAFI 36-2110 para 6.28.4.3.
DEROS_RIP_RESPONSE_DAYS = 30
DEROS_RIP_NOTE = (
    "Member must obtain or decline retainability within 30 days of signing the DEROS Option RIP, "
    "or is involuntarily extended to DOS (DAFI 36-2110 para 6.28.4.3)."
)
# Spec 1 Run 2: "Indefinite DEROS needs 8 months retainability (para 6.28.4.7)".
INDEFINITE_DEROS_RETAINABILITY_MONTHS = 8
INDEFINITE_DEROS_NOTE = (
    "Indefinite DEROS needs 8 months retainability (DAFI 36-2110 para 6.28.4.7)."
)
DEROS_FLAG_NO_ASSIGNMENT = "NO_ASSIGNMENT"
DEROS_FLAG_INSUFFICIENT_RETAINABILITY = "INSUFFICIENT_RETAINABILITY"

# =============================================================================
# RUN 3 — RE Code Management
# =============================================================================
# Spec 1 Run 3: RE_REVIEW_PREFIXES default ["2", "4"]. Local preference.
RE_REVIEW_PREFIXES = ("2", "4")

# =============================================================================
# RUN 4 — SrA BTZ Quarterly Eligibility (DAFI 36-2502; spec cites AFI 36-2502,
# 26 Sep 2024, paras 2.2.1 and 2.3.1)
# =============================================================================
# Fully qualified SrA date = earlier of
#   (a) later of TAFMSD + 36 months and DOR + 20 months, or
#   (b) DOR + 28 months.            — paras 2.2.1 / 2.3.1. VERIFY.
BTZ_TIS_MONTHS = 36
BTZ_TIG_WITH_TIS_MONTHS = 20
BTZ_TIG_ONLY_MONTHS = 28
# BTZ date = fully qualified date minus 6 months — para 2.3.1. VERIFY.
BTZ_MONTHS_EARLY = 6
BTZ_DATE_CITATION = "DAFI 36-2502 paras 2.2.1 and 2.3.1 (spec cites AFI 36-2502, 26 Sep 2024)"
# Quarter assignment — Table 2.7. Keyed by the calendar quarter of the BTZ
# date: (first processing month offset, second processing month offset, board
# month offset) in months relative to the first month of the BTZ quarter.
#   BTZ Apr-Jun: process Jan/Feb, board Mar
#   BTZ Jul-Sep: process Apr/May, board Jun
#   BTZ Oct-Dec: process Jul/Aug, board Sep
#   BTZ Jan-Mar: process Oct/Nov, board Dec (previous calendar year)
BTZ_PROCESSING_OFFSETS_MONTHS = (-3, -2)
BTZ_BOARD_OFFSET_MONTHS = -1
BTZ_QUARTER_CITATION = "DAFI 36-2502 Table 2.7 (spec cites AFI 36-2502, 26 Sep 2024)"
# Quotas — paras 2.3.5-2.3.7. VERIFY.
BTZ_QUOTA_RATE_PERCENT = 15          # 15% of eligibles, rounded half-up
BTZ_LARGE_UNIT_THRESHOLD = 7         # 7 or more eligibles = LARGE unit (own quota)
BTZ_CBB_MIN_POOL_FOR_ONE_QUOTA = 2   # no large units and 2-6 small-unit eligibles = one CBB quota
BTZ_CBB_MAX_POOL_FOR_ONE_QUOTA = 6
BTZ_QUOTA_CITATION = "DAFI 36-2502 paras 2.3.5-2.3.7 (spec cites AFI 36-2502, 26 Sep 2024)"
# Previously considered — grade status reason 5Q.
BTZ_PREVIOUSLY_CONSIDERED_GSR = "5Q"
BTZ_GSR_STANDING_NOTE = "Verify not previously considered (GSR 5Q) in MilPDS."
# Projected PCS — para 2.4.1.
BTZ_PCS_CITATION = "DAFI 36-2502 para 2.4.1"
# Standing note — para 2.3.4.4.2.
BTZ_PRIOR_SERVICE_NOTE = (
    "A1Cs with DOR adjusted for prior service are not BTZ eligible; verify manually "
    "(DAFI 36-2502 para 2.3.4.4.2)."
)
# Quality indicators shown as remarks (from the MEL's checks).
BTZ_CONTROL_ROSTER_RE = "4I"
BTZ_SUSPENDED_ART15_RE = "4H"
BTZ_MIN_SKILL_LEVEL = "3"

# =============================================================================
# CSS PSDG duties (Commanders' Support Staff Execution, Organization, and
# Responsibilities PSD Guide, 5 Dec 2025) — shown on run pages / PDF headers.
# =============================================================================
CSS_PSDG = "CSS PSDG (5 Dec 2025)"
CSS_DUTIES = {
    "F1-3": "Table F1 item 3: Oversight with the MPF of the unit reenlistment and extension program (DAFI 36-2606)",
    "F1-32": "Table F1 item 32: Manage the unit Below-the-Zone (BTZ) program (DAFI 36-2502)",
    "F1-36": "Table F1 item 36: Administer unit Selective Reenlistment Program (SRP) processing (DAFI 36-2606)",
    "F1-37a": "Table F1 item 37(a): Administer unit Selective Retention Bonus (SRB) roster (DAFI 36-2606)",
    "F1-37b": "Table F1 item 37(b): Monitor unit UIFs / Control Roster (DAFI 36-2907)",
    "F1-40": "Table F1 item 40: Manage unit Vulnerable to Move List (VML) (DAFI 36-2110)",
    "G1-1": "Table G1 item 1 (Section Commander): Reenlistments — DAF Forms 901, 1411, 418, 1411-1 SRP Roster (DAFI 36-2606)",
    "G1-6-7": "Table G1 items 6-7: PDD / RNLTD change requests (DAFI 36-2110)",
}

# =============================================================================
# Everything the owner must verify — served by GET /api/v1/rosters/runs and
# printed on each XLSX "Report Info" sheet.
# =============================================================================
RULE_REFERENCES = [
    # (run, rule, value, citation, note)
    ("dos-reenlistment", "DOS window", f"{DOS_WINDOW_MONTHS} months", "Owner spec (DOS_WINDOW_MONTHS)", LOCAL_PREFERENCE),
    ("dos-reenlistment", "Action-by date", f"DOS minus {REENLISTMENT_ACTION_DAYS_BEFORE_DOS} days",
     "DAFI 36-2606 (paragraph not given in spec)", VERIFY),
    ("dos-reenlistment", "RE code map", "1-series eligible, 2 barred, 3 waiver possible, 4 ineligible",
     RE_TABLES_CITATION, VERIFY),
    ("dos-reenlistment", "4-series waivers", "4F, 4K, 4N (unit CC); 4E (AFPC)", RE_WAIVER_CITATION, VERIFY),
    ("dos-reenlistment", "RE 1J", "REVIEW (member elected separation — confirm intent)",
     "Owner decision 2026-11-17", "Owner decision; confirm."),
    ("dos-reenlistment", "UIF", "Any UIF code = REVIEW; UIF blocks CJR for first-termers",
     UIF_BLOCKS_CJR_CITATION, VERIFY),
    ("dos-reenlistment", "CJR required (first term)", "CJR required to reenlist", CJR_REQUIRED_CITATION, VERIFY),
    ("dos-reenlistment", "CJR window", "Months 35-43 (4-year) / 59-67 (6-year) of enlistment",
     "DAFI 36-2606 Table 3.1", VERIFY),
    ("dos-reenlistment", "Extension cap", f"{EXTENSION_CAP_MONTHS} months per enlistment",
     "DAFI 36-2606 Chapter 6", VERIFY),
    ("dos-reenlistment", "Extension reasons", "Service-directed reason (Rules 12, 13, 14); RE 3B cannot extend",
     "DAFI 36-2606 Table 6.2", VERIFY),
    ("dos-reenlistment", "HYT", "DOS at HYT or RE 2T/2U/2V = HYT/RETIREMENT; nothing past the month after HYT",
     HYT_LIMIT_CITATION, VERIFY),
    ("deros-option", "DEROS window", f"{DEROS_WINDOW_MONTHS} months", "Owner spec (DEROS_WINDOW_MONTHS)", LOCAL_PREFERENCE),
    ("deros-option", "OS-to-CONUS retainability", f"{OS_TO_CONUS_RETAINABILITY_MONTHS} months from the DEROS month",
     OS_TO_CONUS_RETAINABILITY_CITATION, VERIFY),
    ("deros-option", "DEROS Option RIP response", f"{DEROS_RIP_RESPONSE_DAYS} days or involuntarily extended to DOS",
     "DAFI 36-2110 para 6.28.4.3", VERIFY),
    ("deros-option", "Indefinite DEROS retainability", f"{INDEFINITE_DEROS_RETAINABILITY_MONTHS} months",
     "DAFI 36-2110 para 6.28.4.7", VERIFY),
    ("re-code-review", "RE review prefixes", ", ".join(RE_REVIEW_PREFIXES), "Owner spec (RE_REVIEW_PREFIXES)",
     LOCAL_PREFERENCE),
    ("btz-quarterly", "Fully qualified SrA date",
     f"earlier of (later of TAFMSD+{BTZ_TIS_MONTHS} mo and DOR+{BTZ_TIG_WITH_TIS_MONTHS} mo) or DOR+{BTZ_TIG_ONLY_MONTHS} mo",
     BTZ_DATE_CITATION, VERIFY),
    ("btz-quarterly", "BTZ date", f"Fully qualified date minus {BTZ_MONTHS_EARLY} months", BTZ_DATE_CITATION, VERIFY),
    ("btz-quarterly", "Quarter table", "Apr-Jun: Jan/Feb, board Mar; Jul-Sep: Apr/May, Jun; Oct-Dec: Jul/Aug, Sep; "
     "Jan-Mar: Oct/Nov, Dec", BTZ_QUARTER_CITATION, VERIFY),
    ("btz-quarterly", "Quota", f"{BTZ_QUOTA_RATE_PERCENT}% rounded half-up; LARGE unit = {BTZ_LARGE_UNIT_THRESHOLD}+ "
     "eligibles; smaller units pooled into CBB", BTZ_QUOTA_CITATION, VERIFY),
    ("btz-quarterly", "CBB edge rules", "No large units and 2-6 pooled eligibles = 1 CBB quota; 1 eligible base-wide = "
     "MPF/CC decision", BTZ_QUOTA_CITATION, VERIFY),
    ("btz-quarterly", "Projected PCS", "RNLTD on/after first processing month = losing unit considers",
     BTZ_PCS_CITATION, VERIFY),
    ("btz-quarterly", "Prior-service DOR", "Not BTZ eligible; verify manually", "DAFI 36-2502 para 2.3.4.4.2", VERIFY),
]
