"""
Roster editor regression tests (QA pass 2026-11-17 on pacetool.app).

Scenarios found broken on production:
  * editing any uploaded member re-ran the filter without PAFSC/RE/UIF and pushed
    them out of Eligible ("Insufficient PAFSC skill level");
  * an ineligible member could not be corrected or moved to eligible;
  * Re-process rebuilt from the original upload, undoing adds / deletes / edits;
  * manually added members leaked a stray PAFSC column into the PDF tables;
  * "total processed" counted discrepancy members twice.
"""

import io

import pandas as pd
import pytest

from constants import PDF_COLUMNS

CYCLE, YEAR = "SSG", "2026"
COLS = ["FULL_NAME", "GRADE", "ASSIGNED_PAS_CLEARTEXT", "DAFSC", "DOR", "DATE_ARRIVED_STATION",
        "TAFMSD", "REENL_ELIG_STATUS", "ASSIGNED_PAS", "PAFSC", "GRADE_PERM_PROJ", "UIF_CODE",
        "UIF_DISPOSITION_DATE", "2AFSC", "3AFSC", "4AFSC"]


def _member(name, pas="ZZ1TEST", unit="99 TST/TSA", dor="01-Jan-2024", taf="01-Jun-2020", pafsc="3F071", re="1A"):
    return {"FULL_NAME": name, "GRADE": "SSG", "ASSIGNED_PAS_CLEARTEXT": unit, "DAFSC": pafsc, "DOR": dor,
            "DATE_ARRIVED_STATION": "01-Jun-2023", "TAFMSD": taf, "REENL_ELIG_STATUS": re, "ASSIGNED_PAS": pas,
            "PAFSC": pafsc, "GRADE_PERM_PROJ": None, "UIF_CODE": None, "UIF_DISPOSITION_DATE": None,
            "2AFSC": None, "3AFSC": None, "4AFSC": None}


def _roster_csv():
    rows = [_member(n) for n in [
        "TESTZULU, ZANE", "TESTBRAVO, BETH", "TESTMIKE, MAX", "TESTALPHA, ADAM", "TESTYANKEE, YARA",
        "TESTCHARLIE, CARL", "TESTKILO, KATE", "TESTDELTA, DAN", "TESTLIMA, LEO", "TESTECHO, EVE",
        "TESTHOTEL, HAL", "TESTFOXTROT, FAY"]]
    rows.append(_member("TESTINDIA, IVY", pafsc="3F051"))          # discrepancy: skill level
    rows.append(_member("TESTGOLF, GUS", re="2J"))                  # discrepancy: RE code
    rows.append(_member("TESTOSCAR, OLLIE", dor="01-Jan-2026"))     # ineligible: TIG
    rows.append(_member("TESTPAPA, PAM", pas="ZZ2TEST", unit="99 TST/TSB"))
    rows.append(_member("TESTQUEBEC, QUINN", pas="ZZ2TEST", unit="99 TST/TSB"))
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=COLS).to_csv(buf, index=False)
    buf.seek(0)
    return buf


@pytest.fixture
def sid(client):
    r = client.post("/api/v1/upload/initial-mel",
                    files={"file": ("roster.csv", _roster_csv(), "text/csv")},
                    data={"cycle": CYCLE, "year": YEAR})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def _preview(client, sid):
    r = client.get(f"/api/v1/roster/preview/{sid}", params={"category": "all", "page": 1, "page_size": 1000})
    assert r.status_code == 200, r.text
    return r.json()


def _names(preview, category):
    return [m["FULL_NAME"] for m in preview["categories"][category]]


def _find(preview, category, name_prefix):
    matches = [m for m in preview["categories"][category] if m["FULL_NAME"].startswith(name_prefix)]
    assert matches, f"{name_prefix} not in {category}: {_names(preview, category)}"
    return matches[0]


def _add(client, sid, name, dor="01-JAN-2024"):
    data = {"FULL_NAME": name, "GRADE": "SSG", "PAFSC": "3F071", "DAFSC": "3F071", "DOR": dor,
            "TAFMSD": "01-JUN-2020", "DATE_ARRIVED_STATION": "01-JUN-2023", "ASSIGNED_PAS": "ZZ1TEST",
            "ASSIGNED_PAS_CLEARTEXT": "99 TST/TSA", "REENL_ELIG_STATUS": "1A", "UIF_CODE": 0}
    r = client.post(f"/api/v1/roster/member/{sid}",
                    json={"category": "eligible", "data": data, "reason": "Member added via UI",
                          "run_eligibility_check": True})
    assert r.status_code == 200, r.text
    return r.json()


