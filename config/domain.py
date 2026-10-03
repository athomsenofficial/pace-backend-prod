"""
USAF promotion domain rules — grades, SCODs, TIG, TIS, HYT, PAFSC, RE codes.

Changes when: Air Force policy changes (new HYT limits, updated SCODs, etc.).
"""

from datetime import datetime

# ============================================================================
# GRADE AND PROMOTION MAPPINGS
# ============================================================================

GRADE_MAP = {
    "AB": "E1", "AMN": "E2", "A1C": "E3", "SRA": "E4",
    "SSG": "E5", "TSG": "E6", "MSG": "E7", "SMS": "E8", "CMS": "E9",
    "2LT": "O1", "1LT": "O2", "CPT": "O3", "MAJ": "O4",
    "LTC": "O5", "COL": "O6", "BG": "O7", "MG": "O8", "LTG": "O9", "GEN": "O10",
}

PROMOTION_MAP = {
    "SRA": "E5", "SSG": "E6", "TSG": "E7", "MSG": "E8", "SMS": "E9",
}

PROMOTIONAL_MAP = {
    'SRA': 'SSG', 'SSG': 'TSG', 'TSG': 'MSG', 'MSG': 'SMS', 'SMS': 'CMS',
}

BOARDS = ['E5', 'E6', 'E7', 'E8', 'E9']

OFFICER_RANKS = ['2LT', '1LT', 'CPT', 'MAJ', 'LTC', 'COL', 'BG', 'MG', 'LTG', 'GEN']
ENLISTED_RANKS = ['AB', 'AMN', 'A1C', 'SRA', 'SSG', 'TSG', 'MSG', 'SMS', 'CMS']

# ============================================================================
# CLOSEOUT DATES (SCODs)
# ============================================================================

SCODS = {
    'AB': '31-MAR', 'AMN': '31-MAR', 'A1C': '31-MAR', 'SRA': '31-MAR',
    'SSG': '31-JAN', 'TSG': '30-NOV', 'MSG': '30-SEP', 'SMS': '31-JUL',
}

# ============================================================================
# TIME IN GRADE (TIG)
# ============================================================================

TIG = {
    'AB': '01-FEB', 'AMN': '01-FEB', 'A1C': '01-FEB', 'SRA': '01-SEP',
    'SSG': '01-AUG', 'TSG': '01-JUL', 'MSG': '01-JUL', 'SMS': '01-MAR',
}

TIG_MONTHS_REQUIRED = {
    'AB': 6, 'AMN': 6, 'A1C': 10, 'SRA': 6,
    'SSG': 23, 'TSG': 24, 'MSG': 20, 'SMS': 21,
}

# ============================================================================
# TIME IN SERVICE (TAFMSD) — years required
# ============================================================================

TAFMSD = {
    'AB': 0.25, 'AMN': 0.5, 'A1C': 1.25, 'SRA': 3,
    'SSG': 5, 'TSG': 8, 'MSG': 11, 'SMS': 14,
}

# ============================================================================
# MANDATORY DATE OF SEPARATION (MDOS)
# ============================================================================

MDOS = {
    'AB': '01-SEP', 'AMN': '01-SEP', 'A1C': '01-SEP', 'SRA': '01-SEP',
    'SSG': '01-AUG', 'TSG': '01-AUG', 'MSG': '01-APR', 'SMS': '01-JAN',
}

# ============================================================================
# HIGHER TENURE (HYT) — years
# ============================================================================

MAIN_HIGHER_TENURE = {
    'AB': 6, 'AMN': 6, 'A1C': 8, 'SRA': 10,
    'SSG': 20, 'TSG': 22, 'MSG': 24, 'SMS': 26,
}

EXCEPTION_HIGHER_TENURE = {
    'AB': 8, 'AMN': 8, 'A1C': 10, 'SRA': 12,
    'SSG': 22, 'TSG': 24, 'MSG': 26, 'SMS': 28,
}

hyt_start_date = datetime(2023, 12, 8)
hyt_end_date = datetime(2026, 9, 30)

# ============================================================================
# AFSC SKILL LEVEL MAPPING
# ============================================================================

PAFSC_MAP = {
    'AB': '3', 'AMN': '3', 'A1C': '3', 'SRA': '5',
    'SSG': '7', 'TSG': '7', 'MSG': '7', 'SMS': '9',
}

# ============================================================================
# REENLISTMENT CODES
# ============================================================================

RE_CODES = {
    "2A": "AFPC Denied Reenlistment",
    "2B": "Discharged, General.",
    "2C": "Involuntary separation.",
    "2F": "Undergoing Rehab",
    "2G": "Substance Abuse, Drugs",
    "2H": "Substance Abuse, Alcohol",
    "2J": "Under investigation",
    "2K": "Involuntary Separation.",
    "2M": "Sentenced under UCMJ",
    "2P": "AWOL; deserter.",
    "2W": "Retired and recalled to AD",
    "2X": "Not selected for Reenlistment.",
    "4H": "Article 15.",
    "4I": "Control Roster.",
    "4L": "Separated, Commissioning program.",
    "4M": "Breach of enlistment.",
    "4N": "Convicted, Civil Court.",
}

# ============================================================================
# VALIDATION RULES
# ============================================================================

VALID_GRADE_TRANSITIONS = {
    'AB': ['AMN'], 'AMN': ['A1C'], 'A1C': ['SRA'], 'SRA': ['SSG'],
    'SSG': ['TSG'], 'TSG': ['MSG'], 'MSG': ['SMS'], 'SMS': ['CMS'],
}

MIN_SERVICE_YEAR = 1950
MAX_SERVICE_YEAR = 2050
MIN_PROMOTION_CYCLE_YEAR = 2020
MAX_PROMOTION_CYCLE_YEAR = 2030

AFSC_LENGTH_REQUIREMENTS = {'MIN_LENGTH': 5, 'MAX_LENGTH': 9}

NAME_VALIDATION = {
    'MIN_LENGTH': 2,
    'MAX_LENGTH': 50,
    'ALLOWED_CHARACTERS': r'^[A-Za-z\s\-\'\.]+$',
}
