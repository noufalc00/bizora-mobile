# Day Book Commercial Consumer Diagnosis

Generated: 2026-05-04 10:06:32
DB initialize result: True
Active company id: 24
Active company: Varnam Clothing Centre Vdl

## Source counts
sales rows: 10
purchases rows: 4
ledger voucher counts:
- purchase: count=24, debit=57115.69, credit=57115.69
- sales: count=70, debit=16448.0, credit=16448.0

## Paid/received voucher source check
sales with amount_received > 0: 10
- 2026-04-30 INV-20260430-001 type=Sales total=1362.0 received=1362.0
- 2026-04-30 INV-20260430-002 type=Credit Sales total=477.0 received=200.0
- 2026-04-30 INV-20260430-003 type=Sales total=477.0 received=477.0
- 2026-04-30 INV-20260430-004 type=Sales total=238.0 received=238.0
- 2026-04-30 INV-20260430-005 type=Sales total=795.0 received=795.0
- 2026-05-02 INV-20260502-001 type=Sales total=477.0 received=477.0
- 2026-05-02 INV-20260502-002 type=Credit Sales total=795.0 received=700.0
- 2026-05-03 INV-20260503-001 type=Sales total=2655.0 received=2655.0
- 2026-05-03 INV-20260503-002 type=Credit Sales total=567.0 received=567.0
- 2026-05-03 INV-20260503-003 type=Sales total=567.0 received=567.0
purchases with amount_paid > 0: 2
- 2026-04-30 6 type=Credit total=29017.49 paid=5000.0
- 2026-04-30 8 type=Credit total=6360.0 paid=12000.0

## Day Book result
date range: 2026-04-30 to 2026-05-03
success: True
rows: 31
sales_receipt rows: 3
purchase_payment rows: 1
cash_receipt rows: 0
cash_payment rows: 0

## Sample Day Book receipt/payment rows
- 2026-04-30 sales_receipt Cash Received - Noufal Dr=200.0 Cr=0.0 Source=Sales Receipt
- 2026-05-02 sales_receipt Cash Received - Noufal Dr=700.0 Cr=0.0 Source=Sales Receipt
- 2026-05-03 sales_receipt Cash Received - Noufal Dr=567.0 Cr=0.0 Source=Sales Receipt
- 2026-04-30 purchase_payment Cash Paid - Calicut Textiles Dr=0.0 Cr=17000.0 Source=Purchase Payment