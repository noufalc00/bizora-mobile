"""
Audit widget modules for safe theme refresh after live theme switching.
"""

from __future__ import annotations

import importlib
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication, QWidget


@dataclass
class AuditTarget:
    """One widget import/instantiate/refresh audit target."""

    label: str
    module_path: str
    class_name: str
    factory: Optional[Callable[[], QWidget]] = None


TARGETS = [
    AuditTarget("Salesman Record Book", "ui.salesman_book", "SalesmanBook"),
    AuditTarget("Best Sellers Report", "ui.best_sellers_report", "BestSellersReport"),
    AuditTarget("Monthly Analysis", "ui.monthly_analysis_page", "MonthlyAnalysisWidget"),
    AuditTarget("Sales Book", "ui.sales_book_page", "SalesBookPageWidget"),
    AuditTarget("Purchase Book", "ui.purchase_book_page", "PurchaseBookPageWidget"),
    AuditTarget("Sales Return Book", "ui.sales_return_book_page", "SalesReturnBookPageWidget"),
    AuditTarget("Purchase Return Book", "ui.purchase_return_book_page", "PurchaseReturnBookPageWidget"),
    AuditTarget("Day Book", "ui.day_book_page", "DayBookPageWidget"),
    AuditTarget("Cash Book", "ui.cash_book_page", "CashBookWidget"),
    AuditTarget("Ledger", "ui.ledger_page", "LedgerPageWidget"),
    AuditTarget("Trial Balance", "ui.trial_balance_page", "TrialBalancePageWidget"),
    AuditTarget("Dashboard", "ui.dashboard", "DashboardWidget"),
]


def _default_factory(module_path: str, class_name: str) -> Callable[[], QWidget]:
    """Build a default widget factory using the module class and shared Database."""

    def _create() -> QWidget:
        from db import Database

        module = importlib.import_module(module_path)
        widget_class = getattr(module, class_name)
        try:
            return widget_class(Database())
        except TypeError:
            return widget_class()

    return _create


def run_audit() -> int:
    """Instantiate widgets and call refresh_theme without recursion errors."""
    app = QApplication.instance() or QApplication(sys.argv)
    del app

    failures: list[str] = []
    passed = 0

    for target in TARGETS:
        factory = target.factory or _default_factory(target.module_path, target.class_name)
        try:
            widget = factory()
            if hasattr(widget, "refresh_theme"):
                widget.refresh_theme()
            passed += 1
            print(f"[PASS] {target.label}")
        except Exception as error:
            failures.append(f"{target.label}: {error}")
            print(f"[FAIL] {target.label}: {error}")
            traceback.print_exc()

    print(f"\nAudit complete: {passed} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_audit())
