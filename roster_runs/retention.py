"""
Runs 1-3: DOS / Reenlistment Decision, DEROS Option, RE Code Management.

Pure functions over canonicalised alpha-roster records (see common.py). Every
number comes from config/retention.py. Every enlisted member is accounted
for: a main row, a bucket row, or a summary count (outside the window).
Officers are excluded and counted. Records whose grade is blank or not
recognised go in the DATA ISSUE bucket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from config.domain import MAIN_HIGHER_TENURE
from config.retention import (
    CSS_DUTIES,
    DEROS_FLAG_INSUFFICIENT_RETAINABILITY, DEROS_FLAG_NO_ASSIGNMENT, DEROS_RIP_NOTE,
    EXTENSION_CAP_MONTHS, EXTENSION_REASON_NOTE, FOUR_YEAR_TERM_MONTHS, HYT_LIMIT_CITATION,
    HYT_RE_CODES, HYT_TENURE_CITATION, HYT_YEARS_NOT_IN_MEL, INDEFINITE_DEROS_NOTE,
    INDEFINITE_DEROS_RETAINABILITY_MONTHS, INELIGIBLE_EXTENSION_NOTE,
    NOT_YET_SRP_CONSIDERED_RE_CODES, OS_TO_CONUS_RETAINABILITY_CITATION, RE_CLASS_BARRED,
    RE_CLASS_ELIGIBLE, RE_CODES_CANNOT_EXTEND, RE_DEFINITION_UNKNOWN, RE_TABLES_CITATION,
    REENLISTMENT_ACTION_CITATION, REENLISTMENT_ACTION_DAYS_BEFORE_DOS, REENLISTMENT_NOTIFY_DAYS_BEFORE_DOS,
    REENLISTMENT_RE_CODES, RETENTION_FOOTER, REVIEW_RE_CODES, SIX_YEAR_TERM_MONTHS, OWNER_ELIGIBLE_RE_CODES,
    STATUS_ELIGIBLE, STATUS_ELIGIBLE_NYSC, STATUS_HYT, STATUS_INELIGIBLE, STATUS_INELIGIBLE_WAIVABLE,
    STATUS_PRECEDENCE, STATUS_REVIEW,
)
from eligibility_calculators import compute_hyt_date

from .common import (
    INDEFINITE, Bucket, Column, Member, RunResult, add_months, date_issue, display_date,
    month_index, month_label, nearest_months, uif_present, whole_months,
)

INFO = "INFO"  # reason level that never changes the status


# =============================================================================
# RE code lookup
# =============================================================================

def re_lookup(code: str) -> dict:
    """Map entry for an RE code, or a REVIEW placeholder for unknown/blank codes."""
    if code and code in REENLISTMENT_RE_CODES:
        return dict(REENLISTMENT_RE_CODES[code], code=code, known=True)
    return {
        "code": code,
        "known": False,
        "series": code[:1] if code else "",
        "definition": RE_DEFINITION_UNKNOWN if code else "No RE code on roster",
        "eligibility_class": "UNKNOWN — REVIEW" if code else "",
        "waivable": None,
        "waiver_authority": "",
        "citation": RE_TABLES_CITATION if code else "",
    }


def _yes_no(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if isinstance(value, str):
        return value  # e.g. "Conditional"
    return ""


# =============================================================================
# Term / extension / HYT analysis (shared by Runs 1 and 2; CJR has its own run, cjr.py)
# =============================================================================

@dataclass
class Assessment:
    reasons: list[tuple[str, str]] = field(default_factory=list)
    fields: dict = field(default_factory=dict)

    def add(self, level: str, text: str) -> None:
        self.reasons.append((level, text))

    @property
    def status(self) -> str:
        levels = {lvl for lvl, _ in self.reasons}
        for status in STATUS_PRECEDENCE:
            if status in levels:
                return status
        return STATUS_REVIEW  # nothing decisive found: a human looks

    def reason_texts(self) -> list[str]:
        return [text for _, text in self.reasons]


def _remaining_text(lo, hi) -> str:
    if lo is not None and hi is not None:
        return str(hi) if lo == hi else f"{lo}-{hi}"
    if hi is not None:
        return f"<= {hi} (verify)"
    return "Unknown (verify)"


def _analyze_term(m: Member, as_of: date, a: Assessment) -> None:
    doe, tafmsd, ets, dos = m.date("DOE"), m.date("TAFMSD"), m.date("ETS"), m.date("DOS")
    cap = EXTENSION_CAP_MONTHS
    f = a.fields

    # --- first-term (owner fallback: DOE == TAFMSD = no prior service, never reenlisted)
    if doe.ok and tafmsd.ok:
        first_term = doe.value == tafmsd.value
    else:
        first_term = None
        missing = [c for c in ("DOE", "TAFMSD") if not m.date(c).ok]
        a.add(INFO, f"DATA ISSUE: {'/'.join(missing)} missing or unreadable — first-term status unknown")
    f["first_term"] = {True: "Yes", False: "No", None: "Unknown"}[first_term]

    # --- pending (not yet effective) extension = ETS -> DOS (owner, authoritative)
    pending = None
    if ets.ok and dos.ok:
        if dos.value > ets.value:
            pending = nearest_months(ets.value, dos.value)
        else:
            pending = 0
            if dos.value < ets.value:
                a.add(STATUS_REVIEW, "DOS is earlier than ETS — verify DOS/ETS in MilPDS")
    elif ets.status in ("blank", "bad") and m.category == "enlisted":
        a.add(INFO, f"DATA ISSUE: ETS {'missing' if ets.status == 'blank' else 'unreadable'} — "
                    "extension estimated from DOE->DOS (first-termers only)")
    f["pending_extension_months"] = pending

    term_label, candidates, history, basis = "", [], "", ""
    used_lo = used_hi = None  # extension months used this enlistment (effective + pending)

    if first_term:
        if ets.ok and doe.ok:
            basis = "ETS vs DOS"
            n = nearest_months(doe.value, ets.value)
            if n == FOUR_YEAR_TERM_MONTHS:
                term_label, candidates = "4-year", [FOUR_YEAR_TERM_MONTHS]
                history = "No effective extensions (ETS-DOE = 48 months)"
                used_lo = used_hi = pending
            elif n == SIX_YEAR_TERM_MONTHS:
                term_label = "AMBIGUOUS: 6-year, or 4-year + 24 months extended"
                candidates = [FOUR_YEAR_TERM_MONTHS, SIX_YEAR_TERM_MONTHS]
                history = "Effective extensions 0 or 24 months (ETS-DOE = 72, ambiguous) — verify in MilPDS"
                if pending is not None:
                    used_lo, used_hi = pending, pending + 24
            elif FOUR_YEAR_TERM_MONTHS < n < SIX_YEAR_TERM_MONTHS:
                term_label, candidates = "4-year", [FOUR_YEAR_TERM_MONTHS]
                history = f"Effective extensions unknown (ETS-DOE = {n} months) — verify in MilPDS"
                used_lo = pending
            else:
                term_label = f"Unknown (ETS-DOE = {n} months)"
                history = f"Effective extensions unknown (ETS-DOE = {n} months) — verify in MilPDS"
                used_lo = pending
        elif doe.ok and dos.ok:
            basis = "DOE->DOS heuristic (ETS blank)"
            n = nearest_months(doe.value, dos.value)
            if n == FOUR_YEAR_TERM_MONTHS:
                term_label, candidates, history = "4-year", [FOUR_YEAR_TERM_MONTHS], "4-year, no extension"
                used_lo = used_hi = 0
            elif FOUR_YEAR_TERM_MONTHS < n < SIX_YEAR_TERM_MONTHS:
                ext = n - FOUR_YEAR_TERM_MONTHS
                term_label, candidates = "4-year", [FOUR_YEAR_TERM_MONTHS]
                history = f"4-year plus {ext} months extended"
                used_lo = used_hi = ext
            elif n == SIX_YEAR_TERM_MONTHS:
                term_label = "AMBIGUOUS: 6-year, or 4-year + 24 months extended"
                candidates = [FOUR_YEAR_TERM_MONTHS, SIX_YEAR_TERM_MONTHS]
                history = "6-year no extension OR 4-year plus 24 (ambiguous)"
                used_lo, used_hi = 0, 24
            elif n > SIX_YEAR_TERM_MONTHS:
                term_label = f"Extended (DOE->DOS = {n} months; term unknown)"
                history = f"Extended: 6-year + {n - 72} or 4-year + {n - 48} months — verify in MilPDS"
                used_lo, used_hi = n - SIX_YEAR_TERM_MONTHS, n - FOUR_YEAR_TERM_MONTHS
            else:
                term_label = f"Unknown (DOE->DOS = {n} months)"
                history = "Extension history unknown, verify in MilPDS"
        else:
            term_label = "Unknown (dates missing)"
            history = "Extension history unknown, verify in MilPDS"
    else:
        basis = "ETS vs DOS" if pending is not None else ""
        term_label = ("Reenlisted/prior service — verify in MilPDS" if first_term is False
                      else "Unknown (DOE/TAFMSD missing)")
        history = "Extension history unknown, verify in MilPDS"
        used_lo = pending

    rem_lo = max(cap - used_hi, 0) if used_hi is not None else None
    rem_hi = max(cap - used_lo, 0) if used_lo is not None else None
    f.update({
        "term": term_label,
        "extension_basis": basis,
        "extension_history": history,
        "extension_remaining_min": rem_lo,
        "extension_remaining_max": rem_hi,
        "extension_remaining": _remaining_text(rem_lo, rem_hi),
    })

    # --- extension eligibility
    if m.re_code in RE_CODES_CANNOT_EXTEND:
        f["extension_note"] = f"RE {m.re_code}: {RE_CODES_CANNOT_EXTEND[m.re_code]}."
    elif rem_hi == 0:
        f["extension_note"] = f"{cap}-month extension cap reached (cannot be waived, DAFI 36-2606 para 6.2.2)."
    elif m.re_code[:1] in ("2", "3", "4") and m.re_code not in OWNER_ELIGIBLE_RE_CODES:
        f["extension_note"] = INELIGIBLE_EXTENSION_NOTE
    else:
        f["extension_note"] = EXTENSION_REASON_NOTE


    # --- HYT (computed from TAFMSD + grade; compute_hyt_date is the MEL's own calc)
    hyt = None
    if tafmsd.ok and MAIN_HIGHER_TENURE.get(m.grade) is not None:
        t = tafmsd.value
        hyt = compute_hyt_date(datetime(t.year, t.month, t.day), m.grade).date()
        f["hyt_date"] = hyt
        f["hyt_basis"] = "computed"
    elif tafmsd.ok and m.grade in HYT_YEARS_NOT_IN_MEL:
        hyt = add_months(tafmsd.value, 12 * HYT_YEARS_NOT_IN_MEL[m.grade])
        f["hyt_date"] = hyt
        f["hyt_basis"] = f"computed ({HYT_YEARS_NOT_IN_MEL[m.grade]} years, {HYT_TENURE_CITATION})"
    else:
        f["hyt_date"] = None
        f["hyt_basis"] = ("not computed (no TAFMSD)" if not tafmsd.ok
                          else f"not computed (no HYT value in PACE for {m.grade or 'blank grade'})")
    if hyt and dos.ok:
        months_past = month_index(dos.value) - month_index(hyt)
        if months_past in (0, 1):
            a.add(STATUS_HYT, f"DOS at HYT (computed HYT {display_date(hyt)}) — not a reenlistment decision")
        elif months_past > 1:
            a.add(STATUS_REVIEW,
                  f"DOS runs past the month after computed HYT {display_date(hyt)} ({HYT_LIMIT_CITATION}) — verify")


def assess_reenlistment(m: Member, as_of: date) -> Assessment:
    """Run 1 status + every reason for one enlisted member (window-independent)."""
    a = Assessment()
    info = re_lookup(m.re_code)
    f = a.fields
    f.update({
        "re_code": m.re_code,
        "re_definition": info["definition"],
        "re_class": info["eligibility_class"],
        "re_waivable": _yes_no(info["waivable"]),
        "re_waiver_authority": info["waiver_authority"],
    })

    # --- RE code (DAFI 36-2606 Tables 5.2-5.6)
    f["re_citation"] = info.get("citation", "")
    code = m.re_code
    if not code:
        a.add(STATUS_REVIEW, "No RE code on roster — verify in MilPDS")
    elif not info["known"]:
        a.add(STATUS_REVIEW, f"RE {code}: {RE_DEFINITION_UNKNOWN}")
    elif code in HYT_RE_CODES:
        a.add(STATUS_HYT, f"RE {code}: {info['definition']}")
    elif code in REVIEW_RE_CODES:
        a.add(STATUS_REVIEW, f"RE {code}: {REVIEW_RE_CODES[code]}")
    elif code in NOT_YET_SRP_CONSIDERED_RE_CODES:
        a.add(STATUS_ELIGIBLE_NYSC, f"RE {code}: {info['definition']}")
    elif info["eligibility_class"] == RE_CLASS_ELIGIBLE:
        a.add(STATUS_ELIGIBLE, f"RE {code}: {info['definition']}")
    elif info["eligibility_class"] == RE_CLASS_BARRED:
        a.add(STATUS_INELIGIBLE, f"RE {code}: {info['definition']} (barred)")
    elif info["waivable"] is True:
        a.add(STATUS_INELIGIBLE_WAIVABLE,
              f"RE {code}: {info['definition']} — waivable: {info['waiver_authority']}")
    else:
        a.add(STATUS_INELIGIBLE, f"RE {code}: {info['definition']} — {info['waiver_authority']}")

    _analyze_term(m, as_of, a)

    # --- UIF: any code = REVIEW; show disposition vs DOS (CJR effect: owner decision, none in Run 1)
    dos = m.date("DOS")
    disp = m.date("UIF_DISPOSITION_DATE")
    f["uif_code"] = m.uif_code if uif_present(m.uif_code) else ""
    f["uif_disposition_date"] = disp.out()
    f["uif_vs_dos"] = ""
    if uif_present(m.uif_code):
        if disp.ok and dos.ok:
            rel = "before DOS" if disp.value < dos.value else "on/after DOS"
        elif disp.ok and dos.indefinite:
            rel = "before DOS (DOS indefinite)"
        elif disp.status in ("bad", "blank"):
            rel = "disposition date not on roster" if disp.status == "blank" else "disposition date unreadable"
        else:
            rel = "DOS unknown"
        f["uif_vs_dos"] = rel
        shown = display_date(disp.value) if disp.ok else "n/a"
        a.add(STATUS_REVIEW, f"UIF code {m.uif_code}, disposition {shown} ({rel})")

    f["status"] = a.status
    f["reasons"] = a.reason_texts()
    return a


# =============================================================================
# Shared column sets / helpers
# =============================================================================

COL_NAME = Column("name", "Name", pdf_weight=2.0)
COL_GRADE = Column("grade", "Grade", pdf_weight=0.6)
COL_PAS = Column("pascode", "PASCODE", pdf_weight=0.9)
COL_UNIT = Column("unit", "Unit", pdf_weight=None)
COL_ISSUE = Column("issues", "Issue", "list", pdf_weight=3.0)

DATA_ISSUE_COLUMNS = [COL_NAME, COL_GRADE, COL_PAS, Column("unit", "Unit", pdf_weight=1.6), COL_ISSUE]


def _data_issue_bucket(description: str) -> Bucket:
    return Bucket("data_issue", "DATA ISSUE", description, list(DATA_ISSUE_COLUMNS))


def _issue_row(m: Member, issues: list[str]) -> dict:
    row = m.base_row()
    row["issues"] = issues
    return row


def _split_population(members: list[Member]):
    """(enlisted, officer_count, unknown_grade_members)."""
    enlisted, unknown, officers = [], [], 0
    for m in members:
        if m.category == "enlisted":
            enlisted.append(m)
        elif m.category == "officer":
            officers += 1
        else:
            unknown.append(m)
    return enlisted, officers, unknown


def _unknown_grade_issue(m: Member) -> list[str]:
    return ["Grade missing" if not m.grade else f"Grade '{m.grade}' not recognised as enlisted or officer"]


def _missing_column_warnings(columns: set[str], wanted: dict[str, str]) -> list[str]:
    return [f"Roster has no {col} column: {effect}" for col, effect in wanted.items() if col not in columns]


def _sort_key_date(value) -> tuple:
    if isinstance(value, date):
        return (0, value)
    return (1, date.max)


# =============================================================================
# RUN 1 — DOS / Reenlistment Decision Roster
# =============================================================================

RUN1_COLUMNS = [
    COL_NAME, COL_GRADE, COL_PAS, COL_UNIT,
    Column("dos", "DOS", "date", 1.0),
    Column("months_remaining", "Mos to DOS", "int", 0.6),
    Column("days_remaining", "Days to DOS", "int", None),
    Column("action_by", f"Action by (DOS-{REENLISTMENT_ACTION_DAYS_BEFORE_DOS}d)", "date", 1.0),
    Column("action_overdue", "Action overdue", "bool", None),
    Column("ets", "ETS", "date", 1.0),
    Column("pending_extension_months", "Pending ext (mos)", "int", 0.7),
    Column("re_code", "RE", "text", 0.5),
    Column("re_definition", "RE definition", "text", None),
    Column("re_class", "RE class", "text", None),
    Column("re_waivable", "Waivable", "text", None),
    Column("re_waiver_authority", "Waiver authority", "text", None),
    Column("re_citation", "RE source", "text", None),
    Column("status", "Status", "text", 1.3),
    Column("reasons", "Reasons", "list", 3.6),
    Column("first_term", "1st term", "text", 0.6),
    Column("extension_remaining", f"Ext mos left ({EXTENSION_CAP_MONTHS} cap)", "text", 0.9),
    Column("term", "Term", "text", None),
    Column("extension_history", "Extension history", "text", None),
    Column("extension_basis", "Extension basis", "text", None),
    Column("extension_note", "Extension eligibility", "text", None),
    Column("uif_code", "UIF", "text", None),
    Column("uif_disposition_date", "UIF disposition", "date", None),
    Column("uif_vs_dos", "UIF vs DOS", "text", None),
    Column("doe", "DOE", "date", None),
    Column("tafmsd", "TAFMSD", "date", None),
    Column("hyt_date", "HYT (computed)", "date", None),
    Column("hyt_basis", "HYT basis", "text", None),
]


def _run1_row(m: Member, as_of: date) -> dict:
    a = assess_reenlistment(m, as_of)
    dos = m.date("DOS")
    row = m.base_row()
    row.update(a.fields)
    row.update({
        "dos": dos.out(),
        "ets": m.date("ETS").out(),
        "doe": m.date("DOE").out(),
        "tafmsd": m.date("TAFMSD").out(),
    })
    if dos.ok:
        action_by = dos.value - timedelta(days=REENLISTMENT_ACTION_DAYS_BEFORE_DOS)
        row.update({
            "months_remaining": whole_months(as_of, dos.value),
            "days_remaining": (dos.value - as_of).days,
            "action_by": action_by,
            "action_overdue": action_by < as_of,
        })
    return row


def run_dos_reenlistment(records_or_members, as_of: date, params: dict, columns: set[str]) -> RunResult:
    from .common import build_members
    members = records_or_members if records_or_members and isinstance(records_or_members[0], Member) \
        else build_members(records_or_members)
    window = params["dos_window_months"]
    horizon = add_months(as_of, window)
    enlisted, officers, unknown = _split_population(members)

    rows: list[dict] = []
    expired = Bucket("dos_expired", "DOS expired, verify",
                     "DOS is before the as-of date. Verify the member's status in MilPDS.",
                     [c for c in RUN1_COLUMNS])
    indefinite = Bucket("indefinite_dos", "Indefinite DOS",
                        "DOS year 3888 (indefinite). No reenlistment decision is due.",
                        [COL_NAME, COL_GRADE, COL_PAS, COL_UNIT, Column("re_code", "RE", pdf_weight=0.6),
                         Column("ets", "ETS", "date", 1.0)])
    data_issue = _data_issue_bucket("Members whose DOS (or grade) is missing or unreadable. Never dropped — fix "
                                    "the roster or verify in MilPDS.")
    outside = 0

    for m in unknown:
        data_issue.rows.append(_issue_row(m, _unknown_grade_issue(m)))
    for m in enlisted:
        dos = m.date("DOS")
        issue = date_issue(m, "DOS")
        if issue:
            data_issue.rows.append(_issue_row(m, [issue]))
        elif dos.indefinite:
            row = m.base_row()
            row.update({"re_code": m.re_code, "ets": m.date("ETS").out()})
            indefinite.rows.append(row)
        elif dos.value < as_of:
            expired.rows.append(_run1_row(m, as_of))
        elif dos.value <= horizon:
            rows.append(_run1_row(m, as_of))
        else:
            outside += 1

    rows.sort(key=lambda r: (r["dos"], r["name"].upper()))
    expired.rows.sort(key=lambda r: (r["dos"], r["name"].upper()))
    for b in (indefinite, data_issue):
        b.rows.sort(key=lambda r: (r["pascode"], r["name"].upper()))

    status_counts = {s: 0 for s in STATUS_PRECEDENCE}
    for r in rows:
        status_counts[r["status"]] += 1
    elects_sep = sum(1 for r in rows + expired.rows if r.get("re_code") in REVIEW_RE_CODES)
    owner_decisions = []
    if elects_sep:
        owner_decisions.append(
            f"{elects_sep} member(s) with RE 1J are shown as REVIEW (\"member elected separation — confirm "
            "intent\"), not ELIGIBLE — owner decision 2026-11-17."
        )

    summary = {
        "total_records": len(members),
        "officers_excluded": officers,
        "enlisted": len(enlisted),
        "in_window": len(rows),
        "dos_expired": len(expired.rows),
        "indefinite_dos": len(indefinite.rows),
        "data_issue": len(data_issue.rows),
        "outside_window": outside,
        "status_counts": status_counts,
        "action_overdue": sum(1 for r in rows if r.get("action_overdue")),
        "owner_decisions": owner_decisions,
    }
    warnings = _missing_column_warnings(columns, {
        "ETS": "pending extensions estimated from DOE->DOS for first-termers only.",
        "DOE": "first-term status cannot be determined.",
        "TAFMSD": "HYT cannot be computed and first-term status is unknown.",
        "REENL_ELIG_STATUS": "every member is REVIEW (no RE code).",
        "UIF_CODE": "UIF check skipped.",
    })
    notes = [
        f"Window: DOS from {display_date(as_of)} through {display_date(horizon)} ({window} months).",
        f"Action-by date = DOS minus {REENLISTMENT_ACTION_DAYS_BEFORE_DOS} days: reenlistment must be projected "
        f"with the MPF by then or the member is projected for separation ({REENLISTMENT_ACTION_CITATION}). The MPF "
        f"notifies reenlistment-eligible members NLT {REENLISTMENT_NOTIFY_DAYS_BEFORE_DOS} days before DOS.",
        "Pending (not yet effective) extension months = ETS to DOS. ETS already includes extensions that have "
        "taken effect.",
        "First term = DOE equals TAFMSD (no prior service, never reenlisted). HYT is computed from TAFMSD and "
        f"grade ({HYT_TENURE_CITATION}; verify against MilPDS).",
        EXTENSION_REASON_NOTE,
        "RE 3B cannot extend while SRP reconsideration is pending; RE 2V with an approved retirement cannot extend "
        "(DAFI 36-2606 paras 6.6.5, 6.6.5.1.1).",
    ]
    return RunResult(
        run_id="dos-reenlistment",
        title="DOS / Reenlistment Decision Roster",
        duty=[CSS_DUTIES["F1-3"], CSS_DUTIES["F1-36"], CSS_DUTIES["G1-1"]],
        as_of=as_of, params=dict(params), columns=list(RUN1_COLUMNS), rows=rows,
        buckets=[expired, indefinite, data_issue], summary=summary, warnings=warnings, notes=notes,
        footer=RETENTION_FOOTER, main_label="DOS within window",
    )


# =============================================================================
# RUN 2 — DEROS Option Roster
# =============================================================================

def _assignment_text(m: Member) -> tuple[bool, str]:
    rnltd = m.date("RNLTD")
    gaining = m.text("GAINING_PAS")
    gaining_text = m.text("GAINING_PAS_CLEARTEXT")
    parts = []
    if m.has("RNLTD"):
        parts.append(f"RNLTD {display_date(rnltd.value)}" if rnltd.ok else "RNLTD (unreadable)")
    if gaining or gaining_text:
        parts.append(f"Gaining {gaining or ''} {gaining_text}".strip())
    return bool(parts), "; ".join(parts)


RUN2_COLUMNS = [
    COL_NAME, COL_GRADE, COL_PAS, COL_UNIT,
    Column("deros", "DEROS", "date", 1.0),
    Column("months_to_deros", "Mos to DEROS", "int", 0.6),
    Column("flags", "Flags", "list", 1.6),
    Column("assignment", "Assignment on file", "text", 1.3),
    Column("dos", "DOS", "date", 1.0),
    Column("required_dos_month", "DOS needed (month)", "text", 0.9),
    Column("months_short", "Mos short", "int", 0.5),
    Column("run1_status", "Reenl/ext status", "text", 1.2),
    Column("extension_remaining", f"Ext mos left ({EXTENSION_CAP_MONTHS} cap)", "text", 0.8),
    Column("notes", "Notes", "list", 2.6),
    Column("run1_reasons", "Reenl/ext reasons", "list", None),
    Column("ets", "ETS", "date", None),
    Column("re_code", "RE", "text", None),
]

_DEROS_SIMPLE_COLUMNS = [
    COL_NAME, COL_GRADE, COL_PAS, COL_UNIT,
    Column("deros", "DEROS", "date", 1.0),
    Column("dos", "DOS", "date", 1.0),
    Column("months_to_dos", "Mos to DOS", "int", 0.6),
    Column("assignment", "Assignment on file", "text", 1.5),
    Column("notes", "Notes", "list", 3.0),
]


def run_deros_option(records_or_members, as_of: date, params: dict, columns: set[str]) -> RunResult:
    from .common import build_members
    members = records_or_members if records_or_members and isinstance(records_or_members[0], Member) \
        else build_members(records_or_members)
    window = params["deros_window_months"]
    required = params["os_to_conus_retainability_months"]
    horizon = add_months(as_of, window)
    enlisted, officers, unknown = _split_population(members)

    rows: list[dict] = []
    separating = Bucket("separating_from_overseas", "Separating from overseas (DOS on or before DEROS)",
                        "DOS is on or before DEROS: the member separates from the overseas assignment.",
                        list(_DEROS_SIMPLE_COLUMNS))
    indefinite = Bucket("indefinite_deros", "Indefinite DEROS",
                        "DEROS year 3888 or later (indefinite). " + INDEFINITE_DEROS_NOTE,
                        list(_DEROS_SIMPLE_COLUMNS))
    blank = Bucket("blank_deros", "Blank DEROS (treated as indefinite)",
                   "No DEROS on the roster (normal for CONUS members); treated as indefinite. "
                   "The PDF shows the count only; rows are in the Excel export and on screen.",
                   list(_DEROS_SIMPLE_COLUMNS), pdf_rows=False)
    past = Bucket("deros_past", "DEROS already past, verify",
                  "DEROS is before the as-of date. Verify DEROS in MilPDS.", list(_DEROS_SIMPLE_COLUMNS))
    data_issue = _data_issue_bucket("DEROS or DOS (or grade) missing/unreadable for a member who needs the check.")
    outside = 0
    in_window_no_flags = 0

    for m in unknown:
        data_issue.rows.append(_issue_row(m, _unknown_grade_issue(m)))

    for m in enlisted:
        deros = m.date("DEROS")
        dos = m.date("DOS")
        has_asg, asg_text = _assignment_text(m)
        simple = m.base_row()
        simple.update({"deros": deros.out(), "dos": dos.out(), "assignment": asg_text, "notes": []})
        if dos.ok:
            simple["months_to_dos"] = whole_months(as_of, dos.value)

        if deros.status == "bad":
            data_issue.rows.append(_issue_row(m, ["DEROS unreadable"]))
            continue
        if deros.status in ("blank", "indefinite"):
            target = blank if deros.status == "blank" else indefinite
            notes = [INDEFINITE_DEROS_NOTE]
            if dos.ok and whole_months(as_of, dos.value) < INDEFINITE_DEROS_RETAINABILITY_MONTHS:
                notes.insert(0, f"Less than {INDEFINITE_DEROS_RETAINABILITY_MONTHS} months retainability "
                                "from the as-of date")
            elif dos.status in ("blank", "bad"):
                notes.insert(0, f"DATA ISSUE: DOS {'missing' if dos.status == 'blank' else 'unreadable'}")
            simple["notes"] = notes
            target.rows.append(simple)
            continue
        if deros.value < as_of:
            past.rows.append(simple)
            continue
        if deros.value > horizon:
            outside += 1
            continue
        # --- in window
        issue = date_issue(m, "DOS")
        if issue:
            data_issue.rows.append(_issue_row(m, [issue + " — retainability cannot be checked",
                                                  "Assignment on file" if has_asg else "No assignment on file"]))
            continue
        if dos.ok and dos.value <= deros.value:
            simple["notes"] = ["DOS on or before DEROS: separating from overseas"]
            separating.rows.append(simple)
            continue

        flags, months_short, needed_label = [], None, ""
        if not has_asg:
            flags.append(DEROS_FLAG_NO_ASSIGNMENT)
        if dos.ok:
            needed = month_index(deros.value) + required
            needed_label = month_label(needed)
            have = month_index(dos.value)
            if have < needed:
                months_short = needed - have
                flags.append(DEROS_FLAG_INSUFFICIENT_RETAINABILITY)
        if not flags:
            in_window_no_flags += 1
            continue

        row = m.base_row()
        row.update({
            "deros": deros.value,
            "months_to_deros": whole_months(as_of, deros.value),
            "flags": flags,
            "assignment": asg_text or "None on file",
            "dos": dos.out(),
            "required_dos_month": needed_label or "n/a (DOS indefinite)",
            "months_short": months_short,
            "ets": m.date("ETS").out(),
            "re_code": m.re_code,
            "notes": [],
        })
        if DEROS_FLAG_INSUFFICIENT_RETAINABILITY in flags:
            a = assess_reenlistment(m, as_of)
            row.update({
                "run1_status": a.status,
                "run1_reasons": a.reason_texts(),
                "extension_remaining": a.fields["extension_remaining"],
            })
            hi = a.fields.get("extension_remaining_max")
            lo = a.fields.get("extension_remaining_min")
            if a.fields["extension_note"] != EXTENSION_REASON_NOTE:
                row["notes"].append(a.fields["extension_note"])
            elif lo is not None and lo >= months_short:
                row["notes"].append(f"Extension room covers the {months_short}-month shortfall "
                                    "(Table 6.2 reason needed, e.g. Rule 12 PCS retainability, DAFI 36-2606).")
            elif hi is not None and hi < months_short:
                row["notes"].append(f"Extension room ({hi} mos max) is less than the shortfall — reenlistment "
                                    "needed to obtain retainability.")
            row["notes"].append(DEROS_RIP_NOTE)
        if DEROS_FLAG_NO_ASSIGNMENT in flags:
            row["notes"].append("No assignment on file (no RNLTD or gaining PAS).")
        rows.append(row)

    rows.sort(key=lambda r: (r["deros"], r["name"].upper()))
    for b in (separating, past):
        b.rows.sort(key=lambda r: (_sort_key_date(r["deros"]), r["name"].upper()))
    for b in (indefinite, blank, data_issue):
        b.rows.sort(key=lambda r: (r["pascode"], r["name"].upper()))

    summary = {
        "total_records": len(members),
        "officers_excluded": officers,
        "enlisted": len(enlisted),
        "flagged": len(rows),
        "no_assignment": sum(1 for r in rows if DEROS_FLAG_NO_ASSIGNMENT in r["flags"]),
        "insufficient_retainability": sum(1 for r in rows if DEROS_FLAG_INSUFFICIENT_RETAINABILITY in r["flags"]),
        "both_flags": sum(1 for r in rows if len(r["flags"]) == 2),
        "in_window_no_flags": in_window_no_flags,
        "separating_from_overseas": len(separating.rows),
        "indefinite_deros": len(indefinite.rows),
        "blank_deros": len(blank.rows),
        "deros_past": len(past.rows),
        "data_issue": len(data_issue.rows),
        "outside_window": outside,
    }
    warnings = _missing_column_warnings(columns, {
        "RNLTD": "assignment is detected from GAINING_PAS only.",
        "GAINING_PAS": "assignment is detected from RNLTD only.",
    })
    if "RNLTD" not in columns and "GAINING_PAS" not in columns:
        warnings.append("No RNLTD or GAINING_PAS column: every member in the window is flagged NO_ASSIGNMENT.")
    notes = [
        f"Window: DEROS from {display_date(as_of)} through {display_date(horizon)} ({window} months).",
        f"Retainability: DOS must reach the DEROS month plus {required} months, counted month/year "
        f"({OS_TO_CONUS_RETAINABILITY_CITATION}).",
        "Assignment on file = RNLTD or gaining PAS present (assignment action number is not in the export).",
        DEROS_RIP_NOTE,
        INDEFINITE_DEROS_NOTE,
    ]
    return RunResult(
        run_id="deros-option",
        title="DEROS Option Roster",
        duty=[CSS_DUTIES["F1-40"], CSS_DUTIES["G1-6-7"], CSS_DUTIES["F1-3"]],
        as_of=as_of, params=dict(params), columns=list(RUN2_COLUMNS), rows=rows,
        buckets=[separating, indefinite, blank, past, data_issue], summary=summary, warnings=warnings,
        notes=notes, footer=RETENTION_FOOTER, main_label="DEROS within window — action needed",
    )


# =============================================================================
# RUN 3 — RE Code Management Roster (no date window)
# =============================================================================

RUN3_COLUMNS = [
    COL_NAME, COL_GRADE, COL_PAS, COL_UNIT,
    Column("re_code", "RE", "text", 0.5),
    Column("re_definition", "Definition", "text", 2.4),
    Column("re_class", "Class", "text", 1.1),
    Column("re_waivable", "Waivable", "text", 0.6),
    Column("re_waiver_authority", "Waiver authority", "text", 1.5),
    Column("re_citation", "RE source", "text", None),
    Column("dos", "DOS", "date", 1.0),
    Column("months_to_dos", "Mos to DOS", "int", 0.6),
    Column("uif_code", "UIF", "text", 0.4),
    Column("uif_disposition_date", "UIF disposition", "date", 1.0),
]


def run_re_code_review(records_or_members, as_of: date, params: dict, columns: set[str]) -> RunResult:
    from .common import build_members
    members = records_or_members if records_or_members and isinstance(records_or_members[0], Member) \
        else build_members(records_or_members)
    prefixes = tuple(p.upper() for p in params["re_review_prefixes"])
    enlisted, officers, unknown = _split_population(members)

    rows: list[dict] = []
    data_issue = _data_issue_bucket("Members with a review RE code whose DOS is missing/unreadable, or whose "
                                    "grade is missing/not recognised.")
    for m in unknown:
        data_issue.rows.append(_issue_row(m, _unknown_grade_issue(m)))
    no_match = 0
    for m in enlisted:
        if not m.re_code or not m.re_code.startswith(prefixes):
            no_match += 1
            continue
        info = re_lookup(m.re_code)
        dos = m.date("DOS")
        row = m.base_row()
        disp = m.date("UIF_DISPOSITION_DATE")
        row.update({
            "re_code": m.re_code,
            "re_definition": info["definition"],
            "re_class": info["eligibility_class"],
            "re_waivable": _yes_no(info["waivable"]),
            "re_waiver_authority": info["waiver_authority"],
            "re_citation": info.get("citation", ""),
            "dos": dos.out(),
            "months_to_dos": whole_months(as_of, dos.value) if dos.ok else None,
            "uif_code": m.uif_code if uif_present(m.uif_code) else "",
            "uif_disposition_date": disp.out() if uif_present(m.uif_code) else None,
        })
        issue = date_issue(m, "DOS")
        if issue:
            row["issues"] = [f"RE {m.re_code}: {info['definition']}", issue]
            data_issue.rows.append(row)
        else:
            rows.append(row)

    rows.sort(key=lambda r: (_sort_key_date(r["dos"]), r["name"].upper()))
    data_issue.rows.sort(key=lambda r: (r["pascode"], r["name"].upper()))
    by_code: dict[str, int] = {}
    for r in rows + [r for r in data_issue.rows if r.get("re_code")]:
        by_code[r["re_code"]] = by_code.get(r["re_code"], 0) + 1
    summary = {
        "total_records": len(members),
        "officers_excluded": officers,
        "enlisted": len(enlisted),
        "listed": len(rows),
        "data_issue": len(data_issue.rows),
        "not_matching_prefixes": no_match,
        "by_code": dict(sorted(by_code.items())),
        "unknown_codes": sorted({c for c in by_code if c not in REENLISTMENT_RE_CODES}),
    }
    warnings = _missing_column_warnings(columns, {"DOS": "months to DOS cannot be shown."})
    notes = [
        f"Lists every enlisted member whose RE code starts with: {', '.join(prefixes)}. Sorted by DOS.",
        f"Definitions, classes and waiver authorities: {RE_TABLES_CITATION} and Table 5.6 (22 May 2024, Chg 1).",
        "Codes not in the publication tables show \"" + RE_DEFINITION_UNKNOWN + "\".",
    ]
    return RunResult(
        run_id="re-code-review",
        title="RE Code Management Roster",
        duty=[CSS_DUTIES["F1-36"], CSS_DUTIES["F1-37b"], CSS_DUTIES["G1-1"]],
        as_of=as_of, params={"re_review_prefixes": list(prefixes)}, columns=list(RUN3_COLUMNS), rows=rows,
        buckets=[data_issue], summary=summary, warnings=warnings, notes=notes,
        footer=RETENTION_FOOTER, main_label="Commander's management review list",
    )


__all__ = [
    "INDEFINITE", "assess_reenlistment", "re_lookup",
    "run_dos_reenlistment", "run_deros_option", "run_re_code_review",
]
