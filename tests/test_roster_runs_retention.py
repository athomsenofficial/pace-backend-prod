"""Runs 1-3 (DOS/Reenlistment, DEROS Option, RE Code Management) + upload/API/PII/export.

Synthetic roster only (tests/roster_runs_fixtures.py, the real 76 headers).
As-of date fixed at 17-NOV-2026.
"""

import io
import json
import logging
import os
from datetime import date

import fitz
import pytest
from openpyxl import load_workbook

from config.columns import ROSTER_COLUMN_ALIASES
from config.domain import RE_CODES
from config.retention import (
    REENLISTMENT_RE_CODES, RE_DEFINITION_UNVERIFIED, RETENTION_FOOTER, STATUS_ELIGIBLE, STATUS_ELIGIBLE_NYSC,
    STATUS_HYT, STATUS_INELIGIBLE, STATUS_INELIGIBLE_WAIVABLE, STATUS_REVIEW,
)
from roster_runs.common import INDEFINITE, parse_roster_date
from roster_runs.exports import build_pdf, build_xlsx
from roster_runs.registry import RunError, execute
from routers.rosters import is_pii_column
from tests.roster_runs_fixtures import AS_OF, PII_SENTINELS, alpha_records, alpha_xlsx, member

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def run(run_id, rows, params=None, as_of=AS_OF, pascodes=None):
    records, columns = alpha_records(rows)
    return execute(run_id, records, columns, params or {}, as_of, pascodes)


def where(result, name):
    """(location, row) for a member: 'rows' or the bucket id. Fails if absent or duplicated."""
    hits = [("rows", r) for r in result.rows if r["name"] == name]
    for b in result.buckets:
        hits += [(b.id, r) for r in b.rows if r["name"] == name]
    assert len(hits) == 1, f"{name}: expected exactly one placement, got {[h[0] for h in hits]}"
    return hits[0]


def first_termer(name, doe, dos, ets=None, re="1R", **kw):
    return member(name, kw.pop("grade", "SRA"), DOE=doe, TAFMSD=doe, DOS=dos, ETS=ets if ets is not None else dos,
                  REENL_ELIG_STATUS=re, **kw)


def careerist(name, dos, re="1P", grade="SSG", **kw):
    # TAFMSD 2016 + reenlisted 2022: HYT (SSG 20 yrs) is 2036, far from DOS.
    return member(name, grade, DOE="01-MAR-2022", TAFMSD="01-MAR-2016", DOS=dos, ETS=kw.pop("ets", dos),
                  REENL_ELIG_STATUS=re, **kw)


# =============================================================================
# Dates
# =============================================================================

class TestDateParsing:
    def test_dd_mmm_yyyy(self):
        assert parse_roster_date("15-JAN-2024").value == date(2024, 1, 15)

    def test_year_3888_is_indefinite_not_data_issue(self):
        v = parse_roster_date("31-DEC-3888")
        assert v.indefinite and v.out() == INDEFINITE

    def test_iso_and_excel_cells(self):
        assert parse_roster_date("2024-01-15T00:00:00").value == date(2024, 1, 15)
        assert parse_roster_date("3888-12-31").indefinite

    def test_blank_and_bad(self):
        assert parse_roster_date(None).status == "blank"
        assert parse_roster_date("  ").status == "blank"
        assert parse_roster_date("31-FOO-2027").status == "bad"
        assert parse_roster_date("30-FEB-2027").status == "bad"


# =============================================================================
# RUN 1 — DOS / Reenlistment
# =============================================================================

