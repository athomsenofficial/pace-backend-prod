import os
import uuid
from fastapi import APIRouter, Form, UploadFile, File, Query
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
from file_ingestion import validate_cycle, validate_year, validate_file_type, ingest_file
from logging_config import LoggerSetup

router = APIRouter(tags=["Documents"])


# ============================================================================
# MPF ROSTER
# ============================================================================

@router.post("/upload/mpf-roster")
async def upload_mpf_roster(file: UploadFile = File(...), cycle: str = Form(...), year: int = Form(...)):
    session_id = str(uuid.uuid4())
    cycle = validate_cycle(cycle)
    year = validate_year(year)
    validate_file_type(file.content_type)
    logger = LoggerSetup.get_session_logger(session_id, cycle, year)
    contents = await file.read()
    try:
        df = ingest_file(contents, file.filename, logger=logger)
        create_session(session_id, cycle, year)
        roster_processor(df, session_id, cycle, year, roster_type="mpf")
        if not get_session(session_id):
            return error_response(500, "Session creation failed", context={"session_id": session_id, "step": "mpf_upload"})
        LoggerSetup.close_session_logger(session_id)
        return JSONResponse(content={"session_id": session_id, "message": "MPF roster processed", "cycle": cycle, "year": year}, status_code=200)
    except Exception as e:
        LoggerSetup.close_session_logger(session_id)
        return error_response(500, str(e), context={"session_id": session_id, "step": "mpf_upload"}, exception=e)


@router.post("/mpf-roster/submit/pascode-info")
async def submit_mpf_pascode_info(payload: PasCodeSubmission):
    try:
        if not get_session(payload.session_id):
            return error_response(404, "Session not found", context={"session_id": payload.session_id if hasattr(payload, "session_id") else session_id})
        senior_rater_data = {}
        for p in payload.pascodeInfo:
            senior_rater_data[p.pascode] = {"srid": p.srid or "N/A", "senior_rater_name": p.senior_rater_name or "N/A", "senior_rater_rank": p.senior_rater_rank or "N/A", "senior_rater_title": p.senior_rater_title or "N/A", "srid mpf": p.srid_mpf or "N/A"}
        update_session(payload.session_id, senior_rater_data=senior_rater_data)
        return JSONResponse(content={"message": "Data submitted"}, status_code=200)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.get("/download/mpf-roster/{session_id}")
async def download_mpf_roster(session_id: str, format: str = Query("list")):
    try:
        session = get_session(session_id)
        if not session:
            return error_response(404, "Session not found", context={"session_id": payload.session_id if hasattr(payload, "session_id") else session_id})
        if not session.get("senior_rater_data"):
            return JSONResponse(content={"error": "Senior rater info required"}, status_code=400)
        logo_path = None
        if session.get("logo"):
            logo_path = f"/tmp/{session_id}_logo.png"
            with open(logo_path, "wb") as f:
                f.write(session.get("logo"))
        output = f"/tmp/mpf_{session_id}.pdf"
        if format == "list":
            pdf_path = generate_mpf_list_pdf(session_id, output, logo_path)
        elif format == "mel":
            pdf_path = generate_roster_pdf(session_id, output, logo_path)
        elif format == "both":
            list_pdf = generate_mpf_list_pdf(session_id, f"/tmp/list_{session_id}.pdf", logo_path)
            mel_pdf = generate_roster_pdf(session_id, f"/tmp/mel_{session_id}.pdf", logo_path)
            if list_pdf and mel_pdf:
                from pdf_templates import merge_pdfs
                pdf_path = merge_pdfs([list_pdf, mel_pdf], output)
                try:
                    os.remove(list_pdf)
                    os.remove(mel_pdf)
                except Exception:
                    pass
            else:
                return JSONResponse(content={"error": "PDF failed"}, status_code=500)
        else:
            return JSONResponse(content={"error": "Invalid format"}, status_code=400)
        if not pdf_path or not os.path.exists(pdf_path):
            return JSONResponse(content={"error": "PDF failed"}, status_code=500)
        if logo_path and os.path.exists(logo_path):
            try:
                os.remove(logo_path)
            except Exception:
                pass
        filename = f"MPF_Roster_{session.get('cycle', 'SSG')}_{session.get('year', 2025)}_{format}.pdf"
        return FileResponse(pdf_path, media_type="application/pdf", filename=filename)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


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
    output_path = f"/tmp/mfr_{uuid.uuid4().hex}.docx"

    try:
        mfr_data = payload.dict()
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
        )

    except Exception as e:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        return error_response(500, f"Error generating MFR: {str(e)}", context={"step": "mfr_generation"}, exception=e)
