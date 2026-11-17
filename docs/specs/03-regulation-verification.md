# 03 — Regulation verification of the roster runs (17 Nov 2026)

Every rule, number, code map, window and citation in `config/retention.py` and
`roster_runs/` (retention.py, btz.py, common.py) was checked against the
publications the owner supplied (PDFs in `~/Reference/Military/PACE-refs/`).
Quotes are short excerpts only; read the publication for the full text.

**Editions used**

| Short name | Publication |
|---|---|
| 36-2606 | DAFI 36-2606, Reenlistment and Extension of Enlistment, 22 May 2024, incl. Change 1 (21 May 2026) |
| 36-2110 | DAFI 36-2110, Total Force Assignments, 9 Aug 2024, incl. Change 2 (5 Mar 2026) |
| 36-2502 | **AFI** 36-2502, Enlisted Airman Promotion/Demotion Programs, 2 Jul 2026 (replaces the "DAFI 36-2502" / "AFI 36-2502, 26 Sep 2024" citations) |
| 36-2907 | DAFI 36-2907 (UIF / control roster), 14 Jan 2026 |
| 36-3203 | DAFI 36-3203, Service Retirements, 8 Jul 2025 |
| 36-2100 | DAFMAN 36-2100 (classification), 7 Jul 2026 |
| BTZ chart | Senior Airman Below The Zone Eligibility Determination Chart (current as of 04 Jun 2021) |
| CBB email | AFPC myFSS "SrA BTZ CBB" clarification, emailed 17 Nov 2026 |
| Elig chart | USAF Enlisted Promotion Eligibility Chart (file "1 Aug 26"; footer reads "Current as of 26 June 2025") |
| PSDGs | Enlisted Promotions PSDG (12 May 25); CSS PSDG (5 Dec 2025) |

