# ACTIVE_RUNTIME_FILES

This document defines the OFFICIAL ACTIVE FILE SET for the Accounting Desktop Application.
All future development, patches, and modifications should target ONLY these files.

## OFFICIAL ACTIVE RUNTIME FILES

### Entry Point
- `main.py` - Application entry point

### Configuration & Helpers
- `config.py` - Application configuration and active company manager
- `helpers.py` - Utility functions for currency, dates, validation
- `ui/theme.py` - Shared UI theme styles and safe parsing helpers

### Database Layer
- `db.py` - Database manager with SQLite/MySQL compatibility

### Logic Layer
- `logic/party_logic.py` - Debitor/Creditor business logic
- `logic/sales_logic.py` - Sales business logic
- `logic/purchase_logic.py` - Purchase business logic
- `logic/sales_return_logic.py` - Sales Return business logic
- `logic/purchase_return_logic.py` - Purchase Return business logic
- `logic/product_logic.py` - Product business logic
- `logic/stock_logic.py` - Stock movement business logic
- `logic/stock_report_logic.py` - Stock report business logic
- `logic/bank_account_logic.py` - Bank account business logic
- `logic/ledger_logic.py` - Ledger accounting engine (double-entry, balances, reports)

### UI Layer - Main Window
- `ui/main_window.py` - Main application window with sidebar and stacked widgets

### UI Layer - Pages
- `ui/dashboard.py` - Financial overview dashboard
- `ui/company_page.py` - Company management page
- `ui/new_company_page.py` - New company creation page (opens as standalone window)
- `ui/open_company_page.py` - Open existing company page (opens as standalone window)
- `ui/products.py` - Product/Service management page (opens as standalone window)
- `ui/debitor_creditor.py` - Debitor/Creditor management page (opens as standalone window)
- `ui/bank_accounts.py` - Bank Account management page (opens as standalone window)
- `ui/ledger_page.py` - Ledger page with account filtering and date range
- `ui/stock_report_page.py` - Stock report page with multiple report types and pagination
- `ui/accounts.py` - Account management page
- `ui/transactions.py` - Transaction management page
- `ui/reports.py` - Financial reports page
- `ui/settings.py` - Application settings page
- `ui/sales_entry.py` - Sales Entry widget (main logic, opens as standalone window)
- `ui/sales_entry_ui.py` - Sales Entry UI builder mixin
- `ui/sales_entry_calculations.py` - Sales Entry calculations module
- `ui/sales_entry_delegate.py` - Sales Entry table delegate
- `ui/sales_entry_helpers.py` - Sales Entry helper functions
- `ui/sales_entry_popup.py` - Sales Entry popup component
- `ui/purchase_entry.py` - Purchase Entry widget (main logic, opens as standalone window)
- `ui/purchase_entry_ui.py` - Purchase Entry UI builder mixin
- `ui/purchase_entry_calculations.py` - Purchase Entry calculations module
- `ui/purchase_entry_delegate.py` - Purchase Entry table delegate
- `ui/purchase_entry_helpers.py` - Purchase Entry helper functions
- `ui/purchase_entry_popup.py` - Purchase Entry popup component
- `ui/sales_return.py` - Sales Return widget (main logic, opens as standalone window)
- `ui/sales_return_ui.py` - Sales Return UI builder mixin
- `ui/sales_return_calculations.py` - Sales Return calculations module
- `ui/sales_return_delegate.py` - Sales Return table delegate
- `ui/sales_return_helpers.py` - Sales Return helper functions
- `ui/sales_return_popup.py` - Sales Return popup component
- `ui/purchase_return.py` - Purchase Return widget (main logic, opens as standalone window)
- `ui/purchase_return_ui.py` - Purchase Return UI builder mixin
- `ui/purchase_return_calculations.py` - Purchase Return calculations module
- `ui/purchase_return_delegate.py` - Purchase Return table delegate
- `ui/purchase_return_helpers.py` - Purchase Return helper functions
- `ui/purchase_return_popup.py` - Purchase Return popup component
- `ui/standalone_window.py` - Standalone window shell for module pages

### UI Layer - Dialogs
- `ui/edit_company_dialog.py` - Edit company dialog
- `ui/view_company_dialog.py` - View company dialog

### Components
- `components/sidebar.py` - Sidebar navigation component
- `components/topbar.py` - Top bar component

### Assets
- `assets/` - All asset files (icons, styles, etc.)

## ARCHIVED / UNUSED FILES

The following files have been moved to `archive_unused_files/` and are NOT part of the active runtime:
- `db_output.py` - Duplicate/backup of db.py
- `db_updated.py` - Duplicate/backup of db.py
- `final_db.py` - Duplicate/backup of db.py
- `debitor_creditor_full.py` - Duplicate/backup of debitor_creditor.py
- `debitor_creditor_output.py` - Duplicate/backup of debitor_creditor.py
- `debitor_creditor_updated.py` - Duplicate/backup of debitor_creditor.py
- `final_debitor_creditor.py` - Duplicate/backup of debitor_creditor.py
- `main_window_output.py` - Duplicate/backup of main_window.py
- `main_window_updated.py` - Duplicate/backup of main_window.py
- `final_main_window.py` - Duplicate/backup of main_window.py
- `products_backup.py` - Duplicate/backup of products.py
- `products_full.txt` - Full text export of products.py

