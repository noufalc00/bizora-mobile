# Day Book Commercial Consumer Step 2

This package is only for Day Book consumer repair after the Step 1 commercial calculation/posting engine.

## What this fixes

- Day Book now shows `Cash Received - <debtor>` rows for credit sales with Amount Received.
- Day Book now shows `Cash Paid - <creditor>` rows for credit purchases with Amount Paid.
- Credit sales are displayed as full debtor credit plus separate received amount, so Balance Cash remains correct.
- Credit purchases are displayed as full creditor debit plus separate paid amount, so Balance Cash remains correct.
- Cash Receipt/Cash Payment table rows are prepared to show with correct account names when those vouchers exist.
- Diagnostic tool now checks Day Book rows for sales receipts, purchase payments, cash receipts, and cash payments.

## Files included

- `logic/day_book_logic.py`
- `ui/day_book_page.py`
- `tools/diagnose_day_book.py`
- `reports/day_book_commercial_consumer_step2_report.md`
- `README_DAY_BOOK_COMMERCIAL_CONSUMER_STEP2.md`

## Do not replace

- `accounting.db`
- `db.py`
- `config.py`
- `main.py`

## After copying

Run:

```bat
python -m py_compile logic\day_book_logic.py ui\day_book_page.py tools\diagnose_day_book.py
python tools\diagnose_day_book.py
python main.py
```

Then open **Books → Day Book** and load the date range containing sales with Amount Received.

Expected rows include examples like:

- `Cash Received - Noufal` on the Debit side
- `Cash Paid - Calicut Textiles` on the Credit side
- `Balance Cash / c/d` includes those amounts
