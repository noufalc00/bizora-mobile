"""
Cash Book Page Widget
Displays cash account inflow/outflow transactions from ledger_entries.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem, QFrame, QAbstractItemView, QMessageBox
from PySide6.QtCore import Qt, QDate, QTimer, QObject, QThread, Signal
from PySide6.QtGui import QFont, QColor
from config import COLORS, resolve_active_company_id
from bizora_core.cash_book_logic import CashBookLogic
from bizora_core.financial_reporting_engine import FinancialReportingEngine
from db import Database
from ui.book_report_common import book_report_special_row_colors, compact_label_style, compact_date_style, compact_primary_button_style, compact_secondary_button_style, compact_topbar_frame_style, page_background_style, page_heading_style, report_data_table_style
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.report_preview_utils import table_widget_to_html
from ui.table_header_utils import apply_read_only_report_table_selection
from ui.ui_memory import UiMemoryMixin

class CashBookWorker(QObject):
    """Load cash book data on a worker-owned database connection."""
    data_ready = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type, db_path, company_id, from_date, to_date):
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id
        self.from_date = from_date
        self.to_date = to_date

    def run(self):
        worker_db = None
        try:
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            result = CashBookLogic(worker_db).get_cash_book(self.company_id, self.from_date, self.to_date)
            if not result.get('success'):
                self.error.emit(result.get('message') or 'Unable to load cash book.')
                return
            self.data_ready.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                worker_db.force_disconnect()
            self.finished.emit()

class CashBookWidget(UiMemoryMixin, QWidget):

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.cash_logic = CashBookLogic(self.db)
        self.reporting_engine = FinancialReportingEngine(self.db)
        self.company_id = resolve_active_company_id(self.db)
        self._loading = False
        self._cash_thread = None
        self._cash_worker = None
        self._last_table_data = None
        self.setup_ui()
        today = QDate.currentDate()
        self.from_date.setDate(today.addDays(-today.day() + 1))
        self.to_date.setDate(today)
        QTimer.singleShot(100, self.load_cash_book)
        self._init_ui_memory()

    def setup_ui(self):
        self.setStyleSheet(page_background_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        header = QHBoxLayout()
        self.title_label = QLabel('Cash Book')
        self.title_label.setStyleSheet(page_heading_style(24))
        header.addWidget(self.title_label)
        header.addStretch()
        layout.addLayout(header)
        self.setup_filters(layout)
        self.setup_table(layout)
        self.setup_summary_strip(layout)

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(page_background_style())
        self.title_label.setStyleSheet(page_heading_style(24))
        self.table.setStyleSheet(report_data_table_style())
        for widget, style_fn in (
            (self.from_date, compact_date_style),
            (self.to_date, compact_date_style),
        ):
            prepare_report_date_edit(widget, style_sheet=style_fn())
        for btn in (self.view_btn,):
            btn.setStyleSheet(compact_primary_button_style())
        for btn in (self.print_btn, self.export_btn):
            btn.setStyleSheet(compact_secondary_button_style())
        summary_frame = self.total_receipts_label.parentWidget()
        if summary_frame is not None:
            summary_frame.setStyleSheet(
                f"\n            QFrame {{\n                background-color: {COLORS['surface']};\n"
                f"                border: 1px solid {COLORS['border']};\n"
                f"                border-radius: 4px;\n                padding: 10px;\n            }}\n        "
            )
        for lbl in (self.total_receipts_label, self.total_payments_label):
            lbl.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']};")
        if self._last_table_data is not None:
            self.populate_table(self._last_table_data)

    def setup_filters(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet(compact_topbar_frame_style())
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)
        from_lbl = QLabel('From Date:')
        from_lbl.setStyleSheet(compact_label_style())
        layout.addWidget(from_lbl)
        self.from_date = QDateEdit()
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        layout.addWidget(self.from_date)
        to_lbl = QLabel('To Date:')
        to_lbl.setStyleSheet(compact_label_style())
        layout.addWidget(to_lbl)
        self.to_date = QDateEdit()
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        layout.addWidget(self.to_date)
        layout.addStretch()
        self.view_btn = QPushButton('View')
        self.view_btn.setStyleSheet(compact_primary_button_style())
        self.view_btn.setFixedWidth(80)
        self.view_btn.clicked.connect(self.load_cash_book)
        layout.addWidget(self.view_btn)
        self.print_btn = QPushButton('Print')
        self.print_btn.setStyleSheet(compact_secondary_button_style())
        self.print_btn.setFixedWidth(80)
        self.print_btn.setEnabled(False)
        self.print_btn.clicked.connect(self.show_preview)
        layout.addWidget(self.print_btn)
        self.export_btn = QPushButton('Export')
        self.export_btn.setStyleSheet(compact_secondary_button_style())
        self.export_btn.setFixedWidth(80)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.show_preview)
        layout.addWidget(self.export_btn)
        parent_layout.addWidget(frame)

    def setup_table(self, parent_layout):
        self.table = QTableWidget()
        self.table.setStyleSheet(report_data_table_style())
        apply_read_only_report_table_selection(self.table)
        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(['SL No', 'Date', 'Voucher No', 'Type', 'Particulars', 'Narration', 'Receipt (Dr)', 'Payment (Cr)', 'Balance'])
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 200)
        self.table.setColumnWidth(6, 100)
        self.table.setColumnWidth(7, 100)
        self.table.setColumnWidth(8, 100)
        parent_layout.addWidget(self.table)

    def setup_summary_strip(self, parent_layout):
        summary_frame = QFrame()
        summary_frame.setStyleSheet(f"\n            QFrame {{\n                background-color: {COLORS['surface']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 4px;\n                padding: 10px;\n            }}\n        ")
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setSpacing(20)
        self.total_receipts_label = QLabel('Total Receipts: ₹0.00')
        self.total_receipts_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']};")
        summary_layout.addWidget(self.total_receipts_label)
        self.total_payments_label = QLabel('Total Payments: ₹0.00')
        self.total_payments_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']};")
        summary_layout.addWidget(self.total_payments_label)
        self.closing_balance_label = QLabel('Closing Balance: ₹0.00')
        self.closing_balance_label.setStyleSheet(f'font-weight: bold; color: #10B981;')
        summary_layout.addWidget(self.closing_balance_label)
        summary_layout.addStretch()
        parent_layout.addWidget(summary_frame)

    def load_cash_book(self):
        if self._loading:
            return
        from_date = self.from_date.date().toPython()
        to_date = self.to_date.date().toPython()
        thread = QThread(self)
        worker = CashBookWorker(getattr(self.db, 'db_type', None), getattr(self.db, 'db_path', None), self.company_id, from_date, to_date)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(self.populate_table)
        worker.error.connect(self._show_load_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._cash_worker_finished)
        self._cash_thread = thread
        self._cash_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _set_loading_state(self, is_loading):
        self._loading = is_loading
        self.view_btn.setEnabled(not is_loading)
        self.from_date.setEnabled(not is_loading)
        self.to_date.setEnabled(not is_loading)
        self.view_btn.setText('Loading...' if is_loading else 'View')

    def _cash_worker_finished(self):
        self._cash_thread = None
        self._cash_worker = None
        self._set_loading_state(False)

    def _show_load_error(self, message):
        self.table.setRowCount(1)
        self.table.setItem(0, 0, QTableWidgetItem(message))
        self.table.setSpan(0, 0, 1, 9)

    def populate_table(self, data):
        self._last_table_data = data
        row_colors = book_report_special_row_colors()
        opening_bg = QColor(row_colors['opening'])
        closing_bg = QColor(row_colors['closing_balance'])
        highlight_fg = QColor(row_colors['highlight_fg'])
        opening_balance = data['opening_balance']
        entries = data['entries']
        total_receipts = data['total_receipts']
        total_payments = data['total_payments']
        closing_balance = data['closing_balance']
        self.table.setRowCount(len(entries) + 2)
        from_date_str = qdate_to_display(self.from_date.date())
        self.table.setItem(0, 0, QTableWidgetItem(''))
        self.table.setItem(0, 1, QTableWidgetItem(from_date_str))
        self.table.setItem(0, 2, QTableWidgetItem(''))
        self.table.setItem(0, 3, QTableWidgetItem(''))
        self.table.setItem(0, 4, QTableWidgetItem('Opening Balance'))
        self.table.setItem(0, 5, QTableWidgetItem(''))
        self.table.setItem(0, 6, QTableWidgetItem(''))
        self.table.setItem(0, 7, QTableWidgetItem(''))
        self.table.setItem(0, 8, QTableWidgetItem(f'{float(opening_balance):.2f}'))
        for col in range(9):
            item = self.table.item(0, col)
            if item:
                item.setBackground(opening_bg)
                item.setForeground(highlight_fg)
                item.setFont(QFont('Arial', 9, QFont.Bold))
        for i, entry in enumerate(entries):
            row = i + 1
            self.table.setItem(row, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(format_display_date(entry.get('voucher_date', ''))))
            self.table.setItem(row, 2, QTableWidgetItem(str(entry.get('voucher_no', ''))))
            self.table.setItem(row, 3, QTableWidgetItem(str(entry.get('voucher_type', ''))))
            self.table.setItem(row, 4, QTableWidgetItem(str(entry.get('particulars', ''))))
            self.table.setItem(row, 5, QTableWidgetItem(str(entry.get('narration', ''))))
            debit = entry.get('debit', 0)
            credit = entry.get('credit', 0)
            running_balance = entry.get('running_balance', 0)
            if debit > 0:
                self.table.setItem(row, 6, QTableWidgetItem(f'{float(debit):.2f}'))
                self.table.item(row, 6).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            else:
                self.table.setItem(row, 6, QTableWidgetItem(''))
            if credit > 0:
                self.table.setItem(row, 7, QTableWidgetItem(f'{float(credit):.2f}'))
                self.table.item(row, 7).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            else:
                self.table.setItem(row, 7, QTableWidgetItem(''))
            self.table.setItem(row, 8, QTableWidgetItem(f'{float(running_balance):.2f}'))
            self.table.item(row, 8).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        closing_row = len(entries) + 1
        self.table.setItem(closing_row, 0, QTableWidgetItem(''))
        self.table.setItem(closing_row, 1, QTableWidgetItem(qdate_to_display(self.to_date.date())))
        self.table.setItem(closing_row, 2, QTableWidgetItem(''))
        self.table.setItem(closing_row, 3, QTableWidgetItem(''))
        self.table.setItem(closing_row, 4, QTableWidgetItem('Closing Balance'))
        self.table.setItem(closing_row, 5, QTableWidgetItem(''))
        self.table.setItem(closing_row, 6, QTableWidgetItem(''))
        self.table.setItem(closing_row, 7, QTableWidgetItem(''))
        self.table.setItem(closing_row, 8, QTableWidgetItem(f'{float(closing_balance):.2f}'))
        self.table.item(closing_row, 8).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for col in range(9):
            item = self.table.item(closing_row, col)
            if item:
                item.setBackground(closing_bg)
                item.setForeground(highlight_fg)
                item.setFont(QFont('Arial', 9, QFont.Bold))
        self.total_receipts_label.setText(f'Total Receipts: ₹{float(total_receipts):.2f}')
        self.total_payments_label.setText(f'Total Payments: ₹{float(total_payments):.2f}')
        self.closing_balance_label.setText(f'Closing Balance: ₹{float(closing_balance):.2f}')
        self.print_btn.setEnabled(True)
        self.export_btn.setEnabled(True)

    def show_preview(self):
        """Open Cash Book in the universal print/PDF preview dialog."""
        if self.table.rowCount() <= 0:
            QMessageBox.information(self, 'No Data', 'Please load cash book data first.')
            return
        subtitle = f"{qdate_to_display(self.from_date.date())} to {qdate_to_display(self.to_date.date())}"
        summary_lines = [self.total_receipts_label.text(), self.total_payments_label.text(), self.closing_balance_label.text()]
        html_string = table_widget_to_html(self.table, 'Cash Book', subtitle, summary_lines)
        dialog = UniversalPreviewDialog(html_string, self)
        dialog.exec()