class TestUploadKeepsFullRecords:
    def test_categories_and_eligibility_fields(self, client, sid):
        p = _preview(client, sid)
        assert len(p["categories"]["eligible"]) == 16
        assert _names(p, "ineligible") == ["TESTOSCAR, OLLIE"]
        assert _names(p, "discrepancy") == ["TESTGOLF, GUS", "TESTINDIA, IVY"]
        adam = _find(p, "eligible", "TESTALPHA")
        assert adam["PAFSC"] == "3F071" and adam["REENL_ELIG_STATUS"] == "1A"
        assert adam["_uid"]

    def test_alphabetical(self, client, sid):
        p = _preview(client, sid)
        names = _names(p, "eligible")
        assert names == sorted(names, key=str.upper)

    def test_total_processed_counts_each_member_once(self, client, sid):
        assert _preview(client, sid)["statistics"]["total_processed"] == 17


class TestEdit:
    def test_name_edit_keeps_member_eligible(self, client, sid):
        adam = _find(_preview(client, sid), "eligible", "TESTALPHA")
        r = client.put(f"/api/v1/roster/member/{sid}/{adam['member_id']}", json={"FULL_NAME": "TESTALPHA, ADAM B"})
        assert r.status_code == 200 and r.json()["new_category"] == "eligible", r.text
        p = _preview(client, sid)
        assert "TESTALPHA, ADAM B" in _names(p, "eligible")
        assert all(not n.startswith("TESTALPHA") for n in _names(p, "discrepancy"))

    def test_fixing_ineligible_dor_moves_to_eligible(self, client, sid):
        ollie = _find(_preview(client, sid), "ineligible", "TESTOSCAR")
        r = client.put(f"/api/v1/roster/member/{sid}/{ollie['member_id']}", json={"DOR": "01-JAN-2024"})
        assert r.json()["new_category"] == "eligible", r.text
        p = _preview(client, sid)
        assert "TESTOSCAR, OLLIE" in _names(p, "eligible")
        assert _names(p, "ineligible") == []

    def test_clearing_discrepancy_leaves_one_eligible_copy(self, client, sid):
        gus = _find(_preview(client, sid), "discrepancy", "TESTGOLF")
        r = client.put(f"/api/v1/roster/member/{sid}/{gus['member_id']}", json={"REENL_ELIG_STATUS": "1A"})
        assert r.json()["new_category"] == "eligible", r.text
        p = _preview(client, sid)
        assert _names(p, "eligible").count("TESTGOLF, GUS") == 1
        assert "TESTGOLF, GUS" not in _names(p, "discrepancy")

    def test_new_discrepancy_also_stays_on_eligible_list(self, client, sid):
        beth = _find(_preview(client, sid), "eligible", "TESTBRAVO")
        client.put(f"/api/v1/roster/member/{sid}/{beth['member_id']}", json={"REENL_ELIG_STATUS": "4H"})
        p = _preview(client, sid)
        assert "TESTBRAVO, BETH" in _names(p, "discrepancy")
        assert _names(p, "eligible").count("TESTBRAVO, BETH") == 1