class TestRun1Extensions:
    def test_four_year_first_termer_no_extension(self):
        r = run("dos-reenlistment", [first_termer("TESTALPHA, ADAM", "15-JAN-2023", "14-JAN-2027")])
        loc, row = where(r, "TESTALPHA, ADAM")
        assert loc == "rows"
        assert row["status"] == STATUS_ELIGIBLE
        assert row["first_term"] == "Yes" and row["term"] == "4-year"
        assert row["pending_extension_months"] == 0
        assert row["extension_remaining"] == "48"
        assert row["months_remaining"] == 1
        assert row["action_by"] == date(2026, 9, 16)  # DOS - 120 days
        assert row["action_overdue"] is True

    def test_pending_extension_is_ets_to_dos(self):
        # ETS 14-JAN-2027, DOS 14-JUL-2027: 6-month extension not yet effective.
        r = run("dos-reenlistment", [first_termer("TESTBRAVO, BEN", "15-JAN-2023", "14-JUL-2027",
                                                  ets="14-JAN-2027")])
        _, row = where(r, "TESTBRAVO, BEN")
        assert row["pending_extension_months"] == 6
        assert row["extension_basis"] == "ETS vs DOS"
        assert row["term"] == "4-year"
        assert row["extension_remaining"] == "42"

    def test_effective_extension_reported_unknown(self):
        # ETS already flipped: ETS-DOE = 54 months -> "effective extensions unknown".
        r = run("dos-reenlistment", [first_termer("TESTCHARLIE, CAL", "15-JUN-2022", "14-DEC-2026")])
        _, row = where(r, "TESTCHARLIE, CAL")
        assert "Effective extensions unknown (ETS-DOE = 54 months)" in row["extension_history"]
        assert row["extension_remaining"] == "<= 48 (verify)"
        assert row["term"] == "4-year"

    def test_six_year_first_termer_72_is_ambiguous(self):
        r = run("dos-reenlistment", [first_termer("TESTDELTA, DAN", "01-AUG-2021", "31-JUL-2027")])
        _, row = where(r, "TESTDELTA, DAN")
        assert row["term"].startswith("AMBIGUOUS")
        assert row["extension_remaining"] == "24-48"
        assert "4-year" in row["cjr"] and "6-year" in row["cjr"]

    def test_fallback_heuristic_when_ets_blank(self):
        rows = [
            first_termer("TESTECHO, EVE", "15-JAN-2023", "14-JAN-2027", ets=""),
            first_termer("TESTFOX, FAY", "15-JAN-2023", "14-JUL-2027", ets=""),
            first_termer("TESTGOLF, GUS", "01-AUG-2021", "31-JUL-2027", ets=""),
            first_termer("TESTHOTEL, HAL", "01-JUN-2021", "31-AUG-2027", ets=""),
        ]
        r = run("dos-reenlistment", rows)
        _, echo = where(r, "TESTECHO, EVE")
        assert echo["extension_history"] == "4-year, no extension"
        assert echo["extension_basis"].startswith("DOE->DOS heuristic")
        assert echo["extension_remaining"] == "48"
        _, fox = where(r, "TESTFOX, FAY")
        assert fox["extension_history"] == "4-year plus 6 months extended"
        assert fox["extension_remaining"] == "42"
        _, golf = where(r, "TESTGOLF, GUS")
        assert "ambiguous" in golf["extension_history"]
        assert golf["extension_remaining"] == "24-48"
        _, hotel = where(r, "TESTHOTEL, HAL")
        assert hotel["term"].startswith("Extended")
        # 75 months: 6-year + 3 or 4-year + 27
        assert hotel["extension_remaining"] == "21-45"
        assert any("DATA ISSUE: ETS missing" in x for x in echo["reasons"])

    def test_reenlisted_extension_history_unknown(self):
        r = run("dos-reenlistment", [careerist("TESTINDIA, IVY", "31-MAY-2027", ets="28-FEB-2027")])
        _, row = where(r, "TESTINDIA, IVY")
        assert row["first_term"] == "No"
        assert row["extension_history"] == "Extension history unknown, verify in MilPDS"
        assert row["pending_extension_months"] == 3
        assert row["extension_remaining"] == "<= 45 (verify)"
        assert row["cjr"] == "N/A (not first term)"

    def test_dos_before_ets_is_review(self):
        r = run("dos-reenlistment", [careerist("TESTJULIET, JO", "31-MAY-2027", ets="31-AUG-2027")])
        _, row = where(r, "TESTJULIET, JO")
        assert row["status"] == STATUS_REVIEW
        assert any("DOS is earlier than ETS" in x for x in row["reasons"])


