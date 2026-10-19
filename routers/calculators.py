from fastapi import APIRouter
from error_handling import error_response
from fastapi.responses import JSONResponse
from classes import PromotionEligibilityRequest, BTZEligibilityRequest
from date_parsing import parse_date
from eligibility_calculators import calculate_promotion_eligibility, calculate_btz_eligibility

router = APIRouter(tags=["Calculators"])


@router.post("/calculators/promotion-eligibility")
async def check_promotion_eligibility(request: PromotionEligibilityRequest):
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
        tig_date = parse_date(request.tig_date)
        tis_date = parse_date(request.tis_date)

        if not tig_date:
            return JSONResponse(
                content={"error": "Invalid tig_date format. Use DD-MMM-YYYY or ISO format."},
                status_code=400
            )

        if not tis_date:
            return JSONResponse(
                content={"error": "Invalid tis_date format. Use DD-MMM-YYYY or ISO format."},
                status_code=400
            )

        valid_ranks = ['AB', 'AMN', 'A1C', 'SRA', 'SSG', 'TSG', 'MSG', 'SMS']
        if request.current_rank not in valid_ranks:
            return JSONResponse(
                content={"error": f"Invalid rank. Must be one of: {', '.join(valid_ranks)}"},
                status_code=400
            )

        if request.target_year < 2020 or request.target_year > 2030:
            return JSONResponse(
                content={"error": "Invalid year. Must be between 2020 and 2030."},
                status_code=400
            )

        result = calculate_promotion_eligibility(
            tig_date=tig_date,
            tis_date=tis_date,
            current_rank=request.current_rank,
            target_year=request.target_year
        )

        if "error" in result:
            return JSONResponse(content={"error": result["error"]}, status_code=400)

        return JSONResponse(content=result)

    except Exception as e:
        return error_response(500, f"Processing error: {str(e)}", context={"step": "eligibility_calculation"}, exception=e)


@router.post("/calculators/btz-eligibility")
async def check_btz_eligibility(request: BTZEligibilityRequest):
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
        enlistment_date = parse_date(request.enlistment_date)
        a1c_dor = parse_date(request.a1c_dor)

        if not enlistment_date:
            return JSONResponse(
                content={"error": "Invalid enlistment_date format. Use DD-MMM-YYYY or ISO format."},
                status_code=400
            )

        if not a1c_dor:
            return JSONResponse(
                content={"error": "Invalid a1c_dor format. Use DD-MMM-YYYY or ISO format."},
                status_code=400
            )

        if request.target_year < 2020 or request.target_year > 2030:
            return JSONResponse(
                content={"error": "Invalid year. Must be between 2020 and 2030."},
                status_code=400
            )

        result = calculate_btz_eligibility(
            enlistment_date=enlistment_date,
            a1c_dor=a1c_dor,
            target_year=request.target_year
        )

        if "error" in result:
            return JSONResponse(content={"error": result["error"]}, status_code=400)

        return JSONResponse(content=result)

    except Exception as e:
        return error_response(500, f"Processing error: {str(e)}", context={"step": "eligibility_calculation"}, exception=e)
