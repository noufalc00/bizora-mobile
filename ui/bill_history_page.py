"""
Bill History and Management Grid.

Standalone dashboard for finding, viewing, and voiding sales/purchase bills.
"""
from __future__ import annotations
import csv
import html
from typing import Any, Dict, Optional
from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtGui import QAction, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import QAbstractItemView, QApplication, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from config import active_company_manager
from db import Database
from bizora_core.bill_history_logic import BillHistoryLogic
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui import theme
from ui.book_report_common import (
    compact_combo_style,
    compact_date_style,
    compact_label_style,
    compact_primary_button_style,
    compact_search_style,
    compact_topbar_frame_style,
    page_heading_style,
)
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class BillHistoryPageWidget(UiMemoryMixin, QWidget):
    """Searchable bill history and management page."""

    def __init__(self, db: Optional[Database]=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.logic = BillHistoryLogic(self.db)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)
        self.setWindowTitle('Bill History & Management')
        self._build_ui()
        self.refresh()
        self._init_ui_memory(table_attrs=("table",))

    def _build_ui(self) -> None:
        self.setStyleSheet(self._page_style())
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        self.title_label = QLabel('Bill History & Management')
        self.title_label.setStyleSheet(page_heading_style(18))
        main_layout.addWidget(self.title_label)
        main_layout.addWidget(self._build_filter_bar())
        main_layout.addWidget(self._build_table(), 1)
        main_layout.addWidget(self._build_action_bar())

    def _build_filter_bar(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet(compact_topbar_frame_style())
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        from_label = QLabel('From:')
        from_label.setStyleSheet(compact_label_style())
        layout.addWidget(from_label)
        self.from_date = QDateEdit()
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        layout.addWidget(self.from_date)
        to_label = QLabel('To:')
        to_label.setStyleSheet(compact_label_style())
        layout.addWidget(to_label)
        self.to_date = QDateEdit()
        self.to_date.setDate(QDate.currentDate())
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        layout.addWidget(self.to_date)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText('Search by Bill No or Party Name...')
        self.search_box.setStyleSheet(compact_search_style())
        self.search_box.setMinimumWidth(220)
        layout.addWidget(self.search_box, 1)
        type_label = QLabel('Type:')
        type_label.setStyleSheet(compact_label_style())
        layout.addWidget(type_label)
        self.type_filter = QComboBox()
        self.type_filter.addItems(['All', 'Sales', 'Purchases', 'Sales Return', 'Purchase Return'])
        self.type_filter.setStyleSheet(compact_combo_style())
        self.type_filter.setFixedWidth(150)
        layout.addWidget(self.type_filter)
        refresh_btn = QPushButton('Refresh')
        refresh_btn.setStyleSheet(compact_primary_button_style())
        refresh_btn.setFixedHeight(30)
        refresh_btn.setMinimumWidth(72)
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)
        self.export_btn = self._create_export_button()
        self.export_btn.setFixedHeight(30)
        self.export_btn.setMinimumWidth(72)
        layout.addWidget(self.export_btn)
        self.from_date.dateChanged.connect(self._queue_refresh)
        self.to_date.dateChanged.connect(self._queue_refresh)
        self.search_box.textChanged.connect(self._queue_refresh)
        self.type_filter.currentTextChanged.connect(self._queue_refresh)
        return frame

    def _create_export_button(self) -> QPushButton:
        button = QPushButton('Export ▼')
        button.setStyleSheet(self._export_button_style())
        menu = QMenu(button)
        pdf_action = QAction('Export to PDF', self)
        excel_action = QAction('Export to Excel', self)
        csv_action = QAction('Export to CSV', self)
        pdf_action.triggered.connect(self.export_to_pdf)
        excel_action.triggered.connect(self.export_to_excel)
        csv_action.triggered.connect(self.export_to_csv)
        menu.addAction(pdf_action)
        menu.addAction(excel_action)
        menu.addAction(csv_action)
        button.setMenu(menu)
        return button

    @staticmethod
    def _export_button_style() -> str:
        return compact_primary_button_style() + ' QPushButton::menu-indicator { image: none; width: 0px; }'

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget()
        self.table.setStyleSheet(self._table_style())
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(['Date', 'Bill No', 'Type', 'Party Name', 'Total Amount', 'Status'])
        apply_read_only_report_table_selection(self.table)
        self.table.itemDoubleClicked.connect(self.open_selected_bill_for_edit)
        return self.table

    def _build_action_bar(self) -> QWidget:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        self.view_btn = QPushButton('View Invoice Details')
        self.view_btn.clicked.connect(self.view_invoice_details)
        self.view_btn.setStyleSheet(self._action_button_style())
        layout.addWidget(self.view_btn)
        self.void_btn = QPushButton('Void/Cancel Bill')
        self.void_btn.clicked.connect(self.void_selected_bill)
        self.void_btn.setStyleSheet(self._action_button_style(danger=True))
        layout.addWidget(self.void_btn)
        return frame

    @staticmethod
    def _page_style() -> str:
        from ui.book_report_common import report_compound_entry_page_style
        return report_compound_entry_page_style()

    @staticmethod
    def _table_style() -> str:
        from ui import theme
        return theme.master_table_style()

    @staticmethod
    def _action_button_style(danger: bool=False) -> str:
        return theme.report_action_button_style(danger=danger)

    def _queue_refresh(self) -> None:
        self._refresh_timer.start(180)

    def _active_company_id(self) -> Optional[int]:
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'No Active Company', 'Please open a company first.')
            return None
        return active_company.get('id')

    def refresh(self) -> None:
        company_id = self._active_company_id()
        if not company_id:
            self.table.setRowCount(0)
            return
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        if from_date > to_date:
            self.table.setRowCount(0)
            return
        bills = self.logic.get_filtered_bills(company_id=company_id, from_date=from_date, to_date=to_date, search_term=self.search_box.text(), transaction_type=self.type_filter.currentText())
        self._populate_table(bills)

    def _populate_table(self, bills) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(bills))
        for row, bill in enumerate(bills):
            date_item = QTableWidgetItem(str(bill.get('bill_date') or ''))
            date_item.setData(Qt.UserRole, bill)
            self.table.setItem(row, 0, date_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(bill.get('bill_no') or '')))
            self.table.setItem(row, 2, QTableWidgetItem(str(bill.get('transaction_type') or '')))
            self.table.setItem(row, 3, QTableWidgetItem(str(bill.get('party_name') or '')))
            total = float(bill.get('total_amount') or 0.0)
            total_item = QTableWidgetItem(f'{total:.2f}')
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 4, total_item)
            status = str(bill.get('status') or 'Active')
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == 'Voided':
                status_item.setForeground(Qt.red)
            self.table.setItem(row, 5, status_item)
        self.table.setSortingEnabled(True)
        apply_adjustable_table_columns(self.table)
        self._restore_memory_table(self.table, "table")

    def _selected_bill(self) -> Optional[Dict[str, Any]]:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, 'Select Bill', 'Please select a bill first.')
            return None
        item = self.table.item(row, 0)
        data = item.data(Qt.UserRole) if item else None
        return dict(data) if isinstance(data, dict) else None

    def view_invoice_details(self) -> None:
        bill = self._selected_bill()
        if not bill:
            return
        company_id = self._active_company_id()
        if not company_id:
            return
        details = self.logic.get_invoice_details(company_id=company_id, voucher_type=str(bill.get('transaction_type') or ''), voucher_id=int(bill.get('voucher_id')))
        if not details:
            QMessageBox.warning(self, 'Not Found', 'Could not load invoice details.')
            return
        dialog = InvoiceDetailsDialog(details, self)
        dialog.exec()

    def export_to_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, 'Export Bill History', 'bill_history.csv', 'CSV Files (*.csv);;All Files (*)')
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.writer(handle)
                writer.writerow([self.table.horizontalHeaderItem(col).text() for col in range(self.table.columnCount())])
                for row in range(self.table.rowCount()):
                    writer.writerow([self.table.item(row, col).text() if self.table.item(row, col) else '' for col in range(self.table.columnCount())])
            QMessageBox.information(self, 'Export Complete', f'Bill history exported to:\n{path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Export Failed', str(exc))

    def export_to_pdf(self) -> None:
        """Open bill history in the universal print/PDF preview dialog."""
        if self.table.rowCount() <= 0:
            QMessageBox.information(self, 'No Data', 'Please load bill history first.')
            return
        dialog = UniversalPreviewDialog(self._table_html('Bill History & Management'), self)
        dialog.exec()

    def export_to_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, 'Export Bill History Excel', 'bill_history.xlsx', 'Excel Files (*.xlsx);;All Files (*)')
        if not path:
            return
        if not path.lower().endswith('.xlsx'):
            path += '.xlsx'
        try:
            from openpyxl import Workbook
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = 'Bill History'
            for row in self._table_rows(include_headers=True):
                sheet.append(row)
            workbook.save(path)
            QMessageBox.information(self, 'Export Complete', f'Excel file exported to:\n{path}')
        except ImportError:
            self._write_csv_fallback(path)
            QMessageBox.warning(self, 'Excel Library Missing', 'openpyxl is not installed. A CSV-formatted fallback was saved with the selected filename.')
        except Exception as exc:
            QMessageBox.critical(self, 'Export Failed', str(exc))

    def _write_csv_fallback(self, path: str) -> None:
        with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.writer(handle)
            writer.writerows(self._table_rows(include_headers=True))

    def _table_rows(self, include_headers: bool=False) -> list:
        rows = []
        if include_headers:
            rows.append([self.table.horizontalHeaderItem(col).text() for col in range(self.table.columnCount())])
        for row in range(self.table.rowCount()):
            rows.append([self.table.item(row, col).text() if self.table.item(row, col) else '' for col in range(self.table.columnCount())])
        return rows

    def _table_html(self, title: str) -> str:
        header_cells = ''.join((f'<th>{html.escape(self.table.horizontalHeaderItem(col).text())}</th>' for col in range(self.table.columnCount())))
        body_rows = []
        for row in range(self.table.rowCount()):
            cells = ''.join((f"<td>{html.escape(self.table.item(row, col).text() if self.table.item(row, col) else '')}</td>" for col in range(self.table.columnCount())))
            body_rows.append(f'<tr>{cells}</tr>')
        return f"\n        <html>\n        <head>\n        <style>\n            body {{ font-family: Arial, sans-serif; font-size: 10pt; }}\n            h1 {{ color: #1976D2; font-size: 18pt; }}\n            table {{ border-collapse: collapse; width: 100%; }}\n            th {{ background: #2196F3; color: white; padding: 6px; border: 1px solid #90CAF9; }}\n            td {{ padding: 5px; border: 1px solid #cccccc; }}\n        </style>\n        </head>\n        <body>\n            <h1>{html.escape(title)}</h1>\n            <table>\n                <thead><tr>{header_cells}</tr></thead>\n                <tbody>{''.join(body_rows)}</tbody>\n            </table>\n        </body>\n        </html>\n        "

    def _main_window(self):
        widget = self
        while widget is not None:
            if hasattr(widget, 'open_voucher_for_edit'):
                return widget
            widget = widget.parent()
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'open_voucher_for_edit'):
                return widget
        return None

    def open_selected_bill_for_edit(self, _item=None) -> None:
        bill = self._selected_bill()
        if not bill:
            return
        main_window = self._main_window()
        if not main_window:
            QMessageBox.warning(self, 'Navigation Error', 'Main window navigation is not available.')
            return
        main_window.open_voucher_for_edit(str(bill.get('transaction_type') or ''), int(bill.get('voucher_id')))

    def void_selected_bill(self) -> None:
        bill = self._selected_bill()
        if not bill:
            return
        if str(bill.get('status') or 'Active') == 'Voided':
            QMessageBox.information(self, 'Already Voided', 'This bill is already voided.')
            return
        bill_no = str(bill.get('bill_no') or '')
        bill_type = str(bill.get('transaction_type') or '')
        reply = QMessageBox.warning(self, 'Strict Confirmation Required', f'Void {bill_type} bill {bill_no}?\n\nThe original invoice and item rows will remain intact.\nThe system will mark it as Voided and post reversal stock and ledger entries.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        company_id = self._active_company_id()
        if not company_id:
            return
        success, message = self.logic.void_bill(company_id=company_id, voucher_type=bill_type, voucher_id=int(bill.get('voucher_id')), reason='Voided from Bill History dashboard')
        if success:
            QMessageBox.information(self, 'Bill Voided', message)
            self.refresh()
        else:
            QMessageBox.critical(self, 'Void Failed', message)

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(self._page_style())
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(page_heading_style(18))
        if hasattr(self, 'from_date'):
            prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        if hasattr(self, 'to_date'):
            prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        if hasattr(self, 'search_box'):
            self.search_box.setStyleSheet(compact_search_style())
        if hasattr(self, 'type_filter'):
            self.type_filter.setStyleSheet(compact_combo_style())
        if hasattr(self, 'table'):
            self.table.setStyleSheet(self._table_style())
        if hasattr(self, 'view_btn'):
            self.view_btn.setStyleSheet(self._action_button_style())
        if hasattr(self, 'void_btn'):
            self.void_btn.setStyleSheet(self._action_button_style(danger=True))
        if hasattr(self, 'export_btn'):
            self.export_btn.setStyleSheet(self._export_button_style())

class InvoiceDetailsDialog(UiMemoryMixin, QDialog):
    """Read-only invoice details popup."""

    def __init__(self, details: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.details = details
        self.setWindowTitle('Invoice Details')
        self.resize(900, 560)
        self._build_ui()
        self._init_ui_memory()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        header = QLabel(self._header_text())
        header.setTextFormat(Qt.PlainText)
        header.setStyleSheet('font-family: Consolas, monospace;')
        layout.addWidget(header)
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(9)
        self.items_table.setHorizontalHeaderLabels(['SL', 'Product', 'HSN', 'Rate', 'Qty', 'Gross', 'Disc', 'Tax', 'Total'])
        apply_read_only_report_table_selection(self.items_table)
        layout.addWidget(self.items_table, 1)
        self._populate_items()
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _header_text(self) -> str:
        return f"Bill No: {self.details.get('bill_no', '')}\nDate: {self.details.get('bill_date', '')}\nType: {self.details.get('transaction_type', '')}\nParty: {self.details.get('party_name', '')}\nStatus: {self.details.get('status', 'Active')}\nSub Total: {float(self.details.get('sub_total') or 0.0):.2f}    Tax: {float(self.details.get('tax_total') or 0.0):.2f}    Round Off: {float(self.details.get('round_off') or 0.0):.2f}    Total: {float(self.details.get('total_amount') or 0.0):.2f}"

    def _populate_items(self) -> None:
        items = self.details.get('items') or []
        self.items_table.setRowCount(len(items))
        columns = ['sl_no', 'product_name', 'hsn', 'rate', 'quantity', 'gross_value', 'discount', 'tax_amount', 'grand_total']
        for row, item in enumerate(items):
            for col, key in enumerate(columns):
                value = item.get(key, '')
                if key in {'rate', 'quantity', 'gross_value', 'discount', 'tax_amount', 'grand_total'}:
                    try:
                        value = f'{float(value or 0.0):.2f}'
                    except (TypeError, ValueError):
                        value = '0.00'
                table_item = QTableWidgetItem(str(value))
                if col >= 3:
                    table_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.items_table.setItem(row, col, table_item)
        apply_adjustable_table_columns(self.items_table, sl_no_column=0)

BillHistoryPage = BillHistoryPageWidget