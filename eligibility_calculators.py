from datetime import datetime
from dateutil.relativedelta import relativedelta
from constants import SCODS, TIG, TIG_MONTHS_REQUIRED, TAFMSD, MDOS, MAIN_HIGHER_TENURE, EXCEPTION_HIGHER_TENURE, hyt_start_date, hyt_end_date

def compute_hyt_date(tafmsd, grade):
    """
    Single authoritative HYT date calculation.
    Used by both board_filter and the eligibility calculators.

    Returns the effective HYT date, accounting for exception windows.
    """
    # Base HYT date
    hyt_years = MAIN_HIGHER_TENURE.get(grade)
    if hyt_years < 1:
        hyt_months_total = int(hyt_years * 12)
        hyt_date = tafmsd + relativedelta(months=hyt_months_total)
    else:
        hyt_months_component = int((hyt_years % 1) * 12)
        hyt_years_component = int(hyt_years)
        hyt_date = tafmsd + relativedelta(years=hyt_years_component, months=hyt_months_component)

    # Check exception window
    if hyt_start_date < hyt_date < hyt_end_date:
        exception_hyt_years = EXCEPTION_HIGHER_TENURE.get(grade, MAIN_HIGHER_TENURE.get(grade))
        if exception_hyt_years < 1:
            hyt_months_total = int(exception_hyt_years * 12)
            hyt_date = tafmsd + relativedelta(months=hyt_months_total)
        else:
            hyt_months_component = int((exception_hyt_years % 1) * 12)
            hyt_years_component = int(exception_hyt_years)
            hyt_date = tafmsd + relativedelta(years=hyt_years_component, months=hyt_months_component)

    return hyt_date


def calculate_promotion_eligibility(
    tig_date: datetime,
    tis_date: datetime,
    current_rank: str,
    target_year: int
) -> dict:
    """
    Calculate which promotion cycles member is eligible for.
    """
    try:
        if current_rank not in SCODS:
            return {
                "error": f"Invalid rank: {current_rank}. Must be one of: AB, AMN, A1C, SRA, SSG, TSG, MSG, SMS"
            }

        tig_months_required = TIG_MONTHS_REQUIRED.get(current_rank)
        tis_years_required = TAFMSD.get(current_rank)

        scod_month_day = SCODS.get(current_rank)
        month_name = scod_month_day.split('-')[1]

        if month_name in ['JAN', 'FEB', 'MAR']:
            scod_year = target_year + 1
        else:
            scod_year = target_year

        scod = f'{scod_month_day}-{scod_year}'
        scod_as_datetime = datetime.strptime(scod, "%d-%b-%Y")

        tig_selection_month = f'{TIG.get(current_rank)}-{target_year + 1}'
        formatted_tig_selection_month = datetime.strptime(tig_selection_month, "%d-%b-%Y")
        tig_eligibility_month = formatted_tig_selection_month - relativedelta(months=tig_months_required)

        if tis_years_required < 1:
            months_total = int(tis_years_required * 12)
            tafmsd_required_date = formatted_tig_selection_month - relativedelta(months=months_total)
        else:
            months_component = int((tis_years_required % 1) * 12)
            years_component = int(tis_years_required)
            tafmsd_required_date = formatted_tig_selection_month - relativedelta(years=years_component, months=months_component)

        hyt_years = MAIN_HIGHER_TENURE.get(current_rank)
        hyt_date = compute_hyt_date(tis_date, current_rank)

        mdos_month = f'{MDOS.get(current_rank)}-{target_year + 1}'
        mdos = datetime.strptime(mdos_month, "%d-%b-%Y")

        tig_met = tig_date <= tig_eligibility_month
        tis_met = tis_date <= tafmsd_required_date
        hyt_met = hyt_date >= mdos

        tig_months_actual = (formatted_tig_selection_month.year - tig_date.year) * 12 + (formatted_tig_selection_month.month - tig_date.month)
        tis_years_actual = (formatted_tig_selection_month.year - tis_date.year) + (formatted_tig_selection_month.month - tis_date.month) / 12.0
        hyt_years_current = (scod_as_datetime.year - tis_date.year) + (scod_as_datetime.month - tis_date.month) / 12.0

        eligible = tig_met and tis_met and hyt_met

        result = {
            "eligible": eligible,
            "cycle": current_rank,
            "year": target_year,
            "scod": scod_as_datetime.strftime("%d-%b-%Y"),
            "requirements": {
                "tig": {
                    "met": tig_met,
                    "required": f"{tig_months_required} months",
                    "actual": f"{tig_months_actual} months",
                    "required_date": tig_eligibility_month.strftime("%d-%b-%Y"),
                    "member_date": tig_date.strftime("%d-%b-%Y")
                },
                "tis": {
                    "met": tis_met,
                    "required": f"{tis_years_required} years",
                    "actual": f"{tis_years_actual:.2f} years",
                    "required_date": tafmsd_required_date.strftime("%d-%b-%Y"),
                    "member_date": tis_date.strftime("%d-%b-%Y")
                },
                "hyt": {
                    "met": hyt_met,
                    "limit": f"{hyt_years} years",
                    "current": f"{hyt_years_current:.2f} years",
                    "hyt_date": hyt_date.strftime("%d-%b-%Y"),
                    "mdos_date": mdos.strftime("%d-%b-%Y")
                }
            }
        }

        if eligible:
            result["eligible_cycles"] = [{"cycle": current_rank, "year": target_year, "scod": scod_as_datetime.strftime("%d-%b-%Y")}]
            result["first_eligible"] = {"cycle": current_rank, "year": target_year}
        else:
            result["eligible_cycles"] = []
            result["first_eligible"] = None
            unmet_requirements = []
            if not tig_met:
                unmet_requirements.append(f"TIG (need {tig_months_required - tig_months_actual} more months)")
            if not tis_met:
                unmet_requirements.append(f"TIS (need {tis_years_required - tis_years_actual:.2f} more years)")
            if not hyt_met:
                unmet_requirements.append("HYT (exceeded tenure limit)")
            result["unmet_requirements"] = unmet_requirements

        return result

    except Exception as e:
        return {"error": "An error occurred during eligibility calculation"}


