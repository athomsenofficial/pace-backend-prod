# In roster_processor.py

import pandas as pd
from accounting_date_check import accounting_date_check
from board_filter import board_filter
from session_manager import update_session, get_session
from constants import (
    REQUIRED_COLUMNS, OPTIONAL_COLUMNS, PDF_COLUMNS,
    GRADE_MAP, PROMOTIONAL_MAP, small_unit_threshold, max_unit_length,
    OFFICER_RANKS, ENLISTED_RANKS
)

from datetime import datetime
from date_parsing import parse_date
from logging_config import LoggerSetup, to_initials
from classes import EligibilityResult

def format_date_for_display(date_value):
    """Format date for display in PDFs as DD-MMM-YYYY"""
    if pd.isna(date_value) or date_value is None:
        return None

    if isinstance(date_value, str):
        parsed_date = parse_date(date_value)
        if parsed_date:
            return parsed_date.strftime("%d-%b-%Y").upper()
        return date_value

    if isinstance(date_value, (datetime, pd.Timestamp)):
        return date_value.strftime("%d-%b-%Y").upper()

    return str(date_value)

def roster_processor(roster_df, session_id, cycle, year, roster_type="mel"):
    # Create session-specific logger
    logger = LoggerSetup.get_session_logger(session_id, cycle, year)
    logger.info(f"Processing {len(roster_df)} members")

    eligible_service_members = []
    eligible_btz_service_members = []
    ineligible_service_members = []
    small_unit_eligible_service_members = []
    discrepancy_service_members = []


    pascodes = []
    small_unit_pascodes = []
    reason_for_ineligible_map = {}
    pascodeUnitMap = {}
    unit_total_map = {}

    error_log = []

    all_roster_columns = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

    missing_columns = [col for col in all_roster_columns if col not in roster_df.columns]
    if missing_columns:
        error_msg = f"Missing required columns: {', '.join(missing_columns)}"
        error_log.append(error_msg)
        logger.error(error_msg)
        logger.info(f"STATUS: FAILED")
        update_session(session_id, error_log=error_log)
        LoggerSetup.close_session_logger(session_id)
        return

    filtered_roster_df = roster_df[all_roster_columns].copy()

    # Parse all date columns in the DataFrame ONCE, before processing
    date_columns = ['DOR', 'UIF_DISPOSITION_DATE', 'TAFMSD', 'DATE_ARRIVED_STATION']
    for col in date_columns:
        if col in filtered_roster_df.columns:
            filtered_roster_df[col] = filtered_roster_df[col].apply(
                lambda x: parse_date(x, error_log, None)
            )

    for index, row in filtered_roster_df.iterrows():
        member_name = row.get('FULL_NAME', 'Unknown')
        grade = row.get('GRADE', 'Unknown')

        # Check for officer ranks - skip silently
        if row['GRADE'] in OFFICER_RANKS:
            msg = f"Officer {row['FULL_NAME']} ({row['GRADE']}) excluded from enlisted promotion processing"
            error_log.append(msg)
            continue

        # Skip unknown ranks - skip silently
        if row['GRADE'] not in ENLISTED_RANKS:
            msg = f"Unknown or unsupported rank: {row['GRADE']} for {row['FULL_NAME']}"
            error_log.append(msg)
            continue

        # Check projected grades FIRST
        projected_grade = row.get('GRADE_PERM_PROJ')

        # If projected for next grade, exclude completely
        if projected_grade == PROMOTIONAL_MAP.get(cycle):
            continue

        # Check if member should be included in this cycle's roster
        has_projected_grade = projected_grade == cycle
        grade_matches_cycle = row['GRADE'] == cycle or (row['GRADE'] == 'A1C' and cycle == 'SRA')

        # Skip if wrong cycle
        if not (grade_matches_cycle or has_projected_grade):
            continue

        # Check accounting date
        valid_member = accounting_date_check(row['DATE_ARRIVED_STATION'], cycle, year, logger=None)
        if not valid_member:
            continue

        # Check for missing required data
        missing_required = False
        for column in REQUIRED_COLUMNS:
            if column in row and pd.isna(row[column]):
                error_log.append(f"Missing required data at row {index}, column {column}")
                missing_required = True
                break

        if missing_required:
            ineligible_service_members.append(index)
            reason_for_ineligible_map[index] = 'Missing required data'
            logger.warning(f"{to_initials(member_name)} | FAIL | Missing required data")
            continue

        # If already projected for this cycle, mark as ineligible
        if has_projected_grade:
            ineligible_service_members.append(index)
            reason_for_ineligible_map[index] = f'Projected for {cycle}.'
            logger.warning(f"{to_initials(member_name)} | FAIL | Already projected for {cycle}")
            continue

        # Track PASCODEs
        if row['ASSIGNED_PAS'] not in pascodes:
            pascodes.append(row['ASSIGNED_PAS'])
            pascodeUnitMap[row['ASSIGNED_PAS']] = row['ASSIGNED_PAS_CLEARTEXT']

        # Board filter check - logs its own PASS/FAIL line per member
        member_status = board_filter(row['GRADE'], year, row['DOR'], row['UIF_CODE'],
                                     row['UIF_DISPOSITION_DATE'], row['TAFMSD'], row['REENL_ELIG_STATUS'],
                                     row['PAFSC'], row['2AFSC'], row['3AFSC'], row['4AFSC'],
                                     member_name=member_name, roster_type=roster_type, logger=logger)

        if member_status.status == "skip":
            continue

        elif member_status.status == "discrepancy":
            eligible_service_members.append(index)
            discrepancy_service_members.append(index)
            unit_total_map[row['ASSIGNED_PAS']] = unit_total_map.get(row['ASSIGNED_PAS'], 0) + 1
            if member_status.reason:
                reason_for_ineligible_map[index] = member_status.reason

        elif member_status.status == "btz":
            eligible_btz_service_members.append(index)
            unit_total_map[row['ASSIGNED_PAS']] = unit_total_map.get(row['ASSIGNED_PAS'], 0) + 1

        elif member_status.status == "ineligible":
            ineligible_service_members.append(index)
            if member_status.reason:
                reason_for_ineligible_map[index] = member_status.reason

        elif member_status.status == "eligible":
            eligible_service_members.append(index)
            unit_total_map[row['ASSIGNED_PAS']] = unit_total_map.get(row['ASSIGNED_PAS'], 0) + 1

    pascodes = sorted(pascodes)

    # Create PDF DataFrames with parsed datetime objects
    pdf_roster = filtered_roster_df[PDF_COLUMNS].copy()

    eligible_df = pdf_roster.loc[eligible_service_members].copy() if eligible_service_members else pd.DataFrame()
    ineligible_df = pdf_roster.loc[ineligible_service_members].copy() if ineligible_service_members else pd.DataFrame()
    discrepancy_df = pdf_roster.loc[discrepancy_service_members].copy() if discrepancy_service_members else pd.DataFrame()
    btz_df = pdf_roster.loc[eligible_btz_service_members].copy() if eligible_btz_service_members else pd.DataFrame()

    if not ineligible_df.empty:
        ineligible_df['REASON'] = ineligible_df.index.map(reason_for_ineligible_map)
    if not discrepancy_df.empty:
        discrepancy_df['REASON'] = discrepancy_df.index.map(reason_for_ineligible_map)

    # NOW format dates for display - only when preparing final output
    def format_df_for_session(df):
        if df.empty:
            return df
        df_copy = df.copy()

        # Format date columns for display ONLY
        date_columns = ['DOR', 'TAFMSD', 'DATE_ARRIVED_STATION']
        for col in date_columns:
            if col in df_copy.columns:
                df_copy[col] = df_copy[col].apply(format_date_for_display)

        # Format text columns
        if 'ASSIGNED_PAS_CLEARTEXT' in df_copy.columns:
            df_copy['ASSIGNED_PAS_CLEARTEXT'] = df_copy['ASSIGNED_PAS_CLEARTEXT'].str[:max_unit_length]
        if 'FULL_NAME' in df_copy.columns:
            df_copy['FULL_NAME'] = df_copy['FULL_NAME'].str[:max_unit_length]
        return df_copy

    # Apply formatting only for final output
    eligible_df = format_df_for_session(eligible_df)
    ineligible_df = format_df_for_session(ineligible_df)
    discrepancy_df = format_df_for_session(discrepancy_df)
    btz_df = format_df_for_session(btz_df)

    for pascode in unit_total_map:
        if cycle == 'MSG' or cycle == 'SMS':
            small_unit_pascodes.append(pascode)
        elif unit_total_map[pascode] <= small_unit_threshold:
            small_unit_pascodes.append(pascode)

    if not eligible_df.empty:
        small_unit_eligible_service_members = eligible_df[eligible_df['ASSIGNED_PAS'].isin(small_unit_pascodes)].index
        small_unit_df = eligible_df.loc[small_unit_eligible_service_members].copy()
    else:
        small_unit_df = pd.DataFrame()

    # Update session with all results in a single batch call
    session_updates = dict(
        pascodes=pascodes,
        eligible_df=eligible_df,
        ineligible_df=ineligible_df,
        discrepancy_df=discrepancy_df,
        btz_df=btz_df,
        small_unit_df=small_unit_df,
    )
    if pascodeUnitMap:
        session_updates["pascode_unit_map"] = pascodeUnitMap
    if error_log:
        session_updates["error_log"] = error_log

    update_session(session_id, **session_updates)

    # Calculate members on roster
    total_on_roster = (len(eligible_service_members) + len(eligible_btz_service_members) +
                      len(ineligible_service_members))
    total_skipped = len(filtered_roster_df) - total_on_roster

    # Log summary
    logger.info(f"SUMMARY | Total: {len(filtered_roster_df)} | Processed: {total_on_roster} | Skipped: {total_skipped}")
    logger.info(f"RESULTS | Eligible: {len(eligible_service_members)} | BTZ: {len(eligible_btz_service_members)} | Ineligible: {len(ineligible_service_members)} | Discrepancy: {len(discrepancy_service_members)}")
    logger.info(f"UNITS | PASCODEs: {len(pascodes)} | Small units: {len(small_unit_pascodes)}")
    if error_log:
        logger.warning(f"ERRORS | {len(error_log)} errors encountered")
    logger.info(f"STATUS: SUCCESS")

    # Close the session logger
    LoggerSetup.close_session_logger(session_id)

    return


