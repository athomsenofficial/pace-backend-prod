"""Stateless roster-run endpoints: POST /api/v1/rosters/runs/{run_id}/process[/export].

Each tool uploads its own roster per request; nothing may reach Redis, the session store or disk,
and logs may carry counts only.
"""

import io
import json
import logging
import os
import tempfile

import fitz
import pytest
from openpyxl import load_workbook

from tests.roster_runs_fixtures import PII_SENTINELS, alpha_xlsx, member

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
AS_OF = "2026-11-17"
RUN_IDS = ["dos-reenlistment", "deros-option", "re-code-review", "btz-quarterly", "cjr-window"]

ROWS = [
    member("TESTALPHA, ADAM", "SRA", DOE="15-JAN-2023", TAFMSD="15-JAN-2023", ETS="14-JAN-2027",
           DOS="14-JUL-2027", DEROS="15-MAR-2027", REENL_ELIG_STATUS="2X", ASSIGNED_PAS="ZZ1TEST", DAFSC="3D032"),
    member("TESTBRAVO, BEN", "SSG", DOE="01-MAR-2022", TAFMSD="01-MAR-2016", ETS="15-JUN-2027", DOS="15-JUN-2027",
           REENL_ELIG_STATUS="1P", UIF_CODE="2", UIF_DISPOSITION_DATE="01-MAR-2027", ASSIGNED_PAS="ZZ2TEST"),
    member("TESTOFFICER, OZ", "CPT", DOS="31-DEC-3888"),
    member("TESTAIRMAN, AL", "A1C", DOR="10-JUL-2025", TAFMSD="10-JUL-2025", DOE="10-JUL-2025", PAFSC="3F031",
           DOS="09-JUL-2031", ETS="09-JUL-2031", REENL_ELIG_STATUS="1M"),
    member("TESTFIRST, FT", "A1C", DOE="01-JAN-2024", TAFMSD="01-JAN-2024", ETS="31-DEC-2027", DOS="31-DEC-2027",
           REENL_ELIG_STATUS="1M", DOR="01-SEP-2024"),
]
NAMES = [r["FULL_NAME"] for r in ROWS]


def _files(rows=ROWS, extra_headers=()):
    return {"file": ("alpha.xlsx", io.BytesIO(alpha_xlsx(rows, extra_headers)), XLSX_TYPE)}


def _form(run_id, **extra):
    data = {"as_of_date": AS_OF}
    if run_id == "btz-quarterly":
        data["params"] = json.dumps({"quarter": "2027-Q2"})
    data.update(extra)
    return data


@pytest.fixture
def no_temp_files(monkeypatch):
    """Fail if anything creates a temp file; also snapshot PACE_TEMP_DIR."""
    def boom(*a, **k):
        raise AssertionError("stateless roster processing must not create temp files")
    for name in ("NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile", "mkstemp", "mkdtemp",
                 "TemporaryDirectory"):
        monkeypatch.setattr(tempfile, name, boom)
    temp_dir = os.environ.get("PACE_TEMP_DIR")
    before = set(os.listdir(temp_dir)) if temp_dir and os.path.isdir(temp_dir) else None
    yield
    if before is not None:
        assert set(os.listdir(temp_dir)) == before


