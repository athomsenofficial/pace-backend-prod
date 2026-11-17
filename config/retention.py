"""
Retention and BTZ roster runs — every window, threshold and code map.

Runs served (one alpha-roster upload per session, see routers/roster_runs.py):
  1. DOS / Reenlistment Decision Roster      (DAFI 36-2606)
  2. DEROS Option Roster                     (DAFI 36-2110)
  3. RE Code Management Roster               (DAFI 36-2606)
  4. SrA BTZ Quarterly Eligibility Roster    (AFI 36-2502)
  5. First-Term CJR Window Roster            (DAFI 36-2606 Chapter 3)

Changes when: a governing publication changes. Every regulatory value below was
checked on 17 Nov 2026 against the editions named in PUB_* (paragraph / table
numbers are from those editions). docs/specs/03-regulation-verification.md has
the rule-by-rule record (quote, status). Values that are local preferences or
that the publications do not state are labelled as such. Change the value here
only; the run code reads nothing else.

Deliberately separate from config/domain.py RE_CODES, which the MEL uses and
must not change.
"""

LOCAL_PREFERENCE = "Local preference (not a regulatory value)."
VERIFIED = "Verified against the publication 17 Nov 2026."
NOT_IN_PUBLICATION = "Not stated in the publication — local rule; owner to confirm."

PUB_REENLISTMENT = "DAFI 36-2606 (22 May 2024, incl. Change 1, 21 May 2026)"
PUB_ASSIGNMENTS = "DAFI 36-2110 (9 Aug 2024, incl. Change 2, 5 Mar 2026)"
PUB_PROMOTIONS = "AFI 36-2502 (2 Jul 2026)"
PUB_RETIREMENTS = "DAFI 36-3203 (8 Jul 2025)"
PUB_ADVERSE_ACTIONS = "DAFI 36-2907 (14 Jan 2026)"

# =============================================================================
# Footers (one line on every PDF page; also the XLSX footer row)
# =============================================================================
RETENTION_FOOTER = (
    "Screening aid only. MPF and commander determine eligibility per DAFI 36-2606 (22 May 2024, Chg 1) "
    "and DAFI 36-2110 (9 Aug 2024, Chg 2)."
)
BTZ_FOOTER = "Screening aid only. MPF verifies eligibility and quotas per AFI 36-2502 (2 Jul 2026)."
CJR_FOOTER = "Screening aid only. MPF and commander determine eligibility per DAFI 36-2606."

# =============================================================================
# Data conventions of the alpha-roster export (owner, 00-decisions)
# =============================================================================
# Year 3888 marks an indefinite date (officers' DOS, some TSG-CMS ETS/DOS).
# Any year at or above this threshold = "indefinite", never a real date and
# never a DATA ISSUE. Indefinite DEROS: blank or year >= threshold.
INDEFINITE_YEAR_THRESHOLD = 3000
# UIF_CODE values that mean "no UIF". DAFI 36-2907 defines UIF codes 1-4 as UIF
# states (1 = UIF on file / final, 2 = control roster, 3 = Article 15 interim;
# Table 3.2, para 1.3.7.2), so every non-blank, non-zero code is a UIF. "0" as
# "no UIF" is an export convention (not in the publication).
# NOTE: the MEL (board_filter) only treats codes > 1 as an issue; these runs
# treat every non-blank, non-zero code as a UIF (a UIF of any kind bars a CJR,
# DAFI 36-2606 para 3.4.1).
UIF_NONE_VALUES = ("", "0")

