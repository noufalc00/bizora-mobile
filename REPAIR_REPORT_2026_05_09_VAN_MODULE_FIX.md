# Van Module Repair Report - 2026-05-09

## Fixed

1. Added official active runtime files:
   - `logic/van_logic.py`
   - `ui/van_entry_page.py`
   - `ui/van_return_page.py`

2. Fixed wrong DB API pattern that caused errors such as:
   - `Database object has no attribute rollback`
   - `Database object has no attribute get_cursor`

3. Added safe DB schema creation for:
   - `locations`
   - `van_loads`
   - `van_load_items`
   - `van_returns`
   - `van_return_items`
   - `van_credit_bills`

4. Added `source_location_id` and `destination_location_id` columns to `stock_movements` when missing.

5. Added separate standalone window opening for:
   - Van Entry / Van Load Entry
   - Van Return Entry / Van Settlement

6. Rebuilt Van Entry and Van Return UI with the app dark theme:
   - dark background
   - yellow labels
   - blue title
   - ledger-style dark tables
   - no white body panels

7. Fixed Van Return calculation initialization so it does not call summary calculations before widgets exist.

## Accounting Safety

- Van Load is saved as an operational record only.
- Van Load does not post ledger entries.
- Van Return does not post ledger entries.
- Sold quantity from Van Return is posted to stock movements once, so stock is reduced only by actual sold quantity.

## Verification

- `python -m py_compile logic/van_logic.py ui/van_entry_page.py ui/van_return_page.py ui/main_window.py` passed.
- `python -m compileall -q .` passed.

## Notes

This repair does not modify Sales, Purchase, Sales Return, Purchase Return, Quotation, PDC, Cash Book, Ledger, Trial Balance, common_finance.py, or the Super Calculation Engine.
