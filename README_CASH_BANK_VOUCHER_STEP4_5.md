# Cash/Bank Voucher Step 4.5 Fix

Focused repair for the voucher-grid pages and ledger discount visibility.

## Files included

- `ui/voucher_grid_common.py`
- `ui/cash_receipt_page.py`
- `ui/cash_payment_page.py`
- `ui/bank_receipt_page.py`
- `ui/bank_payment_page.py`
- `ui/main_window.py`
- `ui/ledger_page.py`
- `ui/book_report_common.py`
- `logic/cash_bank_voucher_logic.py`
- `logic/ledger_logic.py`
- `logic/day_book_logic.py`

## Main fixes

1. Voucher UI made more compact and closer to Sales/Purchase navigation style.
2. Previous/Next moved beside Voucher No as ▲ / ▼ buttons.
3. Bottom Previous/Next buttons removed to reduce voucher window size.
4. Account column width reduced to a more standard size while keeping account dropdown popup wide.
5. Receipt discount ledger posting is separated:
   - Cash/Bank receipt amount is shown separately.
   - Discount Allowed is shown separately in Ledger.
6. Ledger posting now respects per-entry narration, so discount rows are visible as discount rows.
7. Ledger voucher details now reads cash/bank voucher item rows and has Open Original / Edit Voucher button at the top.
8. Party-account lookup is made safer for databases where `parties.ledger_account_id` does not exist.

## After copying

Run:

```bat
python -m py_compile logic\cash_bank_voucher_logic.py logic\ledger_logic.py logic\day_book_logic.py ui\voucher_grid_common.py ui\cash_receipt_page.py ui\cash_payment_page.py ui\bank_receipt_page.py ui\bank_payment_page.py ui\main_window.py ui\ledger_page.py ui\book_report_common.py
python main.py
```

Then test:

1. Cash Receipt / Bank Receipt with discount.
2. Debtor ledger should show receipt row and discount row separately.
3. Previous/Next must work using ▲ / ▼ beside Voucher No.
4. Double-click ledger row and use Open Original / Edit Voucher.
