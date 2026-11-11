"""
Eligibility-chart compliance test (TIG / DOR / TAFMSD) for ALL cycles E5-E9.

Source of truth: the official "Enlisted Promotion Eligibility Chart"
(transcribed below in CHART_ROWS). For each cycle we drive the REAL
board_filter() engine and binary-search the day at which eligibility flips,
giving the engine's ACTUAL TIG cutoff (latest passing DOR) and TAFMSD cutoff
(latest passing TAFMSD = minimum service). We then compare to the chart.

This deliberately does NOT re-implement the date math — it probes the live
engine, so a wrong formula in board_filter shows up as a FAIL here.

Run directly for the pass/fail matrix:   python test_chart_compliance.py
Run under pytest for per-case asserts:   pytest test_chart_compliance.py -q
"""
from datetime import datetime, timedelta

from board_filter import board_filter

# --- Engine driver -----------------------------------------------------------
# roster_type != 'mel' so that UIF / RE / PAFSC gates fall through to "eligible"
# and only the DATE gates (TIG=Step5, TIS=Step6, HYT=Step7, SRA-window=Step4.5)
# can make a member ineligible. That isolates TIG and TAFMSD cleanly.
ROSTER_TYPE = "probe"


def is_eligible(grade, year, dor, tafmsd):
    res = board_filter(
        grade=grade, year=year,
        date_of_rank=dor,
        uif_code=0, uif_disposition_date=None,
        tafmsd=tafmsd,
        re_status=None,
        pafsc=None, two_afsc=None, three_afsc=None, four_afsc=None,
        member_name="PROBE", roster_type=ROSTER_TYPE, logger=None,
    )
    return res.status in ("eligible", "btz")


def _bisect_last_true(predicate, lo, hi):
    """Largest date d in [lo, hi] with predicate(d) True, assuming predicate is
    True up to a point then False (monotonic). Returns (date, ok)."""
    if not predicate(lo):
        return None, "lo_not_eligible"
    if predicate(hi):
        return None, "hi_still_eligible"
    lo_o, hi_o = lo.toordinal(), hi.toordinal()
    while hi_o - lo_o > 1:
        mid = (lo_o + hi_o) // 2
        if predicate(datetime.fromordinal(mid)):
            lo_o = mid
        else:
            hi_o = mid
    return datetime.fromordinal(lo_o), "ok"


def engine_tig_cutoff(grade, year, fixed_tafmsd, near):
    pred = lambda d: is_eligible(grade, year, d, fixed_tafmsd)
    return _bisect_last_true(pred, near - timedelta(days=5 * 365), near + timedelta(days=2 * 365))


def engine_tafmsd_cutoff(grade, year, passing_dor, near):
    pred = lambda t: is_eligible(grade, year, passing_dor, t)
    return _bisect_last_true(pred, near - timedelta(days=3 * 365), near + timedelta(days=3 * 365))


# --- The official chart (transcribed, E5-E9, cycles 21-26) -------------------
def d(day, mon, yy):
    return datetime(2000 + yy, mon, day)


# Per-grade formulas (verified against legible chart cells):
#   E5 SRA: DOR 1 FEB C        / TAFMSD 1 AUG (C-2)   | tool year = C-1
#   E6 SSG: DOR 1 AUG (C-2)    / TAFMSD 1 JUL (C-4)   | tool year = C-1
#   E7 TSG: DOR 1 JUL (C-2)    / TAFMSD 1 JUL (C-7)   | tool year = C-1
#   E8 MSG: DOR 1 JUL (C-2)    / TAFMSD 1 MAR (C-10)  | tool year = C-1
#   E9 SMS: DOR 1 MAR (C-1)    / TAFMSD 1 DEC (C-13)  | tool year = C
def build_chart():
    rows = []
    for cc in range(21, 27):  # 21E* .. 26E*
        rows.append(dict(grade="SRA", board="E5", cycle=f"{cc}E5", year=2000 + cc - 1,
                         dor=d(1, 2, cc), tafmsd=d(1, 8, cc - 2)))
        rows.append(dict(grade="SSG", board="E6", cycle=f"{cc}E6", year=2000 + cc - 1,
                         dor=d(1, 8, cc - 2), tafmsd=d(1, 7, cc - 4)))
        rows.append(dict(grade="TSG", board="E7", cycle=f"{cc}E7", year=2000 + cc - 1,
                         dor=d(1, 7, cc - 2), tafmsd=d(1, 7, cc - 7)))
        rows.append(dict(grade="MSG", board="E8", cycle=f"{cc}E8", year=2000 + cc - 1,
                         dor=d(1, 7, cc - 2), tafmsd=d(1, 3, cc - 10)))
        rows.append(dict(grade="SMS", board="E9", cycle=f"{cc}E9", year=2000 + cc,
                         dor=d(1, 3, cc - 1), tafmsd=d(1, 12, cc - 13)))
    return rows


CHART_ROWS = build_chart()


