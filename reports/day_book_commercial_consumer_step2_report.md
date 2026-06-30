# Day Book Commercial Consumer Step 2 Report

## Scope

Focused Day Book repair only. No theme, Cash Receipt UI, Cash Payment UI, database, or Sales/Purchase logic changes are included.

## Files changed

- `logic/day_book_logic.py`
- `tools/diagnose_day_book.py`

`ui/day_book_page.py` is included for safe replacement alignment, but its business logic was not redesigned.

## Main fixes

1. Credit Sales now show:
   - Sales Grand Total on Debit side
   - Full Debtor Credit line on Credit side
   - Cash Received from debtor on Debit side when Amount Received exists

2. Credit Purchases now show:
   - Purchase Account on Credit side
   - Full Creditor Debit line on Debit side
   - Cash Paid to creditor on Credit side when Amount Paid exists

3. Balance Cash formula remains:

```text
Opening Cash Balance + Debit rows - Credit rows = Balance Cash / c/d
```

4. Cash Receipt and Cash Payment table rows now use account name joins and correct `towards_acc` field handling.

5. `tools/diagnose_day_book.py` now verifies:
   - sales with amount_received
   - purchases with amount_paid
   - Day Book sales_receipt rows
   - Day Book purchase_payment rows
   - cash_receipt rows
   - cash_payment rows

## Verification on uploaded DB copy

Active company: `Varnam Clothing Centre Vdl`

Observed:

- sales with amount_received > 0: 10
- purchases with amount_paid > 0: 2
- Day Book sales_receipt rows: 3
- Day Book purchase_payment rows: 1
- cash_receipt rows: 0 because current cash_receipts table has no saved rows
- cash_payment rows: 0 because current cash_payments table has no saved rows

Example rows generated:

```text
Cash Received - Noufal        Debit 200.00
Cash Received - Noufal        Debit 500.00
Cash Received - Noufal        Debit 567.00
Cash Paid - Calicut Textiles  Credit 17000.00
```

## Compile and scan

- `python -m py_compile logic/day_book_logic.py ui/day_book_page.py tools/diagnose_day_book.py`: success
- hardcoded placeholder scan: `QUESTION_MARK_LINES: 0`

## Remaining notes

Cash Receipt/Cash Payment standalone vouchers will appear in Day Book after those vouchers are saved to their tables and/or posted to ledger by the next Cash/Bank voucher repair step.