## IMPORTANT RULES FOR FUTURE DEVELOPMENT

1. **ONLY EDIT OFFICIAL ACTIVE FILES** listed in the OFFICIAL ACTIVE RUNTIME FILES section above.

2. **DO NOT EDIT ARCHIVED FILES** - They are kept for reference only in case of emergency rollback.

3. **DO NOT CREATE NEW DUPLICATE FILES** - Always edit the official active file directly.

4. **IF YOU NEED TO BACK UP** - Use version control (git) or create a dated backup outside the project directory.

5. **RUNTIME CHAIN** - The active runtime chain starts from `main.py` and follows imports through the official active files listed above.

## ACTIVE RUNTIME CHAIN

```
main.py
├── config.py
├── db.py
├── ui.main_window.py
│   ├── components.sidebar.py
│   ├── components.topbar.py
│   ├── ui.dashboard.py
│   ├── ui.company_page.py
│   ├── ui.new_company_page.py
│   ├── ui.open_company_page.py
│   ├── ui.products.py
│   ├── ui.debitor_creditor.py
│   ├── ui.bank_accounts.py
│   ├── ui.sales_entry.py
│   │   ├── ui.sales_entry_ui.py
│   │   ├── ui.sales_entry_calculations.py
│   │   ├── ui.sales_entry_delegate.py
│   │   ├── ui.sales_entry_helpers.py
│   │   └── ui.sales_entry_popup.py
│   ├── ui.purchase_entry.py
│   │   ├── ui.purchase_entry_ui.py
│   │   ├── ui.purchase_entry_calculations.py
│   │   ├── ui.purchase_entry_delegate.py
│   │   ├── ui.purchase_entry_helpers.py
│   │   └── ui.purchase_entry_popup.py
│   ├── ui.sales_return.py
│   │   ├── ui.sales_return_ui.py
│   │   ├── ui.sales_return_calculations.py
│   │   ├── ui.sales_return_delegate.py
│   │   ├── ui.sales_return_helpers.py
│   │   └── ui.sales_return_popup.py
│   ├── ui.purchase_return.py
│   │   ├── ui.purchase_return_ui.py
│   │   ├── ui.purchase_return_calculations.py
│   │   ├── ui.purchase_return_delegate.py
│   │   ├── ui.purchase_return_helpers.py
│   │   └── ui.purchase_return_popup.py
│   ├── ui.ledger_page.py
│   ├── ui.stock_report_page.py
│   ├── ui.accounts.py
│   ├── ui.transactions.py
│   ├── ui.reports.py
│   └── ui.settings.py
├── logic.party_logic.py
├── logic.sales_logic.py
├── logic.purchase_logic.py
├── logic.sales_return_logic.py
├── logic.purchase_return_logic.py
├── logic.product_logic.py
├── logic.stock_logic.py
├── logic.stock_report_logic.py
├── logic.bank_account_logic.py
└── logic.ledger_logic.py
└── assets.styles.dark_theme
```

## FILES THAT MUST NOT BE EDITED IN FUTURE

All files in `archive_unused_files/` directory must not be edited. They are historical backups only.

---

**LAST UPDATED:** 2026-04-18
**SALES RETURN & PURCHASE RETURN MODULES ADDED:** Complete implementation of Sales Return and Purchase Return modules with database tables, logic layers, and UI components following the same architecture as Sales Entry and Purchase Entry.

## STEP 4 CASH/BANK VOUCHER ACTIVE FILES - 2026-05-04

### Logic Layer - Cash/Bank Vouchers
- `logic/cash_bank_voucher_logic.py` - Shared commercial logic for Cash/Bank Receipt/Payment voucher-grid modules
- `logic/cash_receipt_logic.py` - Cash Receipt wrapper logic
- `logic/cash_payment_logic.py` - Cash Payment wrapper logic
- `logic/bank_receipt_logic.py` - Bank Receipt wrapper logic
- `logic/bank_payment_logic.py` - Bank Payment wrapper logic

### UI Layer - Cash/Bank Vouchers
- `ui/voucher_grid_common.py` - Shared voucher-grid UI for Cash/Bank Receipt/Payment
- `ui/cash_receipt_page.py` - Cash Receipt voucher-grid page
- `ui/cash_payment_page.py` - Cash Payment voucher-grid page
- `ui/bank_receipt_page.py` - Bank Receipt voucher-grid page
- `ui/bank_payment_page.py` - Bank Payment voucher-grid page

### Tools
- `tools/test_cash_bank_vouchers.py` - Cash/Bank voucher posting smoke test

### Rules
- These voucher modules must post to `ledger_entries` using balanced double-entry accounting.
- Cash Receipt/Bank Receipt increase Cash/Bank balance.
- Cash Payment/Bank Payment decrease Cash/Bank balance.
- Do not edit archived files for these modules.
