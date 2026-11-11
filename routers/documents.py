import asyncio
import os
import uuid
from fastapi import APIRouter, Form, Request, UploadFile, File, Query
from error_handling import error_response
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from session_manager import get_session, update_session, create_session
from roster_processor import roster_processor
from initial_mel_generator import generate_roster_pdf
from mpf_list_generator import generate_mpf_list_pdf
from mfr_word_generator import generate_mfr_docx
from classes import PasCodeSubmission
from constants import TEMP_DIR
from file_ingestion import validate_cycle, validate_year, validate_file_type, ingest_file, prepare_session_dataframes
from logging_config import LoggerSetup
from starlette.background import BackgroundTask
from rate_limiter import limiter
from pdf_utils import cleanup_temp_file

router = APIRouter(tags=["Documents"])


# ============================================================================
# MPF ROSTER
# ============================================================================

@router.post("/upload/mpf-roster")
@limiter.limit("10/minute")
async def upload_mpf_roster(request: Request, file: UploadFile = File(...), cycle: str = Form(...), year: int = Form(...)):
    session_id = str(uuid.uuid4())
    cycle = validate_cycle(cycle)
    year = validate_year(year)
    validate_file_type(file.content_type)
    logger = LoggerSetup.get_session_logger(session_id, cycle, year)
    contents = await file.read()
    try:
        df = ingest_file(contents, file.filename, logger=logger)
        processed_df, pdf_df = prepare_session_dataframes(df)
        create_session(processed_df, pdf_df, session_id=session_id)
        update_session(session_id, cycle=cycle, year=year)
        await asyncio.to_thread(roster_processor, df, session_id, cycle, year, "mpf")
        if not get_session(session_id):
            return error_response(500, "Session creation failed", context={"session_id": session_id, "step": "mpf_upload"})
        LoggerSetup.close_session_logger(session_id)
        return JSONResponse(content={"session_id": session_id, "message": "MPF roster processed", "cycle": cycle, "year": year}, status_code=200)
    except Exception as e:
        LoggerSetup.close_session_logger(session_id)
        return error_response(500, "Failed to process MPF roster upload", context={"session_id": session_id, "step": "mpf_upload"}, exception=e)


@router.post("/mpf-roster/submit/pascode-info")
def submit_mpf_pascode_info(payload: PasCodeSubmission):
    try:
        if not get_session(payload.session_id):
            return error_response(404, "Session not found", context={"session_id": payload.session_id})
        senior_rater_data = {}
        for pascode, info in payload.pascode_info.items():
            senior_rater_data[pascode] = {"srid": info.srid or "N/A", "senior_rater_name": info.senior_rater_name or "N/A", "senior_rater_rank": info.senior_rater_rank or "N/A", "senior_rater_title": info.senior_rater_title or "N/A"}
        update_session(payload.session_id, senior_rater_data=senior_rater_data)
        return JSONResponse(content={"message": "Data submitted"}, status_code=200)
    except Exception as e:
        return error_response(500, "Failed to process pascode info", context={"session_id": payload.session_id, "step": "mpf_pascode_submit"}, exception=e)


@router.get("/download/mpf-roster/{session_id}")
async def download_mpf_roster(session_id: str, format: str = Query("list")):
    return await asyncio.to_thread(_download_mpf_roster_sync, session_id, format)

def _download_mpf_roster_sync(session_id: str, format: str):
    try:
        session = get_session(session_id)
        if not session:
            return error_response(404, "Session not found", context={"session_id": session_id})
        if not session.get("senior_rater_data"):
            return error_response(400, "Senior rater info required", context={"session_id": session_id})
        logo_path = None
        custom_logo = session.get("custom_logo", {})
        if custom_logo and custom_logo.get("uploaded"):
            import base64
            from session_manager import _get_redis, _is_encrypted, _decrypt_data
            raw_logo = _get_redis().get(f"{session_id}_logo")
            if raw_logo:
                if _is_encrypted(raw_logo):
                    raw_logo = _decrypt_data(raw_logo)
                logo_data = base64.b64decode(raw_logo)
                logo_path = f"{TEMP_DIR}/{session_id}_logo.png"
                with open(logo_path, "wb") as f:
                    f.write(logo_data)
        output = f"{TEMP_DIR}/mpf_{session_id}.pdf"
        if format == "list":
            pdf_path = generate_mpf_list_pdf(session_id, output, logo_path)
        elif format == "mel":
            pdf_path = generate_roster_pdf(session_id, output, logo_path)
        elif format == "both":
            list_pdf = generate_mpf_list_pdf(session_id, f"{TEMP_DIR}/list_{session_id}.pdf", logo_path)
            mel_pdf = generate_roster_pdf(session_id, f"{TEMP_DIR}/mel_{session_id}.pdf", logo_path)
            if list_pdf and mel_pdf:
                from pdf_templates import merge_pdfs
                pdf_path = merge_pdfs([list_pdf, mel_pdf], output)
                try:
                    os.remove(list_pdf)
                    os.remove(mel_pdf)
                except Exception:
                    pass
            else:
                return error_response(500, "PDF generation failed", context={"session_id": session_id, "format": format})
        else:
            return error_response(400, "Invalid format. Use 'list', 'mel', or 'both'.", context={"session_id": session_id, "format": format})
        if not pdf_path or not os.path.exists(pdf_path):
            return error_response(500, "PDF generation failed", context={"session_id": session_id, "format": format})
        if logo_path and os.path.exists(logo_path):
            try:
                os.remove(logo_path)
            except Exception:
                pass
        filename = f"MPF_Roster_{session.get('cycle', 'SSG')}_{session.get('year', 2025)}_{format}.pdf"
        return FileResponse(pdf_path, media_type="application/pdf", filename=filename,
                            background=BackgroundTask(cleanup_temp_file, pdf_path))
    except Exception as e:
        return error_response(500, "Failed to generate MPF roster PDF", context={"session_id": session_id, "step": "mpf_download"}, exception=e)


# ============================================================================
# MFR GENERATOR
# ============================================================================

class MFRRequest(BaseModel):
    organization: str
    address_line_1: Optional[str] = ""
    address_line_2: Optional[str] = ""
    base_location: Optional[str] = ""
    date: str
    date_format: Optional[str] = "long"
    office_symbol: str
    memo_for: Optional[str] = ""
    subject: str
    paragraphs: List[Any]   # str or {"text": str, "level": int}
    references: Optional[List[str]] = []
    attachments: Optional[List[str]] = []
    endorsements: Optional[List[Any]] = []
    signer_name: str
    signer_rank: str
    signer_branch: str = "USAF"
    signer_title: str


@router.post("/generate/mfr")
async def generate_mfr_endpoint(payload: MFRRequest):
    """
    Generate a Memorandum for Record (MFR) from structured form data.
    Returns a downloadable Word document.
    """
    output_path = f"{TEMP_DIR}/mfr_{uuid.uuid4().hex}.docx"

    try:
        mfr_data = payload.model_dump()
        result_path = generate_mfr_docx(mfr_data, output_path)

        if not result_path or not os.path.exists(result_path):
            return error_response(500, "Word document generation failed", context={"step": "mfr_generation", "subject": payload.subject[:30]})

        safe_subject = "".join(
            c if c.isalnum() or c in (' ', '-', '_') else '_'
            for c in payload.subject
        )[:40].strip()
        filename = f"MFR_{safe_subject}_{payload.date}.docx"

        return FileResponse(
            result_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
            background=BackgroundTask(cleanup_temp_file, result_path),
        )

    except Exception as e:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        return error_response(500, "Failed to generate MFR document", context={"step": "mfr_generation"}, exception=e)