# =============================================================================
# RUN 1 — DOS / Reenlistment Decision
# =============================================================================
# Spec 1 Run 1: "DOS within DOS_WINDOW_MONTHS (default 12)". Local preference.
DOS_WINDOW_MONTHS = 12
# DAFI 36-2606 Table 5.1 Note 4: "Service members must project reenlistments
# with their servicing MPF NLT 120 days prior to their DOS or they are projected
# for Separation." Note 5 / para 1.13.16: MilPDS projects everyone within 120
# days of DOS for separation. Para 1.13.16: MPF notifies eligibles NLT 150 days
# prior to DOS.
REENLISTMENT_ACTION_DAYS_BEFORE_DOS = 120
REENLISTMENT_ACTION_CITATION = "DAFI 36-2606 Table 5.1 Notes 4-5; para 1.13.16"
REENLISTMENT_NOTIFY_DAYS_BEFORE_DOS = 150
# DAFI 36-2606 para 6.2.2: "Voluntary extensions ... limited to a maximum of 48
# months per enlistment (10 USC § 509). This cannot be waived." Involuntary
# extensions (Stop-Loss, admin/disciplinary hold) do not count (para 6.6.2.1).
EXTENSION_CAP_MONTHS = 48
EXTENSION_CAP_CITATION = "DAFI 36-2606 paras 6.2.2 and 6.6.2.1"
# CJR: OWNER DECISION 17 Nov 2026 — the CJR has no bearing on the Run 1
# reenlistment status. It is screened by its own run (RUN 5 below).
# Spec 1 extension-history heuristic (fallback ONLY when ETS is blank, first-
# termers only): months DOE->DOS. 48 = 4-year no extension; 49-71 = 4-year plus
# (n-48) extended; 72 = 6-year no extension OR 4-year plus 24 (ambiguous);
# 73+ = extended. Owner decision: where ETS is present, pending extension
# months = months(ETS -> DOS) instead.
FOUR_YEAR_TERM_MONTHS = 48
SIX_YEAR_TERM_MONTHS = 72
# DAFI 36-2606 Table 6.2 (Reasons for Extensions of Enlistment): Rule 12 PCS/
# PCA/TDY retainability, Rule 13 command sponsorship overseas, Rule 14 overseas
# tour extension or to maintain an indefinite DEROS; Rule 28c personal
# convenience (one time; not allowed while a service-directed requirement exists).
EXTENSION_REASON_NOTE = (
    "Extension needs a DAFI 36-2606 Table 6.2 reason: e.g. Rule 12 PCS/PCA/TDY retainability, Rule 13 command "
    "sponsorship, Rule 14 overseas tour extension or indefinite DEROS. Rule 28c personal convenience (one time: "
    "12 months for a first-termer in RE 1R with a CJR, up to 24 months for a reenlistment-eligible second-term/"
    "career member) cannot be used while a service-directed requirement exists."
)
# Codes that may not extend at all (code -> reason).
RE_CODES_CANNOT_EXTEND = {
    "3B": "cannot extend while SRP reconsideration is pending (DAFI 36-2606 para 6.6.5)",
    "2V": "may not extend once retirement is approved, including Rule 28c (DAFI 36-2606 para 6.6.5.1.1)",
}
# Reenlistment-ineligible members (2-, 3-, 4-series) may extend only where
# Table 6.2 allows it (para 6.6.5.3; Tables 5.3-5.5 headings).
INELIGIBLE_EXTENSION_NOTE = (
    "Reenlistment-ineligible: may extend only where DAFI 36-2606 Table 6.2 allows it for this condition "
    "(para 6.6.5.3)."
)
# HYT: DAFI 36-2606 para 5.11.11: "Under no circumstances will any reenlistment
# or extension exceed the month following the service members HYT or age 62,
# whichever occurs first." (Extensions: para 6.6.9.)
# RE 2T/2U (within 23 months of an HYT of 20+ years) and 2V (retirement
# applied/approved) -> HYT/RETIREMENT.
HYT_RE_CODES = ("2T", "2U", "2V")
HYT_LIMIT_CITATION = "DAFI 36-2606 paras 5.11.11 and 6.6.9"
# HYT tenure points: DAFI 36-3203 para 3.10: E-4 10, E-5 20, E-6 22, E-7 24,
# E-8 26, E-9 30 years. The runs reuse the MEL's compute_hyt_date for AB-SMS
# (config/domain.py MAIN_HIGHER_TENURE, which also applies the MEL's temporary
# HYT-extension window — not in DAFI 36-3203). CMSgt is not in the MEL table,
# so the runs use the publication value here.
HYT_YEARS_NOT_IN_MEL = {"CMS": 30}
HYT_TENURE_CITATION = "DAFI 36-3203 para 3.10"
# Owner decision (00-decisions): RE 1J ("Eligible to reenlist but elects
# separation", Table 5.2 item 2) -> REVIEW, not ELIGIBLE.
REVIEW_RE_CODES = {"1J": "member elected separation — confirm intent"}
# "ELIGIBLE - NOT YET SRP CONSIDERED":
#   1M = second-term/career member not yet considered under the SRP (Table 5.2 item 4);
#   3B = needs SRP consideration/reconsideration, 3C = first-termer not yet SRP
#   considered (Table 5.4 items 5-6, "do not separate"). OWNER DECISION 17 Nov
#   2026: 3B and 3C are treated as eligible, awaiting SRP consideration.
NOT_YET_SRP_CONSIDERED_RE_CODES = ("1M", "3B", "3C")
OWNER_ELIGIBLE_RE_CODES = {
    "3B": "ELIGIBLE (owner decision 17 Nov 2026: awaiting SRP consideration)",
    "3C": "ELIGIBLE (owner decision 17 Nov 2026: awaiting SRP consideration)",
}

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
# Definitions are condensed from the table text (item numbers kept). Table 5.4
# items 2-4 carry no RE code in the publication and are omitted. Any code not in
# this map => REVIEW (never a silent pass).
# =============================================================================
RE_TABLES_CITATION = "DAFI 36-2606 Tables 5.2-5.5"
RE_WAIVER_CITATION = "DAFI 36-2606 Table 5.6"
RE_DEFINITION_UNKNOWN = "Code not in DAFI 36-2606 Tables 5.2-5.5 — verify in MilPDS"

RE_CLASS_ELIGIBLE = "ELIGIBLE"
RE_CLASS_BARRED = "BARRED"
# Table 5.4 heading: "ineligible for immediate reenlistment ... but eligible for
# prior service enlistment with an approved waiver". Table 5.6 has no 3-series
# reenlistment waiver.
RE_CLASS_INELIGIBLE_PS_WAIVER = "INELIGIBLE (prior-service enlistment waiver possible)"
RE_CLASS_INELIGIBLE = "INELIGIBLE"

