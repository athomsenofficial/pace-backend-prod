"""Tests for pdf_utils module."""

import pytest
import pandas as pd
from pdf_utils import format_sig_name, clean_dataframe, resolve_commander_name


class TestFormatSigName:
    def test_full_name(self):
        result = format_sig_name("John", "Michael", "Doe")
        assert result == "JOHN M. DOE"

    def test_first_and_last_only(self):
        result = format_sig_name("John", "", "Doe")
        assert result == "JOHN DOE"

    def test_middle_with_period(self):
        result = format_sig_name("John", "M.", "Doe")
        assert result == "JOHN M. DOE"

    def test_fallback_when_no_names(self):
        result = format_sig_name("", "", "", fallback="FALLBACK NAME")
        assert result == "FALLBACK NAME"

    def test_none_values(self):
        result = format_sig_name(None, None, None)
        assert result == "N/A"

    def test_whitespace_stripped(self):
        result = format_sig_name("  John  ", "  M  ", "  Doe  ")
        assert result == "JOHN M. DOE"


class TestCleanDataframe:
    def test_empty_list_returns_empty_df(self):
        result = clean_dataframe([])
        assert result.empty

    def test_filters_deleted_records(self):
        records = [
            {"FULL_NAME": "DOE, JOHN", "GRADE": "SSG", "deleted": False},
            {"FULL_NAME": "SMITH, JANE", "GRADE": "SSG", "deleted": True},
        ]
        result = clean_dataframe(records)
        assert len(result) == 1

    def test_drops_internal_columns(self):
        records = [
            {"FULL_NAME": "DOE", "GRADE": "SSG", "member_id": "row_0",
             "deletion_reason": None, "deleted": False}
        ]
        result = clean_dataframe(records)
        assert "member_id" not in result.columns
        assert "deletion_reason" not in result.columns
        assert "deleted" not in result.columns

    def test_handles_dataframe_input(self):
        df = pd.DataFrame([{"FULL_NAME": "DOE", "GRADE": "SSG"}])
        result = clean_dataframe(df)
        assert len(result) == 1

    def test_none_returns_empty_df(self):
        result = clean_dataframe(None)
        assert result.empty


class TestResolveCommanderName:
    def test_commander_fields(self):
        data = {
            "commander_first_name": "John",
            "commander_middle_name": "M",
            "commander_last_name": "Smith",
        }
        name, first, middle, last = resolve_commander_name(data)
        assert name == "Smith, John M"
        assert first == "John"
        assert last == "Smith"

    def test_falls_back_to_senior_rater(self):
        data = {
            "senior_rater_first_name": "Jane",
            "senior_rater_last_name": "Doe",
        }
        name, first, middle, last = resolve_commander_name(data)
        assert "Doe" in name
        assert "Jane" in name

    def test_falls_back_to_senior_rater_name(self):
        data = {"senior_rater_name": "COL SMITH"}
        name, first, middle, last = resolve_commander_name(data)
        assert name == "COL SMITH"

    def test_empty_data(self):
        name, first, middle, last = resolve_commander_name({})
        assert name == "N/A"
