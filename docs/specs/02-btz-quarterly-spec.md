# Spec 2 — SrA Below-the-Zone (BTZ) Quarterly Eligibility Roster (owner's text, verbatim)

Add a new roster run: the SrA Below-the-Zone (BTZ) Quarterly Eligibility Roster. It is
separate from the Initial/Final MEL runs. Do not change MEL logic.
(Reuse the existing large/small unit and PASCODE grouping code.)

SCOPE: RegAF A1C (E-3) only.

DATE LOGIC (AFI 36-2502, 26 Sep 2024, paras 2.2.1 and 2.3.1)
- Fully qualified SrA date = the earlier of:
  (a) the later of TAFMSD + 36 months and DOR + 20 months, or
  (b) DOR + 28 months.
- BTZ date = fully qualified date minus 6 months.
- Keep the 36/20/28/6 values in constants.py with the paragraph cited.

QUARTER ASSIGNMENT (Table 2.7)
  BTZ date Apr-Jun: process Jan/Feb, board Mar
  BTZ date Jul-Sep: process Apr/May, board Jun
  BTZ date Oct-Dec: process Jul/Aug, board Sep
  BTZ date Jan-Mar: process Oct/Nov, board Dec
- User picks the quarter; default to the cycle whose first processing
  month is current or next, with an as-of date override.

ELIGIBLES AND QUOTAS (paras 2.3.5-2.3.7)
- Quota eligibles are counted on TIG/TIS only, regardless of other
  ineligibility conditions. Count them per unit (PASCODE). Units
  cannot aggregate above unit level.
- 7 or more eligibles = LARGE UNIT, own quota of 15% of its eligibles.
- Fewer than 7 = SMALL UNIT, pooled into the Central Base Board (CBB).
  CBB quota = 15% of the pooled small-unit eligibles.
- Round 15% half-up (7-9 = 1, 10-16 = 2, 17-23 = 3, 24-29 = 4,
  30-36 = 5). Put the rate and threshold in constants.py.
- Edge rules: no large units and 2-6 small-unit eligibles = one CBB
  quota; only 1 eligible base-wide = "MPF/CC decision" note, no
  automatic quota.
- If the uploaded roster covers one unit only, show that unit's
  status and label the CBB math "requires base-wide roster".

FLAGS (do not remove anyone from the quota count)
- Quality indicators from the existing MEL checks: control roster,
  suspended Article 15, skill level below 3, UIF, RE code. Show as
  remarks.
- Previously considered: if a grade status reason column exists and
  shows 5Q, exclude and list separately.
- Projected PCS: if RNLTD is on or after the first day of the first
  processing month, mark "losing unit considers" (para 2.4.1).
- Add a standing note: A1Cs with DOR adjusted for prior service are
  not BTZ eligible; verify manually (para 2.3.4.4.2).
- Missing or unparseable DOR/TAFMSD go in a DATA ISSUE bucket, never
  dropped.

OUTPUT
- Own endpoint and own button/page, working off the same uploaded
  roster session.
- On-screen table filterable by PASCODE, plus PDF and Excel export in
  the existing PDF style. Dates DD-MMM-YYYY.
- MPF summary page: each unit, eligible count, LARGE/SMALL, quota,
  then CBB pool total and CBB quota.
- Unit pages: name, grade, DOR, TAFMSD, BTZ date, fully qualified
  date, remarks, fillable "Nominate" / "Do Not Nominate" boxes, and a
  commander signature block.
- Footer: "Screening aid only. MPF verifies eligibility and quotas
  per AFI 36-2502."
- No database, no PII on disk or in logs. Serialize datetimes before
  Redis.

TESTS (pytest, synthetic roster, no real PII)
- 36-month TIS path, 28-month TIG path, A1C at enlistment, BTZ date
  on a quarter boundary, unit of exactly 6 and exactly 7, quota
  rounding at 9/10/16/17, no-large-unit base, single eligible,
  5Q exclusion, PCS flag, blank dates, non-A1C excluded.
- When done, summarize what you built, every assumption, and every
  rule I should verify against the current AFI.
