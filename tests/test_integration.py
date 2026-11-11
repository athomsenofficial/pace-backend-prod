"""
Integration test — full upload → preview → download cycle.

Run: pytest tests/test_integration.py -v

Uses client and sample_csv fixtures from conftest.py.
"""
import pytest
import io
import pandas as pd


# ─── Test: Health check ──────────────────────────────────────────────────────

class TestHealthCheck:

    def test_health_v1(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"] == "pace-backend"

    def test_health_legacy_redirect(self, client):
        response = client.get("/api/health", follow_redirects=False)
        assert response.status_code == 307
        assert "/api/v1/health" in response.headers["location"]


# ─── Test: Upload → Preview cycle ────────────────────────────────────────────

class TestUploadPreviewCycle:

    def test_initial_mel_upload(self, client, sample_csv):
        """Upload a CSV and verify we get a session back."""
        response = client.post(
            "/api/v1/upload/initial-mel",
            files={"file": ("test_roster.csv", sample_csv, "text/csv")},
            data={"cycle": "SSG", "year": "2025"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["session_id"] is not None

    def test_upload_then_preview(self, client, sample_csv):
        """Upload, then fetch preview and verify member data."""
        # Upload
        upload_resp = client.post(
            "/api/v1/upload/initial-mel",
            files={"file": ("test_roster.csv", sample_csv, "text/csv")},
            data={"cycle": "SSG", "year": "2025"},
        )
        assert upload_resp.status_code == 200
        session_id = upload_resp.json()["session_id"]

        # Preview
        preview_resp = client.get(f"/api/v1/roster/preview/{session_id}")
        assert preview_resp.status_code == 200
        body = preview_resp.json()
        assert body["session_id"] == session_id
        assert body["cycle"] == "SSG"
        assert body["year"] == 2025

        # Should have processed members into categories
        stats = body["statistics"]
        total = stats["eligible"] + stats["ineligible"] + stats["discrepancy"] + stats["btz"]
        assert total > 0, "At least one member should be categorized"

    def test_upload_invalid_cycle(self, client, sample_csv):
        """Invalid cycle should return error."""
        response = client.post(
            "/api/v1/upload/initial-mel",
            files={"file": ("test.csv", sample_csv, "text/csv")},
            data={"cycle": "INVALID", "year": "2025"},
        )
        assert response.status_code == 400

    def test_upload_invalid_file_type(self, client):
        """Non-CSV/XLSX file should be rejected."""
        fake_file = io.BytesIO(b"not a csv")
        response = client.post(
            "/api/v1/upload/initial-mel",
            files={"file": ("test.txt", fake_file, "text/plain")},
            data={"cycle": "SSG", "year": "2025"},
        )
        assert response.status_code == 400


# ─── Test: Session not found ─────────────────────────────────────────────────

class TestSessionNotFound:

    def test_preview_invalid_session(self, client):
        response = client.get("/api/v1/roster/preview/nonexistent-session-id")
        assert response.status_code == 404
        body = response.json()
        assert "error" in str(body).lower()


# ─── Test: Calculator endpoints ──────────────────────────────────────────────

class TestCalculators:

    def test_promotion_eligibility(self, client):
        response = client.post("/api/v1/calculators/promotion-eligibility", json={
            "tig_date": "15-Jan-2023",
            "tis_date": "01-Jun-2018",
            "current_rank": "SSG",
            "target_year": 2025,
        })
        assert response.status_code == 200
        body = response.json()
        assert "eligible" in body

    def test_btz_eligibility(self, client):
        response = client.post("/api/v1/calculators/btz-eligibility", json={
            "enlistment_date": "01-Jan-2023",
            "a1c_dor": "01-Jul-2023",
            "target_year": 2025,
        })
        assert response.status_code == 200
        body = response.json()
        assert "eligible" in body

    def test_invalid_rank(self, client):
        response = client.post("/api/v1/calculators/promotion-eligibility", json={
            "tig_date": "15-Jan-2023",
            "tis_date": "01-Jun-2018",
            "current_rank": "INVALID",
            "target_year": 2025,
        })
        assert response.status_code in [200, 400]