class TestRun1Cjr:
    def test_first_termer_past_cjr_window_without_1r_flagged(self):
        r = run("dos-reenlistment", [first_termer("TESTKILO, KAY", "01-JAN-2023", "31-DEC-2026", re="1M")])
        _, row = where(r, "TESTKILO, KAY")
        assert row["month_of_enlistment"] == 47
        assert "past window" in row["cjr"]
        assert row["status"] == STATUS_REVIEW
        assert any("CJR required to reenlist (DAFI 36-2606 para 3.1.1)" in x for x in row["reasons"])

    def test_first_termer_with_1r_not_flagged(self):
        r = run("dos-reenlistment", [first_termer("TESTLIMA, LEO", "01-JAN-2023", "31-DEC-2026", re="1R")])
        _, row = where(r, "TESTLIMA, LEO")
        assert row["status"] == STATUS_ELIGIBLE
        assert not any("CJR" in x for x in row["reasons"])

    def test_first_termer_in_window(self):
        # 6-year first-termer, month 64 of 72 -> 6-year window 59-67 (ambiguous 72 checks both).
        r = run("dos-reenlistment", [first_termer("TESTMIKE, MO", "01-AUG-2021", "31-JUL-2027", re="3C")])
        _, row = where(r, "TESTMIKE, MO")
        assert "6-year: in window (59-67)" in row["cjr"]
        assert row["status"] == STATUS_INELIGIBLE_WAIVABLE


class TestRun1ReCodes:
    @pytest.mark.parametrize("code,status", [
        ("1R", STATUS_ELIGIBLE),
        ("1P", STATUS_ELIGIBLE),
        ("1M", STATUS_ELIGIBLE_NYSC),
        ("1J", STATUS_REVIEW),
        ("2X", STATUS_INELIGIBLE),
        ("2M", STATUS_INELIGIBLE),
        ("2U", STATUS_HYT),
        ("2V", STATUS_HYT),
        ("3A", STATUS_INELIGIBLE_WAIVABLE),
        ("3B", STATUS_INELIGIBLE_WAIVABLE),
        ("3C", STATUS_INELIGIBLE_WAIVABLE),
        ("4D", STATUS_INELIGIBLE),
        ("4K", STATUS_INELIGIBLE_WAIVABLE),
        ("4E", STATUS_INELIGIBLE_WAIVABLE),
        ("9Z", STATUS_REVIEW),
        ("", STATUS_REVIEW),
    ])
    def test_each_series(self, code, status):
        r = run("dos-reenlistment", [careerist("TESTNOVEMBER, NED", "15-JUN-2027", re=code)])
        _, row = where(r, "TESTNOVEMBER, NED")
        assert row["status"] == status, row["reasons"]

    def test_1j_flagged_as_owner_decision(self):
        r = run("dos-reenlistment", [careerist("TESTOSCAR, OLA", "15-JUN-2027", re="1J")])
        _, row = where(r, "TESTOSCAR, OLA")
        assert "RE 1J: member elected separation — confirm intent" in row["reasons"]
        assert r.summary["owner_decisions"] and "1J" in r.summary["owner_decisions"][0]

    def test_unknown_code_never_silent_pass(self):
        r = run("dos-reenlistment", [careerist("TESTPAPA, PIA", "15-JUN-2027", re="9Z")])
        _, row = where(r, "TESTPAPA, PIA")
        assert row["re_definition"] == RE_DEFINITION_UNVERIFIED
        assert any("not in PACE RE map" in x for x in row["reasons"])

    def test_waiver_authority(self):
        r = run("dos-reenlistment", [careerist("TESTQUEBEC, QI", "15-JUN-2027", re="4K"),
                                     careerist("TESTROMEO, RAY", "15-JUN-2027", re="4E")])
        assert where(r, "TESTQUEBEC, QI")[1]["re_waiver_authority"] == "Unit CC"
        assert where(r, "TESTROMEO, RAY")[1]["re_waiver_authority"] == "AFPC"

    def test_3b_cannot_extend(self):
        r = run("dos-reenlistment", [careerist("TESTSIERRA, SUE", "15-JUN-2027", re="3B")])
        assert where(r, "TESTSIERRA, SUE")[1]["extension_note"] == "RE 3B: cannot extend."

    def test_re_map_covers_codes_seen_and_undefined_codes_not_invented(self):
        for code in "1R 1P 1M 1J 3C 3B 3A 4K 4D 2U 2V 2M".split():
            assert code in REENLISTMENT_RE_CODES
        assert REENLISTMENT_RE_CODES["1K"]["definition"] == RE_DEFINITION_UNVERIFIED
        assert REENLISTMENT_RE_CODES["4D"]["definition"] == RE_DEFINITION_UNVERIFIED

    def test_mel_re_codes_untouched(self):
        assert RE_CODES["4I"] == "Control Roster." and len(RE_CODES) == 17


