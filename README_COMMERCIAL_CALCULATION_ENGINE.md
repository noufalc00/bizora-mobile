# Commercial Calculation and Posting Engine

This package adds a commercial-standard calculation, validation, ledger posting and stock reposting layer for the accounting app.

## Files included

Copy these files into the same locations in the project folder:

```text
logic/commercial_calculation_engine.py
logic/commercial_voucher_validator.py
logic/voucher_posting_engine.py
tools/test_commercial_calculation_engine.py
tools/rebuild_commercial_voucher_postings.py
tools/test_voucher_posting_engine.py
tools/rebuild_voucher_postings_with_engine.py
```

Do not replace:

```text
accounting.db
db.py
config.py
main.py
```

## Final commercial rules

### Cash type

Cash type does not allow overpayment.

Examples:

```text
Cash Sale 5000, received 10000     blocked
Cash Purchase 5000, paid 10000     blocked
Cash Sales Return 5000, refunded 10000 blocked
Cash Purchase Return 5000, received 10000 blocked
```

### Credit type

Credit type allows overpayment and treats extra amount as advance or on-account balance in the same party ledger.

Credit Sale 5000, received 10000:

```text
Dr Debtor 5000
Cr Sales and Tax 5000
Dr Cash 10000
Cr Debtor 10000
```

Debtor ledger result:

```text
Debit sale 5000
Credit receipt 10000
Closing 5000 Cr advance received
```

Credit Purchase 5000, paid 10000:

```text
Dr Purchase and Tax 5000
Cr Creditor 5000
Dr Creditor 10000
Cr Cash 10000
```

Creditor ledger result:

```text
Credit purchase 5000
Debit payment 10000
Closing 5000 Dr advance paid
```

## Test before integration

Run from the project folder:

```bat
python tools\test_commercial_calculation_engine.py
```

Expected:

```text
success: True
failed_count: 0
```

## Real rebuild

After test passes and after backing up the database, run:

```bat
python tools\rebuild_commercial_voucher_postings.py
```

Compatibility wrappers are also included:

```bat
python tools\test_voucher_posting_engine.py
python tools\rebuild_voucher_postings_with_engine.py
```

## Integration

After copying and testing, paste `WINDSURF_INTEGRATE_COMMERCIAL_CALCULATION_ENGINE.txt` into Windsurf.

Windsurf must connect all Sales, Purchase, Sales Return and Purchase Return save and update flows to this engine.
