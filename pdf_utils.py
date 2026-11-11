"""Shared PDF utility functions — name formatting, DataFrame cleaning, commander name resolution."""

import logging
import os
import pandas as pd

logger = logging.getLogger(__name__)


def cleanup_temp_file(path: str):
    """Remove a temporary file if it exists. For use with BackgroundTask."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def format_sig_name(first, middle, last, fallback='N/A'):
    """Format name for signature block: FIRST M. LAST"""
    first = (first or '').strip()
    middle = (middle or '').strip()
    last = (last or '').strip()
    if first or last:
        parts = []
        if first:
            parts.append(first)
        if middle:
            mi = middle if middle.endswith('.') else middle[0] + '.'
            parts.append(mi)
        if last:
            parts.append(last)
        return ' '.join(parts).upper()
    return (fallback or 'N/A').upper()


def clean_dataframe(records):
    """Clean dataframe by removing deleted records and internal columns.

    Works for both initial MEL, final MEL, and MPF list generators.
    """
    if isinstance(records, pd.DataFrame):
        df = records.copy()
    elif isinstance(records, list) and records:
        df = pd.DataFrame.from_records(records)
    else:
        return pd.DataFrame()

    # Filter out soft-deleted records
    if 'deleted' in df.columns:
        df = df[df['deleted'] != True]

    # Remove internal delete-related columns AND any UI-only columns
    columns_to_drop = ['deleted', 'deletion_reason', 'member_id',
                       'REENL_ELIG_STATUS', 'UIF_CODE', 'UIF_DISPOSITION_DATE',
                       'GRADE_PERM_PROJ', '2AFSC', '3AFSC', '4AFSC']
    for col in columns_to_drop:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Ensure only PDF-appropriate columns remain
    from constants import PDF_COLUMNS
    expected_cols = PDF_COLUMNS + ['REASON', 'SSAN', 'PAFSC']

    df_cols = df.columns.tolist()
    cols_to_keep = [col for col in df_cols if col in expected_cols or col in
                    ['FULL_NAME', 'GRADE', 'DATE_ARRIVED_STATION', 'DAFSC',
                     'ASSIGNED_PAS_CLEARTEXT', 'DOR', 'TAFMSD', 'ASSIGNED_PAS', 'REASON']]
    if cols_to_keep:
        df = df[cols_to_keep]

    # Sort alphabetically by last name (FULL_NAME is in "LAST, FIRST" format)
    if 'FULL_NAME' in df.columns and not df.empty:
        df = df.sort_values('FULL_NAME', key=lambda s: s.str.upper()).reset_index(drop=True)

    return df


def resolve_commander_name(data_source):
    """Resolve commander name from a data source dict (pascode_map entry or senior_rater dict).

    Checks both commander_* and senior_rater_* fields.
    Returns (commander_name, first, middle, last) tuple.
    """
    last = data_source.get('commander_last_name') or data_source.get('senior_rater_last_name', '')
    first = data_source.get('commander_first_name') or data_source.get('senior_rater_first_name', '')
    middle = data_source.get('commander_middle_name') or data_source.get('senior_rater_middle_name', '')

    if last or first:
        name = f"{last}, {first}"
        if middle:
            name += f" {middle}"
        name = name.strip().strip(',')
    else:
        name = data_source.get('senior_rater_name', 'N/A')

    return name, first, middle, last
