# Decisions, real data facts and references (from the owner, 2026-11-17)

Owner approved: "run the plan". Build all four runs (DOS/Reenlistment, DEROS Option,
RE Code Management, BTZ Quarterly) on the existing recurring-rosters framework
(roster_rules.py, routers/rosters.py, config/rosters.py, roster_exports.py), one
alpha-roster upload per session serving all four. Deploy target: test site only.

## Real alpha roster export (sheet "ReportOutput", 76 columns)
Header row, exactly (two blank-header columns appear as None in openpyxl):
FULL_NAME, <blank>, GRADE, RECORD_STATUS, ASSIGNED_PAS, ASSIGNED_PAS_CLEARTEXT, OFFICE_SYMBOL,
DUTY_TITLE, DUTY_START_DATE, DOR, DAFSC, CAFSC, PAFSC, 2AFSC, 3AFSC, 4AFSC,
DATE_ARRIVED_STATION, DUTY_PHONE, TAFMSD, DOE, DOS, ETS, DATE_OF_BIRTH, HOME_ADDRESS,
HOME_CITY, HOME_STATE, HOME_ZIP_CODE, SUPV_NAME, GRADE_PERM_PROJ, UIF_CODE,
UIF_DISPOSITION_DATE, PROJ_EVAL_CLOSE_DATE, MARITAL_STATUS, RNLTD, GAINING_PAS,
GAINING_PAS_CLEARTEXT, LAST_EVAL_RATING, LAST_EVAL_CLOSE_DATE, PERF_INDICATOR, <blank>,
SUPV_BEGIN_DATE, REENL_ELIG_STATUS, HOME_PHONE_NUMBER, AGE, DEROS, DEPLOY_ADMIN_STATUS,
DEPLOY_ADMIN_STATUS_CLEARTEXT, DEPLOY_ADMIN_STOP_DATE, DEPLOY_LEGAL_STATUS,
DEPLOY_LEGAL_STATUS_CLEARTEXT, DEPLOY_LEGAL_STOP_DATE, DEPLOY_PHYS_STATUS,
DEPLOY_PHYS_STATUS_CLEARTEXT, DEPLOY_PHYS_STOP_DATE, DEPLOY_TIME_STATUS,
DEPLOY_TIME_STATUS_CLEARTEXT, DEPLOY_TIME_STOP_DATE, AVAILABILITY_CODE,
AVAILABILITY_CODE_CLEARTEXT, AVAILABILITY_DATE, AVAILABILITY_STATUS,
AVAILABILITY_STATUS_CLEARTEXT, LIMITATION_CODE, LIMITATION_CODE_CLEARTEXT,
LIMITATION_END_DATE, SEC_CLR, TYPE_SEC_INV, DT_SCTY_INVES_COMPL, SEC_ELIG_DT, TECH_ID,
ACDU_STATUS, ANG_ROLL_INDICATOR, AFR_SECTION_ID, CIVILIAN_ART_ID, ATTACHED_PAS,
FUNCTIONAL_CATEGORY

Facts observed (aggregate only):
- All dates are strings "DD-MMM-YYYY" (e.g. 15-JAN-2024). Year 3888 = indefinite
  (officers' DOS; ETS/DOS of some TSG-CMS). Treat 3888 as "indefinite", never as a
  real date and never as DATA ISSUE.
- Officers (CPT, MAJ, LTC, COL, 1LT, ...) have blank DOE, ETS, REENL_ELIG_STATUS.
- RE codes seen: 1R 1P 1M 1J 3C 3B 3A 4K 4D 2U 2V 2M. UIF_CODE values like "1".
- DAFSC/CAFSC carry a leading "-" (e.g. -3F051); PAFSC does not. Enlisted skill
  level = 4th character of the 5-char AFSC (3F0[5]1); officer AFSCs are 4 chars.
- RNLTD, GAINING_PAS(_CLEARTEXT), AVAILABILITY_* exist but were empty in the sample.
- ACDU_STATUS / ANG_ROLL_INDICATOR / AFR_SECTION_ID empty: assume RegAF; if
  ANG_ROLL_INDICATOR or AFR_SECTION_ID is populated, exclude the member from BTZ.

## ETS vs DOS (owner, authoritative)
"ETS is their expiration term of service, but if a member has an extension their DOS
will not match; the day they enter the extension the ETS will flip to match."
=> pending (not yet effective) extension months = months(ETS -> DOS) when DOS > ETS.
Use this INSTEAD of the DOE->DOS heuristic where ETS is present; keep the heuristic
(48/49-71/72 ambiguous/73+) only as a fallback when ETS is blank, and only for
first-termers. Note: ETS already includes extensions that have taken effect, so
ETS - DOE may be >48 or between 48 and 72; report "effective extensions unknown"
unless ETS-DOE is exactly 48 or 72 (still ambiguous at 72).

## Missing from the export — fallbacks
- HYT date: compute with eligibility_calculators.compute_hyt_date(TAFMSD, grade); label "computed".
- Term of enlistment / category of enlistment: first-term = DOE == TAFMSD (no prior
  service, never reenlisted); otherwise "reenlisted/prior service - verify in MilPDS".
- Assignment action number: not exported. "Assignment on file" = RNLTD or GAINING_PAS present.
- Fitness: not exported; RE 4J covers it.
- Grade status reason (BTZ 5Q): not exported. Support an optional column if present
  (accept aliases GRADE_STATUS_REASON, GSR, GRADE_STATUS_RSN); otherwise add a standing
  remark "Verify not previously considered (GSR 5Q) in MilPDS".
- Indefinite DEROS representation unknown (none in sample): treat blank or year >= 3000
  as indefinite.

## Rule positions decided for the build
- RE 1J ("elects separation") -> REVIEW (not ELIGIBLE), with reason "member elected
  separation — confirm intent". Flag in the summary as a decision for the owner.
- RE codes the spec lists without a definition: definition text = "Verify definition
  in DAFI 36-2606 Table 5.x" — never invent text.
- The spec's numbers (12/120 days/48 cap/CJR 35-43 & 59-67/12 retainability/8 indefinite,
  BTZ 36/20/28/6, 15%, threshold 7) go in config with the cited paragraph AND a
  "verify against current publication" note. The promotion pub is DAFI 36-2502 per the
  CSS PSDG (5 Dec 2025); the owner's text says AFI 36-2502 (26 Sep 2024) — cite as
  "DAFI 36-2502 (spec cites AFI 36-2502, 26 Sep 2024)".

## CSS PSDG (Commanders' Support Staff Execution, Organization, and Responsibilities PSD
## Guide, 5 DEC 2025) — duties these runs support (use in page descriptions/PDF headers)
- Table F1 item 32: Manage the unit Below-the-Zone (BTZ) program — DAFI 36-2502.
- Table F1 item 36: Administer unit Selective Reenlistment Program (SRP) processing — DAFI 36-2606.
- Table F1 item 37(a): Administer unit Selective Retention Bonus (SRB) roster — DAFI 36-2606.
- Table F1 item 37(b): Monitor unit UIFs / Control Roster — DAFI 36-2907.
- Table F1 item 3: Oversight with the MPF of the unit reenlistment and extension program — DAFI 36-2606.
- Table F1 item 40: Manage unit Vulnerable to Move List (VML) — DAFI 36-2110.
- Table G1 item 1 (Section Commander): Reenlistments — DAF Forms 901, 1411, 418, 1411-1 SRP Roster — DAFI 36-2606.
- Table G1 items 6-7: PDD / RNLTD change requests — DAFI 36-2110.