class TestAddAndDelete:
    def test_added_members_are_filtered_and_sorted(self, client, sid):
        assert _add(client, sid, "TESTNOVEMBER, NED")["category"] == "eligible"
        assert _add(client, sid, "TESTJULIET, JAY", dor="01-JAN-2026")["category"] == "ineligible"
        p = _preview(client, sid)
        names = _names(p, "eligible")
        assert "TESTNOVEMBER, NED" in names and names == sorted(names, key=str.upper)
        assert "TESTJULIET, JAY" in _names(p, "ineligible")

    def test_add_does_not_copy_other_members_data(self, client, sid):
        r = client.post(f"/api/v1/roster/member/{sid}", json={
            "category": "eligible", "reason": "Member added via UI",
            "data": {"FULL_NAME": "TESTSIERRA, SAM", "GRADE": "SSG", "PAFSC": "3F071", "DOR": "01-JAN-2024",
                     "TAFMSD": "01-JUN-2020", "ASSIGNED_PAS": "ZZ1TEST", "ASSIGNED_PAS_CLEARTEXT": "99 TST/TSA"}})
        assert r.status_code == 200, r.text
        sam = _find(_preview(client, sid), "eligible", "TESTSIERRA")
        assert sam["DATE_ARRIVED_STATION"] in (None, "")

    def test_hard_delete_removes_everywhere(self, client, sid):
        gus = _find(_preview(client, sid), "eligible", "TESTGOLF")   # also on discrepancy list
        r = client.delete(f"/api/v1/roster/member/{sid}/{gus['member_id']}",
                          params={"reason": "QA", "hard_delete": True})
        assert r.status_code == 200, r.text
        p = _preview(client, sid)
        assert "TESTGOLF, GUS" not in _names(p, "eligible") + _names(p, "discrepancy")

    def test_soft_delete_hides_member(self, client, sid):
        yara = _find(_preview(client, sid), "eligible", "TESTYANKEE")
        client.delete(f"/api/v1/roster/member/{sid}/{yara['member_id']}", params={"reason": "QA"})
        assert "TESTYANKEE, YARA" not in _names(_preview(client, sid), "eligible")

    def test_delete_requires_reason(self, client, sid):
        zane = _find(_preview(client, sid), "eligible", "TESTZULU")
        r = client.delete(f"/api/v1/roster/member/{sid}/{zane['member_id']}", params={"reason": " "})
        assert r.status_code == 400


class TestMoveToEligible:
    def test_override_requires_reason(self, client, sid):
        ollie = _find(_preview(client, sid), "ineligible", "TESTOSCAR")
        r = client.post(f"/api/v1/roster/member/{sid}/{ollie['member_id']}/move-to-eligible", json={})
        assert r.status_code == 400

    def test_override_and_undo(self, client, sid):
        ollie = _find(_preview(client, sid), "ineligible", "TESTOSCAR")
        r = client.post(f"/api/v1/roster/member/{sid}/{ollie['member_id']}/move-to-eligible",
                        json={"reason": "DOR on roster is wrong; vMPF shows 01-JAN-2024"})
        assert r.status_code == 200 and r.json()["new_category"] == "eligible", r.text
        p = _preview(client, sid)
        moved = _find(p, "eligible", "TESTOSCAR")
        assert moved["override"] is True and "vMPF" in moved["override_reason"]
        assert _names(p, "ineligible") == []

        # A later edit keeps the reviewer's decision.
        client.put(f"/api/v1/roster/member/{sid}/{moved['member_id']}", json={"DAFSC": "3F071"})
        assert "TESTOSCAR, OLLIE" in _names(_preview(client, sid), "eligible")

        moved = _find(_preview(client, sid), "eligible", "TESTOSCAR")
        r = client.post(f"/api/v1/roster/member/{sid}/{moved['member_id']}/clear-override")
        assert r.json()["new_category"] == "ineligible", r.text

    def test_override_discrepancy_member(self, client, sid):
        ivy = _find(_preview(client, sid), "discrepancy", "TESTINDIA")
        client.post(f"/api/v1/roster/member/{sid}/{ivy['member_id']}/move-to-eligible", json={"reason": "Waiver"})
        p = _preview(client, sid)
        assert "TESTINDIA, IVY" not in _names(p, "discrepancy")
        assert _names(p, "eligible").count("TESTINDIA, IVY") == 1


