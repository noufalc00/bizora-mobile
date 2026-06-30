"""Fast import/instantiate audit with per-page timeout via subprocess."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAGES = [
    ("Dashboard", "ui.dashboard", "DashboardWidget"),
    ("Company", "ui.company_page", "CompanyPageWidget"),
    ("Products", "ui.products", "ProductsWidget"),
    ("Debtors", "ui.debitor_creditor", "DebitorCreditorWidget"),
    ("Bank Accounts", "ui.bank_accounts", "BankAccountWidget"),
    ("Accounts", "ui.account_creation_page", "AccountCreationPageWidget"),
    ("Sales Entry", "ui.sales_entry", "SalesEntryWidget"),
    ("Purchase Entry", "ui.purchase_entry", "PurchaseEntryWidget"),
    ("Purchase Order", "ui.purchase_order", "PurchaseOrderUI"),
    ("Quotation", "ui.quotation_entry", "QuotationEntryWidget"),
    ("PDC", "ui.pdc_page", "PDCPage"),
    ("Credit Debit Note", "ui.credit_debit_note_page", "CreditDebitNotePage"),
    ("Sales Return", "ui.sales_return", "SalesReturnPageWidget"),
    ("Purchase Return", "ui.purchase_return", "PurchaseReturnPageWidget"),
    ("Ledger", "ui.ledger_page", "LedgerPageWidget"),
    ("Trial Balance", "ui.trial_balance_page", "TrialBalancePageWidget"),
    ("Profit Loss", "ui.profit_loss_page", "ProfitLossPageWidget"),
    ("Balance Sheet", "ui.balance_sheet_page", "BalanceSheetPageWidget"),
    ("Stock Report", "ui.stock_report_page", "StockReportPageWidget"),
    ("Stock Value", "ui.stock_value_page", "StockValuePageWidget"),
    ("Day Book", "ui.day_book_page", "DayBookPageWidget"),
    ("Cash Book", "ui.cash_book_page", "CashBookWidget"),
    ("PDC Book", "ui.pdc_book_page", "PDCBookPageWidget"),
    ("Journal Book", "ui.journal_book_page", "JournalBookPageWidget"),
    ("Daily Stock", "ui.daily_stock_register_page", "DailyStockRegisterPageWidget"),
    ("Price List", "ui.price_list_page", "PriceListPageWidget"),
    ("Stock Checker", "ui.stock_checker_page", "StockCheckerPageWidget"),
    ("Diagnostics", "ui.diagnostic_view", "DiagnosticView"),
    ("Audit Logs", "ui.audit_log_view", "AuditLogView"),
    ("Opening Balance", "ui.opening_balance_page", "OpeningBalanceWidget"),
    ("Stock Adjustment", "ui.stock_adjustment_page", "StockAdjustmentWidget"),
    ("Van Entry", "ui.van_entry_page", "VanEntryWidget"),
    ("Van Return", "ui.van_return_page", "VanReturnWidget"),
    ("Sales Book", "ui.sales_book_page", "SalesBookPageWidget"),
    ("Ledger Stmt", "ui.ledger_statement_page", "LedgerStatementPageWidget"),
    ("Bill History", "ui.bill_history_page", "BillHistoryPageWidget"),
    ("Cash Tender Hist", "ui.cash_tender_history_page", "CashTenderHistoryPageWidget"),
    ("Sales Profit", "ui.sales_profit_book_page", "SalesProfitBookPageWidget"),
    ("Monthly Analysis", "ui.monthly_analysis_page", "MonthlyAnalysisWidget"),
    ("Quotation Book", "ui.quotation_book_page", "QuotationBookPageWidget"),
    ("Sales Return Book", "ui.sales_return_book_page", "SalesReturnBookPageWidget"),
    ("Purchase Book", "ui.purchase_book_page", "PurchaseBookPageWidget"),
    ("PO Book", "ui.purchase_order_book", "PurchaseOrderBookUI"),
    ("Purchase Return Book", "ui.purchase_return_book_page", "PurchaseReturnBookPageWidget"),
    ("Cash Receipt", "ui.cash_receipt_page", "CashReceiptPageWidget"),
    ("Cash Payment", "ui.cash_payment_page", "CashPaymentPageWidget"),
    ("Bank Receipt", "ui.bank_receipt_page", "BankReceiptPageWidget"),
    ("Bank Payment", "ui.bank_payment_page", "BankPaymentPageWidget"),
    ("Journal Entry", "ui.journal_entry_page", "JournalEntryPageWidget"),
    ("GST Sales", "ui.gst_sales_report_page", "GSTSalesReportPage"),
    ("GSTR1", "ui.gstr1_page", "GSTR1Page"),
    ("GST Purchase", "ui.gst_purchase_report_page", "GSTPurchaseReportPage"),
    ("Collection Report", "ui.collection_report", "CollectionReportUI"),
    ("Best Sellers", "ui.best_sellers_report", "BestSellersReport"),
    ("Net Sales Book", "ui.net_sales_book", "NetSalesBook"),
    ("Salesman Book", "ui.salesman_book", "SalesmanBook"),
    ("Settings", "ui.settings", "SettingsWidget"),
    ("Theme Settings", "ui.theme_settings_page", "ThemeSettingsPage"),
    ("Login", "ui.login_window", "LoginWindow"),
    ("Company Gateway", "ui.company_gateway", "CompanyGateway"),
    ("Standalone Window", "ui.standalone_window", "StandaloneModuleWindow"),
]

SNIPPET = """
import os, sys, tempfile, traceback
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = {root!r}
sys.path.insert(0, ROOT)
from PySide6.QtWidgets import QApplication
from db import Database
import importlib
app = QApplication.instance() or QApplication([])
db = Database(db_type='sqlite', db_path=os.path.join(tempfile.mkdtemp(), 't.db'))
mod = importlib.import_module({mod!r})
cls = getattr(mod, {cls!r})
name = {cls!r}
try:
    if name.endswith('BookPageWidget'):
        from bizora_core.sales_book_logic import SalesBookLogic
        w = cls(db, SalesBookLogic(db), 'T', ['Bill Wise'])
    elif name == 'PurchaseOrderUI':
        w = cls(db)
    elif name in ('BestSellersReport', 'NetSalesBook'):
        w = cls(db_path=db.db_path)
    elif name == 'SalesmanBook':
        w = cls(db)
    elif name == 'CollectionReportUI':
        w = cls(db)
    elif name == 'DiagnosticView':
        w = cls(db_path=db.db_path)
    elif name == 'AuditLogView':
        w = cls(db_path=db.db_path)
    elif name == 'LoginWindow':
        w = cls(db_path=db.db_path)
    elif name == 'CompanyGateway':
        w = cls()
    elif name == 'StandaloneModuleWindow':
        from ui.dashboard import DashboardWidget
        w = cls(DashboardWidget(), 'Test', None)
    else:
        w = cls(db)
    w.show()
    app.processEvents()
    if hasattr(w, 'refresh'):
        w.refresh()
        app.processEvents()
    print('OK')
except Exception as e:
    print('FAIL:', e)
    traceback.print_exc()
"""


def main() -> int:
    failures = []
    for label, mod, cls in PAGES:
        code = SNIPPET.format(root=str(ROOT), mod=mod, cls=cls)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=45,
            cwd=str(ROOT),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 or "FAIL:" in out or "OK" not in out:
            failures.append((label, out.strip() or f"exit {proc.returncode}"))
            print(f"FAIL {label}")
        else:
            print(f"OK   {label}")

    print(f"\n{len(PAGES) - len(failures)} ok, {len(failures)} failed")
    for label, detail in failures:
        print(f"\n=== {label} ===\n{detail[:2000]}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
