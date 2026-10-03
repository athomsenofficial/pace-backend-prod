from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
from date_parsing import parse_date
from constants import (
    SCODS, TIG, TIG_MONTHS_REQUIRED, TAFMSD, MDOS,
    MAIN_HIGHER_TENURE, EXCEPTION_HIGHER_TENURE, PAFSC_MAP,
    RE_CODES, hyt_start_date, hyt_end_date
)
from typing import Union, Tuple, Optional
from classes import EligibilityResult
from eligibility_calculators import compute_hyt_date
from logging import Logger
from logging_config import to_initials

def pafsc_check(grade: str, pafsc: Optional[str], two_afsc: Optional[str],
                 three_afsc: Optional[str], four_afsc: Optional[str]) -> Optional[bool]:
    """
    Check if any AFSC meets the required skill level for the grade.

    Returns:
        True if meets requirement, False if doesn't, None if AFSC is 8/9 prefixed
    """
    # Handle NaN/None values - convert to None
    if pd.isna(pafsc):
        pafsc = None
    if pd.isna(two_afsc):
        two_afsc = None
    if pd.isna(three_afsc):
        three_afsc = None
    if pd.isna(four_afsc):
        four_afsc = None

    # Check for special AFSCs (8/9 prefix)
    if pafsc and isinstance(pafsc, str) and len(pafsc) > 0 and pafsc[0] in ('8', '9'):
        return None

    required_level = PAFSC_MAP.get(grade)
    if not required_level:
        return False

    afscs = [pafsc, two_afsc, three_afsc, four_afsc]

    for afsc in afscs:
        # Skip None or NaN values
        if afsc is None or pd.isna(afsc):
            continue
        if isinstance(afsc, str) and len(afsc) >= 5:
            skill_level_index = 4 if afsc[0].isalpha() or afsc[0] == '-' else 3

            try:
                if afsc[skill_level_index] >= required_level:
                    return True
            except IndexError:
                continue

    return False

def btz_elgibility_check(date_of_rank, year):
    date_of_rank = parse_date(date_of_rank)
    if not date_of_rank:
        return False
    cutoff_date = datetime.strptime(f"01-Feb-{year}", "%d-%b-%Y")
    btz_date_of_rank = date_of_rank + relativedelta(months=22)
    scod_date = datetime.strptime(f"{SCODS.get('SRA')}-{year}", "%d-%b-%Y")
    if btz_date_of_rank <= cutoff_date:
        return True
    if cutoff_date < btz_date_of_rank <= scod_date:
        return True
    return False

def check_a1c_eligbility(date_of_rank, year):
    date_of_rank = parse_date(date_of_rank)
    if not date_of_rank:
        return False
    cutoff_date = datetime.strptime(f"01-Feb-{year}", "%d-%b-%Y")
    scod_date = datetime.strptime(f"{SCODS.get('SRA')}-{year}", "%d-%b-%Y")
    standard_a1c_date_of_rank = date_of_rank + relativedelta(months=28)
    if standard_a1c_date_of_rank <= cutoff_date:
        return True
    if cutoff_date < standard_a1c_date_of_rank <= scod_date:
        return False
    return None

def three_year_tafmsd_check(scod_as_datetime, tafmsd):
    tafmsd = parse_date(tafmsd)
    if tafmsd is None:
        return False
    adjusted_tafmsd = tafmsd + relativedelta(months=36)
    # Return True if they WILL have more than 36 months TIS by SCOD (ineligible)
    return adjusted_tafmsd <= scod_as_datetime

