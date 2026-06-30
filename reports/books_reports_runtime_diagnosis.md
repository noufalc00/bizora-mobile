
============================================================
  BOOKS & REPORTS RUNTIME DIAGNOSIS
============================================================

Database path: accounting.db

============================================================
  ACTIVE COMPANY
============================================================

Active company: None

============================================================
  COMPANIES
============================================================

Total companies: 6
  - ID: 15, Name: Best Vdl, Active: 0
  - ID: 16, Name: Dfdf, Active: 0
  - ID: 19, Name: Glkhjlkdksf, Active: 0
  - ID: 23, Name: Shalimar Textiles And Readymade, Active: 0
  - ID: 24, Name: Varnam Clothing Centre Vdl, Active: 1
  - ID: 1, Name: libas fashion, Active: 0

Note: Using first company (id=15) since no active company set

============================================================
  PRODUCTS
============================================================

Total products: 4

============================================================
  PARTIES
============================================================

Total parties: 2
  Debitor count: 1
  Creditor count: 1
  Both count: 0

============================================================
  STOCK MOVEMENTS
============================================================

Total stock movements: 0

Count by movement_type:

Sample 10 rows:

============================================================
  LEDGER ACCOUNTS
============================================================

Total ledger accounts: 23

Count by account_type:
  - capital: 1
  - cash_bank: 2
  - expense: 3
  - income: 2
  - party: 4
  - stock: 1
  - tax_liability: 10

Sample 10 rows:
  1. id=8, account_name=Cash Account, account_type=cash_bank, opening_balance=0.0
  2. id=9, account_name=Bank Account, account_type=cash_bank, opening_balance=0.0
  3. id=10, account_name=Sundry Debtors, account_type=party, opening_balance=0.0
  4. id=11, account_name=Sundry Creditors, account_type=party, opening_balance=0.0
  5. id=12, account_name=Stock Account, account_type=stock, opening_balance=0.0
  6. id=13, account_name=Sales Account, account_type=income, opening_balance=0.0
  7. id=14, account_name=Purchase Account, account_type=expense, opening_balance=0.0
  8. id=15, account_name=Sales Return Account, account_type=expense, opening_balance=0.0
  9. id=16, account_name=Purchase Return Account, account_type=income, opening_balance=0.0
  10. id=17, account_name=Output CGST, account_type=tax_liability, opening_balance=0.0

============================================================
  LEDGER ENTRIES
============================================================

Total ledger entries: 6

Count by voucher_type:
  - purchase: 4
  - sales: 2

Sample 10 rows:
  1. voucher_type=sales, voucher_id=9999, account_id=13, debit=0.0, credit=150.0
  2. voucher_type=purchase, voucher_id=8888, account_id=14, debit=300.0, credit=0.0
  3. voucher_type=purchase, voucher_id=8888, account_id=21, debit=9.0, credit=0.0
  4. voucher_type=purchase, voucher_id=8888, account_id=22, debit=9.0, credit=0.0
  5. voucher_type=sales, voucher_id=9999, account_id=29, debit=150.0, credit=0.0
  6. voucher_type=purchase, voucher_id=8888, account_id=30, debit=0.0, credit=318.0

============================================================
  SALES / PURCHASES / RETURNS
============================================================

Sales count: 0
Purchases count: 0
Sales Returns count: 0
Purchase Returns count: 0

============================================================
  TRIAL BALANCE QUERY
============================================================

Trial balance query result count: 23

Sample 5 rows:
  1. Cash Account (cash_bank) - Opening: 0.0, Debit: 0, Credit: 0
  2. Bank Account (cash_bank) - Opening: 0.0, Debit: 0, Credit: 0
  3. Sundry Debtors (party) - Opening: 0.0, Debit: 0, Credit: 0
  4. Sundry Creditors (party) - Opening: 0.0, Debit: 0, Credit: 0
  5. Stock Account (stock) - Opening: 0.0, Debit: 0, Credit: 0

============================================================
  DIAGNOSIS COMPLETE
============================================================

