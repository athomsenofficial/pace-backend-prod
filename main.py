from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from constants import cors_origins

from routers.health import router as health_router
from routers.mel import router as mel_router
from routers.roster import router as roster_router
from routers.documents import router as documents_router
from routers.calculators import router as calculators_router

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from request_logging import RequestLoggingMiddleware
app.add_middleware(RequestLoggingMiddleware)

# v1 routes
app.include_router(health_router, prefix="/api/v1")
app.include_router(mel_router, prefix="/api/v1")
app.include_router(roster_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(calculators_router, prefix="/api/v1")

# Backward-compat: /api/* redirects to /api/v1/*
from fastapi.responses import RedirectResponse
from starlette.requests import Request

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def legacy_redirect(request: Request, path: str):
    """Redirect old /api/ routes to /api/v1/ for backward compatibility."""
    new_url = f"/api/v1/{path}"
    if request.query_params:
        new_url += f"?{request.query_params}"
    return RedirectResponse(url=new_url, status_code=307)