_SERIES_CLASS = {
    "1": RE_CLASS_ELIGIBLE,
    "2": RE_CLASS_BARRED,
    "3": RE_CLASS_INELIGIBLE_PS_WAIVER,
    "4": RE_CLASS_INELIGIBLE,
}
_SERIES_TABLE = {"1": "5.2", "2": "5.3", "3": "5.4", "4": "5.5"}

# code -> (Table item number, definition)
_RE_DEFINITIONS = {
    # Table 5.2 — RE-1 series: eligible for immediate reenlistment
    "1A": (1, "Ineligible to reenlist, but condition waived (do not separate)"),
    "1J": (2, "Eligible to reenlist but elects separation (incl. SRP-selected members who elect separation)"),
    "1K": (3, "Career member selected under the SRP with 13 months or less before 20 years TAFMS (do not separate)"),
    "1M": (4, "Eligible; second-term or career member not yet considered under the SRP (do not separate)"),
    "1P": (5, "Eligible; second-term/career member under 19 years TAFMS, SRP-selected, 13 months or less before "
              "original ETS or serving an extension (do not separate)"),
    "1Q": (6, "Eligible; career member over 20 years TAFMS, SRP-selected, 13 months or less before original ETS "
              "or serving an extension (do not separate)"),
    "1R": (7, "First-term Airman/Guardian selected for reenlistment under the SRP (do not separate)"),
    "1T": (8, "ANG/AFR member on extended active duty — may request RegAF/USSF enlistment only"),
    "1S": (9, "ANG/AFR member on a STAT tour — eligible under the ANG/AFR program only"),
    # Table 5.3 — RE-2 series: conditions barring immediate reenlistment
    "2A": (1, "AFPC denied reenlistment (AFPC use only)"),
    "2B": (2, "Separated with a general or under-other-than-honorable-conditions discharge"),
    "2C": (3, "Involuntarily separated with an honorable discharge, or entry-level separation without "
              "characterization"),
    "2D": (4, "Returned prisoner with less than six months of service since return to duty"),
    "2E": (5, "Serving a period of probation and rehabilitation"),
    "2F": (6, "Undergoing (or separated while undergoing) rehabilitation in a DoD regional confinement facility"),
    "2G": (7, "Participating in, failed, or failed to complete the ADAPT program for drugs"),
    "2H": (8, "Participating in, or failed to complete, the ADAPT program for alcohol"),
    "2I": (9, "Non-US citizen serving on initial enlistment"),
    "2J": (10, "Under investigation that may result in discharge or court-martial (do not separate)"),
    "2K": (11, "Formally notified by the commander of initiation of involuntary separation action"),
    "2L": (12, "Civilian criminal charges pending, court-martial charges preferred, or court-martial action under "
               "appellate review"),
    "2M": (13, "Serving a sentence or suspended sentence of court-martial"),
    "2N": (14, "Conscientious objector whose convictions preclude unrestricted assignment"),
    "2P": (15, "Absent without leave, deserter, or dropped from rolls"),
    "2Q": (16, "Medically retired or discharged"),
    "2R": (17, "Within 23 months of 62nd birthday, 18 years 1 month+ TAFMS, 13 months or less until DOS"),
    "2S": (18, "Within 23 months of 62nd birthday, 18 years 1 month+ TAFMS, more than 13 months until DOS"),
    "2T": (19, "HYT of at least 20 years TAFMS, within 23 months of HYT, 13 months or less until DOS"),
    "2U": (20, "HYT of at least 20 years TAFMS, within 23 months of HYT, more than 13 months until DOS"),
    "2V": (21, "Applied for retirement or retirement approved"),
    "2W": (22, "Retired and recalled to RegAF/USSF"),
    "2X": (23, "Non-selected for reenlistment (or non-selected for continued service under the NCO Career Status "
               "Program)"),
    # Table 5.4 — RE-3 series: barred from immediate reenlistment; prior-service
    # enlistment possible with an approved waiver
    "3A": (1, "First-termer separating before 36 months (60 for a 6-year enlistee) with no disqualifier except "
              "grade, skill level or insufficient TAFMS"),
    "3B": (5, "Was ineligible; condition no longer exists and member requires SRP consideration or reconsideration "
              "(do not separate)"),
    "3C": (6, "First-termer not yet considered under the SRP (do not separate)"),
    "3D": (7, "Second-term/career member who refused PCS or TDY retainability (incl. a deployment)"),
    "3E": (8, "Second-term/career member who refused retainability for, or declined, training or retraining"),
    "3F": (9, "Selected for non-retention by an Enlisted Retention Board"),
    "3I": (10, "First-termer selected under the SRP but not awarded/selected for a CJR and removed from "
               "eligibility"),
    "3K": (11, "Reserved for AFPC / AFBCMR when no other RE code applies"),
    "3Q": (12, "Selected for non-retention by a Quality Force Review Board"),
    "3S": (13, "Separated with Special Separation Benefit"),
    "3V": (14, "Separated with Voluntary Separation Incentive or Enlisted Voluntary Separation Pay"),
    # Table 5.5 — RE-4 series: ineligible to reenlist
    "4A": (1, "Separated for hardship or dependency"),
    "4C": (2, "Separated for concealed juvenile records, minority, failing physical or reading standards, or void "
              "enlistment"),
    "4D": (3, "E-4 with 9 to under 16 years TAFMS, not selected for promotion to E-5"),
    "4E": (4, "Grade/time in grade too low for months served (e.g. 4-year first-termer at 31+ months still E-3 with "
              "under 12 months TIG)"),
    "4F": (5, "Five or more days lost time during current enlistment"),
    "4G": (6, "No AFSC/SFSC skill level commensurate with grade"),
    "4H": (7, "Serving suspended punishment under Article 15, UCMJ"),
    "4I": (8, "Serving on the control roster"),
    "4J": (9, "Unsatisfactory fitness assessment"),
    "4K": (10, "Pending Medical Evaluation Board / Physical Evaluation Board"),
    "4L": (11, "Separated after elimination from a commissioning program"),
    "4M": (12, "Breach of enlistment/reenlistment agreement"),
    "4N": (13, "Convicted by civilian authorities"),
}

