"""Run 5 — First-Term CJR Window Roster (DAFI 36-2606 Table 3.1). Synthetic roster; as-of 17-NOV-2026."""

import io
from datetime import date

import fitz
import pytest
from openpyxl import load_workbook

from config.retention import CJR_FOOTER, CJR_WINDOWS_BY_TERM_MONTHS, RULE_REFERENCES
from roster_runs.cjr import cjr_window, term_from_ets
from roster_runs.exports import build_pdf, build_xlsx
from roster_runs.registry import RunError, execute
from tests.roster_runs_fixtures import AS_OF, alpha_records, member


def run(rows, params=None, as_of=AS_OF):
    records, columns = alpha_records(rows)
    return execute("cjr-window", records, columns, params or {}, as_of)


def ft(name, doe, ets, dos=None, re="1M", grade="A1C", **kw):
    """First-termer: DOE == TAFMSD."""
    return member(name, grade, DOE=doe, TAFMSD=doe, ETS=ets, DOS=dos or ets, REENL_ELIG_STATUS=re,
                  DAFSC=kw.pop("DAFSC", "3D032"), ASSIGNED_PAS=kw.pop("ASSIGNED_PAS", "ZZ1TEST"), **kw)


def row_of(result, name):
    hits = [r for r in result.rows if r["name"] == name]
    assert len(hits) == 1, name
    return hits[0]


class TestWindowMath:
    def test_table_3_1(self):
        assert CJR_WINDOWS_BY_TERM_MONTHS == {48: (32, 43), 72: (56, 67)}

    def test_calendar_month_window(self):
        # DOE 15-JAN-2023 completes 32 months on 14-SEP-2025 and 43 months on 14-AUG-2026.
        w = cjr_window(date(2023, 1, 15), 48)
        assert w.start == date(2025, 9, 1) and w.end == date(2026, 8, 31)
        w6 = cjr_window(date(2021, 8, 1), 72)
        assert w6.start == date(2026, 3, 1) and w6.end == date(2027, 2, 28)

    @pytest.mark.parametrize("doe,ets,expected", [
        (date(2023, 1, 1), date(2026, 12, 31), ("4-year", [48])),
        (date(2023, 1, 1), date(2027, 6, 30), ("4-year", [48])),        # 54: 4-year + effective extension
        (date(2021, 8, 1), date(2027, 7, 31), ("AMBIGUOUS (6-year, or 4-year extended)", [48, 72])),
        (date(2023, 1, 1), date(2025, 12, 31), None),                    # 36 months: unknown
    ])
    def test_term_from_ets(self, doe, ets, expected):
        assert term_from_ets(doe, ets) == expected


