"""
Sales Wise Profit Book page.
Shows Bill-wise, Party-wise, and Item-wise profit reports using historical cost snapshot.
"""

from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

from db import Database
from bizora_core.sales_profit_book_logic import SalesProfitBookLogic
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from bizora_core.book_report_common import safe_float
from .book_report_common import BookReportPageWidget


class SalesProfitReportWorker(QObject):
    """Load Sales Wise Profit rows on a worker-owned database connection."""

    data_ready = Signal(list)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type, db_path, method_name: str, args: tuple):
        """Initialize the worker with an immutable filter snapshot."""
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.method_name = method_name
        self.args = args

    def run(self):
        """Fetch profit rows and emit them back to the GUI thread."""
        worker_db = None
        try:
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            logic = SalesProfitBookLogic(worker_db)
            method = getattr(logic, self.method_name)
            result = method(*self.args)
            if not result.get("success"):
                self.error.emit(result.get("message") or "Unable to load profit report.")
                return
            self.data_ready.emit(result.get("data", []))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                try:
                    worker_db.force_disconnect()
                except Exception:
                    pass
            self.finished.emit()


class SalesProfitBookPageWidget(BookReportPageWidget):
    """UI page for Sales Wise Profit Book."""

    def __init__(self, db: Optional[Database] = None, parent=None):
        """Initialize the profit report page with dedicated report loading."""
        db = db or Database()
        self.logic_instance = SalesProfitBookLogic(db)
        super().__init__(
            db,
            self.logic_instance,
            "Sales Wise Profit Book",
            ["Bill Wise Profit", "Party Wise Profit", "Item Wise Profit"],
            parent,
        )
        self.footer_total_titles["rows"] = "Sales Value"
        self.footer_total_titles["total_tax"] = "Purchase Value"
        self.footer_total_titles["total_amount"] = "Net Profit"
        self._set_footer_total("rows", "0.00")
        self._set_footer_total("total_tax", "0.00")
        self._set_footer_total("total_amount", "0.00")

    def _start_report_worker(self, method_name: str, args: tuple, report_key: str):
        """Start the module-specific profit worker for custom SQL and math."""
        if self._loading:
            return
        db_type = getattr(self.db, "db_type", None)
        db_path = getattr(self.db, "db_path", None)
        thread = QThread(self)
        worker = SalesProfitReportWorker(db_type, db_path, method_name, args)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(
            lambda rows, key=report_key: self.populate_table(rows, key)
        )
        worker.error.connect(
            lambda message: self.show_no_data(f"Error loading profit report: {message}")
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_report_worker_finished)
        self._report_thread = thread
        self._report_worker = worker
        self._set_loading_state(True)
        thread.start()

    def populate_table(self, rows, key: str):
        """Populate the table on the GUI thread and show profit totals."""
        super().populate_table(rows, key)
        if not rows:
            return

        total_sales = sum(safe_float(row.get("sales_value")) for row in rows)
        total_purchase = sum(safe_float(row.get("cost_value")) for row in rows)
        total_profit = sum(safe_float(row.get("profit")) for row in rows)
        self.summary_label.setText(
            f"Rows: {len(rows)}    Sales Value: {total_sales:,.2f}    "
            f"Purchase Value: {total_purchase:,.2f}    Net Profit: {total_profit:,.2f}"
        )
        self.footer_total_titles["total_tax"] = "Purchase Value"
        self.footer_total_titles["total_amount"] = "Net Profit"
        self._set_footer_total("rows", f"{total_sales:,.2f}")
        self._set_footer_total("total_tax", f"{total_purchase:,.2f}")
        self._set_footer_total("total_amount", f"{total_profit:,.2f}")