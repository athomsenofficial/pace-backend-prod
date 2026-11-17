
from dataclasses import dataclass
from typing import Literal


@dataclass
class EligibilityResult:
    """Typed return from board_filter — replaces ambiguous tuple/bool/None."""
    status: Literal["eligible", "ineligible", "btz", "discrepancy", "skip"]
    reason: str | None = None

    @property
    def is_eligible(self) -> bool:
        return self.status in ("eligible", "btz", "discrepancy")

from typing import Dict
from pydantic import BaseModel

class PasCodeInfo(BaseModel):
    srid: str
    senior_rater_name: str
    senior_rater_rank: str
    senior_rater_title: str
    senior_rater_first_name: str | None = None
    senior_rater_middle_name: str | None = None
    senior_rater_last_name: str | None = None
    commander_rank: str | None = None
    # The UI has always sent commander_title; without this field pydantic dropped it and
    # the MEL printed the senior rater's title on the commander's signature line.
    commander_title: str | None = None
    commander_first_name: str | None = None
    commander_middle_name: str | None = None
    commander_last_name: str | None = None

class PasCodeSubmission(BaseModel):
    session_id: str
    pascode_info: Dict[str, PasCodeInfo]

class PromotionEligibilityRequest(BaseModel):
    tig_date: str  # DD-MMM-YYYY or ISO format
    tis_date: str
    current_rank: str
    target_year: int

class BTZEligibilityRequest(BaseModel):
    enlistment_date: str
    a1c_dor: str
    target_year: int
