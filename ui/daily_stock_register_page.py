"""
Daily Stock Register page.
Read-only inventory reporting module showing chronological stock movement history with running balance.
"""
from typing import Optional, Dict, List, Any
from datetime import date, timedelta
from PySide6.QtCore import Qt, QDate, QStringListModel, QObject, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QAbstractItemView, QLineEdit, QCompleter, QGridLayout, QSizePolicy, QMessageBox
from db import Database
from bizora_core.daily_stock_register_logic import DailyStockRegisterLogic
from ui.book_report_common import BOOK_REPORT_ACTION_BUTTON_HEIGHT, add_labeled_filter_rows, attach_filter_action_row, compact_label_style, compact_input_style, compact_date_style, compact_primary_button_style, compact_topbar_frame_style, create_filter_action_layout, page_background_style, page_heading_style, report_data_table_style, report_detail_dialog_style, report_summary_label_style
from ui.theme import sales_barcode_input_style
from ui import theme
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class DailyStockRegisterWorker(QObject):
    """Load daily stock register rows on a worker-owned database connection."""
    data_ready = Signal(list)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type, db_path, company_id, filters):
        """Initialize worker with immutable filter values."""
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id
        self.filters = dict(filters)

    def run(self):
        """Fetch finalized register rows outside the GUI thread."""
        worker_db = None
        try:
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            logic = DailyStockRegisterLogic(worker_db)
            rows = logic.get_stock_register_data(
                self.company_id,
                self.filters.get('from_date'),
                self.filters.get('to_date'),
                product_id=self.filters.get('product_id'),
                voucher_type=self.filters.get('voucher_type'),
            )
            self.data_ready.emit(rows)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                worker_db.force_disconnect()
            self.finished.emit()

