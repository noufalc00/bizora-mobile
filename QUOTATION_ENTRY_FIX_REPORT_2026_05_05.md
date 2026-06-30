# Quotation Entry Fix Report - 2026-05-05

Modified file:
- ui/quotation_entry.py

Fixes applied:
1. Added first-letter capitalization for normal text entry fields.
2. GSTIN now forces uppercase alphanumeric input and max length 15.
3. State now auto-fills from GSTIN first two digits using shared Indian GST state code mapping, while remaining manually editable.
4. Added Sales-like Enter/Esc navigation across top fields, party fields, product fields, footer fields, and editable table cells.
5. Reworked product entry bar to use separate short Barcode field and Product field like Sales Entry.
6. Added footer discount entry field and included it in grand-total calculation using sales-style subtraction from footer total.
7. Styled Save and Update buttons more like Sales Entry action buttons.
8. Fixed Save button database failure by replacing invalid execute_query(return_insert_id=True) usage with a safe insert-return-id helper.
9. Quotation save remains zero-impact: it writes only quotation tables and does not post ledger, stock, day book, bank, or trial balance.

Verification:
- python -m py_compile main.py ui/quotation_entry.py ui/main_window.py db.py passed.

Files not changed:
- accounting.db was not modified.
- theme/light theme files were not touched.
- archive/quarantine files were not touched.
- Sales Entry, Ledger, Trial Balance, Day Book, GST reports, and voucher files were not touched.