class TestRun1HytUif:
    def test_career_airman_dos_equals_hyt(self):
        # TSG, TAFMSD 15-MAR-2005 -> HYT 22 yrs = 15-MAR-2027; DOS 31-MAR-2027.
        r = run("dos-reenlistment", [member("TESTTANGO, TIM", "TSG", DOE="01-APR-2021", TAFMSD="15-MAR-2005",
                                            ETS="31-MAR-2027", DOS="31-MAR-2027", REENL_ELIG_STATUS="1P")])
        _, row = where(r, "TESTTANGO, TIM")
        assert row["status"] == STATUS_HYT
        assert row["hyt_date"] == date(2027, 3, 15) and row["hyt_basis"] == "computed"

    def test_uif_disposition_before_dos(self):
        r = run("dos-reenlistment", [careerist("TESTUNIFORM, UMA", "15-JUN-2027", UIF_CODE="1",
                                               UIF_DISPOSITION_DATE="01-FEB-2027")])
        _, row = where(r, "TESTUNIFORM, UMA")
        assert row["status"] == STATUS_REVIEW
        assert row["uif_vs_dos"] == "before DOS"
        assert row["uif_disposition_date"] == date(2027, 2, 1)

    def test_uif_disposition_after_dos(self):
        r = run("dos-reenlistment", [careerist("TESTVICTOR, VAL", "15-JUN-2027", UIF_CODE="3",
                                               UIF_DISPOSITION_DATE="01-DEC-2027")])
        _, row = where(r, "TESTVICTOR, VAL")
        assert row["uif_vs_dos"] == "on/after DOS"
        assert row["status"] == STATUS_REVIEW

    def test_uif_blocks_cjr_first_termer(self):
        r = run("dos-reenlistment", [first_termer("TESTWHISKEY, WES", "15-JAN-2023", "14-JAN-2027",
                                                  UIF_CODE="1", UIF_DISPOSITION_DATE="01-MAR-2027")])
        _, row = where(r, "TESTWHISKEY, WES")
        assert any("UIF blocks a CJR" in x for x in row["reasons"])

    def test_uif_zero_is_no_uif(self):
        r = run("dos-reenlistment", [careerist("TESTXRAY, XAN", "15-JUN-2027", UIF_CODE="0")])
        assert where(r, "TESTXRAY, XAN")[1]["status"] == STATUS_ELIGIBLE


class TestRun1Buckets:
    def test_buckets_and_nothing_dropped(self):
        rows = [
            careerist("TESTYANKEE, YUL", "15-JUN-2027"),
            careerist("TESTZULU, ZOE", "01-JAN-2027"),
            careerist("TESTEXPIRED, EDD", "01-OCT-2026"),
            careerist("TESTBLANK, BO", ""),
            careerist("TESTBAD, BEA", "31-FOO-2027"),
            member("TESTCHIEF, CY", "CMS", DOE="01-JAN-2000", TAFMSD="01-JAN-1998", DOS="31-DEC-3888",
                   ETS="31-DEC-3888", REENL_ELIG_STATUS="1P"),
            member("TESTOFFICER, OZ", "CPT", DOS="31-DEC-3888"),
            member("TESTMAJOR, MAX", "MAJ", DOS="31-DEC-3888"),
            careerist("TESTFAR, FIN", "15-JUN-2029"),
            member("TESTNOGRADE, NIA", "", DOS="15-JUN-2027"),
        ]
        r = run("dos-reenlistment", rows)
        assert [x["name"] for x in r.rows] == ["TESTZULU, ZOE", "TESTYANKEE, YUL"]  # soonest first
        assert where(r, "TESTEXPIRED, EDD")[0] == "dos_expired"
        assert where(r, "TESTBLANK, BO") == ("data_issue", where(r, "TESTBLANK, BO")[1])
        assert where(r, "TESTBLANK, BO")[1]["issues"] == ["DOS missing"]
        assert where(r, "TESTBAD, BEA")[1]["issues"] == ["DOS unreadable"]
        assert where(r, "TESTCHIEF, CY")[0] == "indefinite_dos"
        assert where(r, "TESTNOGRADE, NIA")[0] == "data_issue"
        names = [x["name"] for x in r.rows] + [x["name"] for b in r.buckets for x in b.rows]
        assert "TESTOFFICER, OZ" not in names and "TESTMAJOR, MAX" not in names
        s = r.summary
        assert s["officers_excluded"] == 2 and s["outside_window"] == 1
        assert s["total_records"] == len(rows)
        accounted = (s["in_window"] + s["dos_expired"] + s["indefinite_dos"] + s["data_issue"]
                     + s["outside_window"] + s["officers_excluded"])
        assert accounted == len(rows)

    def test_window_param_and_validation(self):
        rows = [careerist("TESTWIN, WIN", "15-FEB-2027")]
        assert run("dos-reenlistment", rows, {"dos_window_months": 3}).rows
        assert not run("dos-reenlistment", rows, {"dos_window_months": 2}).rows
        with pytest.raises(RunError) as e:
            run("dos-reenlistment", rows, {"dos_window_months": "abc"})
        assert e.value.invalid_params == ["dos_window_months"]

    def test_pascode_filter(self):
        rows = [careerist("TESTONE, ONE", "15-JUN-2027"),
                careerist("TESTTWO, TWO", "15-JUN-2027", ASSIGNED_PAS="ZZ2TEST")]
        r = run("dos-reenlistment", rows, pascodes=["zz2test"])
        assert [x["name"] for x in r.rows] == ["TESTTWO, TWO"]


