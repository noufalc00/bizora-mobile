"""
Best Sellers Report — top-selling products ranked by quantity within a date range.
"""
from __future__ import annotations
import contextlib
import sqlite3
from typing import List, Optional
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QDateEdit
from config import active_company_manager
from db import DB_PATH
from ui.book_report_common import BOOK_REPORT_ACTION_BUTTON_HEIGHT, compact_date_style, compact_label_style, compact_primary_button_style, compact_topbar_frame_style, page_background_style, page_heading_style, report_data_table_style, report_summary_label_style
from ui.table_header_utils import (
    apply_read_only_report_table_selection,
    finalize_report_table_layout,
)
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

def _safe_float(value) -> float:
    """Convert database numeric values to float safely."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def _format_quantity(value: float) -> str:
    """Format sold quantity with up to three decimal places."""
    return f'{value:,.3f}'

def _format_currency(value: float) -> str:
    """Format line revenue with rupee symbol and two decimal places."""
    return f'₹{value:,.2f}'

class BestSellersReport(UiMemoryMixin, QWidget):
    """Report page listing the top 50 products by quantity sold in a date range."""
    TABLE_HEADERS = ['Rank', 'Item Name', 'Total Quantity Sold', 'Total Revenue Generated']

    def __init__(self, db_path=None, parent=None):
        """
        Initialize the Best Sellers report widget.

        Args:
            db_path: SQLite database file path used for report queries.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.db_path = db_path or DB_PATH
        self.company_id: Optional[int] = None
        self._filter_labels: list[QLabel] = []
        self._build_ui()
        self._init_ui_memory(table_attrs=("results_table",))
        self._apply_results_table_layout()

    def _apply_theme_styles(self) -> None:
        """Apply current light/dark theme tokens to report widgets."""
        self.setStyleSheet(page_background_style())
        if hasattr(self, 'header_label'):
            self.header_label.setStyleSheet(page_heading_style(22))
        if hasattr(self, 'filter_frame'):
            self.filter_frame.setStyleSheet(compact_topbar_frame_style())
        prepare_report_date_edit(self.start_date, style_sheet=compact_date_style())
        prepare_report_date_edit(self.end_date, style_sheet=compact_date_style())
        self.generate_btn.setStyleSheet(compact_primary_button_style())
        self.summary_label.setStyleSheet(report_summary_label_style())
        self.results_table.setStyleSheet(report_data_table_style())
        for label in self._filter_labels:
            label.setStyleSheet(compact_label_style())

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self._apply_theme_styles()

    def _build_ui(self) -> None:
        """Build header, date filters, generate button, and results table."""
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)
        self.header_label = QLabel('Top Selling Products')
        self.header_label.setStyleSheet(page_heading_style(22))
        root.addWidget(self.header_label)
        filter_frame = QFrame()
        self.filter_frame = filter_frame
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_row = QHBoxLayout(filter_frame)
        filter_row.setContentsMargins(10, 8, 10, 8)
        filter_row.setSpacing(10)
        today = QDate.currentDate()
        month_start = QDate(today.year(), today.month(), 1)
        self.start_date = QDateEdit()
        self.start_date.setDate(month_start)
        prepare_report_date_edit(self.start_date, style_sheet=compact_date_style())
        self.end_date = QDateEdit()
        self.end_date.setDate(today)
        prepare_report_date_edit(self.end_date, style_sheet=compact_date_style())
        self.generate_btn = QPushButton('Generate Report')
        self.generate_btn.setFixedHeight(BOOK_REPORT_ACTION_BUTTON_HEIGHT)
        self.generate_btn.setMinimumWidth(130)
        btn_font = QFont(self.generate_btn.font())
        btn_font.setBold(True)
        self.generate_btn.setFont(btn_font)
        self.generate_btn.setStyleSheet(compact_primary_button_style())
        self.generate_btn.clicked.connect(self.generate_report)
        for label_text, widget in (('Start Date', self.start_date), ('End Date', self.end_date)):
            label = QLabel(label_text)
            label.setStyleSheet(compact_label_style())
            self._filter_labels.append(label)
            filter_row.addWidget(label)
            filter_row.addWidget(widget)
        filter_row.addStretch(1)
        filter_row.addWidget(self.generate_btn)
        root.addWidget(filter_frame)
        self.summary_label = QLabel('Ready — select dates and click Generate Report.')
        self.summary_label.setStyleSheet(report_summary_label_style())
        root.addWidget(self.summary_label)
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(len(self.TABLE_HEADERS))
        self.results_table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        apply_read_only_report_table_selection(self.results_table)
        header_font = QFont()
        header_font.setBold(True)
        self.results_table.horizontalHeader().setFont(header_font)
        finalize_report_table_layout(self.results_table, sl_no_column=0, sl_no_width=60)
        self.results_table.setStyleSheet(report_data_table_style())
        root.addWidget(self.results_table, 1)
        self._apply_theme_styles()

    def _apply_results_table_layout(self) -> None:
        """Keep columns user-resizable and restore any saved widths."""
        finalize_report_table_layout(self.results_table, sl_no_column=0, sl_no_width=60)
        self._restore_memory_table(self.results_table, "results_table")

    def refresh(self) -> None:
        """Resolve the active company context for subsequent report queries."""
        company = active_company_manager.get_active_company()
        self.company_id = company.get('id') if company else None
        if not self.company_id:
            self._clear_table()
            self.summary_label.setText('Please open a company first.')

    def generate_report(self) -> None:
        """
        Query top-selling products for the selected date range and populate the table.

        Revenue is sourced from ``sales_items.grand_total`` (line item total) joined
        to ``sales`` for invoice-date filtering and company scoping.
        """
        if not self.company_id:
            company = active_company_manager.get_active_company()
            self.company_id = company.get('id') if company else None
        if not self.company_id:
            QMessageBox.warning(self, 'Best Sellers Report', 'Please open a company first.')
            self._clear_table()
            return
        start_date = qdate_to_db(self.start_date.date())
        end_date = qdate_to_db(self.end_date.date())
        if self.start_date.date() > self.end_date.date():
            QMessageBox.warning(self, 'Best Sellers Report', 'Start Date cannot be after End Date.')
            return
        query = "\n            SELECT\n                si.product_id,\n                COALESCE(pr.name, 'Unknown Item') AS item_name,\n                COALESCE(SUM(si.quantity), 0) AS total_quantity,\n                COALESCE(SUM(si.grand_total), 0) AS total_revenue\n            FROM sales_items si\n            INNER JOIN sales s\n                ON s.id = si.sale_id\n               AND s.company_id = ?\n            LEFT JOIN products pr\n                ON pr.id = si.product_id\n               AND pr.company_id = s.company_id\n            WHERE s.invoice_date BETWEEN ? AND ?\n              AND COALESCE(s.status, 'Active') <> 'Voided'\n            GROUP BY si.product_id, COALESCE(pr.name, 'Unknown Item')\n            ORDER BY total_quantity DESC\n            LIMIT 50\n        "
        params = (self.company_id, start_date, end_date)
        try:
            with contextlib.closing(sqlite3.connect(self.db_path, timeout=30.0)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, 'Best Sellers Report', f'Could not generate report:\n{exc}')
            return
        self._populate_table(rows)
        self.summary_label.setText(f"Showing top {len(rows)} product(s) from {qdate_to_display(self.start_date.date())} to {qdate_to_display(self.end_date.date())}.")

    def _clear_table(self) -> None:
        """Remove all rows from the results table."""
        self.results_table.setRowCount(0)

    def _populate_table(self, rows: List[sqlite3.Row]) -> None:
        """Fill the results grid with rank, name, quantity, and revenue columns."""
        self.results_table.setRowCount(0)
        self.results_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            rank = row_index + 1
            item_name = str(row['item_name'] or 'Unknown Item')
            total_quantity = _safe_float(row['total_quantity'])
            total_revenue = _safe_float(row['total_revenue'])
            rank_item = QTableWidgetItem(str(rank))
            rank_item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter))
            name_item = QTableWidgetItem(item_name)
            name_item.setTextAlignment(int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
            qty_item = QTableWidgetItem(_format_quantity(total_quantity))
            qty_item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            revenue_item = QTableWidgetItem(_format_currency(total_revenue))
            revenue_item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            self.results_table.setItem(row_index, 0, rank_item)
            self.results_table.setItem(row_index, 1, name_item)
            self.results_table.setItem(row_index, 2, qty_item)
            self.results_table.setItem(row_index, 3, revenue_item)
        self._apply_results_table_layout()