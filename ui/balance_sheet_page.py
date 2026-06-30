"""
Balance Sheet Page

Professional financial statement with T-Format: Liabilities & Capital (Left), Assets (Right).
MVC Pattern: UI only displays data from FinancialReportingEngine, no calculations.
Compact Ledger-style layout fitting all content without scrolling.
"""
from datetime import date
from typing import Dict, Any, Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFrame, QAbstractItemView, QFileDialog
from PySide6.QtCore import Qt, QDate
from config import COLORS, active_company_manager
from bizora_core.financial_reporting_engine import FinancialReportingEngine
from bizora_core.export_engine import ExportEngine
from ui import theme
from ui.book_report_common import compact_label_style, compact_input_style, compact_date_style, compact_primary_button_style, compact_topbar_frame_style, page_background_style, page_heading_style, report_filter_frame_style, report_summary_label_style, financial_statement_table_style, apply_financial_statement_row_style
from ui.report_preview_utils import table_widget_to_html
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class BalanceSheetPageWidget(UiMemoryMixin, QWidget):
    """Balance Sheet page with compact Ledger-style T-Format layout."""

    def __init__(self, db=None):
        super().__init__()
        self.db = db
        self.reporting_engine = FinancialReportingEngine(self.db) if self.db else None
        self.company_id = active_company_manager.get_active_company_id()
        self.current_data = None
        self._init_ui()
        self._load_data()
        self._init_ui_memory(table_attrs=("balance_sheet_table",))

    def showEvent(self, event):
        """Refresh data when page is shown."""
        super().showEvent(event)
        self.company_id = active_company_manager.get_active_company_id()
        if self.company_id and (not self.reporting_engine):
            self.reporting_engine = FinancialReportingEngine(self.db)
        self._load_data()

    def _init_ui(self):
        """Initialize the UI layout - compact Ledger style."""
        self.setStyleSheet(page_background_style())
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        self.title_label = QLabel('Balance Sheet')
        self.title_label.setStyleSheet(page_heading_style(24))
        main_layout.addWidget(self.title_label)
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(10)
        to_label = QLabel('As On Date:')
        to_label.setStyleSheet(compact_label_style())
        filter_layout.addWidget(to_label)
        self.to_date_edit = QDateEdit()
        self.to_date_edit.setDate(QDate.currentDate())
        prepare_report_date_edit(self.to_date_edit, style_sheet=compact_date_style())
        filter_layout.addWidget(self.to_date_edit)
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setStyleSheet(compact_primary_button_style())
        self.refresh_btn.clicked.connect(self._load_data)
        filter_layout.addWidget(self.refresh_btn)
        self.export_excel_btn = QPushButton('Export Excel')
        self.export_excel_btn.setStyleSheet(compact_primary_button_style())
        self.export_excel_btn.clicked.connect(self._export_excel)
        filter_layout.addWidget(self.export_excel_btn)
        self.export_pdf_btn = QPushButton('Export PDF')
        self.export_pdf_btn.setStyleSheet(compact_primary_button_style())
        self.export_pdf_btn.clicked.connect(self._export_pdf)
        filter_layout.addWidget(self.export_pdf_btn)
        filter_layout.addStretch()
        main_layout.addWidget(filter_frame)
        summary_layout = QHBoxLayout()
        self.net_profit_label = QLabel('Net Profit: ₹0.00')
        self.net_profit_label.setStyleSheet(theme.summary_profit_label_style(positive=True))
        summary_layout.addWidget(self.net_profit_label)
        summary_layout.addStretch()
        main_layout.addLayout(summary_layout)
        table_frame = QFrame()
        table_frame.setStyleSheet(report_filter_frame_style())
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(8, 6, 8, 6)
        table_layout.setSpacing(6)
        self.section_title_label = QLabel('BALANCE SHEET')
        self.section_title_label.setStyleSheet(report_summary_label_style())
        table_layout.addWidget(self.section_title_label)
        self.balance_sheet_table = self._create_table()
        table_layout.addWidget(self.balance_sheet_table)
        main_layout.addWidget(table_frame, 1)

    def _create_table(self) -> QTableWidget:
        """Create a compact styled table widget - Ledger style T-Format."""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(['Liabilities', 'Amount (₹)', 'Assets', 'Amount (₹)'])
        apply_read_only_report_table_selection(table)
        table.setColumnWidth(0, 250)
        table.setColumnWidth(1, 120)
        table.setColumnWidth(2, 250)
        table.setStyleSheet(financial_statement_table_style())
        return table

    def _load_data(self):
        """Load and display Balance Sheet data from FinancialReportingEngine."""
        if not self.reporting_engine or not self.company_id:
            return
        try:
            to_date = qdate_to_db(self.to_date_edit.date())
            self.current_data = self.reporting_engine.generate_balance_sheet(self.company_id, to_date)
            self._update_summary_label()
            self._populate_balance_sheet()
        except Exception as e:
            print(f'Error loading Balance Sheet data: {e}')
            import traceback
            traceback.print_exc()

    def _update_summary_label(self):
        """Update the summary label with Net Profit/Loss value - compact style."""
        if not self.current_data:
            return
        net_profit = self.current_data.get('net_profit', 0)
        if net_profit >= 0:
            self.net_profit_label.setText(f'Net Profit: {self._format_amount(net_profit)}')
            self.net_profit_label.setStyleSheet(theme.summary_profit_label_style(positive=True))
        else:
            self.net_profit_label.setText(f'Net Loss: {self._format_amount(abs(net_profit))}')
            self.net_profit_label.setStyleSheet(theme.summary_profit_label_style(positive=False))

    def _populate_balance_sheet(self):
        """Populate Balance Sheet table - MVC: only display engine data."""
        table = self.balance_sheet_table
        table.setRowCount(0)
        if not self.current_data:
            return
        left_rows = []
        for acc in self.current_data['capital_accounts']:
            left_rows.append((acc['account_name'], acc['balance']))
        net_profit = self.current_data['net_profit']
        if net_profit >= 0:
            left_rows.append(('Add: Net Profit', net_profit))
        else:
            left_rows.append(('Less: Net Loss', abs(net_profit)))
        for acc in self.current_data['current_liabilities']:
            left_rows.append((acc['account_name'], acc['balance']))
        left_total = self.current_data['adjusted_capital'] + self.current_data['total_liabilities']
        right_rows = []
        for acc in self.current_data['fixed_assets']:
            right_rows.append((acc['account_name'], acc['balance']))
        for acc in self.current_data['current_assets']:
            right_rows.append((acc['account_name'], acc['balance']))
        right_total = self.current_data['total_assets']
        left_display_total = abs(left_total)
        right_display_total = abs(right_total)
        left_rows.append(('Total', left_display_total))
        right_rows.append(('Total', right_display_total))
        max_rows = max(len(left_rows), len(right_rows))
        table.setRowCount(max_rows)
        for i in range(max_rows):
            left_label = left_rows[i][0] if i < len(left_rows) else ''
            left_amount = left_rows[i][1] if i < len(left_rows) else 0
            right_label = right_rows[i][0] if i < len(right_rows) else ''
            right_amount = right_rows[i][1] if i < len(right_rows) else 0
            table.setItem(i, 0, QTableWidgetItem(left_label))
            table.setItem(i, 1, QTableWidgetItem(self._format_amount(left_amount)))
            table.setItem(i, 2, QTableWidgetItem(right_label))
            table.setItem(i, 3, QTableWidgetItem(self._format_amount(right_amount)))
            if left_label == 'Total' or right_label == 'Total':
                apply_financial_statement_row_style(table, i, row_kind='total')
            elif left_label in ('Add: Net Profit', 'Less: Net Loss'):
                apply_financial_statement_row_style(table, i, row_kind='opening')
        apply_adjustable_table_columns(table)
        self._restore_memory_table(table, "balance_sheet_table")

    def _format_amount(self, amount) -> str:
        """Format amount with currency symbol."""
        if amount is None or amount == 0:
            return ''
        try:
            float_amount = float(amount)
            if float_amount == 0:
                return ''
            return f'₹{float_amount:,.2f}'
        except (ValueError, TypeError):
            return ''

    def _export_excel(self):
        """Export Balance Sheet data to Excel using centralized ExportEngine."""
        if not self.current_data:
            QMessageBox.information(self, 'No Data', 'Load Balance Sheet data first.')
            return
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save Balance Sheet', 'balance_sheet.xlsx', 'Excel Files (*.xlsx)')
        if not file_path:
            return
        headers = ['Liabilities', 'Amount (₹)', 'Assets', 'Amount (₹)']
        data = []
        for row in range(self.balance_sheet_table.rowCount()):
            row_data = []
            for col in range(4):
                item = self.balance_sheet_table.item(row, col)
                row_data.append(item.text() if item else '')
            data.append(row_data)
        export_engine = ExportEngine(self.db)
        result = export_engine.export_table_to_excel('Balance Sheet', headers, data, file_path)
        if result['success']:
            QMessageBox.information(self, 'Export', result['message'])
        else:
            QMessageBox.critical(self, 'Export Error', result['error'])

    def _export_pdf(self):
        """Open Balance Sheet data in the universal print/PDF preview dialog."""
        if not self.current_data:
            QMessageBox.information(self, 'No Data', 'Load Balance Sheet data first.')
            return
        subtitle = f"As on {qdate_to_display(self.to_date_edit.date())}"
        html_string = table_widget_to_html(self.balance_sheet_table, 'Balance Sheet', subtitle)
        dialog = UniversalPreviewDialog(html_string, self)
        dialog.exec()

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(page_background_style())
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(page_heading_style(24))
        if hasattr(self, 'section_title_label'):
            self.section_title_label.setStyleSheet(report_summary_label_style())
        if hasattr(self, 'balance_sheet_table'):
            self.balance_sheet_table.setStyleSheet(financial_statement_table_style())
        self._update_summary_label()
        if self.current_data:
            self._populate_balance_sheet()