class TestStatelessProcess:
    @pytest.mark.parametrize("run_id", RUN_IDS)
    def test_process_and_both_exports_write_nothing(self, client, mock_redis_with_fakeredis, no_temp_files,
                                                    caplog, run_id):
        caplog.set_level(logging.DEBUG)
        resp = client.post(f"/api/v1/rosters/runs/{run_id}/process", files=_files(), data=_form(run_id))
        assert resp.status_code == 200, resp.text
        assert resp.headers["cache-control"] == "no-store"
        body = resp.json()
        assert body["run_id"] == run_id and body["as_of"] == AS_OF and body["as_of_display"] == "17-NOV-2026"
        for key in ("title", "duty", "params", "main_label", "columns", "rows", "buckets", "summary", "warnings",
                    "notes", "footer", "pascodes"):
            assert key in body

        pdf = client.post(f"/api/v1/rosters/runs/{run_id}/process/export?format=pdf", files=_files(),
                          data=_form(run_id))
        assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF") and pdf.headers["cache-control"] == "no-store"
        assert f'filename="{run_id}' in pdf.headers["content-disposition"]
        assert fitz.open(stream=pdf.content, filetype="pdf").page_count >= 1

        xlsx = client.post(f"/api/v1/rosters/runs/{run_id}/process/export", params={"format": "xlsx"},
                           files=_files(), data=_form(run_id))
        assert xlsx.status_code == 200 and xlsx.headers["content-type"] == XLSX_TYPE
        assert xlsx.content[:2] == b"PK" and xlsx.headers["cache-control"] == "no-store"
        assert load_workbook(io.BytesIO(xlsx.content)).sheetnames

        assert mock_redis_with_fakeredis.keys() == []  # nothing stored, ever
        logged = " ".join(r.getMessage() for r in caplog.records)
        for name in NAMES:
            assert name not in logged
        for sentinel in PII_SENTINELS.values():
            assert sentinel not in logged

    @pytest.mark.parametrize("run_id", RUN_IDS)
    def test_same_result_as_session_path(self, client, run_id):
        stateless = client.post(f"/api/v1/rosters/runs/{run_id}/process", files=_files(),
                                data=_form(run_id)).json()
        up = client.post("/api/v1/rosters/upload", files=_files())
        assert up.status_code == 200
        sid = up.json()["session_id"]
        payload = {"as_of_date": AS_OF}
        if run_id == "btz-quarterly":
            payload["params"] = {"quarter": "2027-Q2"}
        session = client.post(f"/api/v1/rosters/{sid}/runs/{run_id}", json=payload).json()
        for body in (stateless, session):
            body["warnings"] = [w for w in body["warnings"] if not w.startswith("Ignored")]
        stateless.pop("warnings"), session.pop("warnings")
        assert stateless == session

    def test_pii_never_returned(self, client):
        body = client.post("/api/v1/rosters/runs/dos-reenlistment/process", files=_files(),
                           data=_form("dos-reenlistment")).text
        for sentinel in PII_SENTINELS.values():
            assert sentinel not in body

    def test_params_and_pascodes_form_fields(self, client):
        resp = client.post("/api/v1/rosters/runs/dos-reenlistment/process", files=_files(),
                           data=_form("dos-reenlistment", params=json.dumps({"dos_window_months": 12}),
                                      pascodes=json.dumps(["zz2test"])))
        body = resp.json()
        assert resp.status_code == 200 and body["params"] == {"dos_window_months": 12}
        assert body["pascode_filter"] == ["ZZ2TEST"] and [r["name"] for r in body["rows"]] == ["TESTBRAVO, BEN"]

    def test_cjr_window_via_process(self, client):
        body = client.post("/api/v1/rosters/runs/cjr-window/process", files=_files(),
                           data=_form("cjr-window", params=json.dumps({"approaching_months": 3}))).json()
        rows = {r["name"]: r for r in body["rows"]}
        assert rows["TESTFIRST, FT"]["status"] == "IN WINDOW"
        assert rows["TESTALPHA, ADAM"]["status"] == "PAST WINDOW"
        assert body["summary"]["not_first_term_excluded"] == 1 and body["summary"]["officers_excluded"] == 1


class TestStatelessErrors:
    def test_unknown_run_404(self, client, mock_redis_with_fakeredis):
        resp = client.post("/api/v1/rosters/runs/nope/process", files=_files(), data={})
        assert resp.status_code == 404 and "error" in resp.json()
        assert mock_redis_with_fakeredis.keys() == []

    def test_missing_columns_422(self, client):
        csv = b"FULL_NAME,GRADE\nTESTCSV, CS,SSG\n"
        resp = client.post("/api/v1/rosters/runs/dos-reenlistment/process",
                           files={"file": ("r.csv", io.BytesIO(csv), "text/csv")}, data={"as_of_date": AS_OF})
        assert resp.status_code == 422 and resp.json()["missing_columns"] == ["DOS"]

    def test_bad_param_value_422(self, client):
        resp = client.post("/api/v1/rosters/runs/dos-reenlistment/process", files=_files(),
                           data={"params": json.dumps({"dos_window_months": "abc"})})
        assert resp.status_code == 422 and resp.json()["invalid_params"] == ["dos_window_months"]

    @pytest.mark.parametrize("field,value", [("params", "{not json"), ("params", "[1, 2]"),
                                             ("pascodes", "ZZ1TEST"), ("pascodes", "[1]")])
    def test_bad_json_fields_422(self, client, field, value):
        resp = client.post("/api/v1/rosters/runs/dos-reenlistment/process", files=_files(), data={field: value})
        assert resp.status_code == 422 and resp.json()["invalid_params"] == [field]

    def test_bad_as_of_422(self, client):
        resp = client.post("/api/v1/rosters/runs/dos-reenlistment/process", files=_files(),
                           data={"as_of_date": "17-11-2026"})
        assert resp.status_code == 422

    def test_bad_file_type_400(self, client):
        resp = client.post("/api/v1/rosters/runs/dos-reenlistment/process",
                           files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")})
        assert resp.status_code == 400

    def test_bad_export_format(self, client):
        resp = client.post("/api/v1/rosters/runs/dos-reenlistment/process/export?format=doc", files=_files())
        assert resp.status_code == 422


class TestCatalogue:
    def test_list_runs_without_session(self, client, mock_redis_with_fakeredis):
        resp = client.get("/api/v1/rosters/runs", params={"as_of_date": AS_OF})
        assert resp.status_code == 200
        runs = {r["id"]: r for r in resp.json()["runs"]}
        assert set(runs) == set(RUN_IDS)
        for r in runs.values():
            assert r["label"] and r["description"] and r["duty"] and "params" in r and r["formats"] == ["pdf", "xlsx"]
        assert runs["cjr-window"]["params"][0]["default"] == 3
        assert mock_redis_with_fakeredis.keys() == []
