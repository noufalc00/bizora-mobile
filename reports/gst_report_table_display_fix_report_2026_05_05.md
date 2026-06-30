# GST Sales/Purchase Report Table Display Fix Report — 2026-05-05

## Problem Fixed
- GST Sales Report was retrieving sales rows from database but only one/no visible row appeared in the table because the report table section-row insertion logic was unsafe.
- GST Sales classification used ambiguous GSTIN/state fields and could trust stale `form_of_sale` values instead of deriving B2B/B2CL/B2CS from actual GSTIN/state/grand-total data.
- GST Purchase Report table rows were editable on double-click, so the user saw an inline editor instead of clean row viewing/details.
- GST Purchase Report used wrong field names for purchase number/date and duplicated GSTIN/state aliases, causing blank invoice fields and weak display.
- GST tax split columns were showing 0.00 where item tax values existed.

## Files Modified
- `db.py`
- `ui/gst_sales_report_page.py`
- `ui/gst_purchase_report_page.py`

## Main Repairs
1. Rebuilt GST Sales Report table population safely:
   - All required rows are explicitly inserted before setting table items.
   - B2B/B2CL/B2CS sections no longer fail silently.
   - Table items are non-editable.
   - Double-click now opens details instead of cell editing.

2. Improved GST Sales classification:
   - Uses party GSTIN first, then bill GSTIN.
   - Uses party state first, then bill state.
   - Derives B2B/B2CL/B2CS from actual GST rules instead of blindly trusting stale saved value.

3. Improved GST Purchase Report display:
   - Correct purchase fields used: `purchase_number`, `purchase_date`.
   - Supplier GSTIN/state aliases are explicit and stable.
   - Table items are non-editable and have tooltips.
   - Detail dialog uses a larger readable table.

4. Improved tax columns:
   - `db.py` now aggregates `cgst_amount`, `sgst_amount`, `igst_amount`, `cess_amount`, and `tax_amount` from item rows.
   - UI safely derives CGST/SGST or IGST from `tax_total` when split columns are not populated.

## Verification Done
- `python -m py_compile db.py ui/gst_sales_report_page.py ui/gst_purchase_report_page.py main.py ui/main_window.py` completed successfully in the repair environment.
- Database query check confirmed active company 24 returns:
  - 14 GST sales rows for 2026-04-05 to 2026-05-05
  - 6 GST purchase rows for 2026-04-05 to 2026-05-05

## Not Changed
- No theme settings changed.
- No light theme work touched.
- No accounting.db included or overwritten.
- No archive/quarantine files edited.
- No sidebar/main routing changed.
- No ledger, trial balance, day book, voucher, sales entry, or purchase entry logic changed.

## User Test Required
After copying these files into the project folder, run:

```bash
python -m py_compile db.py ui/gst_sales_report_page.py ui/gst_purchase_report_page.py main.py ui/main_window.py
python main.py
```

Then test:
1. Open GST Sales Report → Generate.
2. Confirm sales report table shows rows/sections properly.
3. Double-click a data row and confirm detail dialog opens.
4. Open GST Purchase Report → Generate.
5. Confirm invoice number/date and tax columns show properly.
6. Double-click a purchase row and confirm it opens details instead of inline cell editing.
