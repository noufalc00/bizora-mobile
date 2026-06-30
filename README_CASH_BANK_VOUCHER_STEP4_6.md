# Cash/Bank Voucher Step 4.6 Fix

Copy these files into the same folders in your project:

- ui/voucher_grid_common.py
- ui/ledger_page.py
- logic/ledger_logic.py
- logic/cash_bank_voucher_logic.py

Do not replace:

- accounting.db
- db.py
- config.py
- main.py

After copying, run:

```bat
python -m py_compile ui\voucher_grid_common.py ui\ledger_page.py logic\ledger_logic.py logic\cash_bank_voucher_logic.py
python main.py
```

Manual checks:

1. Open Ledger and confirm Account dropdown loads General/Debtor/Creditor options.
2. Open Cash Receipt / Bank Receipt and confirm Voucher No has compact ▲ / ▼ buttons beside it.
3. Click table cells and confirm the large blue row shade is gone or reduced.
4. Check Discount column width is compact.
5. Create receipt with discount and rebuild/refresh ledger if old voucher discount rows were created before this fix.