class DailyStockRegisterPageWidget(UiMemoryMixin, QWidget):
    """UI page for Daily Stock Register - read-only inventory reporting."""

    def __init__(self, db: Optional[Database]=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.logic = DailyStockRegisterLogic(self.db)
        self.company_id: Optional[int] = None
        self.current_report_data: List[Dict[str, Any]] = []
        self.product_options: List[Dict[str, Any]] = []
        self.selected_product_data: Optional[Dict[str, Any]] = None
        self._products_cache: Dict[int, Dict[str, Any]] = {}
        self.selected_voucher_type: Optional[str] = None
        self.movement_types_list: List[str] = []
        self.product_model = QStringListModel([])
        self._loading = False
        self._register_thread = None
        self._register_worker = None
        self._build_ui()
        self.refresh()
        self._init_ui_memory()

    def _build_ui(self):
        """Build the Daily Stock Register UI."""
        self.setStyleSheet(page_background_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QLabel('Daily Stock Register')
        header.setStyleSheet(page_heading_style())
        root.addWidget(header)
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QVBoxLayout(filter_frame)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(10)
        top_row = QGridLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setHorizontalSpacing(10)
        top_row.setVerticalSpacing(6)
        field_height = BOOK_REPORT_ACTION_BUTTON_HEIGHT
        self.from_date = QDateEdit()
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        self.from_date.setFixedHeight(field_height)
        self.to_date = QDateEdit()
        self.to_date.setDate(QDate.currentDate())
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        self.to_date.setFixedHeight(field_height)
        self.product_filter = QLineEdit()
        self.product_filter.setPlaceholderText('Enter product name...')
        self.product_filter.setStyleSheet(compact_input_style())
        self.product_filter.setMinimumWidth(160)
        self.product_filter.setFixedHeight(field_height)
        self.product_filter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.product_filter.returnPressed.connect(self.on_product_enter)
        self.product_filter.editingFinished.connect(self._sync_product_selection_from_text)
        self.barcode_filter = QLineEdit()
        self.barcode_filter.setPlaceholderText('Scan barcode...')
        self.barcode_filter.setStyleSheet(sales_barcode_input_style())
        self.barcode_filter.setMinimumWidth(110)
        self.barcode_filter.setFixedHeight(field_height)
        self.barcode_filter.returnPressed.connect(self.on_barcode_enter)
        self.voucher_type_filter = QLineEdit()
        self.voucher_type_filter.setPlaceholderText('All')
        self.voucher_type_filter.setStyleSheet(compact_input_style())
        self.voucher_type_filter.setMinimumWidth(110)
        self.voucher_type_filter.setFixedHeight(field_height)
        self.voucher_type_filter.returnPressed.connect(self.on_voucher_type_enter)
        self.voucher_type_filter.setReadOnly(True)
        self.voucher_type_filter.mousePressEvent = self.on_voucher_type_click
        self.load_btn = QPushButton('Load')
        self.refresh_btn = QPushButton('Refresh')
        self.load_btn.clicked.connect(self.load_report)
        self.refresh_btn.clicked.connect(self.refresh)
        add_labeled_filter_rows(
            top_row,
            [[
                ('From', self.from_date),
                ('To', self.to_date),
                ('Product', self.product_filter),
                ('Barcode', self.barcode_filter),
                ('Voucher Type', self.voucher_type_filter),
            ]],
        )
        for col in range(top_row.columnCount()):
            top_row.setColumnStretch(col, 0)
        top_row.setColumnStretch(2, 1)
        action_layout = create_filter_action_layout([self.load_btn, self.refresh_btn])
        attach_filter_action_row(top_row, action_layout, row=2)
        filter_layout.addLayout(top_row)
        root.addWidget(filter_frame)
        self.summary_label = QLabel('Ready')
        self.summary_label.setStyleSheet(report_summary_label_style())
        root.addWidget(self.summary_label)
        self.table = QTableWidget()
        self.table.setStyleSheet(report_data_table_style())
        apply_read_only_report_table_selection(self.table)
        self.table.itemDoubleClicked.connect(self.on_row_double_clicked)
        root.addWidget(self.table)

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        colors = theme._theme_colors()
        self.setStyleSheet(page_background_style())
        self.table.setStyleSheet(report_data_table_style())
        self.summary_label.setStyleSheet(report_summary_label_style())
        if self.current_report_data:
            self.populate_table(self.current_report_data)
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())

    def label(self, text):
        """Create a compact label."""
        lbl = QLabel(text)
        lbl.setStyleSheet(compact_label_style())
        return lbl

    def refresh(self):
        """Refresh data and filters."""
        from config import active_company_manager
        self.company_id = active_company_manager.get_active_company_id()
        if not self.company_id:
            self.show_no_data('Please open a company first.')
            return
        self.populate_product_options()
        self.populate_voucher_types()
        self.load_report()

    def populate_product_options(self):
        """Load products into cache for popup dialog (matching Stock Adjustment)."""
        if not self.company_id:
            self._products_cache = {}
            self.selected_product_data = None
            self.product_filter.clear()
            self.product_filter.setEnabled(False)
            return
        self.product_filter.setEnabled(True)
        preserved_name = self.product_filter.text().strip()
        self._products_cache = {}
        all_products = self.logic.get_all_products(self.company_id)
        for product in all_products:
            self._products_cache[product['id']] = product
        self.product_options = all_products
        if preserved_name:
            self.product_filter.setText(preserved_name)
            self.selected_product_data = self.logic.resolve_product(
                self.company_id,
                preserved_name,
                barcode=self.barcode_filter.text().strip() or None,
            )
        else:
            self.selected_product_data = None

    def populate_voucher_types(self):
        """Populate movement type options for popup."""
        if not self.company_id:
            return
        movement_types = self.logic.get_voucher_types(self.company_id)
        print(f'[DAILY STOCK REGISTER] Movement types from DB: {movement_types}')
        self.movement_types_list = movement_types or []
        print(f'[DAILY STOCK REGISTER] Movement types list: {self.movement_types_list}')

    def on_voucher_type_click(self, event):
        """Handle voucher type click - show popup dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem
        from PySide6.QtCore import Qt
        popup = QDialog(self)
        popup.setWindowTitle('Select Movement Type')
        popup.resize(250, 300)
        popup.setStyleSheet(theme.entry_picker_dialog_style())
        layout = QVBoxLayout(popup)
        label = QLabel('Select Movement Type:')
        layout.addWidget(label)
        list_widget = QListWidget()
        list_widget.addItem('All')
        print(f'[DAILY STOCK REGISTER] Popup movement types: {self.movement_types_list}')
        for mt in self.movement_types_list:
            if mt and mt.strip():
                list_widget.addItem(mt.strip())
        layout.addWidget(list_widget)
        button_layout = QHBoxLayout()
        select_btn = QPushButton('Select')
        cancel_btn = QPushButton('Cancel')
        button_layout.addWidget(select_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        selected_voucher_type = [None]

        def on_select():
            current_item = list_widget.currentItem()
            if current_item:
                selected = current_item.text()
                if selected == 'All':
                    selected_voucher_type[0] = None
                else:
                    selected_voucher_type[0] = selected
            popup.accept()

        def on_cancel():
            popup.reject()
        select_btn.clicked.connect(on_select)
        cancel_btn.clicked.connect(on_cancel)
        list_widget.itemDoubleClicked.connect(on_select)
        if popup.exec() == QDialog.Accepted:
            if selected_voucher_type[0] is not None:
                self.voucher_type_filter.setText(selected_voucher_type[0] if selected_voucher_type[0] else 'All')
                self.selected_voucher_type = selected_voucher_type[0]
            else:
                self.voucher_type_filter.setText('All')
                self.selected_voucher_type = None
            self.load_report()

    def on_voucher_type_enter(self):
        """Handle voucher type Enter key - trigger load."""
        self.load_report()

    def on_product_enter(self):
        """Handle product input Enter key - open product search popup dialog (like Stock Adjustment)."""
        print('[DAILY STOCK REGISTER] on_product_enter called')
        self.show_product_dialog()

    def show_product_dialog(self):
        """Show product search popup dialog (same pattern as Stock Adjustment)."""
        from config import active_company_manager
        company_id = active_company_manager.get_active_company_id()
        if not company_id:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView
        from PySide6.QtCore import Qt, QTimer
        popup = QDialog(self)
        popup.setWindowTitle('Select Product')
        popup.resize(620, 440)
        popup.setStyleSheet(theme.entry_picker_dialog_style())
        layout = QVBoxLayout(popup)
        search_layout = QHBoxLayout()
        search_label = QLabel('Search Product:')
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type product name or barcode...')
        search_layout.addWidget(search_label)
        search_layout.addWidget(search_input)
        layout.addLayout(search_layout)
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['Name', 'Barcode', 'Stock', 'Rate', ''])
        apply_read_only_report_table_selection(table)
        layout.addWidget(table)
        button_layout = QHBoxLayout()
        select_btn = QPushButton('Select')
        cancel_btn = QPushButton('Cancel')
        button_layout.addWidget(select_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        products = list(self._products_cache.values())
        table.setRowCount(len(products))
        print(f'[DAILY STOCK REGISTER] POPUP: Loading {len(products)} products from cache')
        for row, product in enumerate(products):
            table.setItem(row, 0, QTableWidgetItem(str(product.get('name') or '')))
            table.setItem(row, 1, QTableWidgetItem(str(product.get('barcode') or '')))
            try:
                stock_qty = float(product.get('quantity') or 0)
            except (TypeError, ValueError):
                stock_qty = 0.0
            table.setItem(row, 2, QTableWidgetItem(f'{stock_qty:.3f}'))
            try:
                rate = float(
                    product.get('sale_price') or product.get('mrp') or product.get('purchase_rate') or 0
                )
            except (TypeError, ValueError):
                rate = 0.0
            table.setItem(row, 3, QTableWidgetItem(f'{rate:.2f}'))
        apply_adjustable_table_columns(table)
        selected_product = [None]

        def on_search_changed():
            text = search_input.text().strip().lower()
            print(f"[DAILY STOCK REGISTER] SEARCH TEXT: '{text}'")
            for row in range(table.rowCount()):
                name = table.item(row, 0).text().lower()
                barcode = table.item(row, 1).text().lower()
                if text in name or text in barcode:
                    table.setRowHidden(row, False)
                else:
                    table.setRowHidden(row, True)

        def on_select():
            current_row = table.currentRow()
            if current_row >= 0:
                name = table.item(current_row, 0).text()
                for product in self._products_cache.values():
                    if product.get('name') == name:
                        selected_product[0] = product
                        break
            popup.accept()

        def on_cancel():
            popup.reject()
        search_input.textChanged.connect(on_search_changed)
        select_btn.clicked.connect(on_select)
        cancel_btn.clicked.connect(on_cancel)
        table.itemDoubleClicked.connect(on_select)
        QTimer.singleShot(100, search_input.setFocus)
        if popup.exec() == QDialog.Accepted and selected_product[0]:
            product = selected_product[0]
            print(f"[DAILY STOCK REGISTER] Product selected from popup: {product.get('name')}")
            self._products_cache[product['id']] = product
            self.product_filter.setText(product.get('name', ''))
            self.selected_product_data = product
            self.load_report()

    def _sync_product_selection_from_text(self) -> None:
        """Keep selected product in sync when the user types a product name."""
        if not self.company_id:
            return
        product_text = self.product_filter.text().strip()
        if not product_text:
            self.selected_product_data = None
            return
        if (
            self.selected_product_data
            and str(self.selected_product_data.get('name', '')).strip().lower() == product_text.lower()
        ):
            return
        self.selected_product_data = self.logic.resolve_product(
            self.company_id,
            product_text,
            barcode=self.barcode_filter.text().strip() or None,
        )

    def _resolve_report_filters(self) -> Optional[Dict[str, Any]]:
        """Build validated filter payload from the top bar controls."""
        if not self.company_id:
            return None

        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        if from_date > to_date:
            QMessageBox.warning(self, 'Invalid Date Range', 'From Date cannot be later than To Date.')
            return None

        barcode_text = self.barcode_filter.text().strip()
        product_text = self.product_filter.text().strip()
        product = self.logic.resolve_product(
            self.company_id,
            product_text,
            barcode=barcode_text or None,
        )
        if product:
            self.selected_product_data = product
            self.product_filter.setText(str(product.get('name') or product_text))
            if barcode_text and str(product.get('barcode') or '').strip() != barcode_text:
                QMessageBox.warning(
                    self,
                    'Barcode Mismatch',
                    'The entered barcode does not match the selected product name.',
                )
                return None
        elif product_text or barcode_text:
            label = barcode_text or product_text
            QMessageBox.warning(
                self,
                'Product Not Found',
                f'No unique product found for: {label}',
            )
            return None
        else:
            self.selected_product_data = None

        return {
            'from_date': from_date,
            'to_date': to_date,
            'product_id': int(product['id']) if product else None,
            'location_id': None,
            'voucher_type': self.selected_voucher_type,
            'barcode': None,
        }

    def on_barcode_enter(self):
        """Handle barcode Enter key - auto-select product and refresh."""
        barcode = self.barcode_filter.text().strip()
        if not barcode or not self.company_id:
            return
        product = self.logic.get_product_by_barcode(self.company_id, barcode)
        if product:
            self.product_filter.setText(product.get('name', ''))
            self.selected_product_data = product
            self.load_report()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Product Not Found', f'No product found with barcode: {barcode}')
            self.barcode_filter.selectAll()

    def load_report(self):
        """Load report data based on filters."""
        if self._loading:
            return
        if not self.company_id:
            self.show_no_data('Please open a company first.')
            return
        filters = self._resolve_report_filters()
        if not filters:
            return
        thread = QThread(self)
        worker = DailyStockRegisterWorker(
            getattr(self.db, 'db_type', None),
            getattr(self.db, 'db_path', None),
            self.company_id,
            filters,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(self._apply_register_data)
        worker.error.connect(self._show_load_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._register_worker_finished)
        self._register_thread = thread
        self._register_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _apply_register_data(self, rows: List[Dict[str, Any]]):
        """Apply worker rows on the GUI thread."""
        self.current_report_data = rows or []
        if not self.current_report_data:
            self.show_no_data('No stock movements available.')
            return
        self.populate_table(self.current_report_data)

    def _set_loading_state(self, is_loading: bool):
        """Disable controls while report data is loading."""
        self._loading = is_loading
        for widget in (
            self.from_date,
            self.to_date,
            self.product_filter,
            self.barcode_filter,
            self.voucher_type_filter,
            self.load_btn,
            self.refresh_btn,
        ):
            widget.setEnabled(not is_loading)
        self.load_btn.setText('Loading...' if is_loading else 'Load')
        if is_loading:
            self.show_no_data('Loading stock register...')

    def _register_worker_finished(self):
        """Clear worker references and restore controls."""
        self._register_thread = None
        self._register_worker = None
        self._set_loading_state(False)

    def _show_load_error(self, message: str):
        """Display worker errors without touching worker-owned objects."""
        self.show_no_data(message)

    def populate_table(self, data: List[Dict[str, Any]]):
        """Populate table with stock register data."""
        headers = [
            'Date', 'Voucher Type', 'Voucher No', 'Product',
            'IN Qty', 'OUT Qty', 'Balance Qty', 'Rate', 'Value (₹)', 'Narration',
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        if not data:
            self.table.setRowCount(1)
            item = QTableWidgetItem('No Stock Movements Available')
            item.setForeground(QColor('#fbbf24'))
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(0, 0, item)
            self.table.setSpan(0, 0, 1, len(headers))
            self.summary_label.setText('No stock movements found for selected filters.')
            return
        self.table.setRowCount(len(data))
        total_in = 0.0
        total_out = 0.0
        for row_index, row in enumerate(data):
            self.set_cell(row_index, 0, format_display_date(row.get('date', '')))
            voucher_type = row.get('voucher_type', '')
            self.set_cell(row_index, 1, voucher_type)
            self.set_cell(row_index, 2, row.get('voucher_no', ''))
            self.set_cell(row_index, 3, row.get('product_name', ''))
            qty_in = row.get('qty_in', 0.0)
            total_in += qty_in
            self.set_cell(row_index, 4, self.format_qty(qty_in), align_right=True, color='#4ade80')
            qty_out = row.get('qty_out', 0.0)
            total_out += qty_out
            self.set_cell(row_index, 5, self.format_qty(qty_out), align_right=True, color='#f87171')
            balance_qty = row.get('balance_qty', 0.0)
            self.set_cell(row_index, 6, self.format_qty(balance_qty), align_right=True, bold=True)
            rate = row.get('rate', 0.0)
            self.set_cell(row_index, 7, self.format_rate(rate), align_right=True)
            value = row.get('value', 0.0)
            self.set_cell(row_index, 8, self.format_currency(value), align_right=True)
            self.set_cell(row_index, 9, row.get('narration', ''))
        self.resize_table_columns()
        final_balance = data[-1].get('balance_qty', 0.0) if data else 0.0
        summary = f'Total IN: {self.format_qty(total_in)} | Total OUT: {self.format_qty(total_out)} | Final Balance: {self.format_qty(final_balance)}'
        self.summary_label.setText(summary)

    def set_cell(self, row, col, text, align_right=False, color=None, bold=False):
        colors = theme._theme_colors()
        item = QTableWidgetItem(str(text))
        item.setForeground(QColor(color or colors['table_text']))
        item.setTextAlignment((Qt.AlignRight if align_right else Qt.AlignLeft) | Qt.AlignVCenter)
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        self.table.setItem(row, col, item)

    def resize_table_columns(self):
        apply_adjustable_table_columns(self.table)

    def show_no_data(self, message):
        """Show no data message in table."""
        headers = ['Message']
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(1)
        item = QTableWidgetItem(message)
        item.setForeground(QColor('#fbbf24'))
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(0, 0, item)
        self.summary_label.setText(message)

    def on_row_double_clicked(self, index):
        """Handle row double-click - open related voucher entry page using centralized dispatcher."""
        row = index.row()
        if row < 0 or row >= len(self.current_report_data):
            return
        data = self.current_report_data[row]
        reference_type = data.get('reference_type')
        reference_id = data.get('reference_id')
        movement_type = data.get('movement_type')
        print(f'[DAILY STOCK REGISTER] DOUBLE CLICK - reference_type={reference_type}, reference_id={reference_id}, movement_type={movement_type}')
        print(f'[DAILY STOCK REGISTER] DOUBLE CLICK VOUCHER TYPE = {reference_type}')
        print(f'[DAILY STOCK REGISTER] DOUBLE CLICK VOUCHER NO = {reference_id}')
        print(f'[DAILY STOCK REGISTER] DOUBLE CLICK MOVEMENT TYPE = {movement_type}')
        if not reference_type or not reference_id:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, 'No Reference', 'This stock movement has no linked voucher.')
            return
        main_window = self.window()
        while main_window and (not hasattr(main_window, 'open_voucher_for_edit')):
            main_window = main_window.parent()
        if not main_window:
            print('[DAILY STOCK REGISTER] Could not find main window')
            return
        print(f'[DAILY STOCK REGISTER] OPEN ROUTE = main_window.open_voucher_for_edit({reference_type}, {reference_id})')
        try:
            main_window.open_voucher_for_edit(reference_type, reference_id)
        except Exception as e:
            print(f'[DAILY STOCK REGISTER] Error opening voucher: {e}')
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Error', f'Could not open voucher: {e}')

    @staticmethod
    def format_qty(value):
        """Format quantity."""
        try:
            return f'{float(value or 0.0):,.2f}'
        except Exception:
            return '0.00'

    @staticmethod
    def format_rate(value):
        """Format rate."""
        try:
            return f'{float(value or 0.0):,.2f}'
        except Exception:
            return '0.00'

    @staticmethod
    def format_currency(value):
        """Format currency with ₹ symbol."""
        try:
            return f'₹{float(value or 0.0):,.2f}'
        except Exception:
            return '₹0.00'