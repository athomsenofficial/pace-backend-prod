"""Tests for error_handling.error_response."""

import json
import pytest
from error_handling import error_response


class TestErrorResponse:
    def test_error_response_returns_correct_status(self):
        resp = error_response(400, "test")
        assert resp.status_code == 400

    def test_error_response_returns_json_with_error_key(self):
        resp = error_response(422, "test message")
        body = json.loads(resp.body.decode())
        assert body == {"error": "test message"}

    def test_error_response_does_not_leak_exception(self):
        resp = error_response(
            500,
            "Something went wrong",
            exception=ValueError("secret internal detail"),
        )
        body_text = resp.body.decode()
        assert "secret" not in body_text
        # The response should only contain the user-facing message
        body = json.loads(body_text)
        assert body == {"error": "Something went wrong"}
