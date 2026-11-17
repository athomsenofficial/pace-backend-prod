"""Run 4 — SrA BTZ Quarterly Eligibility Roster (synthetic roster, real 76 headers)."""

import io
from datetime import date

import fitz
import pytest
from openpyxl import load_workbook

from config.retention import (
    BTZ_CBB_POLICY_NOTE, BTZ_FOOTER, BTZ_GSR_STANDING_NOTE, BTZ_PRIOR_SERVICE_NOTE, RULE_REFERENCES,
)
from roster_runs.btz import (
    CBB_REQUIRES_BASE_WIDE, compute_quotas, default_quarter, fully_qualified_date, parse_quarter, quarter_info,
    quota_for,
)
from roster_runs.exports import build_pdf, build_xlsx
from roster_runs.registry import RunError, execute
from tests.roster_runs_fixtures import AS_OF, alpha_records, alpha_xlsx, member

Q2_2027 = {"quarter": "2027-Q2"}  # BTZ dates Apr-Jun 2027: process Jan/Feb 2027, board Mar 2027


def run(rows, params=Q2_2027, as_of=AS_OF, extra_headers=(), pascodes=None):
    records, columns = alpha_records(rows, extra_headers)
    return execute("btz-quarterly", records, columns, params, as_of, pascodes)


def a1c(name, dor, tafmsd, pas="ZZ1TEST", **kw):
    kw.setdefault("PAFSC", "3F031")
    kw.setdefault("ASSIGNED_PAS_CLEARTEXT", f"{pas} SQ")
    return member(name, "A1C", DOR=dor, TAFMSD=tafmsd, ASSIGNED_PAS=pas, **kw)


def in_q2(name, pas="ZZ1TEST", **kw):
    """A1C-at-enlistment with BTZ date 10-MAY-2027 (fully qualified 10-NOV-2027)."""
    return a1c(name, "10-JUL-2025", "10-JUL-2025", pas, **kw)


def placement(result, name):
    hits = [("rows", r) for r in result.rows if r["name"] == name]
    for b in result.buckets:
        hits += [(b.id, r) for r in b.rows if r["name"] == name]
    assert len(hits) <= 1
    return hits[0] if hits else (None, None)


class TestDates:
    def test_36_month_tis_path(self):
        fq, path = fully_qualified_date(date(2024, 10, 15), date(2025, 10, 15))
        assert fq == date(2027, 10, 15) and path.startswith("TIS")
        r = run([a1c("TESTTIS, TIA", "15-OCT-2025", "15-OCT-2024")])
        _, row = placement(r, "TESTTIS, TIA")
        assert row["btz_date"] == date(2027, 4, 15) and row["fully_qualified_date"] == date(2027, 10, 15)

    def test_28_month_tig_path(self):
        fq, path = fully_qualified_date(date(2025, 1, 1), date(2025, 8, 1))
        assert fq == date(2027, 12, 1) and path.startswith("TIG (DOR+28)")
        r = run([a1c("TESTTIG, TIG", "01-AUG-2025", "01-JAN-2025")])
        assert placement(r, "TESTTIG, TIG")[1]["btz_date"] == date(2027, 6, 1)

    def test_tig_plus_tis_path(self):
        fq, path = fully_qualified_date(date(2023, 1, 1), date(2026, 3, 1))
        assert fq == date(2027, 11, 1) and path.startswith("TIG+TIS")

    def test_a1c_at_enlistment(self):
        r = run([in_q2("TESTENLIST, EVA")])
        _, row = placement(r, "TESTENLIST, EVA")
        assert row["fq_path"] == "TIG (DOR+28)"
        assert row["fully_qualified_date"] == date(2027, 11, 10) and row["btz_date"] == date(2027, 5, 10)

    def test_btz_date_on_quarter_boundaries(self):
        rows = [
            a1c("TESTFIRSTDAY, FD", "01-JUN-2025", "01-JUN-2025"),   # BTZ 01-APR-2027 -> in Q2
            a1c("TESTLASTDAY, LD", "30-AUG-2025", "30-AUG-2025"),    # BTZ 30-JUN-2027 -> in Q2
            a1c("TESTBEFORE, BF", "30-MAY-2025", "30-MAY-2025"),     # BTZ 30-MAR-2027 -> Q1
            a1c("TESTAFTER, AF", "01-SEP-2025", "01-SEP-2025"),      # BTZ 01-JUL-2027 -> Q3
        ]
        r = run(rows)
        assert placement(r, "TESTFIRSTDAY, FD")[1]["btz_date"] == date(2027, 4, 1)
        assert placement(r, "TESTLASTDAY, LD")[1]["btz_date"] == date(2027, 6, 30)
        assert placement(r, "TESTBEFORE, BF") == (None, None)
        assert placement(r, "TESTAFTER, AF") == (None, None)
        assert r.summary["btz_date_before_quarter"] == 1 and r.summary["btz_date_after_quarter"] == 1
        q1 = run(rows, {"quarter": "2027-Q1"})
        assert [x["name"] for x in q1.rows] == ["TESTBEFORE, BF"]


