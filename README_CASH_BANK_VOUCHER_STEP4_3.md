# Cash/Bank Voucher Step 4.3 Fixes

Copy these files into the same locations in your project:

- ui/voucher_grid_common.py
- logic/cash_bank_voucher_logic.py
- logic/day_book_logic.py
- ui/day_book_page.py
- tools/diagnose_day_book.py

Do not replace accounting.db, db.py, config.py, or main.py.

After copying, run:

```bat
python -m py_compile ui\voucher_grid_common.py logic\cash_bank_voucher_logic.py logic\day_book_logic.py ui\day_book_page.py tools\diagnose_day_book.py
python main.py
```

Manual tests:

1. Save Cash Receipt, Cash Payment, Bank Receipt, Bank Payment. The window should reset after OK/Save.
2. Use Previous/Next. Loaded voucher should show Update button.
3. Save Bank Receipt with discount. Ledger must show discount transaction.
4. Day Book must show Cash/Bank Receipt/Payment rows.
