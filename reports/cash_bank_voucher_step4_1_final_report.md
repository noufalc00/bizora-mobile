# Cash/Bank Voucher Step 4.1 Repair Report

## Fixes included

1. Fixed QCompleter warning by making account combo boxes editable before assigning completer.
2. Improved table input visibility with taller rows and visible combo/edit height.
3. Added Enter/Esc table navigation:
   - Enter: Account -> Towards V.No. -> Amount -> Discount -> next line Account
   - Esc: reverse direction
4. Selected account balance now updates after amount/discount entry using the selected row effect.
5. Added Discount column to Bank Receipt by enabling discount in the Bank Receipt voucher spec.
6. Reduced account column from oversized stretch behavior to a standard interactive width while keeping a wide dropdown popup and tooltips for long names.
7. Kept ledger posting logic balanced.

## Files changed

- logic/cash_bank_voucher_logic.py
- ui/voucher_grid_common.py

## Files not included

- accounting.db
- db.py
- config.py
- main.py

## Compile result

py_compile passed for changed files.
