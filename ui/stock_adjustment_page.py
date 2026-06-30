"""
Stock Adjustment Page

Main widget for Stock Adjustment module.
Integrates with centralized stock movement and ledger posting systems.
"""
from decimal import Decimal
from PySide6.QtWidgets import QWidget, QTableWidgetItem, QMessageBox, QLineEdit, QAbstractItemView
from PySide6.QtCore import Qt, QDate, QTimer, QEvent
from config import active_company_manager
from db import Database
from bizora_core.stock_adjustment_logic import StockAdjustmentLogic
from bizora_core.stock_logic import StockLogic
from bizora_core.ledger_logic import LedgerLogic
from ui import theme
from .stock_adjustment_ui import StockAdjustmentUIMixin
from .stock_adjustment_delegate import StockAdjustmentDelegate
from .table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from .sales_entry_popup import setup_product_completer
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class StockAdjustmentWidget(UiMemoryMixin, QWidget, StockAdjustmentUIMixin):
    """Stock Adjustment main widget."""

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.adjustment_logic = StockAdjustmentLogic(self.db)
        self.stock_logic = StockLogic(self.db)
        self.ledger_logic = LedgerLogic(self.db)
        self.current_adjustment_id = None
        self._adjustment_nav_ids = []
        self._products_cache = {}
        self._deferred_load_started = False
        self._initial_load_done = False
        self.setup_ui()
        self._initialize_state()
        self._wire_signals()
        QTimer.singleShot(100, self._start_deferred_load)
        self._init_ui_memory()

    def _start_deferred_load(self):
        """Start deferred data loading."""
        if self._deferred_load_started:
            return
        self._deferred_load_started = True
        QTimer.singleShot(100, self._perform_deferred_load)

    def _perform_deferred_load(self):
        """Actually perform the heavy data loading."""
        try:
            self.load_products()
            self.generate_voucher_number()
            self._initial_load_done = True
        finally:
            self._deferred_load_started = False

    def _initialize_state(self):
        """Initialize widget state."""
        active = active_company_manager.get_active_company()
        if active:
            self._load_navigation_ids(active['id'])

    def _wire_signals(self):
        """Wire signal connections."""
        self.save_btn.clicked.connect(self.save_adjustment)
        self.remove_item_btn.clicked.connect(self.remove_item)
        self.clear_btn.clicked.connect(self.clear_form)
        self.prev_btn.clicked.connect(self.next_adjustment)
        self.next_btn.clicked.connect(self.previous_adjustment)
        self.barcode_input.returnPressed.connect(self.on_barcode_enter)
        completer = setup_product_completer(self.product_input, self, None, self.on_top_product_popup_selected, min_chars=1)
        if completer:
            completer.popup().installEventFilter(self)
        self.product_input.returnPressed.connect(self.on_product_enter)
        self.qty_only_checkbox.toggled.connect(self._update_totals)
        self.items_table.itemChanged.connect(self.on_item_changed)
        self.items_table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.items_table.installEventFilter(self)
        self.items_table.viewport().installEventFilter(self)
        delegate = StockAdjustmentDelegate(self)
        self.items_table.setItemDelegate(delegate)
        self.manually_selected_row = -1

    def load_products(self):
        """Load products into cache."""
        active = active_company_manager.get_active_company()
        if not active:
            return
        products = self.db.get_products_by_company(active['id'])
        self._products_cache = {p['id']: p for p in products}

    def _active_company_id(self):
        active = active_company_manager.get_active_company()
        return active.get('id') if active else None

    def _valuation_rate(self, product: dict) -> float:
        """Use product rates already carried by active product queries."""
        for key in ('purchase_rate', 'sale_price', 'mrp', 'wholesale_rate', 'rate'):
            try:
                value = float(product.get(key) or 0)
            except (TypeError, ValueError):
                value = 0.0
            if value:
                return value
        return 0.0

    def _safe_float(self, text, default=0.0):
        """Convert text to float safely (Sales Entry pattern)."""
        try:
            return float(text)
        except (ValueError, TypeError):
            return default

    def safe_float_from_cell(self, row, col, default=0.0):
        """Get float value from table cell safely (Sales Entry pattern)."""
        try:
            item = self.items_table.item(row, col)
            if item is None:
                return default
            return self._safe_float(item.text(), default)
        except Exception:
            return default

    def generate_voucher_number(self):
        """Generate next voucher number."""
        active = active_company_manager.get_active_company()
        if not active:
            return
        next_num = self.db.get_next_stock_adjustment_number(active['id'])
        self.voucher_no_input.setText(next_num)

    def _load_navigation_ids(self, company_id: int):
        """Load adjustment IDs for navigation."""
        self._adjustment_nav_ids = self.db.get_stock_adjustment_ids_by_company(company_id)

    def clear_form(self):
        """Clear the form for new entry."""
        self.current_adjustment_id = None
        self.generate_voucher_number()
        self.date_input.setDate(QDate.currentDate())
        self.narration_input.clear()
        self.barcode_input.clear()
        self.product_input.clear()
        self.stock_display.clear()
        self.rate_display.clear()
        self.qty_only_checkbox.setChecked(False)
        self.items_table.setRowCount(0)
        self._add_empty_row()
        self._update_totals()

    def on_barcode_enter(self):
        """Handle barcode Enter in top entry bar."""
        barcode = self.barcode_input.text().strip()
        print(f'[STOCK ADJ] BARCODE ENTERED = {barcode}')
        if not barcode:
            self.product_input.setFocus()
            self.product_input.selectAll()
            self.show_product_dialog()
            return
        product = self._find_product_by_barcode(barcode)
        if product:
            print(f"[STOCK ADJ] PRODUCT FOUND = {product.get('name')}")
            self._fill_top_entry_product(product)
            self._add_product_from_top_entry()
            self.barcode_input.clear()
        else:
            QMessageBox.warning(self, 'Product Not Found', f'No product found with barcode: {barcode}')
            self.barcode_input.selectAll()

    def on_product_enter(self):
        """Handle product input Enter key - open product search popup dialog like Sales Entry."""
        print('[STOCK ADJ] on_product_enter called')
        self.show_product_dialog()

    def show_product_dialog(self):
        """Show product search popup dialog (same pattern as Sales Entry)."""
        from config import active_company_manager
        company_id = active_company_manager.get_active_company_id()
        if not company_id:
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
        for row, product in enumerate(products):
            table.setItem(row, 0, QTableWidgetItem(product.get('name', '')))
            table.setItem(row, 1, QTableWidgetItem(product.get('barcode', '')))
            table.setItem(row, 2, QTableWidgetItem(f"{float(product.get('quantity', 0)):.3f}"))
            rate = self._valuation_rate(product)
            table.setItem(row, 3, QTableWidgetItem(f'{rate:.2f}'))
        apply_adjustable_table_columns(table)
        selected_product = [None]

        def on_search_changed():
            text = search_input.text().strip().lower()
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
            print(f"[STOCK ADJ] Product selected from popup: {product.get('name')}")
            self._products_cache[product['id']] = product
            self._fill_top_entry_product(product)
            self._add_product_from_top_entry()

    def eventFilter(self, obj, event):
        """Handle Enter/Esc on table when NOT editing, SL No click for row selection, and debug completer popup focus."""
        completer = self.product_input.completer() if hasattr(self, 'product_input') else None
        if completer and obj == completer.popup():
            if event.type() == QEvent.KeyPress:
                key = event.key()
                print(f'[STOCK ADJ] POPUP KEY PRESS: key={key}, obj={obj}, focusWidget={QApplication.focusWidget()}, popup.hasFocus()={completer.popup().hasFocus()}')
                if key == Qt.Key_Down:
                    print('[STOCK ADJ] DOWN KEY RECEIVED IN POPUP')
                if key == Qt.Key_Up:
                    print('[STOCK ADJ] UP KEY RECEIVED IN POPUP')
            elif event.type() == QEvent.Show:
                print(f'[STOCK ADJ] POPUP SHOW: obj={obj}, focusWidget={QApplication.focusWidget()}, popup.hasFocus()={completer.popup().hasFocus()}')
            elif event.type() == QEvent.FocusIn:
                print(f'[STOCK ADJ] POPUP FOCUS IN: obj={obj}, focusWidget={QApplication.focusWidget()}')
        if obj == self.items_table.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                item = self.items_table.itemAt(event.pos())
                if item:
                    clicked_row = item.row()
                    clicked_column = item.column()
                    print(f'[STOCK ADJ] viewport click: row={clicked_row}, col={clicked_column}')
                    if clicked_column == 0:
                        self.manually_selected_row = clicked_row
                        print(f'[STOCK ADJ] set manually_selected_row={clicked_row}')
                        self.items_table.clearSelection()
                        self.items_table.viewport().update()
                        return True
                    else:
                        self.manually_selected_row = -1
                        print(f'[STOCK ADJ] cleared manually_selected_row')
                        self.items_table.clearSelection()
                        self.items_table.viewport().update()
                        if clicked_column in [4, 8]:
                            self.items_table.editItem(item)
                        return True
        if obj == self.items_table and event.type() == QEvent.KeyPress:
            if self.items_table.state() != QAbstractItemView.EditingState:
                key = event.key()
                if key in (Qt.Key_Return, Qt.Key_Enter):
                    row = self.items_table.currentRow()
                    col = self.items_table.currentColumn()
                    if row >= 0 and col in [4, 8]:
                        item = self.items_table.item(row, col)
                        if item:
                            self.items_table.editItem(item)
                    return True
                elif key == Qt.Key_Escape:
                    self.barcode_input.setFocus()
                    return True
        return super().eventFilter(obj, event)

    def on_top_product_popup_selected(self, _index, model_idx, editor):
        """Sales Entry product completer callback for the top product field."""
        product = model_idx.data(Qt.UserRole) if model_idx.isValid() else None
        if not product:
            return
        self._products_cache[product['id']] = product
        self._fill_top_entry_product(product)
        self._add_product_from_top_entry()
        editor.clear()
        self.barcode_input.setFocus()

    def on_table_product_popup_selected(self, index, model_idx, _editor):
        """Sales Entry product completer callback for inline table product cells."""
        product = model_idx.data(Qt.UserRole) if model_idx.isValid() else None
        if not product or not index.isValid():
            return
        self._products_cache[product['id']] = product
        self._fill_product_details(index.row(), product)

    def _find_product_by_barcode(self, barcode: str):
        company_id = self._active_company_id()
        if company_id:
            product = self.db.get_product_by_barcode(company_id, barcode)
            if product:
                self._products_cache[product['id']] = product
                return product
        text = str(barcode).strip()
        for p in self._products_cache.values():
            if str(p.get('barcode') or '').strip() == text:
                return p
        return None

    def _find_product_by_name(self, name: str):
        text = str(name).strip().lower()
        for p in self._products_cache.values():
            if str(p.get('name') or '').strip().lower() == text:
                return p
        return None

    def _find_first_product_prefix(self, text: str):
        company_id = self._active_company_id()
        if company_id:
            results = self.db.search_products_limited(company_id, text, limit=1)
            if results:
                product = results[0]
                self._products_cache[product['id']] = product
                return product
        lower = text.strip().lower()
        for p in self._products_cache.values():
            if str(p.get('name') or '').lower().startswith(lower):
                return p
        return None

    def _fill_top_entry_product(self, product: dict):
        """Fill top entry bar with product details."""
        self.product_input.setText(product.get('name', ''))
        company_id = self._active_company_id()
        current_stock = self.stock_logic.get_current_stock(company_id, product['id']) if company_id else 0.0
        self.stock_display.setText(f'{float(current_stock):.3f}')
        rate = self._valuation_rate(product)
        self.rate_display.setText(f'{rate:.2f}')

    def _add_product_from_top_entry(self):
        """Add product from top entry bar to table."""
        product_name = self.product_input.text().strip()
        if not product_name:
            return
        product_id = None
        product = None
        for pid, p in self._products_cache.items():
            if p.get('name') == product_name:
                product_id = pid
                product = p
                break
        if not product_id:
            return
        for row in range(self.items_table.rowCount()):
            existing_item = self.items_table.item(row, 2)
            existing_product = existing_item.text().strip() if existing_item else ''
            if existing_product == product_name:
                self.items_table.setCurrentCell(row, 4)
                self.items_table.editItem(self.items_table.item(row, 4))
                self.product_input.clear()
                self._update_top_entry_from_row(row)
                return
        row = self.items_table.rowCount()
        for candidate in range(self.items_table.rowCount()):
            item = self.items_table.item(candidate, 2)
            if item is None or not item.text().strip():
                row = candidate
                break
        else:
            self.items_table.insertRow(row)
        self.items_table.blockSignals(True)
        try:
            sl_item = QTableWidgetItem(str(row + 1))
            sl_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 0, sl_item)
            barcode_item = QTableWidgetItem(product.get('barcode', ''))
            self.items_table.setItem(row, 1, barcode_item)
            product_item = QTableWidgetItem(product_name)
            self.items_table.setItem(row, 2, product_item)
            system_qty = float(self.stock_display.text() or '0')
            system_qty_item = QTableWidgetItem(f'{system_qty:.3f}')
            system_qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 3, system_qty_item)
            physical_qty_item = QTableWidgetItem('0.00')
            self.items_table.setItem(row, 4, physical_qty_item)
            diff_qty_item = QTableWidgetItem('0.00')
            diff_qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 5, diff_qty_item)
            rate = float(self.rate_display.text() or '0')
            rate_item = QTableWidgetItem(f'{rate:.2f}')
            self.items_table.setItem(row, 6, rate_item)
            value_item = QTableWidgetItem('0.00')
            value_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 7, value_item)
            reason_item = QTableWidgetItem('')
            self.items_table.setItem(row, 8, reason_item)
        finally:
            self.items_table.blockSignals(False)
        print(f'[STOCK ADJ] MOVE TO PHYSICAL QTY row={row}')
        self.items_table.setCurrentCell(row, 4)
        qty_item = self.items_table.item(row, 4)
        if qty_item:
            self.items_table.editItem(qty_item)
            QTimer.singleShot(0, lambda: self._select_editor_all())
        self.product_input.clear()
        self._update_top_entry_from_row(row)

    def _select_editor_all(self):
        """Select all text in current editor (Sales Entry pattern)."""
        current_widget = self.focusWidget()
        if isinstance(current_widget, QLineEdit):
            current_widget.selectAll()

    def _select_physical_qty_all(self):
        """Select all text in Physical Qty editor."""
        current_widget = self.focusWidget()
        if isinstance(current_widget, QLineEdit):
            current_widget.selectAll()

    def show_product_popup_for_top_entry(self, search_term: str):
        """Show product search popup for top entry bar with STARTS-WITH matching."""
        self.product_input.setText(search_term)
        completer = self.product_input.completer()
        if completer:
            completer.complete()
        return

    def _add_empty_row(self):
        """Add an empty row to the table."""
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        self.items_table.blockSignals(True)
        try:
            sl_item = QTableWidgetItem(str(row + 1))
            sl_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 0, sl_item)
            barcode_item = QTableWidgetItem('')
            self.items_table.setItem(row, 1, barcode_item)
            product_item = QTableWidgetItem('')
            self.items_table.setItem(row, 2, product_item)
            system_qty_item = QTableWidgetItem('0.00')
            system_qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 3, system_qty_item)
            physical_qty_item = QTableWidgetItem('0.00')
            self.items_table.setItem(row, 4, physical_qty_item)
            diff_qty_item = QTableWidgetItem('0.00')
            diff_qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 5, diff_qty_item)
            rate_item = QTableWidgetItem('0.00')
            self.items_table.setItem(row, 6, rate_item)
            value_item = QTableWidgetItem('0.00')
            value_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 7, value_item)
            reason_item = QTableWidgetItem('')
            self.items_table.setItem(row, 8, reason_item)
        finally:
            self.items_table.blockSignals(False)

    def on_item_changed(self, item):
        """Handle item change in table."""
        row = item.row()
        col = item.column()
        self.items_table.blockSignals(True)
        try:
            if col == 1:
                self._handle_barcode_change(row)
            elif col == 2:
                self._handle_product_change(row)
            elif col == 4:
                self._calculate_difference(row)
            elif col == 6:
                self._calculate_value(row)
            self._update_totals()
        finally:
            self.items_table.blockSignals(False)

    def _handle_barcode_change(self, row: int):
        """Handle barcode change - auto-fill product details."""
        barcode_item = self.items_table.item(row, 1)
        barcode = barcode_item.text().strip() if barcode_item else ''
        if not barcode:
            return
        product = self._find_product_by_barcode(barcode)
        if product:
            self._fill_product_details(row, product)
        else:
            QMessageBox.warning(self, 'Product Not Found', f'No product found with barcode: {barcode}')
            if barcode_item:
                barcode_item.setText('')

    def _handle_product_change(self, row: int):
        """Handle product change from inline editor."""
        product_item = self.items_table.item(row, 2)
        product_name = product_item.text().strip() if product_item else ''
        if len(product_name) < 1:
            return
        product = self._find_product_by_name(product_name)
        if product:
            self._fill_product_details(row, product)

    def _ensure_row_items(self, row: int):
        """Ensure a row has all cells before signal-driven autofill writes."""
        defaults = ['', '', '', '0.00', '0.00', '0.00', '0.00', '0.00', '']
        readonly_cols = {0, 3, 5, 7}
        for col, default in enumerate(defaults):
            if self.items_table.item(row, col) is None:
                value = str(row + 1) if col == 0 else default
                item = QTableWidgetItem(value)
                if col in readonly_cols:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.items_table.setItem(row, col, item)

    def show_product_popup(self, row: int, search_term: str):
        """Show product search popup with STARTS-WITH matching."""
        item = self.items_table.item(row, 2)
        if item:
            item.setText(search_term)
            self.items_table.setCurrentCell(row, 2)
            self.items_table.editItem(item)
        return
        search_input.setPlaceholderText('Type to search…')

    def _fill_product_details(self, row: int, product: dict):
        """Fill product details in row."""
        self.items_table.blockSignals(True)
        try:
            self._ensure_row_items(row)
            self.items_table.item(row, 2).setText(product.get('name', ''))
            self.items_table.item(row, 1).setText(product.get('barcode', ''))
            company_id = self._active_company_id()
            current_stock = self.stock_logic.get_current_stock(company_id, product['id']) if company_id else 0.0
            self.items_table.item(row, 3).setText(f'{float(current_stock):.3f}')
            rate = self._valuation_rate(product)
            self.items_table.item(row, 6).setText(f'{rate:.2f}')
            self.items_table.item(row, 4).setText('0.00')
            self._calculate_difference(row)
            self._calculate_value(row)
            self.items_table.setCurrentCell(row, 4)
            self.items_table.editItem(self.items_table.item(row, 4))
            self._update_top_entry_from_row(row)
        finally:
            self.items_table.blockSignals(False)

    def _calculate_difference(self, row: int):
        """Calculate difference qty = physical_qty - system_qty."""
        try:
            system_qty = Decimal(self.items_table.item(row, 3).text() or '0')
            physical_qty = Decimal(self.items_table.item(row, 4).text() or '0')
            difference = physical_qty - system_qty
            self.items_table.item(row, 5).setText(str(difference))
            self._calculate_value(row)
        except:
            self.items_table.item(row, 5).setText('0.00')

    def _calculate_value(self, row: int):
        """Calculate value = difference_qty * rate."""
        try:
            if self.qty_only_checkbox.isChecked():
                self.items_table.item(row, 7).setText('0.00')
                return
            difference_qty = Decimal(self.items_table.item(row, 5).text() or '0')
            rate = Decimal(self.items_table.item(row, 6).text() or '0')
            value = difference_qty * rate
            self.items_table.item(row, 7).setText(str(value))
        except:
            self.items_table.item(row, 7).setText('0.00')

    def _update_totals(self):
        """Calculate and update footer totals."""
        total_increase = Decimal('0')
        total_decrease = Decimal('0')
        qty_only = self.qty_only_checkbox.isChecked()
        for row in range(self.items_table.rowCount()):
            try:
                difference_qty = Decimal(self.items_table.item(row, 5).text() or '0')
                rate = Decimal(self.items_table.item(row, 6).text() or '0')
                value = Decimal('0') if qty_only else difference_qty * rate
                if difference_qty > 0:
                    total_increase += value
                elif difference_qty < 0:
                    total_decrease += abs(value)
            except:
                continue
        net_adjustment = total_increase - total_decrease
        self.total_increase_label.setText(f'{total_increase:.2f}')
        self.total_decrease_label.setText(f'{total_decrease:.2f}')
        self.net_adjustment_label.setText(f'{net_adjustment:.2f}')

    def on_table_selection_changed(self):
        """Handle table selection change (Sales Entry pattern)."""
        current_row = self.items_table.currentRow()
        if self.manually_selected_row == -1:
            self.items_table.clearSelection()
        self._update_top_entry_from_row(current_row)

    def _update_top_entry_from_row(self, row: int):
        """Keep the top stock/rate displays tied to the selected product row."""
        if row < 0 or row >= self.items_table.rowCount():
            self.stock_display.clear()
            self.rate_display.clear()
            return
        stock_item = self.items_table.item(row, 3)
        rate_item = self.items_table.item(row, 6)
        self.stock_display.setText(stock_item.text() if stock_item else '')
        self.rate_display.setText(rate_item.text() if rate_item else '')

    def _edit_clicked_cell(self, index):
        """Single-click edit with Sales Entry-style select-all behavior."""
        if not index.isValid() or index.column() not in [1, 2, 4, 6, 8]:
            return
        item = self.items_table.item(index.row(), index.column())
        if item:
            self.items_table.setCurrentCell(index.row(), index.column())
            self.items_table.editItem(item)

    def save_adjustment(self):
        """Save stock adjustment with atomic transaction."""
        active = active_company_manager.get_active_company()
        if not active:
            QMessageBox.warning(self, 'Error', 'No active company')
            return
        if self.items_table.rowCount() == 0:
            QMessageBox.warning(self, 'Error', 'No items to save')
            return
        qty_only = self.qty_only_checkbox.isChecked()
        items_data = []
        for row in range(self.items_table.rowCount()):
            product_name = self.items_table.item(row, 2).text().strip()
            if not product_name:
                continue
            product_id = None
            for pid, p in self._products_cache.items():
                if p.get('name') == product_name:
                    product_id = pid
                    break
            if not product_id:
                continue
            rate = 0.0 if qty_only else float(self.items_table.item(row, 6).text() or '0')
            value = 0.0 if qty_only else float(self.items_table.item(row, 7).text() or '0')
            item = {'sl_no': row + 1, 'product_id': product_id, 'barcode': self.items_table.item(row, 1).text().strip(), 'system_qty': float(self.items_table.item(row, 3).text() or '0'), 'physical_qty': float(self.items_table.item(row, 4).text() or '0'), 'difference_qty': float(self.items_table.item(row, 5).text() or '0'), 'rate': rate, 'value': value, 'reason': self.items_table.item(row, 8).text().strip()}
            if item['difference_qty'] == 0:
                continue
            items_data.append(item)
        if not items_data:
            QMessageBox.warning(self, 'Error', 'No valid items with quantity difference')
            return
        header_data = {'company_id': active['id'], 'voucher_no': self.voucher_no_input.text().strip(), 'voucher_date': qdate_to_db(self.date_input.date()), 'narration': self.narration_input.text().strip(), 'qty_only_no_value_effect': qty_only}
        if self.current_adjustment_id:
            result = self.adjustment_logic.update_adjustment(self.current_adjustment_id, header_data, items_data)
        else:
            result = self.adjustment_logic.save_adjustment(header_data, items_data)
        if result['success']:
            QMessageBox.information(self, 'Success', result['message'])
            self._load_navigation_ids(active['id'])
            self.clear_form()
        else:
            QMessageBox.critical(self, 'Error', result['message'])

    def remove_item(self):
        """Remove selected row from table (requires SL No selection)."""
        if self.manually_selected_row == -1:
            QMessageBox.warning(self, 'Warning', 'Please select a row by clicking SL No to delete.')
            return
        current_row = self.manually_selected_row
        if current_row < 0:
            return
        reply = QMessageBox.question(self, 'Confirm Remove', 'Remove selected item?', QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.items_table.removeRow(current_row)
            self.manually_selected_row = -1
            for row in range(self.items_table.rowCount()):
                sl_item = QTableWidgetItem(str(row + 1))
                self.items_table.setItem(row, 0, sl_item)
            self._update_totals()

    def previous_adjustment(self):
        """Navigate to previous adjustment."""
        if not self._adjustment_nav_ids:
            return
        if self.current_adjustment_id is None:
            if self._adjustment_nav_ids:
                self.load_adjustment(self._adjustment_nav_ids[0])
        else:
            try:
                idx = self._adjustment_nav_ids.index(self.current_adjustment_id)
                if idx < len(self._adjustment_nav_ids) - 1:
                    self.load_adjustment(self._adjustment_nav_ids[idx + 1])
            except ValueError:
                pass

    def next_adjustment(self):
        """Navigate to next adjustment."""
        if not self._adjustment_nav_ids:
            return
        if self.current_adjustment_id is None:
            if self._adjustment_nav_ids:
                self.load_adjustment(self._adjustment_nav_ids[0])
        else:
            try:
                idx = self._adjustment_nav_ids.index(self.current_adjustment_id)
                if idx > 0:
                    self.load_adjustment(self._adjustment_nav_ids[idx - 1])
            except ValueError:
                pass

    def load_adjustment(self, adjustment_id: int):
        """Load existing adjustment into form."""
        adjustment = self.db.get_stock_adjustment_by_id(adjustment_id)
        if not adjustment:
            return
        items = self.db.get_stock_adjustment_items(adjustment_id)
        self.current_adjustment_id = adjustment_id
        self.voucher_no_input.setText(adjustment.get('voucher_no', ''))
        self.date_input.setDate(QDate.fromString(adjustment.get('voucher_date', ''), 'yyyy-MM-dd'))
        self.narration_input.setText(adjustment.get('narration', ''))
        self.qty_only_checkbox.setChecked(False)
        self.barcode_input.clear()
        self.product_input.clear()
        self.stock_display.clear()
        self.rate_display.clear()
        self.items_table.setRowCount(0)
        for item in items:
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)
            sl_item = QTableWidgetItem(str(item.get('sl_no', row + 1)))
            sl_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 0, sl_item)
            barcode_item = QTableWidgetItem(item.get('barcode', ''))
            self.items_table.setItem(row, 1, barcode_item)
            product = self._products_cache.get(item.get('product_id'))
            product_name = product.get('name', '') if product else ''
            product_item = QTableWidgetItem(product_name)
            self.items_table.setItem(row, 2, product_item)
            system_qty_item = QTableWidgetItem(str(item.get('system_qty', 0)))
            system_qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 3, system_qty_item)
            physical_qty_item = QTableWidgetItem(str(item.get('physical_qty', 0)))
            self.items_table.setItem(row, 4, physical_qty_item)
            diff_qty_item = QTableWidgetItem(str(item.get('difference_qty', 0)))
            diff_qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 5, diff_qty_item)
            rate_item = QTableWidgetItem(str(item.get('rate', 0)))
            self.items_table.setItem(row, 6, rate_item)
            value_item = QTableWidgetItem(str(item.get('value', 0)))
            value_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.items_table.setItem(row, 7, value_item)
            reason_item = QTableWidgetItem(item.get('reason', ''))
            self.items_table.setItem(row, 8, reason_item)
        has_qty_change = any((float(item.get('difference_qty', 0) or 0) != 0 for item in items))
        has_value = any((float(item.get('value', 0) or 0) != 0 for item in items))
        self.qty_only_checkbox.setChecked(has_qty_change and (not has_value))
        self._update_totals()