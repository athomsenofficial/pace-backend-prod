"""
Recurring-roster rule engine.

A roster rule is a declarative filter over an uploaded roster: which columns it
needs, which parameters it takes (with units, help and citations), the output
columns it produces, and a compute function that returns matching members.

Design notes
- Stateless: rules read the session's records and return results; nothing is
  written anywhere. Exports are built in memory by roster_exports.py.
- Never invents regulatory numbers: AFI/DAFI-derived params default to the
  values in config/rosters.py, which are all None until confirmed. A required
  param that resolves to None makes the run fail with RosterRunError (-> 422).
- CUI: nothing in this module logs member data. Warnings returned to the
  caller contain counts and column names only, never names or row values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable

import pandas as pd
from dateutil.relativedelta import relativedelta

from config.columns import ROSTER_COLUMN_ALIASES
from config.domain import MAIN_HIGHER_TENURE, RE_CODES
from config.rosters import (
    ASSIGNMENT_RETAINABILITY_BY_TYPE,
    GRADE_ALIASES,
    PREFERENCE_DEFAULTS,
    regulatory_citation,
    regulatory_default,
)
from date_parsing import parse_date
from eligibility_calculators import compute_hyt_date


# =============================================================================
# Errors
# =============================================================================

class RosterRunError(Exception):
    """A run cannot proceed (missing columns/params, bad values). Maps to 422."""

    def __init__(self, message: str, missing_columns=None, missing_params=None, invalid_params=None):
        super().__init__(message)
        self.message = message
        self.missing_columns = list(missing_columns or [])
        self.missing_params = list(missing_params or [])
        self.invalid_params = list(invalid_params or [])

    def extra(self) -> dict:
        return {
            "missing_columns": self.missing_columns,
            "missing_params": self.missing_params,
            "invalid_params": self.invalid_params,
        }


# =============================================================================
# Header alias resolution
# =============================================================================

def normalize_header(header: Any) -> str:
    """Same normalisation as file_ingestion (strip + upper) plus separator folding."""
    text = str(header).strip().upper()
    text = re.sub(r"[\s\-\.\/]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, variants in ROSTER_COLUMN_ALIASES.items():
        for variant in [canonical, *variants]:
            index.setdefault(normalize_header(variant), canonical)
    return index


def resolve_columns(headers: Iterable[Any]) -> tuple[dict[str, str], list[str], list[str]]:
    """Map uploaded headers to canonical names.

    Returns (rename_map {original_header: canonical}, unmapped_headers, warnings).
    When several headers map to the same canonical column, the header that is
    literally the canonical name wins, otherwise the first alias in config order;
    the others are reported as unmapped.
    """
    index = _alias_index()
    candidates: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for header in headers:
        canonical = index.get(normalize_header(header))
        if canonical is None:
            unmapped.append(str(header))
        else:
            candidates.setdefault(canonical, []).append(header)

    rename: dict[str, str] = {}
    warnings: list[str] = []
    for canonical, headers_for in candidates.items():
        if len(headers_for) == 1:
            chosen = headers_for[0]
        else:
            order = [normalize_header(v) for v in [canonical, *ROSTER_COLUMN_ALIASES[canonical]]]
            chosen = min(headers_for, key=lambda h: order.index(normalize_header(h)))
            others = [str(h) for h in headers_for if h is not chosen]
            unmapped.extend(others)
            warnings.append(
                f"Several columns map to {canonical}; using '{chosen}' and ignoring {', '.join(repr(o) for o in others)}."
            )
        rename[chosen] = canonical
    return rename, unmapped, warnings


def canonicalize_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str], list[str]]:
    """Return (canonical_df, columns_found, unmapped_columns, warnings).

    Only recognised columns are kept (data minimisation: unrecognised columns,
    which may include SSANs etc., are never stored in the session).
    """
    rename, unmapped, warnings = resolve_columns(df.columns)
    out = df[list(rename.keys())].rename(columns=rename)
    columns_found = [c for c in ROSTER_COLUMN_ALIASES if c in out.columns]
    return out[columns_found], columns_found, unmapped, warnings


# =============================================================================
# Value helpers (no logging of values, ever)
# =============================================================================

def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def to_date(value: Any) -> date | None:
    if _blank(value):
        return None
    try:
        parsed = parse_date(value)
    except Exception:
        return None
    if parsed is None:
        return None
    return parsed.date() if isinstance(parsed, datetime) else parsed


def to_int(value: Any) -> int | None:
    if _blank(value) or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if pd.isna(number) or number != int(number):
        return None
    return int(number)


def to_text(value: Any) -> str:
    if _blank(value):
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


def normalize_grade(value: Any) -> str:
    text = re.sub(r"[\s\-\.]", "", to_text(value).upper())
    return GRADE_ALIASES.get(text, text)


def add_months(d: date, months: int) -> date:
    return d + relativedelta(months=months)


def whole_months_between(start: date, end: date) -> int:
    """Completed calendar months from start to end (negative if end < start)."""
    if end < start:
        return -whole_months_between(end, start)
    delta = relativedelta(end, start)
    return delta.years * 12 + delta.months


def months_short(have: date, need: date) -> int:
    """Months (rounded UP) that `have` must move forward to reach `need`."""
    if have >= need:
        return 0
    delta = relativedelta(need, have)
    months = delta.years * 12 + delta.months
    return months + (1 if delta.days > 0 else 0)


# =============================================================================
# Declarations
# =============================================================================

@dataclass(frozen=True)
class ParamSpec:
    name: str
    label: str
    type: str  # "int" | "date" | "enum"
    default: Any
    unit: str | None
    help: str
    citation: str | None
    required: bool = True
    min_value: int | None = None
    max_value: int | None = None
    options: tuple[str, ...] | None = None
    # Param is not required when ANY of these columns is in the roster.
    required_unless_columns: tuple[str, ...] = ()

    def is_required(self, columns: Iterable[str] | None = None) -> bool:
        if not self.required:
            return False
        if columns is not None and any(c in set(columns) for c in self.required_unless_columns):
            return False
        return True

    def to_dict(self, columns: Iterable[str] | None = None) -> dict:
        out = {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "default": self.default,
            "unit": self.unit,
            "help": self.help,
            "citation": self.citation,
            "required": self.is_required(columns),
        }
        if self.type == "enum":
            out["options"] = list(self.options or ())
        return out


@dataclass(frozen=True)
class OutputColumn:
    key: str
    label: str
    kind: str = "text"  # "text" | "date" | "int"
    requires_any: tuple[str, ...] = ()  # include only if one of these columns exists

    def applies(self, columns: set[str]) -> bool:
        return not self.requires_any or any(c in columns for c in self.requires_any)


@dataclass
class RuleContext:
    as_of: date
    params: dict[str, Any]
    columns: set[str]
    warnings: list[str] = field(default_factory=list)

    def warn_count(self, count: int, what: str) -> None:
        if count:
            noun = "row" if count == 1 else "rows"
            self.warnings.append(f"{count} {noun} {what}")


@dataclass(frozen=True)
class RosterRule:
    id: str
    title: str
    description: str
    required_columns: tuple[str, ...]
    optional_columns: tuple[str, ...]
    params: tuple[ParamSpec, ...]
    columns: tuple[OutputColumn, ...]
    compute: Callable[[list[dict], RuleContext], list[dict]]

    def missing_columns(self, columns: Iterable[str]) -> list[str]:
        present = set(columns)
        return [c for c in self.required_columns if c not in present]

    def to_dict(self, columns: Iterable[str] | None = None) -> dict:
        out = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "required_columns": list(self.required_columns),
            "optional_columns": list(self.optional_columns),
            "params": [p.to_dict(columns) for p in self.params],
        }
        if columns is not None:
            missing = self.missing_columns(columns)
            out["available"] = not missing
            out["missing_columns"] = missing
        return out

    def output_columns(self, columns: Iterable[str]) -> list[OutputColumn]:
        present = set(columns)
        return [c for c in self.columns if c.applies(present)]


@dataclass
class RosterResult:
    rule: RosterRule
    as_of: date
    params: dict[str, Any]
    columns: list[OutputColumn]
    rows: list[dict]
    warnings: list[str]
    missing_columns: list[str]

    def to_json(self) -> dict:
        return {
            "roster_id": self.rule.id,
            "title": self.rule.title,
            "as_of": self.as_of.isoformat(),
            "count": len(self.rows),
            "columns": [{"key": c.key, "label": c.label} for c in self.columns],
            "rows": [{c.key: json_value(row.get(c.key)) for c in self.columns} for row in self.rows],
            "warnings": list(self.warnings),
            "missing_columns": list(self.missing_columns),
        }

    def param_summary(self) -> list[tuple[str, str]]:
        """[(label, display value)] for report headers."""
        out = []
        for spec in self.rule.params:
            value = self.params.get(spec.name)
            if value is None:
                shown = "not set"
            else:
                shown = value.isoformat() if isinstance(value, date) else str(value)
                if spec.unit:
                    shown = f"{shown} {spec.unit}"
            out.append((spec.label, shown))
        return out


def json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if value is None:
        return None
    return value


# =============================================================================
# Shared output columns
# =============================================================================

_UNIT_SOURCES = ("ASSIGNED_PAS_CLEARTEXT", "ASSIGNED_PAS")

COL_NAME = OutputColumn("full_name", "Name")
COL_GRADE = OutputColumn("grade", "Grade")
COL_UNIT = OutputColumn("unit", "Unit", requires_any=_UNIT_SOURCES)


def _base_row(rec: dict) -> dict:
    unit = to_text(rec.get("ASSIGNED_PAS_CLEARTEXT")) or to_text(rec.get("ASSIGNED_PAS"))
    return {
        "full_name": to_text(rec.get("FULL_NAME")),
        "grade": normalize_grade(rec.get("GRADE")),
        "unit": unit,
    }


def _read_date(rec: dict, column: str, counters: dict) -> date | None:
    """Parse a date cell; tally blank vs unreadable per column for warnings."""
    raw = rec.get(column)
    if _blank(raw):
        counters[(column, "blank")] = counters.get((column, "blank"), 0) + 1
        return None
    parsed = to_date(raw)
    if parsed is None:
        counters[(column, "bad")] = counters.get((column, "bad"), 0) + 1
    return parsed


def _flush_date_warnings(ctx: RuleContext, counters: dict, report_blank: Iterable[str] = ()) -> None:
    report_blank = set(report_blank)
    for (column, kind), count in sorted(counters.items()):
        if kind == "bad":
            ctx.warn_count(count, f"have an unreadable {column} value and were not evaluated.")
        elif column in report_blank:
            ctx.warn_count(count, f"have no {column} and were not evaluated.")


def _status(days: int) -> str:
    if days < 0:
        return "Past due"
    if days == 0:
        return "Due today"
    return "Upcoming"


# =============================================================================
# Rule 1: DEROS retainability
# =============================================================================

def _compute_deros(records: list[dict], ctx: RuleContext) -> list[dict]:
    window = ctx.params["window_close_months_before_deros"]
    required = ctx.params["required_retainability_months"]
    horizon = ctx.as_of + timedelta(days=ctx.params["lookahead_days"])
    counters: dict = {}
    rows = []
    for rec in records:
        deros = _read_date(rec, "DEROS", counters)
        if deros is None:
            continue
        close = add_months(deros, -window)
        if not (ctx.as_of <= close <= horizon):
            continue
        dos = _read_date(rec, "DOS", counters)
        if dos is None:
            continue
        required_dos = add_months(close, required)
        if dos >= required_dos:
            continue
        row = _base_row(rec)
        row.update({
            "deros": deros,
            "window_close_date": close,
            "days_until_window_close": (close - ctx.as_of).days,
            "dos": dos,
            "required_dos": required_dos,
            "shortfall_months": months_short(dos, required_dos),
            "_sort": close,
        })
        rows.append(row)
    # Blank DEROS is normal (CONUS members); blank DOS is not, for members in window.
    _flush_date_warnings(ctx, counters, report_blank=["DOS"])
    return rows


# =============================================================================
# Rule 2: Assignment retainability
# =============================================================================

def _compute_assignment(records: list[dict], ctx: RuleContext) -> list[dict]:
    fallback = ctx.params["required_retainability_months"]
    has_tour = "TOUR_LENGTH_MONTHS" in ctx.columns
    has_type = "ASSIGNMENT_TYPE" in ctx.columns
    counters: dict = {}
    no_requirement = 0
    rows = []
    for rec in records:
        rnltd = _read_date(rec, "RNLTD", counters)
        if rnltd is None:
            continue  # no assignment

        months, basis = None, ""
        tour = to_int(rec.get("TOUR_LENGTH_MONTHS")) if has_tour else None
        a_type = to_text(rec.get("ASSIGNMENT_TYPE")).upper() if has_type else ""
        if tour is not None and tour > 0:
            months, basis = tour, "Tour length column"
        elif a_type and ASSIGNMENT_RETAINABILITY_BY_TYPE.get(a_type) is not None:
            months, basis = ASSIGNMENT_RETAINABILITY_BY_TYPE[a_type], "Assignment type table"
        elif fallback is not None:
            months, basis = fallback, "Parameter"
        if months is None:
            no_requirement += 1
            continue

        dos = _read_date(rec, "DOS", counters)
        if dos is None:
            continue
        required_dos = add_months(rnltd, months)
        if dos >= required_dos:
            continue
        row = _base_row(rec)
        row.update({
            "assignment_type": to_text(rec.get("ASSIGNMENT_TYPE")),
            "rnltd": rnltd,
            "days_until_rnltd": (rnltd - ctx.as_of).days,
            "required_retainability_months": months,
            "requirement_basis": basis,
            "dos": dos,
            "required_dos": required_dos,
            "shortfall_months": months_short(dos, required_dos),
            "_sort": rnltd,
        })
        rows.append(row)
    _flush_date_warnings(ctx, counters, report_blank=["DOS"])
    ctx.warn_count(
        no_requirement,
        "have an assignment but no tour length and no required_retainability_months was given; not evaluated.",
    )
    return rows


# =============================================================================
# Rule 3: DOS window
# =============================================================================

def _compute_dos_window(records: list[dict], ctx: RuleContext) -> list[dict]:
    horizon = add_months(ctx.as_of, ctx.params["months"])
    counters: dict = {}
    past = 0
    rows = []
    for rec in records:
        dos = _read_date(rec, "DOS", counters)
        if dos is None:
            continue
        if dos < ctx.as_of:
            past += 1
            continue
        if dos > horizon:
            continue
        re_code = to_text(rec.get("REENL_ELIG_STATUS")).upper()
        row = _base_row(rec)
        row.update({
            "dos": dos,
            "days_until_dos": (dos - ctx.as_of).days,
            "months_remaining": whole_months_between(ctx.as_of, dos),
            "re_code": re_code,
            "re_description": RE_CODES.get(re_code, "") if re_code else "",
            "_sort": dos,
        })
        rows.append(row)
    _flush_date_warnings(ctx, counters, report_blank=["DOS"])
    ctx.warn_count(past, "have a DOS before the as-of date and were excluded.")
    return rows


# =============================================================================
# Rule 4: HYT approaching
# =============================================================================

def _compute_hyt(records: list[dict], ctx: RuleContext) -> list[dict]:
    horizon = add_months(ctx.as_of, ctx.params["months"])
    has_dos = "DOS" in ctx.columns
    counters: dict = {}
    unsupported_grades: dict[str, int] = {}
    past = 0
    rows = []
    for rec in records:
        grade = normalize_grade(rec.get("GRADE"))
        if MAIN_HIGHER_TENURE.get(grade) is None:
            unsupported_grades[grade or "(blank)"] = unsupported_grades.get(grade or "(blank)", 0) + 1
            continue
        tafmsd = _read_date(rec, "TAFMSD", counters)
        if tafmsd is None:
            continue
        # compute_hyt_date compares against datetime exception-window bounds.
        hyt = compute_hyt_date(datetime(tafmsd.year, tafmsd.month, tafmsd.day), grade).date()
        if hyt < ctx.as_of:
            past += 1
            continue
        if hyt > horizon:
            continue
        dos = to_date(rec.get("DOS")) if has_dos else None
        row = _base_row(rec)
        row.update({
            "grade": grade,
            "tafmsd": tafmsd,
            "hyt_date": hyt,
            "days_until_hyt": (hyt - ctx.as_of).days,
            "months_until_hyt": whole_months_between(ctx.as_of, hyt),
            "dos": dos,
            "dos_beyond_hyt": ("Yes" if dos > hyt else "No") if dos else "",
            "_sort": hyt,
        })
        rows.append(row)
    _flush_date_warnings(ctx, counters, report_blank=["TAFMSD"])
    if unsupported_grades:
        total = sum(unsupported_grades.values())
        grades = ", ".join(sorted(unsupported_grades)[:10])
        ctx.warn_count(total, f"have a grade with no HYT value in PACE ({grades}) and were not evaluated.")
    ctx.warn_count(past, "have an HYT date before the as-of date and were excluded.")
    return rows


# =============================================================================
# Rule 5: UIF disposition due
# =============================================================================

def _compute_uif(records: list[dict], ctx: RuleContext) -> list[dict]:
    horizon = ctx.as_of + timedelta(days=ctx.params["days"])
    counters: dict = {}
    rows = []
    for rec in records:
        disp = _read_date(rec, "UIF_DISPOSITION_DATE", counters)
        if disp is None or disp > horizon:
            continue
        days = (disp - ctx.as_of).days
        row = _base_row(rec)
        row.update({
            "uif_code": to_text(rec.get("UIF_CODE")),
            "uif_disposition_date": disp,
            "days_until_due": days,
            "status": _status(days),
            "_sort": disp,
        })
        rows.append(row)
    _flush_date_warnings(ctx, counters)
    return rows


# =============================================================================
# Rule 6: Time on station
# =============================================================================

def _compute_time_on_station(records: list[dict], ctx: RuleContext) -> list[dict]:
    tour = ctx.params["tour_length_months"]
    horizon = ctx.as_of + timedelta(days=ctx.params["days"])
    counters: dict = {}
    rows = []
    for rec in records:
        das = _read_date(rec, "DATE_ARRIVED_STATION", counters)
        if das is None:
            continue
        tour_end = add_months(das, tour)
        if tour_end > horizon:
            continue
        days = (tour_end - ctx.as_of).days
        row = _base_row(rec)
        row.update({
            "date_arrived_station": das,
            "months_on_station": whole_months_between(das, ctx.as_of),
            "tour_end_date": tour_end,
            "days_until_tour_end": days,
            "status": _status(days),
            "_sort": tour_end,
        })
        rows.append(row)
    _flush_date_warnings(ctx, counters, report_blank=["DATE_ARRIVED_STATION"])
    return rows


# =============================================================================
# Registry
# =============================================================================

def _reg_param(name, label, key, unit, help_text, **kw) -> ParamSpec:
    return ParamSpec(
        name=name, label=label, type="int", default=regulatory_default(key), unit=unit,
        help=help_text, citation=regulatory_citation(key), min_value=kw.pop("min_value", 0), **kw,
    )


def _pref_param(name, label, key, unit, help_text, min_value=0, max_value=None) -> ParamSpec:
    return ParamSpec(
        name=name, label=label, type="int", default=PREFERENCE_DEFAULTS[key], unit=unit,
        help=help_text, citation=None, min_value=min_value, max_value=max_value,
    )


ROSTER_RULES: dict[str, RosterRule] = {}


def _register(rule: RosterRule) -> None:
    ROSTER_RULES[rule.id] = rule


_register(RosterRule(
    id="deros-retainability",
    title="DEROS Retainability",
    description=(
        "Members whose DEROS option-window close date falls within the lookahead and whose DOS is "
        "earlier than the retainability required at window close."
    ),
    required_columns=("FULL_NAME", "GRADE", "DEROS", "DOS"),
    optional_columns=_UNIT_SOURCES,
    params=(
        _reg_param(
            "window_close_months_before_deros", "Option window closes (months before DEROS)",
            "deros.window_close_months_before_deros", "months",
            "How many months before DEROS the DEROS option window closes. Regulatory value - enter it from "
            "the current publication; PACE does not assume one.",
        ),
        _reg_param(
            "required_retainability_months", "Required retainability at window close",
            "deros.required_retainability_months", "months",
            "Months of retainability (DOS beyond window close) required. Regulatory value - enter it from "
            "the current publication; PACE does not assume one.",
        ),
        _pref_param(
            "lookahead_days", "Lookahead", "deros.lookahead_days", "days",
            "Show members whose window closes between the as-of date and this many days later.",
            max_value=3650,
        ),
    ),
    columns=(
        COL_NAME, COL_GRADE, COL_UNIT,
        OutputColumn("deros", "DEROS", "date"),
        OutputColumn("window_close_date", "Window closes", "date"),
        OutputColumn("days_until_window_close", "Days until window closes", "int"),
        OutputColumn("dos", "DOS", "date"),
        OutputColumn("required_dos", "Required DOS", "date"),
        OutputColumn("shortfall_months", "Shortfall (months)", "int"),
    ),
    compute=_compute_deros,
))

_register(RosterRule(
    id="assignment-retainability",
    title="Assignment Retainability",
    description=(
        "Members with an assignment (RNLTD present) whose DOS is earlier than RNLTD plus the required "
        "retainability. Uses the roster's tour-length column per member when present."
    ),
    required_columns=("FULL_NAME", "GRADE", "RNLTD", "DOS"),
    optional_columns=("ASSIGNMENT_TYPE", "TOUR_LENGTH_MONTHS", *_UNIT_SOURCES),
    params=(
        _reg_param(
            "required_retainability_months", "Required retainability after RNLTD",
            "assignment.required_retainability_months", "months",
            "Months of retainability beyond RNLTD required. Used for members without a tour length on the "
            "roster; not required if the roster has a TOUR_LENGTH_MONTHS column. Regulatory value - enter "
            "it from the current publication; PACE does not assume one.",
            required_unless_columns=("TOUR_LENGTH_MONTHS",) + (
                ("ASSIGNMENT_TYPE",) if ASSIGNMENT_RETAINABILITY_BY_TYPE else ()
            ),
        ),
    ),
    columns=(
        COL_NAME, COL_GRADE, COL_UNIT,
        OutputColumn("assignment_type", "Assignment type", requires_any=("ASSIGNMENT_TYPE",)),
        OutputColumn("rnltd", "RNLTD", "date"),
        OutputColumn("days_until_rnltd", "Days until RNLTD", "int"),
        OutputColumn("required_retainability_months", "Required retainability (months)", "int"),
        OutputColumn("requirement_basis", "Requirement source"),
        OutputColumn("dos", "DOS", "date"),
        OutputColumn("required_dos", "Required DOS", "date"),
        OutputColumn("shortfall_months", "Shortfall (months)", "int"),
    ),
    compute=_compute_assignment,
))

_register(RosterRule(
    id="dos-window",
    title="DOS Window",
    description="Members whose DOS falls within the next N months (reenlistment / AF Form 901 workload).",
    required_columns=("FULL_NAME", "GRADE", "DOS"),
    optional_columns=("REENL_ELIG_STATUS", *_UNIT_SOURCES),
    params=(
        _pref_param(
            "months", "Window", "dos_window.months", "months",
            "Show members whose DOS is between the as-of date and this many months later. A local "
            "preference, not a regulatory value.",
            min_value=1, max_value=120,
        ),
    ),
    columns=(
        COL_NAME, COL_GRADE, COL_UNIT,
        OutputColumn("dos", "DOS", "date"),
        OutputColumn("days_until_dos", "Days until DOS", "int"),
        OutputColumn("months_remaining", "Months remaining", "int"),
        OutputColumn("re_code", "RE code", requires_any=("REENL_ELIG_STATUS",)),
        OutputColumn("re_description", "RE code meaning", requires_any=("REENL_ELIG_STATUS",)),
    ),
    compute=_compute_dos_window,
))

_register(RosterRule(
    id="hyt-approaching",
    title="HYT Approaching",
    description=(
        "Members whose High Year of Tenure date (PACE's standard HYT calculation from TAFMSD and grade, "
        "including the temporary exception window) falls within the next N months, and whether their DOS "
        "extends beyond HYT."
    ),
    required_columns=("FULL_NAME", "GRADE", "TAFMSD"),
    optional_columns=("DOS", *_UNIT_SOURCES),
    params=(
        _pref_param(
            "months", "Window", "hyt.months", "months",
            "Show members whose HYT date is between the as-of date and this many months later.",
            min_value=1, max_value=120,
        ),
    ),
    columns=(
        COL_NAME, COL_GRADE, COL_UNIT,
        OutputColumn("tafmsd", "TAFMSD", "date"),
        OutputColumn("hyt_date", "HYT date", "date"),
        OutputColumn("days_until_hyt", "Days until HYT", "int"),
        OutputColumn("months_until_hyt", "Months until HYT", "int"),
        OutputColumn("dos", "DOS", "date", requires_any=("DOS",)),
        OutputColumn("dos_beyond_hyt", "DOS beyond HYT", requires_any=("DOS",)),
    ),
    compute=_compute_hyt,
))

_register(RosterRule(
    id="uif-disposition-due",
    title="UIF Disposition Due",
    description="Members whose UIF disposition date is within the next N days or already past.",
    required_columns=("FULL_NAME", "GRADE", "UIF_DISPOSITION_DATE"),
    optional_columns=("UIF_CODE", *_UNIT_SOURCES),
    params=(
        _pref_param(
            "days", "Lookahead", "uif.days", "days",
            "Show dispositions due between now and this many days out, plus any past due.",
            max_value=3650,
        ),
    ),
    columns=(
        COL_NAME, COL_GRADE, COL_UNIT,
        OutputColumn("uif_code", "UIF code", requires_any=("UIF_CODE",)),
        OutputColumn("uif_disposition_date", "Disposition date", "date"),
        OutputColumn("days_until_due", "Days until due", "int"),
        OutputColumn("status", "Status"),
    ),
    compute=_compute_uif,
))

_register(RosterRule(
    id="time-on-station",
    title="Time on Station",
    description=(
        "Members whose date arrived station plus the tour length is within the next N days or already past."
    ),
    required_columns=("FULL_NAME", "GRADE", "DATE_ARRIVED_STATION"),
    optional_columns=_UNIT_SOURCES,
    params=(
        _reg_param(
            "tour_length_months", "Tour length", "time_on_station.tour_length_months", "months",
            "Tour length to measure from date arrived station. Regulatory / location-specific value - enter "
            "it from the current publication; PACE does not assume one.",
            min_value=1,
        ),
        _pref_param(
            "days", "Lookahead", "time_on_station.days", "days",
            "Show members whose tour end is between now and this many days out, plus any already past.",
            max_value=3650,
        ),
    ),
    columns=(
        COL_NAME, COL_GRADE, COL_UNIT,
        OutputColumn("date_arrived_station", "Date arrived station", "date"),
        OutputColumn("months_on_station", "Months on station", "int"),
        OutputColumn("tour_end_date", "Tour end date", "date"),
        OutputColumn("days_until_tour_end", "Days until tour end", "int"),
        OutputColumn("status", "Status"),
    ),
    compute=_compute_time_on_station,
))


# =============================================================================
# Running
# =============================================================================

def get_rule(roster_id: str) -> RosterRule | None:
    return ROSTER_RULES.get(roster_id)


def list_rules(columns: Iterable[str] | None = None) -> list[dict]:
    cols = list(columns) if columns is not None else None
    return [rule.to_dict(cols) for rule in ROSTER_RULES.values()]


def parse_as_of(value: Any) -> date:
    if _blank(value):
        return date.today()
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise RosterRunError("as_of_date must be a date in YYYY-MM-DD format.", invalid_params=["as_of_date"])


def _coerce(spec: ParamSpec, raw: Any) -> tuple[Any, str | None]:
    """Return (value, error). value None with no error means 'not supplied'."""
    if _blank(raw):
        return None, None
    if spec.type == "int":
        if isinstance(raw, bool):
            return None, "must be a whole number"
        value = to_int(raw)
        if value is None:
            return None, "must be a whole number"
        if spec.min_value is not None and value < spec.min_value:
            return None, f"must be at least {spec.min_value}"
        if spec.max_value is not None and value > spec.max_value:
            return None, f"must be at most {spec.max_value}"
        return value, None
    if spec.type == "date":
        try:
            return date.fromisoformat(str(raw).strip()), None
        except ValueError:
            return None, "must be a date in YYYY-MM-DD format"
    if spec.type == "enum":
        text = str(raw).strip()
        if text not in (spec.options or ()):
            return None, f"must be one of: {', '.join(spec.options or ())}"
        return text, None
    return None, "has an unsupported type"


def resolve_params(rule: RosterRule, supplied: dict | None, columns: Iterable[str]) -> tuple[dict, list[str], list[str], list[str]]:
    """Return (values, missing_required, invalid_messages, warnings)."""
    supplied = dict(supplied or {})
    columns = list(columns)
    values: dict[str, Any] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for spec in rule.params:
        value, error = _coerce(spec, supplied.pop(spec.name, None))
        if error:
            invalid.append(f"{spec.name} {error}")
            continue
        if value is None:
            value = spec.default
        if value is None and spec.is_required(columns):
            missing.append(spec.name)
        values[spec.name] = value
    warnings = []
    if supplied:
        warnings.append(f"Ignored unknown parameter(s): {', '.join(sorted(supplied))}.")
    return values, missing, invalid, warnings


def run_rule(rule: RosterRule, records: list[dict], columns: Iterable[str], params: dict | None, as_of: date) -> RosterResult:
    """Validate inputs and compute the roster. Raises RosterRunError on 422 conditions."""
    columns = list(columns)
    missing_columns = rule.missing_columns(columns)
    values, missing_params, invalid, warnings = resolve_params(rule, params, columns)

    if missing_columns or missing_params or invalid:
        parts = []
        if missing_columns:
            parts.append(f"Roster is missing required column(s): {', '.join(missing_columns)}.")
        if missing_params:
            cited = sorted({s.citation for s in rule.params if s.name in missing_params and s.citation})
            note = f" ({'; '.join(cited)})" if cited else ""
            parts.append(
                f"Missing required parameter(s): {', '.join(missing_params)}. These have no default because "
                f"they are regulatory values{note}; supply them explicitly."
            )
        if invalid:
            parts.append(f"Invalid parameter value(s): {'; '.join(invalid)}.")
        raise RosterRunError(
            " ".join(parts),
            missing_columns=missing_columns,
            missing_params=missing_params,
            invalid_params=[m.split(" ", 1)[0] for m in invalid],
        )

    ctx = RuleContext(as_of=as_of, params=values, columns=set(columns), warnings=warnings)
    rows = rule.compute(records, ctx)
    rows.sort(key=lambda r: (r["_sort"], r.get("full_name", "").upper()))
    for row in rows:
        row.pop("_sort", None)

    optional_missing = [c for c in rule.optional_columns if c not in set(columns)]
    # Unit can come from either source; don't nag if one is present.
    if any(c in columns for c in _UNIT_SOURCES):
        optional_missing = [c for c in optional_missing if c not in _UNIT_SOURCES]

    return RosterResult(
        rule=rule,
        as_of=as_of,
        params=values,
        columns=rule.output_columns(columns),
        rows=rows,
        warnings=ctx.warnings,
        missing_columns=optional_missing,
    )