`MilPDS Code Breakdown.xls` could not be parsed: the venv has no `xlrd` and no
other reader is installed. A `strings` pass over its string table confirmed the
UIF descriptions ("has UIF but not on control roster" / "UIF and is on
control roster" / "UIF under Art15/CM punishment") and RE descriptions
consistent with 36-2606. Without a parser it can't tie each text to its code,
so the file is not used as a source.

Status key: **MATCH** = code already agreed; **FIXED** = code changed in this
commit; **NOT FOUND** = publications are silent (local rule kept);
**NEEDS OWNER** = a judgment call for the owner; **OWNER DECISION 17 Nov 2026** / **OWNER: keep** = the owner's answer (also recorded in 00-decisions-and-data.md).

## Run 1 — DOS / Reenlistment Decision (36-2606)

| Rule | Implemented (after this commit) | Source | Short quote | Status |
|---|---|---|---|---|
| DOS window 12 mo | 12 months | Owner spec | — | Local preference |
| Action-by = DOS − 120 days | 120 days | 36-2606 Table 5.1 Notes 4-5; para 1.13.16 | "must project reenlistments with their servicing MPF NLT 120 days prior to their DOS or they are projected for Separation" | MATCH (citation FIXED: was "paragraph not given") |
| MPF notice 150 days | Shown in notes | 36-2606 para 1.13.16 | "no later than 150 days prior to Date of Separation" | Added (info) |
| CJR in Run 1 | **No CJR reason, column or status effect** (moved to the new `cjr-window` run) | Owner | — | **OWNER DECISION 17 Nov 2026** (was: REVIEW if in/past window without 1R) |
| CJR window | Months 32-43 (4-year) / 56-67 (6-year) — now used only by the `cjr-window` run | 36-2606 Table 3.1 | "complete 32 months, but not later than ... 43 months"; "56 months ... 67 months" | FIXED (was 35-43 / 59-67) |
| RE 1R = has CJR | 1R used as CJR proxy | 36-2606 Table 5.2 item 7; para 3.4.7.2; Table 6.2 Rule 28c | 1R = "First Term ... selected for reenlistment under the SRP"; CJR is MilPDS code "C" | **OWNER DECISION 17 Nov 2026**: CJR has no bearing on Run 1; RE 1R members are left off the `cjr-window` run |
| UIF | Run 1: any UIF code = REVIEW (no CJR effect). `cjr-window`: UIF shown for information | 36-2606 para 3.4.1 | "may not consider ... for award of a CJR if they have a UIF" | MATCH; CJR effect removed from Run 1 per **OWNER DECISION 17 Nov 2026** |
| UIF code meaning | non-blank, non-"0" = UIF | 36-2907 Table 3.2; para 1.3.7.2 | Control Roster "(INTERIM – Code 2)"; Art 15 "(INTERIM – Code 3)"; "(FINAL – Code 1)" | MATCH. "0" = none is NOT FOUND (export convention) |
| Extension cap | 48 months per enlistment | 36-2606 para 6.2.2 (and 6.6.2.1) | "limited to a maximum of 48 months per enlistment ... This cannot be waived." Involuntary extensions "do not count" | MATCH (citation FIXED: was "Chapter 6") |
| Extension reasons | Rules 12, 13, 14 + Rule 28c note | 36-2606 Table 6.2 | R12 "retainability for a CONUS or overseas PCS, PCA, or TDY"; R13 "command sponsorship"; R14 "overseas tour extension or to maintain indefinite" DEROS; R28c "obtain retainability for any reason" | Rule numbers MATCH. **FIXED**: the "needs a service-directed reason" text left out Rule 28c (personal convenience, one time) |
| RE 3B cannot extend | 3B: no extension | 36-2606 para 6.6.5 | "will not permit service members to extend while SRP reconsideration [RE code 3B] is pending" | MATCH (citation added) |
| RE 2V cannot extend | **2V (approved retirement): no extension** | 36-2606 para 6.6.5.1.1 | "approved for retirement and who hold RE code 2V may not extend ... (to include ... Rule 28c)" | **FIXED** (added) |
| Ineligible codes extend only per Table 6.2 | Note on 2/3/4-series | 36-2606 para 6.6.5.3; Tables 5.3/5.4 headings | "may only request extensions if ineligibility conditions allow for an extension in Table 6.2" | **FIXED** (added) |
| HYT limit | DOS at HYT or month after = HYT/RETIREMENT; later = REVIEW | 36-2606 para 5.11.11 (and 6.6.9) | "Under no circumstances will any reenlistment or extension exceed the month following the service members HYT or age 62" | MATCH |
| HYT RE codes 2T/2U/2V | HYT/RETIREMENT | 36-2606 Table 5.3 items 19-21 | 2T/2U "within 23 months of HYT date"; 2V "Applied for retirement or retirement has been approved" | MATCH |
| HYT tenure (E-4..E-9) | MEL compute_hyt_date (SRA 10, SSG 20, TSG 22, MSG 24, SMS 26); **CMS 30 added in the runs** | 36-3203 para 3.10 | "E-4 at 10 years ... E-5 at 20 ... E-6 at 22 ... E-7 at 24 ... E-8 at 26 ... E-9 at 30" | MATCH for SRA-SMS. **FIXED**: CMS was "not computed" |
| HYT E-1..E-3 (MEL 6/6/8) | MEL values used | — | Not in the provided publications (36-3203 defers to DAFI 36-3211) | NOT FOUND — **OWNER: keep** |
| Temporary HYT extension window (MEL: HYT dates 8 Dec 2023–30 Sep 2026 get +2 years) | Used through compute_hyt_date | — | 36-3203 para 3.10.1: "The DAF rarely extends HYT dates" (individual extensions only) | NOT FOUND — **OWNER: keep** |
| RE 1J | REVIEW | 36-2606 Table 5.2 item 2 | "Eligible to reenlist but elects separation" | Owner decision kept. The publication puts 1J in the eligible series (it is not barred), so REVIEW is a local choice that doesn't conflict with it |
| RE 1M | ELIGIBLE - NOT YET SRP CONSIDERED | 36-2606 Table 5.2 item 4 | "Second Term or Career ... not yet considered under the SRP" | MATCH |

### RE code map (36-2606 Tables 5.2-5.6)

Every placeholder ("Verify definition in DAFI 36-2606 Table 5.x") is replaced
with the table text. Each code carries its table/item citation
(`REENLISTMENT_RE_CODES[code]["citation"]`).

| Code(s) | Definition source | Old | New | Status |
|---|---|---|---|---|
| 1A, 1J, 1M, 1R | T5.2 items 1, 2, 4, 7 | spec wording | table wording | MATCH (reworded) |
| 1K, 1P, 1Q | T5.2 items 3, 5, 6 | placeholder | e.g. 1K "Career ... selected ... under the SRP and 13 months or less remain before completing 20 years TAFMS" | **FIXED** |
| 1T, 1S | T5.2 items 8, 9 (ANG/AFR) | missing (→ unknown/REVIEW) | added, eligible series | **FIXED** |
| 2B, 2C, 2D, 2E, 2F, 2N, 2W | T5.3 items 2-6, 14, 22 | placeholder | table text | **FIXED** |
| 2R / 2S | T5.3 items 17-18 | both "Age 62" | split: ≤13 / >13 months until DOS | **FIXED** |
| 2T / 2U | T5.3 items 19-20 | both "Within 23 months of HYT" | split: ≤13 / >13 months until DOS (HYT of 20+ years) | **FIXED** |
| other 2-series | T5.3 | spec wording | table wording | MATCH |
| 3A, 3F, 3K, 3Q, 3S, 3V | T5.4 items 1, 9, 11-14 | placeholder | table text | **FIXED** |
| T5.4 items 2-4 | — | — | no RE code printed in the publication (verified in PDF layout) | NOT FOUND (omitted) |
| 4A, 4C, 4D, 4L, 4M | T5.5 items 1, 2, 3, 11, 12 | placeholder | e.g. 4D "Grade is E-4, completed at least 9 years TAFMS, but fewer than 16 ... not currently selected for promotion to E-5" | **FIXED** |

**Classification and waivers**

| Item | Old | New | Source / quote | Status |
|---|---|---|---|---|
| 1-series | ELIGIBLE | ELIGIBLE | T5.2 "eligible for immediate reenlistment" | MATCH |
| 2-series | BARRED, not waivable | same | T5.3 "ineligible to reenlist"; no Table 5.6 row | MATCH |
| 3-series class | "INELIGIBLE - WAIVER POSSIBLE", waivable, authority "Verify ..." | "INELIGIBLE (prior-service enlistment waiver possible)"; **not waivable for reenlistment** | T5.4: "ineligible for immediate reenlistment ... but eligible for prior service enlistment with an approved waiver"; Table 5.6 has no 3-series row | **FIXED** (Run 1 status for 3A/3D/3E/3F/3I/3K/3Q/3S/3V: INELIGIBLE - WAIVABLE → INELIGIBLE) |
| 3B, 3C | INELIGIBLE - WAIVABLE (then REVIEW in the first fix) | **ELIGIBLE - NOT YET SRP CONSIDERED**; class "ELIGIBLE (owner decision ...)"; 3B still cannot extend (para 6.6.5); 3C may extend (para 6.6.5.2) | T5.4 items 5-6 "(Do not separate service members with this RE code.)" | **OWNER DECISION 17 Nov 2026** |
| 4F | waivable, "Unit CC" | waivable, CC/civilian director | T5.6 item 1 | **FIXED** (wording) |
| 4K | waivable, "Unit CC" | waivable, CC/civilian director; SRB AFSC: AF/A1 or SF/S1 final approval | T5.6 item 2 "AF/A1 or SF/S1 is final approval" | **FIXED** |
| 4N | waivable, "Unit CC" | waivable, CC/civilian director | T5.6 item 4 | **FIXED** (wording) |
| 4E | waivable, "AFPC" | waivable (first-termers): group/delta CC approves an **extension** via AFPC/DPPSA to meet grade/TIG; no direct reenlistment waiver | T5.6 item 6; Note 6 "are not reenlisted and will remain in RE code 4E until that condition no longer exists" | **FIXED** |
| 4G | not waivable | "Conditional": only RI 9A000-9A300 members approved for retraining/special duty (CC) | T5.6 item 5 | **FIXED** (Run 1 status stays INELIGIBLE) |
| Other 4-series | INELIGIBLE, not waivable | same | no Table 5.6 row | MATCH |
| Unknown code text | "Verify definition in DAFI 36-2606 Table 5.x" | "Code not in DAFI 36-2606 Tables 5.2-5.5 — verify in MilPDS" (REVIEW) | — | **FIXED** |

## Run 2 — DEROS Option (36-2110)

| Rule | Implemented | Source | Short quote | Status |
|---|---|---|---|---|
| DEROS window 12 mo | 12 | Owner spec | — | Local preference |
| OS→CONUS retainability | 12 months | 36-2110 Table 6.4 Rules 10-11 | "Overseas to CONUS ... 12 months" | MATCH (citation sharpened to Rules 10-11) |
| Counted from DEROS month | month/year | 36-2110 para 6.28.2 | "add the number of months retainability required to the member's DEROS (month and year only)" | MATCH |
| 30-day RIP rule | 30 calendar days or involuntarily extended to DOS | 36-2110 para 6.28.4.3 (also Table 6.5 Note 3; para 7.5.3.3.1-.2) | "within 30 calendar days of the date they sign their DEROS Option RIP"; "involuntarily extended at their overseas location until their date of separation" | MATCH (note now says "calendar days") |
| Indefinite DEROS | 8 months retainability | 36-2110 para 6.28.4.7; para 7.5.5.1.3 | "must maintain at least 8 months service retainability to keep an indefinite DEROS" | MATCH (second citation added) |
| Ineligible/declining members | not modelled | 36-2110 Table 6.4 Note 4 | under 7 months DEROS→DOS: DEROS extended to DOS; 7+ months: assignment as an exception | Info only (not implemented) |

## Run 3 — RE Code Management

| Rule | Implemented | Source | Status |
|---|---|---|---|
| Prefixes 2, 4 | default ("2", "4") | Owner spec | Local preference |
| Definitions / class / waiver | from the corrected map above, plus a new "RE source" column | 36-2606 Tables 5.2-5.6 | FIXED (see map) |

## Run 4 — SrA BTZ Quarterly (AFI 36-2502, 2 Jul 2026)

| Rule | Implemented | Source | Short quote | Status |
|---|---|---|---|---|
| Publication name/date | "AFI 36-2502 (2 Jul 2026)" everywhere | cover page | "AIR FORCE INSTRUCTION 36-2502, 2 JULY 2026" | **FIXED** (was "DAFI 36-2502 (spec cites AFI 36-2502, 26 Sep 2024)") |
| Fully qualified date | earlier of (later of TAFMSD+36, DOR+20) or DOR+28 | para 2.2.1; BTZ chart | "36 months' time-in-service and 20 months' time-in-grade or 28 months' time-in-grade whichever occurs first" | MATCH (chart rows reproduced in tests) |
| BTZ date = FQ − 6 | 6 months | para 2.3.1 | "advance to SrA six months prior to the fully qualified phase point" | MATCH |
| Quarter / processing / board | Jan/Feb→Mar for Apr-Jun, etc. | Table 2.7; BTZ chart | "January/February · March · April - June" | MATCH |
| RegAF only | A1C, ANG/AFR excluded | Chapter 2 title | "REGULAR AIR FORCE (REGAF) AIRMAN PROMOTIONS" | MATCH |
| Count on TIG/TIS only | yes | paras 2.3.4.4, 2.3.5 | "based on time-in-grade and time-in-service only, regardless of normal ineligibility conditions" | MATCH |
| Stays in count once identified | note | para 2.3.2 | "will remain for the below-the-zone quota purpose" | Added (note) |
| Quota 15% | 15% | para 2.3.5 | "15 percent of eligibles" | MATCH |
| Rounding | **none — exact 15%, two decimals** (e.g. 10 → 1.50, 17 → 2.55); note "AFI 36-2502 sets no rounding rule; the MPF determines the whole-number quota." | — | not stated | **OWNER DECISION 17 Nov 2026** (was half-up) |
| Large unit threshold | 7+ | para 2.3.5 | "Large units (seven or more eligible)" | MATCH |
| No aggregation above unit | yes | para 2.3.5.1 | "Units cannot aggregate above the unit level." | MATCH |
| No large units, 2-6 eligibles | 1 CBB quota | para 2.3.5.3 | "allowed one quota" | MATCH |
| One eligible base-wide | "MPF/CC decision" | para 2.3.5.4 | "the MPF commander will determine if a board will be held and may authorize one quota" | **FIXED** (wording: MPF commander) |
| CBB quota | **15% of the total pooled small-unit eligibles**, always (units under 7 always pool); para 2.3.5.2 combining is cited for information only | paras 2.3.5, 2.3.7 (2.3.5.2) | "Distribute central base board quotas based on 15 percent of eligibles" | **OWNER DECISION 17 Nov 2026** (the first fix's combine-at-CBB branch was removed) |
| CBB participation | note in run notes, CBB extra, PDF summary | para 2.4.2.1; CBB email (17 Nov 2026) | "require all units under the installation MPF ID (regardless of command) to nominate ... if the unit has fewer than seven eligible" | **FIXED** (added, cited) |
| Previously considered | GSR 5Q excluded | para 2.3.4 | "whose grade status reason is not 5Q, previously considered" | MATCH |
| Projected PCS | RNLTD ≥ 1st of first processing month → losing unit | paras 2.3.3, 2.4.1 | "considered by the losing unit if their report not later than date is the 1st day of the first processing month or later" | MATCH (para 2.3.3 added) |
| Prior-service DOR | not BTZ eligible; manual | para 2.3.4.4.2 | "A1C who receive an adjusted DOR due to previous service ... will not be eligible for SrA below-the-zone" | MATCH (ROTC/USAFA DOR-credit case added to note) |
| Skill level 3 | remark | Table 2.1 Rule 1, Note 4; PSDG | "Airmen only need to possess a 3-skill level for BTZ consideration" | MATCH |
| Skill level digit | 4th character (board_filter.pafsc_check) | DAFMAN 36-2100 Attachment 1 | "shown by the fourth character of an enlisted AFSC" | MATCH |
| CSS PSDG duty items | F1 3, 32, 36, 37(a), 37(b), 40; G1 1, 6-7 | CSS PSDG Tables F1/G1 | item titles as printed | MATCH (item 32 now cites AFI 36-2502) |

## Footers

| Footer | Old | New |
|---|---|---|
| Retention runs | "...per DAFI 36-2606 and DAFI 36-2110." | "...per DAFI 36-2606 (22 May 2024, Chg 1) and DAFI 36-2110 (9 Aug 2024, Chg 2)." |
| BTZ | "...per AFI 36-2502." | "...per AFI 36-2502 (2 Jul 2026)." |

`RULE_REFERENCES` (API + XLSX "Report Info", rows now labelled "Rule:")
carries the edition and paragraph for every rule, with a status note: verified,
local preference, owner decision, or not stated in the publication.

## MEL constants (config/domain.py, board_filter.py) — report only, NOT edited

Cross-check method: each Elig chart cycle (25-30 for E5-E9, 30 cycles) was
mapped to the MEL `year` input (PECD calendar year; SCOD Jan-Mar uses year+1,
as in board_filter / accounting_date_check). The MEL dates were computed from
the constants and compared field by field.

| Constant | Finding | Status |
|---|---|---|
| BOARD_DOR_CUTOFF, BOARD_TAFMSD_CUTOFF | All 30 cycles match the chart (e.g. year 2025 → 26E5 DOR 1 FEB 26 / TAFMSD 1 AUG 24; 26E6 1 AUG 24 / 1 JUL 22; 26E7 1 JUL 24 / 1 JUL 19; 26E8 1 JUL 24 / 1 MAR 16; 25E9 1 MAR 24 / 1 DEC 12) | MATCH (confirms the coordinator's spot check) |
| SCODS (SRA..SMS) | 31 Mar / 31 Jan / 30 Nov / 30 Sep / 31 Jul = chart PECDs and AFI Table 1.4 | MATCH |
| MDOS (SRA..SMS) | 1 Sep / 1 Aug / 1 Aug / 1 Apr / 1 Jan of year+1 = chart "MDOS/RET date must be on or after" for all 30 cycles | MATCH |
| TIG_MONTHS_REQUIRED (SRA..SMS) | 6/23/24/20/21 = chart and AFI Table 2.1 | MATCH |
| TAFMSD (SRA..SMS) | 3/5/8/11/14 years = chart and AFI Table 2.1 | MATCH |
| TIG_MONTHS_REQUIRED AMN = 6, A1C = 10 | Keyed by current grade (as SRA..SMS are), AFI says Amn→A1C needs 10 months (para 2.1.1: "An Amn is fully qualified for promotion to A1C at ten months' time-in-grade") and A1C→SrA needs 20/28 months (para 2.2.1). Only the legacy AB/AMN/A1C path in board_filter / eligibility_calculators uses them | CONFLICT (low impact) — **OWNER: keep** (do not touch) |
| TAFMSD AB 0.25, AMN 0.5, A1C 1.25 yrs | AFI sets no TIS for AB→Amn or Amn→A1C; A1C→SrA uses 36 months TIS (para 2.2.1) | CONFLICT / NOT FOUND — **OWNER: keep** (do not touch) |
| TIG dict (selection-month anchors) | Not a publication value. Used only by the legacy non-board path | NOT FOUND |
| PAFSC_MAP | A1C 3, SRA 5, SSG 7, TSG 7, MSG 7, SMS 9 = AFI Table 2.1 skill levels for the next grade | MATCH |
| MAIN_HIGHER_TENURE SRA..SMS | 10/20/22/24/26 = 36-3203 para 3.10 | MATCH. CMS (30) is absent; no MEL impact |
| MAIN_HIGHER_TENURE AB/AMN 6, A1C 8 | not in the provided publications | NOT FOUND — **OWNER: keep** |
| EXCEPTION_HIGHER_TENURE (+2 years, HYT dates 8 Dec 2023–30 Sep 2026) | 36-3203 (8 Jul 2025) has no such program, only individual extensions (para 3.10.1). The window is now closed, but members whose base HYT fell inside it still get +2 years | NOT FOUND — **OWNER: keep** |
| RE_CODES (17 MEL codes) | Short labels agree with 36-2606 Tables 5.3/5.5 (e.g. 4H "Article 15." = "Serving suspended punishment pursuant to Article 15") | MATCH (abbreviated) |
| UIF rule in MEL (codes > 1 are an issue) | AFI Table 1.2 makes control roster (code 2) and a suspended Art 15 reduction ineligibility conditions; a UIF alone (code 1) is not | MATCH |
| board_filter.py line 234 `btz_pin = DOR + 22 months` (and `btz_eligibility_check`, line 64) | AFI paras 2.2.1/2.3.1: BTZ = FQ − 6 with FQ = min(DOR+28, max(TAFMSD+36, DOR+20)), i.e. BTZ = min(DOR+22, max(TAFMSD+30, DOR+14)). The MEL ignores the TIS path, so AB/Amn entrants reach BTZ earlier than the MEL projects. Example: TAFMSD 1 Jan 2024, DOR 1 Mar 2025 → FQ 1 Jan 2027, BTZ 1 Jul 2026; the MEL projects 1 Jan 2027 | **OWNER: keep** — DOR+22 is correct for the MEL (separate process) |
| Elig chart document date | The filename says "1 Aug 26" but the footer reads "Current as of 26 June 2025". Cycles 25-30 are listed | Info |

## Owner decisions (17 Nov 2026)

1. **3B / 3C** are ELIGIBLE: Run 1 status "ELIGIBLE - NOT YET SRP CONSIDERED"
   (awaiting SRP consideration). "RE 3B cannot extend" stays. Run 3 unchanged.
2. **CJR** has no bearing on the reenlistment status. It is removed from Run 1
   and screened by the new **First-Term CJR Window** run (`cjr-window`):
   enlisted first-termers (DOE = TAFMSD), not RE 1R, IN WINDOW / PAST WINDOW /
   APPROACHING (window opens within `approaching_months`, default 3). Uses
   Table 3.1 calendar-month windows (32-43 / 56-67; ETS−DOE of 72+ checks both),
   paras 3.1.1, 3.1.2, Table 3.1 Note 3, and para 3.4.1 (UIF, for information).
3. **BTZ quota**: no rounding. Exact 15% to two decimals; the MPF sets the
   whole-number quota. Edge rules kept: paras 2.3.5.3 and 2.3.5.4.
4. **CBB quota** = 15% of the total pooled small-unit eligibles. The para
   2.3.5.2 combine computation is removed.
5. **MEL**: keep the temporary HYT window, the E1-E3 HYT values, the DOR+22 BTZ
   projection and the AMN/A1C TIG/TIS values. No MEL code changed.

## Run 5 — First-Term CJR Window (36-2606 Chapter 3)

| Rule | Implemented | Source | Short quote | Status |
|---|---|---|---|---|
| CJR required | Context note | 36-2606 para 3.1.1 | "All FTA/FTG ... must have a CJR to reenlist" | MATCH |
| Window | From the 1st day of the month the member completes 32 (56) months to the last day of the month they complete 43 (67) months | 36-2606 Table 3.1 | "first duty day of the month they complete 32 months, but not later than the last duty day of the month they complete 43 months" | MATCH |
| Only in window | Past-window note | 36-2606 Table 3.1 Note 3; para 3.1.2 | "only eligible for a CJR during their CJR eligibility window" | MATCH |
| UIF | Informational column + note | 36-2606 para 3.4.1 | "may not consider ... if they have a UIF" | MATCH |
| RE 1R excluded | Not listed (counted) | 36-2606 Table 5.2 item 7 | "First Term ... selected for reenlistment under the SRP" | Owner spec |
| Approaching horizon | 3 months (param 0-12) | Owner spec | — | Local preference |
| Footer | "Screening aid only. MPF and commander determine eligibility per DAFI 36-2606." | Owner | — | Owner spec |