class TestQuarters:
    def test_table_2_7(self):
        q = quarter_info(2027, 2)
        assert q["processing_months"] == ["JAN-2027", "FEB-2027"] and q["board_month"] == "MAR-2027"
        assert quarter_info(2027, 3)["processing_months"] == ["APR-2027", "MAY-2027"]
        assert quarter_info(2027, 3)["board_month"] == "JUN-2027"
        assert quarter_info(2027, 4)["board_month"] == "SEP-2027"
        q1 = quarter_info(2028, 1)
        assert q1["processing_months"] == ["OCT-2027", "NOV-2027"] and q1["board_month"] == "DEC-2027"
        assert q1["btz_date_start"] == date(2028, 1, 1) and q1["btz_date_end"] == date(2028, 3, 31)

    @pytest.mark.parametrize("as_of,expected", [
        (date(2026, 11, 17), (2027, 2)),   # next first-processing month is JAN-2027
        (date(2027, 1, 15), (2027, 2)),    # JAN is the current first-processing month
        (date(2027, 2, 1), (2027, 3)),
        (date(2026, 10, 10), (2027, 1)),   # OCT-2026 processes BTZ JAN-MAR 2027
    ])
    def test_default_quarter(self, as_of, expected):
        assert default_quarter(as_of) == expected

    def test_default_used_when_not_supplied(self):
        assert run([in_q2("TESTDEFAULT, DEF")], params={}).params == {"quarter": "2027-Q2"}

    def test_parse(self):
        assert parse_quarter("2027-Q2") == (2027, 2) and parse_quarter("q3-2027") == (2027, 3)
        with pytest.raises(ValueError):
            parse_quarter("2027-Q5")
        with pytest.raises(RunError):
            run([in_q2("TESTX, X")], params={"quarter": "next"})


