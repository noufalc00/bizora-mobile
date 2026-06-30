# Cash/Bank Voucher Step 4.2 Fixes

Copy these files into your project folder:

- `ui/voucher_grid_common.py`
- `logic/cash_bank_voucher_logic.py`

Do not replace `accounting.db`, `db.py`, `config.py`, or `main.py`.

After copying, run:

```bat
python -m py_compile ui\voucher_grid_common.py logic\cash_bank_voucher_logic.py
python main.py
```

Test Cash Receipt, Cash Payment, Bank Receipt, and Bank Payment:

- Date must show fully.
- Enter moves Account -> Towards V.No. -> Amount -> Discount -> next row.
- Esc moves backward in one key press.
- Selected account balance updates live while typing amount/discount.
