"""
Standardized response models for all API routes.

All routes return PaceResponse[T] — a consistent envelope that the frontend
can rely on without defensive checks for varying shapes.
"""

from pydantic import BaseModel
from typing import Generic, TypeVar, Optional, List, Dict, Any

T = TypeVar("T")


class PaceResponse(BaseModel, Generic[T]):
    """Standard response envelope for all PACE API endpoints."""
    success: bool
    data: Optional[T] = None
    errors: List[str] = []
    session_id: Optional[str] = None


# ============================================================================
# Upload responses
# ============================================================================

class UploadResult(BaseModel):
    message: str
    pascodes: List[str] = []
    pascode_unit_map: Dict[str, str] = {}
    senior_rater_needed: bool = False


# ============================================================================
# Roster responses
# ============================================================================

class RosterStatistics(BaseModel):
    total_uploaded: int = 0
    total_processed: int = 0
    eligible: int = 0
    ineligible: int = 0
    discrepancy: int = 0
    btz: int = 0
    errors: int = 0


class RosterPreview(BaseModel):
    cycle: str
    year: int
    edited: bool = False
    statistics: RosterStatistics
    categories: Dict[str, List[Dict[str, Any]]]
    errors: List[str] = []
    pascodes: List[str] = []
    pascode_unit_map: Dict[str, str] = {}
    custom_logo: Dict[str, Any] = {}
    pascode_map: Dict[str, Any] = {}
    srid_pascode_map: Dict[str, Any] = {}
    small_unit_sr: Optional[Dict[str, Any]] = None
    senior_rater_needed: bool = False


class MemberAction(BaseModel):
    message: str
    member_id: Optional[str] = None
    category: Optional[str] = None


class DeleteAction(MemberAction):
    reason: Optional[str] = None
    hard_delete: bool = False


class LogoAction(BaseModel):
    message: str
    filename: Optional[str] = None


class ReprocessResult(BaseModel):
    message: str
    preserve_edits: bool = True
    categories: List[str] = []


# ============================================================================
# Document responses
# ============================================================================

class MPFUploadResult(BaseModel):
    message: str
    cycle: str
    year: int


class SimpleMessage(BaseModel):
    message: str
