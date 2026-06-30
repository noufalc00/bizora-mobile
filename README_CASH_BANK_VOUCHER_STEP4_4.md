# Cash/Bank Voucher Step 4.4 Repair

Copy the files in this zip into the same locations in your project folder.

Do **not** replace:

- `accounting.db`
- `db.py`
- `config.py`
- `main.py`

## After Copying

Run:

```bat
python -m py_compile logic\cash_bank_voucher_logic.py logic\day_book_logic.py ui\voucher_grid_common.py ui\cash_receipt_page.py ui\cash_payment_page.py ui\bank_receipt_page.py ui\bank_payment_page.py ui\main_window.py ui\day_book_page.py tools\test_cash_bank_voucher_step4_4.py
python tools\test_cash_bank_voucher_step4_4.py
python main.py
```

## Manual Test

1. Open Cash Receipt and save a voucher.
2. Confirm it resets after OK / Save.
3. Click Previous and confirm saved voucher loads.
4. Confirm button text changes to Update.
5. Save Bank Receipt with discount.
6. Open Ledger and confirm discount appears as a separate transaction line.
7. Double-click Ledger voucher row and click Open Original / Edit Voucher.
8. Open Day Book and confirm Cash/Bank voucher rows are visible.
