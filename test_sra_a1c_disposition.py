"""SrA (E5) cycle disposition tests — encodes the stated rules:
  promote (SrA pin) <= 1 Feb (yr+1)        -> ELIGIBLE   (eligible MEL section)
  A1C->SrA pin 2 Feb - 31 Mar (yr+1)       -> INELIGIBLE (on MEL)
  pin > 31 Mar, BTZ-eligible (22mo by SCOD)-> BTZ        (BTZ page only)
  pin > 31 Mar, not BTZ                     -> SKIP       (off MEL)
DOR = current-grade date of rank. A1C projected SrA pin = min(DOR+28mo, max(TAFMSD+36mo, DOR+20mo)).
year=2025 => cycle 26E5, cutoff 01-Feb-2026, SCOD 31-Mar-2026.
"""
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pytest
from board_filter import board_filter

Y = 2025

def bucket(grade, dor, tafmsd, pafsc="3F051"):
    r = board_filter(grade=grade, year=Y, date_of_rank=dor, uif_code=0,
                     uif_disposition_date=None, tafmsd=tafmsd, re_status=None,
                     pafsc=pafsc, two_afsc=None, three_afsc=None, four_afsc=None,
                     member_name="T", roster_type="mel", logger=None)
    return {"eligible": "ELIGIBLE", "discrepancy": "ELIGIBLE", "btz": "BTZ",
            "ineligible": "INELIGIBLE", "skip": "SKIP"}[r.status]

def a1c_dor(pin):       # A1C DOR so standard pin (28mo path) == pin
    return pin - relativedelta(months=28)

# (label, grade, dor, tafmsd, expected)
CASES = [
    # --- actual SrA members ---
    ("SrA DOR 15-Jan-2026",        "SRA", datetime(2026,1,15), datetime(2021,6,1), "ELIGIBLE"),
    ("SrA DOR 01-Feb-2026 (bnd)",  "SRA", datetime(2026,2,1),  datetime(2021,6,1), "ELIGIBLE"),
    ("SrA DOR 02-Feb-2026 (win)",  "SRA", datetime(2026,2,2),  datetime(2021,6,1), "INELIGIBLE"),
    ("SrA DOR 31-Mar-2026 (win)",  "SRA", datetime(2026,3,31), datetime(2021,6,1), "INELIGIBLE"),
    # --- A1C projected to SrA (TAFMSD ~ DOR, so 28mo TIG path governs) ---
    ("A1C pin 15-Jan-2026",        "A1C", a1c_dor(datetime(2026,1,15)), a1c_dor(datetime(2026,1,15)), "ELIGIBLE"),
    ("A1C pin 01-Feb-2026 (bnd)",  "A1C", a1c_dor(datetime(2026,2,1)),  a1c_dor(datetime(2026,2,1)),  "ELIGIBLE"),
    ("A1C pin 15-Feb-2026 (win)",  "A1C", a1c_dor(datetime(2026,2,15)), a1c_dor(datetime(2026,2,15)), "INELIGIBLE"),
    ("A1C pin 15-Mar-2026 (win)",  "A1C", a1c_dor(datetime(2026,3,15)), a1c_dor(datetime(2026,3,15)), "INELIGIBLE"),
    ("A1C pin 15-Apr-2026 (BTZ)",  "A1C", a1c_dor(datetime(2026,4,15)), a1c_dor(datetime(2026,4,15)), "BTZ"),
    ("A1C junior (skip)",          "A1C", datetime(2025,3,1),  datetime(2025,3,1),  "SKIP"),
]

@pytest.mark.parametrize("label,grade,dor,tafmsd,expected", CASES, ids=[c[0] for c in CASES])
def test_disposition(label, grade, dor, tafmsd, expected):
    assert bucket(grade, dor, tafmsd) == expected, f"{label}: got {bucket(grade,dor,tafmsd)}, want {expected}"

def main():
    print(f"\nSrA (E5) disposition — year={Y} => 26E5 (cutoff 01-Feb-2026, SCOD 31-Mar-2026)\n")
    print(f"{'CASE':30} {'GOT':12} {'EXPECT':12} OK?")
    print("-"*64)
    npass = 0
    for label, grade, dor, tafmsd, expected in CASES:
        got = bucket(grade, dor, tafmsd)
        ok = got == expected
        npass += ok
        print(f"{label:30} {got:12} {expected:12} {'OK' if ok else '** MISMATCH **'}")
    print(f"\n{npass}/{len(CASES)} pass")

if __name__ == "__main__":
    main()
