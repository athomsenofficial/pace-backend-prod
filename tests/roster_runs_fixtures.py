"""Synthetic alpha roster (no real PII) with the SAME 76 headers as the real export.

Names are fake (TESTALPHA, ADAM ...), PASCODEs are ZZ*TEST, and the PII columns
carry obviously fake sentinel values so tests can prove they are never stored.
"""

import io
from datetime import date

import pandas as pd
from openpyxl import Workbook

from file_ingestion import ingest_file
from roster_rules import canonicalize_dataframe

AS_OF = date(2026, 11, 17)

# Exactly as listed in docs/specs/00-decisions-and-data.md (None = blank header).
ALPHA_HEADERS = [
    "FULL_NAME", None, "GRADE", "RECORD_STATUS", "ASSIGNED_PAS", "ASSIGNED_PAS_CLEARTEXT", "OFFICE_SYMBOL",
    "DUTY_TITLE", "DUTY_START_DATE", "DOR", "DAFSC", "CAFSC", "PAFSC", "2AFSC", "3AFSC", "4AFSC",
    "DATE_ARRIVED_STATION", "DUTY_PHONE", "TAFMSD", "DOE", "DOS", "ETS", "DATE_OF_BIRTH", "HOME_ADDRESS",
    "HOME_CITY", "HOME_STATE", "HOME_ZIP_CODE", "SUPV_NAME", "GRADE_PERM_PROJ", "UIF_CODE",
    "UIF_DISPOSITION_DATE", "PROJ_EVAL_CLOSE_DATE", "MARITAL_STATUS", "RNLTD", "GAINING_PAS",
    "GAINING_PAS_CLEARTEXT", "LAST_EVAL_RATING", "LAST_EVAL_CLOSE_DATE", "PERF_INDICATOR", None,
    "SUPV_BEGIN_DATE", "REENL_ELIG_STATUS", "HOME_PHONE_NUMBER", "AGE", "DEROS", "DEPLOY_ADMIN_STATUS",
    "DEPLOY_ADMIN_STATUS_CLEARTEXT", "DEPLOY_ADMIN_STOP_DATE", "DEPLOY_LEGAL_STATUS",
    "DEPLOY_LEGAL_STATUS_CLEARTEXT", "DEPLOY_LEGAL_STOP_DATE", "DEPLOY_PHYS_STATUS",
    "DEPLOY_PHYS_STATUS_CLEARTEXT", "DEPLOY_PHYS_STOP_DATE", "DEPLOY_TIME_STATUS",
    "DEPLOY_TIME_STATUS_CLEARTEXT", "DEPLOY_TIME_STOP_DATE", "AVAILABILITY_CODE", "AVAILABILITY_CODE_CLEARTEXT",
    "AVAILABILITY_DATE", "AVAILABILITY_STATUS", "AVAILABILITY_STATUS_CLEARTEXT", "LIMITATION_CODE",
    "LIMITATION_CODE_CLEARTEXT", "LIMITATION_END_DATE", "SEC_CLR", "TYPE_SEC_INV", "DT_SCTY_INVES_COMPL",
    "SEC_ELIG_DT", "TECH_ID", "ACDU_STATUS", "ANG_ROLL_INDICATOR", "AFR_SECTION_ID", "CIVILIAN_ART_ID",
    "ATTACHED_PAS", "FUNCTIONAL_CATEGORY",
]
assert len(ALPHA_HEADERS) == 76

# Sentinel fake PII — must never reach the session.
PII_SENTINELS = {
    "DATE_OF_BIRTH": "01-JAN-1901",
    "HOME_ADDRESS": "1 FAKEPII STREET",
    "HOME_CITY": "FAKEPIICITY",
    "HOME_STATE": "FAKEPIISTATE",
    "HOME_ZIP_CODE": "FAKEPIIZIP",
    "HOME_PHONE_NUMBER": "555-0100-FAKE",
    "DUTY_PHONE": "555-0199-FAKE",
    "MARITAL_STATUS": "FAKEMARITAL",
    "AGE": "FAKEPIIAGE",
    "SUPV_NAME": "FAKESUPERVISOR, ZED",
}

_counter = [0]


def member(name: str, grade: str, **fields) -> dict:
    """One alpha-roster row; unspecified columns are blank except fake PII sentinels."""
    _counter[0] += 1
    row = {h: None for h in ALPHA_HEADERS if h}
    row.update(PII_SENTINELS)
    row.update({
        "FULL_NAME": name,
        "GRADE": grade,
        "RECORD_STATUS": "ACTIVE",
        "ASSIGNED_PAS": "ZZ1TEST",
        "ASSIGNED_PAS_CLEARTEXT": "1 TEST SQ",
        "OFFICE_SYMBOL": "TST",
        "DUTY_TITLE": "TEST DUTY",
        "TECH_ID": f"T{_counter[0]:05d}",
    })
    row.update(fields)
    return row


def alpha_xlsx(rows: list[dict], extra_headers: list[str] = ()) -> bytes:
    """Write rows to an in-memory XLSX with the 76 real headers (+ optional extras)."""
    headers = ALPHA_HEADERS + list(extra_headers)
    wb = Workbook()
    ws = wb.active
    ws.title = "ReportOutput"
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h) if h else None for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def alpha_records(rows: list[dict], extra_headers: list[str] = ()) -> tuple[list[dict], set[str]]:
    """Round-trip through the real ingestion + canonicalisation path, like an upload."""
    df = ingest_file(alpha_xlsx(rows, extra_headers), "alpha.xlsx", None, [])
    canonical, columns, _unmapped, _warnings = canonicalize_dataframe(df)
    canonical = canonical.astype(object).where(pd.notna(canonical), None)
    return canonical.to_dict(orient="records"), set(columns)