class TestStatuses:
    def test_four_year_in_window(self):
        r = run([ft("TESTIN, IN", "01-JAN-2024", "31-DEC-2027")])
        row = row_of(r, "TESTIN, IN")
        assert row["status"] == "IN WINDOW" and row["term"] == "4-year"
        assert row["month_of_enlistment"] == 35
        assert row["window_start"] == date(2026, 8, 1) and row["window_end"] == date(2027, 7, 31)
        assert row["months_until_close"] == 8
        assert row["dafsc"] == "3D032" and row["doe"] == date(2024, 1, 1) and row["dos"] == date(2027, 12, 31)

    def test_last_month_of_window_is_in_window(self):
        row = row_of(run([ft("TESTEDGE, ED", "01-MAY-2023", "30-APR-2027")]), "TESTEDGE, ED")
        assert row["status"] == "IN WINDOW" and row["month_of_enlistment"] == 43 and row["months_until_close"] == 0

    def test_four_year_past_window(self):
        row = row_of(run([ft("TESTPAST, PA", "01-APR-2023", "31-MAR-2027")]), "TESTPAST, PA")
        assert row["status"] == "PAST WINDOW" and row["months_until_close"] == -1
        assert any("para 3.1.2" in n for n in row["notes"])

    def test_approaching_and_param(self):
        rows = [ft("TESTSOON, SO", "01-MAY-2024", "30-APR-2028")]  # window opens 01-DEC-2026
        row = row_of(run(rows), "TESTSOON, SO")
        assert row["status"] == "APPROACHING" and row["window_start"] == date(2026, 12, 1)
        r0 = run(rows, {"approaching_months": 0})
        assert not r0.rows and r0.summary["window_not_yet_open"] == 1

    def test_window_far_off_not_listed(self):
        r = run([ft("TESTLATER, LA", "01-JAN-2025", "31-DEC-2028")])  # opens 01-AUG-2027
        assert not r.rows and r.summary["window_not_yet_open"] == 1

    def test_six_year_ambiguous_checks_both(self):
        # ETS-DOE = 72: 4-year window closed FEB-2025, 6-year window MAR-2026..FEB-2027 open.
        row = row_of(run([ft("TESTSIX, SX", "01-AUG-2021", "31-JUL-2027")]), "TESTSIX, SX")
        assert row["term"].startswith("AMBIGUOUS") and row["status"] == "IN WINDOW"
        assert row["window_end"] == date(2027, 2, 28) and row["months_until_close"] == 3
        assert "4-year:" in row["windows"] and "6-year:" in row["windows"]
        assert any("both 4-year and 6-year" in n for n in row["notes"])

    def test_ambiguous_both_past_uses_later_close(self):
        row = row_of(run([ft("TESTOLD, OL", "01-JAN-2020", "31-DEC-2025", dos="31-DEC-2026")]), "TESTOLD, OL")
        assert row["status"] == "PAST WINDOW" and row["window_end"] == date(2025, 7, 31)

    def test_sorted_by_window_close(self):
        r = run([ft("TESTIN, IN", "01-JAN-2024", "31-DEC-2027"),
                 ft("TESTPAST, PA", "01-APR-2023", "31-MAR-2027"),
                 ft("TESTSIX, SX", "01-AUG-2021", "31-JUL-2027")])
        assert [x["name"] for x in r.rows] == ["TESTPAST, PA", "TESTSIX, SX", "TESTIN, IN"]


class TestExclusionsAndBuckets:
    def test_exclusions_and_data_issues(self):
        rows = [
            ft("TESTONER, OR", "01-JAN-2024", "31-DEC-2027", re="1R"),
            member("TESTCAREER, CA", "SSG", DOE="01-MAR-2022", TAFMSD="01-MAR-2016", ETS="28-FEB-2028",
                   DOS="28-FEB-2028", REENL_ELIG_STATUS="1M"),
            member("TESTOFFICER, OZ", "CPT", DOE="01-JAN-2024", TAFMSD="01-JAN-2024", ETS="31-DEC-2027",
                   DOS="31-DEC-2027"),
            ft("TESTNOETS, NE", "01-JAN-2024", ""),
            member("TESTNODOS, ND", "A1C", DOE="01-JAN-2024", TAFMSD="01-JAN-2024", ETS="31-DEC-2027", DOS=""),
            ft("TESTODD, OD", "01-JAN-2024", "31-DEC-2026"),          # ETS-DOE = 36: term unknown
            member("TESTNOGRADE, NG", "", DOE="01-JAN-2024", TAFMSD="01-JAN-2024"),
            ft("TESTIN, IN", "01-JAN-2024", "31-DEC-2027", re="2X"),
        ]
        r = run(rows)
        assert [x["name"] for x in r.rows] == ["TESTIN, IN"]
        issues = {x["name"]: x["issues"] for x in r.buckets[0].rows}
        assert set(issues) == {"TESTNOETS, NE", "TESTNODOS, ND", "TESTODD, OD", "TESTNOGRADE, NG"}
        assert issues["TESTNOETS, NE"][0] == "ETS missing"
        assert issues["TESTNODOS, ND"][0] == "DOS missing"
        assert issues["TESTODD, OD"][0].startswith("Term unknown (ETS minus DOE = 36 months)")
        s = r.summary
        assert s["re_1r_excluded"] == 1 and s["not_first_term_excluded"] == 1 and s["officers_excluded"] == 1
        assert s["data_issue"] == 4 and s["listed"] == 1 and s["total_records"] == len(rows)

    def test_uif_is_informational(self):
        row = row_of(run([ft("TESTUIF, UI", "01-JAN-2024", "31-DEC-2027", UIF_CODE="2",
                              UIF_DISPOSITION_DATE="01-MAR-2027")]), "TESTUIF, UI")
        assert row["status"] == "IN WINDOW"
        assert row["uif_code"] == "2" and row["uif_disposition_date"] == date(2027, 3, 1)
        assert any("para 3.4.1" in n for n in row["notes"])

    def test_re_definition_shown(self):
        row = row_of(run([ft("TESTRE, RE", "01-JAN-2024", "31-DEC-2027", re="3C")]), "TESTRE, RE")
        assert row["re_code"] == "3C" and row["re_definition"].startswith("First-termer not yet considered")

    def test_param_validation(self):
        with pytest.raises(RunError) as e:
            run([ft("TESTX, X", "01-JAN-2024", "31-DEC-2027")], {"approaching_months": 13})
        assert e.value.invalid_params == ["approaching_months"]

    def test_missing_required_column(self):
        records, columns = alpha_records([ft("TESTX, X", "01-JAN-2024", "31-DEC-2027")])
        with pytest.raises(RunError) as e:
            execute("cjr-window", records, columns - {"ETS"}, {}, AS_OF)
        assert e.value.missing_columns == ["ETS"]


