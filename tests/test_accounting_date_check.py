"""Tests for accounting_date_check module."""

import pytest
from datetime import datetime
from accounting_date_check import accounting_date_check


class TestAccountingDateCheck:
    def test_returns_false_for_none_das(self):
        assert accounting_date_check(None, "SSG", 2025) is False

    def test_member_within_window_passes(self):
        # A member who arrived well before the accounting date
        das = datetime(2020, 1, 1)
        result = accounting_date_check(das, "SSG", 2025)
        assert result is True

    def test_member_arrived_recently_fails(self):
        # A member who arrived after the accounting date (very recent)
        das = datetime(2025, 12, 1)
        result = accounting_date_check(das, "SSG", 2025)
        assert result is False

    def test_sra_cycle_accounting_date(self):
        das = datetime(2020, 6, 15)
        result = accounting_date_check(das, "SRA", 2025)
        assert result is True

    def test_msg_cycle_accounting_date(self):
        das = datetime(2020, 3, 1)
        result = accounting_date_check(das, "MSG", 2025)
        assert result is True

    def test_boundary_date_on_accounting_date(self):
        # Member arrived exactly on the accounting date boundary
        # This tests the <= comparison
        das = datetime(2020, 1, 3)  # Should be on or before adjusted date
        result = accounting_date_check(das, "SSG", 2025)
        assert result is True
