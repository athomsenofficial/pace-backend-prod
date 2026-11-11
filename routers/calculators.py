from fastapi import APIRouter, Request
from error_handling import error_response
from fastapi.responses import JSONResponse
from classes import PromotionEligibilityRequest, BTZEligibilityRequest
from date_parsing import parse_date
from eligibility_calculators import calculate_promotion_eligibility, calculate_btz_eligibility
from rate_limiter import limiter

router = APIRouter(tags=["Calculators"])


@router.post("/calculators/promotion-eligibility")
@limiter.limit("30/minute")
async def check_promotion_eligibility(request: Request, payload: PromotionEligibilityRequest):
    """
    Calculate promotion eligibility for a member.

    Expects:
    {
        "tig_date": "01-Jan-2023",
        "tis_date": "01-Jan-2018",
        "current_rank": "SSG",
        "target_year": 2026
    }
    """
    try:
        tig_date = parse_date(payload.tig_date)
        tis_date = parse_date(payload.tis_date)

        if not tig_date:
            return error_response(400, "Invalid tig_date format. Use DD-MMM-YYYY or ISO format.", context={"step": "eligibility_calculation"})

        if not tis_date:
            return error_response(400, "Invalid tis_date format. Use DD-MMM-YYYY or ISO format.", context={"step": "eligibility_calculation"})

        valid_ranks = ['AB', 'AMN', 'A1C', 'SRA', 'SSG', 'TSG', 'MSG', 'SMS']
        if payload.current_rank not in valid_ranks:
            return error_response(400, f"Invalid rank. Must be one of: {', '.join(valid_ranks)}", context={"step": "eligibility_calculation"})

        if payload.target_year < 2020 or payload.target_year > 2030:
            return error_response(400, "Invalid year. Must be between 2020 and 2030.", context={"step": "eligibility_calculation"})

        result = calculate_promotion_eligibility(
            tig_date=tig_date,
            tis_date=tis_date,
            current_rank=payload.current_rank,
            target_year=payload.target_year
        )

        if "error" in result:
            return JSONResponse(content={"error": result["error"]}, status_code=400)

        return JSONResponse(content=result)

    except Exception as e:
        return error_response(500, "An internal processing error occurred", context={"step": "eligibility_calculation"}, exception=e)


@router.post("/calculators/btz-eligibility")
@limiter.limit("30/minute")
async def check_btz_eligibility(request: Request, payload: BTZEligibilityRequest):
    """
    Calculate BTZ (Below-the-Zone) eligibility for A1C to SRA promotion.

    Expects:
    {
        "enlistment_date": "01-Jan-2022",
        "a1c_dor": "01-Jul-2022",
        "target_year": 2024
    }
    """
    try:
        enlistment_date = parse_date(payload.enlistment_date)
        a1c_dor = parse_date(payload.a1c_dor)

        if not enlistment_date:
            return error_response(400, "Invalid enlistment_date format. Use DD-MMM-YYYY or ISO format.", context={"step": "btz_calculation"})

        if not a1c_dor:
            return error_response(400, "Invalid a1c_dor format. Use DD-MMM-YYYY or ISO format.", context={"step": "btz_calculation"})

        if payload.target_year < 2020 or payload.target_year > 2030:
            return error_response(400, "Invalid year. Must be between 2020 and 2030.", context={"step": "btz_calculation"})

        result = calculate_btz_eligibility(
            enlistment_date=enlistment_date,
            a1c_dor=a1c_dor,
            target_year=payload.target_year
        )

        if "error" in result:
            return JSONResponse(content={"error": result["error"]}, status_code=400)

        return JSONResponse(content=result)

    except Exception as e:
        return error_response(500, "An internal processing error occurred", context={"step": "eligibility_calculation"}, exception=e)
