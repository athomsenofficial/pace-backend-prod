import hmac
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from rate_limiter import limiter
from constants import cors_origins

logger = logging.getLogger(__name__)

from routers.health import router as health_router
from routers.mel import router as mel_router
from routers.roster import router as roster_router
from routers.documents import router as documents_router
from routers.calculators import router as calculators_router
from routers.rosters import router as rosters_router
from routers.roster_runs import router as roster_runs_router


@asynccontextmanager
async def lifespan(app):
    # Startup — nothing needed
    yield
    # Shutdown
    from logging_config import LoggerSetup
    for logger_key in list(LoggerSetup._session_loggers.keys()):
        session_id = logger_key.removeprefix("session_")
        LoggerSetup.close_session_logger(session_id)
    from session_manager import _redis_client
    if _redis_client is not None:
        _redis_client.close()
    logger.info("PACE backend shut down gracefully")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# --- Security Headers Middleware ---
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)


# --- API Key Authentication Middleware ---
API_KEY = os.getenv("PACE_API_KEY")
if not API_KEY:
    logger.warning("PACE_API_KEY not set — API authentication is DISABLED. Set this env var in production!")

class APIKeyMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = {"/api/v1/health", "/api/health"}

    async def dispatch(self, request: Request, call_next):
        if not API_KEY:
            return await call_next(request)

        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        provided_key = request.headers.get("X-API-Key") or ""
        if not hmac.compare_digest(provided_key, API_KEY):
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid or missing API key"}
            )
        return await call_next(request)

app.add_middleware(APIKeyMiddleware)


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    # Let browser clients read the download filename on export responses.
    expose_headers=["Content-Disposition"],
)

from request_logging import RequestLoggingMiddleware
app.add_middleware(RequestLoggingMiddleware)


# v1 routes
app.include_router(health_router, prefix="/api/v1")
app.include_router(mel_router, prefix="/api/v1")
app.include_router(roster_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(calculators_router, prefix="/api/v1")
app.include_router(rosters_router, prefix="/api/v1")
app.include_router(roster_runs_router, prefix="/api/v1")

# Backward-compat: /api/* redirects to /api/v1/*
from fastapi.responses import RedirectResponse  # noqa: F811

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def legacy_redirect(request: Request, path: str):
    """Redirect old /api/ routes to /api/v1/ for backward compatibility.

    Only un-versioned legacy paths are redirected. A path that already starts
    with /api/v1/ and reached this catch-all has no matching v1 route, so it is
    a genuine 404 (redirecting it would loop: /api/v1/x -> /api/v1/v1/x -> ...).
    """
    if path == "v1" or path.startswith("v1/"):
        return JSONResponse(status_code=404, content={"error": "Not found"})
    new_url = f"/api/v1/{path}"
    if request.query_params:
        new_url += f"?{request.query_params}"
    return RedirectResponse(url=new_url, status_code=307)