# Table 5.6 (Conditions Requiring a Waiver to Reenlist): code -> (waivable, authority).
# waivable: True, or "Conditional" (only in the narrow case the item names).
RE_4_SERIES_WAIVERS = {
    "4F": (True, "CC/civilian director (Table 5.6 item 1)"),
    "4K": (True, "CC/civilian director; SRB AFSC: AF/A1 or SF/S1 final approval (Table 5.6 item 2)"),
    "4N": (True, "CC/civilian director (Table 5.6 item 4)"),
    "4E": (True, "First-termer: group/delta CC approves an extension (via AFPC/DPPSA) to meet grade/TIG; "
                 "no direct reenlistment waiver (Table 5.6 item 6, Note 6)"),
    "4G": ("Conditional", "CC/civilian director only if disqualified from the AFSC, in RI 9A000-9A300 and approved "
                          "for retraining/special duty (Table 5.6 item 5)"),
}
RE_3_SERIES_WAIVER_TEXT = ("No reenlistment waiver in Table 5.6; prior-service enlistment needs an approved "
                           "waiver per Table 5.4")
RE_2_SERIES_WAIVER_TEXT = "Not waivable — no Table 5.6 provision"


def _build_re_map() -> dict:
    out = {}
    for code, (item, definition) in _RE_DEFINITIONS.items():
        series = code[0]
        if series == "1":
            waivable, authority = None, "N/A (eligible series)"
        elif series == "2":
            waivable, authority = False, RE_2_SERIES_WAIVER_TEXT
        elif series == "3":
            waivable, authority = False, RE_3_SERIES_WAIVER_TEXT
        else:
            waivable, authority = RE_4_SERIES_WAIVERS.get(code, (False, "Not waivable — no Table 5.6 provision"))
        citation = f"DAFI 36-2606 Table {_SERIES_TABLE[series]} item {item}"
        if code in RE_4_SERIES_WAIVERS:
            citation += f"; {RE_WAIVER_CITATION}"
        if code in OWNER_ELIGIBLE_RE_CODES:
            waivable, authority = None, "N/A (owner: eligible, awaiting SRP consideration)"
        out[code] = {
            "series": series,
            "definition": definition,
            "eligibility_class": OWNER_ELIGIBLE_RE_CODES.get(code, _SERIES_CLASS[series]),
            "waivable": waivable,
            "waiver_authority": authority,
            "citation": citation,
        }
    return out


REENLISTMENT_RE_CODES = _build_re_map()

# =============================================================================
# RUN 2 — DEROS Option
# =============================================================================
# Spec 1 Run 2: "within DEROS_WINDOW_MONTHS (default 12) of DEROS". Local preference.
DEROS_WINDOW_MONTHS = 12
# DAFI 36-2110 Table 6.4 Rules 10-11: PCS overseas to CONUS = 12 months minimum
# retainability. Para 6.28.2: "For PCS overseas to CONUS, add the number of
# months retainability required to the member's DEROS (month and year only)."
OS_TO_CONUS_RETAINABILITY_MONTHS = 12
OS_TO_CONUS_RETAINABILITY_CITATION = "DAFI 36-2110 Table 6.4 Rules 10-11; counted from the DEROS month per para 6.28.2"
# DAFI 36-2110 para 6.28.4.3: have/obtain retainability or complete declination
# within 30 calendar days of signing the DEROS Option RIP; members without the
# retainability are involuntarily extended overseas until DOS (para 7.6.1,
# Table 7.9). Para 7.5.3.3.1-.2: the RIP goes back to the MPF NLT 30 calendar
# days from the date it was produced.
DEROS_RIP_RESPONSE_DAYS = 30
DEROS_RIP_NOTE = (
    "Member must have/obtain retainability or complete a declination within 30 calendar days of signing the DEROS "
    "Option RIP, or is involuntarily extended overseas to DOS (DAFI 36-2110 para 6.28.4.3)."
)
# DAFI 36-2110 para 6.28.4.7 (and 7.5.5.1.3): enlisted members must maintain at
# least 8 months service retainability to keep an indefinite DEROS.
INDEFINITE_DEROS_RETAINABILITY_MONTHS = 8
INDEFINITE_DEROS_NOTE = (
    "Indefinite DEROS needs at least 8 months service retainability; under 8 months the DEROS is set to DOS "
    "(DAFI 36-2110 paras 6.28.4.7, 7.5.5.1.3)."
)
DEROS_FLAG_NO_ASSIGNMENT = "NO_ASSIGNMENT"
DEROS_FLAG_INSUFFICIENT_RETAINABILITY = "INSUFFICIENT_RETAINABILITY"

