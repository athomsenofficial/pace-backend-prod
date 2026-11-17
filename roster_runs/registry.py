"""
Run registry: labels, descriptions (with CSS PSDG duty), parameters and
defaults, required columns, and dispatch to the pure run functions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable

from config.retention import (
    CSS_DUTIES, CSS_PSDG, DEROS_WINDOW_MONTHS, DOS_WINDOW_MONTHS, OS_TO_CONUS_RETAINABILITY_CITATION,
    OS_TO_CONUS_RETAINABILITY_MONTHS, RE_REVIEW_PREFIXES, RULE_REFERENCES,
)
from roster_rules import to_int

from .btz import default_quarter, parse_quarter, quarter_id, quarter_info, quarter_options, run_btz_quarterly
from .common import RunResult, build_members
from .retention import run_deros_option, run_dos_reenlistment, run_re_code_review


class RunError(Exception):
    """A run cannot proceed (unknown run, missing columns, bad params). Maps to 404/422."""

    def __init__(self, message: str, status_code: int = 422, missing_columns=None, invalid_params=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.missing_columns = list(missing_columns or [])
        self.invalid_params = list(invalid_params or [])

    def extra(self) -> dict:
        return {"missing_columns": self.missing_columns, "invalid_params": self.invalid_params}


@dataclass(frozen=True)
class RunParam:
    name: str
    label: str
    type: str  # int | prefix_list | quarter
    default: Any
    unit: str | None
    help: str
    citation: str | None
    min_value: int | None = None
    max_value: int | None = None

    def to_dict(self, as_of: date) -> dict:
        default = self.default
        if self.type == "quarter":
            default = quarter_id(*default_quarter(as_of))
        elif isinstance(default, tuple):
            default = list(default)
        out = {
            "name": self.name, "label": self.label, "type": self.type, "default": default,
            "unit": self.unit, "help": self.help, "citation": self.citation,
        }
        if self.min_value is not None:
            out["min"] = self.min_value
        if self.max_value is not None:
            out["max"] = self.max_value
        if self.type == "quarter":
            out["options"] = quarter_options(as_of)
        return out


@dataclass(frozen=True)
class RunDef:
    id: str
    label: str
    description: str
    duty: tuple[str, ...]
    required_columns: tuple[str, ...]
    optional_columns: tuple[str, ...]
    params: tuple[RunParam, ...]
    compute: Callable[..., RunResult]

    def missing_columns(self, columns: Iterable[str]) -> list[str]:
        present = set(columns)
        return [c for c in self.required_columns if c not in present]

    def to_dict(self, as_of: date, columns: Iterable[str] | None = None) -> dict:
        out = {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "duty": [f"{CSS_PSDG} {d}" for d in self.duty],
            "required_columns": list(self.required_columns),
            "optional_columns": list(self.optional_columns),
            "params": [p.to_dict(as_of) for p in self.params],
            "formats": ["pdf", "xlsx"],
            "rule_references": [
                {"rule": r[1], "value": r[2], "citation": r[3], "note": r[4]}
                for r in RULE_REFERENCES if r[0] == self.id
            ],
        }
        if columns is not None:
            missing = self.missing_columns(columns)
            out["available"] = not missing
            out["missing_columns"] = missing
        return out


_COMMON_OPTIONAL = ("ASSIGNED_PAS", "ASSIGNED_PAS_CLEARTEXT")

RUNS: dict[str, RunDef] = {}


def _register(run: RunDef) -> None:
    RUNS[run.id] = run


_register(RunDef(
    id="dos-reenlistment",
    label="DOS / Reenlistment Decision",
    description=(
        "Enlisted members whose DOS is within the window: months remaining, action-by date (DOS minus 120 days), "
        "reenlistment status with every reason (RE code, UIF, CJR, extension history, HYT). DOS already past, "
        "indefinite DOS and data issues are listed separately. Officers excluded."
    ),
    duty=(CSS_DUTIES["F1-3"], CSS_DUTIES["F1-36"], CSS_DUTIES["G1-1"]),
    required_columns=("FULL_NAME", "GRADE", "DOS"),
    optional_columns=("ETS", "DOE", "TAFMSD", "REENL_ELIG_STATUS", "UIF_CODE", "UIF_DISPOSITION_DATE",
                      *_COMMON_OPTIONAL),
    params=(RunParam("dos_window_months", "DOS window", "int", DOS_WINDOW_MONTHS, "months",
                     "List members whose DOS is between the as-of date and this many months later.",
                     "Owner spec (DOS_WINDOW_MONTHS) — local preference", 1, 60),),
    compute=run_dos_reenlistment,
))

_register(RunDef(
    id="deros-option",
    label="DEROS Option",
    description=(
        "Enlisted members within the window of DEROS with no assignment on file and/or insufficient retainability "
        "(DOS short of the DEROS month plus the OS-to-CONUS requirement), with their reenlistment/extension status. "
        "Separating-from-overseas, indefinite/blank DEROS, past DEROS and data issues listed separately."
    ),
    duty=(CSS_DUTIES["F1-40"], CSS_DUTIES["G1-6-7"], CSS_DUTIES["F1-3"]),
    required_columns=("FULL_NAME", "GRADE", "DEROS", "DOS"),
    optional_columns=("RNLTD", "GAINING_PAS", "GAINING_PAS_CLEARTEXT", "ETS", "DOE", "TAFMSD",
                      "REENL_ELIG_STATUS", *_COMMON_OPTIONAL),
    params=(
        RunParam("deros_window_months", "DEROS window", "int", DEROS_WINDOW_MONTHS, "months",
                 "List members whose DEROS is between the as-of date and this many months later.",
                 "Owner spec (DEROS_WINDOW_MONTHS) — local preference", 1, 36),
        RunParam("os_to_conus_retainability_months", "OS-to-CONUS retainability", "int",
                 OS_TO_CONUS_RETAINABILITY_MONTHS, "months",
                 "Months of retainability required past the DEROS month (counted month/year).",
                 OS_TO_CONUS_RETAINABILITY_CITATION + " — verify", 1, 48),
    ),
    compute=run_deros_option,
))

_register(RunDef(
    id="re-code-review",
    label="RE Code Management",
    description=(
        "Every enlisted member whose RE code starts with a review prefix (default 2 and 4): code, definition, "
        "waivable and waiver authority, DOS, months to DOS and UIF. Sorted by DOS. No date window."
    ),
    duty=(CSS_DUTIES["F1-36"], CSS_DUTIES["F1-37b"], CSS_DUTIES["G1-1"]),
    required_columns=("FULL_NAME", "GRADE", "REENL_ELIG_STATUS"),
    optional_columns=("DOS", "UIF_CODE", "UIF_DISPOSITION_DATE", *_COMMON_OPTIONAL),
    params=(RunParam("re_review_prefixes", "RE prefixes to review", "prefix_list", RE_REVIEW_PREFIXES, None,
                     "RE code first characters to list, e.g. [\"2\", \"4\"] or \"2,3,4\".",
                     "Owner spec (RE_REVIEW_PREFIXES) — local preference"),),
    compute=run_re_code_review,
))

_register(RunDef(
    id="btz-quarterly",
    label="SrA BTZ Quarterly Eligibility",
    description=(
        "RegAF A1Cs whose BTZ date falls in the selected quarter, counted per unit (PASCODE): LARGE units (7+) "
        "get a 15% quota, smaller units pool into the Central Base Board. Quality indicators shown as remarks. "
        "MPF summary page plus unit pages with Nominate / Do Not Nominate boxes."
    ),
    duty=(CSS_DUTIES["F1-32"],),
    required_columns=("FULL_NAME", "GRADE", "DOR", "TAFMSD", "ASSIGNED_PAS"),
    optional_columns=("ASSIGNED_PAS_CLEARTEXT", "PAFSC", "2AFSC", "3AFSC", "4AFSC", "REENL_ELIG_STATUS",
                      "UIF_CODE", "UIF_DISPOSITION_DATE", "RNLTD", "GAINING_PAS", "ANG_ROLL_INDICATOR",
                      "AFR_SECTION_ID", "GRADE_STATUS_REASON"),
    params=(RunParam("quarter", "BTZ quarter", "quarter", None, None,
                     "Calendar quarter of the BTZ dates, e.g. 2027-Q2 (BTZ dates Apr-Jun 2027, processed Jan/Feb, "
                     "board Mar). Default: the cycle whose first processing month is the current or next month.",
                     "AFI 36-2502 (2 Jul 2026) Table 2.7"),),
    compute=run_btz_quarterly,
))


# =============================================================================
# Params
# =============================================================================

_PREFIX = re.compile(r"^[0-9A-Z]{1,2}$")


def _coerce(spec: RunParam, raw: Any, as_of: date) -> Any:
    """Return the value or raise ValueError(message)."""
    if raw is None or (isinstance(raw, str) and not raw.strip()) or raw == []:
        if spec.type == "quarter":
            return default_quarter(as_of)
        return spec.default
    if spec.type == "int":
        value = None if isinstance(raw, bool) else to_int(raw)
        if value is None:
            raise ValueError("must be a whole number")
        if spec.min_value is not None and value < spec.min_value:
            raise ValueError(f"must be at least {spec.min_value}")
        if spec.max_value is not None and value > spec.max_value:
            raise ValueError(f"must be at most {spec.max_value}")
        return value
    if spec.type == "prefix_list":
        items = raw.split(",") if isinstance(raw, str) else raw
        if not isinstance(items, (list, tuple)):
            raise ValueError("must be a list of RE code prefixes")
        cleaned = [str(i).strip().upper() for i in items if str(i).strip()]
        if not cleaned or not all(_PREFIX.match(p) for p in cleaned):
            raise ValueError("must be 1-2 character RE code prefixes, e.g. [\"2\", \"4\"]")
        return tuple(dict.fromkeys(cleaned))
    if spec.type == "quarter":
        return parse_quarter(str(raw))
    raise ValueError("has an unsupported type")


def resolve_params(run: RunDef, supplied: dict | None, as_of: date) -> tuple[dict, list[str]]:
    supplied = dict(supplied or {})
    values, invalid = {}, []
    for spec in run.params:
        try:
            values[spec.name] = _coerce(spec, supplied.pop(spec.name, None), as_of)
        except ValueError as e:
            invalid.append(f"{spec.name} {e}")
    if invalid:
        raise RunError("Invalid parameter value(s): " + "; ".join(invalid) + ".",
                       invalid_params=[i.split(" ", 1)[0] for i in invalid])
    warnings = [f"Ignored unknown parameter(s): {', '.join(sorted(supplied))}."] if supplied else []
    return values, warnings


# =============================================================================
# Dispatch
# =============================================================================

def get_run(run_id: str) -> RunDef | None:
    return RUNS.get(run_id)


def list_runs(as_of: date, columns: Iterable[str] | None = None) -> list[dict]:
    cols = list(columns) if columns is not None else None
    return [run.to_dict(as_of, cols) for run in RUNS.values()]


def execute(run_id: str, records: list[dict], columns: Iterable[str], params: dict | None, as_of: date,
            pascodes: Iterable[str] | None = None) -> RunResult:
    run = get_run(run_id)
    if run is None:
        raise RunError(f"Unknown run '{run_id}'", status_code=404)
    columns = set(columns)
    missing = run.missing_columns(columns)
    if missing:
        raise RunError(f"Roster is missing required column(s): {', '.join(missing)}.", missing_columns=missing)
    values, warnings = resolve_params(run, params, as_of)
    result = run.compute(build_members(records), as_of, values, columns)
    result.warnings = warnings + result.warnings
    return result.filter_pascodes(pascodes)


__all__ = ["RUNS", "RunError", "execute", "get_run", "list_runs", "resolve_params", "quarter_info"]
