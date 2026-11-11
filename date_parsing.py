import pandas as pd
from datetime import datetime
from typing import Optional, List, Union


def _to_naive_datetime(ts: Union[datetime, pd.Timestamp]) -> datetime:
    """Return a timezone-naive ``datetime``.

    Roster values occasionally arrive as timezone-aware ISO strings (e.g.
    ``2024-03-15T00:00:00+09:00``). Every downstream comparison in the
    eligibility pipeline uses naive datetimes, so mixing in an aware value
    raises ``TypeError: can't compare offset-naive and offset-aware datetimes``
    and 500s the whole upload. We drop the tzinfo while preserving the
    wall-clock date (intentionally NOT converting to UTC, which could shift the
    calendar date and flip an eligibility decision).
    """
    dt = pd.to_datetime(ts).to_pydatetime()
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def parse_date(
    value: Union[str, int, float, datetime, pd.Timestamp, None],
    error_log: Optional[List[str]] = None,
    full_name: Optional[str] = None
) -> Optional[datetime]:
    if pd.isna(value) or value is None or value == '':
        return None

    original_value = value
    original_type = type(value)

    if isinstance(value, (datetime, pd.Timestamp)):
        return _to_naive_datetime(value)

    # Handle Excel serial dates (numbers)
    if isinstance(value, (int, float)):
        try:
            # Excel serial dates start from 1900-01-01
            if 1 <= value <= 2958465:
                return _to_naive_datetime(
                    pd.to_datetime(value, unit="D", origin="1899-12-30")
                )
        except Exception:
            pass

    # Use pandas to_datetime with inference as the primary method
    if isinstance(value, str):
        try:
            result = pd.to_datetime(value.strip())
            if pd.notna(result):
                return _to_naive_datetime(result)
        except Exception:
            pass

    if error_log is not None and full_name:
        error_log.append(f"Date parsing failed for {full_name}: '{original_value}' (type: {original_type})")

    return None