# Commercial Calculation Engine Step 1

This package contains ONLY the commercial calculation / posting engine repair files.
It does not include theme changes, Cash Receipt/Payment UI redesign, or `accounting.db`.

## What this step fixes

1. Adds `commercial_calculation_engine.py`.
2. Adds `commercial_voucher_validator.py`.
3. Replaces `voucher_posting_engine.py` with a fuller commercial engine.
4. Links Sales, Purchase, Sales Return, and Purchase Return save/update validation before DB mutation.
5. Adds missing engine methods used by Cash Receipt, Cash Payment, Bank Receipt, Bank Payment, and Journal logic.
6. Adds delete-posting cleanup to prevent duplicate ledger rows.
7. Adds commercial rules:
   - Cash type overpayment is blocked.
   - Credit type overpayment is accepted as advance/on-account in the same party ledger.
   - Paid/received amount must appear as a separate ledger transaction.
   - Every voucher posting must balance.
8. Adds dry-run test and rebuild tools.

## How to install

Copy/extract these files into your existing working project folder:

```text
logic/commercial_calculation_engine.py
logic/commercial_voucher_validator.py
logic/voucher_posting_engine.py
logic/sales_logic.py
logic/purchase_logic.py
logic/sales_return_logic.py
logic/purchase_return_logic.py
tools/test_commercial_calculation_engine.py
tools/rebuild_commercial_voucher_postings.py
tools/test_voucher_posting_engine.py
tools/rebuild_voucher_postings_with_engine.py
reports/commercial_calculation_engine_report.md
```

Do NOT replace:

```text
accounting.db
db.py
config.py
main.py
```

## First command after copying

From the project folder:

```bat
python tools\test_commercial_calculation_engine.py
```

Expected:

```text
success: True
failed_count: 0
```

## Before real rebuild

Backup your current database:

```bat
copy accounting.db accounting_backup_before_commercial_engine_step1.db
```

Then run:

```bat
python tools\rebuild_commercial_voucher_postings.py
```

## Important

This is step 1 only. It is intentionally focused on calculation/posting safety.
It does not change theme and does not rebuild Cash Receipt/Cash Payment UI.
