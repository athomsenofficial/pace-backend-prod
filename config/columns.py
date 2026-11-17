"""
Column definitions for roster data and PDF output.

Changes when: a new data field is added to the roster format.
"""

REQUIRED_COLUMNS = [
    'FULL_NAME', 'GRADE', 'ASSIGNED_PAS_CLEARTEXT', 'DAFSC', 'DOR',
    'DATE_ARRIVED_STATION', 'TAFMSD', 'REENL_ELIG_STATUS', 'ASSIGNED_PAS', 'PAFSC',
]

OPTIONAL_COLUMNS = [
    'GRADE_PERM_PROJ', 'UIF_CODE', 'UIF_DISPOSITION_DATE', '2AFSC', '3AFSC', '4AFSC',
]

PDF_COLUMNS = [
    'FULL_NAME', 'GRADE', 'DATE_ARRIVED_STATION', 'DAFSC',
    'ASSIGNED_PAS_CLEARTEXT', 'DOR', 'TAFMSD', 'ASSIGNED_PAS',
]

MPF_LIST_COLUMNS = [
    'FULL_NAME', 'GRADE', 'ASSIGNED_PAS_CLEARTEXT', 'DAFSC', 'DOR', 'TAFMSD',
]

# ============================================================================
# RECURRING ROSTERS — header aliases
# ----------------------------------------------------------------------------
# Canonical column name -> accepted header variants. Headers are matched after
# the same normalisation file_ingestion.ingest_file applies (strip + upper),
# plus spaces / hyphens / dots collapsed to "_" so "Date of Separation" and
# "DATE-OF-SEPARATION" both match DATE_OF_SEPARATION. The canonical name itself
# is always accepted; list it first. Order of keys = order reported to clients.
# Changes when: a roster export (MilPDS query, AMS, unit tracker) uses a new
# header for an existing field.
# ============================================================================

ROSTER_COLUMN_ALIASES = {
    'FULL_NAME': ['FULL_NAME', 'NAME', 'MEMBER_NAME', 'NAME_FULL'],
    'GRADE': ['GRADE', 'RANK', 'CURRENT_GRADE', 'GRADE_ABBR'],
    'ASSIGNED_PAS_CLEARTEXT': ['ASSIGNED_PAS_CLEARTEXT', 'UNIT', 'UNIT_NAME', 'ORGANIZATION'],
    'ASSIGNED_PAS': ['ASSIGNED_PAS', 'PAS', 'PASCODE', 'PAS_CODE'],
    'DAFSC': ['DAFSC', 'DUTY_AFSC'],
    'DOR': ['DOR', 'DATE_OF_RANK'],
    'TAFMSD': ['TAFMSD', 'TAFMS_DATE'],
    # DOS and ETS are DIFFERENT fields in the alpha roster: ETS = expiration of
    # term of service (flips to match DOS when an extension takes effect); DOS
    # already includes pending (not yet effective) extensions. Never alias them.
    'DOS': ['DOS', 'DATE_OF_SEPARATION', 'DOS_DATE'],
    'ETS': ['ETS', 'EXPIRATION_TERM_OF_SERVICE', 'ETS_DATE'],
    'DOE': ['DOE', 'DATE_OF_ENLISTMENT', 'DOE_DATE'],
    'DEROS': ['DEROS', 'DEROS_DATE'],
    'RNLTD': ['RNLTD', 'REPORT_NLT_DATE', 'ASSIGNMENT_RNLTD'],
    'ASSIGNMENT_TYPE': ['ASSIGNMENT_TYPE', 'ASGN_TYPE', 'ASSIGNMENT_TOUR_TYPE'],
    'TOUR_LENGTH_MONTHS': ['TOUR_LENGTH_MONTHS', 'TOUR_LENGTH', 'TOUR_LENGTH_MOS'],
    'DATE_ARRIVED_STATION': ['DATE_ARRIVED_STATION', 'DAS', 'DATE_ARRIVED'],
    'UIF_CODE': ['UIF_CODE', 'UIF'],
    'UIF_DISPOSITION_DATE': ['UIF_DISPOSITION_DATE', 'UIF_DISP_DATE'],
    'REENL_ELIG_STATUS': ['REENL_ELIG_STATUS', 'RE_CODE', 'REENL_ELIGIBILITY_STATUS', 'REENLISTMENT_ELIGIBILITY'],
    # Used by the retention / BTZ roster runs (roster_runs/).
    'CAFSC': ['CAFSC', 'CONTROL_AFSC'],
    'PAFSC': ['PAFSC', 'PRIMARY_AFSC'],
    '2AFSC': ['2AFSC', 'SECOND_AFSC'],
    '3AFSC': ['3AFSC', 'THIRD_AFSC'],
    '4AFSC': ['4AFSC', 'FOURTH_AFSC'],
    'GAINING_PAS': ['GAINING_PAS', 'GAINING_PASCODE'],
    'GAINING_PAS_CLEARTEXT': ['GAINING_PAS_CLEARTEXT', 'GAINING_UNIT'],
    'ANG_ROLL_INDICATOR': ['ANG_ROLL_INDICATOR'],
    'AFR_SECTION_ID': ['AFR_SECTION_ID'],
    'GRADE_STATUS_REASON': ['GRADE_STATUS_REASON', 'GSR', 'GRADE_STATUS_RSN'],
}

# Headers that must NEVER be stored in a recurring-roster session, even if an
# alias above were ever added for them (defence in depth; checked at upload and
# by tests). Matched against the normalised header (upper, separators -> "_").
ROSTER_PII_DENYLIST_PATTERNS = (
    r'^DATE_OF_BIRTH$', r'^DOB$', r'^BIRTH_?DATE$', r'^AGE$',
    r'^HOME_', r'PHONE', r'ADDRESS', r'^MARITAL',
    r'SSN', r'SSAN', r'^SOCIAL_SECURITY', r'^DOD_?ID', r'^EDIPI',
    r'^SUPV_NAME$',
)

# Columns a recurring-roster upload must contain (after alias resolution).
ROSTER_UPLOAD_REQUIRED_COLUMNS = ['FULL_NAME', 'GRADE']