# =============================================================================
# RUN 2 — DEROS Option
# =============================================================================

def overseas(name, deros, dos, **kw):
    return careerist(name, dos, DEROS=deros, **kw)


class TestRun2:
    def test_flags_and_buckets(self):
        rows = [
            overseas("TESTOK, OKA", "15-MAR-2027", "01-JUN-2029", RNLTD="15-MAR-2027"),
            overseas("TESTNOASG, NIK", "15-MAR-2027", "01-JUN-2029"),
            overseas("TESTSHORT, SAM", "15-MAR-2027", "29-FEB-2028", GAINING_PAS="ZZ9GAIN"),
            overseas("TESTEXACT, EXA", "15-MAR-2027", "01-MAR-2028", RNLTD="15-MAR-2027"),
            overseas("TESTBOTH, BOB", "15-MAR-2027", "30-SEP-2027"),
            overseas("TESTSEP, SEP", "15-MAR-2027", "01-MAR-2027"),
            overseas("TESTINDEF, IDA", "31-DEC-3888", "01-MAY-2027"),
            overseas("TESTCONUS, CON", "", "01-JUN-2029"),
            overseas("TESTPAST, PAT", "01-OCT-2026", "01-JUN-2029"),
            overseas("TESTNODOS, NOD", "15-MAR-2027", ""),
            overseas("TESTFAR, FAR", "15-MAR-2028", "01-JUN-2029"),
            member("TESTCAPTAIN, CAP", "CPT", DEROS="15-MAR-2027", DOS="31-DEC-3888"),
        ]
        r = run("deros-option", rows)
        assert {x["name"] for x in r.rows} == {"TESTNOASG, NIK", "TESTSHORT, SAM", "TESTBOTH, BOB"}

        _, noasg = where(r, "TESTNOASG, NIK")
        assert noasg["flags"] == ["NO_ASSIGNMENT"] and noasg["months_short"] is None

        _, short = where(r, "TESTSHORT, SAM")
        assert short["flags"] == ["INSUFFICIENT_RETAINABILITY"]
        assert short["months_short"] == 1 and short["required_dos_month"] == "MAR-2028"
        assert short["run1_status"] == STATUS_ELIGIBLE  # pulled from Run 1
        assert short["extension_remaining"] == "<= 48 (verify)"
        assert any("30 days of signing the DEROS Option RIP" in n for n in short["notes"])
        assert "Gaining ZZ9GAIN" in short["assignment"]

        _, both = where(r, "TESTBOTH, BOB")
        assert both["flags"] == ["NO_ASSIGNMENT", "INSUFFICIENT_RETAINABILITY"] and both["months_short"] == 6

        assert where(r, "TESTSEP, SEP")[0] == "separating_from_overseas"
        loc, indef = where(r, "TESTINDEF, IDA")
        assert loc == "indefinite_deros" and indef["deros"] == INDEFINITE
        assert any("8 months" in n for n in indef["notes"])
        assert indef["notes"][0].startswith("Less than 8 months retainability")
        assert where(r, "TESTCONUS, CON")[0] == "blank_deros"
        assert where(r, "TESTPAST, PAT")[0] == "deros_past"
        assert where(r, "TESTNODOS, NOD")[0] == "data_issue"
        names = [x["name"] for x in r.rows] + [x["name"] for b in r.buckets for x in b.rows]
        assert "TESTCAPTAIN, CAP" not in names and "TESTOK, OKA" not in names
        s = r.summary
        assert s["in_window_no_flags"] == 2 and s["outside_window"] == 1 and s["officers_excluded"] == 1
        assert s["both_flags"] == 1 and s["insufficient_retainability"] == 2

    def test_retainability_param(self):
        rows = [overseas("TESTPARAM, PAM", "15-MAR-2027", "01-OCT-2027", RNLTD="15-MAR-2027")]
        assert not run("deros-option", rows, {"os_to_conus_retainability_months": 6}).rows
        assert run("deros-option", rows, {"os_to_conus_retainability_months": 8}).rows[0]["months_short"] == 1