class TestQuotas:
    # Owner decision 17 Nov 2026: no rounding — exact 15%, two decimals; the MPF sets the whole number.
    @pytest.mark.parametrize("n,q", [(1, 0.15), (2, 0.30), (7, 1.05), (9, 1.35), (10, 1.50), (11, 1.65),
                                     (16, 2.40), (17, 2.55), (23, 3.45), (36, 5.40)])
    def test_exact_15_percent_no_rounding(self, n, q):
        assert quota_for(n) == q

    def test_unit_of_exactly_6_and_7(self):
        rows = [in_q2(f"TESTSIX, S{i}", "ZZ6TEST") for i in range(6)]
        rows += [in_q2(f"TESTSEVEN, S{i}", "ZZ7TEST") for i in range(7)]
        r = run(rows)
        units = {u["pascode"]: u for u in r.extra["units"]}
        assert units["ZZ6TEST"]["size"] == "SMALL" and units["ZZ6TEST"]["quota"] is None
        assert units["ZZ7TEST"]["size"] == "LARGE" and units["ZZ7TEST"]["quota"] == 1.05
        assert units["ZZ7TEST"]["quota_display"] == "1.05"
        assert r.extra["cbb"]["pool_total"] == 6
        assert r.extra["cbb"]["quota"] == 0.90 and r.extra["cbb"]["quota_display"] == "0.90"  # 15% of pooled 6
        assert r.summary["total_quota"] == 1.95
        assert "the MPF determines the whole-number quota" in r.extra["cbb"]["note"]

    @pytest.mark.parametrize("n,q", [(9, 1.35), (10, 1.50), (16, 2.40), (17, 2.55)])
    def test_large_unit_quota_via_run(self, n, q):
        r = run([in_q2(f"TESTBIG, B{i:02d}", "ZZBTEST") for i in range(n)])
        assert r.extra["units"][0]["quota"] == q
        assert r.extra["units"][0]["quota_display"] == f"{q:.2f}"

    @pytest.mark.parametrize("pool", [2, 3, 4, 5, 6])
    def test_no_large_unit_2_to_6_gets_one_cbb_quota(self, pool):
        units, cbb = compute_quotas({"ZZATEST": pool - 1, "ZZBTEST": 1}, {}, False)
        assert cbb["pool_total"] == pool and cbb["quota"] == 1.0 and "para 2.3.5.3" in cbb["note"]

    def test_no_large_unit_via_run(self):
        rows = [in_q2("TESTPOOL, A1", "ZZATEST"), in_q2("TESTPOOL, A2", "ZZATEST"),
                in_q2("TESTPOOL, B1", "ZZBTEST")]
        r = run(rows)
        assert r.extra["cbb"]["quota"] == 1.0 and "No large units" in r.extra["cbb"]["note"]

    def test_cbb_is_15_percent_of_pooled_total_even_with_large_units(self):
        # Owner decision: CBB quota = 15% of all pooled small-unit eligibles; no combining computation.
        units, cbb = compute_quotas({"ZZLTEST": 10, "ZZSTEST": 2}, {}, False)
        assert cbb["quota"] == 0.30 and "combine_with_large_unit" not in cbb
        assert "para 2.3.5.2" in cbb["note"]  # cited for information only
        assert units[0]["quota"] == 1.50 and units[0]["quota_note"] == "Own quota"
        units, cbb = compute_quotas({"ZZLTEST": 10, "ZZSTEST": 4, "ZZTTEST": 6, "ZZUTEST": 3}, {}, False)
        assert cbb["pool_total"] == 13 and cbb["quota"] == 1.95

    def test_no_large_unit_pool_over_6(self):
        units, cbb = compute_quotas({"ZZATEST": 6, "ZZBTEST": 5}, {}, False)
        assert cbb["pool_total"] == 11 and cbb["quota"] == 1.65

    def test_cbb_policy_note_cited(self):
        r = run([in_q2("TESTPOLICY, PO")])
        assert BTZ_CBB_POLICY_NOTE in r.notes and r.extra["cbb"]["policy_note"] == BTZ_CBB_POLICY_NOTE
        assert "para 2.4.2.1" in BTZ_CBB_POLICY_NOTE and "17 Nov 2026" in BTZ_CBB_POLICY_NOTE
        assert "fewer than seven eligibles" in BTZ_CBB_POLICY_NOTE

    def test_single_eligible_base_wide(self):
        rows = [in_q2("TESTSOLO, SOL", "ZZ1TEST"),
                member("TESTOTHER, OTH", "SSG", ASSIGNED_PAS="ZZ2TEST")]
        r = run(rows)
        assert r.extra["cbb"]["quota"] is None
        assert "MPF commander decides" in r.extra["cbb"]["note"] and "para 2.3.5.4" in r.extra["cbb"]["note"]
        assert r.summary["total_quota"] == 0
        assert r.extra["cbb"]["requires_base_wide_roster"] is False

    def test_one_unit_roster_labels_cbb(self):
        r = run([in_q2(f"TESTONEUNIT, U{i}") for i in range(3)])
        assert r.summary["single_unit_roster"] is True
        assert r.extra["cbb"]["label"] == CBB_REQUIRES_BASE_WIDE
        assert any("base-wide roster" in n for n in r.notes)


