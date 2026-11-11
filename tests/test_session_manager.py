"""Tests for session_manager module."""

import json
import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        from session_manager import _encrypt_data, _decrypt_data
        original = '{"test": "data", "number": 42}'
        encrypted = _encrypt_data(original)
        assert encrypted != original
        decrypted = _decrypt_data(encrypted)
        assert decrypted == original

    def test_is_encrypted_detects_fernet_tokens(self):
        from session_manager import _is_encrypted
        fernet = Fernet(Fernet.generate_key())
        token = fernet.encrypt(b"test").decode()
        assert _is_encrypted(token) is True

    def test_is_encrypted_rejects_plain_json(self):
        from session_manager import _is_encrypted
        assert _is_encrypted('{"key": "value"}') is False

    def test_is_encrypted_handles_empty_string(self):
        from session_manager import _is_encrypted
        assert _is_encrypted("") is False


class TestComprehensiveSanitize:
    def test_sanitizes_datetime(self):
        from session_manager import _comprehensive_sanitize
        result = _comprehensive_sanitize({"date": datetime(2023, 6, 15)})
        assert result == {"date": "2023-06-15T00:00:00"}

    def test_sanitizes_nan(self):
        from session_manager import _comprehensive_sanitize
        result = _comprehensive_sanitize({"val": float("nan")})
        assert result == {"val": None}

    def test_sanitizes_nested(self):
        from session_manager import _comprehensive_sanitize
        result = _comprehensive_sanitize([{"ts": pd.Timestamp("2023-01-15")}])
        assert result == [{"ts": "2023-01-15T00:00:00"}]

    def test_preserves_strings(self):
        from session_manager import _comprehensive_sanitize
        assert _comprehensive_sanitize("hello") == "hello"

    def test_preserves_none(self):
        from session_manager import _comprehensive_sanitize
        assert _comprehensive_sanitize(None) is None


class TestCreateSession:
    def test_creates_session_with_dataframes(self):
        from session_manager import create_session
        processed_df = pd.DataFrame({"FULL_NAME": ["DOE, JOHN"], "GRADE": ["SSG"]})
        pdf_df = pd.DataFrame({"FULL_NAME": ["DOE, JOHN"], "GRADE": ["SSG"]})

        session_id = create_session(processed_df, pdf_df)
        assert session_id is not None
        assert len(session_id) == 36  # UUID format

    def test_uses_provided_session_id(self):
        from session_manager import create_session
        processed_df = pd.DataFrame({"A": [1]})
        pdf_df = pd.DataFrame({"A": [1]})

        session_id = create_session(processed_df, pdf_df, session_id="test-id-123")
        assert session_id == "test-id-123"


class TestGetSession:
    def test_returns_none_for_missing_session(self):
        from session_manager import get_session
        assert get_session("nonexistent") is None

    def test_returns_decrypted_data(self):
        from session_manager import get_session, _encrypt_data, _get_redis
        data = {"cycle": "SSG", "year": 2025}
        encrypted = _encrypt_data(json.dumps(data))
        _get_redis().set("test-id", encrypted)

        result = get_session("test-id")
        assert result == data

    def test_handles_legacy_unencrypted_data(self):
        from session_manager import get_session, _get_redis
        data = {"cycle": "SSG", "year": 2025}
        _get_redis().set("test-id", json.dumps(data))

        result = get_session("test-id")
        assert result == data


class TestDeleteSession:
    def test_deletes_session(self):
        from session_manager import delete_session, _get_redis, _encrypt_data
        # Store something first
        _get_redis().set("test-id", _encrypt_data(json.dumps({"a": 1})))
        delete_session("test-id")
        assert _get_redis().get("test-id") is None
