"""Shared pytest fixtures for PACE backend tests."""

import os
import io
import pytest
import pandas as pd
import fakeredis
from datetime import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient


# Set required env vars BEFORE any application module is imported
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("SESSION_ENCRYPTION_KEY", "TL89C2wq2LBuK6KhUxbyDV76HIS8IN-f-awvTto-o5c=")


@pytest.fixture(autouse=True)
def mock_redis_with_fakeredis():
    """Patch session_manager._redis_client with a fakeredis instance."""
    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    with patch("session_manager._redis_client", fake):
        yield fake


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the slowapi rate limiter between tests so upload limits don't bleed."""
    yield
    try:
        from rate_limiter import limiter
        limiter.reset()
    except Exception:
        pass


@pytest.fixture
def client():
    """FastAPI test client."""
    from main import app
    return TestClient(app)


@pytest.fixture
def sample_csv():
    """Generate a minimal valid roster CSV for testing."""
    data = {
        "FULL_NAME": ["DOE, JOHN A", "SMITH, JANE B", "JONES, BOB C"],
        "GRADE": ["SSG", "SSG", "SSG"],
        "ASSIGNED_PAS_CLEARTEXT": ["51 FSS/FSM", "51 FSS/FSM", "51 FSS/FSVS"],
        "DAFSC": ["3F071", "3F071", "1N071"],
        "DOR": ["15-Jan-2023", "01-Mar-2023", "01-Jun-2024"],
        "DATE_ARRIVED_STATION": ["01-Jun-2022", "15-Aug-2021", "01-Mar-2023"],
        "TAFMSD": ["01-Jun-2018", "01-Jan-2017", "01-Sep-2019"],
        "REENL_ELIG_STATUS": [None, None, None],
        "ASSIGNED_PAS": ["FE8GAA", "FE8GAA", "FE8GAB"],
        "PAFSC": ["3F071", "3F071", "1N071"],
        "GRADE_PERM_PROJ": [None, None, None],
        "UIF_CODE": [None, None, None],
        "UIF_DISPOSITION_DATE": [None, None, None],
        "2AFSC": [None, None, None],
        "3AFSC": [None, None, None],
        "4AFSC": [None, None, None],
    }
    df = pd.DataFrame(data)
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer


@pytest.fixture
def sample_roster_df():
    """Sample roster DataFrame with realistic military data."""
    return pd.DataFrame([
        {
            "FULL_NAME": "DOE, JOHN A",
            "GRADE": "SSG",
            "DOR": "01-Jan-2022",
            "TAFMSD": "15-Jun-2016",
            "ASSIGNED_PAS": "ABCD1234",
            "ASSIGNED_PAS_CLEARTEXT": "51 FSS/FSH",
            "DAFSC": "3F071",
            "PAFSC": "3F071",
            "DATE_ARRIVED_STATION": "01-Mar-2020",
            "UIF_CODE": 0,
            "UIF_DISPOSITION_DATE": None,
            "REENL_ELIG_STATUS": None,
            "2AFSC": None,
            "3AFSC": None,
            "4AFSC": None,
            "GRADE_PERM_PROJ": None,
        },
        {
            "FULL_NAME": "SMITH, JANE B",
            "GRADE": "SSG",
            "DOR": "01-Jul-2023",
            "TAFMSD": "10-May-2018",
            "ASSIGNED_PAS": "EFGH5678",
            "ASSIGNED_PAS_CLEARTEXT": "51 CES/CEF",
            "DAFSC": "3E071",
            "PAFSC": "3E071",
            "DATE_ARRIVED_STATION": "15-Sep-2021",
            "UIF_CODE": 0,
            "UIF_DISPOSITION_DATE": None,
            "REENL_ELIG_STATUS": None,
            "2AFSC": None,
            "3AFSC": None,
            "4AFSC": None,
            "GRADE_PERM_PROJ": None,
        },
    ])


@pytest.fixture
def sample_session_data():
    """Sample session data dict as stored in Redis."""
    return {
        "cycle": "SSG",
        "year": 2025,
        "eligible_df": [
            {"FULL_NAME": "DOE, JOHN A", "GRADE": "SSG", "DAFSC": "3F071",
             "ASSIGNED_PAS": "ABCD1234", "ASSIGNED_PAS_CLEARTEXT": "51 FSS/FSH",
             "DOR": "01-Jan-2022", "TAFMSD": "15-Jun-2016",
             "DATE_ARRIVED_STATION": "01-Mar-2020"}
        ],
        "ineligible_df": [],
        "discrepancy_df": [],
        "btz_df": [],
        "small_unit_df": [],
        "pascodes": ["ABCD1234"],
        "pascode_unit_map": {"ABCD1234": "51 FSS/FSH"},
        "error_log": [],
    }
