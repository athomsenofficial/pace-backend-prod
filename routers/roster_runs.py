"""
Retention, BTZ and CJR roster runs.

STATELESS (current): each roster tool uploads its own alpha roster with every
request. The file is parsed in memory with the same column canonicalisation and
PII denylist as /rosters/upload (DATE_OF_BIRTH / HOME_* / phone / SSN-like
columns are dropped), the rule runs, and the response is returned. Nothing is
written to Redis, the session store or disk; logs carry the run id and counts
only — never names or row values.

Run ids:

  dos-reenlistment   DOS / Reenlistment Decision      (CSS PSDG F1 items 3, 36; G1 item 1)
  deros-option       DEROS Option                     (CSS PSDG F1 item 40; G1 items 6-7; F1 item 3)
  re-code-review     RE Code Management               (CSS PSDG F1 items 36, 37(b); G1 item 1)
  btz-quarterly      SrA BTZ Quarterly Eligibility    (CSS PSDG F1 item 32)
  cjr-window         First-Term CJR Window            (CSS PSDG F1 items 36, 3)

Endpoints (all under /api/v1)
-----------------------------
GET  /rosters/runs[?as_of_date=YYYY-MM-DD]            (session_id optional, deprecated)
     -> {"as_of": "YYYY-MM-DD", "runs": [{id, label, description, duty[], required_columns[],
         optional_columns[], params[{name, label, type, default, unit, help, citation, min?, max?,
         options?}], formats ["pdf","xlsx"], rule_references[{rule, value, citation, note}],
         available?, missing_columns?}]}
     Param types: "int"; "prefix_list" (list of strings or "2,4"); "quarter" ("2027-Q2" = calendar
     quarter of the BTZ dates; options[] lists {id, label, default}).

POST /rosters/runs/{run_id}/process                   (multipart/form-data, stateless)
     form fields:
       file         required  .xlsx / .xls / .csv alpha roster
       as_of_date   optional  "YYYY-MM-DD" (default today)
       params       optional  JSON object string, e.g. '{"dos_window_months": 12}'
       pascodes     optional  JSON array string, e.g. '["ZZ1TEST"]'
     -> 200 run result (shape below), Cache-Control: no-store. The roster's canonicalisation
        warnings are prepended to warnings[].
     Errors: 404 {"error"} unknown run; 400 {"error"} bad file type, unreadable or empty file;
        422 {"error", missing_columns[], invalid_params[]} (missing roster columns, bad param
        values, or params/pascodes/as_of_date that are not valid JSON / dates).

POST /rosters/runs/{run_id}/process/export?format=pdf|xlsx   (same multipart body, stateless)
     -> file bytes (application/pdf or
        application/vnd.openxmlformats-officedocument.spreadsheetml.sheet),
        Content-Disposition: attachment; filename="<run_id>[_<quarter>]_<as_of>.<fmt>",
        Cache-Control: no-store. Built in memory, never written to disk. Same errors as above.

Run result (JSON):
     {
       run_id, title, duty[], as_of, as_of_display ("17-NOV-2026"), params{}, main_label,
       columns[{key, label, kind}], rows[{...}],
       buckets[{id, label, description, count, columns[], rows[]}],
       summary{...counts...}, warnings[], notes[], footer, pascodes[] (for the filter),
       pascode_filter? (when pascodes was sent),
       # btz-quarterly only:
       quarter{id, label, btz_date_start, btz_date_end, processing_months[], board_month},
       quarter_options[{id, label, default}],
       units[{pascode, unit, eligible_count, size LARGE|SMALL, quota|null (exact 15%, 2 decimals),
              quota_display ("1.65" | ""), quota_note}],
       cbb{pool_units[], pool_total, quota|null, quota_display, note, policy_note,
           requires_base_wide_roster, label}
     }
     Cell values by column kind: date -> "YYYY-MM-DD" | "INDEFINITE" | null (display as
     DD-MMM-YYYY); int -> number|null; decimal -> number; list -> string[]; bool -> true/false;
     text -> string. Rows always carry name, grade, pascode, unit. "pascodes" filters rows/buckets
     only (BTZ quota math stays base-wide).

     cjr-window rows: name, grade, pascode, unit, dafsc, doe, ets, dos, term ("4-year" |
       "AMBIGUOUS (6-year, or 4-year extended)"), month_of_enlistment, window_start, window_end,
       months_until_close (negative = past), status ("IN WINDOW" | "PAST WINDOW" | "APPROACHING"),
       windows (text), re_code, re_definition, uif_code, uif_disposition_date, notes[].
       params: approaching_months (int 0-12, default 3). Buckets: data_issue. Summary: listed,
       in_window, past_window, approaching, not_first_term_excluded, re_1r_excluded,
       window_not_yet_open, officers_excluded, data_issue, with_uif.

DEPRECATED (kept until the frontend moves to /process; they read the roster from a Redis session
created by POST /rosters/upload):
POST /rosters/{session_id}/runs/{run_id}                        JSON body {"as_of_date", "params", "pascodes"}
POST /rosters/{session_id}/runs/{run_id}/export?format=pdf|xlsx (same body)
     Same response shapes as the /process endpoints; 404 for an unknown/expired session.

Statuses (dos-reenlistment): ELIGIBLE, ELIGIBLE - NOT YET SRP CONSIDERED, INELIGIBLE - WAIVABLE,
INELIGIBLE, HYT/RETIREMENT, REVIEW. DEROS flags: NO_ASSIGNMENT, INSUFFICIENT_RETAINABILITY.

CUI: logs carry the run id, truncated session id (deprecated endpoints) and counts only — never
names or row values.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from error_handling import error_response
from file_ingestion import ingest_file, validate_file_type
from rate_limiter import limiter
from roster_rules import RosterRunError, canonicalize_dataframe, parse_as_of
from roster_runs.exports import build_export, export_filename
from roster_runs.registry import RunError, execute, get_run, list_runs
from routers.rosters import is_pii_column
from session_manager import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Roster runs"])

_NO_STORE = {"Cache-Control": "no-store"}


class RunRequest(BaseModel):
    as_of_date: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    pascodes: Optional[List[str]] = None


def _session_columns(session: dict) -> list[str]:
    columns = session.get("roster_columns")
    if columns is not None:
        return list(columns)
    seen: dict[str, None] = {}
    for record in session.get("dataframe") or []:
        for key in record:
            seen.setdefault(key, None)
    return list(seen)


def _load(session_id: str):
    session = get_session(session_id) if session_id else None
    if not session or "dataframe" not in session:
        return None
    return session


def _execute(session_id: str, run_id: str, payload: RunRequest):
    """Returns (RunResult, None) or (None, error JSONResponse)."""
    ctx = {"session_id": session_id[:8], "run_id": run_id}
    session = _load(session_id)
    if session is None:
        return None, error_response(404, "Session not found or expired", context=ctx)
    try:
        as_of = parse_as_of(payload.as_of_date)
        result = execute(run_id, session["dataframe"], _session_columns(session), payload.params, as_of,
                         payload.pascodes)
    except RosterRunError as e:
        return None, error_response(422, e.message, context=ctx, extra=e.extra())
    except RunError as e:
        return None, error_response(e.status_code, e.message, context=ctx, extra=e.extra())
    logger.info(
        "Roster run %s session=%s records=%d rows=%d buckets=%d",
        run_id, session_id[:8], len(session["dataframe"]), len(result.rows),
        sum(len(b.rows) for b in result.buckets),
    )
    return result, None


# =============================================================================
# Stateless processing (no Redis, no disk)
# =============================================================================

class _RequestError(Exception):
    def __init__(self, status_code: int, message: str, extra: Optional[dict] = None):
        super().__init__(message)
        self.status_code, self.message, self.extra = status_code, message, extra or {}


def _records_like_session(df: pd.DataFrame) -> list[dict]:
    """The records exactly as the (deprecated) session path would store and reload them:
    datetimes -> 'YYYY-MM-DD' / ISO strings, NaN -> None, JSON-native values. In memory only."""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d").fillna("")
        elif out[col].dtype == "object":
            out[col] = out[col].apply(lambda x: x.isoformat() if isinstance(x, (datetime, pd.Timestamp)) else x)
    records = out.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if not isinstance(value, (list, dict)) and pd.isna(value):
                record[key] = None
    return json.loads(json.dumps(records, default=str))


def _parse_form(run_id: str, contents: bytes, filename: str, as_of_date: Optional[str], params: Optional[str],
                pascodes: Optional[str]):
    """-> (records, columns, as_of, params, pascodes, canonicalisation warnings). Raises _RequestError."""
    if get_run(run_id) is None:
        raise _RequestError(404, f"Unknown run '{run_id}'")
    invalid = []
    try:
        params_value = json.loads(params) if params and params.strip() else {}
        if not isinstance(params_value, dict):
            raise ValueError
    except ValueError:
        params_value = None
        invalid.append("params")
    try:
        pascodes_value = json.loads(pascodes) if pascodes and pascodes.strip() else None
        if pascodes_value is not None and not (
                isinstance(pascodes_value, list) and all(isinstance(p, str) for p in pascodes_value)):
            raise ValueError
    except ValueError:
        pascodes_value = None
        invalid.append("pascodes")
    if invalid:
        raise _RequestError(422, "params must be a JSON object string and pascodes a JSON array of strings.",
                            {"missing_columns": [], "invalid_params": invalid})
    try:
        as_of = parse_as_of(as_of_date)
    except RosterRunError as e:
        raise _RequestError(422, e.message, e.extra())
    try:
        df = ingest_file(contents, filename or "", None, [])
    except HTTPException as e:
        raise _RequestError(e.status_code, str(e.detail))
    except Exception:
        raise _RequestError(400, "Could not read the uploaded file")
    if df.empty:
        raise _RequestError(400, "Uploaded file contains no data")
    canonical_df, columns_found, _unmapped, warnings = canonicalize_dataframe(df)
    pii = [c for c in columns_found if is_pii_column(c)]
    if pii:
        canonical_df = canonical_df.drop(columns=pii)
        columns_found = [c for c in columns_found if c not in pii]
    return _records_like_session(canonical_df), columns_found, as_of, params_value, pascodes_value, warnings


def _process(run_id: str, contents: bytes, filename: str, as_of_date, params, pascodes):
    """Returns (RunResult, None) or (None, error JSONResponse). Stateless."""
    ctx = {"run_id": run_id, "step": "roster_process"}
    try:
        records, columns, as_of, params_value, pascodes_value, warnings = _parse_form(
            run_id, contents, filename, as_of_date, params, pascodes)
        result = execute(run_id, records, columns, params_value, as_of, pascodes_value)
    except _RequestError as e:
        return None, error_response(e.status_code, e.message, context=ctx, extra=e.extra or None)
    except RosterRunError as e:
        return None, error_response(422, e.message, context=ctx, extra=e.extra())
    except RunError as e:
        return None, error_response(e.status_code, e.message, context=ctx, extra=e.extra())
    result.warnings = list(warnings) + result.warnings
    logger.info("Roster run (stateless) %s records=%d rows=%d buckets=%d", run_id, len(records), len(result.rows),
                sum(len(b.rows) for b in result.buckets))
    return result, None


async def _read_upload(file: UploadFile):
    validate_file_type(file.content_type)
    return await file.read()


@router.post("/rosters/runs/{run_id}/process")
@limiter.limit("60/minute")
async def process_roster_run(
    request: Request,
    run_id: str,
    file: UploadFile = File(...),
    as_of_date: Optional[str] = Form(None),
    params: Optional[str] = Form(None),
    pascodes: Optional[str] = Form(None),
):
    """Upload a roster and run one rule in a single stateless request (nothing is stored)."""
    try:
        try:
            contents = await _read_upload(file)
        except HTTPException as e:
            return error_response(e.status_code, str(e.detail), context={"run_id": run_id, "step": "roster_process"})
        result, error = await asyncio.to_thread(_process, run_id, contents, file.filename or "", as_of_date,
                                                params, pascodes)
        if error is not None:
            return error
        return JSONResponse(content=result.to_json(), headers=_NO_STORE)
    except Exception as e:
        return error_response(500, "Failed to run roster", context={"run_id": run_id, "step": "roster_process"},
                              exception=e)


@router.post("/rosters/runs/{run_id}/process/export")
@limiter.limit("30/minute")
async def process_roster_run_export(
    request: Request,
    run_id: str,
    file: UploadFile = File(...),
    as_of_date: Optional[str] = Form(None),
    params: Optional[str] = Form(None),
    pascodes: Optional[str] = Form(None),
    format: Literal["pdf", "xlsx"] = Query("pdf"),
):
    """Upload a roster, run one rule and return the PDF/XLSX in one stateless request."""
    try:
        try:
            contents = await _read_upload(file)
        except HTTPException as e:
            return error_response(e.status_code, str(e.detail), context={"run_id": run_id, "step": "roster_process"})
        result, error = await asyncio.to_thread(_process, run_id, contents, file.filename or "", as_of_date,
                                                params, pascodes)
        if error is not None:
            return error
        content, media_type = await asyncio.to_thread(build_export, result, format)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{export_filename(result, format)}"',
                     **_NO_STORE},
        )
    except Exception as e:
        return error_response(500, "Failed to export roster", context={"run_id": run_id, "step": "roster_process"},
                              exception=e)


# =============================================================================
# Run catalogue + deprecated session-based endpoints
# =============================================================================

@router.get("/rosters/runs")
async def get_roster_runs(session_id: Optional[str] = None, as_of_date: Optional[str] = None):
    """List the runs with labels, descriptions, CSS PSDG duty, params and defaults (no session needed;
    session_id is optional and deprecated)."""
    try:
        as_of = parse_as_of(as_of_date)
    except RosterRunError as e:
        return error_response(422, e.message, context={"step": "list_runs"}, extra=e.extra())
    columns = None
    if session_id:
        session = await asyncio.to_thread(_load, session_id)
        if session is None:
            return error_response(404, "Session not found or expired", context={"session_id": session_id[:8]})
        columns = _session_columns(session)
    return JSONResponse(content={"as_of": as_of.isoformat(), "runs": list_runs(as_of, columns)})


@router.post("/rosters/{session_id}/runs/{run_id}", deprecated=True)
@limiter.limit("60/minute")
async def run_roster_run(request: Request, session_id: str, run_id: str, payload: Optional[RunRequest] = None):
    """DEPRECATED: use POST /rosters/runs/{run_id}/process (stateless)."""
    payload = payload or RunRequest()
    try:
        result, error = await asyncio.to_thread(_execute, session_id, run_id, payload)
        if error is not None:
            return error
        return JSONResponse(content=result.to_json(), headers=_NO_STORE)
    except Exception as e:
        return error_response(500, "Failed to run roster", context={"run_id": run_id, "step": "roster_run"},
                              exception=e)


@router.post("/rosters/{session_id}/runs/{run_id}/export", deprecated=True)
@limiter.limit("30/minute")
async def export_roster_run(
    request: Request,
    session_id: str,
    run_id: str,
    payload: Optional[RunRequest] = None,
    format: Literal["pdf", "xlsx"] = Query("pdf"),
):
    payload = payload or RunRequest()
    try:
        result, error = await asyncio.to_thread(_execute, session_id, run_id, payload)
        if error is not None:
            return error
        content, media_type = await asyncio.to_thread(build_export, result, format)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{export_filename(result, format)}"',
                     **_NO_STORE},
        )
    except Exception as e:
        return error_response(500, "Failed to export roster", context={"run_id": run_id, "step": "roster_export"},
                              exception=e)


__all__ = ["router"]
