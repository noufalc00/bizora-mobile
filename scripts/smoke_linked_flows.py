"""
Smoke-test cross-page UI flows that are not covered by simple page open.

These paths often fail with missing imports or broken popup wiring while the
host page still opens fine (e.g. Day Book -> View Net Sales Book).

Usage (from project root):
    python scripts/smoke_linked_flows.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from config import active_company_manager
from db import Database


def _make_db() -> Database:
    """Create an isolated temporary database for smoke tests."""
    temp_dir = tempfile.mkdtemp(prefix="fpa_smoke_")
    return Database(db_type="sqlite", db_path=os.path.join(temp_dir, "smoke.db"))


@contextmanager
def _seed_smoke_company(db: Database, company_id: int = 1):
    """Provide a fake active company so refresh paths do not open modal dialogs."""
    previous_company = active_company_manager.get_active_company()
    try:
        try:
            placeholder = db._get_placeholder()
            db.execute_update(
                f"""
                INSERT OR IGNORE INTO companies (id, business_name, is_active)
                VALUES ({placeholder}, {placeholder}, 0)
                """,
                (company_id, "Smoke Test Company"),
            )
        except Exception:
            pass
        active_company_manager.set_active_company(
            {"id": company_id, "business_name": "Smoke Test Company"}
        )
        yield company_id
    finally:
        if previous_company:
            active_company_manager.set_active_company(previous_company)
        else:
            active_company_manager.clear_active_company()


@contextmanager
def _suppress_blocking_dialogs():
    """Prevent QMessageBox calls from blocking headless smoke runs."""
    originals = {
        name: getattr(QMessageBox, name)
        for name in ("warning", "information", "critical", "question")
    }

    def _question(*_args, **_kwargs):
        return QMessageBox.StandardButton.No

    for name in ("warning", "information", "critical"):
        setattr(QMessageBox, name, staticmethod(lambda *_a, **_k: None))
    QMessageBox.question = staticmethod(_question)
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(QMessageBox, name, original)


def _run_flow(label: str, callback) -> tuple[bool, str]:
    """Execute one linked-flow callback and capture failures."""
    try:
        with _suppress_blocking_dialogs():
            callback()
        print(f"OK   {label}")
        return True, ""
    except Exception as exc:
        detail = f"{exc}\n{traceback.format_exc()}"
        print(f"FAIL {label}: {exc}")
        return False, detail


def _test_net_sales_book_direct(db: Database) -> None:
    """Net Sales Book must construct and refresh without NameError."""
    from ui.net_sales_book import NetSalesBook

    with _seed_smoke_company(db):
        widget = NetSalesBook(db_path=db.db_path)
        widget.show()
        QApplication.processEvents()
        widget.refresh()
        QApplication.processEvents()
        widget.hide()


def _test_net_sales_book_popup(db: Database) -> None:
    """Popup opener used by Day Book and Sales Book must not crash."""
    from ui.net_sales_book import open_net_sales_book_window

    host = QWidget()
    with _seed_smoke_company(db):
        dialog = open_net_sales_book_window(host, db_path=db.db_path)
        QApplication.processEvents()
        dialog.close()
        QApplication.processEvents()


def _test_bill_history_refresh(db: Database) -> None:
    """Bill History filter bar and refresh path must stay import-safe."""
    from ui.bill_history_page import BillHistoryPageWidget

    with _seed_smoke_company(db):
        page = BillHistoryPageWidget(db=db)
        page.show()
        QApplication.processEvents()
        page.refresh()
        QApplication.processEvents()
        page.hide()


def _test_pdc_quick_create_button(db: Database) -> None:
    """PDC bank quick-create control must build with 3D styling hooks."""
    from ui.pdc_page import PDCPage

    with _seed_smoke_company(db):
        page = PDCPage(db=db)
        button = page._quick_create_button()
        assert button.text() == "+"
        page.hide()


def _test_book_report_party_completer(db: Database) -> None:
    """Sales/Purchase book party search popup must use light-theme list colors."""
    from bizora_core.sales_book_logic import SalesBookLogic
    from ui.book_report_common import BookReportPageWidget

    with _seed_smoke_company(db):
        page = BookReportPageWidget(db, SalesBookLogic(db), "Sales Book", ["Bill Wise"])
        page.show()
        QApplication.processEvents()
        popup = page.party_completer.popup()
        stylesheet = popup.styleSheet() if popup is not None else ""
        assert stylesheet.strip(), "Party completer popup has no theme stylesheet"
        page.party_model.setStringList(["All Parties", "Jamshy", "Jamshy 1"])
        page.party_search.setText("j")
        page.party_completer.complete()
        QApplication.processEvents()
        page.hide()


def _test_trial_balance_filter_bar(db: Database) -> None:
    """Trial Balance must build default FY date range without NameError."""
    from ui.trial_balance_page import TrialBalancePageWidget

    with _seed_smoke_company(db):
        page = TrialBalancePageWidget(db=db)
        page.show()
        QApplication.processEvents()
        assert page.from_date.date().isValid()
        assert page.to_date.date().isValid()
        page.hide()


def main() -> int:
    """Run all registered linked-flow smoke tests."""
    app = QApplication.instance() or QApplication(sys.argv)
    db = _make_db()

    flows = [
        ("Net Sales Book (direct)", lambda: _test_net_sales_book_direct(db)),
        ("Net Sales Book (popup host)", lambda: _test_net_sales_book_popup(db)),
        ("Bill History refresh", lambda: _test_bill_history_refresh(db)),
        ("Book report party completer", lambda: _test_book_report_party_completer(db)),
        ("PDC quick-create button", lambda: _test_pdc_quick_create_button(db)),
        ("Trial Balance filter bar", lambda: _test_trial_balance_filter_bar(db)),
    ]

    failures: list[tuple[str, str]] = []
    for label, callback in flows:
        ok, detail = _run_flow(label, callback)
        if not ok:
            failures.append((label, detail))

    print(f"\n{len(flows) - len(failures)} passed, {len(failures)} failed")
    if failures:
        print("\n=== LINKED FLOW FAILURES ===")
        for label, detail in failures:
            print(f"\n--- {label} ---")
            print(detail)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
