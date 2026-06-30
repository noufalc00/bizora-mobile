"""
Daily Collection Report — sales settlement tally by payment mode.
"""
from typing import Any, List, Optional
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QAbstractItemView, QApplication, QComboBox, QDateEdit, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from config import active_company_manager
from db import Database
from ui.pdc_book_page import compact_combo_style, compact_date_style, compact_label_style, compact_topbar_frame_style
from ui.book_report_common import compact_primary_button_style, page_background_style, page_heading_style, report_detail_dialog_style
from ui import theme
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
ONLINE_PAYMENT_MODES = frozenset({'Online / UPI', 'Bank Transfer'})

class SalesBillDetailView(UiMemoryMixin, QDialog):
    """Read-only drill-down dialog for sales invoice line items."""
    COL_SL = 0
    COL_BARCODE = 1
    COL_PRODUCT = 2
    COL_QTY = 3
    COL_RATE = 4
    COL_DISCOUNT = 5
    COL_TAX = 6
    COL_NET = 7

    def __init__(self, db: Database, company_id: int, invoice_no: str, invoice_date: str='', customer_name: str='', parent=None):
        super().__init__(parent)
        self.db = db
        self.company_id = company_id
        self.invoice_no = (invoice_no or '').strip()
        self.setWindowTitle(f'Invoice Details — {self.invoice_no}')
        self.setModal(True)
        self.setMinimumSize(800, 400)
        self.resize(900, 460)
        self.setStyleSheet(report_detail_dialog_style())
        self._build_ui(invoice_date, customer_name)
        self._load_line_items()
        self._init_ui_memory()

    def _build_ui(self, invoice_date: str, customer_name: str):
        """Build header trackers, items grid, and close button."""
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        header_style = theme.report_detail_caption_style()
        value_style = theme.report_detail_value_style()
        header_row = QHBoxLayout()
        header_row.setSpacing(16)
        for caption, value in (('Invoice No:', self.invoice_no), ('Date:', invoice_date or '—'), ('Customer:', customer_name or '—')):
            cap_lbl = QLabel(caption)
            cap_lbl.setStyleSheet(header_style)
            val_lbl = QLabel(value)
            val_lbl.setStyleSheet(value_style)
            header_row.addWidget(cap_lbl)
            header_row.addWidget(val_lbl)
        header_row.addStretch(1)
        root.addLayout(header_row)
        self.items_table = QTableWidget(0, 8)
        self.items_table.setHorizontalHeaderLabels(['SL', 'Barcode', 'Product Name', 'Qty', 'Rate', 'Discount', 'Tax', 'Net Amount'])
        apply_read_only_report_table_selection(self.items_table)
        root.addWidget(self.items_table, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton('Close')
        close_btn.setStyleSheet(theme.sales_nav_button_style())
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _load_line_items(self):
        """Fetch line items for the invoice via sales + sales_items join."""
        self.items_table.blockSignals(True)
        self.items_table.setRowCount(0)
        if not self.invoice_no or not self.company_id:
            self.items_table.blockSignals(False)
            return
        try:
            rows = self.db.execute_query('\n                SELECT pr.barcode, pr.name AS product_name, si.quantity,\n                       si.rate, si.discount, si.tax_amount, si.grand_total,\n                       si.sl_no\n                FROM sales_items si\n                INNER JOIN sales s ON si.sale_id = s.id\n                LEFT JOIN products pr ON si.product_id = pr.id\n                WHERE s.company_id = ?\n                  AND s.invoice_number = ?\n                ORDER BY si.sl_no\n                ', (self.company_id, self.invoice_no)) or []
        except Exception as exc:
            QMessageBox.warning(self, 'Invoice Details', f'Could not load bill items: {exc}')
            self.items_table.blockSignals(False)
            return
        self.items_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            if isinstance(row, dict):
                barcode = row.get('barcode', '')
                product_name = row.get('product_name', '')
                qty = row.get('quantity', 0)
                rate = row.get('rate', 0)
                discount = row.get('discount', 0)
                tax_amount = row.get('tax_amount', 0)
                net_amount = row.get('grand_total', 0)
                sl_no = row.get('sl_no', row_idx + 1)
            else:
                barcode = row[0] if len(row) > 0 else ''
                product_name = row[1] if len(row) > 1 else ''
                qty = row[2] if len(row) > 2 else 0
                rate = row[3] if len(row) > 3 else 0
                discount = row[4] if len(row) > 4 else 0
                tax_amount = row[5] if len(row) > 5 else 0
                net_amount = row[6] if len(row) > 6 else 0
                sl_no = row[7] if len(row) > 7 else row_idx + 1
            values = ((self.COL_SL, str(sl_no), False), (self.COL_BARCODE, str(barcode or ''), False), (self.COL_PRODUCT, str(product_name or ''), False), (self.COL_QTY, f'{_safe_float(qty):.2f}', True), (self.COL_RATE, f'{_safe_float(rate):.2f}', True), (self.COL_DISCOUNT, f'{_safe_float(discount):.2f}', True), (self.COL_TAX, f'{_safe_float(tax_amount):.2f}', True), (self.COL_NET, f'{_safe_float(net_amount):.2f}', True))
            for col, text, right_align in values:
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == self.COL_SL:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                elif right_align:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.items_table.setItem(row_idx, col, item)
            if row_idx % 25 == 0:
                QApplication.processEvents()
        self.items_table.blockSignals(False)
        apply_adjustable_table_columns(self.items_table, sl_no_column=self.COL_SL)

def _safe_float(value: Any) -> float:
    """Convert database numeric values to float safely."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

class CollectionReportUI(UiMemoryMixin, QWidget):
    """Daily collection register with payment-mode filters and footer tally."""
    COL_SL = 0
    COL_INVOICE = 1
    COL_DATE = 2
    COL_CUSTOMER = 3
    COL_GRAND_TOTAL = 4
    COL_AMOUNT_PAID = 5
    COL_PAYMENT_MODE = 6

    def __init__(self, db: Optional[Database]=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.company_id: Optional[int] = None
        self._build_ui()
        self.refresh()
        self._init_ui_memory(table_attrs=("table",))

    def _build_ui(self):
        """Build filters, grid, and tally footer card."""
        self.setStyleSheet(page_background_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QLabel('Daily Collection Report')
        header.setStyleSheet(page_heading_style(22))
        root.addWidget(header)
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_row = QHBoxLayout(filter_frame)
        filter_row.setContentsMargins(10, 8, 10, 8)
        filter_row.setSpacing(10)
        today = QDate.currentDate()
        self.from_date = QDateEdit()
        self.from_date.setDate(today)
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        self.to_date = QDateEdit()
        self.to_date.setDate(today)
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        self.payment_mode_combo = QComboBox()
        self.payment_mode_combo.addItems(['All', 'Cash', 'Online / UPI', 'Bank Transfer', 'Credit'])
        self.payment_mode_combo.setStyleSheet(compact_combo_style())
        self.payment_mode_combo.setFixedWidth(140)
        self.load_btn = QPushButton('Load Report')
        load_font = QFont(self.load_btn.font())
        load_font.setBold(True)
        self.load_btn.setFont(load_font)
        self.load_btn.setStyleSheet(compact_primary_button_style())
        self.load_btn.clicked.connect(self.fetch_collection_data)
        for label_text, widget in (('From Date', self.from_date), ('To Date', self.to_date), ('Payment Mode', self.payment_mode_combo)):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(compact_label_style())
            filter_row.addWidget(lbl)
            filter_row.addWidget(widget)
        filter_row.addStretch(1)
        filter_row.addWidget(self.load_btn)
        root.addWidget(filter_frame)
        self.report_table = QTableWidget(0, 7)
        self.report_table.setHorizontalHeaderLabels(['SL', 'Invoice No', 'Date', 'Customer Name', 'Grand Total', 'Amount Paid', 'Payment Mode'])
        apply_read_only_report_table_selection(self.report_table)
        self.report_table.cellDoubleClicked.connect(self.show_bill_details)
        root.addWidget(self.report_table, 1)
        tally_frame = QFrame()
        tally_frame.setStyleSheet(theme.collection_tally_frame_style())
        tally_layout = QHBoxLayout(tally_frame)
        tally_layout.setContentsMargins(16, 12, 16, 12)
        tally_layout.setSpacing(28)
        tally_label_style = theme.collection_tally_label_style()
        self.total_cash_label = QLabel('Total Cash Received: Rs. 0.00')
        self.total_online_label = QLabel('Total Online/Bank Received: Rs. 0.00')
        self.total_credit_label = QLabel('Total Credit/Pending: Rs. 0.00')
        for lbl in (self.total_cash_label, self.total_online_label, self.total_credit_label):
            lbl.setStyleSheet(tally_label_style)
        tally_layout.addWidget(self.total_cash_label)
        tally_layout.addWidget(self.total_online_label)
        tally_layout.addWidget(self.total_credit_label)
        tally_layout.addStretch(1)
        root.addWidget(tally_frame)

    def refresh(self):
        """Resolve active company and load today's collection rows."""
        company = active_company_manager.get_active_company()
        self.company_id = company.get('id') if company else None
        if not self.company_id:
            self._reset_grid('Please open a company first.')
            return
        self.fetch_collection_data()

    def _reset_grid(self, message: str=''):
        """Clear table and tally labels."""
        self.report_table.blockSignals(True)
        self.report_table.setRowCount(0)
        self.report_table.blockSignals(False)
        self._update_tally_labels(0.0, 0.0, 0.0)
        if message:
            QMessageBox.information(self, 'Daily Collection Report', message)

    def _update_tally_labels(self, total_cash: float, total_online: float, total_credit: float):
        """Refresh footer tally card with two-decimal rupee amounts."""
        self.total_cash_label.setText(f'Total Cash Received: Rs. {total_cash:.2f}')
        self.total_online_label.setText(f'Total Online/Bank Received: Rs. {total_online:.2f}')
        self.total_credit_label.setText(f'Total Credit/Pending: Rs. {total_credit:.2f}')

    def _accumulate_tally(self, payment_mode: str, grand_total: float, amount_paid: float, total_cash: float, total_online: float, total_credit: float):
        """
        Route amount_paid and pending balances into cash, online, or credit buckets.
        """
        mode = (payment_mode or 'Cash').strip()
        pending = max(0.0, grand_total - amount_paid)
        if mode == 'Cash':
            total_cash += amount_paid
        elif mode in ONLINE_PAYMENT_MODES:
            total_online += amount_paid
        if mode == 'Credit' or pending > 0.0:
            if pending > 0.0:
                total_credit += pending
            elif mode == 'Credit':
                total_credit += grand_total
        return (total_cash, total_online, total_credit)

    def fetch_collection_data(self):
        """Load sales headers for the date range and payment-mode filter."""
        if not self.company_id:
            company = active_company_manager.get_active_company()
            self.company_id = company.get('id') if company else None
        if not self.company_id:
            self._reset_grid('Please open a company first.')
            return
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        mode_filter = self.payment_mode_combo.currentText().strip()
        sql = "\n            SELECT s.invoice_number, s.invoice_date, p.name AS customer_name,\n                   s.grand_total, s.amount_received,\n                   COALESCE(s.payment_mode, 'Cash') AS payment_mode\n            FROM sales s\n            LEFT JOIN parties p ON s.party_id = p.id\n            WHERE s.company_id = ?\n              AND s.invoice_date >= ?\n              AND s.invoice_date <= ?\n        "
        params: List[Any] = [self.company_id, from_date, to_date]
        if mode_filter and mode_filter != 'All':
            sql += " AND COALESCE(s.payment_mode, 'Cash') = ?"
            params.append(mode_filter)
        sql += ' ORDER BY s.invoice_date DESC, s.invoice_number DESC'
        try:
            rows = self.db.execute_query(sql, tuple(params)) or []
        except Exception as exc:
            QMessageBox.warning(self, 'Daily Collection Report', f'Could not load collection data: {exc}')
            return
        self.report_table.blockSignals(True)
        self.report_table.setRowCount(len(rows))
        total_cash = 0.0
        total_online = 0.0
        total_credit = 0.0
        for row_idx, row in enumerate(rows):
            if isinstance(row, dict):
                invoice_no = row.get('invoice_number', '')
                invoice_date = row.get('invoice_date', '')
                customer = row.get('customer_name', '')
                grand_total = _safe_float(row.get('grand_total'))
                amount_paid = _safe_float(row.get('amount_received'))
                payment_mode = row.get('payment_mode', 'Cash')
            else:
                invoice_no = row[0] if len(row) > 0 else ''
                invoice_date = row[1] if len(row) > 1 else ''
                customer = row[2] if len(row) > 2 else ''
                grand_total = _safe_float(row[3] if len(row) > 3 else 0)
                amount_paid = _safe_float(row[4] if len(row) > 4 else 0)
                payment_mode = row[5] if len(row) > 5 else 'Cash'
            total_cash, total_online, total_credit = self._accumulate_tally(payment_mode, grand_total, amount_paid, total_cash, total_online, total_credit)
            sl_item = QTableWidgetItem(str(row_idx + 1))
            sl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            sl_item.setFlags(sl_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.report_table.setItem(row_idx, self.COL_SL, sl_item)
            for col, text, right_align in ((self.COL_INVOICE, str(invoice_no or ''), False), (self.COL_DATE, str(invoice_date or ''), False), (self.COL_CUSTOMER, str(customer or ''), False), (self.COL_GRAND_TOTAL, f'{grand_total:.2f}', True), (self.COL_AMOUNT_PAID, f'{amount_paid:.2f}', True), (self.COL_PAYMENT_MODE, str(payment_mode or 'Cash'), False)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if right_align:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.report_table.setItem(row_idx, col, item)
            if row_idx % 40 == 0:
                QApplication.processEvents()
        self.report_table.blockSignals(False)
        self._update_tally_labels(total_cash, total_online, total_credit)
        apply_adjustable_table_columns(self.report_table, sl_no_column=self.COL_SL)
        self._restore_memory_table(self.report_table, "report_table")

    def show_bill_details(self, row: int, col: int):
        """Open a modal line-item viewer for the double-clicked invoice row."""
        if row < 0:
            return
        invoice_item = self.report_table.item(row, self.COL_INVOICE)
        if invoice_item is None or not invoice_item.text().strip():
            QMessageBox.information(self, 'Invoice Details', 'Could not read the invoice number for this row.')
            return
        invoice_no = invoice_item.text().strip()
        date_item = self.report_table.item(row, self.COL_DATE)
        customer_item = self.report_table.item(row, self.COL_CUSTOMER)
        invoice_date = date_item.text().strip() if date_item else ''
        customer_name = customer_item.text().strip() if customer_item else ''
        if not self.company_id:
            company = active_company_manager.get_active_company()
            self.company_id = company.get('id') if company else None
        if not self.company_id:
            QMessageBox.information(self, 'Invoice Details', 'Please open a company first.')
            return
        dialog = SalesBillDetailView(self.db, self.company_id, invoice_no, invoice_date=invoice_date, customer_name=customer_name, parent=self)
        dialog.exec()