# =============================================================================
# RUN 3 — RE Code Management
# =============================================================================

class TestRun3:
    def test_default_prefixes_sorted_by_dos(self):
        rows = [
            careerist("TESTR2X, AA", "15-JUN-2028", re="2X"),
            careerist("TESTR4K, BB", "15-JAN-2027", re="4K", UIF_CODE="2", UIF_DISPOSITION_DATE="01-MAR-2027"),
            careerist("TESTR1R, CC", "15-JAN-2027", re="1R"),
            careerist("TESTR3B, DD", "15-JAN-2027", re="3B"),
            careerist("TESTR2Z, EE", "15-JAN-2026", re="2Z"),
            member("TESTR4I, FF", "CMS", REENL_ELIG_STATUS="4I", DOS="31-DEC-3888"),
            careerist("TESTR2M, GG", "", re="2M"),
            member("TESTR2XO, HH", "MAJ", REENL_ELIG_STATUS="2X", DOS="31-DEC-3888"),
        ]
        r = run("re-code-review", rows)
        assert [x["name"] for x in r.rows] == ["TESTR2Z, EE", "TESTR4K, BB", "TESTR2X, AA", "TESTR4I, FF"]
        _, k = where(r, "TESTR4K, BB")
        assert k["re_waivable"] == "Yes" and k["re_waiver_authority"] == "Unit CC"
        assert k["uif_code"] == "2" and k["uif_disposition_date"] == date(2027, 3, 1)
        assert k["months_to_dos"] == 1
        assert where(r, "TESTR2Z, EE")[1]["re_definition"] == RE_DEFINITION_UNVERIFIED
        assert where(r, "TESTR4I, FF")[1]["dos"] == INDEFINITE
        assert where(r, "TESTR2M, GG")[0] == "data_issue"
        assert r.summary["unknown_codes"] == ["2Z"] and r.summary["officers_excluded"] == 1

    def test_custom_prefixes(self):
        rows = [careerist("TESTP3, P3", "15-JUN-2027", re="3B"), careerist("TESTP2, P2", "15-JUN-2027", re="2X")]
        r = run("re-code-review", rows, {"re_review_prefixes": "3"})
        assert [x["name"] for x in r.rows] == ["TESTP3, P3"]
        with pytest.raises(RunError):
            run("re-code-review", rows, {"re_review_prefixes": ["toolong"]})


# =============================================================================
# Exports (pure)
# =============================================================================