class TestReprocessKeepsEdits:
    def test_everything_survives_reprocess(self, client, sid):
        p = _preview(client, sid)
        client.put(f"/api/v1/roster/member/{sid}/{_find(p, 'eligible', 'TESTALPHA')['member_id']}",
                   json={"FULL_NAME": "TESTALPHA, ADAM B"})
        _add(client, sid, "TESTNOVEMBER, NED")
        _add(client, sid, "TESTJULIET, JAY", dor="01-JAN-2026")
        p = _preview(client, sid)
        client.delete(f"/api/v1/roster/member/{sid}/{_find(p, 'eligible', 'TESTZULU')['member_id']}",
                      params={"reason": "QA", "hard_delete": True})
        p = _preview(client, sid)
        client.delete(f"/api/v1/roster/member/{sid}/{_find(p, 'eligible', 'TESTYANKEE')['member_id']}",
                      params={"reason": "QA"})
        p = _preview(client, sid)
        client.post(f"/api/v1/roster/member/{sid}/{_find(p, 'ineligible', 'TESTJULIET')['member_id']}/move-to-eligible",
                    json={"reason": "QA override"})
        p = _preview(client, sid)
        client.put(f"/api/v1/roster/member/{sid}/{_find(p, 'ineligible', 'TESTOSCAR')['member_id']}",
                   json={"DOR": "01-JAN-2024"})
        before = _preview(client, sid)

        r = client.post(f"/api/v1/roster/reprocess/{sid}", json={})
        assert r.status_code == 200, r.text
        after = _preview(client, sid)

        for cat in ("eligible", "ineligible", "discrepancy", "btz", "small_unit"):
            assert _names(after, cat) == _names(before, cat), cat
        eligible = _names(after, "eligible")
        assert "TESTALPHA, ADAM B" in eligible and "TESTNOVEMBER, NED" in eligible
        assert "TESTJULIET, JAY" in eligible and "TESTOSCAR, OLLIE" in eligible
        assert "TESTZULU, ZANE" not in eligible and "TESTYANKEE, YARA" not in eligible
        assert _find(after, "eligible", "TESTJULIET")["override"] is True


class TestPdfColumns:
    def test_clean_dataframe_keeps_display_columns_only(self, client, sid):
        from pdf_utils import clean_dataframe
        from session_manager import get_session
        _add(client, sid, "TESTNOVEMBER, NED")
        session = get_session(sid)
        df = clean_dataframe(session["eligible_df"])
        assert df.columns.tolist() == PDF_COLUMNS
        disc = clean_dataframe(session["discrepancy_df"])
        assert disc.columns.tolist() == PDF_COLUMNS + ["REASON"]

    def test_pdf_generates_after_edits(self, client, sid):
        p = _preview(client, sid)
        client.put(f"/api/v1/roster/member/{sid}/{_find(p, 'eligible', 'TESTALPHA')['member_id']}",
                   json={"FULL_NAME": "TESTALPHA, ADAM B"})
        _add(client, sid, "TESTNOVEMBER, NED")
        info = lambda srid: {"srid": srid, "senior_rater_rank": "Col", "senior_rater_title": "Commander",
                             "senior_rater_name": "TESTSR, CASEY", "commander_rank": "Lt Col",
                             "commander_title": "Commander", "commander_first_name": "ALEX",
                             "commander_last_name": "TESTCC"}
        r = client.post("/api/v1/initial-mel/submit/pascode-info", json={
            "session_id": sid,
            "pascode_info": {"ZZ1TEST": info("1111111"), "ZZ2TEST": info("2222222"),
                             "small_unit_sr": info("3333333")}})
        assert r.status_code == 200, r.text[:300]
        assert r.headers["content-type"].startswith("application/pdf")


class TestSmallUnits:
    def test_soft_deleted_members_do_not_count(self, client, sid):
        # ZZ1TEST has 14 eligible; soft-delete 4 -> 10 -> becomes a small unit.
        for prefix in ("TESTZULU", "TESTYANKEE", "TESTMIKE", "TESTLIMA"):
            m = _find(_preview(client, sid), "eligible", prefix)
            client.delete(f"/api/v1/roster/member/{sid}/{m['member_id']}", params={"reason": "QA"})
        p = _preview(client, sid)
        assert any(m["ASSIGNED_PAS"] == "ZZ1TEST" for m in p["categories"]["small_unit"])


class TestDateNormalisation:
    def test_iso_dates_from_the_ui_are_stored_as_roster_dates(self, client, sid):
        ollie = _find(_preview(client, sid), "ineligible", "TESTOSCAR")
        client.put(f"/api/v1/roster/member/{sid}/{ollie['member_id']}", json={"DOR": "2024-01-01"})
        moved = _find(_preview(client, sid), "eligible", "TESTOSCAR")
        assert moved["DOR"] == "01-JAN-2024"
