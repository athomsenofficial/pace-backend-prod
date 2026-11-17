"""
Retention and BTZ roster runs (DOS/Reenlistment, DEROS Option, RE Code
Management, SrA BTZ Quarterly) over one uploaded alpha roster.

- common.py     record normalisation, alpha-roster date parsing (3888 = indefinite)
- retention.py  Runs 1-3 (pure functions)
- btz.py        Run 4 (pure functions)
- registry.py   run metadata, parameter parsing, dispatch
- exports.py    in-memory PDF / XLSX builders

Pure and stateless: nothing here logs member data or writes to disk.
"""