# =============================================================================
# RUN 3 — RE Code Management
# =============================================================================
# Spec 1 Run 3: RE_REVIEW_PREFIXES default ["2", "4"]. Local preference.
RE_REVIEW_PREFIXES = ("2", "4")

# =============================================================================
# RUN 5 — First-Term CJR Window (DAFI 36-2606 Chapter 3)
# =============================================================================
# Table 3.1 (CJR Eligibility Window): four-year enlistee = first duty day of the
# month they complete 32 months through the last duty day of the month they
# complete 43 months; six-year enlistee = months 56-67.
CJR_WINDOWS_BY_TERM_MONTHS = {48: (32, 43), 72: (56, 67)}
CJR_WINDOW_CITATION = "DAFI 36-2606 Table 3.1"
# Para 3.1.1: "All FTA/FTG, regardless of AFSC/SFSC, must have a CJR to reenlist."
CJR_REQUIRED_CITATION = "DAFI 36-2606 para 3.1.1"
# Para 3.1.2: no CJR in the window (constrained AFSC) = no CJR later; separate at DOS.
CJR_MISSED_CITATION = "DAFI 36-2606 para 3.1.2"
# Para 3.4.1: CC may not consider members for a CJR if they have a UIF, lost
# time, or active NJP on the current enlistment (shown for information).
UIF_BLOCKS_CJR_CITATION = "DAFI 36-2606 para 3.4.1"
# RE 1R = "First Term Airmen/Guardians selected for reenlistment under the SRP"
# (Table 5.2 item 7). Members in 1R are left off the CJR run (owner spec); the
# MilPDS CJR code ("C", para 3.4.7.2) is not in the alpha-roster export.
CJR_SELECTED_RE_CODE = "1R"
# "APPROACHING" = window opens within this many months. Local preference (param).
CJR_APPROACHING_MONTHS = 3
CJR_STATUS_IN_WINDOW = "IN WINDOW"
CJR_STATUS_PAST_WINDOW = "PAST WINDOW"
CJR_STATUS_APPROACHING = "APPROACHING"
CJR_NOTES = (
    "First term = DOE equals TAFMSD (no prior service, never reenlisted). Term from ETS minus DOE: 48 months = "
    "4-year; 49-71 = 4-year with effective extensions; 72 or more = ambiguous (6-year, or 4-year extended) — both "
    "windows are checked.",
    "CJR window (DAFI 36-2606 Table 3.1): from the first day of the month the member completes 32 months (56 for a "
    "6-year enlistee) through the last day of the month they complete 43 months (67).",
    "A CJR is required to reenlist (para 3.1.1); members are only eligible for a CJR during their window (Table 3.1 "
    "Note 3); in a constrained AFSC, no CJR in the window means no CJR later (para 3.1.2).",
    "UIF shown for information: a UIF, lost time or active NJP bars CJR consideration (para 3.4.1).",
    "Members in RE 1R (first-termer selected under the SRP) are not listed. The MilPDS CJR code is not in the "
    "export — verify CJR status in MilPDS.",
)

