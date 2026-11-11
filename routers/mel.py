import asyncio
import os
import io
import uuid
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, File
from error_handling import error_response
from fastapi.responses import JSONResponse, StreamingResponse
import pandas as pd
from typing import Optional
from session_manager import create_session, get_pdf_from_redis, get_session, update_session
from roster_processor import roster_processor
from initial_mel_generator import generate_roster_pdf
from final_mel_generator import generate_final_roster_pdf
from classes import PasCodeSubmission
from constants import images_dir, default_logo, TEMP_DIR
from file_ingestion import validate_cycle, validate_year, validate_file_type, ingest_file, prepare_session_dataframes
from logging_config import LoggerSetup
from starlette.background import BackgroundTask
from rate_limiter import limiter
from pdf_utils import cleanup_temp_file

router = APIRouter(tags=["MEL"])


def _process_upload(file, contents, cycle, year, session_id, mel_type):
    """Shared upload logic for both initial and final MEL."""
    logger = LoggerSetup.get_session_logger(session_id, cycle, year)
    logger.info(f"{mel_type.upper()} MEL UPLOAD STARTED")
    logger.info(f"  Filename: {file.filename}, Content Type: {file.content_type}, Cycle: {cycle}, Year: {year}")

    try:
        df = ingest_file(contents, file.filename, logger=logger)
        processed_df, pdf_df = prepare_session_dataframes(df)

        create_session(processed_df, pdf_df, session_id=session_id)
        logger.info(f"  Session created: {session_id}")

        update_session(session_id, cycle=cycle, year=year)

        logger.info(f"  Starting roster processing...")
        roster_processor(df, session_id, cycle, year)
        logger.info(f"  Roster processing complete")

        session = get_session(session_id)
        result = {
            "message": "Upload successful.",
            "errors": session.get("error_log", []),
            "pascodes": session.get("pascodes", []),
            "pascode_unit_map": session.get("pascode_unit_map", {}),
            "senior_rater_needed": bool(session.get("small_unit_df")),
        }

        if result["pascodes"]:
            logger.info(f"  PASCODEs found: {len(result['pascodes'])}")
        if result["senior_rater_needed"]:
            logger.info(f"  Senior rater required for small units")
        if result["errors"]:
            logger.warning(f"  Upload completed with {len(result['errors'])} errors")
        else:
            logger.info(f"  Upload completed successfully with no errors")
        logger.info(f"{mel_type.upper()} MEL UPLOAD COMPLETED SUCCESSFULLY")

        return JSONResponse(content={
            "success": True,
            "message": result["message"],
            "pascodes": result["pascodes"],
            "pascode_unit_map": result["pascode_unit_map"],
            "senior_rater_needed": result["senior_rater_needed"],
            "errors": result["errors"],
            "session_id": session_id,
        })

    except HTTPException:
        LoggerSetup.close_session_logger(session_id)
        raise
    except Exception as e:
        logger.error(f"  EXCEPTION during {mel_type} MEL upload: {e}", exc_info=True)
        LoggerSetup.close_session_logger(session_id)
        return error_response(500, "Failed to process roster upload", context={"session_id": session_id, "step": f"{mel_type}_mel_upload"}, exception=e)