def recalculate_small_units(session_id):
    """
    Recalculate small_unit_df after add/edit/delete operations.
    This ensures senior_rater_needed flag is correctly set based on current data.
    """
    session = get_session(session_id)
    if not session:
        return

    cycle = session.get('cycle', 'SSG')
    eligible_df = session.get('eligible_df', pd.DataFrame())

    # Convert to DataFrame if it's a list
    if isinstance(eligible_df, list):
        eligible_df = pd.DataFrame(eligible_df)

    # If no eligible members, clear small_unit_df
    if eligible_df.empty:
        update_session(session_id, small_unit_df=pd.DataFrame())
        return

    # Count eligible members per pascode
    unit_total_map = {}
    for _, row in eligible_df.iterrows():
        pascode = row.get('ASSIGNED_PAS', '')
        if pascode:
            unit_total_map[pascode] = unit_total_map.get(pascode, 0) + 1

    # Determine which pascodes are small units
    small_unit_pascodes = []
    for pascode in unit_total_map:
        if cycle == 'MSG' or cycle == 'SMS':
            # MSG and SMS cycles: all units are small units
            small_unit_pascodes.append(pascode)
        elif unit_total_map[pascode] <= small_unit_threshold:
            # Other cycles: units with <= threshold eligible members
            small_unit_pascodes.append(pascode)

    # Extract small unit members from eligible_df
    if small_unit_pascodes:
        small_unit_df = eligible_df[eligible_df['ASSIGNED_PAS'].isin(small_unit_pascodes)].copy()
    else:
        small_unit_df = pd.DataFrame()

    # Update session with the recalculated small_unit_df
    update_session(session_id, small_unit_df=small_unit_df)

def rescan_and_update_pascodes(session_id: str):
    """
    Re-scan ALL categories for PASCODEs and update session.
    This ensures PASCODE tracking stays synchronized with roster data
    after add/edit/delete operations.
    """
    session = get_session(session_id)
    if not session:
        return

    all_pascodes = set()
    pascode_unit_map = {}

    for cat_key in ['eligible_df', 'ineligible_df', 'discrepancy_df', 'btz_df', 'small_unit_df']:
        cat_list = session.get(cat_key, [])
        if isinstance(cat_list, list):
            for member in cat_list:
                if not member.get('deleted', False):
                    pas = member.get('ASSIGNED_PAS')
                    if pas and isinstance(pas, str) and pas.strip():
                        all_pascodes.add(pas.strip())
                        if 'ASSIGNED_PAS_CLEARTEXT' in member:
                            pascode_unit_map[pas.strip()] = member['ASSIGNED_PAS_CLEARTEXT']

    if all_pascodes:
        update_session(session_id,
                       pascodes=sorted(list(all_pascodes)),
                       pascode_unit_map=pascode_unit_map)
    else:
        update_session(session_id,
                       pascodes=[],
                       pascode_unit_map={})