# =============================================================================
# RUN 4 — SrA BTZ Quarterly Eligibility — AFI 36-2502 (2 Jul 2026)
# =============================================================================
# Para 2.2.1: SrA after "36 months' time-in-service and 20 months' time-in-grade
# or 28 months' time-in-grade whichever occurs first". Fully qualified date =
# earlier of (a) later of TAFMSD + 36 and DOR + 20, or (b) DOR + 28.
BTZ_TIS_MONTHS = 36
BTZ_TIG_WITH_TIS_MONTHS = 20
BTZ_TIG_ONLY_MONTHS = 28
# Para 2.3.1: BTZ is "a one-time promotion consideration to advance to SrA six
# months prior to the fully qualified phase point listed in paragraph 2.2.1".
BTZ_MONTHS_EARLY = 6
BTZ_DATE_CITATION = "AFI 36-2502 (2 Jul 2026) paras 2.2.1 and 2.3.1"
# Table 2.7 (SrA Below the Zone Processing Months and Board Dates). Keyed by the
# calendar quarter of the BTZ date: (first processing month offset, second
# processing month offset, board month offset) relative to the first month of
# the BTZ quarter.
#   BTZ Apr-Jun: process Jan/Feb, board Mar
#   BTZ Jul-Sep: process Apr/May, board Jun
#   BTZ Oct-Dec: process Jul/Aug, board Sep
#   BTZ Jan-Mar: process Oct/Nov, board Dec (previous calendar year)
BTZ_PROCESSING_OFFSETS_MONTHS = (-3, -2)
BTZ_BOARD_OFFSET_MONTHS = -1
BTZ_QUARTER_CITATION = "AFI 36-2502 (2 Jul 2026) Table 2.7"
# Quotas — paras 2.3.5-2.3.7: 15 percent of TIG/TIS eligibles; large unit =
# seven or more eligible. OWNER DECISION 17 Nov 2026: no rounding — PACE shows
# the exact 15% value (two decimals); the MPF sets the whole-number quota.
BTZ_QUOTA_RATE_PERCENT = 15
BTZ_QUOTA_DECIMALS = 2
BTZ_LARGE_UNIT_THRESHOLD = 7          # 7 or more eligibles = LARGE unit (own quota)
BTZ_CBB_MIN_POOL_FOR_ONE_QUOTA = 2    # para 2.3.5.3: no large units and 2-6 small-unit eligibles = one quota
BTZ_CBB_MAX_POOL_FOR_ONE_QUOTA = 6
BTZ_QUOTA_CITATION = "AFI 36-2502 (2 Jul 2026) paras 2.3.5-2.3.7"
BTZ_ROUNDING_NOTE = "AFI 36-2502 sets no rounding rule; the MPF determines the whole-number quota."
BTZ_SINGLE_ELIGIBLE_NOTE = ("Only 1 eligible base-wide: the MPF commander decides whether a board is held and may "
                            "authorize one quota (AFI 36-2502 para 2.3.5.4).")
# OWNER DECISION 17 Nov 2026: the CBB quota is always 15% of the total pooled
# small-unit eligibles (units under 7 always pool). Para 2.3.5.2 (a large unit
# may combine with the small units at the CBB) is cited for information only.
BTZ_COMBINE_WITH_LARGE_NOTE = ("AFI 36-2502 para 2.3.5.2 allows a large unit to combine with the small units at the "
                               "central base board when the small units cannot make one quota; PACE shows 15% of "
                               "the pooled small-unit eligibles (owner decision).")
# CBB participation: para 2.4.2.1, restated by AFPC on myFSS (emailed to the
# owner 17 Nov 2026).
BTZ_CBB_POLICY_NOTE = (
    "CBB: the host wing/installation commander requires every unit under the installation MPF ID (regardless of "
    "command) with fewer than seven eligibles to nominate BTZ candidates to the Central Base Board, and sets the "
    "CBB guidance (AFI 36-2502 para 2.4.2.1; AFPC myFSS clarification, 17 Nov 2026)."
)
# Previously considered — grade status reason 5Q (para 2.3.4).
BTZ_PREVIOUSLY_CONSIDERED_GSR = "5Q"
BTZ_GSR_STANDING_NOTE = ("Verify not previously considered (GSR 5Q) in MilPDS (AFI 36-2502 para 2.3.4).")
# Projected PCS — paras 2.3.3 and 2.4.1: RNLTD on/after the 1st day of the first
# processing month = considered by the losing unit.
BTZ_PCS_CITATION = "AFI 36-2502 paras 2.3.3, 2.4.1"
# Standing note — para 2.3.4.4.2.
BTZ_PRIOR_SERVICE_NOTE = (
    "A1Cs with DOR adjusted for prior service are not BTZ eligible, nor are ROTC/USAFA eliminees credited toward "
    "DOR; verify manually (AFI 36-2502 para 2.3.4.4.2)."
)
# Para 2.3.2: an Airman identified as eligible in the first processing month
# who later becomes ineligible stays in the quota count.
BTZ_QUOTA_COUNT_NOTE = (
    "Quota eligibles are counted on TIG/TIS only, regardless of other ineligibility conditions; anyone eligible in "
    "the first processing month stays in the count. Remarks do not remove anyone. Units cannot aggregate above unit "
    "level (AFI 36-2502 paras 2.3.2, 2.3.5, 2.3.5.1)."
)
# Quality indicators shown as remarks (from the MEL's checks).
BTZ_CONTROL_ROSTER_RE = "4I"
BTZ_SUSPENDED_ART15_RE = "4H"
# AFI 36-2502 Table 2.1 Rule 1 / Note 4: SrA needs a 3-skill level (by the
# promotion effective date). Skill level = 4th character of the AFSC (DAFMAN
# 36-2100, 7 Jul 2026, Attachment 1).
BTZ_MIN_SKILL_LEVEL = "3"

