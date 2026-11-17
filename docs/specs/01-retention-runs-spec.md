# Spec 1 — DOS/Reenlistment, DEROS Option, RE Code Management rosters (owner's text, verbatim)

Add three new roster runs, separate from the MEL runs, so a CSS can catch
reenlistment and DEROS actions before they go late. Do not change MEL logic.

SCOPE: enlisted only. Use the existing officer/enlisted split and drop
officers from all three runs.

RUN 1: DOS / REENLISTMENT DECISION ROSTER
- Flag every enlisted member whose DOS is within DOS_WINDOW_MONTHS
  (default 12) of the run date. Show months remaining and an
  "action by" date of DOS minus 120 days (reenlistment must be
  projected with the MPF by then or the member is projected for
  separation). Sort soonest first. DOS already past goes in a
  "DOS expired, verify" bucket.
- Give each member a status: ELIGIBLE, ELIGIBLE - NOT YET SRP
  CONSIDERED, INELIGIBLE - WAIVABLE, INELIGIBLE, HYT/RETIREMENT, or
  REVIEW, with every reason listed.
- RE code check (DAFI 36-2606 Tables 5.2-5.5). Put the full map in
  constants.py:
  1-series eligible: 1A waived, 1J selected/elects separation, 1K, 1M
  not yet SRP considered, 1P, 1Q, 1R first-term selected.
  2-series barred: 2A AFPC denied, 2B, 2C, 2D, 2E, 2F, 2G drug ADAPT,
  2H alcohol ADAPT, 2I non-citizen initial enlistment, 2J under
  investigation, 2K notified of involuntary separation, 2L charges
  pending, 2M serving court-martial sentence, 2N, 2P AWOL/deserter,
  2Q medical, 2R/2S age 62, 2T/2U within 23 months of HYT, 2V
  retirement applied/approved, 2W, 2X non-selected.
  3-series ineligible, waiver possible: 3A, 3B needs SRP
  consideration, 3C first-term not yet SRP considered, 3D refused
  PCS/TDY retainability, 3E refused training retainability, 3F, 3I
  SRP selected but no CJR, 3K, 3Q, 3S, 3V.
  4-series ineligible: 4A, 4C, 4D, 4E grade/TIG, 4F lost time 5+
  days, 4G skill level not commensurate with grade, 4H Article 15
  suspended punishment, 4I control roster, 4J fitness, 4K MEB/PEB
  pending, 4L, 4M, 4N civil conviction.
  Waivable per Table 5.6: 4F, 4K, 4N (unit CC), 4E (via AFPC).
  Any code not in the map = REVIEW, never a silent pass.
- UIF check: any UIF code = REVIEW, show the disposition date and
  whether it falls before or after DOS. A UIF blocks a CJR for
  first-termers (para 3.4.1).
- First-term check: a CJR is required to reenlist (para 3.1.1). CJR
  window is months 35-43 (4-year) or 59-67 (6-year) of the enlistment
  (Table 3.1). Flag first-termers in the window or past it without
  RE 1R.
- Extension history: use the roster's extension field if one exists.
  If not, for first-termers only, compute months from DOE to DOS:
  48 = 4-year, no extension; 49-71 = 4-year plus (n-48) months
  extended; 72 = 6-year no extension OR 4-year plus 24 (mark
  ambiguous); 73+ = extended. For anyone who has reenlisted, mark
  "extension history unknown, verify in MilPDS" because reenlistment
  terms vary. Show remaining months under the 48-month
  per-enlistment extension cap (Chapter 6).
- Extension eligibility: needs a service-directed reason (Table 6.2;
  Rule 12 PCS retainability, 13 command sponsorship, 14 overseas tour
  extension). RE 3B cannot extend.
- HYT: if DOS equals HYT, or RE is 2T/2U/2V, classify HYT/RETIREMENT,
  not a reenlistment decision. No reenlistment or extension may run
  past the month after HYT (para 5.11.11).

RUN 2: DEROS OPTION ROSTER
- Flag enlisted members within DEROS_WINDOW_MONTHS (default 12) of
  DEROS who have (a) no assignment on file, or (b) insufficient
  retainability: DOS earlier than DEROS plus
  OS_TO_CONUS_RETAINABILITY_MONTHS (default 12, verify against
  DAFI 36-2110 Table 6.4), counted month/year from the DEROS month
  (para 6.28.2).
- Flags: NO_ASSIGNMENT, INSUFFICIENT_RETAINABILITY, or both, with
  months short.
- For retainability cases, pull the Run 1 status so the roster shows
  whether the member can actually reenlist or extend to fix it, and
  how many extension months remain.
- Notes column: member must obtain or decline retainability within
  30 days of signing the DEROS Option RIP, or is involuntarily
  extended to DOS (para 6.28.4.3). Indefinite DEROS needs 8 months
  retainability (para 6.28.4.7).
- Separate buckets: indefinite/blank DEROS; DOS on or before DEROS
  (separating from overseas).

RUN 3: RE CODE MANAGEMENT ROSTER (on demand, no date window)
- Every enlisted member whose RE code starts with a prefix in
  RE_REVIEW_PREFIXES (default ["2","4"]). Show code, definition,
  waivable and waiver authority, DOS, months to DOS, UIF. Sort by
  DOS. This is the commander's management review list.

SHARED REQUIREMENTS
- Each run gets its own endpoint and its own button/page, all working
  off the same uploaded alpha roster session.
- Run date defaults to today, with an as-of date override.
- Output: on-screen table filterable by PASCODE, plus PDF and Excel
  export in the existing PDF style. Dates in DD-MMM-YYYY.
- No database and no PII written to disk or logs. Same session and
  encryption handling as MEL. Serialize datetimes before Redis.
- All windows, thresholds and code maps live in constants.py, each
  with its DAFI paragraph/table in a comment.
- Missing or unparseable dates go in a DATA ISSUE bucket, never
  dropped.
- Footer on every output: "Screening aid only. MPF and commander
  determine eligibility per DAFI 36-2606 and DAFI 36-2110."
- pytest suite using a synthetic roster (no real PII) covering:
  4-year and 6-year first-termers with and without extensions, the
  72-month ambiguous case, career airman with DOS = HYT, each RE
  series, unknown RE code, UIF with disposition before and after
  DOS, DEROS with and without assignment, retainability short by
  1 month, indefinite DEROS, blank dates, officers excluded.
- When done, summarize what you built, every assumption, and every
  rule I should verify against the current DAFIs.
