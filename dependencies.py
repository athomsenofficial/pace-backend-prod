"""
Shared FastAPI dependencies — session validation, cycle/year validation.

Usage in route handlers:
    @router.get("/api/roster/preview/{session_id}")
    async def get_preview(session: dict = Depends(require_session)):
        # session is guaranteed to exist — no manual get_session + 404 check needed
        ...
"""

from fastapi import HTTPException
from session_manager import get_session


def require_session(session_id: str) -> dict:
    """
    FastAPI dependency that loads and validates a session.
    Raises 404 if session is missing or expired.

    Use as: session: dict = Depends(require_session)
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session