def calculate_btz_eligibility(
    enlistment_date: datetime,
    a1c_dor: datetime,
    target_year: int
) -> dict:
    """
    Calculate BTZ (Below-the-Zone) eligibility for A1C to SRA.

    BTZ boards meet quarterly. Members are considered when they reach 20 months TIG.
    The board quarter is determined by when the member's 20th month falls.
    If selected, promotion occurs at the 22-month mark.

    Quarterly board schedule (typically):
    - Q1: January/February board (considers members reaching 20 mo TIG in Jan-Mar)
    - Q2: April/May board (considers members reaching 20 mo TIG in Apr-Jun)
    - Q3: July/August board (considers members reaching 20 mo TIG in Jul-Sep)
    - Q4: October/November board (considers members reaching 20 mo TIG in Oct-Dec)
    """
    try:
        # BTZ board consideration is at 20 months TIG
        btz_board_months = 20
        # Promotion occurs at 22 months TIG if selected
        btz_promotion_months = 22

        # Calculate when member hits 20 months TIG (board consideration date)
        board_consideration_date = a1c_dor + relativedelta(months=btz_board_months)

        # Calculate when member would promote if selected (22 months TIG)
        promotion_date = a1c_dor + relativedelta(months=btz_promotion_months)

        # Determine board quarter based on 20-month date
        board_month = board_consideration_date.month
        board_year = board_consideration_date.year

        if board_month in [1, 2, 3]:
            board_quarter = "Q1"
        elif board_month in [4, 5, 6]:
            board_quarter = "Q2"
        elif board_month in [7, 8, 9]:
            board_quarter = "Q3"
        else:
            board_quarter = "Q4"

        # Calculate 36-month TIS date (3-year exclusion check)
        three_year_tis_date = enlistment_date + relativedelta(months=36)

        # Member is NOT eligible for BTZ if they will have 36+ months TIS by their promotion date
        exceeds_three_year_tis = three_year_tis_date <= promotion_date

        # Calculate actual TIG months at board consideration
        tig_at_board = (board_consideration_date.year - a1c_dor.year) * 12 + (board_consideration_date.month - a1c_dor.month)

        # Calculate TIS at promotion date
        tis_at_promotion_months = (promotion_date.year - enlistment_date.year) * 12 + (promotion_date.month - enlistment_date.month)

        # Member is eligible if:
        # 1. They reach 20 months TIG within the target year
        # 2. They do not exceed 36 months TIS by their promotion date
        board_in_target_year = board_consideration_date.year == target_year

        eligible = board_in_target_year and not exceeds_three_year_tis

        result = {
            "eligible": eligible,
            "board_quarter": f"{board_quarter} {board_year}",
            "board_consideration_date": board_consideration_date.strftime("%d-%b-%Y"),
            "promotion_date": promotion_date.strftime("%d-%b-%Y") if eligible else None,
            "requirements": {
                "tig_20_months": {
                    "met": board_in_target_year,
                    "board_quarter": f"{board_quarter} {board_year}",
                    "consideration_date": board_consideration_date.strftime("%d-%b-%Y"),
                    "promotion_date": promotion_date.strftime("%d-%b-%Y"),
                    "tig_at_board": f"{tig_at_board} months",
                    "a1c_dor": a1c_dor.strftime("%d-%b-%Y")
                },
                "three_year_tis_exclusion": {
                    "met": not exceeds_three_year_tis,
                    "exceeds": exceeds_three_year_tis,
                    "tis_at_promotion": f"{tis_at_promotion_months} months",
                    "three_year_date": three_year_tis_date.strftime("%d-%b-%Y"),
                    "enlistment_date": enlistment_date.strftime("%d-%b-%Y")
                }
            }
        }

        if not eligible:
            reasons = []
            if not board_in_target_year:
                reasons.append(f"20-month board consideration falls in {board_year}, not {target_year}")
            if exceeds_three_year_tis:
                reasons.append(f"Will have {tis_at_promotion_months} months TIS by promotion date (exceeds 36-month limit)")
            result["ineligible_reasons"] = reasons

        return result

    except Exception as e:
        return {"error": "An error occurred during BTZ eligibility calculation"}