# =============================================================================
# CSS PSDG duties (Commanders' Support Staff Execution, Organization, and
# Responsibilities PSD Guide, 5 Dec 2025) — shown on run pages / PDF headers.
# Item numbers verified against Table F1 / Table G1 on 17 Nov 2026. The PSDG
# lists "DAFI 36-2502" for item 32; the current promotion publication is
# AFI 36-2502 (2 Jul 2026).
# =============================================================================
CSS_PSDG = "CSS PSDG (5 Dec 2025)"
CSS_DUTIES = {
    "F1-3": "Table F1 item 3: Oversight with the MPF of the unit reenlistment and extension program (DAFI 36-2606)",
    "F1-32": "Table F1 item 32: Manage the unit Below-the-Zone (BTZ) program (AFI 36-2502)",
    "F1-36": "Table F1 item 36: Administer unit Selective Reenlistment Program (SRP) processing (DAFI 36-2606)",
    "F1-37a": "Table F1 item 37(a): Administer unit Selective Retention Bonus (SRB) roster (DAFI 36-2606)",
    "F1-37b": "Table F1 item 37(b): Monitor unit UIFs / Control Roster (DAFI 36-2907)",
    "F1-40": "Table F1 item 40: Manage unit Vulnerable to Move List (VML) (DAFI 36-2110)",
    "G1-1": "Table G1 item 1 (Section Commander): Reenlistments — DAF Forms 901, 1411, 418, 1411-1 SRP Roster (DAFI 36-2606)",
    "G1-6-7": "Table G1 items 6-7: PDD / RNLTD change requests (DAFI 36-2110)",
}

