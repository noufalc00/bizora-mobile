"""
Profit & Loss Account Page

Professional financial statement with Trading Account and Profit & Loss Account.
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
from ui.report_preview_utils import build_report_html
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class ProfitLossPageWidget(UiMemoryMixin, QWidget):
    """Profit & Loss Account page with compact Ledger-style layout."""

    def __init__(self, db=None):
        super().__init__()
        self.db = db
        self.reporting_engine = FinancialReportingEngine(self.db) if self.db else None
        self.company_id = active_company_manager.get_active_company_id()
        self.current_data = None
        self._init_ui()
        self._load_data()
        self._init_ui_memory()

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
        self.title_label = QLabel('Profit & Loss Account')
        self.title_label.setStyleSheet(page_heading_style(24))
        main_layout.addWidget(self.title_label)
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(10)
        from_label = QLabel('From Date:')
        from_label.setStyleSheet(compact_label_style())
        filter_layout.addWidget(from_label)
        self.from_date_edit = QDateEdit()
        self.from_date_edit.setDate(QDate.currentDate().addMonths(-12))
        prepare_report_date_edit(self.from_date_edit, style_sheet=compact_date_style())
        filter_layout.addWidget(self.from_date_edit)
        to_label = QLabel('To Date:')
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
        self.gross_profit_label = QLabel('Gross Profit: ₹0.00')
        self.gross_profit_label.setStyleSheet(theme.summary_profit_label_style(positive=True))
        summary_layout.addWidget(self.gross_profit_label)
        self.net_profit_label = QLabel('Net Profit: ₹0.00')
        self.net_profit_label.setStyleSheet(theme.summary_profit_label_style(positive=True))
        summary_layout.addWidget(self.net_profit_label)
        summary_layout.addStretch()
        main_layout.addLayout(summary_layout)
        tables_layout = QHBoxLayout()
        tables_layout.setSpacing(12)
        trading_frame = self._create_section_frame('TRADING ACCOUNT')
        self.trading_table = self._create_table()
        trading_frame.layout().addWidget(self.trading_table)
        tables_layout.addWidget(trading_frame, 1)
        pl_frame = self._create_section_frame('PROFIT & LOSS ACCOUNT')
        self.pl_table = self._create_table()
        pl_frame.layout().addWidget(self.pl_table)
        tables_layout.addWidget(pl_frame, 1)
        main_layout.addLayout(tables_layout, 1)

    def _create_section_frame(self, title: str) -> QFrame:
        """Create a compact section frame with title - Ledger style."""
        frame = QFrame()
        frame.setStyleSheet(report_filter_frame_style())
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setStyleSheet(report_summary_label_style())
        layout.addWidget(title_label)
        return frame

    def _create_table(self) -> QTableWidget:
        """Create a compact styled table widget - Ledger style."""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(['Particulars', 'Amount (₹)', 'Particulars', 'Amount (₹)'])
        apply_read_only_report_table_selection(table)
        table.setStyleSheet(financial_statement_table_style())
        table.setColumnWidth(0, 220)
        table.setColumnWidth(1, 100)
        table.setColumnWidth(2, 220)
        return table

    def _load_data(self):
        """Load and display Profit & Loss data from FinancialReportingEngine."""
        if not self.reporting_engine or not self.company_id:
            return
        try:
            from_date = qdate_to_db(self.from_date_edit.date())
            to_date = qdate_to_db(self.to_date_edit.date())
            self.current_data = self.reporting_engine.generate_profit_and_loss(self.company_id, from_date, to_date)
            self._update_summary_cards()
            self._populate_trading_account()
            self._populate_profit_loss_account()
        except Exception as e:
            print(f'Error loading P&L data: {e}')
            import traceback
            traceback.print_exc()

    def _update_summary_cards(self):
        """Update the summary labels with Gross Profit and Net Profit values - compact style."""
        if not self.current_data:
            return
        gross_profit = self.current_data.get('gross_profit', 0)
        net_profit = self.current_data.get('net_profit', 0)
        if gross_profit >= 0:
            self.gross_profit_label.setText(f'Gross Profit: {self._format_amount(gross_profit)}')
            self.gross_profit_label.setStyleSheet(theme.summary_profit_label_style(positive=True))
        else:
            self.gross_profit_label.setText(f'Gross Loss: {self._format_amount(abs(gross_profit))}')
            self.gross_profit_label.setStyleSheet(theme.summary_profit_label_style(positive=False))
        if net_profit >= 0:
            self.net_profit_label.setText(f'Net Profit: {self._format_amount(net_profit)}')
            self.net_profit_label.setStyleSheet(theme.summary_profit_label_style(positive=True))
        else:
            self.net_profit_label.setText(f'Net Loss: {self._format_amount(abs(net_profit))}')
            self.net_profit_label.setStyleSheet(theme.summary_profit_label_style(positive=False))

    def _populate_trading_account(self):
        """Populate Trading Account table - MVC: only display engine data."""
        table = self.trading_table
        table.setRowCount(0)
        if not self.current_data:
            return
        left_rows = []
        for acc in self.current_data['direct_expenses']:
            left_rows.append((f"To {acc['account_name']}", acc['balance']))
        left_total = self.current_data['total_direct_expenses']
        right_rows = []
        for acc in self.current_data['direct_incomes']:
            right_rows.append((f"By {acc['account_name']}", acc['balance']))
        right_total = self.current_data['total_direct_incomes']
        gross_profit = self.current_data['gross_profit']
        if gross_profit >= 0:
            left_rows.append(('To Gross Profit c/d', gross_profit))
            left_total += gross_profit
        else:
            right_rows.append(('By Gross Loss c/d', abs(gross_profit)))
            right_total += abs(gross_profit)
        final_total = max(left_total, right_total)
        left_rows.append(('Total', final_total))
        right_rows.append(('Total', final_total))
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
            if 'Total' in left_label or 'Total' in right_label:
                apply_financial_statement_row_style(table, i, row_kind='total')
            elif (
                'Gross Profit' in left_label
                or 'Gross Profit' in right_label
                or 'Gross Loss' in left_label
                or 'Gross Loss' in right_label
            ):
                apply_financial_statement_row_style(table, i, row_kind='opening')
        apply_adjustable_table_columns(table)

    def _populate_profit_loss_account(self):
        """Populate P&L Account table - MVC: only display engine data."""
        table = self.pl_table
        table.setRowCount(0)
        if not self.current_data:
            return
        left_rows = []
        for acc in self.current_data['indirect_expenses']:
            left_rows.append((f"To {acc['account_name']}", acc['balance']))
        left_total = self.current_data['total_indirect_expenses']
        gross_profit = self.current_data['gross_profit']
        if gross_profit >= 0:
            right_rows = [(f'By Gross Profit b/d', gross_profit)]
            right_total = gross_profit
        else:
            left_rows.append((f'To Gross Loss b/d', abs(gross_profit)))
            left_total += abs(gross_profit)
            right_rows = []
            right_total = 0
        for acc in self.current_data['indirect_incomes']:
            right_rows.append((f"By {acc['account_name']}", acc['balance']))
        right_total += self.current_data['total_indirect_incomes']
        net_profit = self.current_data['net_profit']
        if net_profit >= 0:
            left_rows.append(('To Net Profit', net_profit))
            left_total += net_profit
        else:
            right_rows.append(('By Net Loss', abs(net_profit)))
            right_total += abs(net_profit)
        final_total = max(left_total, right_total)
        left_rows.append(('Total', final_total))
        right_rows.append(('Total', final_total))
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
            if 'Total' in left_label or 'Total' in right_label:
                apply_financial_statement_row_style(table, i, row_kind='total')
            elif (
                'Gross Profit' in left_label
                or 'Gross Profit' in right_label
                or 'Gross Loss' in left_label
                or 'Gross Loss' in right_label
            ):
                apply_financial_statement_row_style(table, i, row_kind='opening')
            elif (
                'Net Profit' in left_label
                or 'Net Profit' in right_label
                or 'Net Loss' in left_label
                or 'Net Loss' in right_label
            ):
                apply_financial_statement_row_style(table, i, row_kind='opening')
        apply_adjustable_table_columns(table)

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
        """Export Profit & Loss data to Excel using centralized ExportEngine."""
        if not self.current_data:
            QMessageBox.information(self, 'No Data', 'Load Profit & Loss data first.')
            return
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save Profit & Loss', 'profit_loss.xlsx', 'Excel Files (*.xlsx)')
        if not file_path:
            return
        headers = ['Particulars', 'Amount (Dr)', 'Particulars', 'Amount (Cr)']
        data = []
        max_rows = max(self.trading_table.rowCount(), self.pl_table.rowCount())
        data.append(['TRADING ACCOUNT', '', '', ''])
        for row in range(self.trading_table.rowCount()):
            row_data = []
            for col in range(4):
                item = self.trading_table.item(row, col)
                row_data.append(item.text() if item else '')
            data.append(row_data)
        data.append(['', '', '', ''])
        data.append(['PROFIT & LOSS ACCOUNT', '', '', ''])
        for row in range(self.pl_table.rowCount()):
            row_data = []
            for col in range(4):
                item = self.pl_table.item(row, col)
                row_data.append(item.text() if item else '')
            data.append(row_data)
        export_engine = ExportEngine(self.db)
        result = export_engine.export_table_to_excel('Profit & Loss', headers, data, file_path)
        if result['success']:
            QMessageBox.information(self, 'Export', result['message'])
        else:
            QMessageBox.critical(self, 'Export Error', result['error'])

    def _export_pdf(self):
        """Open Profit & Loss data in the universal print/PDF preview dialog."""
        if not self.current_data:
            QMessageBox.information(self, 'No Data', 'Load Profit & Loss data first.')
            return
        headers = ['Particulars', 'Amount (Dr)', 'Particulars', 'Amount (Cr)']
        data = [['Trading Account', '', '', '']]
        for row in range(self.trading_table.rowCount()):
            data.append([self.trading_table.item(row, col).text() if self.trading_table.item(row, col) else '' for col in range(4)])
        data.append(['', '', '', ''])
        data.append(['Profit & Loss Account', '', '', ''])
        for row in range(self.pl_table.rowCount()):
            data.append([self.pl_table.item(row, col).text() if self.pl_table.item(row, col) else '' for col in range(4)])
        subtitle = f"{qdate_to_display(self.from_date_edit.date())} to {qdate_to_display(self.to_date_edit.date())}"
        html_string = build_report_html('Profit & Loss Account', headers, data, subtitle)
        dialog = UniversalPreviewDialog(html_string, self)
        dialog.exec()

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(page_background_style())
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(page_heading_style(24))
        if hasattr(self, 'trading_table'):
            self.trading_table.setStyleSheet(financial_statement_table_style())
        if hasattr(self, 'pl_table'):
            self.pl_table.setStyleSheet(financial_statement_table_style())
        self._update_summary_cards()
        if self.current_data:
            self._populate_trading_account()
            self._populate_profit_loss_account()