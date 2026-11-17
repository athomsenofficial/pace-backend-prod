"""
Centralized error handling with diagnostic logging.

Provides error_response() — a single function that:
1. Logs the error with full context (what happened, where, why)
2. Returns a consistent JSONResponse to the client

Usage in routers:
    from error_handling import error_response

    # Instead of:
    return JSONResponse(content={"error": "Session not found"}, status_code=404)

    # Use:
    return error_response(404, "Session not found", context={"session_id": session_id})
"""

import logging
import traceback
from fastapi.responses import JSONResponse

logger = logging.getLogger("pace.errors")

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def error_response(
    status_code: int,
    message: str,
    context: dict | None = None,
    exception: Exception | None = None,
    extra: dict | None = None,
) -> JSONResponse:
    """
    Log the error with diagnostic context and return a consistent error response.

    Args:
        status_code: HTTP status code (400, 404, 500, etc.)
        message: Human-readable error message (sent to client)
        context: Dict of diagnostic info (session_id, cycle, filename, step, etc.)
        exception: The caught exception (if any) — logged but NOT sent to client
        extra: Optional additional JSON fields sent to the client alongside
            "error" (e.g. {"missing_params": [...]}). Never put row data here.

    Returns:
        JSONResponse with consistent error format
    """
    # Build diagnostic log
    parts = [f"[{status_code}] {message}"]

    if context:
        # Filter out None values and format
        ctx_parts = [f"{k}={v}" for k, v in context.items() if v is not None]
        if ctx_parts:
            parts.append(f"context={{ {', '.join(ctx_parts)} }}")

    if exception:
        parts.append(f"exception={type(exception).__name__}: {str(exception)[:200]}")

    log_msg = " | ".join(parts)

    if status_code >= 500:
        logger.error(log_msg)
        if exception:
            logger.debug(traceback.format_exc())
    elif status_code >= 400:
        logger.warning(log_msg)

    content = {"error": message}
    if extra:
        content.update({k: v for k, v in extra.items() if k != "error"})
    return JSONResponse(
        content=content,
        status_code=status_code,
    )


def log_step(step: str, detail: str = "", session_id: str = ""):
    """Log a processing step for tracing multi-step operations."""
    parts = [f"STEP: {step}"]
    if detail:
        parts.append(detail)
    if session_id:
        parts.append(f"session={session_id[:8]}")
    logger.info(" | ".join(parts))