class TestFlagsAndBuckets:
    def test_quality_remarks_do_not_remove_from_count(self):
        rows = [
            in_q2("TESTCTRL, CR", REENL_ELIG_STATUS="4I"),
            in_q2("TESTART15, AR", REENL_ELIG_STATUS="4H"),
            in_q2("TESTSKILL, SK", PAFSC="3F011"),
            in_q2("TESTUIF, UI", UIF_CODE="2", UIF_DISPOSITION_DATE="01-JUN-2027"),
            in_q2("TESTRE, RE", REENL_ELIG_STATUS="2X"),
            in_q2("TESTCLEAN, CL", REENL_ELIG_STATUS="1M"),
        ]
        r = run(rows)
        assert r.summary["eligibles"] == 6
        remarks = {x["name"]: x["remarks"] for x in r.rows}
        assert remarks["TESTCTRL, CR"] == ["Control roster (RE 4I)"]
        assert remarks["TESTART15, AR"] == ["Suspended Article 15 (RE 4H)"]
        assert remarks["TESTSKILL, SK"] == ["Skill level below 3"]
        assert remarks["TESTUIF, UI"] == ["UIF code 2, disposition 01-JUN-2027"]
        assert remarks["TESTRE, RE"] == ["RE 2X: Non-selected for reenlistment (or non-selected for continued "
                                         "service under the NCO Career Status Program)"]
        assert remarks["TESTCLEAN, CL"] == []

    def test_previously_considered_5q_excluded(self):
        rows = [in_q2("TEST5Q, FQ", GRADE_STATUS_REASON="5Q"), in_q2("TESTNEW, NW", GRADE_STATUS_REASON="")]
        r = run(rows, extra_headers=["GRADE_STATUS_REASON"])
        assert placement(r, "TEST5Q, FQ")[0] == "previously_considered"
        assert r.summary["eligibles"] == 1 and r.summary["previously_considered"] == 1
        assert BTZ_GSR_STANDING_NOTE not in r.notes

    def test_gsr_alias_and_standing_note_when_absent(self):
        r = run([in_q2("TESTGSR, GS", GSR="5Q")], extra_headers=["GSR"])
        assert placement(r, "TESTGSR, GS")[0] == "previously_considered"
        r2 = run([in_q2("TESTNOGSR, NG")])
        assert BTZ_GSR_STANDING_NOTE in r2.notes
        assert BTZ_PRIOR_SERVICE_NOTE in r2.notes

    def test_projected_pcs(self):
        rows = [in_q2("TESTPCS, PC", RNLTD="15-FEB-2027"), in_q2("TESTEARLY, EA", RNLTD="01-DEC-2026")]
        r = run(rows)
        _, pcs = placement(r, "TESTPCS, PC")
        assert any("losing unit considers" in x for x in pcs["remarks"])
        _, early = placement(r, "TESTEARLY, EA")
        assert any("before processing" in x for x in early["remarks"])
        assert r.summary["eligibles"] == 2

    def test_blank_and_bad_dates_go_to_data_issue(self):
        rows = [a1c("TESTNODOR, ND", "", "10-JUL-2025"), a1c("TESTBADTAF, BT", "10-JUL-2025", "10-XYZ-2025")]
        r = run(rows)
        assert placement(r, "TESTNODOR, ND")[1]["issues"] == ["DOR missing"]
        assert placement(r, "TESTBADTAF, BT")[1]["issues"] == ["TAFMSD unreadable"]
        assert r.summary["eligibles"] == 0 and r.summary["data_issue"] == 2

    def test_non_a1c_and_officers_excluded(self):
        rows = [
            member("TESTSRA, SR", "SRA", DOR="10-JUL-2025", TAFMSD="10-JUL-2025"),
            member("TESTAMN, AM", "AMN", DOR="10-JUL-2025", TAFMSD="10-JUL-2025"),
            member("TESTLT, LT", "1LT", DOR="10-JUL-2025", TAFMSD="10-JUL-2025"),
            in_q2("TESTA1C, AC"),
        ]
        r = run(rows)
        assert [x["name"] for x in r.rows] == ["TESTA1C, AC"]
        assert r.summary["enlisted_not_a1c"] == 2 and r.summary["officers_excluded"] == 1

    def test_ang_afr_excluded(self):
        r = run([in_q2("TESTANG, AN", ANG_ROLL_INDICATOR="Y"), in_q2("TESTAFR, AF", AFR_SECTION_ID="12")])
        assert placement(r, "TESTANG, AN")[0] == "excluded_non_regaf"
        assert placement(r, "TESTAFR, AF")[0] == "excluded_non_regaf"
        assert r.summary["eligibles"] == 0

    def test_pascode_filter_keeps_basewide_quota(self):
        rows = [in_q2(f"TESTLG, L{i}", "ZZLTEST") for i in range(7)] + [in_q2("TESTSM, S1", "ZZSTEST")]
        r = run(rows, pascodes=["ZZSTEST"])
        assert [x["name"] for x in r.rows] == ["TESTSM, S1"]
        assert r.summary["eligibles"] == 8 and len(r.extra["units"]) == 2


