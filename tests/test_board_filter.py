"""
Step 15: Unit tests for board_filter — per grade eligibility checks.

Run: pytest tests/test_board_filter.py -v
"""
import pytest
from datetime import datetime
from classes import EligibilityResult


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def eligible_ssg():
    """SSG member who meets all requirements for 2025 cycle."""
    return dict(
        grade="SSG",
        year=2025,
        date_of_rank=datetime(2023, 1, 15),   # >23 months TIG
        uif_code=0,
        uif_disposition_date=None,
        tafmsd=datetime(2018, 6, 1),           # >5 years TIS
        re_status=None,
        pafsc="3F071",                          # 7-level (meets SSG requirement)
        two_afsc=None,
        three_afsc=None,
        four_afsc=None,
        member_name="TEST MEMBER",
        roster_type="mel",
        logger=None,
    )


@pytest.fixture
def eligible_sra():
    """SRA member who meets all requirements for 2025 cycle."""
    return dict(
        grade="SRA",
        year=2025,
        date_of_rank=datetime(2024, 12, 1),    # >6 months TIG by Sep 2026
        uif_code=0,
        uif_disposition_date=None,
        tafmsd=datetime(2021, 6, 1),           # >3 years TIS
        re_status=None,
        pafsc="3F051",                          # 5-level (meets SRA requirement)
        two_afsc=None,
        three_afsc=None,
        four_afsc=None,
        member_name="TEST SRA",
        roster_type="mel",
        logger=None,
    )


@pytest.fixture
def eligible_tsg():
    """TSG member who meets all requirements for 2025 cycle."""
    return dict(
        grade="TSG",
        year=2025,
        date_of_rank=datetime(2023, 6, 1),     # >24 months TIG
        uif_code=0,
        uif_disposition_date=None,
        tafmsd=datetime(2016, 1, 1),           # >8 years TIS
        re_status=None,
        pafsc="3F071",                          # 7-level
        two_afsc=None,
        three_afsc=None,
        four_afsc=None,
        member_name="TEST TSG",
        roster_type="mel",
        logger=None,
    )


@pytest.fixture
def eligible_msg():
    """MSG member who meets all requirements for 2025 cycle."""
    return dict(
        grade="MSG",
        year=2025,
        date_of_rank=datetime(2023, 10, 1),    # >20 months TIG
        uif_code=0,
        uif_disposition_date=None,
        tafmsd=datetime(2013, 1, 1),           # >11 years TIS
        re_status=None,
        pafsc="3F071",
        two_afsc=None,
        three_afsc=None,
        four_afsc=None,
        member_name="TEST MSG",
        roster_type="mel",
        logger=None,
    )


@pytest.fixture
def eligible_sms():
    """SMS member who meets all requirements for 2025 cycle."""
    return dict(
        grade="SMS",
        year=2025,
        date_of_rank=datetime(2023, 5, 1),     # >21 months TIG
        uif_code=0,
        uif_disposition_date=None,
        tafmsd=datetime(2010, 1, 1),           # >14 years TIS
        re_status=None,
        pafsc="3F091",                          # 9-level
        two_afsc=None,
        three_afsc=None,
        four_afsc=None,
        member_name="TEST SMS",
        roster_type="mel",
        logger=None,
    )


# ─── Tests: Eligible members pass ────────────────────────────────────────────

class TestEligibleMembers:
    """Members who meet all requirements should get 'eligible' status."""

    def test_ssg_eligible(self, eligible_ssg):
        from board_filter import board_filter
        result = board_filter(**eligible_ssg)
        assert isinstance(result, EligibilityResult)
        assert result.status == "eligible"

    def test_sra_eligible(self, eligible_sra):
        from board_filter import board_filter
        result = board_filter(**eligible_sra)
        assert isinstance(result, EligibilityResult)
        assert result.status == "eligible"

    def test_tsg_eligible(self, eligible_tsg):
        from board_filter import board_filter
        result = board_filter(**eligible_tsg)
        assert isinstance(result, EligibilityResult)
        assert result.status == "eligible"

    def test_msg_eligible(self, eligible_msg):
        from board_filter import board_filter
        result = board_filter(**eligible_msg)
        assert isinstance(result, EligibilityResult)
        assert result.status == "eligible"

    def test_sms_eligible(self, eligible_sms):
        from board_filter import board_filter
        result = board_filter(**eligible_sms)
        assert isinstance(result, EligibilityResult)
        assert result.status == "eligible"


# ─── Tests: TIG failures ─────────────────────────────────────────────────────

class TestTIGFailures:
    """Members who don't meet Time in Grade should be ineligible."""

    def test_ssg_insufficient_tig(self, eligible_ssg):
        from board_filter import board_filter
        eligible_ssg["date_of_rank"] = datetime(2025, 6, 1)  # Too recent
        result = board_filter(**eligible_ssg)
        assert result.status == "ineligible"
        assert "TIG" in result.reason

    def test_tsg_insufficient_tig(self, eligible_tsg):
        from board_filter import board_filter
        eligible_tsg["date_of_rank"] = datetime(2025, 6, 1)  # Too recent
        result = board_filter(**eligible_tsg)
        assert result.status == "ineligible"
        assert "TIG" in result.reason


# ─── Tests: TIS failures ─────────────────────────────────────────────────────

class TestTISFailures:
    """Members who don't meet Time in Service should be ineligible."""

    def test_ssg_insufficient_tis(self, eligible_ssg):
        from board_filter import board_filter
        eligible_ssg["tafmsd"] = datetime(2024, 1, 1)  # Only ~1 year TIS
        result = board_filter(**eligible_ssg)
        assert result.status == "ineligible"
        assert "TIS" in result.reason

    def test_sra_insufficient_tis(self, eligible_sra):
        from board_filter import board_filter
        eligible_sra["tafmsd"] = datetime(2024, 6, 1)  # Only ~1 year TIS
        result = board_filter(**eligible_sra)
        assert result.status == "ineligible"
        assert "TIS" in result.reason


