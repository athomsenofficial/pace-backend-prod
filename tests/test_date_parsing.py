"""Tests for date_parsing module."""

import pytest
from datetime import datetime
import pandas as pd
from date_parsing import parse_date


class TestParseDate:
    def test_returns_none_for_none(self):
        assert parse_date(None) is None

    def test_returns_none_for_empty_string(self):
        assert parse_date("") is None

    def test_returns_none_for_nan(self):
        assert parse_date(float("nan")) is None

    def test_returns_none_for_pd_nat(self):
        assert parse_date(pd.NaT) is None

    def test_parses_iso_format(self):
        result = parse_date("2023-01-15")
        assert result == datetime(2023, 1, 15)

    def test_parses_military_format(self):
        result = parse_date("15-Jan-2023")
        assert result == datetime(2023, 1, 15)

    def test_parses_us_format(self):
        result = parse_date("01/15/2023")
        assert result == datetime(2023, 1, 15)

    def test_passes_through_datetime_objects(self):
        dt = datetime(2023, 6, 15)
        result = parse_date(dt)
        assert result == dt

    def test_passes_through_pd_timestamp(self):
        ts = pd.Timestamp("2023-06-15")
        result = parse_date(ts)
        assert result == datetime(2023, 6, 15)

    def test_parses_excel_serial_date(self):
        # Excel serial 44927 = 2023-01-01
        result = parse_date(44927)
        assert result is not None
        assert result.year == 2023

    def test_invalid_excel_serial_zero(self):
        result = parse_date(0)
        assert result is None

    def test_invalid_string_returns_none(self):
        result = parse_date("not-a-date")
        assert result is None

    def test_error_log_populated_on_failure(self):
        error_log = []
        parse_date("garbage", error_log=error_log, full_name="SMITH, JOHN")
        assert len(error_log) == 1
        assert "SMITH, JOHN" in error_log[0]

    def test_error_log_not_populated_without_full_name(self):
        error_log = []
        parse_date("garbage", error_log=error_log)
        assert len(error_log) == 0
