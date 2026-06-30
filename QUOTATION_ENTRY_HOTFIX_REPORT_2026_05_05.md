# Quotation Entry Hotfix Report - 2026-05-05

Fixed crash when opening Quotation Entry:
- Added missing `convert_to_invoice()` method in `ui/quotation_entry.py`.
- Method is intentionally safe/placeholder until full SalesLogic conversion is verified.
- No database, theme, sidebar, ledger, trial balance, or stock logic changed.

Compile:
- `python -m py_compile ui/quotation_entry.py` passed.

