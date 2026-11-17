"""
Retention and BTZ roster runs over one uploaded alpha roster.

Upload once (POST /api/v1/rosters/upload, multipart "file", CSV/XLSX — the real
76-column alpha-roster export works as-is; only the columns these runs need are
kept and PII such as DATE_OF_BIRTH / HOME_* / phone / SSN-like columns is
dropped before the encrypted Redis session is written). Then call any run
against the returned session_id. Run ids:

  dos-reenlistment   DOS / Reenlistment Decision      (CSS PSDG F1 items 3, 36; G1 item 1)
  deros-option       DEROS Option                     (CSS PSDG F1 item 40; G1 items 6-7; F1 item 3)
  re-code-review     RE Code Management               (CSS PSDG F1 items 36, 37(b); G1 item 1)
  btz-quarterly      SrA BTZ Quarterly Eligibility    (CSS PSDG F1 item 32)

Endpoints (all under /api/v1)
-----------------------------
GET  /rosters/runs[?session_id=...&as_of_date=YYYY-MM-DD]
     -> {"as_of": "YYYY-MM-DD", "runs": [{id, label, description, duty[], required_columns[],
         optional_columns[], params[{name, label, type, default, unit, help, citation, min?, max?,
         options?}], formats ["pdf","xlsx"], rule_references[{rule, value, citation, note}],
         available?, missing_columns?}]}
     Param types: "int"; "prefix_list" (list of strings or "2,4"); "quarter" ("2027-Q2" = calendar
     quarter of the BTZ dates; options[] lists {id, label, default}).

POST /rosters/{session_id}/runs/{run_id}
     body (all optional): {"as_of_date": "YYYY-MM-DD", "params": {...}, "pascodes": ["ZZ1TEST"]}
     -> 200 {
          run_id, title, duty[], as_of, as_of_display ("17-NOV-2026"), params{}, main_label,
          columns[{key, label, kind}], rows[{...}],
          buckets[{id, label, description, count, columns[], rows[]}],
          summary{...counts...}, warnings[], notes[], footer, pascodes[] (for the filter),
          pascode_filter? (when pascodes was sent),
          # btz-quarterly only:
          quarter{id, label, btz_date_start, btz_date_end, processing_months[], board_month},
          quarter_options[{id, label, default}],
          units[{pascode, unit, eligible_count, size LARGE|SMALL, quota|null, quota_note}],
          cbb{pool_units[], pool_total, quota|null, note, requires_base_wide_roster, label}
        }
     Cell values by column kind: date -> "YYYY-MM-DD" | "INDEFINITE" | null (display as
     DD-MMM-YYYY); int -> number|null; list -> string[]; bool -> true/false; text -> string.
     Rows always carry name, grade, pascode, unit. "pascodes" filters rows/buckets only (BTZ quota
     math stays base-wide).
     Errors: 404 {"error"} unknown session/run; 422 {"error", missing_columns[], invalid_params[]}.

POST /rosters/{session_id}/runs/{run_id}/export?format=pdf|xlsx   (same body)
     -> file bytes (application/pdf or .xlsx), Content-Disposition attachment;
        filename "<run_id>[_<quarter>]_<as_of>.<fmt>". Built in memory, never written to disk.

Statuses (dos-reenlistment): ELIGIBLE, ELIGIBLE - NOT YET SRP CONSIDERED, INELIGIBLE - WAIVABLE,
INELIGIBLE, HYT/RETIREMENT, REVIEW. DEROS flags: NO_ASSIGNMENT, INSUFFICIENT_RETAINABILITY.

CUI: logs carry the run id, truncated session id and counts only — never names or row values.
"""

import asyncio
import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from error_handling import error_response
from rate_limiter import limiter
from roster_rules import RosterRunError, parse_as_of
from roster_runs.exports import build_export, export_filename
from roster_runs.registry import RunError, execute, list_runs
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


@router.get("/rosters/runs")
async def get_roster_runs(session_id: Optional[str] = None, as_of_date: Optional[str] = None):
    """List the four runs with labels, descriptions, CSS PSDG duty, params and defaults."""
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


@router.post("/rosters/{session_id}/runs/{run_id}")
@limiter.limit("60/minute")
async def run_roster_run(request: Request, session_id: str, run_id: str, payload: Optional[RunRequest] = None):
    payload = payload or RunRequest()
    try:
        result, error = await asyncio.to_thread(_execute, session_id, run_id, payload)
        if error is not None:
            return error
        return JSONResponse(content=result.to_json(), headers=_NO_STORE)
    except Exception as e:
        return error_response(500, "Failed to run roster", context={"run_id": run_id, "step": "roster_run"},
                              exception=e)


@router.post("/rosters/{session_id}/runs/{run_id}/export")
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
