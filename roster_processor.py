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
from logging_config import LoggerSetup, mask_name
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
    logger.info(f"Processing roster with {len(roster_df)} total members")

    eligible_service_members = []
    eligible_btz_service_members = []
    ineligible_service_members = []
    small_unit_eligible_service_members = []
    discrepancy_service_members = []


    pascodes = []
    small_unit_pascodes = []
    reason_for_ineligible_map = {}
    pascode_unit_map = {}
    unit_total_map = {}

    error_log = []

    all_roster_columns = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

    # Only REQUIRED_COLUMNS are mandatory. OPTIONAL_COLUMNS (e.g. GRADE_PERM_PROJ,
    # UIF_CODE, 2AFSC/3AFSC/4AFSC) may legitimately be absent from a roster — aborting
    # when they're missing produced an empty result while still reporting success.
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in roster_df.columns]
    if missing_columns:
        error_msg = f"Missing required columns: {', '.join(missing_columns)}"
        error_log.append(error_msg)
        logger.error(error_msg)
        logger.info(f"STATUS: FAILED - {error_msg}")
        update_session(session_id, error_log=error_log)
        LoggerSetup.close_session_logger(session_id)
        return

    # Slice to the columns that actually exist, then reintroduce any missing optional
    # columns as empty so downstream row['UIF_CODE'] / row['2AFSC'] access stays safe
    # (an absent optional column is equivalent to one full of blank cells).
    present_columns = [col for col in all_roster_columns if col in roster_df.columns]
    filtered_roster_df = roster_df[present_columns].copy()
    for col in OPTIONAL_COLUMNS:
        if col not in filtered_roster_df.columns:
            filtered_roster_df[col] = None
            logger.info(f"Optional column '{col}' not present in roster; defaulting to empty.")
    logger.info(f"Roster filtered to required columns. Processing {len(filtered_roster_df)} members.")

    # Parse all date columns in the DataFrame ONCE, before processing
    date_columns = ['DOR', 'UIF_DISPOSITION_DATE', 'TAFMSD', 'DATE_ARRIVED_STATION']
    for col in date_columns:
        if col in filtered_roster_df.columns:
            filtered_roster_df[col] = filtered_roster_df[col].apply(
                lambda x: parse_date(x, error_log, None)
            )

    # Processing loop - now working with properly parsed datetime objects
    logger.info("=" * 80)
    logger.info("STARTING MEMBER-BY-MEMBER PROCESSING")
    logger.info("=" * 80)

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

        # Check projected grades FIRST - this determines if they should be on the roster
        # CRITICAL FIX: Use .get() for optional columns to prevent KeyError
        projected_grade = row.get('GRADE_PERM_PROJ')

        # If projected for next grade (e.g., MSG when cycle is TSG), exclude completely - skip silently
        if projected_grade == PROMOTIONAL_MAP.get(cycle):
            continue

        # Check if member should be included in this cycle's roster
        # Include if: (1) current grade matches cycle OR (2) projected for this cycle
        has_projected_grade = projected_grade == cycle
        grade_matches_cycle = row['GRADE'] == cycle or (row['GRADE'] == 'A1C' and cycle == 'SRA')

        # Skip if wrong cycle - skip silently
        if not (grade_matches_cycle or has_projected_grade):
            continue

        # Check accounting date - those who fail should be excluded completely - skip silently
        valid_member = accounting_date_check(row['DATE_ARRIVED_STATION'], cycle, year, logger=None)
        if not valid_member:
            continue

        # ONLY log members that will appear on the roster (passed all initial filters)
        # Use PII masking for CUI compliance
        logger.info(f"\n{'='*60}")
        logger.info(f"ROW {index}: Processing {mask_name(member_name)}")
        logger.info(f"  Current Grade: {grade}")
        logger.info(f"  Promotion Cycle: {cycle} {year}")
        logger.info(f"  Projected Grade: {projected_grade if projected_grade else 'None'}")
        logger.info(f"  ✓ Grade matches cycle or projected for cycle")
        logger.info(f"  ✓ Accounting date check passed")

        # Check for missing required data
        missing_required = False
        for column in REQUIRED_COLUMNS:
            if column in row and pd.isna(row[column]):
                error_log.append(f"Missing required data at row {index}, column {column}")
                logger.warning(f"  ❌ Missing required column: {column}")
                missing_required = True
                break

        if missing_required:
            ineligible_service_members.append(index)
            reason_for_ineligible_map[index] = 'Missing required data'
            logger.info(f"  Decision: Marked as ineligible (Missing Required Data)")
            continue

        logger.info(f"  ✓ All required data present")

        # If projected INTO this cycle's grade but not yet there, mark ineligible —
        # EXCEPT A1Cs in the SrA cycle. Those are date-evaluated for their projected
        # SrA pin by board_filter (eligible / ineligible / BTZ / skip), regardless of
        # whether GRADE_PERM_PROJ is populated, so they must NOT be short-circuited here.
        a1c_in_sra_cycle = row['GRADE'] == 'A1C' and cycle == 'SRA'
        if has_projected_grade and not a1c_in_sra_cycle:
            ineligible_service_members.append(index)
            reason_for_ineligible_map[index] = f'Projected for {cycle}.'
            logger.info(f"  ❌ INELIGIBLE: Already projected for {cycle}")
            logger.info(f"  Decision: Marked as ineligible (Already Projected)")
            continue

        # Track PASCODEs
        if row['ASSIGNED_PAS'] not in pascodes:
            pascodes.append(row['ASSIGNED_PAS'])
            pascode_unit_map[row['ASSIGNED_PAS']] = row['ASSIGNED_PAS_CLEARTEXT']

        logger.info(f"  ✓ Ready for board filter - calling board_filter() for detailed eligibility check")

        # Board filter check - pass member info and logger for logging
        member_status = board_filter(row['GRADE'], year, row['DOR'], row['UIF_CODE'],
                                     row['UIF_DISPOSITION_DATE'], row['TAFMSD'], row['REENL_ELIG_STATUS'],
                                     row['PAFSC'], row['2AFSC'], row['3AFSC'], row['4AFSC'],
                                     member_name=member_name, roster_type=roster_type, logger=logger)

        if member_status.status == "skip":
            logger.info(f"  Decision: Not eligible (skipped by board_filter)")
            continue

        elif member_status.status == "discrepancy":
            eligible_service_members.append(index)
            discrepancy_service_members.append(index)
            unit_total_map[row['ASSIGNED_PAS']] = unit_total_map.get(row['ASSIGNED_PAS'], 0) + 1
            if member_status.reason:
                reason_for_ineligible_map[index] = member_status.reason
            logger.info(f"  ✅ ELIGIBLE (WITH DISCREPANCY): {member_status.reason or 'No reason provided'}")
            logger.info(f"  Decision: Added to eligible roster with discrepancy flag")

        elif member_status.status == "btz":
            eligible_btz_service_members.append(index)
            unit_total_map[row['ASSIGNED_PAS']] = unit_total_map.get(row['ASSIGNED_PAS'], 0) + 1
            logger.info(f"  ✅ ELIGIBLE (BTZ): Below-the-Zone eligibility")
            logger.info(f"  Decision: Added to BTZ eligible roster")

        elif member_status.status == "ineligible":
            ineligible_service_members.append(index)
            if member_status.reason:
                reason_for_ineligible_map[index] = member_status.reason
                logger.info(f"  ❌ INELIGIBLE: {member_status.reason}")
            else:
                logger.info(f"  ❌ INELIGIBLE: No specific reason provided")
            logger.info(f"  Decision: Added to ineligible roster")

        elif member_status.status == "eligible":
            eligible_service_members.append(index)
            unit_total_map[row['ASSIGNED_PAS']] = unit_total_map.get(row['ASSIGNED_PAS'], 0) + 1
            logger.info(f"  ✅ ELIGIBLE: Meets all requirements")
            logger.info(f"  Decision: Added to eligible roster")

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
    if pascode_unit_map:
        session_updates["pascode_unit_map"] = pascode_unit_map
    if error_log:
        session_updates["error_log"] = error_log

    update_session(session_id, **session_updates)

    # Calculate members on roster
    total_on_roster = (len(eligible_service_members) + len(eligible_btz_service_members) +
                      len(ineligible_service_members))
    total_skipped = len(filtered_roster_df) - total_on_roster

    # Log summary statistics
    logger.info("")
    logger.info("=" * 80)
    logger.info("PROCESSING SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total Members in Upload: {len(filtered_roster_df)}")
    logger.info(f"Members on Roster (logged above): {total_on_roster}")
    logger.info(f"Members Skipped (not matching cycle/accounting date): {total_skipped}")
    logger.info("")
    logger.info("ROSTER BREAKDOWN:")
    logger.info(f"  • Eligible Members: {len(eligible_service_members)}")
    logger.info(f"  • BTZ Eligible Members: {len(eligible_btz_service_members)}")
    logger.info(f"  • Ineligible Members: {len(ineligible_service_members)}")
    logger.info(f"  • Discrepancy Members: {len(discrepancy_service_members)}")
    logger.info("")
    logger.info(f"PASCODEs (Units) Found: {len(pascodes)}")
    logger.info(f"Small Units Requiring Senior Rater: {len(small_unit_pascodes)}")
    if error_log:
        logger.warning(f"Errors Encountered: {len(error_log)}")

    logger.info(f"STATUS: SUCCESS")

    # Close the session logger
    LoggerSetup.close_session_logger(session_id)

    return


