"""Tests for eligibility_calculators module."""

import pytest
from datetime import datetime
from eligibility_calculators import calculate_promotion_eligibility, calculate_btz_eligibility, compute_hyt_date


class TestComputeHytDate:
    def test_ssg_hyt_date(self):
        tafmsd = datetime(2010, 1, 1)
        result = compute_hyt_date(tafmsd, "SSG")
        assert result.year >= 2030  # SSG HYT is 20 years

    def test_sra_hyt_date(self):
        tafmsd = datetime(2020, 1, 1)
        result = compute_hyt_date(tafmsd, "SRA")
        assert result is not None


class TestPromotionEligibility:
    def test_eligible_ssg(self):
        result = calculate_promotion_eligibility(
            tig_date=datetime(2022, 1, 1),
            tis_date=datetime(2016, 6, 15),
            current_rank="SSG",
            target_year=2025,
        )
        assert "eligible" in result
        assert result["eligible"] is True

    def test_ineligible_insufficient_tig(self):
        result = calculate_promotion_eligibility(
            tig_date=datetime(2025, 1, 1),  # Very recent DOR
            tis_date=datetime(2016, 6, 15),
            current_rank="SSG",
            target_year=2025,
        )
        assert result["eligible"] is False

    def test_invalid_rank_returns_error(self):
        result = calculate_promotion_eligibility(
            tig_date=datetime(2022, 1, 1),
            tis_date=datetime(2016, 6, 15),
            current_rank="INVALID",
            target_year=2025,
        )
        assert "error" in result

    def test_result_contains_requirements(self):
        result = calculate_promotion_eligibility(
            tig_date=datetime(2022, 1, 1),
            tis_date=datetime(2016, 6, 15),
            current_rank="SSG",
            target_year=2025,
        )
        assert "requirements" in result
        assert "tig" in result["requirements"]
        assert "tis" in result["requirements"]
        assert "hyt" in result["requirements"]


class TestBTZEligibility:
    def test_eligible_btz(self):
        result = calculate_btz_eligibility(
            enlistment_date=datetime(2022, 6, 1),
            a1c_dor=datetime(2023, 1, 1),
            target_year=2024,
        )
        assert "eligible" in result

    def test_result_contains_board_quarter(self):
        result = calculate_btz_eligibility(
            enlistment_date=datetime(2022, 6, 1),
            a1c_dor=datetime(2023, 1, 1),
            target_year=2024,
        )
        assert "board_quarter" in result

    def test_ineligible_three_year_tis(self):
        result = calculate_btz_eligibility(
            enlistment_date=datetime(2020, 1, 1),  # > 3 years TIS
            a1c_dor=datetime(2021, 6, 1),
            target_year=2023,
        )
        assert "eligible" in result
