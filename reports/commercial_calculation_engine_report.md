# Commercial Calculation Engine Report

Generated: 2026-05-04T09:48:28
DB initialize result: True
Active company: Varnam Clothing Centre Vdl (24)

## Validator rules
- cash_sale_overpayment_block: PASS result={'success': False, 'message': 'Cash type amount cannot be greater than bill amount. Use Credit type / Advance Receipt or Payment for excess amount.', 'against_bill_amount': 5000.0, 'advance_amount': 5000.0, 'is_credit': False, 'is_cash': True}
- credit_sale_overpayment_allow: PASS result={'success': True, 'message': 'OK', 'against_bill_amount': 5000.0, 'advance_amount': 5000.0, 'is_credit': True, 'is_cash': False}
- cash_purchase_overpayment_block: PASS result={'success': False, 'message': 'Cash type amount cannot be greater than bill amount. Use Credit type / Advance Receipt or Payment for excess amount.', 'against_bill_amount': 5000.0, 'advance_amount': 5000.0, 'is_credit': False, 'is_cash': True}
- credit_purchase_overpayment_allow: PASS result={'success': True, 'message': 'OK', 'against_bill_amount': 5000.0, 'advance_amount': 5000.0, 'is_credit': True, 'is_cash': False}
- cash_return_overpayment_block: PASS result={'success': False, 'message': 'Cash type amount cannot be greater than bill amount. Use Credit type / Advance Receipt or Payment for excess amount.', 'against_bill_amount': 5000.0, 'advance_amount': 5000.0, 'is_credit': False, 'is_cash': True}
- credit_return_overpayment_allow: PASS result={'success': True, 'message': 'OK', 'against_bill_amount': 5000.0, 'advance_amount': 5000.0, 'is_credit': True, 'is_cash': False}

## Existing voucher dry-run
success: True
posted: {'sales': 10, 'purchase': 4, 'sales_return': 0, 'purchase_return': 0, 'cash_receipt': 0, 'cash_payment': 0, 'bank_receipt': 0, 'bank_payment': 0, 'journal': 0}
failed_count: 0

## Required engine method audit
- repost_voucher_from_db: YES
- delete_voucher_postings: YES
- post_cash_receipt: YES
- post_cash_payment: YES
- post_bank_receipt: YES
- post_bank_payment: YES
- post_journal_entry: YES
- update_voucher_ledger_entries: YES
- delete_voucher_ledger_entries: YES
- repost_all_company: YES

## Final
success: True
failed_count: 0