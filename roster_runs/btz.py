"""
Run 4: SrA Below-the-Zone (BTZ) Quarterly Eligibility Roster.

Pure functions. Scope: RegAF A1C only. Numbers from config/retention.py
(AFI 36-2502, 2 Jul 2026, paras 2.2-2.4 and Table 2.7).

Quota eligibles are counted on TIG/TIS only (quality flags are remarks and
never remove anyone from the count). Previously considered (GSR 5Q) members
are excluded from the count and listed separately. Missing/unreadable DOR or
TAFMSD go in the DATA ISSUE bucket.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from board_filter import pafsc_check
from config.retention import (
    BTZ_BOARD_OFFSET_MONTHS, BTZ_CBB_MAX_POOL_FOR_ONE_QUOTA, BTZ_CBB_MIN_POOL_FOR_ONE_QUOTA,
    BTZ_CBB_POLICY_NOTE, BTZ_COMBINE_WITH_LARGE_NOTE, BTZ_QUOTA_COUNT_NOTE, BTZ_QUOTA_DECIMALS, BTZ_ROUNDING_NOTE,
    BTZ_SINGLE_ELIGIBLE_NOTE,
    BTZ_CONTROL_ROSTER_RE, BTZ_DATE_CITATION, BTZ_FOOTER, BTZ_GSR_STANDING_NOTE,
    BTZ_LARGE_UNIT_THRESHOLD, BTZ_MIN_SKILL_LEVEL, BTZ_MONTHS_EARLY, BTZ_PCS_CITATION,
    BTZ_PREVIOUSLY_CONSIDERED_GSR, BTZ_PRIOR_SERVICE_NOTE, BTZ_PROCESSING_OFFSETS_MONTHS,
    BTZ_QUARTER_CITATION, BTZ_QUOTA_CITATION, BTZ_QUOTA_RATE_PERCENT, BTZ_SUSPENDED_ART15_RE,
    BTZ_TIG_ONLY_MONTHS, BTZ_TIG_WITH_TIS_MONTHS, BTZ_TIS_MONTHS, CSS_DUTIES,
)

from .common import (
    Bucket, Column, Member, RunResult, add_months, build_members, display_date, uif_present,
)
from .retention import DATA_ISSUE_COLUMNS, re_lookup

SIZE_LARGE = "LARGE"
SIZE_SMALL = "SMALL"
CBB_REQUIRES_BASE_WIDE = "requires base-wide roster"

_QUARTER_PATTERNS = (
    re.compile(r"^(?P<y>\d{4})\s*-?\s*Q(?P<q>[1-4])$", re.I),
    re.compile(r"^Q(?P<q>[1-4])\s*-?\s*(?P<y>\d{4})$", re.I),
)


# =============================================================================
# Dates
# =============================================================================

def fully_qualified_date(tafmsd: date, dor: date) -> tuple[date, str]:
    """Earlier of (later of TAFMSD+36 and DOR+20) or DOR+28. Returns (date, path)."""
    tis = add_months(tafmsd, BTZ_TIS_MONTHS)
    tig_with_tis = add_months(dor, BTZ_TIG_WITH_TIS_MONTHS)
    tig_only = add_months(dor, BTZ_TIG_ONLY_MONTHS)
    combined = max(tis, tig_with_tis)
    if tig_only <= combined:
        return tig_only, f"TIG (DOR+{BTZ_TIG_ONLY_MONTHS})"
    if tis >= tig_with_tis:
        return combined, f"TIS (TAFMSD+{BTZ_TIS_MONTHS})"
    return combined, f"TIG+TIS (DOR+{BTZ_TIG_WITH_TIS_MONTHS})"


def btz_date(fq: date) -> date:
    return add_months(fq, -BTZ_MONTHS_EARLY)


# =============================================================================
# Quarters (Table 2.7) — identified by the calendar quarter of the BTZ dates
# =============================================================================

def parse_quarter(text: str) -> tuple[int, int]:
    raw = str(text or "").strip()
    for pattern in _QUARTER_PATTERNS:
        m = pattern.match(raw)
        if m:
            year = int(m.group("y"))
            if 2000 <= year <= 2100:
                return year, int(m.group("q"))
    raise ValueError("quarter must look like 2027-Q2 (calendar quarter of the BTZ dates)")


def quarter_id(year: int, q: int) -> str:
    return f"{year}-Q{q}"


def quarter_info(year: int, q: int) -> dict:
    start = date(year, 3 * q - 2, 1)
    end = _last_day(add_months(start, 2))
    processing = [add_months(start, off) for off in BTZ_PROCESSING_OFFSETS_MONTHS]
    board = add_months(start, BTZ_BOARD_OFFSET_MONTHS)
    fmt = lambda d: d.strftime("%b-%Y").upper()  # noqa: E731
    return {
        "id": quarter_id(year, q),
        "btz_date_start": start,
        "btz_date_end": end,
        "processing_months": [fmt(d) for d in processing],
        "processing_start": processing[0],
        "board_month": fmt(board),
        "label": (f"BTZ dates {start.strftime('%b').upper()}-{end.strftime('%b').upper()} {year} | process "
                  f"{'/'.join(d.strftime('%b').upper() for d in processing)} {processing[0].year} | board "
                  f"{fmt(board)}"),
    }


def _last_day(d: date) -> date:
    return add_months(d.replace(day=1), 1) - timedelta(days=1)


def _next_quarter(year: int, q: int, step: int = 1) -> tuple[int, int]:
    index = year * 4 + (q - 1) + step
    return index // 4, index % 4 + 1


def default_quarter(as_of: date) -> tuple[int, int]:
    """The cycle whose first processing month is the current month or the next one."""
    month_start = as_of.replace(day=1)
    year, q = as_of.year - 1, 1
    for _ in range(24):
        if quarter_info(year, q)["processing_start"] >= month_start:
            return year, q
        year, q = _next_quarter(year, q)
    raise RuntimeError("no BTZ quarter found")  # unreachable


def quarter_options(as_of: date) -> list[dict]:
    year, q = default_quarter(as_of)
    out = []
    for step in (-1, 0, 1, 2, 3):
        y, qq = _next_quarter(year, q, step)
        info = quarter_info(y, qq)
        out.append({"id": info["id"], "label": info["label"], "default": step == 0})
    return out


# =============================================================================
# Quotas (AFI 36-2502 paras 2.3.5-2.3.7)
# =============================================================================

def quota_for(count: int) -> float:
    """Exact 15% of the eligibles (para 2.3.5), two decimals, NOT rounded to a whole number.

    Owner decision 17 Nov 2026: AFI 36-2502 sets no rounding rule; the MPF
    determines the whole-number quota. 10 -> 1.50, 17 -> 2.55.
    """
    value = Decimal(count) * Decimal(BTZ_QUOTA_RATE_PERCENT) / Decimal(100)
    return float(value.quantize(Decimal(1).scaleb(-BTZ_QUOTA_DECIMALS)))


def _sum_quotas(values) -> float:
    total = sum((Decimal(str(v)) for v in values if v is not None), Decimal(0))
    return float(total.quantize(Decimal(1).scaleb(-BTZ_QUOTA_DECIMALS)))


def compute_quotas(unit_counts: dict[str, int], unit_names: dict[str, str], single_unit_roster: bool):
    """Return (units, cbb). Units with zero eligibles are omitted."""
    units = []
    for pas in sorted(unit_counts):
        n = unit_counts[pas]
        if n <= 0:
            continue
        large = n >= BTZ_LARGE_UNIT_THRESHOLD
        units.append({
            "pascode": pas,
            "unit": unit_names.get(pas, ""),
            "eligible_count": n,
            "size": SIZE_LARGE if large else SIZE_SMALL,
            "quota": quota_for(n) if large else None,
            "quota_display": f"{quota_for(n):.2f}" if large else "",
            "quota_note": "Own quota" if large else "Pooled into CBB",
        })
    pool_units = [u["pascode"] for u in units if u["size"] == SIZE_SMALL]
    pool = sum(u["eligible_count"] for u in units if u["size"] == SIZE_SMALL)
    any_large = any(u["size"] == SIZE_LARGE for u in units)
    base_wide = sum(u["eligible_count"] for u in units)
    if base_wide == 1:
        # para 2.3.5.4
        quota, note = None, BTZ_SINGLE_ELIGIBLE_NOTE
    elif not any_large and BTZ_CBB_MIN_POOL_FOR_ONE_QUOTA <= pool <= BTZ_CBB_MAX_POOL_FOR_ONE_QUOTA:
        # para 2.3.5.3
        quota, note = 1.0, (f"No large units and {BTZ_CBB_MIN_POOL_FOR_ONE_QUOTA}-{BTZ_CBB_MAX_POOL_FOR_ONE_QUOTA} "
                            "small-unit eligibles: one CBB quota (AFI 36-2502 para 2.3.5.3).")
    else:
        # Owner decision 17 Nov 2026: always 15% of the total pooled small-unit eligibles.
        quota = quota_for(pool)
        note = (f"{BTZ_QUOTA_RATE_PERCENT}% of {pool} pooled small-unit eligibles = {quota:.2f} (AFI 36-2502 para "
                f"2.3.5). {BTZ_ROUNDING_NOTE}")
        if any_large and pool:
            note += " " + BTZ_COMBINE_WITH_LARGE_NOTE
    cbb = {
        "pool_units": pool_units,
        "pool_total": pool,
        "quota": quota,
        "quota_display": f"{quota:.2f}" if quota is not None else "",
        "note": note,
        "requires_base_wide_roster": single_unit_roster,
        "policy_note": BTZ_CBB_POLICY_NOTE,
        "label": CBB_REQUIRES_BASE_WIDE if single_unit_roster else "",
    }
    return units, cbb


# =============================================================================
# Remarks (quality indicators from the MEL's checks — never remove anyone)
# =============================================================================

def _remarks(m: Member, processing_start: date) -> list[str]:
    out = []
    code = m.re_code
    if code == BTZ_CONTROL_ROSTER_RE:
        out.append(f"Control roster (RE {code})")
    elif code == BTZ_SUSPENDED_ART15_RE:
        out.append(f"Suspended Article 15 (RE {code})")
    elif code and not code.startswith("1"):
        info = re_lookup(code)
        out.append(f"RE {code}: {info['definition']}")

    pafsc = m.text("PAFSC")
    if not pafsc:
        out.append("PAFSC blank — verify skill level")
    else:
        ok = pafsc_check("A1C", pafsc, m.text("2AFSC") or None, m.text("3AFSC") or None,
                         m.text("4AFSC") or None)
        if ok is False:
            out.append(f"Skill level below {BTZ_MIN_SKILL_LEVEL}")

    if uif_present(m.uif_code):
        disp = m.date("UIF_DISPOSITION_DATE")
        shown = f", disposition {display_date(disp.value)}" if disp.ok else ""
        out.append(f"UIF code {m.uif_code}{shown}")

    rnltd = m.date("RNLTD")
    if rnltd.ok:
        if rnltd.value >= processing_start:
            out.append(f"Projected PCS (RNLTD {display_date(rnltd.value)}): losing unit considers "
                       f"({BTZ_PCS_CITATION})")
        else:
            out.append(f"RNLTD {display_date(rnltd.value)} is before processing — verify which unit considers")
    elif rnltd.status == "bad":
        out.append("RNLTD unreadable — verify PCS")
    elif m.text("GAINING_PAS"):
        out.append("Gaining PAS on file without RNLTD — verify PCS timing")
    return out


# =============================================================================
# Run
# =============================================================================

BTZ_COLUMNS = [
    Column("name", "Name", pdf_weight=2.2),
    Column("grade", "Grade", pdf_weight=0.6),
    Column("pascode", "PASCODE", pdf_weight=None),
    Column("unit", "Unit", pdf_weight=None),
    Column("dor", "DOR", "date", 1.0),
    Column("tafmsd", "TAFMSD", "date", 1.0),
    Column("btz_date", "BTZ date", "date", 1.0),
    Column("fully_qualified_date", "Fully qualified", "date", 1.0),
    Column("fq_path", "Qualifying path", "text", None),
    Column("unit_size", "Unit size", "text", None),
    Column("remarks", "Remarks", "list", 3.4),
]

_PERSON_COLUMNS = [
    Column("name", "Name", pdf_weight=2.2), Column("grade", "Grade", pdf_weight=0.6),
    Column("pascode", "PASCODE", pdf_weight=0.9), Column("unit", "Unit", pdf_weight=1.6),
    Column("dor", "DOR", "date", 1.0), Column("tafmsd", "TAFMSD", "date", 1.0),
    Column("btz_date", "BTZ date", "date", 1.0), Column("issues", "Note", "list", 2.6),
]


def run_btz_quarterly(records_or_members, as_of: date, params: dict, columns: set[str]) -> RunResult:
    members = records_or_members if records_or_members and isinstance(records_or_members[0], Member) \
        else build_members(records_or_members)
    year, q = params["quarter"]
    qi = quarter_info(year, q)
    start, end, processing_start = qi["btz_date_start"], qi["btz_date_end"], qi["processing_start"]
    has_gsr = "GRADE_STATUS_REASON" in columns

    data_issue = Bucket("data_issue", "DATA ISSUE",
                        "RegAF A1Cs whose DOR or TAFMSD (or PASCODE) is missing/unreadable, and records whose "
                        "grade is missing/not recognised. Never dropped.", list(DATA_ISSUE_COLUMNS))
    previously = Bucket("previously_considered", "Previously considered (GSR 5Q) — excluded",
                        "Grade status reason 5Q: previously considered for BTZ. Not counted.",
                        list(_PERSON_COLUMNS))
    non_regaf = Bucket("excluded_non_regaf", "Excluded — not RegAF (ANG/AFR indicator present)",
                       "ANG_ROLL_INDICATOR or AFR_SECTION_ID is populated. BTZ scope is RegAF A1C only.",
                       list(_PERSON_COLUMNS))

    officers = not_a1c = before = after = 0
    rows: list[dict] = []
    unit_names: dict[str, Counter] = {}
    all_pascodes = {m.pascode for m in members if m.pascode}

    for m in members:
        if m.category == "officer":
            officers += 1
            continue
        if m.category == "unknown":
            data_issue.rows.append({**m.base_row(), "issues": [
                "Grade missing" if not m.grade else f"Grade '{m.grade}' not recognised"]})
            continue
        if m.grade != "A1C":
            not_a1c += 1
            continue
        base = m.base_row()
        dor, tafmsd = m.date("DOR"), m.date("TAFMSD")
        base.update({"dor": dor.out(), "tafmsd": tafmsd.out()})
        if m.text("ANG_ROLL_INDICATOR") or m.text("AFR_SECTION_ID"):
            non_regaf.rows.append({**base, "issues": ["ANG/AFR indicator present"]})
            continue
        issues = [f"{col} {'missing' if v.status == 'blank' else 'unreadable'}"
                  for col, v in (("DOR", dor), ("TAFMSD", tafmsd)) if not v.ok]
        if issues:
            data_issue.rows.append({**base, "issues": issues})
            continue
        fq, path = fully_qualified_date(tafmsd.value, dor.value)
        bd = btz_date(fq)
        base.update({"btz_date": bd, "fully_qualified_date": fq, "fq_path": path})
        if has_gsr and m.text("GRADE_STATUS_REASON").upper() == BTZ_PREVIOUSLY_CONSIDERED_GSR:
            previously.rows.append({**base, "issues": ["GSR 5Q: previously considered"]})
            continue
        if bd < start:
            before += 1
            continue
        if bd > end:
            after += 1
            continue
        if not m.pascode:
            data_issue.rows.append({**base, "issues": ["PASCODE missing — cannot assign to a unit quota"]})
            continue
        base["remarks"] = _remarks(m, processing_start)
        rows.append(base)
        unit_names.setdefault(m.pascode, Counter())[m.unit] += 1

    counts = Counter(r["pascode"] for r in rows)
    names = {p: c.most_common(1)[0][0] for p, c in unit_names.items()}
    single_unit = len(all_pascodes) == 1
    units, cbb = compute_quotas(dict(counts), names, single_unit)
    size_by_pas = {u["pascode"]: u["size"] for u in units}
    for r in rows:
        r["unit_size"] = size_by_pas.get(r["pascode"], "")
    rows.sort(key=lambda r: (r["pascode"], r["name"].upper()))
    for b in (data_issue, previously, non_regaf):
        b.rows.sort(key=lambda r: (r["pascode"], r["name"].upper()))

    large_quota = _sum_quotas(u["quota"] for u in units if u["size"] == SIZE_LARGE)
    summary = {
        "total_records": len(members),
        "officers_excluded": officers,
        "enlisted_not_a1c": not_a1c,
        "eligibles": len(rows),
        "units_large": sum(1 for u in units if u["size"] == SIZE_LARGE),
        "units_small": sum(1 for u in units if u["size"] == SIZE_SMALL),
        "large_unit_quota_total": large_quota,
        "cbb_pool_total": cbb["pool_total"],
        "cbb_quota": cbb["quota"],
        "total_quota": _sum_quotas([large_quota, cbb["quota"]]),
        "btz_date_before_quarter": before,
        "btz_date_after_quarter": after,
        "previously_considered": len(previously.rows),
        "excluded_non_regaf": len(non_regaf.rows),
        "data_issue": len(data_issue.rows),
        "single_unit_roster": single_unit,
    }
    notes = [
        f"Quarter {qi['id']}: {qi['label']} ({BTZ_QUARTER_CITATION}).",
        f"Fully qualified SrA date = earlier of (later of TAFMSD + {BTZ_TIS_MONTHS} months and DOR + "
        f"{BTZ_TIG_WITH_TIS_MONTHS} months) or DOR + {BTZ_TIG_ONLY_MONTHS} months; BTZ date = fully qualified "
        f"date minus {BTZ_MONTHS_EARLY} months ({BTZ_DATE_CITATION}).",
        BTZ_QUOTA_COUNT_NOTE,
        f"{BTZ_LARGE_UNIT_THRESHOLD} or more eligibles = LARGE unit with its own {BTZ_QUOTA_RATE_PERCENT}% quota; "
        f"fewer = SMALL unit pooled into the Central Base Board (CBB) ({BTZ_QUOTA_CITATION}). {BTZ_ROUNDING_NOTE}",
        BTZ_CBB_POLICY_NOTE,
        BTZ_PRIOR_SERVICE_NOTE,
    ]
    if not has_gsr:
        notes.append(BTZ_GSR_STANDING_NOTE)
    if single_unit:
        notes.append("Roster covers one unit only: CBB math requires a base-wide roster.")
    warnings = []
    if "RNLTD" not in columns:
        warnings.append("Roster has no RNLTD column: projected PCS cannot be flagged.")
    if "PAFSC" not in columns:
        warnings.append("Roster has no PAFSC column: skill level cannot be checked.")

    return RunResult(
        run_id="btz-quarterly",
        title="SrA BTZ Quarterly Eligibility Roster",
        duty=[CSS_DUTIES["F1-32"]],
        as_of=as_of, params={"quarter": qi["id"]}, columns=list(BTZ_COLUMNS), rows=rows,
        buckets=[previously, non_regaf, data_issue], summary=summary, warnings=warnings, notes=notes,
        footer=BTZ_FOOTER, main_label="Quota eligibles",
        extra={
            "quarter": {k: v for k, v in qi.items() if k != "processing_start"},
            "quarter_options": quarter_options(as_of),
            "units": units,
            "cbb": cbb,
        },
    )
