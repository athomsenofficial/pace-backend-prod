"""Tests for logo upload/get/delete endpoints in routers/roster.py."""

import io
import struct
import zlib
import pytest


def create_tiny_png():
    """Create a minimal 1x1 white PNG."""
    def chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    raw = zlib.compress(b'\x00\xff\xff\xff')
    idat = chunk(b'IDAT', raw)
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


def _upload_csv(client, sample_csv):
    """Upload CSV and return session_id."""
    resp = client.post(
        "/api/v1/upload/initial-mel",
        files={"file": ("test_roster.csv", sample_csv, "text/csv")},
        data={"cycle": "SSG", "year": "2025"},
    )
    assert resp.status_code == 200
    return resp.json()["session_id"]


class TestUploadLogo:
    def test_upload_logo_success(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)
        png_data = create_tiny_png()

        resp = client.post(
            f"/api/v1/roster/logo/{session_id}",
            files={"logo": ("logo.png", io.BytesIO(png_data), "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    def test_upload_logo_rejects_invalid_type(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)

        resp = client.post(
            f"/api/v1/roster/logo/{session_id}",
            files={"logo": ("bad.txt", io.BytesIO(b"not an image"), "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_logo_rejects_oversized(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)
        # Create data > 2MB
        big_data = b"\x00" * (2 * 1024 * 1024 + 1)

        resp = client.post(
            f"/api/v1/roster/logo/{session_id}",
            files={"logo": ("big.png", io.BytesIO(big_data), "image/png")},
        )
        assert resp.status_code == 400


class TestGetLogo:
    def test_get_logo_not_found(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)
        resp = client.get(f"/api/v1/roster/logo/{session_id}")
        assert resp.status_code == 404


class TestDeleteLogo:
    def test_delete_logo(self, client, sample_csv):
        session_id = _upload_csv(client, sample_csv)
        png_data = create_tiny_png()

        # Upload first
        upload_resp = client.post(
            f"/api/v1/roster/logo/{session_id}",
            files={"logo": ("logo.png", io.BytesIO(png_data), "image/png")},
        )
        assert upload_resp.status_code == 200

        # Delete
        del_resp = client.delete(f"/api/v1/roster/logo/{session_id}")
        assert del_resp.status_code == 200
        body = del_resp.json()
        assert body["success"] is True
