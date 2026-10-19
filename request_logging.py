"""
Enhanced request/response logging middleware.

Two-layer logging:
  1. This middleware: logs every request with method, path, status, duration, route label
  2. error_handling.error_response(): logs diagnostic context (reason, session_id, step)

The middleware does NOT read the response body — that's fragile with ASGI.
Instead, error_response() logs the "why" and the middleware logs the "what".
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("pace.requests")

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


_ROUTE_LABELS = {
    "upload/initial-mel": "Initial MEL Upload",
    "upload/final-mel": "Final MEL Upload",
    "upload/mpf-roster": "MPF Roster Upload",
    "download/initial-mel": "Initial MEL Download",
    "download/final-mel": "Final MEL Download",
    "download/mpf-roster": "MPF Roster Download",
    "roster/preview": "Roster Preview",
    "roster/member": "Roster Member",
    "roster/logo": "Logo",
    "roster/reprocess": "Roster Reprocess",
    "initial-mel/submit/pascode-info": "Initial MEL PASCODE Submit",
    "final-mel/submit/pascode-info": "Final MEL PASCODE Submit",
    "mpf-roster/submit/pascode-info": "MPF PASCODE Submit",
    "calculators/promotion-eligibility": "Promotion Calculator",
    "calculators/btz-eligibility": "BTZ Calculator",
    "generate/mfr": "MFR Generator",
}


def _get_route_label(path: str) -> str:
    clean = path.replace("/api/v1/", "").replace("/api/", "")
    parts = clean.split("/")
    # Strip UUIDs from path
    clean_parts = [p for p in parts if not (len(p) == 36 and p.count("-") == 4)]
    clean_key = "/".join(clean_parts)
    return _ROUTE_LABELS.get(clean_key, clean_key)


def _extract_session_id(path: str) -> str | None:
    for part in path.strip("/").split("/"):
        if len(part) == 36 and part.count("-") == 4:
            return part[:8]
    return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip health checks
        if path.endswith("/health"):
            return await call_next(request)

        start = time.perf_counter()
        method = request.method
        label = _get_route_label(path)
        session = _extract_session_id(path)

        try:
            response = await call_next(request)
            duration = time.perf_counter() - start
            status = response.status_code

            parts = [f"{label} | {method} {path} {status} {duration:.2f}s"]
            if session:
                parts.append(f"session={session}")

            if status >= 500:
                logger.error(" | ".join(parts))
            elif status >= 400:
                logger.warning(" | ".join(parts))
            else:
                logger.info(" | ".join(parts))

            return response

        except Exception as e:
            duration = time.perf_counter() - start
            parts = [
                f"{label} EXCEPTION | {method} {path} 500 {duration:.2f}s",
                f"{type(e).__name__}: {str(e)[:150]}",
            ]
            if session:
                parts.append(f"session={session}")
            logger.error(" | ".join(parts))
            raise