def _process_pascode_submit(payload, pdf_generator, output_prefix):
    """Shared pascode submission + PDF generation logic."""
    pascode_map = {pascode: info.model_dump() for pascode, info in payload.pascode_info.items()}
    small_unit_sr = pascode_map.pop('small_unit_sr', None)

    initial_updates = dict(pascode_map=pascode_map)
    if small_unit_sr:
        initial_updates["small_unit_sr"] = small_unit_sr
    update_session(payload.session_id, **initial_updates)

    session = get_session(payload.session_id)
    if not session:
        return error_response(404, "Session not found or expired", context={"session_id": payload.session_id, "step": "pascode_submit"})

    if 'pascodes' not in session or 'pascode_map' not in session:
        return error_response(400, "Invalid session data - missing required keys", context={"session_id": payload.session_id})

    srid_pascode_map = {}
    for pascode in session['pascodes']:
        pm = session['pascode_map'].get(pascode, {})
        srid = pm.get('srid')
        if not srid:
            continue
        if srid in srid_pascode_map:
            srid_pascode_map[srid].append(pascode)
        else:
            srid_pascode_map[srid] = [pascode]

    update_session(payload.session_id, srid_pascode_map=srid_pascode_map)

    logo_path = os.path.join(images_dir, default_logo)
    custom_logo = session.get('custom_logo')
    temp_logo_path = None

    if custom_logo and custom_logo.get('uploaded'):
        import base64
        from session_manager import _get_redis, _is_encrypted, _decrypt_data
        raw_logo = _get_redis().get(f"{payload.session_id}_logo")
        if raw_logo:
            if _is_encrypted(raw_logo):
                raw_logo = _decrypt_data(raw_logo)
            logo_data = base64.b64decode(raw_logo)
            temp_logo_path = f"{TEMP_DIR}/{payload.session_id}_logo.png"
            with open(temp_logo_path, 'wb') as f:
                f.write(logo_data)
            logo_path = temp_logo_path

    try:
        output_path = f"{TEMP_DIR}/{payload.session_id}_{output_prefix}_mel_roster.pdf"
        result_path = pdf_generator(
            payload.session_id,
            output_filename=output_path,
            logo_path=logo_path
        )

        if temp_logo_path and os.path.exists(temp_logo_path):
            os.remove(temp_logo_path)

        if result_path and os.path.exists(result_path):
            from fastapi.responses import FileResponse
            return FileResponse(result_path, media_type="application/pdf",
                                filename=f"{output_prefix}_mel_roster.pdf",
                                background=BackgroundTask(cleanup_temp_file, result_path))
        return error_response(500, "PDF generation failed", context={"session_id": payload.session_id, "step": "pdf_generation"})
    except Exception as e:
        if temp_logo_path and os.path.exists(temp_logo_path):
            os.remove(temp_logo_path)
        raise


def _download_pdf(session_id, filename):
    """Shared PDF download logic."""
    try:
        pdf_buffer: Optional[io.BytesIO] = get_pdf_from_redis(session_id)
        if not pdf_buffer:
            return error_response(404, "PDF not found for this session", context={"session_id": session_id})

        return StreamingResponse(
            pdf_buffer,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return error_response(500, "Failed to retrieve PDF", context={"session_id": session_id, "step": "pdf_download"}, exception=e)


# ============================================================================
# INITIAL MEL
# ============================================================================

@router.post("/upload/initial-mel")
@limiter.limit("10/minute")
async def upload_file(request: Request, file: UploadFile = File(...), cycle: str = Form(...), year: int = Form(...)):
    session_id = str(uuid.uuid4())
    cycle = validate_cycle(cycle)
    year = validate_year(year)
    validate_file_type(file.content_type)
    contents = await file.read()
    return await asyncio.to_thread(_process_upload, file, contents, cycle, year, session_id, "initial")


@router.post("/initial-mel/submit/pascode-info")
async def submit_pascode_info(payload: PasCodeSubmission):
    return await asyncio.to_thread(_process_pascode_submit, payload, generate_roster_pdf, "initial")


@router.get("/download/initial-mel/{session_id}")
async def download_initial_mel(session_id: str):
    return _download_pdf(session_id, "initial_mel_roster.pdf")


# ============================================================================
# FINAL MEL
# ============================================================================

@router.post("/upload/final-mel")
@limiter.limit("10/minute")
async def upload_final_mel_file(request: Request, file: UploadFile = File(...), cycle: str = Form(...), year: int = Form(...)):
    session_id = str(uuid.uuid4())
    cycle = validate_cycle(cycle)
    year = validate_year(year)
    validate_file_type(file.content_type)
    contents = await file.read()
    return await asyncio.to_thread(_process_upload, file, contents, cycle, year, session_id, "final")


@router.post("/final-mel/submit/pascode-info")
async def submit_final_pascode_info(payload: PasCodeSubmission):
    return await asyncio.to_thread(_process_pascode_submit, payload, generate_final_roster_pdf, "final")


@router.get("/download/final-mel/{session_id}")
async def download_final_mel(session_id: str):
    return _download_pdf(session_id, "final_mel_roster.pdf")
