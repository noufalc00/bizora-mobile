# Cash/Bank Voucher Step 4.1 Fix

Copy these files into the same locations in your project:

- logic/cash_bank_voucher_logic.py
- ui/voucher_grid_common.py

Do not replace accounting.db, db.py, config.py, or main.py.

After copying, run:

python -m py_compile logic\cash_bank_voucher_logic.py ui\voucher_grid_common.py
python main.py

Manual checks:

1. Open Cash Receipt, Cash Payment, Bank Receipt, Bank Payment.
2. Confirm the shell warning "Setting a QCompleter on non-editable QComboBox is not allowed" is gone.
3. Confirm Account dropdown is searchable and visible.
4. Confirm Enter moves Account -> Towards -> Amount -> Discount -> next line.
5. Confirm Esc moves reverse.
6. Confirm selected account balance changes after amount/discount entry.
7. Confirm Bank Receipt has Discount column.