def board_filter(
    grade: str,
    year: int,
    date_of_rank: Union[str, datetime, None],
    uif_code: Union[int, float, str, None],
    uif_disposition_date: Union[str, datetime, None],
    tafmsd: Union[str, datetime, None],
    re_status: Optional[str],
    pafsc: Optional[str],
    two_afsc: Optional[str],
    three_afsc: Optional[str],
    four_afsc: Optional[str],
    member_name: str = "Unknown",
    roster_type: str = "mel",
    logger: Optional[Logger] = None
) -> Union[bool, Tuple[bool, str], Tuple[str, str], None]:
    """
    Filter members for board eligibility.
    Logs a single PASS/FAIL line per member with initials only.
    """
    initials = to_initials(member_name)

    def _log_result(status, reason=None):
        if logger:
            msg = f"{initials} | {status}"
            if reason:
                msg += f" | {reason}"
            if status == "FAIL":
                logger.warning(msg)
            else:
                logger.info(msg)

    try:
        # Step 1: Parse dates
        date_of_rank = parse_date(date_of_rank)
        uif_disposition_date = parse_date(uif_disposition_date)
        tafmsd = parse_date(tafmsd)

        if date_of_rank is None or tafmsd is None:
            reason = 'Required date missing or unreadable'
            _log_result("FAIL", reason)
            return EligibilityResult("ineligible", reason)

        # Step 2: Calculate key dates
        scod_month_day = SCODS.get(grade)
        month_name = scod_month_day.split('-')[1]

        if month_name in ['JAN', 'FEB', 'MAR']:
            scod_year = year + 1
        else:
            scod_year = year

        scod = f'{scod_month_day}-{scod_year}'
        scod_as_datetime = datetime.strptime(scod, "%d-%b-%Y")

        tig_selection_month = f'{TIG.get(grade)}-{year + 1}'
        formatted_tig_selection_month = datetime.strptime(tig_selection_month, "%d-%b-%Y")
        tig_eligibility_month = formatted_tig_selection_month - relativedelta(months=TIG_MONTHS_REQUIRED.get(grade))

        tafmsd_years = TAFMSD.get(grade)
        if tafmsd_years < 1:
            months_total = int(tafmsd_years * 12)
            tafmsd_required_date = formatted_tig_selection_month - relativedelta(months=months_total)
        else:
            months_component = int((tafmsd_years % 1) * 12)
            years_component = int(tafmsd_years)
            tafmsd_required_date = formatted_tig_selection_month - relativedelta(years=years_component,
                                                                                 months=months_component)

        hyt_date = compute_hyt_date(tafmsd, grade)

        mdos_month = f'{MDOS.get(grade)}-{year + 1}'
        mdos = datetime.strptime(mdos_month, "%d-%b-%Y")

        btz_check = None

        # Step 3: A1C specific checks
        if grade == 'A1C':
            if three_year_tafmsd_check(scod_as_datetime, tafmsd):
                reason = 'SRA 2 Feb - 31 Mar or 3yr TIS'
                _log_result("FAIL", reason)
                return EligibilityResult("ineligible", reason)

            eligibility_status = check_a1c_eligbility(date_of_rank, year)
            if eligibility_status is None:
                btz_check = btz_elgibility_check(date_of_rank, year)
                if not btz_check:
                    _log_result("SKIP")
                    return EligibilityResult("skip")
            elif eligibility_status is False:
                reason = 'Failed A1C Check.'
                _log_result("FAIL", reason)
                return EligibilityResult("ineligible", reason)

        # Step 4: 3-year TIS check for AMN and AB only
        if grade in ('AMN', 'AB'):
            if three_year_tafmsd_check(scod_as_datetime, tafmsd):
                reason = 'SRA 2 Feb - 31 Mar or 3yr TIS'
                _log_result("FAIL", reason)
                return EligibilityResult("ineligible", reason)

        # Step 4.5: SRA Feb-March promotion window exclusion
        if grade == 'SRA':
            promotion_year = year + 1
            dor_year = date_of_rank.year
            dor_month = date_of_rank.month
            dor_day = date_of_rank.day

            if dor_year == promotion_year:
                if (dor_month == 2 and dor_day >= 2) or (dor_month == 3):
                    reason = 'SRA 2 Feb - 31 Mar or 3yr TIS'
                    _log_result("FAIL", reason)
                    return EligibilityResult("ineligible", reason)

        # Step 5: TIG check
        if date_of_rank is None or date_of_rank > tig_eligibility_month:
            reason = f'TIG: < {TIG_MONTHS_REQUIRED.get(grade)} months'
            _log_result("FAIL", reason)
            return EligibilityResult("ineligible", reason)

        # Step 6: TIS check
        if tafmsd > tafmsd_required_date:
            reason = f'TIS < {TAFMSD.get(grade)} years'
            _log_result("FAIL", reason)
            return EligibilityResult("ineligible", reason)

        # Step 7: HYT check
        if hyt_date < mdos:
            reason = 'Higher tenure.'
            _log_result("FAIL", reason)
            return EligibilityResult("ineligible", reason)

        # Step 8: UIF check
        if pd.isna(uif_code) or uif_code is None or uif_code == '':
            uif_code = 0
        else:
            try:
                uif_code = int(uif_code)
            except (TypeError, ValueError):
                uif_code = 0

        if uif_code > 1 and uif_disposition_date and uif_disposition_date < scod_as_datetime:
            reason = f'UIF code: {uif_code}'
            _log_result("PASS", f"DISCREPANCY: {reason}")
            return EligibilityResult("discrepancy", reason) if roster_type == 'mel' else EligibilityResult("eligible")

        # Step 9: RE status check
        if pd.isna(re_status) or re_status is None:
            re_status = None

        if re_status and re_status in RE_CODES.keys():
            reason = f'{re_status}: {RE_CODES.get(re_status)}'
            _log_result("PASS", f"DISCREPANCY: {reason}")
            return EligibilityResult("discrepancy", reason) if roster_type == 'mel' else EligibilityResult("eligible")

        # Step 10: PAFSC skill level check
        if grade not in ('SMS', 'MSG') and roster_type == 'mel':
            pafsc_result = pafsc_check(grade, pafsc, two_afsc, three_afsc, four_afsc)
            if pafsc_result is False:
                reason = 'Insufficient PAFSC skill level.'
                _log_result("PASS", f"DISCREPANCY: {reason}")
                return EligibilityResult("discrepancy", reason) if roster_type == 'mel' else EligibilityResult("eligible")

        # Final determination
        if btz_check is not None and btz_check is True:
            _log_result("PASS", "BTZ")
            return EligibilityResult("btz")

        _log_result("PASS")
        return EligibilityResult("eligible")

    except Exception as e:
        error_msg = f'Processing error: {str(e)}'
        _log_result("FAIL", error_msg)
        return EligibilityResult("ineligible", error_msg)