def recheck_member_eligibility(session_id: str, member_data: dict, source_category: str, source_index: int):
    """
    Re-run board_filter on a single member after edit/add.
    Moves the member to the correct category based on the result.
    Returns the new category name.
    """
    session = get_session(session_id)
    if not session:
        return source_category

    cycle = session.get('cycle', 'SSG')
    year = session.get('year', 2025)

    # Run board_filter on this member. Dates may arrive as strings (manual add/edit
    # from the UI) or as datetimes (already-parsed roster rows) — parse_date handles
    # both and returns tz-naive datetimes, which board_filter's comparisons require.
    result = board_filter(
        grade=member_data.get('GRADE', ''),
        year=year,
        date_of_rank=parse_date(member_data.get('DOR')),
        uif_code=member_data.get('UIF_CODE'),
        uif_disposition_date=parse_date(member_data.get('UIF_DISPOSITION_DATE')),
        tafmsd=parse_date(member_data.get('TAFMSD')),
        re_status=member_data.get('REENL_ELIG_STATUS'),
        pafsc=member_data.get('PAFSC'),
        two_afsc=member_data.get('2AFSC'),
        three_afsc=member_data.get('3AFSC'),
        four_afsc=member_data.get('4AFSC'),
        member_name=member_data.get('FULL_NAME', 'Unknown'),
        roster_type='mel',
    )

    # Map board_filter result to category
    status_to_category = {
        'eligible': 'eligible',
        'ineligible': 'ineligible',
        'btz': 'btz',
        'discrepancy': 'discrepancy',
        'skip': 'ineligible',
    }
    new_category = status_to_category.get(result.status, 'ineligible')

    # If the category didn't change, nothing to do
    if new_category == source_category:
        # Still update reason if applicable
        if result.reason and new_category in ('ineligible', 'discrepancy'):
            member_data['REASON'] = result.reason
            cat_list = session.get(f'{source_category}_df', [])
            if isinstance(cat_list, list) and source_index < len(cat_list):
                cat_list[source_index]['REASON'] = result.reason
                update_session(session_id, **{f'{source_category}_df': pd.DataFrame(cat_list)})
        return new_category

    # Category changed — remove from old, add to new
    old_key = f'{source_category}_df'
    new_key = f'{new_category}_df'

    old_list = session.get(old_key, [])
    new_list = session.get(new_key, [])

    if isinstance(old_list, list) and source_index < len(old_list):
        # Remove from old category
        moved_member = old_list.pop(source_index)
    else:
        moved_member = member_data.copy()

    # Add reason if ineligible/discrepancy
    if result.reason and new_category in ('ineligible', 'discrepancy'):
        moved_member['REASON'] = result.reason
    elif 'REASON' in moved_member and new_category in ('eligible', 'btz'):
        del moved_member['REASON']

    if not isinstance(new_list, list):
        new_list = []
    new_list.append(moved_member)

    updates = {
        old_key: pd.DataFrame(old_list) if old_list else pd.DataFrame(),
        new_key: pd.DataFrame(new_list),
        'edited': True,
    }
    update_session(session_id, **updates)

    return new_category


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

    # Count eligible members per pascode (vectorized)
    unit_total_map = eligible_df.groupby('ASSIGNED_PAS').size().to_dict()

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
