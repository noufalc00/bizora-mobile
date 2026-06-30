"""
Salesman Record Book — performance summary by salesman for a date range.
"""
from __future__ import annotations
import contextlib
import sqlite3
from typing import Any, List, Optional
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QComboBox, QDateEdit, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget
from config import active_company_manager
from db import DB_PATH, Database
from ui import theme
from ui.book_report_common import BOOK_REPORT_ACTION_BUTTON_HEIGHT, compact_combo_style, compact_date_style, compact_label_style, compact_primary_button_style, page_heading_style, report_data_table_style, report_filter_frame_style, report_page_shell_style, report_summary_label_style
from ui.table_header_utils import (
    apply_read_only_report_table_selection,
    finalize_report_table_layout,
)
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
ALL_SALESMEN_LABEL = 'All Salesmen'
UNASSIGNED_LABEL = 'Unassigned'
TABLE_HEADERS = ['Salesman Name', 'Total Bills Generated', 'Total Revenue (Net Sales)', 'Avg Bill Value']

def _safe_float(value: Any) -> float:
    """Convert database numeric values to float safely."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def _format_currency(value: float) -> str:
    """Format monetary values to two decimal places."""
    return f'{value:,.2f}'

def _normalize_salesman_name(value: Any) -> str:
    """Map blank salesman values to a readable label."""
    cleaned = str(value or '').strip()
    return cleaned or UNASSIGNED_LABEL

class SalesmanBook(UiMemoryMixin, QWidget):
    """Report page summarizing bills and revenue by salesman."""

    def __init__(self, db: Optional[Database]=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.db_path = getattr(self.db, 'db_path', None) or DB_PATH
        self.company_id: Optional[int] = None
        self._filter_labels: list[QLabel] = []
        self._build_ui()
        self._apply_theme_styles()
        self.refresh()
        self._init_ui_memory(table_attrs=("results_table",))
        self._apply_results_table_layout()

    def _build_ui(self) -> None:
        """Build header, filters, generate button, and results table."""
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)
        self.header_label = QLabel('Salesman Performance Record')
        root.addWidget(self.header_label)
        self.filter_frame = QFrame()
        filter_row = QHBoxLayout(self.filter_frame)
        filter_row.setContentsMargins(10, 8, 10, 8)
        filter_row.setSpacing(10)
        today = QDate.currentDate()
        month_start = QDate(today.year(), today.month(), 1)
        self.salesman_combo = QComboBox()
        self.salesman_combo.setMinimumWidth(180)
        self.start_date = QDateEdit()
        self.start_date.setDate(month_start)
        prepare_report_date_edit(self.start_date, style_sheet=compact_date_style())
        self.end_date = QDateEdit()
        self.end_date.setDate(today)
        prepare_report_date_edit(self.end_date, style_sheet=compact_date_style())
        self.generate_btn = QPushButton('Generate Report')
        self.generate_btn.setFixedHeight(BOOK_REPORT_ACTION_BUTTON_HEIGHT)
        self.generate_btn.setMinimumWidth(140)
        btn_font = QFont(self.generate_btn.font())
        btn_font.setBold(True)
        self.generate_btn.setFont(btn_font)
        self.generate_btn.clicked.connect(self.generate_report)
        for label_text, widget in (('Salesman', self.salesman_combo), ('Start Date', self.start_date), ('End Date', self.end_date)):
            label = QLabel(label_text)
            self._filter_labels.append(label)
            filter_row.addWidget(label)
            filter_row.addWidget(widget)
        filter_row.addStretch(1)
        filter_row.addWidget(self.generate_btn)
        root.addWidget(self.filter_frame)
        self.summary_label = QLabel('Ready — select filters and click Generate Report.')
        root.addWidget(self.summary_label)
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(len(TABLE_HEADERS))
        self.results_table.setHorizontalHeaderLabels(TABLE_HEADERS)
        self.results_table.setAlternatingRowColors(True)
        apply_read_only_report_table_selection(self.results_table)
        header_font = QFont()
        header_font.setBold(True)
        self.results_table.horizontalHeader().setFont(header_font)
        finalize_report_table_layout(self.results_table)
        root.addWidget(self.results_table, 1)

    def _apply_results_table_layout(self) -> None:
        """Keep columns user-resizable and restore any saved widths."""
        finalize_report_table_layout(self.results_table)
        self._restore_memory_table(self.results_table, "results_table")

    def _style_date_calendar(self, date_edit: QDateEdit) -> None:
        """Apply shared calendar popup styling for light and dark themes."""
        calendar = date_edit.calendarWidget()
        if calendar is None:
            return
        calendar.setStyleSheet(theme.entry_calendar_style())
        theme.apply_calendar_day_formats(calendar)
        prev_btn = calendar.findChild(QToolButton, 'qt_calendar_prevmonth')
        if prev_btn:
            prev_btn.setArrowType(Qt.ArrowType.NoArrow)
            prev_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            prev_btn.setText('<')
            prev_btn.setFixedSize(24, 24)
        next_btn = calendar.findChild(QToolButton, 'qt_calendar_nextmonth')
        if next_btn:
            next_btn.setArrowType(Qt.ArrowType.NoArrow)
            next_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            next_btn.setText('>')
            next_btn.setFixedSize(24, 24)

    def _apply_theme_styles(self) -> None:
        """Apply current light/dark theme tokens to all report widgets."""
        self.setStyleSheet(report_page_shell_style())
        self.header_label.setStyleSheet(page_heading_style(22))
        self.filter_frame.setStyleSheet(report_filter_frame_style())
        self.summary_label.setStyleSheet(report_summary_label_style())
        self.salesman_combo.setStyleSheet(compact_combo_style())
        prepare_report_date_edit(self.start_date, style_sheet=compact_date_style())
        prepare_report_date_edit(self.end_date, style_sheet=compact_date_style())
        self.generate_btn.setStyleSheet(compact_primary_button_style())
        self.results_table.setStyleSheet(report_data_table_style())
        for label in self._filter_labels:
            label.setStyleSheet(compact_label_style())
        self._style_date_calendar(self.start_date)
        self._style_date_calendar(self.end_date)

    def refresh(self) -> None:
        """Resolve active company and refresh salesman filter options."""
        company = active_company_manager.get_active_company()
        self.company_id = company.get('id') if company else None
        self._load_salesman_filter()
        if not self.company_id:
            self._clear_table()
            self.summary_label.setText('Please open a company first.')

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self._apply_theme_styles()

    def _load_salesman_filter(self) -> None:
        """Populate salesman dropdown from the master table."""
        current_text = self.salesman_combo.currentText() if self.salesman_combo.count() else ALL_SALESMEN_LABEL
        self.salesman_combo.blockSignals(True)
        self.salesman_combo.clear()
        self.salesman_combo.addItem(ALL_SALESMEN_LABEL)
        try:
            salesmen = self.db.get_salesmen() or []
            for row in salesmen:
                name = str(row.get('name') or '').strip()
                if name:
                    self.salesman_combo.addItem(name)
        except Exception as exc:
            print(f'Error loading salesmen for report filter: {exc}')
        index = self.salesman_combo.findText(current_text, Qt.MatchFlag.MatchFixedString)
        self.salesman_combo.setCurrentIndex(index if index >= 0 else 0)
        self.salesman_combo.blockSignals(False)

    def generate_report(self) -> None:
        """Query salesman performance for the selected date range and populate the grid."""
        if not self.company_id:
            company = active_company_manager.get_active_company()
            self.company_id = company.get('id') if company else None
        if not self.company_id:
            QMessageBox.warning(self, 'Salesman Record Book', 'Please open a company first.')
            self._clear_table()
            return
        start_date = qdate_to_db(self.start_date.date())
        end_date = qdate_to_db(self.end_date.date())
        if self.start_date.date() > self.end_date.date():
            QMessageBox.warning(self, 'Salesman Record Book', 'Start Date cannot be after End Date.')
            return
        selected_salesman = self.salesman_combo.currentText().strip()
        salesman_expr = "COALESCE(NULLIF(TRIM(salesman), ''), ?)"
        query = f"\n            SELECT\n                {salesman_expr} AS salesman_name,\n                COUNT(invoice_number) AS total_bills,\n                COALESCE(SUM(grand_total), 0) AS total_revenue,\n                COALESCE(AVG(grand_total), 0) AS avg_bill_value\n            FROM sales\n            WHERE company_id = ?\n              AND invoice_date BETWEEN ? AND ?\n              AND COALESCE(status, 'Active') <> 'Voided'\n        "
        params: List[Any] = [UNASSIGNED_LABEL, self.company_id, start_date, end_date]
        if selected_salesman and selected_salesman != ALL_SALESMEN_LABEL:
            query += f'\n              AND {salesman_expr} = ?\n            '
            params.extend([UNASSIGNED_LABEL, selected_salesman])
        query += f'\n            GROUP BY {salesman_expr}\n            ORDER BY total_revenue DESC, salesman_name ASC\n        '
        params.append(UNASSIGNED_LABEL)
        try:
            with contextlib.closing(sqlite3.connect(self.db_path, timeout=30.0)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, 'Salesman Record Book', f'Could not generate report:\n{exc}')
            return
        self._populate_table(rows)
        self.summary_label.setText(f"Showing {len(rows)} salesman record(s) from {qdate_to_display(self.start_date.date())} to {qdate_to_display(self.end_date.date())}.")

    def _clear_table(self) -> None:
        """Remove all rows from the results table."""
        self.results_table.setRowCount(0)

    def _populate_table(self, rows: List[sqlite3.Row]) -> None:
        """Fill the results grid with salesman performance metrics."""
        self.results_table.blockSignals(True)
        self.results_table.setRowCount(0)
        self.results_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            salesman_name = _normalize_salesman_name(row['salesman_name'])
            total_bills = int(_safe_float(row['total_bills']))
            total_revenue = _safe_float(row['total_revenue'])
            avg_bill_value = _safe_float(row['avg_bill_value'])
            name_item = QTableWidgetItem(salesman_name)
            name_item.setTextAlignment(int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
            bills_item = QTableWidgetItem(str(total_bills))
            bills_item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            revenue_item = QTableWidgetItem(_format_currency(total_revenue))
            revenue_item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            avg_item = QTableWidgetItem(_format_currency(avg_bill_value))
            avg_item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            for col_index, item in enumerate((name_item, bills_item, revenue_item, avg_item)):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.results_table.setItem(row_index, col_index, item)
            if row_index % 25 == 0:
                QApplication.processEvents()
        self.results_table.blockSignals(False)
        self._apply_results_table_layout()