class TestBtzExports:
    def _result(self):
        rows = [in_q2(f"TESTLARGE, L{i}", "ZZLTEST", ASSIGNED_PAS_CLEARTEXT="LARGE TEST SQ") for i in range(7)]
        rows += [in_q2("TESTSMALL, S1", "ZZSTEST", ASSIGNED_PAS_CLEARTEXT="SMALL TEST SQ", RNLTD="15-FEB-2027")]
        rows += [a1c("TESTDATA, DI", "", "10-JUL-2025")]
        return run(rows)

    def test_pdf_summary_unit_pages_and_checkboxes(self):
        r = self._result()
        pdf = build_pdf(r)
        doc = fitz.open(stream=pdf, filetype="pdf")
        first = doc[0].get_text()
        assert "MPF Summary" in first and "CBB pool" in first and "ZZLTEST" in first
        assert "BTZ dates APR-JUN 2027" in first
        widgets = [w for page in doc for w in page.widgets()]
        assert len(widgets) == 2 * len(r.rows)
        names = {w.field_name for w in widgets}
        assert "btz_ZZLTEST_0_nominate" in names and "btz_ZZSTEST_0_do_not_nominate" in names
        assert all(w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX for w in widgets)
        unit_pages = [p for p in doc if "Unit ZZLTEST" in p.get_text() or "Unit ZZSTEST" in p.get_text()]
        assert len(unit_pages) == 2
        for page in unit_pages:
            text = page.get_text()
            assert "Commander signature" in text and "Nominate" in text and "Do Not" in text
            # every widget on a unit page sits inside the page and below the header block
            for w in page.widgets():
                assert 0 < w.rect.x0 < page.rect.width and 1.5 * 72 < w.rect.y0 < page.rect.height - 72
        for page in doc:
            assert BTZ_FOOTER in page.get_text().replace("\n", " ")
        assert "TESTDATA, DI" in "".join(p.get_text() for p in doc)

    def test_pdf_checkbox_lands_in_its_row(self):
        r = self._result()
        doc = fitz.open(stream=build_pdf(r), filetype="pdf")
        page = next(p for p in doc if "Unit ZZSTEST" in p.get_text())
        name_rect = page.search_for("TESTSMALL, S1")[0]
        boxes = [w.rect for w in page.widgets()]
        assert len(boxes) == 2
        for rect in boxes:
            mid = (rect.y0 + rect.y1) / 2
            assert name_rect.y0 - 12 < mid < name_rect.y1 + 12

    def test_xlsx(self):
        r = self._result()
        wb = load_workbook(io.BytesIO(build_xlsx(r)))
        assert wb.sheetnames[:2] == ["MPF Summary", "Eligibles"]
        summary = [[c.value for c in row] for row in wb["MPF Summary"].iter_rows()]
        assert any(row[0] == "CBB POOL" for row in summary)
        assert any(BTZ_FOOTER in [v for v in row if v] for row in summary)
        headers = [c.value for c in wb["Eligibles"][1]]
        assert headers[-2:] == ["Nominate", "Do Not Nominate"]
        assert wb["Eligibles"].max_row >= len(r.rows) + 1

    def test_empty_quarter_exports(self):
        r = run([member("TESTSSG, SS", "SSG")])
        assert build_pdf(r).startswith(b"%PDF")
        load_workbook(io.BytesIO(build_xlsx(r)))

    def test_api_export_filename_has_quarter(self, client):
        resp = client.post(
            "/api/v1/rosters/upload",
            files={"file": ("a.xlsx", io.BytesIO(alpha_xlsx([in_q2("TESTAPI, AP")])),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        sid = resp.json()["session_id"]
        out = client.post(f"/api/v1/rosters/{sid}/runs/btz-quarterly/export?format=pdf",
                          json={"as_of_date": "2026-11-17", "params": {"quarter": "2027-Q2"}})
        assert out.status_code == 200
        assert 'filename="btz-quarterly_2027-Q2_2026-11-17.pdf"' in out.headers["content-disposition"]
        body = client.post(f"/api/v1/rosters/{sid}/runs/btz-quarterly",
                           json={"as_of_date": "2026-11-17"}).json()
        assert body["quarter"]["id"] == "2027-Q2" and body["rows"][0]["btz_date"] == "2027-05-10"
        assert body["units"][0]["size"] == "SMALL" and body["cbb"]["requires_base_wide_roster"] is True
        assert any(o["default"] for o in body["quarter_options"])


class TestPublicationAlignment:
    """AFI 36-2502 (2 Jul 2026) and the SrA BTZ Eligibility Determination Chart (04 Jun 2021)."""

    @pytest.mark.parametrize("tafmsd,dor,fq", [
        # Chart columns 1 & 2 (AB/Amn entrants): TAFMSD Jan-Mar 19 AND DOR May-Jul 20 -> FQ Jan-Mar 22.
        (date(2019, 1, 1), date(2020, 5, 1), date(2022, 1, 1)),
        (date(2019, 3, 1), date(2020, 7, 1), date(2022, 3, 1)),
        # Chart column 3 (A1C entrants): DOR Sep-Nov 19 -> FQ Jan-Mar 22 (28 months TIG).
        (date(2019, 9, 1), date(2019, 9, 1), date(2022, 1, 1)),
        (date(2019, 11, 1), date(2019, 11, 1), date(2022, 3, 1)),
    ])
    def test_chart_rows(self, tafmsd, dor, fq):
        got, _ = fully_qualified_date(tafmsd, dor)
        assert got == fq
        # Chart: FQ Jan-Mar 22 -> BTZ promotion Jul-Sep 21 -> board Jun 21 (Table 2.7 item 2).
        info = quarter_info(2021, 3)
        assert info["board_month"] == "JUN-2021" and info["processing_months"] == ["APR-2021", "MAY-2021"]
        from roster_runs.btz import btz_date
        assert info["btz_date_start"] <= btz_date(got) <= info["btz_date_end"]

    def test_footer_and_citations_name_afi_2_jul_2026(self):
        assert BTZ_FOOTER.endswith("per AFI 36-2502 (2 Jul 2026).")
        btz = [r for r in RULE_REFERENCES if r[0] == "btz-quarterly"]
        assert btz and all("DAFI 36-2502" not in r[3] for r in btz)
        assert any(r[1] == "Quota rounding" and "OWNER DECISION" in r[4] for r in btz)

    def test_pdf_summary_prints_cbb_policy(self):
        r = run([in_q2("TESTPDFPOL, PP", "ZZATEST"), in_q2("TESTPDFPOL, PQ", "ZZBTEST")])
        doc = fitz.open(stream=build_pdf(r), filetype="pdf")
        text = doc[0].get_text().replace("\n", " ")
        assert "Policy:" in text and "2.4.2.1" in text


class TestExactQuotaExports:
    def test_pdf_and_xlsx_show_two_decimals(self):
        rows = [in_q2(f"TESTBIG, B{i:02d}", "ZZBTEST") for i in range(11)]
        rows += [in_q2("TESTSMALL, S1", "ZZSTEST"), in_q2("TESTSMALL, S2", "ZZSTEST")]
        r = run(rows)
        text = fitz.open(stream=build_pdf(r), filetype="pdf")[0].get_text().replace("\n", " ")
        assert "1.65" in text and "0.30" in text and "1.95" in text
        assert "sets no rounding rule" in text
        ws = load_workbook(io.BytesIO(build_xlsx(r)))["MPF Summary"]
        quotas = {row[0].value: row[4] for row in ws.iter_rows(min_row=2) if row[0].value}
        assert quotas["ZZBTEST"].value == 1.65 and quotas["ZZBTEST"].number_format == "0.00"
        assert quotas["CBB POOL"].value == 0.3 and quotas["TOTAL"].value == 1.95