# ─── Tests: HYT failures ─────────────────────────────────────────────────────

class TestHYTFailures:
    """Members who exceed High Year of Tenure should be ineligible."""

    def test_ssg_hyt_exceeded(self, eligible_ssg):
        from board_filter import board_filter
        eligible_ssg["tafmsd"] = datetime(2004, 1, 1)  # >20 years — exceeds SSG HYT
        result = board_filter(**eligible_ssg)
        assert result.status == "ineligible"
        assert "tenure" in result.reason.lower()


# ─── Tests: Missing required dates ───────────────────────────────────────────

class TestMissingDates:
    """Members with missing required dates should be ineligible."""

    def test_missing_dor(self, eligible_ssg):
        from board_filter import board_filter
        eligible_ssg["date_of_rank"] = None
        result = board_filter(**eligible_ssg)
        assert result.status == "ineligible"
        assert "missing" in result.reason.lower() or "unreadable" in result.reason.lower()

    def test_missing_tafmsd(self, eligible_ssg):
        from board_filter import board_filter
        eligible_ssg["tafmsd"] = None
        result = board_filter(**eligible_ssg)
        assert result.status == "ineligible"


# ─── Tests: UIF discrepancy ──────────────────────────────────────────────────

class TestUIFDiscrepancy:
    """Members with UIF codes should get discrepancy flag on MEL."""

    def test_uif_triggers_discrepancy(self, eligible_ssg):
        from board_filter import board_filter
        eligible_ssg["uif_code"] = 3
        eligible_ssg["uif_disposition_date"] = datetime(2025, 6, 1)  # Before SCOD
        result = board_filter(**eligible_ssg)
        assert result.status == "discrepancy"
        assert "UIF" in result.reason


# ─── Tests: RE code discrepancy ──────────────────────────────────────────────

class TestRECodeDiscrepancy:
    """Members with adverse RE codes should get discrepancy flag."""

    def test_re_code_2a(self, eligible_ssg):
        from board_filter import board_filter
        eligible_ssg["re_status"] = "2A"
        result = board_filter(**eligible_ssg)
        assert result.status == "discrepancy"
        assert "2A" in result.reason


# ─── Tests: PAFSC skill level ────────────────────────────────────────────────

class TestPAFSCSkillLevel:
    """Members with insufficient skill level should get discrepancy."""

    def test_ssg_insufficient_skill_level(self, eligible_ssg):
        from board_filter import board_filter
        eligible_ssg["pafsc"] = "3F031"  # 3-level, SSG needs 7
        eligible_ssg["two_afsc"] = None
        eligible_ssg["three_afsc"] = None
        eligible_ssg["four_afsc"] = None
        result = board_filter(**eligible_ssg)
        assert result.status == "discrepancy"
        assert "PAFSC" in result.reason or "skill" in result.reason.lower()


# ─── Tests: A1C / BTZ ────────────────────────────────────────────────────────

class TestA1CBTZ:
    """A1C-specific checks including BTZ eligibility."""

    def test_a1c_standard_eligible(self):
        from board_filter import board_filter
        result = board_filter(
            grade="A1C",
            year=2025,
            date_of_rank=datetime(2022, 3, 1),   # DOR+28=Jul2024 <= Feb2025 cutoff -> True
            uif_code=0,
            uif_disposition_date=None,
            tafmsd=datetime(2023, 6, 1),          # 3yr TIS=Jun2026 > SCOD Mar2026 -> no exclusion
            re_status=None,
            pafsc="3F031",
            two_afsc=None, three_afsc=None, four_afsc=None,
            member_name="TEST A1C",
            roster_type="mel",
            logger=None,
        )
        assert isinstance(result, EligibilityResult)
        assert result.status == "eligible"

    def test_a1c_btz_eligible(self):
        from board_filter import board_filter
        result = board_filter(
            grade="A1C",
            year=2025,
            date_of_rank=datetime(2023, 4, 1),    # DOR+28=Aug2025 > Feb cutoff -> None (BTZ path)
            uif_code=0,                             # DOR+22=Feb2025 <= Feb2025 cutoff -> BTZ True
            uif_disposition_date=None,
            tafmsd=datetime(2023, 6, 1),           # 3yr TIS=Jun2026 > SCOD Mar2026 (no exclusion)
            re_status=None,
            pafsc="3F031",
            two_afsc=None, three_afsc=None, four_afsc=None,
            member_name="TEST BTZ",
            roster_type="mel",
            logger=None,
        )
        assert isinstance(result, EligibilityResult)
        assert result.status == "btz"


# ─── Tests: EligibilityResult type ───────────────────────────────────────────

class TestEligibilityResultType:
    """Verify the EligibilityResult dataclass works correctly."""

    def test_eligible_is_eligible(self):
        r = EligibilityResult("eligible")
        assert r.is_eligible is True
        assert r.reason is None

    def test_ineligible_is_not_eligible(self):
        r = EligibilityResult("ineligible", "TIG too short")
        assert r.is_eligible is False
        assert r.reason == "TIG too short"

    def test_btz_is_eligible(self):
        r = EligibilityResult("btz")
        assert r.is_eligible is True

    def test_discrepancy_is_eligible(self):
        r = EligibilityResult("discrepancy", "UIF code: 3")
        assert r.is_eligible is True

    def test_skip_is_not_eligible(self):
        r = EligibilityResult("skip")
        assert r.is_eligible is False