class TestOutput:
    def test_footer_duty_and_rule_references(self):
        r = run([ft("TESTIN, IN", "01-JAN-2024", "31-DEC-2027")])
        assert r.footer == CJR_FOOTER == "Screening aid only. MPF and commander determine eligibility per DAFI 36-2606."
        assert any("item 36" in d for d in r.duty) and any("item 3:" in d for d in r.duty)
        refs = [x for x in RULE_REFERENCES if x[0] == "cjr-window"]
        assert any("Table 3.1" in x[3] for x in refs) and any("para 3.4.1" in x[3] for x in refs)

    def test_pdf_and_xlsx(self):
        r = run([ft("TESTIN, IN", "01-JAN-2024", "31-DEC-2027"), ft("TESTNOETS, NE", "01-JAN-2024", "")])
        doc = fitz.open(stream=build_pdf(r), filetype="pdf")
        text = " ".join(p.get_text() for p in doc).replace("\n", " ")
        assert "First-Term CJR Window Roster" in text and CJR_FOOTER in text and "CUI" in text
        assert "31-JUL-2027" in text and "IN WINDOW" in text
        wb = load_workbook(io.BytesIO(build_xlsx(r)))
        values = [c for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for c in row if c]
        assert "IN WINDOW" in values and CJR_FOOTER in values

    def test_api_endpoint(self, client):
        from tests.roster_runs_fixtures import alpha_xlsx
        up = client.post("/api/v1/rosters/upload",
                         files={"file": ("alpha.xlsx", alpha_xlsx([ft("TESTIN, IN", "01-JAN-2024", "31-DEC-2027")]),
                                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert up.status_code == 200, up.text
        sid = up.json()["session_id"]
        body = client.post(f"/api/v1/rosters/{sid}/runs/cjr-window",
                           json={"as_of_date": "2026-11-17", "params": {"approaching_months": 3}}).json()
        assert body["run_id"] == "cjr-window" and body["params"] == {"approaching_months": 3}
        assert body["rows"][0]["status"] == "IN WINDOW" and body["rows"][0]["window_end"] == "2027-07-31"
        out = client.post(f"/api/v1/rosters/{sid}/runs/cjr-window/export?format=pdf",
                          json={"as_of_date": "2026-11-17"})
        assert out.status_code == 200 and 'filename="cjr-window_2026-11-17.pdf"' in out.headers["content-disposition"]
