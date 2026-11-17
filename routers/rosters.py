"""
Recurring rosters — upload any personnel roster, run rule-based watch lists
(retainability, DOS, HYT, UIF, time on station), export PDF/XLSX.

Stateless: the canonicalised roster lives only in the encrypted Redis session
(same TTL as every other session); exports are built in memory per request.
CUI: never log names or row values — only counts and truncated session ids.
"""

import asyncio
import logging
import re
import uuid
from datetime import date
from typing import Any, Dict, Literal, Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from config.columns import ROSTER_PII_DENYLIST_PATTERNS, ROSTER_UPLOAD_REQUIRED_COLUMNS
from error_handling import error_response
from file_ingestion import ingest_file, validate_file_type
from rate_limiter import limiter
from roster_exports import build_pdf, build_xlsx
from roster_rules import (
    RosterRunError, canonicalize_dataframe, get_rule, list_rules, normalize_header, parse_as_of, run_rule,
)
from roster_runs.registry import list_runs
from session_manager import create_session, get_session, update_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Rosters"])

SESSION_KIND = "recurring_roster"
_NO_STORE = {"Cache-Control": "no-store"}


class RosterRunRequest(BaseModel):
    session_id: str
    params: Dict[str, Any] = Field(default_factory=dict)
    as_of_date: Optional[str] = None


class RosterExportRequest(RosterRunRequest):
    format: Literal["pdf", "xlsx"]


_PII_PATTERNS = [re.compile(p) for p in ROSTER_PII_DENYLIST_PATTERNS]


def is_pii_column(name: str) -> bool:
    """True for headers that must never be stored (DOB, HOME_*, phone, SSN-like, ...)."""
    text = normalize_header(name)
    return any(p.search(text) for p in _PII_PATTERNS)


def _session_columns(session: dict) -> list[str]:
    columns = session.get("roster_columns")
    if columns is not None:
        return list(columns)
    seen: dict[str, None] = {}
    for record in session.get("dataframe") or []:
        for key in record:
            seen.setdefault(key, None)
    return list(seen)


def _load_roster_session(session_id: str):
    session = get_session(session_id) if session_id else None
    if not session or "dataframe" not in session:
        return None
    return session


def _run(roster_id: str, payload: RosterRunRequest):
    """Shared run logic. Returns (result, None) or (None, error JSONResponse)."""
    rule = get_rule(roster_id)
    if rule is None:
        return None, error_response(404, f"Unknown roster '{roster_id}'", context={"roster_id": roster_id})
    session = _load_roster_session(payload.session_id)
    if session is None:
        return None, error_response(
            404, "Session not found or expired",
            context={"session_id": payload.session_id[:8], "roster_id": roster_id},
        )
    try:
        as_of = parse_as_of(payload.as_of_date)
        result = run_rule(rule, session["dataframe"], _session_columns(session), payload.params, as_of)
    except RosterRunError as e:
        return None, error_response(
            422, e.message, context={"session_id": payload.session_id[:8], "roster_id": roster_id},
            extra=e.extra(),
        )
    logger.info(
        "Roster run %s session=%s rows_in=%d rows_out=%d",
        roster_id, payload.session_id[:8], len(session["dataframe"]), len(result.rows),
    )
    return result, None


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/rosters/upload")
@limiter.limit("10/minute")
async def upload_roster(request: Request, file: UploadFile = File(...)):
    """Upload a CSV/XLSX roster. Only FULL_NAME and GRADE (or their aliases) are required.

    Only recognised columns (config/columns.py ROSTER_COLUMN_ALIASES) are stored; everything else —
    including DATE_OF_BIRTH, HOME_*, phone, SSN-like columns — is dropped before the session is
    written. The response lists which retention/BTZ runs the stored columns support.
    """
    try:
        validate_file_type(file.content_type)
        contents = await file.read()
        df = await asyncio.to_thread(ingest_file, contents, file.filename or "", None, [])
    except HTTPException as e:
        return error_response(e.status_code, str(e.detail), context={"step": "rosters_upload"})
    except Exception as e:
        return error_response(400, "Could not read the uploaded file", context={"step": "rosters_upload"}, exception=e)

    try:
        if df.empty:
            return error_response(400, "Uploaded file contains no data", context={"step": "rosters_upload"})
        canonical_df, columns_found, unmapped, warnings = canonicalize_dataframe(df)
        # Defence in depth: never store PII columns, even if an alias ever maps one.
        pii = [c for c in columns_found if is_pii_column(c)]
        if pii:
            canonical_df = canonical_df.drop(columns=pii)
            columns_found = [c for c in columns_found if c not in pii]
        missing = [c for c in ROSTER_UPLOAD_REQUIRED_COLUMNS if c not in columns_found]
        if missing:
            return error_response(
                422, f"Missing required columns: {', '.join(missing)}",
                context={"step": "rosters_upload"},
                extra={"missing_columns": missing, "columns_found": columns_found, "unmapped_columns": unmapped},
            )

        session_id = str(uuid.uuid4())
        await asyncio.to_thread(create_session, canonical_df, pd.DataFrame(), session_id)
        await asyncio.to_thread(
            update_session, session_id, session_kind=SESSION_KIND, roster_columns=columns_found,
        )
        logger.info(
            "Roster upload session=%s rows=%d columns=%d unmapped=%d",
            session_id[:8], len(canonical_df), len(columns_found), len(unmapped),
        )
        runs = [
            {"id": r["id"], "label": r["label"], "available": r["available"], "missing_columns": r["missing_columns"]}
            for r in list_runs(date.today(), columns_found)
        ]
        return JSONResponse(content={
            "session_id": session_id,
            "row_count": int(len(canonical_df)),
            "columns_found": columns_found,
            "unmapped_columns": unmapped,
            "warnings": warnings,
            "runs": runs,
        })
    except Exception as e:
        return error_response(500, "Failed to process roster upload", context={"step": "rosters_upload"}, exception=e)


@router.get("/rosters")
async def get_rosters(session_id: Optional[str] = None):
    """List roster rules; with ?session_id= also report availability per rule."""
    if session_id is None:
        return JSONResponse(content=list_rules())
    session = _load_roster_session(session_id)
    if session is None:
        return error_response(404, "Session not found or expired", context={"session_id": session_id[:8]})
    return JSONResponse(content=list_rules(_session_columns(session)))


@router.post("/rosters/{roster_id}/run")
@limiter.limit("60/minute")
async def run_roster(request: Request, roster_id: str, payload: RosterRunRequest):
    try:
        result, error = await asyncio.to_thread(_run, roster_id, payload)
        if error is not None:
            return error
        return JSONResponse(content=result.to_json(), headers=_NO_STORE)
    except Exception as e:
        return error_response(500, "Failed to run roster", context={"roster_id": roster_id, "step": "roster_run"}, exception=e)


@router.post("/rosters/{roster_id}/export")
@limiter.limit("30/minute")
async def export_roster(request: Request, roster_id: str, payload: RosterExportRequest):
    try:
        result, error = await asyncio.to_thread(_run, roster_id, payload)
        if error is not None:
            return error
        if payload.format == "pdf":
            content = await asyncio.to_thread(build_pdf, result)
            media_type = "application/pdf"
        else:
            content = await asyncio.to_thread(build_xlsx, result)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", result.rule.id)
        filename = f"{safe_id}_{result.as_of.isoformat()}.{payload.format}"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"', **_NO_STORE},
        )
    except Exception as e:
        return error_response(
            500, "Failed to export roster", context={"roster_id": roster_id, "step": "roster_export"}, exception=e,
        )
