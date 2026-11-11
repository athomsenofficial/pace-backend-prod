"""Tests for roster endpoints (preview, edit, delete, add)."""

import pytest
import io
import json


def _upload_csv(client, sample_csv):
    """Upload CSV and return session_id."""
    resp = client.post(
        "/api/v1/upload/initial-mel",
        files={"file": ("test_roster.csv", sample_csv, "text/csv")},
        data={"cycle": "SSG", "year": "2025"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    return body["session_id"]


class TestPreview:
    def test_preview_returns_session_data(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)
        resp = client.get(f"/api/v1/roster/preview/{session_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session_id
        assert "cycle" in body
        assert "year" in body
        assert "statistics" in body
        assert "categories" in body

    def test_preview_invalid_session_404(self, client):
        resp = client.get("/api/v1/roster/preview/does-not-exist-session")
        assert resp.status_code == 404


class TestEditMember:
    def test_edit_member_success(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)

        # Get preview to find a valid member_id
        preview = client.get(f"/api/v1/roster/preview/{session_id}").json()
        categories = preview["categories"]
        # Find the first non-empty category
        member_id = None
        for cat_name, members in categories.items():
            if members:
                member_id = members[0].get("member_id")
                break

        assert member_id is not None, "No members found in any category after upload"

        resp = client.put(
            f"/api/v1/roster/member/{session_id}/{member_id}",
            json={"FULL_NAME": "EDITED, NAME A"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    def test_edit_invalid_member_id(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)
        resp = client.put(
            f"/api/v1/roster/member/{session_id}/badformat",
            json={"FULL_NAME": "TEST"},
        )
        assert resp.status_code == 400

    def test_edit_invalid_category(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)
        resp = client.put(
            f"/api/v1/roster/member/{session_id}/row_fakecategory_0",
            json={"FULL_NAME": "TEST"},
        )
        assert resp.status_code == 400


class TestDeleteMember:
    def test_delete_member_soft(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)

        # Get a valid member_id
        preview = client.get(f"/api/v1/roster/preview/{session_id}").json()
        member_id = None
        for cat_name, members in preview["categories"].items():
            if members:
                member_id = members[0].get("member_id")
                break

        assert member_id is not None

        resp = client.delete(
            f"/api/v1/roster/member/{session_id}/{member_id}",
            params={"reason": "test deletion", "hard_delete": "false"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True


class TestAddMember:
    def test_add_member(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)

        # Find the first non-empty category to determine which category to add to
        preview = client.get(f"/api/v1/roster/preview/{session_id}").json()
        target_category = None
        for cat_name, members in preview["categories"].items():
            if members:
                target_category = cat_name
                break

        assert target_category is not None

        resp = client.post(
            f"/api/v1/roster/member/{session_id}",
            json={
                "category": target_category,
                "data": {
                    "FULL_NAME": "NEW, MEMBER A",
                    "GRADE": "SSG",
                    "DAFSC": "3F071",
                    "ASSIGNED_PAS": "FE8GAA",
                    "ASSIGNED_PAS_CLEARTEXT": "51 FSS/FSM",
                    "DOR": "01-Jan-2023",
                    "TAFMSD": "01-Jun-2018",
                    "DATE_ARRIVED_STATION": "01-Jun-2022",
                },
                "reason": "Manual add: test add",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
