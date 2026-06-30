# Step 4 Cash / Bank Voucher Repair

Copy the files from this zip into the same locations in your working project folder.

Do not replace:

- `accounting.db`
- `db.py`
- `config.py`
- `main.py`

After copying, run:

```bat
python -m py_compile logic\cash_bank_voucher_logic.py logic\cash_receipt_logic.py logic\cash_payment_logic.py logic\bank_receipt_logic.py logic\bank_payment_logic.py ui\voucher_grid_common.py ui\cash_receipt_page.py ui\cash_payment_page.py ui\bank_receipt_page.py ui\bank_payment_page.py ui\main_window.py tools\test_cash_bank_vouchers.py
python tools\test_cash_bank_vouchers.py
python main.py
```

Manual checks:

1. Entry → Cash Receipt opens.
2. Entry → Cash Payment opens.
3. Entry → Bank Receipt opens.
4. Entry → Bank Payment opens.
5. General/Debtor/Creditor/Bill tabs load related accounts.
6. Cash/Bank Balance appears.
7. Selected Account Balance appears.
8. Save posts entries to Ledger.
9. Trial Balance remains balanced.
10. Day Book should show these vouchers if Day Book reads `ledger_entries` voucher types.
