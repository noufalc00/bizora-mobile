"""
Purchase Order Book — register of saved purchase orders with filters and drill-down.
"""
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import QAbstractItemView, QApplication, QComboBox, QDateEdit, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from PySide6.QtGui import QFont
from config import active_company_manager
from db import Database
from ui.book_report_common import compact_combo_style, compact_date_style, compact_input_style, compact_label_style, compact_primary_button_style, compact_topbar_frame_style, page_background_style, page_heading_style, report_summary_label_style, report_detail_dialog_style
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

def _safe_float(value: Any) -> float:
    """Convert database numeric values to float safely."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

class PODetailView(UiMemoryMixin, QDialog):
    """Modal dialog showing line items for one purchase order."""

    def __init__(self, db: Database, po_id: int, po_number: str='', parent=None):
        super().__init__(parent)
        self.db = db
        self.po_id = po_id
        title_suffix = f' — {po_number}' if po_number else ''
        self.setWindowTitle(f'Purchase Order Items{title_suffix}')
        self.setModal(True)
        self.resize(820, 420)
        self.setStyleSheet(report_detail_dialog_style())
        self._build_ui()
        self._load_items()
        self._init_ui_memory()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        heading = QLabel('Line items for this purchase order')
        heading.setStyleSheet(page_heading_style(14))
        layout.addWidget(heading)
        self.items_table = QTableWidget(0, 5)
        self.items_table.setHorizontalHeaderLabels(['Barcode', 'Product Name', 'Qty', 'Rate', 'Net Amount'])
        apply_read_only_report_table_selection(self.items_table)
        layout.addWidget(self.items_table, 1)
        close_btn = QPushButton('Close')
        close_btn.setStyleSheet(compact_primary_button_style())
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _load_items(self):
        """Load purchase_order_items for the selected PO."""
        self.items_table.blockSignals(True)
        self.items_table.setRowCount(0)
        try:
            ph = self.db._get_placeholder()
            rows = self.db.execute_query(f'\n                SELECT barcode, product_name, qty, rate, net_amount\n                FROM purchase_order_items\n                WHERE po_id = {ph}\n                ORDER BY id\n                ', (self.po_id,)) or []
        except Exception as exc:
            QMessageBox.warning(self, 'PO Details', f'Could not load order items: {exc}')
            self.items_table.blockSignals(False)
            return
        self.items_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            if isinstance(row, dict):
                barcode = row.get('barcode', '')
                product_name = row.get('product_name', '')
                qty = row.get('qty', 0)
                rate = row.get('rate', 0)
                net_amount = row.get('net_amount', 0)
            else:
                barcode = row[0] if len(row) > 0 else ''
                product_name = row[1] if len(row) > 1 else ''
                qty = row[2] if len(row) > 2 else 0
                rate = row[3] if len(row) > 3 else 0
                net_amount = row[4] if len(row) > 4 else 0
            self.items_table.setItem(row_idx, 0, QTableWidgetItem(str(barcode or '')))
            self.items_table.setItem(row_idx, 1, QTableWidgetItem(str(product_name or '')))
            self.items_table.setItem(row_idx, 2, QTableWidgetItem(f'{_safe_float(qty):.2f}'))
            self.items_table.setItem(row_idx, 3, QTableWidgetItem(f'{_safe_float(rate):.2f}'))
            self.items_table.setItem(row_idx, 4, QTableWidgetItem(f'{_safe_float(net_amount):.2f}'))
            if row_idx % 25 == 0:
                QApplication.processEvents()
        self.items_table.blockSignals(False)
        apply_adjustable_table_columns(self.items_table)

class PurchaseOrderBookUI(UiMemoryMixin, QWidget):
    """Purchase Order register with date/status filters and item drill-down."""
    COL_SL = 0
    COL_PO_NUMBER = 1
    COL_DATE = 2
    COL_CREDITOR = 3
    COL_GRAND_TOTAL = 4
    COL_STATUS = 5

    def __init__(self, db: Optional[Database]=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.company_id: Optional[int] = None
        self._row_po_ids: List[int] = []
        self._build_ui()
        self.refresh()
        self._init_ui_memory(table_attrs=("po_table",))

    def _build_ui(self):
        """Build filter bar, PO grid, and footer totals."""
        self.setStyleSheet(page_background_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QLabel('Purchase Order Book')
        header.setStyleSheet(page_heading_style(22))
        root.addWidget(header)
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_row = QHBoxLayout(filter_frame)
        filter_row.setContentsMargins(10, 8, 10, 8)
        filter_row.setSpacing(10)
        today = QDate.currentDate()
        month_start = QDate(today.year(), today.month(), 1)
        self.from_date = QDateEdit()
        self.from_date.setDate(month_start)
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        self.to_date = QDateEdit()
        self.to_date.setDate(today)
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        self.status_combo = QComboBox()
        self.status_combo.addItems(['All', 'Pending', 'Completed', 'Cancelled'])
        self.status_combo.setStyleSheet(compact_combo_style())
        self.status_combo.setFixedWidth(120)
        self.creditor_search = QLineEdit()
        self.creditor_search.setPlaceholderText('Search creditor name...')
        self.creditor_search.setStyleSheet(compact_input_style())
        self.creditor_search.setMinimumWidth(200)
        self.load_btn = QPushButton('Load Data')
        load_font = QFont(self.load_btn.font())
        load_font.setBold(True)
        self.load_btn.setFont(load_font)
        self.load_btn.setStyleSheet('\n            QPushButton {\n                background-color: #16a34a; color: white; border: none;\n                border-radius: 4px; font-size: 11px; font-weight: bold;\n                padding: 6px 18px;\n            }\n            QPushButton:hover { background-color: #15803d; }\n            QPushButton:pressed { background-color: #166534; }\n        ')
        self.load_btn.clicked.connect(self.fetch_po_data)
        for label_text, widget in (('From Date', self.from_date), ('To Date', self.to_date), ('Status', self.status_combo)):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(compact_label_style())
            filter_row.addWidget(lbl)
            filter_row.addWidget(widget)
        creditor_lbl = QLabel('Search Creditor')
        creditor_lbl.setStyleSheet(compact_label_style())
        filter_row.addWidget(creditor_lbl)
        filter_row.addWidget(self.creditor_search, 1)
        filter_row.addWidget(self.load_btn)
        root.addWidget(filter_frame)
        self.po_table = QTableWidget(0, 6)
        self.po_table.setHorizontalHeaderLabels(['SL', 'PO Number', 'Date', 'Creditor Name', 'Grand Total', 'Status'])
        apply_read_only_report_table_selection(self.po_table)
        self.po_table.cellDoubleClicked.connect(self.show_po_details)
        root.addWidget(self.po_table, 1)
        footer = QHBoxLayout()
        footer.setSpacing(24)
        self.total_count_label = QLabel('Total Count: 0')
        self.total_amount_label = QLabel('Total Amount: 0.00')
        for lbl in (self.total_count_label, self.total_amount_label):
            lbl.setStyleSheet(report_summary_label_style())
        footer.addWidget(self.total_count_label)
        footer.addWidget(self.total_amount_label)
        footer.addStretch(1)
        root.addLayout(footer)

    def refresh(self):
        """Reload active company context and fetch PO rows."""
        company = active_company_manager.get_active_company()
        self.company_id = company.get('id') if company else None
        if not self.company_id:
            self._clear_table('Please open a company first.')
            return
        self.fetch_po_data()

    def _clear_table(self, message: str=''):
        """Reset grid and footer labels."""
        self.po_table.blockSignals(True)
        self.po_table.setRowCount(0)
        self.po_table.blockSignals(False)
        self._row_po_ids = []
        self.total_count_label.setText('Total Count: 0')
        self.total_amount_label.setText('Total Amount: 0.00')
        if message:
            QMessageBox.information(self, 'Purchase Order Book', message)

    def fetch_po_data(self):
        """Query purchase_orders with date, status, and creditor filters."""
        if not self.company_id:
            company = active_company_manager.get_active_company()
            self.company_id = company.get('id') if company else None
        if not self.company_id:
            self._clear_table('Please open a company first.')
            return
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        status_filter = self.status_combo.currentText().strip()
        creditor_text = self.creditor_search.text().strip()
        sql = '\n            SELECT id, po_number, date, creditor_name, grand_total, status\n            FROM purchase_orders\n            WHERE company_id = ?\n              AND date >= ?\n              AND date <= ?\n        '
        params: List[Any] = [self.company_id, from_date, to_date]
        if status_filter and status_filter != 'All':
            sql += ' AND status = ?'
            params.append(status_filter)
        if creditor_text:
            sql += ' AND creditor_name LIKE ?'
            params.append(f'%{creditor_text}%')
        sql += ' ORDER BY date DESC, id DESC'
        try:
            rows = self.db.execute_query(sql, tuple(params)) or []
        except Exception as exc:
            QMessageBox.warning(self, 'Purchase Order Book', f'Could not load purchase orders: {exc}')
            return
        self.po_table.blockSignals(True)
        self.po_table.setRowCount(len(rows))
        self._row_po_ids = []
        grand_sum = 0.0
        for row_idx, row in enumerate(rows):
            if isinstance(row, dict):
                po_id = row.get('id', 0)
                po_number = row.get('po_number', '')
                po_date = row.get('date', '')
                creditor = row.get('creditor_name', '')
                grand_total = row.get('grand_total', 0)
                status = row.get('status', '')
            else:
                po_id = row[0] if len(row) > 0 else 0
                po_number = row[1] if len(row) > 1 else ''
                po_date = row[2] if len(row) > 2 else ''
                creditor = row[3] if len(row) > 3 else ''
                grand_total = row[4] if len(row) > 4 else 0
                status = row[5] if len(row) > 5 else ''
            po_id_int = int(po_id or 0)
            self._row_po_ids.append(po_id_int)
            amount = _safe_float(grand_total)
            grand_sum += amount
            sl_item = QTableWidgetItem(str(row_idx + 1))
            sl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            sl_item.setData(Qt.ItemDataRole.UserRole, po_id_int)
            sl_item.setFlags(sl_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.po_table.setItem(row_idx, self.COL_SL, sl_item)
            for col, text in ((self.COL_PO_NUMBER, str(po_number or '')), (self.COL_DATE, str(po_date or '')), (self.COL_CREDITOR, str(creditor or '')), (self.COL_GRAND_TOTAL, f'{amount:.2f}'), (self.COL_STATUS, str(status or ''))):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == self.COL_GRAND_TOTAL:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.po_table.setItem(row_idx, col, item)
            if row_idx % 40 == 0:
                QApplication.processEvents()
        self.po_table.blockSignals(False)
        self.total_count_label.setText(f'Total Count: {len(rows)}')
        self.total_amount_label.setText(f'Total Amount: {grand_sum:.2f}')
        apply_adjustable_table_columns(self.po_table, sl_no_column=self.COL_SL)
        self._restore_memory_table(self.po_table, "po_table")

    def _po_id_for_row(self, row: int) -> Optional[int]:
        """Return purchase order id stored on the SL column."""
        if row < 0:
            return None
        if 0 <= row < len(self._row_po_ids):
            return self._row_po_ids[row]
        item = self.po_table.item(row, self.COL_SL)
        if item is None:
            return None
        try:
            return int(item.data(Qt.ItemDataRole.UserRole) or 0) or None
        except (TypeError, ValueError):
            return None

    def show_po_details(self, row: int, col: int):
        """Open item breakdown dialog for the double-clicked purchase order."""
        po_id = self._po_id_for_row(row)
        if not po_id:
            QMessageBox.information(self, 'PO Details', 'Could not resolve this purchase order.')
            return
        po_number = ''
        number_item = self.po_table.item(row, self.COL_PO_NUMBER)
        if number_item is not None:
            po_number = number_item.text()
        dialog = PODetailView(self.db, po_id, po_number=po_number, parent=self)
        dialog.exec()