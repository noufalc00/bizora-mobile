# Central Save / Runtime Repair Round 2 — 2026-05-10

## User-reported failures repaired

1. Modules opened without explicitly opening a company.
2. Sales Return and Purchase Return did not save.
3. Van Entry / Van Return Entry navigation and Van Return credit bill table behavior were not updated as requested.
4. Startup and first-open performance had regressed.
5. Runtime logs repeated schema errors:
   - `no such column: p.bill_date`
   - `no such column: pr.amount_paid`

## Root causes found

### Active company auto-load regression
`ui/main_window.py` was loading the last active company from the database at startup and setting it into session state automatically. That allowed entry modules to open/save without the user explicitly using File > Open Company in the current session.

### Schema mismatch in party balance / voucher query
`db.get_vouchers_before_date()` referenced non-existing columns:
- `p.bill_date` while the active purchases schema uses `purchase_date`.
- `pr.amount_paid` while purchase returns schema uses `amount_received_or_adjusted`.
It also used inconsistent amount aliases for sales returns/purchase returns.

### Return item insert mismatch
`db.insert_sales_return_item()` and `db.insert_purchase_return_item()` had 21 target columns but only 20 placeholders, causing return save failures.

### Stock movement type mismatch
Return posting used stock movement types that were not allowed by the active `stock_movements` CHECK constraint. Return stock movements now use the valid `return` movement type with correct signed quantity direction.

### Ledger amount type mismatch
Purchase ledger posting mixed Decimal and float amounts, causing `unsupported operand type(s) for +: 'decimal.Decimal' and 'float'` during purchase save. Ledger posting now normalizes local posting amounts consistently.

## Files changed

- `config.py`
- `db.py`
- `logic/book_report_common.py`
- `logic/ledger_logic.py`
- `logic/van_logic.py`
- `logic/voucher_posting_engine.py`
- `ui/main_window.py`
- `ui/open_company_page.py`
- `ui/new_company_page.py`
- `ui/sales_entry.py`
- `ui/van_entry_page.py`
- `ui/van_return_page.py`

## Key repairs

### Company guard
- No module auto-opens based on database active company at startup.
- Runtime session starts with no active company.
- Entry/books/reports modules are blocked until the user opens or creates a company in the current session.
- File > Open Company now explicitly sets database active company and session active company.
- File > New Company explicitly sets session active company after successful creation.
- File > Close Company clears DB active flag and session state.

### Sales Return / Purchase Return saving
- Fixed item insert placeholder counts.
- Fixed return stock movement type validation.
- Fixed return query amount/date aliases.
- Engine-level SQLite save tests passed for Sales Return and Purchase Return.

### Sales / Purchase saving
- Re-tested Sales and Purchase save logic after ledger amount normalization.
- Engine-level SQLite save tests passed for Sales and Purchase.

### Van module updates
- Van Entry now has previous/next load navigation similar to Sales Entry.
- Van Return now has previous/next return navigation similar to Sales Entry.
- Van Return credit bills table selection style avoids full-row blue selection.
- Van Return credit bills table supports one-click editor text selection and Enter/Esc flow across Party/Shop → Bill No → Amount.

### Performance repairs
- Sales Entry no longer synchronously loads party/product caches before first paint.
- Sales Entry heavy party/product load is deferred shortly after the page is shown.
- Main window no longer auto-loads and initializes a database active company at startup.
- Main window performance logs for first page openings now report total page-open time, not only import time.

## Validation completed in repair environment

Syntax compilation passed:

```text
python -m py_compile main.py db.py config.py
python -m py_compile changed logic/ui files
python -m compileall -q logic ui components assets main.py db.py config.py
```

SQLite logic save tests passed for:

- Sales
- Purchase
- Sales Return
- Purchase Return

## Important limitation

The repair environment is headless and cannot open a real PySide6 Windows GUI. Final visual/keyboard confirmation must be performed in Thonny on Windows. If any GUI traceback appears, send the full traceback and screenshot.