def evaluate(row):
    """Return dict with engine cutoffs, chart cutoffs, deltas, pass/fail."""
    g, y = row["grade"], row["year"]
    # Find the engine's TAFMSD/TIS cutoff first, then probe TIG with a tafmsd that
    # the engine definitely accepts (just inside its TIS cutoff) so TIS/HYT can't
    # contaminate the TIG boundary search.
    taf_eng, taf_ok = engine_tafmsd_cutoff(g, y, row["dor"] - timedelta(days=365), row["tafmsd"])
    safe_tafmsd = (taf_eng - timedelta(days=30)) if taf_eng else row["tafmsd"]
    tig_eng, tig_ok = engine_tig_cutoff(g, y, safe_tafmsd, row["dor"])
    out = dict(row)
    out["tig_engine"], out["tig_status"] = tig_eng, tig_ok
    out["taf_engine"], out["taf_status"] = taf_eng, taf_ok
    out["tig_delta"] = (tig_eng - row["dor"]).days if tig_eng else None
    out["taf_delta"] = (taf_eng - row["tafmsd"]).days if taf_eng else None
    out["tig_pass"] = tig_ok == "ok" and out["tig_delta"] == 0
    out["taf_pass"] = taf_ok == "ok" and out["taf_delta"] == 0
    return out


# --- pytest entry points -----------------------------------------------------
import pytest


@pytest.mark.parametrize("row", CHART_ROWS, ids=[r["cycle"] for r in CHART_ROWS])
def test_tig_cutoff_matches_chart(row):
    r = evaluate(row)
    assert r["tig_status"] == "ok", f"{row['cycle']}: TIG probe failed ({r['tig_status']})"
    assert r["tig_delta"] == 0, (
        f"{row['cycle']} {row['grade']}: engine TIG cutoff "
        f"{r['tig_engine']:%d-%b-%Y} vs chart DOR {row['dor']:%d-%b-%Y} "
        f"(off {r['tig_delta']:+d} days)")


@pytest.mark.parametrize("row", CHART_ROWS, ids=[r["cycle"] for r in CHART_ROWS])
def test_tafmsd_cutoff_matches_chart(row):
    r = evaluate(row)
    assert r["taf_status"] == "ok", f"{row['cycle']}: TAFMSD probe failed ({r['taf_status']})"
    assert r["taf_delta"] == 0, (
        f"{row['cycle']} {row['grade']}: engine TAFMSD cutoff "
        f"{r['taf_engine']:%d-%b-%Y} vs chart {row['tafmsd']:%d-%b-%Y} "
        f"(off {r['taf_delta']:+d} days)")


# --- Standalone matrix printer ----------------------------------------------
def _fmt(dt):
    return dt.strftime("%d-%b-%Y") if dt else "   (n/a)   "


def main():
    rows = [evaluate(r) for r in CHART_ROWS]
    print("\nENLISTED PROMOTION ELIGIBILITY - ENGINE vs CHART (TIG & TAFMSD), all cycles\n")
    hdr = (f"{'Cycle':6} {'Gr':4} {'ToolYr':6} | "
           f"{'Chart DOR':12} {'Engine DOR':12} {'dTIG':6} {'TIG':4} | "
           f"{'Chart TAFMSD':12} {'Engine TAFMSD':13} {'dTAF':5} {'TAF':4}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['cycle']:6} {r['grade']:4} {r['year']:<6} | "
              f"{_fmt(r['dor']):12} {_fmt(r['tig_engine']):12} "
              f"{(str(r['tig_delta']) if r['tig_delta'] is not None else '?'):>6} "
              f"{'PASS' if r['tig_pass'] else 'FAIL':4} | "
              f"{_fmt(r['tafmsd']):12} {_fmt(r['taf_engine']):13} "
              f"{(str(r['taf_delta']) if r['taf_delta'] is not None else '?'):>5} "
              f"{'PASS' if r['taf_pass'] else 'FAIL':4}")

    # Per-board summary
    print("\nSummary by board (TIG):")
    boards = {}
    for r in rows:
        b = boards.setdefault(r["board"], {"tig": [], "taf": []})
        b["tig"].append(r["tig_delta"])
        b["taf"].append(r["taf_delta"])
    for b in ["E5", "E6", "E7", "E8", "E9"]:
        deltas = boards[b]["tig"]
        same = set(deltas)
        td = boards[b]["taf"]
        print(f"  {b}: TIG delta {sorted(same)} days, TAFMSD delta {sorted(set(td))} days "
              f"-> {'TIG OK' if same == {0} else 'TIG MISMATCH'}, "
              f"{'TAFMSD OK' if set(td) == {0} else 'TAFMSD MISMATCH'}")

    n_tig = sum(1 for r in rows if r["tig_pass"])
    n_taf = sum(1 for r in rows if r["taf_pass"])
    print(f"\nTOTAL: TIG {n_tig}/{len(rows)} pass, TAFMSD {n_taf}/{len(rows)} pass")


if __name__ == "__main__":
    main()
