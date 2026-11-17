"""
Run 5: First-Term CJR Window Roster (DAFI 36-2606 Chapter 3, Table 3.1).

Pure functions. Lists enlisted first-termers (DOE == TAFMSD) who are inside or
past their Career Job Reservation window, or whose window opens within the
"approaching" horizon, and who are not in RE 1R. Owner decision 17 Nov 2026:
the CJR has no effect on the DOS / Reenlistment run; it is screened here.

Every enlisted member is accounted for: a main row, the DATA ISSUE bucket, or
a summary count. Officers are excluded and counted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from config.retention import (
    CJR_APPROACHING_MONTHS, CJR_FOOTER, CJR_NOTES, CJR_SELECTED_RE_CODE, CJR_STATUS_APPROACHING,
    CJR_STATUS_IN_WINDOW, CJR_STATUS_PAST_WINDOW, CJR_WINDOW_CITATION, CJR_WINDOWS_BY_TERM_MONTHS, CSS_DUTIES,
    FOUR_YEAR_TERM_MONTHS, SIX_YEAR_TERM_MONTHS,
)

from .common import (
    Bucket, Column, Member, RunResult, add_months, build_members, display_date, month_index, nearest_months,
    uif_present, whole_months,
)
from .retention import DATA_ISSUE_COLUMNS, re_lookup

TERM_4 = "4-year"
TERM_6 = "6-year"
TERM_AMBIGUOUS = "AMBIGUOUS (6-year, or 4-year extended)"

# Status precedence when an ambiguous term yields two windows.
_STATUS_ORDER = (CJR_STATUS_IN_WINDOW, CJR_STATUS_APPROACHING, CJR_STATUS_PAST_WINDOW)


@dataclass(frozen=True)
class Window:
    term_months: int
    start: date   # first day of the month the member completes `first` months
    end: date     # last day of the month the member completes `last` months

    @property
    def label(self) -> str:
        return TERM_4 if self.term_months == FOUR_YEAR_TERM_MONTHS else TERM_6


def _month_completed(doe: date, months: int) -> date:
    """The day the member completes `months` months of the enlistment (DOE + n months - 1 day)."""
    return add_months(doe, months) - timedelta(days=1)


def _last_day(d: date) -> date:
    return add_months(d.replace(day=1), 1) - timedelta(days=1)


def cjr_window(doe: date, term_months: int) -> Window:
    first, last = CJR_WINDOWS_BY_TERM_MONTHS[term_months]
    return Window(term_months, _month_completed(doe, first).replace(day=1), _last_day(_month_completed(doe, last)))


def term_from_ets(doe: date, ets: date) -> tuple[str, list[int]] | None:
    """(term label, candidate term lengths) from ETS - DOE, or None when unknown.

    48 = 4-year; 49-71 = 4-year with effective extensions; 72+ = ambiguous
    (6-year, or 4-year extended 24+ months): both windows are checked.
    """
    n = nearest_months(doe, ets)
    if n == FOUR_YEAR_TERM_MONTHS or FOUR_YEAR_TERM_MONTHS < n < SIX_YEAR_TERM_MONTHS:
        return TERM_4, [FOUR_YEAR_TERM_MONTHS]
    if n >= SIX_YEAR_TERM_MONTHS:
        return TERM_AMBIGUOUS, [FOUR_YEAR_TERM_MONTHS, SIX_YEAR_TERM_MONTHS]
    return None


def window_status(w: Window, as_of: date, approaching_months: int) -> str | None:
    if as_of > w.end:
        return CJR_STATUS_PAST_WINDOW
    if as_of >= w.start:
        return CJR_STATUS_IN_WINDOW
    if w.start <= add_months(as_of, approaching_months):
        return CJR_STATUS_APPROACHING
    return None  # window opens later than the approaching horizon


CJR_COLUMNS = [
    Column("name", "Name", pdf_weight=1.9),
    Column("grade", "Grade", pdf_weight=0.55),
    Column("pascode", "PASCODE", pdf_weight=0.85),
    Column("unit", "Unit", pdf_weight=None),
    Column("dafsc", "DAFSC", "text", 0.7),
    Column("doe", "DOE", "date", 1.0),
    Column("ets", "ETS", "date", 1.0),
    Column("dos", "DOS", "date", 1.0),
    Column("term", "Term", "text", 0.9),
    Column("month_of_enlistment", "Month of enl.", "int", 0.55),
    Column("window_start", "Window opens", "date", 1.0),
    Column("window_end", "Window closes", "date", 1.0),
    Column("months_until_close", "Mos to close", "int", 0.55),
    Column("status", "Status", "text", 1.0),
    Column("windows", "Windows checked", "text", None),
    Column("re_code", "RE", "text", 0.4),
    Column("re_definition", "RE definition", "text", 1.8),
    Column("uif_code", "UIF", "text", 0.4),
    Column("uif_disposition_date", "UIF disposition", "date", 1.0),
    Column("notes", "Notes", "list", None),
]


def run_cjr_window(records_or_members, as_of: date, params: dict, columns: set[str]) -> RunResult:
    members = records_or_members if records_or_members and isinstance(records_or_members[0], Member) \
        else build_members(records_or_members)
    approaching = params.get("approaching_months", CJR_APPROACHING_MONTHS)

    rows: list[dict] = []
    data_issue = Bucket("data_issue", "DATA ISSUE",
                        "Enlisted members whose DOE, TAFMSD, ETS or DOS is missing/unreadable/indefinite (first-term "
                        "status or term cannot be set), whose term cannot be read from ETS minus DOE, or whose grade "
                        "is missing/not recognised. Never dropped.", list(DATA_ISSUE_COLUMNS))
    officers = not_first_term = re_1r = before = 0

    for m in members:
        if m.category == "officer":
            officers += 1
            continue
        if m.category == "unknown":
            data_issue.rows.append({**m.base_row(), "issues": [
                "Grade missing" if not m.grade else f"Grade '{m.grade}' not recognised as enlisted or officer"]})
            continue
        doe, tafmsd, ets, dos = m.date("DOE"), m.date("TAFMSD"), m.date("ETS"), m.date("DOS")
        if doe.ok and tafmsd.ok and doe.value != tafmsd.value:
            not_first_term += 1
            continue
        issues = []
        for col, v in (("DOE", doe), ("TAFMSD", tafmsd), ("ETS", ets), ("DOS", dos)):
            if not v.ok:
                state = {"blank": "missing", "bad": "unreadable", "indefinite": "indefinite"}[v.status]
                issues.append(f"{col} {state}")
        if issues:
            data_issue.rows.append({**m.base_row(), "issues": issues + ["first-term CJR window cannot be checked"]})
            continue
        if m.re_code == CJR_SELECTED_RE_CODE:
            re_1r += 1
            continue
        term = term_from_ets(doe.value, ets.value)
        if term is None:
            n = nearest_months(doe.value, ets.value)
            data_issue.rows.append({**m.base_row(), "issues": [
                f"Term unknown (ETS minus DOE = {n} months) — verify enlistment term in MilPDS"]})
            continue
        term_label, candidates = term
        windows = [cjr_window(doe.value, t) for t in candidates]
        statuses = [(window_status(w, as_of, approaching), w) for w in windows]
        listed = [(st, w) for st, w in statuses if st]
        if not listed:
            before += 1
            continue
        status = next(st for st in _STATUS_ORDER if any(x == st for x, _ in listed))
        chosen = [w for st, w in listed if st == status]
        primary = max(chosen, key=lambda w: w.end) if status == CJR_STATUS_PAST_WINDOW else chosen[0]

        info = re_lookup(m.re_code)
        uif = uif_present(m.uif_code)
        disp = m.date("UIF_DISPOSITION_DATE")
        notes = []
        if uif:
            notes.append("UIF on file: a UIF bars CJR consideration (DAFI 36-2606 para 3.4.1)")
        if status == CJR_STATUS_PAST_WINDOW:
            notes.append("Window closed: no CJR outside the window (Table 3.1 Note 3); constrained AFSC — no CJR "
                         "later, separates at DOS (para 3.1.2). Verify CJR status in MilPDS.")
        if len(windows) > 1:
            notes.append("Term ambiguous (ETS minus DOE is 72+ months): both 4-year and 6-year windows checked.")
        row = m.base_row()
        row.update({
            "dafsc": m.text("DAFSC"),
            "doe": doe.value,
            "ets": ets.value,
            "dos": dos.value,
            "term": term_label,
            "month_of_enlistment": whole_months(doe.value, as_of) + 1,
            "window_start": primary.start,
            "window_end": primary.end,
            "months_until_close": month_index(primary.end) - month_index(as_of),
            "status": status,
            "windows": "; ".join(
                f"{w.label}: {display_date(w.start)} to {display_date(w.end)} ({st or 'not yet'})"
                for st, w in statuses),
            "re_code": m.re_code,
            "re_definition": info["definition"],
            "uif_code": m.uif_code if uif else "",
            "uif_disposition_date": disp.out() if uif else None,
            "notes": notes,
        })
        rows.append(row)

    rows.sort(key=lambda r: (r["window_end"], r["name"].upper()))
    data_issue.rows.sort(key=lambda r: (r["pascode"], r["name"].upper()))
    enlisted = len(members) - officers
    summary = {
        "total_records": len(members),
        "officers_excluded": officers,
        "enlisted": enlisted - sum(1 for m in members if m.category == "unknown"),
        "listed": len(rows),
        "in_window": sum(1 for r in rows if r["status"] == CJR_STATUS_IN_WINDOW),
        "past_window": sum(1 for r in rows if r["status"] == CJR_STATUS_PAST_WINDOW),
        "approaching": sum(1 for r in rows if r["status"] == CJR_STATUS_APPROACHING),
        "not_first_term_excluded": not_first_term,
        "re_1r_excluded": re_1r,
        "window_not_yet_open": before,
        "data_issue": len(data_issue.rows),
        "with_uif": sum(1 for r in rows if r["uif_code"]),
    }
    warnings = [f"Roster has no {col} column: {effect}" for col, effect in {
        "DAFSC": "DAFSC column left blank.",
        "UIF_CODE": "UIF not shown.",
        "REENL_ELIG_STATUS": f"RE {CJR_SELECTED_RE_CODE} members cannot be excluded.",
    }.items() if col not in columns]
    notes = [
        f"As of {display_date(as_of)}: first-termers in or past their CJR window, or whose window opens within "
        f"{approaching} month(s), excluding RE {CJR_SELECTED_RE_CODE} ({CJR_WINDOW_CITATION}). Sorted by window close.",
        *CJR_NOTES,
    ]
    return RunResult(
        run_id="cjr-window",
        title="First-Term CJR Window Roster",
        duty=[CSS_DUTIES["F1-36"], CSS_DUTIES["F1-3"]],
        as_of=as_of, params={"approaching_months": approaching}, columns=list(CJR_COLUMNS), rows=rows,
        buckets=[data_issue], summary=summary, warnings=warnings, notes=notes, footer=CJR_FOOTER,
        main_label="First-termers in / past / approaching the CJR window",
    )


__all__ = ["run_cjr_window", "cjr_window", "term_from_ets", "window_status"]