class TestExports:
    @pytest.mark.parametrize("run_id", ["dos-reenlistment", "deros-option", "re-code-review"])
    def test_pdf_and_xlsx_valid(self, run_id):
        rows = [
            first_termer("TESTALPHA, ADAM", "15-JAN-2023", "14-JUL-2027", ets="14-JAN-2027", DEROS="15-MAR-2027",
                         re="2X"),
            careerist("TESTBLANK, BO", "", DEROS="15-MAR-2027"),
        ]
        r = run(run_id, rows)
        pdf = build_pdf(r)
        assert pdf.startswith(b"%PDF")
        doc = fitz.open(stream=pdf, filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        for page in doc:
            assert RETENTION_FOOTER in page.get_text().replace("\n", " ")
            assert "CUI// CONTROLLED UNCLASSIFIED INFORMATION" in page.get_text()
        assert "TESTALPHA, ADAM" in text or run_id == "deros-option"
        assert "17-NOV-2026" in text
        wb = load_workbook(io.BytesIO(build_xlsx(r)))
        assert "Report Info" in wb.sheetnames
        ws = wb.worksheets[0]
        values = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
        assert RETENTION_FOOTER in values
        for ws in wb.worksheets:
            assert ws.oddHeader.center.text == "CUI"

    def test_xlsx_dates_are_real_dates(self):
        r = run("dos-reenlistment", [careerist("TESTDATE, DAY", "15-JUN-2027")])
        ws = load_workbook(io.BytesIO(build_xlsx(r))).worksheets[0]
        headers = [c.value for c in ws[1]]
        cell = ws.cell(row=2, column=headers.index("DOS") + 1)
        assert cell.value.date() == date(2027, 6, 15) and cell.number_format == "DD-MMM-YYYY"


# =============================================================================
# Upload / session / API
# =============================================================================

def _upload(client, rows, extra_headers=()):
    resp = client.post(
        "/api/v1/rosters/upload",
        files={"file": ("alpha.xlsx", io.BytesIO(alpha_xlsx(rows, extra_headers)), XLSX_TYPE)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _session_json(session_id):
    from session_manager import get_session
    return json.dumps(get_session(session_id))


API_ROWS = [
    first_termer("TESTALPHA, ADAM", "15-JAN-2023", "14-JUL-2027", ets="14-JAN-2027", DEROS="15-MAR-2027",
                 re="2X", ASSIGNED_PAS="ZZ1TEST"),
    careerist("TESTBRAVO, BEN", "15-JUN-2027", ASSIGNED_PAS="ZZ2TEST"),
    member("TESTOFFICER, OZ", "CPT", DOS="31-DEC-3888", ETS=None, DOE=None, REENL_ELIG_STATUS=None),
    member("TESTAIRMAN, AL", "A1C", DOR="15-OCT-2025", TAFMSD="15-OCT-2024", PAFSC="3F031",
           DOS="14-OCT-2028", ETS="14-OCT-2028", DOE="15-OCT-2024", REENL_ELIG_STATUS="1M"),
]


class TestUploadAndPii:
    def test_76_column_export_accepted_and_pii_not_stored(self, client):
        body = _upload(client, API_ROWS)
        cols = body["columns_found"]
        assert "DOS" in cols and "ETS" in cols and "DOE" in cols and "DEROS" in cols
        for pii in ("DATE_OF_BIRTH", "HOME_ADDRESS", "HOME_CITY", "HOME_STATE", "HOME_ZIP_CODE",
                    "HOME_PHONE_NUMBER", "AGE", "MARITAL_STATUS", "SUPV_NAME", "DUTY_PHONE"):
            assert pii not in cols
        assert {r["id"]: r["available"] for r in body["runs"]} == {
            "dos-reenlistment": True, "deros-option": True, "re-code-review": True, "btz-quarterly": True}
        stored = _session_json(body["session_id"])
        for key, sentinel in PII_SENTINELS.items():
            assert sentinel not in stored, key
            assert f'"{key}"' not in stored, key

    def test_ets_and_dos_stay_separate(self, client):
        body = _upload(client, API_ROWS)
        from session_manager import get_session
        rec = next(r for r in get_session(body["session_id"])["dataframe"] if r["FULL_NAME"] == "TESTALPHA, ADAM")
        assert rec["ETS"] == "14-JAN-2027" and rec["DOS"] == "14-JUL-2027"

    def test_aliases_never_map_pii_headers(self):
        for canonical, variants in ROSTER_COLUMN_ALIASES.items():
            for name in [canonical, *variants]:
                assert not is_pii_column(name), name
        for header in PII_SENTINELS:
            assert is_pii_column(header), header


class TestApi:
    def test_list_runs(self, client):
        resp = client.get("/api/v1/rosters/runs", params={"as_of_date": "2026-11-17"})
        assert resp.status_code == 200
        runs = {r["id"]: r for r in resp.json()["runs"]}
        assert set(runs) == {"dos-reenlistment", "deros-option", "re-code-review", "btz-quarterly"}
        assert any("item 32" in d for d in runs["btz-quarterly"]["duty"])
        assert runs["dos-reenlistment"]["params"][0]["default"] == 12
        assert runs["re-code-review"]["params"][0]["default"] == ["2", "4"]
        assert runs["btz-quarterly"]["params"][0]["default"] == "2027-Q2"
        assert runs["deros-option"]["rule_references"]

    @pytest.mark.parametrize("run_id", ["dos-reenlistment", "deros-option", "re-code-review", "btz-quarterly"])
    def test_run_and_exports(self, client, run_id):
        sid = _upload(client, API_ROWS)["session_id"]
        resp = client.post(f"/api/v1/rosters/{sid}/runs/{run_id}", json={"as_of_date": "2026-11-17"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for key in ("run_id", "as_of", "params", "columns", "rows", "buckets", "summary", "warnings", "footer"):
            assert key in body
        assert body["as_of"] == "2026-11-17" and body["as_of_display"] == "17-NOV-2026"
        assert resp.headers["cache-control"] == "no-store"

        pdf = client.post(f"/api/v1/rosters/{sid}/runs/{run_id}/export?format=pdf",
                          json={"as_of_date": "2026-11-17"})
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert pdf.headers["content-type"] == "application/pdf"
        assert f'filename="{run_id}' in pdf.headers["content-disposition"]
        fitz.open(stream=pdf.content, filetype="pdf")

        xlsx = client.post(f"/api/v1/rosters/{sid}/runs/{run_id}/export", params={"format": "xlsx"},
                           json={"as_of_date": "2026-11-17"})
        assert xlsx.status_code == 200 and xlsx.headers["content-type"] == XLSX_TYPE
        assert xlsx.content[:2] == b"PK"
        load_workbook(io.BytesIO(xlsx.content))

    def test_dos_run_officers_excluded_via_api(self, client):
        sid = _upload(client, API_ROWS)["session_id"]
        body = client.post(f"/api/v1/rosters/{sid}/runs/dos-reenlistment",
                           json={"as_of_date": "2026-11-17"}).json()
        assert body["summary"]["officers_excluded"] == 1
        alpha = next(r for r in body["rows"] if r["name"] == "TESTALPHA, ADAM")
        assert alpha["dos"] == "2027-07-14" and alpha["pending_extension_months"] == 6
        assert alpha["status"] == STATUS_INELIGIBLE
        assert body["pascodes"] == ["ZZ1TEST", "ZZ2TEST"]

    def test_errors(self, client):
        assert client.post("/api/v1/rosters/nope/runs/dos-reenlistment", json={}).status_code == 404
        sid = _upload(client, API_ROWS)["session_id"]
        assert client.post(f"/api/v1/rosters/{sid}/runs/not-a-run", json={}).status_code == 404
        bad = client.post(f"/api/v1/rosters/{sid}/runs/btz-quarterly", json={"params": {"quarter": "Q9"}})
        assert bad.status_code == 422 and bad.json()["invalid_params"] == ["quarter"]
        bad_date = client.post(f"/api/v1/rosters/{sid}/runs/deros-option", json={"as_of_date": "17-11-2026"})
        assert bad_date.status_code == 422
        bad_fmt = client.post(f"/api/v1/rosters/{sid}/runs/deros-option/export?format=doc", json={})
        assert bad_fmt.status_code == 422

    def test_missing_required_column_is_422(self, client):
        import pandas as pd
        buf = io.BytesIO()
        pd.DataFrame([{"FULL_NAME": "TESTONLY, ONE", "GRADE": "SSG"}]).to_csv(buf, index=False)
        buf.seek(0)
        sid = client.post("/api/v1/rosters/upload", files={"file": ("r.csv", buf, "text/csv")}).json()["session_id"]
        resp = client.post(f"/api/v1/rosters/{sid}/runs/dos-reenlistment", json={})
        assert resp.status_code == 422 and resp.json()["missing_columns"] == ["DOS"]

    def test_no_names_in_logs_or_files(self, client, caplog, tmp_path):
        from constants import TEMP_DIR
        from logging_config import LOGS_DIR

        def snapshot():
            files = set()
            for d in (str(LOGS_DIR), TEMP_DIR):
                if d and os.path.isdir(d):
                    for root, _, names in os.walk(d):
                        files.update(os.path.join(root, n) for n in names)
            return files

        before = snapshot()
        caplog.set_level(logging.DEBUG)
        sid = _upload(client, API_ROWS)["session_id"]
        for run_id in ("dos-reenlistment", "deros-option", "re-code-review", "btz-quarterly"):
            client.post(f"/api/v1/rosters/{sid}/runs/{run_id}", json={})
            for fmt in ("pdf", "xlsx"):
                client.post(f"/api/v1/rosters/{sid}/runs/{run_id}/export?format={fmt}", json={})
        assert "TESTALPHA" not in caplog.text and "TESTBRAVO" not in caplog.text
        new_files = snapshot() - before
        for path in new_files:
            with open(path, "rb") as fh:
                assert b"TESTALPHA" not in fh.read(), path
