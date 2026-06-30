# Quotation Entry Repair Report — 2026-05-05

## Files modified
- ui/quotation_entry.py only

## Fixes completed
1. Implemented Previous / Next quotation navigation using saved quotation id sequence.
2. Added quotation loading from quotation_master and quotation_items.
3. Implemented quotation update flow without ledger/stock impact.
4. Reworked live calculation so Qty/Rate/Discount/Tax changes refresh Gross, Net, Tax, Total and footer totals.
5. Added Sales Entry style table selection:
   - Click SL No selects full row.
   - Click normal cell selects only that cell and opens editor with text selected.
6. Added Round Off checkbox.
   - Checked: deducts decimal paise from grand total by applying negative round-off.
   - Unchecked/manual entry: uses typed round-off value.
7. Preserved zero-impact quotation accounting rule.

## Compile result
Passed:
- python -m py_compile main.py
- python -m py_compile db.py
- python -m py_compile ui/main_window.py
- python -m py_compile ui/quotation_entry.py

## Not touched
- accounting.db
- theme/settings files
- ledger/trial balance/day book/books/vouchers/GST modules
- archive/quarantine files
