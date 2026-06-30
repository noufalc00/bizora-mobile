"""
Audit: instantiate every main-window page widget and report failures.

Usage (from project root):
    python scripts/audit_page_open.py
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from db import Database

# (label, module_path, class_name, constructor_args)
PAGE_SPECS: list[tuple[str, str, str, tuple]] = [
    ("Dashboard", "ui.dashboard", "DashboardWidget", ()),
    ("Company", "ui.company_page", "CompanyPageWidget", ()),
    ("New Company", "ui.new_company_page", "NewCompanyPageWidget", ()),
    ("Open Company", "ui.open_company_page", "OpenCompanyPageWidget", ()),
    ("Products", "ui.products", "ProductsWidget", ()),
    ("Debtors/Creditors", "ui.debitor_creditor", "DebitorCreditorWidget", ()),
    ("Bank Accounts", "ui.bank_accounts", "BankAccountWidget", ()),
    ("Chart of Accounts", "ui.account_creation_page", "AccountCreationPageWidget", ()),
    ("Sales Entry", "ui.sales_entry", "SalesEntryWidget", ()),
    ("Purchase Entry", "ui.purchase_entry", "PurchaseEntryWidget", ()),
    ("Purchase Order", "ui.purchase_order", "PurchaseOrderUI", ()),
    ("Quotation Entry", "ui.quotation_entry", "QuotationEntryWidget", ()),
    ("PDC", "ui.pdc_page", "PDCPage", ()),
    ("Credit/Debit Note", "ui.credit_debit_note_page", "CreditDebitNotePage", ()),
    ("Sales Return", "ui.sales_return", "SalesReturnPageWidget", ()),
    ("Purchase Return", "ui.purchase_return", "PurchaseReturnPageWidget", ()),
    ("Ledger", "ui.ledger_page", "LedgerPageWidget", ()),
    ("Trial Balance", "ui.trial_balance_page", "TrialBalancePageWidget", ()),
    ("Profit & Loss", "ui.profit_loss_page", "ProfitLossPageWidget", ()),
    ("Balance Sheet", "ui.balance_sheet_page", "BalanceSheetPageWidget", ()),
    ("Stock Report", "ui.stock_report_page", "StockReportPageWidget", ()),
    ("Stock Value", "ui.stock_value_page", "StockValuePageWidget", ()),
    ("Day Book", "ui.day_book_page", "DayBookPageWidget", ()),
    ("Cash Book", "ui.cash_book_page", "CashBookWidget", ()),
    ("PDC Book", "ui.pdc_book_page", "PDCBookPageWidget", ()),
    ("Journal Book", "ui.journal_book_page", "JournalBookPageWidget", ()),
    ("Daily Stock Register", "ui.daily_stock_register_page", "DailyStockRegisterPageWidget", ()),
    ("Price List", "ui.price_list_page", "PriceListPageWidget", ()),
    ("Stock Checker", "ui.stock_checker_page", "StockCheckerPageWidget", ()),
    ("Diagnostics", "ui.diagnostic_view", "DiagnosticView", ()),
    ("Audit Logs", "ui.audit_log_view", "AuditLogView", ()),
    ("Opening Balance", "ui.opening_balance_page", "OpeningBalanceWidget", ()),
    ("Stock Adjustment", "ui.stock_adjustment_page", "StockAdjustmentWidget", ()),
    ("Van Entry", "ui.van_entry_page", "VanEntryWidget", ()),
    ("Van Return", "ui.van_return_page", "VanReturnWidget", ()),
    ("Sales Book", "ui.sales_book_page", "SalesBookPageWidget", ()),
    ("Ledger Statement", "ui.ledger_statement_page", "LedgerStatementPageWidget", ()),
    ("Bill History", "ui.bill_history_page", "BillHistoryPageWidget", ()),
    ("Cash Tender History", "ui.cash_tender_history_page", "CashTenderHistoryPageWidget", ()),
    ("Sales Profit Book", "ui.sales_profit_book_page", "SalesProfitBookPageWidget", ()),
    ("Monthly Analysis", "ui.monthly_analysis_page", "MonthlyAnalysisWidget", ()),
    ("Quotation Book", "ui.quotation_book_page", "QuotationBookPageWidget", ()),
    ("Sales Return Book", "ui.sales_return_book_page", "SalesReturnBookPageWidget", ()),
    ("Purchase Book", "ui.purchase_book_page", "PurchaseBookPageWidget", ()),
    ("Purchase Order Book", "ui.purchase_order_book", "PurchaseOrderBookUI", ()),
    ("Purchase Return Book", "ui.purchase_return_book_page", "PurchaseReturnBookPageWidget", ()),
    ("Cash Receipt", "ui.cash_receipt_page", "CashReceiptPageWidget", ()),
    ("Cash Payment", "ui.cash_payment_page", "CashPaymentPageWidget", ()),
    ("Bank Receipt", "ui.bank_receipt_page", "BankReceiptPageWidget", ()),
    ("Bank Payment", "ui.bank_payment_page", "BankPaymentPageWidget", ()),
    ("Journal Entry", "ui.journal_entry_page", "JournalEntryPageWidget", ()),
    ("GST Sales Report", "ui.gst_sales_report_page", "GSTSalesReportPage", ()),
    ("GSTR-1", "ui.gstr1_page", "GSTR1Page", ()),
    ("GST Purchase Report", "ui.gst_purchase_report_page", "GSTPurchaseReportPage", ()),
    ("Collection Report", "ui.collection_report", "CollectionReportUI", ()),
    ("Best Sellers", "ui.best_sellers_report", "BestSellersReport", ()),
    ("Salesman Book", "ui.salesman_book", "SalesmanBook", ()),
    ("Net Sales Book", "ui.net_sales_book", "NetSalesBook", ()),
    ("Settings", "ui.settings", "SettingsWidget", ()),
    ("Theme Settings", "ui.theme_settings_page", "ThemeSettingsPage", ()),
]

BOOK_PAGE_EXTRA = [
    ("Sales Book logic", "logic.sales_book_logic", "SalesBookLogic"),
    ("Purchase Book logic", "logic.purchase_book_logic", "PurchaseBookLogic"),
]


def _make_db() -> Database:
    temp_dir = tempfile.mkdtemp(prefix="fpa_audit_")
    db_path = os.path.join(temp_dir, "audit.db")
    return Database(db_type="sqlite", db_path=db_path)


def _construct(cls, db: Database, extra_args: tuple):
    if extra_args:
        return cls(db, *extra_args)
    try:
        return cls(db)
    except TypeError:
        return cls()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    db = _make_db()

    failures: list[tuple[str, str]] = []
    ok = 0

    for label, module_path, class_name, extra in PAGE_SPECS:
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)

            if class_name.endswith("BookPageWidget"):
                logic_mod = importlib.import_module(module_path.replace("_page", "_logic").replace("ui.", "logic."))
                # fallback per known book pages
                logic_map = {
                    "SalesBookPageWidget": ("logic.sales_book_logic", "SalesBookLogic"),
                    "PurchaseBookPageWidget": ("logic.purchase_book_logic", "PurchaseBookLogic"),
                    "SalesReturnBookPageWidget": ("logic.sales_return_book_logic", "SalesReturnBookLogic"),
                    "PurchaseReturnBookPageWidget": ("logic.purchase_return_book_logic", "PurchaseReturnBookLogic"),
                    "QuotationBookPageWidget": ("logic.quotation_book_logic", "QuotationBookLogic"),
                    "SalesProfitBookPageWidget": ("logic.sales_profit_book_logic", "SalesProfitBookLogic"),
                }
                if class_name in logic_map:
                    lm, ln = logic_map[class_name]
                    logic_cls = getattr(importlib.import_module(lm), ln)
                    widget = cls(db, logic_cls(db), "Audit", ["Bill Wise"])
                else:
                    widget = cls(db, None, "Audit", ["Bill Wise"])
            elif class_name == "PurchaseOrderUI":
                widget = cls(db)
            elif class_name in {"BestSellersReport", "NetSalesBook"}:
                widget = cls(db_path=db.db_path)
            elif class_name == "SalesmanBook":
                widget = cls(db)
            elif class_name == "CollectionReportUI":
                widget = cls(db)
            elif class_name == "DiagnosticView":
                widget = cls(db_path=db.db_path)
            elif class_name == "AuditLogView":
                widget = cls(db_path=db.db_path)
            else:
                widget = _construct(cls, db, extra)

            widget.show()
            app.processEvents()
            if hasattr(widget, "refresh"):
                widget.refresh()
                app.processEvents()
            widget.hide()
            app.processEvents()
            ok += 1
            print(f"OK  {label}")
        except Exception as exc:
            tb = traceback.format_exc()
            failures.append((label, f"{exc}\n{tb}"))
            print(f"FAIL {label}: {exc}")

    print(f"\n{ok} passed, {len(failures)} failed")
    if failures:
        print("\n=== FAILURE DETAILS ===")
        for label, detail in failures:
            print(f"\n--- {label} ---")
            print(detail)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
