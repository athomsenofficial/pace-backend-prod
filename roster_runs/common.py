"""
Shared, pure helpers for the roster runs: alpha-roster date parsing, member
normalisation, month arithmetic and the result container.

CUI: nothing here logs. Warnings carry counts and column names only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable

import pandas as pd
from dateutil.relativedelta import relativedelta

from config.domain import ENLISTED_RANKS, OFFICER_RANKS
from config.retention import INDEFINITE_YEAR_THRESHOLD, UIF_NONE_VALUES
from date_parsing import parse_date
from roster_rules import normalize_grade, to_text

INDEFINITE = "INDEFINITE"
DISPLAY_DATE_FORMAT = "%d-%b-%Y"  # 15-JAN-2024 after .upper()

# Officer spellings seen in exports -> config/domain OFFICER_RANKS codes
# (data normalisation only; grades are compared after spaces/dots/dashes go).
_OFFICER_ALIASES = {
    "2NDLT": "2LT", "1STLT": "1LT", "CAPT": "CPT", "LTCOL": "LTC",
    "BRIGGEN": "BG", "MAJGEN": "MG", "LTGEN": "LTG",
    "O1": "2LT", "O2": "1LT", "O3": "CPT", "O4": "MAJ", "O5": "LTC",
    "O6": "COL", "O7": "BG", "O8": "MG", "O9": "LTG", "O10": "GEN",
}

_DMY = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")
_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")


# =============================================================================
# Dates
# =============================================================================

@dataclass(frozen=True)
class DateValue:
    """A roster date cell: status is 'ok', 'blank', 'bad' or 'indefinite'."""

    status: str
    value: date | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def indefinite(self) -> bool:
        return self.status == "indefinite"

    def out(self) -> Any:
        """Row value: a date, INDEFINITE, or None."""
        if self.status == "ok":
            return self.value
        if self.status == "indefinite":
            return INDEFINITE
        return None


BLANK = DateValue("blank")
BAD = DateValue("bad")


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def _from_parts(year: int, month: int, day: int) -> DateValue:
    if year >= INDEFINITE_YEAR_THRESHOLD:
        return DateValue("indefinite")
    try:
        return DateValue("ok", date(year, month, day))
    except ValueError:
        return BAD


def parse_roster_date(raw: Any) -> DateValue:
    """Parse an alpha-roster date.

    The export uses "DD-MMM-YYYY" strings; year >= 3000 (3888 in practice)
    means indefinite. Excel dates / ISO strings (what the session stores for
    real date cells) and Excel serials are accepted too.
    """
    if _blank(raw):
        return BLANK
    if isinstance(raw, bool):
        return BAD
    if isinstance(raw, (datetime, pd.Timestamp)):
        return _from_parts(raw.year, raw.month, raw.day)
    if isinstance(raw, date):
        return _from_parts(raw.year, raw.month, raw.day)
    text = str(raw).strip()
    m = _DMY.match(text)
    if m:
        day, mon, year = int(m.group(1)), m.group(2).title(), int(m.group(3))
        if year >= INDEFINITE_YEAR_THRESHOLD:
            return DateValue("indefinite")
        try:
            return DateValue("ok", datetime.strptime(f"{day:02d}-{mon}-{year}", "%d-%b-%Y").date())
        except ValueError:
            return BAD
    m = _ISO.match(text)
    if m:
        return _from_parts(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if not isinstance(raw, (int, float)):
        years = [int(y) for y in _YEAR.findall(text)]
        if years and max(years) >= INDEFINITE_YEAR_THRESHOLD:
            return DateValue("indefinite")
    try:
        parsed = parse_date(raw)
    except Exception:
        parsed = None
    if parsed is None:
        return BAD
    return _from_parts(parsed.year, parsed.month, parsed.day)


def display_date(value: Any) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime(DISPLAY_DATE_FORMAT).upper()
    if value is None:
        return ""
    return str(value)


def add_months(d: date, months: int) -> date:
    return d + relativedelta(months=months)


def whole_months(start: date, end: date) -> int:
    """Completed calendar months from start to end (negative when end < start)."""
    if end < start:
        return -whole_months(end, start)
    delta = relativedelta(end, start)
    return delta.years * 12 + delta.months


def nearest_months(start: date, end: date) -> int:
    """Months from start to end rounded to the nearest month.

    Enlistment terms run DOE -> DOE + N years - 1 day (15-JAN-2023 ->
    14-JAN-2027 is 48 months, not 47), so term / extension math rounds.
    """
    if end < start:
        return -nearest_months(end, start)
    delta = relativedelta(end, start)
    months = delta.years * 12 + delta.months
    return months + (1 if delta.days >= 15 else 0)


def month_index(d: date) -> int:
    """Month/year count (ignores the day) — for 'counted from the month' rules."""
    return d.year * 12 + (d.month - 1)


def month_label(index: int) -> str:
    year, month0 = divmod(index, 12)
    return date(year, month0 + 1, 1).strftime("%b-%Y").upper()


# =============================================================================
# Members
# =============================================================================

def grade_category(grade: str) -> str:
    if grade in ENLISTED_RANKS:
        return "enlisted"
    if grade in OFFICER_RANKS:
        return "officer"
    return "unknown"


def _norm_grade(raw: Any) -> str:
    grade = normalize_grade(raw)
    return _OFFICER_ALIASES.get(grade, grade)


def uif_present(code: str) -> bool:
    return code not in UIF_NONE_VALUES


@dataclass
class Member:
    """One roster record, normalised. Never logged."""

    index: int
    record: dict
    name: str
    grade: str
    category: str
    pascode: str
    unit: str
    re_code: str
    uif_code: str
    _dates: dict = field(default_factory=dict)

    def date(self, column: str) -> DateValue:
        if column not in self._dates:
            self._dates[column] = parse_roster_date(self.record.get(column))
        return self._dates[column]

    def text(self, column: str) -> str:
        return to_text(self.record.get(column))

    def has(self, column: str) -> bool:
        return not _blank(self.record.get(column))

    def base_row(self) -> dict:
        return {
            "name": self.name,
            "grade": self.grade,
            "pascode": self.pascode,
            "unit": self.unit,
        }


def build_members(records: Iterable[dict]) -> list[Member]:
    members = []
    for i, rec in enumerate(records or []):
        grade = _norm_grade(rec.get("GRADE"))
        uif = to_text(rec.get("UIF_CODE")).upper()
        members.append(Member(
            index=i,
            record=rec,
            name=to_text(rec.get("FULL_NAME")),
            grade=grade,
            category=grade_category(grade),
            pascode=to_text(rec.get("ASSIGNED_PAS")).upper(),
            unit=to_text(rec.get("ASSIGNED_PAS_CLEARTEXT")),
            re_code=to_text(rec.get("REENL_ELIG_STATUS")).upper(),
            uif_code=uif,
        ))
    return members


def date_issue(member: Member, column: str) -> str | None:
    """'DOS missing' / 'DOS unreadable' when a required date is unusable."""
    value = member.date(column)
    if value.status == "blank":
        return f"{column} missing"
    if value.status == "bad":
        return f"{column} unreadable"
    return None


# =============================================================================
# Results
# =============================================================================

@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: str = "text"            # text | date | int | list | bool
    pdf_weight: float | None = 1.0  # None = XLSX/JSON only

    def to_json(self) -> dict:
        return {"key": self.key, "label": self.label, "kind": self.kind}


@dataclass
class Bucket:
    id: str
    label: str
    description: str
    columns: list[Column]
    rows: list[dict] = field(default_factory=list)
    pdf_rows: bool = True  # False: PDF shows the count only (rows in JSON/XLSX)


@dataclass
class RunResult:
    run_id: str
    title: str
    duty: list[str]
    as_of: date
    params: dict
    columns: list[Column]
    rows: list[dict]
    buckets: list[Bucket]
    summary: dict
    warnings: list[str]
    notes: list[str]
    footer: str
    extra: dict = field(default_factory=dict)
    main_label: str = "Roster"

    def all_pascodes(self) -> list[str]:
        seen = {r.get("pascode") for r in self.rows}
        for b in self.buckets:
            seen.update(r.get("pascode") for r in b.rows)
        return sorted(p for p in seen if p)

    def filter_pascodes(self, pascodes: Iterable[str] | None) -> "RunResult":
        """Restrict rows/buckets to these PASCODEs (summary math is unchanged)."""
        wanted = {p.strip().upper() for p in (pascodes or []) if p and p.strip()}
        if not wanted:
            return self
        self.rows = [r for r in self.rows if r.get("pascode") in wanted]
        for b in self.buckets:
            b.rows = [r for r in b.rows if r.get("pascode") in wanted]
        self.extra["pascode_filter"] = sorted(wanted)
        return self

    def to_json(self) -> dict:
        out = {
            "run_id": self.run_id,
            "title": self.title,
            "duty": list(self.duty),
            "as_of": self.as_of.isoformat(),
            "as_of_display": display_date(self.as_of),
            "params": json_value(self.params),
            "main_label": self.main_label,
            "columns": [c.to_json() for c in self.columns],
            "rows": [json_row(r, self.columns) for r in self.rows],
            "buckets": [
                {
                    "id": b.id,
                    "label": b.label,
                    "description": b.description,
                    "count": len(b.rows),
                    "columns": [c.to_json() for c in b.columns],
                    "rows": [json_row(r, b.columns) for r in b.rows],
                }
                for b in self.buckets
            ],
            "summary": json_value(self.summary),
            "warnings": list(self.warnings),
            "notes": list(self.notes),
            "footer": self.footer,
            "pascodes": self.all_pascodes(),
        }
        out.update(json_value(self.extra))
        return out


def json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def json_row(row: dict, columns: list[Column]) -> dict:
    keys = [c.key for c in columns]
    for extra in ("pascode", "unit", "name", "grade"):
        if extra not in keys:
            keys.append(extra)
    return {k: json_value(row.get(k)) for k in keys}