# =============================================================================
# Every rule with its source — served by GET /api/v1/rosters/runs and printed
# on each XLSX "Report Info" sheet. (run, rule, value, citation, status note)
# =============================================================================
RULE_REFERENCES = [
    ("dos-reenlistment", "DOS window", f"{DOS_WINDOW_MONTHS} months", "Owner spec (DOS_WINDOW_MONTHS)", LOCAL_PREFERENCE),
    ("dos-reenlistment", "Action-by date", f"DOS minus {REENLISTMENT_ACTION_DAYS_BEFORE_DOS} days",
     f"{PUB_REENLISTMENT} {REENLISTMENT_ACTION_CITATION}", VERIFIED),
    ("dos-reenlistment", "RE code map", "1-series eligible; 2 barred; 3 barred from immediate reenlistment "
     "(prior-service waiver only); 4 ineligible", f"{PUB_REENLISTMENT} Tables 5.2-5.5", VERIFIED),
    ("dos-reenlistment", "4-series waivers", "4F, 4K, 4N: CC/civilian director (4K in an SRB AFSC: AF/A1 or SF/S1); "
     "4E: group CC extension via AFPC/DPPSA (first-termers); 4G: RI 9A000-9A300 retrainees only",
     f"{PUB_REENLISTMENT} Table 5.6", VERIFIED),
    ("dos-reenlistment", "RE 3B / 3C", "ELIGIBLE - NOT YET SRP CONSIDERED (awaiting SRP consideration)",
     f"{PUB_REENLISTMENT} Table 5.4 items 5-6 (\"do not separate\")", "OWNER DECISION 17 Nov 2026."),
    ("dos-reenlistment", "RE 1J", "REVIEW (member elected separation — confirm intent)",
     "Owner decision 2026-11-17; DAFI 36-2606 Table 5.2 item 2 (eligible, elects separation)", "Owner decision."),
    ("dos-reenlistment", "UIF", "Any UIF code = REVIEW", f"Owner spec; {PUB_ADVERSE_ACTIONS} Table 3.2 (UIF codes)",
     VERIFIED),
    ("dos-reenlistment", "CJR", "No effect on the reenlistment status (see the CJR Window run)", "Owner",
     "OWNER DECISION 17 Nov 2026."),
    ("dos-reenlistment", "Extension cap", f"{EXTENSION_CAP_MONTHS} months per enlistment (voluntary; cannot be waived)",
     f"{PUB_REENLISTMENT} paras 6.2.2, 6.6.2.1", VERIFIED),
    ("dos-reenlistment", "Extension reasons", "Table 6.2 reason (Rules 12, 13, 14; Rule 28c personal convenience); "
     "RE 3B and approved 2V cannot extend", f"{PUB_REENLISTMENT} Table 6.2; paras 6.6.5, 6.6.5.1.1", VERIFIED),
    ("dos-reenlistment", "HYT", "DOS at HYT or RE 2T/2U/2V = HYT/RETIREMENT; nothing past the month after HYT",
     f"{PUB_REENLISTMENT} paras 5.11.11, 6.6.9", VERIFIED),
    ("dos-reenlistment", "HYT tenure", "E-4 10, E-5 20, E-6 22, E-7 24, E-8 26, E-9 30 years TAFMS",
     f"{PUB_RETIREMENTS} para 3.10", VERIFIED + " E-1 to E-3 values and the MEL's temporary HYT-extension window "
     "are not in the provided publications — OWNER: keep (17 Nov 2026)."),
    ("deros-option", "DEROS window", f"{DEROS_WINDOW_MONTHS} months", "Owner spec (DEROS_WINDOW_MONTHS)", LOCAL_PREFERENCE),
    ("deros-option", "OS-to-CONUS retainability", f"{OS_TO_CONUS_RETAINABILITY_MONTHS} months from the DEROS month",
     f"{PUB_ASSIGNMENTS} Table 6.4 Rules 10-11; para 6.28.2", VERIFIED),
    ("deros-option", "DEROS Option RIP response", f"{DEROS_RIP_RESPONSE_DAYS} calendar days or involuntarily "
     "extended to DOS", f"{PUB_ASSIGNMENTS} para 6.28.4.3", VERIFIED),
    ("deros-option", "Indefinite DEROS retainability", f"{INDEFINITE_DEROS_RETAINABILITY_MONTHS} months",
     f"{PUB_ASSIGNMENTS} paras 6.28.4.7, 7.5.5.1.3", VERIFIED),
    ("cjr-window", "CJR required (first term)", "CJR required to reenlist", f"{PUB_REENLISTMENT} para 3.1.1",
     VERIFIED),
    ("cjr-window", "CJR window", "Months 32-43 (4-year) / 56-67 (6-year) of enlistment, calendar months",
     f"{PUB_REENLISTMENT} Table 3.1", VERIFIED),
    ("cjr-window", "Only in window", "No CJR outside the window; constrained AFSC: none later",
     f"{PUB_REENLISTMENT} Table 3.1 Note 3; para 3.1.2", VERIFIED),
    ("cjr-window", "UIF", "Shown for information (bars CJR consideration)", f"{PUB_REENLISTMENT} para 3.4.1",
     VERIFIED),
    ("cjr-window", "RE 1R excluded", f"RE {CJR_SELECTED_RE_CODE} (first-termer selected under the SRP) not listed",
     f"{PUB_REENLISTMENT} Table 5.2 item 7", "Owner spec; CJR code not in the export."),
    ("cjr-window", "Approaching", f"Window opens within {CJR_APPROACHING_MONTHS} months", "Owner spec",
     LOCAL_PREFERENCE),
    ("re-code-review", "RE review prefixes", ", ".join(RE_REVIEW_PREFIXES), "Owner spec (RE_REVIEW_PREFIXES)",
     LOCAL_PREFERENCE),
    ("btz-quarterly", "Fully qualified SrA date",
     f"earlier of (later of TAFMSD+{BTZ_TIS_MONTHS} mo and DOR+{BTZ_TIG_WITH_TIS_MONTHS} mo) or DOR+{BTZ_TIG_ONLY_MONTHS} mo",
     "AFI 36-2502 (2 Jul 2026) para 2.2.1", VERIFIED),
    ("btz-quarterly", "BTZ date", f"Fully qualified date minus {BTZ_MONTHS_EARLY} months",
     "AFI 36-2502 (2 Jul 2026) para 2.3.1", VERIFIED),
    ("btz-quarterly", "Quarter table", "Apr-Jun: Jan/Feb, board Mar; Jul-Sep: Apr/May, Jun; Oct-Dec: Jul/Aug, Sep; "
     "Jan-Mar: Oct/Nov, Dec", BTZ_QUARTER_CITATION, VERIFIED),
    ("btz-quarterly", "Quota", f"{BTZ_QUOTA_RATE_PERCENT}%; LARGE unit = {BTZ_LARGE_UNIT_THRESHOLD}+ eligibles; "
     "smaller units pooled into CBB", BTZ_QUOTA_CITATION, VERIFIED),
    ("btz-quarterly", "Quota rounding", "None: exact 15% shown to two decimals; MPF sets the whole number",
     "AFI 36-2502 sets no rounding rule", "OWNER DECISION 17 Nov 2026."),
    ("btz-quarterly", "CBB quota", "15% of the total pooled small-unit eligibles (units under 7 always pool)",
     "AFI 36-2502 (2 Jul 2026) paras 2.3.5, 2.3.7 (para 2.3.5.2 combining noted only)",
     "OWNER DECISION 17 Nov 2026."),
    ("btz-quarterly", "CBB edge rules", "No large units and 2-6 pooled eligibles = 1 CBB quota; 1 eligible base-wide "
     "= MPF commander decides", "AFI 36-2502 (2 Jul 2026) paras 2.3.5.3-2.3.5.4", VERIFIED),
    ("btz-quarterly", "CBB participation", "Units with fewer than 7 eligibles nominate to the CBB; host wing CC sets "
     "CBB guidance", "AFI 36-2502 para 2.4.2.1; AFPC myFSS clarification 17 Nov 2026", VERIFIED),
    ("btz-quarterly", "Previously considered", "GSR 5Q excluded", "AFI 36-2502 (2 Jul 2026) para 2.3.4", VERIFIED),
    ("btz-quarterly", "Projected PCS", "RNLTD on/after first processing month = losing unit considers",
     f"AFI 36-2502 (2 Jul 2026) {BTZ_PCS_CITATION.split(' ', 2)[2]}", VERIFIED),
    ("btz-quarterly", "Prior-service DOR", "Not BTZ eligible; verify manually",
     "AFI 36-2502 (2 Jul 2026) para 2.3.4.4.2", VERIFIED),
    ("btz-quarterly", "Scope", "RegAF A1Cs only", "AFI 36-2502 (2 Jul 2026) Chapter 2", VERIFIED),
]
