# Cash/Bank Voucher Step 4.3 Final Report

## Scope
Focused repair for Cash Receipt, Cash Payment, Bank Receipt, Bank Payment, and Day Book consumer visibility.

## Files Changed
- ui/voucher_grid_common.py
- logic/cash_bank_voucher_logic.py
- logic/day_book_logic.py
- ui/day_book_page.py
- tools/diagnose_day_book.py

## Fixes
1. OK/Save/Update now resets the voucher screen after successful save/update.
2. Save button label changes to Update when a previous/next voucher is loaded.
3. Fresh opening of Cash/Bank voucher pages starts a new voucher.
4. Day Book reads the new cash_bank_vouchers table and includes cash/bank receipts/payments.
5. Receipt discount posting is split so Ledger shows discount as a separate transaction instead of hiding it inside one combined party amount.
6. Account column size remains compact while popup/tooltips keep names visible.

## Verification
- py_compile passed for changed files.
- Hardcoded SQL placeholder scan: 0 active question-mark placeholders in changed files.

## Remaining Manual Tests
- Cash Receipt save then screen reset.
- Previous/Next loads voucher and button says Update.
- Bank Receipt discount appears in Ledger.
- Day Book includes Cash Receipt, Cash Payment, Bank Receipt, Bank Payment rows.
