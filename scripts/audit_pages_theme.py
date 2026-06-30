"""Audit page open + refresh_theme using production-like constructors."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAGES = [
    ("Dashboard", "ui.dashboard", "DashboardWidget", "w = cls()"),
    ("Company", "ui.company_page", "CompanyPageWidget", "w = cls(db)"),
    ("Products", "ui.products", "ProductsWidget", "w = cls(db)"),
    ("Debtors", "ui.debitor_creditor", "DebitorCreditorWidget", "w = cls(db)"),
    ("Bank Accounts", "ui.bank_accounts", "BankAccountWidget", "w = cls(db)"),
    ("Chart of Accounts", "ui.account_creation_page", "AccountCreationPageWidget", "w = cls(db)"),
    ("Sales Entry", "ui.sales_entry", "SalesEntryWidget", "w = cls(db)"),
    ("Purchase Entry", "ui.purchase_entry", "PurchaseEntryWidget", "w = cls(parent=host, db=db)"),
    ("Purchase Order", "ui.purchase_order", "PurchaseOrderUI", "w = cls(parent=None, db=db)"),
    ("Quotation", "ui.quotation_entry", "QuotationEntryWidget", "w = cls(db=db)"),
    ("PDC", "ui.pdc_page", "PDCPage", "w = cls(db)"),
    ("Credit/Debit Note", "ui.credit_debit_note_page", "CreditDebitNotePage", "w = cls(db)"),
    ("Sales Return", "ui.sales_return", "SalesReturnPageWidget", "w = cls(host, db)"),
    ("Purchase Return", "ui.purchase_return", "PurchaseReturnPageWidget", "w = cls(host, db)"),
    ("Ledger", "ui.ledger_page", "LedgerPageWidget", "w = cls(db)"),
    ("Trial Balance", "ui.trial_balance_page", "TrialBalancePageWidget", "w = cls(db)"),
    ("Profit & Loss", "ui.profit_loss_page", "ProfitLossPageWidget", "w = cls(db)"),
    ("Balance Sheet", "ui.balance_sheet_page", "BalanceSheetPageWidget", "w = cls(db)"),
    ("Stock Report", "ui.stock_report_page", "StockReportPageWidget", "w = cls(db=db)"),
    ("Stock Value", "ui.stock_value_page", "StockValuePageWidget", "w = cls(db=db)"),
    ("Day Book", "ui.day_book_page", "DayBookPageWidget", "w = cls(db)"),
    ("Cash Book", "ui.cash_book_page", "CashBookWidget", "w = cls(db)"),
    ("PDC Book", "ui.pdc_book_page", "PDCBookPageWidget", "w = cls(db)"),
    ("Journal Book", "ui.journal_book_page", "JournalBookPageWidget", "w = cls(db)"),
    ("Daily Stock Register", "ui.daily_stock_register_page", "DailyStockRegisterPageWidget", "w = cls(db)"),
    ("Price List", "ui.price_list_page", "PriceListPageWidget", "w = cls(db)"),
    ("Stock Checker", "ui.stock_checker_page", "StockCheckerPageWidget", "w = cls(db)"),
    ("Opening Balance", "ui.opening_balance_page", "OpeningBalanceWidget", "w = cls(db)"),
    ("Stock Adjustment", "ui.stock_adjustment_page", "StockAdjustmentWidget", "w = cls(db)"),
    ("Van Entry", "ui.van_entry_page", "VanEntryWidget", "w = cls(db)"),
    ("Van Return", "ui.van_return_page", "VanReturnWidget", "w = cls(db)"),
    ("Sales Book", "ui.sales_book_page", "SalesBookPageWidget", "from bizora_core.sales_book_logic import SalesBookLogic; w = cls(db, SalesBookLogic(db), 'Sales Book', ['Bill Wise'])"),
    ("Ledger Statement", "ui.ledger_statement_page", "LedgerStatementPageWidget", "w = cls(db)"),
    ("Bill History", "ui.bill_history_page", "BillHistoryPageWidget", "w = cls(db)"),
    ("Cash Tender History", "ui.cash_tender_history_page", "CashTenderHistoryPageWidget", "w = cls(db)"),
    ("Monthly Analysis", "ui.monthly_analysis_page", "MonthlyAnalysisWidget", "w = cls(db)"),
    ("GST Sales", "ui.gst_sales_report_page", "GSTSalesReportPage", "w = cls(db)"),
    ("GSTR-1", "ui.gstr1_page", "GSTR1Page", "w = cls(db)"),
    ("GST Purchase", "ui.gst_purchase_report_page", "GSTPurchaseReportPage", "w = cls(db)"),
    ("Collection Report", "ui.collection_report", "CollectionReportUI", "w = cls(db)"),
    ("Best Sellers", "ui.best_sellers_report", "BestSellersReport", "w = cls(db_path=db.db_path)"),
    ("Salesman Book", "ui.salesman_book", "SalesmanBook", "w = cls(db)"),
    ("Cash Receipt", "ui.cash_receipt_page", "CashReceiptPageWidget", "w = cls(db, 'cash_receipt', 'Cash Receipt')"),
    ("Cash Payment", "ui.cash_payment_page", "CashPaymentPageWidget", "w = cls(db, 'cash_payment', 'Cash Payment')"),
    ("Journal Entry", "ui.journal_entry_page", "JournalEntryPageWidget", "w = cls(db)"),
    ("Company Gateway", "ui.company_gateway", "CompanyGateway", "w = cls()"),
    ("Standalone Shell", "ui.standalone_window", "StandaloneModuleWindow", "from ui.dashboard import DashboardWidget; w = cls(DashboardWidget(), 'Test', None)"),
]

TEMPLATE = """
import os, sys, tempfile, traceback
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = {root!r}
sys.path.insert(0, ROOT)
from PySide6.QtWidgets import QApplication, QWidget
from db import Database, get_default_database_path
import importlib
app = QApplication.instance() or QApplication([])
host = QWidget()
try:
    try:
        db = Database(get_default_database_path())
    except Exception:
        db = Database(os.path.join(tempfile.mkdtemp(), 'audit.db'))
    mod = importlib.import_module({mod!r})
    cls = getattr(mod, {cls!r})
    {build}
    w.show()
    app.processEvents()
    if hasattr(w, 'refresh_theme'):
        w.refresh_theme()
        app.processEvents()
    w.hide()
    app.processEvents()
    print('OK')
except Exception as exc:
    print('FAIL:', exc)
    traceback.print_exc()
"""


def main() -> int:
    failures = []
    for label, mod, cls, build in PAGES:
        code = TEMPLATE.format(root=str(ROOT), mod=mod, cls=cls, build=build)
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(ROOT),
            )
        except subprocess.TimeoutExpired:
            failures.append((label, "TIMEOUT after 60s"))
            print(f"FAIL {label} (timeout)")
            continue
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 or "FAIL:" in out or "OK" not in out:
            failures.append((label, out.strip()[:2500]))
            print(f"FAIL {label}")
        else:
            print(f"OK   {label}")
    print(f"\n{len(PAGES) - len(failures)} passed, {len(failures)} failed")
    for label, detail in failures:
        print(f"\n=== {label} ===\n{detail}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
