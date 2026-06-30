"""Van Entry / Van Load Entry page."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox, QFrame, QAbstractItemView, QHeaderView, QInputDialog, QCheckBox, QDialog
from PySide6.QtCore import Qt, QDate, QEvent, QTimer, QModelIndex
from config import active_company_manager
from bizora_core.common_finance import to_decimal, format_money
from bizora_core.van_logic import VanLogic
from .sales_entry_popup import setup_product_completer
from ui import theme
from ui.checkbox_style import create_checkbox
from ui.sales_entry_delegate import SalesBillDelegate
from ui.theme_palette import palette
from ui.book_report_common import page_background_style, report_compound_entry_page_style
from .table_header_utils import apply_adjustable_table_columns
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class VanEntryWidget(UiMemoryMixin, QWidget):
    """Van Load Entry widget."""
    COL_SL = 0
    COL_PRODUCT = 1
    COL_STOCK = 2
    COL_LOAD_QTY = 3
    COL_RATE = 4

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.logic = VanLogic(self.db)
        self.vans = []
        self.current_load_id = None
        self._van_load_nav_ids = []
        self._loading = False
        self.manually_selected_row = -1
        self._products_list = []
        self._barcode_cache = {}
        self._sales_entry_window = None
        self.setup_ui()
        self._install_event_filters()
        self.load_initial_data()
        self._init_ui_memory()

    def label_style(self):
        return theme.sales_micro_label_style()

    def input_style(self):
        return theme.sales_compact_input_style()

    def button_style(self, color=None):
        p = palette()
        color = color or p['BLUE']
        hover = p['FOCUS']
        return f"\n            QPushButton {{\n                background-color: {color};\n                color: white;\n                border: none;\n                border-radius: 3px;\n                padding: 4px 8px;\n                font-weight: bold;\n                font-size: 11px;\n                min-height: 24px;\n            }}\n            QPushButton:hover {{\n                background-color: {hover};\n            }}\n            QPushButton:disabled {{\n                background-color: {p['MUTED']};\n                color: {p['TEXT']};\n            }}\n        "

    def table_style(self):
        return theme.editable_table_style()

    def setup_ui(self):
        p = palette()
        self.setObjectName('VanEntryWidget')
        self.setStyleSheet(page_background_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        title = QLabel('Van Entry / Van Load Entry')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"\n            QLabel {{\n                color: {p['BLUE']};\n                background-color: {p['PANEL']};\n                border: 1px solid {p['BORDER']};\n                border-radius: 6px;\n                padding: 8px;\n                font-size: 20px;\n                font-weight: bold;\n            }}\n        ")
        root.addWidget(title)
        top = QFrame()
        top.setStyleSheet(f"QFrame {{ background-color: {p['PANEL_2']}; border: 1px solid {p['BORDER']}; border-radius: 3px; }}")
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(4)
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self.load_no_edit = QLineEdit()
        self.load_no_edit.setReadOnly(True)
        self.load_no_edit.setStyleSheet(self.input_style())
        self.load_no_edit.setFixedWidth(75)
        self.date_edit = QDateEdit()
        configure_qdate_edit(self.date_edit)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setStyleSheet(self.input_style())
        self.date_edit.setFixedWidth(100)
        row1.addWidget(self._label('Load No:'))
        row1.addWidget(self.load_no_edit)
        nav_container = QWidget()
        nav_container.setFixedWidth(18)
        nav_v = QVBoxLayout(nav_container)
        nav_v.setSpacing(1)
        nav_v.setContentsMargins(0, 0, 0, 0)
        self.prev_load_btn = QPushButton('▲')
        self.prev_load_btn.setToolTip('Next Van Load')
        self.prev_load_btn.setStyleSheet(theme.sales_nav_button_style())
        self.prev_load_btn.setFixedSize(18, 11)
        self.prev_load_btn.clicked.connect(self.next_van_load)
        nav_v.addWidget(self.prev_load_btn)
        self.next_load_btn = QPushButton('▼')
        self.next_load_btn.setToolTip('Previous Van Load')
        self.next_load_btn.setStyleSheet(theme.sales_nav_button_style())
        self.next_load_btn.setFixedSize(18, 11)
        self.next_load_btn.clicked.connect(self.previous_van_load)
        nav_v.addWidget(self.next_load_btn)
        row1.addWidget(nav_container)
        self.header_reset_btn = QPushButton('Reset')
        self.header_reset_btn.setStyleSheet(theme.sales_compact_button_style())
        self.header_reset_btn.setFixedWidth(50)
        self.header_reset_btn.clicked.connect(self.reset_form)
        row1.addWidget(self.header_reset_btn)
        row1.addWidget(self._label('Date:'))
        row1.addWidget(self.date_edit)
        row1.addStretch()
        top_layout.addLayout(row1)
        row2 = QHBoxLayout()
        row2.setSpacing(4)
        self.van_combo = QComboBox()
        self.van_combo.setStyleSheet(self.input_style())
        self.van_combo.setFixedWidth(250)
        self.refresh_btn = QPushButton('Refresh Products')
        self.refresh_btn.setStyleSheet(self.button_style('#475569'))
        self.refresh_btn.clicked.connect(self.load_products_cache)
        self.add_van_btn = QPushButton('Manage Vans')
        self.add_van_btn.setStyleSheet(self.button_style('#475569'))
        self.add_van_btn.clicked.connect(self.manage_vans)
        row2.addWidget(self._label('Select Van:'))
        row2.addWidget(self.van_combo)
        row2.addWidget(self.refresh_btn)
        row2.addWidget(self.add_van_btn)
        row2.addStretch()
        top_layout.addLayout(row2)
        strip_frame = QFrame()
        strip_frame.setStyleSheet(f"QFrame {{ background-color: {p['PANEL_2']}; border: 1px solid {p['BORDER']}; border-radius: 4px; }}")
        strip_layout = QHBoxLayout(strip_frame)
        strip_layout.setSpacing(3)
        strip_layout.setContentsMargins(4, 4, 4, 4)
        code_layout = QHBoxLayout()
        code_layout.setSpacing(0)
        code_layout.setContentsMargins(0, 0, 0, 0)
        self.barcode_tick = create_checkbox(variant='compact')
        self.barcode_tick.setChecked(True)
        code_layout.addWidget(self.barcode_tick)
        barcode_label = QLabel(' Barcode')
        barcode_label.setStyleSheet(self.label_style())
        barcode_label.setFixedWidth(58)
        code_layout.addWidget(barcode_label)
        self.barcode_input = QLineEdit()
        self.barcode_input.setStyleSheet(theme.sales_barcode_input_style() if hasattr(theme, 'sales_barcode_input_style') else self.input_style())
        self.barcode_input.setFixedWidth(120)
        self.barcode_input.returnPressed.connect(self.on_barcode_enter)
        code_layout.addWidget(self.barcode_input)
        strip_layout.addLayout(code_layout)
        prod_layout = QHBoxLayout()
        prod_layout.setSpacing(1)
        prod_label = QLabel('Product')
        prod_label.setStyleSheet(self.label_style())
        prod_label.setFixedWidth(50)
        self.product_input = QLineEdit()
        self.product_input.setStyleSheet(self.input_style())
        self.product_input.setFixedWidth(280)
        prod_layout.addWidget(prod_label)
        prod_layout.addWidget(self.product_input)
        strip_layout.addLayout(prod_layout)
        strip_layout.addStretch()
        top_layout.addWidget(strip_frame)
        row6 = QHBoxLayout()
        row6.setSpacing(4)
        self.narration_edit = QLineEdit()
        self.narration_edit.setStyleSheet(self.input_style())
        self.narration_edit.setFixedWidth(380)
        row6.addWidget(self._label('Narration:'))
        row6.addWidget(self.narration_edit)
        row6.addStretch()
        top_layout.addLayout(row6)
        root.addWidget(top)
        section = QLabel('Products')
        section.setStyleSheet(f"color: {p['YELLOW']}; background-color: {p['PANEL']}; border: 1px solid {p['BORDER']}; border-radius: 5px; padding: 5px; font-weight: bold;")
        root.addWidget(section)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['SL No', 'Product Name', 'Current Main Stock', 'Load Qty', 'Rate'])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)
        self.table.setStyleSheet(self.table_style())
        self.table.horizontalHeader().setSectionResizeMode(self.COL_PRODUCT, QHeaderView.Stretch)
        self.table.setColumnWidth(self.COL_SL, 50)
        self.table.setColumnWidth(self.COL_STOCK, 120)
        self.table.setColumnWidth(self.COL_LOAD_QTY, 100)
        self.table.setColumnWidth(self.COL_RATE, 100)
        self.table_delegate = SalesBillDelegate(self)
        self.table.setItemDelegate(self.table_delegate)
        self.table.setRowCount(0)
        self.table.itemChanged.connect(self.on_item_changed)
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)
        root.addWidget(self.table, 1)
        footer = QFrame()
        footer.setStyleSheet(f"QFrame {{ background-color: {p['PANEL_2']}; border: 1px solid {p['BORDER']}; border-radius: 4px; }}")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(6, 6, 6, 6)
        footer_layout.setSpacing(4)
        self.remove_item_btn = QPushButton('Remove Item')
        self.remove_item_btn.setStyleSheet(theme.sales_danger_button_style() if hasattr(theme, 'sales_danger_button_style') else self.button_style(RED))
        self.remove_item_btn.clicked.connect(self.remove_selected_item)
        footer_layout.addWidget(self.remove_item_btn)
        self.remove_entry_btn = QPushButton('Remove Van Entry')
        self.remove_entry_btn.setStyleSheet(theme.sales_danger_button_style() if hasattr(theme, 'sales_danger_button_style') else self.button_style(RED))
        self.remove_entry_btn.setToolTip('Delete this saved Van Entry permanently')
        self.remove_entry_btn.clicked.connect(self.remove_van_entry)
        footer_layout.addWidget(self.remove_entry_btn)
        footer_layout.addStretch()
        self.convert_btn = QPushButton('Convert to Sales')
        self.convert_btn.setStyleSheet(self.button_style('#7c3aed'))
        self.convert_btn.setToolTip('Convert this Van Entry into a Sales Bill')
        self.convert_btn.clicked.connect(self.convert_to_sales_bill)
        self.save_btn = QPushButton('Save Van Load')
        self.save_btn.setStyleSheet(self.button_style(p['GREEN']))
        self.save_btn.clicked.connect(self.save_van_load)
        self.reset_btn = QPushButton('Reset All')
        self.reset_btn.setStyleSheet(self.button_style('#64748b'))
        self.reset_btn.clicked.connect(self.reset_form)
        self.exit_btn = QPushButton('Exit')
        self.exit_btn.setStyleSheet(self.button_style('#475569'))
        self.exit_btn.clicked.connect(self.close_window)
        footer_layout.addWidget(self.convert_btn)
        footer_layout.addWidget(self.save_btn)
        footer_layout.addWidget(self.reset_btn)
        footer_layout.addWidget(self.exit_btn)
        root.addWidget(footer)

    def _label(self, text):
        label = QLabel(text)
        label.setStyleSheet(self.label_style())
        label.setMinimumWidth(80)
        return label

    def company_id(self):
        return active_company_manager.get_active_company_id()

    def load_initial_data(self):
        company_id = self.company_id()
        if not company_id:
            return
        self.logic.ensure_schema()
        self.load_no_edit.setText(self.logic.get_next_van_load_no(company_id))
        self.load_vans()
        self.load_products_cache()
        self._setup_product_completer()

    def load_vans(self):
        company_id = self.company_id()
        self.van_combo.blockSignals(True)
        self.van_combo.clear()
        self.vans = []
        if company_id:
            self.vans = self.logic.get_vans(company_id)
        if not self.vans:
            self.van_combo.addItem('-- Add Van First --', None)
        else:
            for van in self.vans:
                self.van_combo.addItem(van.get('location_name', ''), van.get('id'))
        self.van_combo.blockSignals(False)

    def load_products_cache(self):
        """Build product lookup caches. Table stays EMPTY."""
        company_id = self.company_id()
        self._products_list = []
        self._barcode_cache = {}
        if not company_id:
            return
        self._products_list = self.logic.get_products_for_van_load(company_id)
        for p in self._products_list:
            bc = str(p.get('barcode', '')).strip()
            if bc:
                self._barcode_cache[bc] = p

    def _set_item(self, row, col, text, editable=True, align=None):
        item = QTableWidgetItem(str(text))
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if editable:
            flags |= Qt.ItemIsEditable
        item.setFlags(flags)
        if align is not None:
            item.setTextAlignment(align)
        self.table.setItem(row, col, item)
        return item

    def on_item_changed(self, item):
        if self._loading or item.column() not in (self.COL_LOAD_QTY, self.COL_RATE):
            return
        value = to_decimal(item.text())
        item.setText(str(value))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def manage_vans(self):
        company_id = self.company_id()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        dialog = VanSelectionPopup(self, self.db, self.logic)
        if dialog.exec() and dialog.selected_van:
            self.load_vans()
            index = self.van_combo.findData(dialog.selected_van['id'])
            if index >= 0:
                self.van_combo.setCurrentIndex(index)

    def collect_items(self):
        items = []
        for row in range(self.table.rowCount()):
            product_item = self.table.item(row, self.COL_PRODUCT)
            if not product_item:
                continue
            product = product_item.data(Qt.UserRole) or {}
            load_qty = to_decimal(self._text(row, self.COL_LOAD_QTY))
            if load_qty <= 0:
                continue
            items.append({'product_id': product.get('product_id'), 'product_name': product.get('product_name', product_item.text()), 'current_main_stock': self._text(row, self.COL_STOCK), 'load_qty': load_qty, 'rate': self._text(row, self.COL_RATE)})
        return items

    def _text(self, row, col):
        item = self.table.item(row, col)
        return item.text() if item else ''

    def save_van_load(self):
        company_id = self.company_id()
        van_id = self.van_combo.currentData()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        if not van_id:
            QMessageBox.warning(self, 'No Van', 'Please add/select a van first.')
            return
        items = self.collect_items()
        result = self.logic.save_van_entry(company_id=company_id, van_id=van_id, load_date=qdate_to_db(self.date_edit.date()), items=items, narration=self.narration_edit.text().strip())
        if result.get('success'):
            QMessageBox.information(self, 'Saved', result.get('message', 'Van Load saved.'))
            self.reset_form()
        else:
            QMessageBox.warning(self, 'Error', result.get('message', 'Failed to save Van Load.'))

    def remove_van_entry(self):
        """Safely delete the currently loaded Van Entry with confirmation."""
        company_id = self.company_id()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        load_id = self.current_load_id
        if not load_id:
            QMessageBox.warning(self, 'No Van Entry Selected', 'Please navigate to a saved Van Entry before deleting.\nUse the ▲/▼ buttons to load a previous entry.')
            return
        load_no = self.load_no_edit.text().strip() or str(load_id)
        ans = QMessageBox.question(self, 'Remove Van Entry', f"Do you want to remove Van Entry  '{load_no}'?\n\nThis will permanently delete:\n  • The Van Entry header\n  • All product rows\n  • Any associated stock movements\n\nThis action cannot be undone.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        result = self.logic.delete_van_load(company_id, load_id)
        if result.get('success'):
            QMessageBox.information(self, 'Deleted', result.get('message', 'Van Entry deleted.'))
            self.reset_form()
        else:
            QMessageBox.warning(self, 'Delete Failed', result.get('message', 'Failed to delete Van Entry.'))

    def reset_form(self):
        company_id = self.company_id()
        self.current_load_id = None
        self.narration_edit.clear()
        self.barcode_input.clear()
        self.product_input.clear()
        self.date_edit.setDate(QDate.currentDate())
        self.table.clearFocus()
        self.table.clearSelection()
        self.table.setCurrentItem(None)
        self.manually_selected_row = -1
        self.table.setRowCount(0)
        if company_id:
            self.load_no_edit.setText(self.logic.get_next_van_load_no(company_id))
        self.barcode_input.setFocus()

    def previous_van_load(self):
        """Navigate to previous van load."""
        company_id = self.company_id()
        if not company_id:
            return
        current_load_id = self.current_load_id
        if current_load_id:
            prev_load = self.logic.get_previous_van_load(company_id, current_load_id)
            if prev_load:
                self.load_van_load_by_id(int(prev_load['id']))
        else:
            ids = self.logic.get_van_load_ids(company_id)
            if ids:
                self.load_van_load_by_id(ids[-1])

    def next_van_load(self):
        """Navigate to next van load."""
        company_id = self.company_id()
        if not company_id:
            return
        current_load_id = self.current_load_id
        if current_load_id:
            next_load = self.logic.get_next_van_load(company_id, current_load_id)
            if next_load:
                self.load_van_load_by_id(int(next_load['id']))

    def load_van_load_by_id(self, load_id):
        """Load van load by ID."""
        company_id = self.company_id()
        if not company_id:
            return
        result = self.logic.get_van_load_by_id(company_id, load_id)
        if not result or not result.get('success'):
            return
        header = result.get('header') or {}
        items = result.get('items', [])
        self.current_load_id = load_id
        self.load_no_edit.setText(str(header.get('load_no', load_id)))
        date_str = header.get('load_date', '')
        if date_str:
            self.date_edit.setDate(QDate.fromString(str(date_str), 'yyyy-MM-dd'))
        van_id = header.get('van_id')
        for i in range(self.van_combo.count()):
            if self.van_combo.itemData(i) == van_id:
                self.van_combo.setCurrentIndex(i)
                break
        self.narration_edit.setText(header.get('narration') or '')
        self._loading = True
        self.table.clearFocus()
        self.table.clearSelection()
        self.table.setCurrentItem(None)
        self.table.setRowCount(0)
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            self._set_item(row, self.COL_SL, str(row + 1), editable=False, align=Qt.AlignCenter)
            name_item = self._set_item(row, self.COL_PRODUCT, item.get('product_name', ''), editable=False)
            name_item.setData(Qt.UserRole, {'product_id': item.get('product_id'), 'product_name': item.get('product_name', '')})
            stock_val = item.get('main_stock_before') or item.get('current_main_stock') or 0
            self._set_item(row, self.COL_STOCK, str(to_decimal(stock_val)), editable=False, align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_item(row, self.COL_LOAD_QTY, str(to_decimal(item.get('load_qty'))), editable=True, align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_item(row, self.COL_RATE, str(to_decimal(item.get('rate'))), editable=True, align=Qt.AlignRight | Qt.AlignVCenter)
        self._loading = False

    def on_barcode_enter(self):
        """Barcode field Enter — look up product and add to table."""
        code = self.barcode_input.text().strip()
        if not code:
            self.product_input.setFocus()
            return
        product = self._barcode_cache.get(code)
        if not product and self.db:
            cid = self.company_id()
            raw = self.db.get_product_by_barcode(cid, code) if cid else None
            if raw:
                product = {'product_id': raw['id'], 'product_name': raw.get('name', ''), 'barcode': raw.get('barcode', ''), 'current_main_stock': raw.get('quantity', 0), 'rate': raw.get('sale_price') or raw.get('mrp') or raw.get('purchase_rate') or 0}
        if not product:
            QMessageBox.warning(self, 'Product Not Found', f'No product for barcode: {code}')
            self.barcode_input.clear()
            self.barcode_input.setFocus()
            return
        self._add_product_to_table(product)
        self.barcode_input.clear()
        self.barcode_input.setFocus()

    def _add_product_to_table(self, product, qty=1.0, rate=None):
        """Add product row or increment Load Qty if product already present. Returns the row index."""
        pid = product.get('product_id') or product.get('id')
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_PRODUCT)
            if item:
                ex = item.data(Qt.UserRole) or {}
                if (ex.get('product_id') or ex.get('id')) == pid and pid:
                    qi = self.table.item(row, self.COL_LOAD_QTY)
                    if qi:
                        self._loading = True
                        qi.setText(str(to_decimal(qi.text()) + to_decimal(qty)))
                        qi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        self._loading = False
                    return row
        if rate is None:
            rate = product.get('rate') or product.get('sale_price') or 0
        r = self.table.rowCount()
        self._loading = True
        self.table.insertRow(r)
        self._set_item(r, self.COL_SL, str(r + 1), editable=False, align=Qt.AlignCenter)
        ni = self._set_item(r, self.COL_PRODUCT, product.get('product_name', product.get('name', '')), editable=False)
        ni.setData(Qt.UserRole, product)
        self._set_item(r, self.COL_STOCK, str(to_decimal(product.get('current_main_stock', product.get('quantity', 0)))), editable=False, align=Qt.AlignRight | Qt.AlignVCenter)
        self._set_item(r, self.COL_LOAD_QTY, str(to_decimal(qty)), editable=True, align=Qt.AlignRight | Qt.AlignVCenter)
        self._set_item(r, self.COL_RATE, str(to_decimal(rate)), editable=True, align=Qt.AlignRight | Qt.AlignVCenter)
        self._loading = False
        return r

    def _setup_product_completer(self):
        pass

    def _install_event_filters(self):
        for w in [self.date_edit, self.van_combo, self.barcode_input, self.product_input, self.narration_edit, self.table]:
            w.installEventFilter(self)
        self.table.viewport().installEventFilter(self)

    def show_product_popup(self):
        """Show product search popup dialog (same pattern as sales entry)."""
        company_id = self.company_id()
        if not company_id:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView
        from PySide6.QtCore import Qt, QTimer
        popup = QDialog(self)
        popup.setWindowTitle('Select Product')
        popup.resize(620, 440)
        popup.setStyleSheet(report_compound_entry_page_style())
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)
        top = QHBoxLayout()
        search_lbl = QLabel('Search (name / barcode):')
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type at least 2 characters…')
        top.addWidget(search_lbl)
        top.addWidget(search_input)
        layout.addLayout(top)
        hint = QLabel('Type to search. Max 100 results shown.')
        hint.setStyleSheet('color: #64748b; font-size: 10px;')
        layout.addWidget(hint)
        tbl = QTableWidget()
        tbl.setColumnCount(5)
        tbl.setHorizontalHeaderLabels(['Name', 'Barcode', 'Code', 'Rate', 'Stock'])
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setColumnWidth(0, 220)
        tbl.setColumnWidth(1, 110)
        tbl.setColumnWidth(2, 80)
        tbl.setColumnWidth(3, 80)
        layout.addWidget(tbl)
        _search_timer = QTimer()
        _search_timer.setSingleShot(True)
        _search_timer.setInterval(200)

        def do_search():
            term = search_input.text().strip()
            tbl.setRowCount(0)
            if len(term) < 1:
                return
            results = self.db.search_products_limited(company_id, term, limit=100)
            tbl.setUpdatesEnabled(False)
            tbl.blockSignals(True)
            for product in results:
                row = tbl.rowCount()
                tbl.insertRow(row)
                name_item = QTableWidgetItem(product.get('name', ''))
                name_item.setData(Qt.UserRole, product.get('id'))
                tbl.setItem(row, 0, name_item)
                tbl.setItem(row, 1, QTableWidgetItem(str(product.get('barcode', '') or '')))
                tbl.setItem(row, 2, QTableWidgetItem(str(product.get('code', '') or '')))
                rate = float(product.get('sale_price') or product.get('mrp') or product.get('wholesale_rate') or product.get('purchase_rate') or 0)
                tbl.setItem(row, 3, QTableWidgetItem(f'{rate:.2f}'))
                stock = float(product.get('quantity') or 0.0)
                tbl.setItem(row, 4, QTableWidgetItem(f'{stock:.3f}'))
            tbl.blockSignals(False)
            tbl.setUpdatesEnabled(True)
            if tbl.rowCount() > 0:
                tbl.selectRow(0)
            apply_adjustable_table_columns(tbl)
        _search_timer.timeout.connect(do_search)
        search_input.textChanged.connect(lambda: _search_timer.start())
        initial_term = self.product_input.text().strip() if hasattr(self, 'product_input') else ''
        search_input.setText(initial_term)
        search_input.setFocus()
        if initial_term:
            search_input.selectAll()

        def search_key_press(event):
            if event.key() == Qt.Key_Up:
                row = tbl.currentRow()
                if row > 0:
                    tbl.selectRow(row - 1)
                return
            elif event.key() == Qt.Key_Down:
                row = tbl.currentRow()
                if row < tbl.rowCount() - 1:
                    tbl.selectRow(row + 1)
                return
            elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
                select_product()
                return
            elif event.key() == Qt.Key_Escape:
                popup.reject()
                return
            QLineEdit.keyPressEvent(search_input, event)
        search_input.keyPressEvent = search_key_press

        def select_product():
            row = tbl.currentRow()
            if row < 0:
                return
            product_id = tbl.item(row, 0).data(Qt.UserRole)
            product_name = tbl.item(row, 0).text()
            try:
                stock_val = float(tbl.item(row, 4).text())
            except (ValueError, AttributeError):
                stock_val = 0.0
            try:
                rate_val = float(tbl.item(row, 3).text())
            except (ValueError, AttributeError):
                rate_val = 0.0
            code_val = tbl.item(row, 2).text() if tbl.item(row, 2) else ''
            full_product = self.db.get_product_by_id(company_id, product_id)
            if full_product:
                product = full_product
            else:
                product = {'id': product_id, 'name': product_name, 'rate': rate_val, 'code': code_val}
            self.product_input.blockSignals(True)
            self.product_input.setText(product_name)
            self.product_input.blockSignals(False)
            popup.accept()
            target_row = self._add_product_to_table(product)
            if target_row is not None and target_row >= 0:
                if hasattr(self, 'table_delegate') and hasattr(self.table_delegate, 'move_to_cell'):
                    self.table_delegate.move_to_cell(target_row, self.COL_LOAD_QTY)
                else:
                    self.table.setCurrentCell(target_row, self.COL_LOAD_QTY)
                    idx = self.table.model().index(target_row, self.COL_LOAD_QTY)
                    if idx.isValid():
                        self.table.edit(idx)
        tbl.doubleClicked.connect(select_product)
        btns = QHBoxLayout()
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(popup.reject)
        select_btn = QPushButton('Select')
        select_btn.setStyleSheet(theme.sales_primary_button_style())
        select_btn.clicked.connect(select_product)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(select_btn)
        layout.addLayout(btns)

        def key_press(event):
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                select_product()
            elif event.key() == Qt.Key_Escape:
                popup.reject()
            else:
                QDialog.keyPressEvent(popup, event)
        popup.keyPressEvent = key_press
        popup.exec()

    def recalculate_row(self, row, **kwargs):
        """Called by SalesBillDelegate after edit completes. VanEntry has no row totals to calculate."""
        pass

    def close_window(self):
        w = self.window()
        if w:
            w.close()

    def remove_selected_item(self):
        """Remove the selected row after SL No click (Sales Entry pattern)."""
        target_row = getattr(self, 'manually_selected_row', -1)
        if target_row < 0:
            QMessageBox.information(
                self,
                'Remove Item',
                'Please click the SL No of the item you want to remove, then press Remove Item.',
            )
            return
        if target_row >= self.table.rowCount():
            self.manually_selected_row = -1
            return
        reply = QMessageBox.question(
            self,
            'Remove Item',
            f'Are you sure you want to remove item at row {target_row + 1}?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.table.removeRow(target_row)
        self.manually_selected_row = -1
        self.table.clearSelection()
        self.table.viewport().update()
        self._loading = True
        for r in range(self.table.rowCount()):
            it = self.table.item(r, self.COL_SL)
            if it:
                it.setText(str(r + 1))
        self._loading = False
        self.barcode_input.setFocus()

    def eventFilter(self, obj, event):
        if obj == self.table.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                item = self.table.itemAt(event.pos())
                if item:
                    clicked_row = item.row()
                    clicked_column = item.column()
                    if clicked_column == 0:
                        self.manually_selected_row = clicked_row
                        self.table.clearSelection()
                        self.table.viewport().update()
                        return True
                    else:
                        self.manually_selected_row = -1
                        self.table.clearSelection()
                        self.table.viewport().update()
                        self.table.editItem(item)
                        return True
        if event.type() != QEvent.KeyPress:
            return super().eventFilter(obj, event)
        key = event.key()
        enter = key in (Qt.Key_Return, Qt.Key_Enter)
        esc = key == Qt.Key_Escape
        f1 = key == Qt.Key_F1
        if f1:
            if self.table.rowCount() > 0:
                row = self.table.rowCount() - 1
                if hasattr(self, 'table_delegate') and hasattr(self.table_delegate, 'move_to_cell'):
                    self.table_delegate.move_to_cell(row, self.COL_LOAD_QTY)
                else:
                    self.table.setCurrentCell(row, self.COL_LOAD_QTY)
                    idx = self.table.model().index(row, self.COL_LOAD_QTY)
                    if idx.isValid():
                        self.table.edit(idx)
            return True
        if enter:
            if obj is self.date_edit:
                self.van_combo.setFocus()
                return True
            if obj is self.van_combo:
                self.barcode_input.setFocus()
                return True
            if obj is self.barcode_input:
                self.on_barcode_enter()
                return True
            if obj is self.product_input:
                self.show_product_popup()
                return True
            if obj is self.narration_edit:
                self.barcode_input.setFocus()
                return True
        if esc:
            if obj is self.table:
                self.table.clearFocus()
                self.barcode_input.setFocus()
                return True
            if obj is self.narration_edit:
                self.product_input.setFocus()
                return True
            if obj is self.product_input:
                self.barcode_input.setFocus()
                return True
            if obj is self.barcode_input:
                self.van_combo.setFocus()
                return True
            if obj is self.van_combo:
                self.date_edit.setFocus()
                return True
        return super().eventFilter(obj, event)

    def convert_to_sales_bill(self):
        """ERP-style: convert Van Entry into a Sales Bill with safe tracking."""
        company_id = self.company_id()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        load_id = self.current_load_id
        if load_id:
            status = self.logic.get_van_load_conversion_status(company_id, load_id)
            if status.get('converted'):
                ref = status.get('sales_ref', '')
                QMessageBox.warning(self, 'Already Converted', f"Van Entry already converted to Sales Bill{(' (' + ref + ')' if ref else '')}.")
                return
        items = []
        for row in range(self.table.rowCount()):
            pi = self.table.item(row, self.COL_PRODUCT)
            if not pi:
                continue
            prod = pi.data(Qt.UserRole) or {}
            load_qty = to_decimal(self._text(row, self.COL_LOAD_QTY))
            rate = to_decimal(self._text(row, self.COL_RATE))
            if load_qty <= 0:
                continue
            items.append({'product_id': prod.get('product_id') or prod.get('id'), 'name': prod.get('product_name', pi.text()), 'barcode': prod.get('barcode', ''), 'qty': float(load_qty), 'rate': float(rate)})
        if not items:
            QMessageBox.warning(self, 'No Items', 'No items with load qty > 0 to convert.')
            return
        if load_id:
            self.logic.mark_van_load_converted(company_id, load_id, 'Pending')
        self._open_sales_with_items(items, source_van_load_id=load_id)

    def _open_sales_with_items(self, items, source_van_load_id=None):
        if hasattr(self, '_sales_entry_window') and self._sales_entry_window is not None:
            if self._sales_entry_window.isVisible():
                QMessageBox.warning(self, 'In Progress', 'Conversion is already in progress.')
                self._sales_entry_window.activateWindow()
                return
        try:
            from .sales_entry import SalesEntryWidget
            from .standalone_window import StandaloneModuleWindow, _resolve_hub_window
            widget = SalesEntryWidget(self.db)
            title = f'Sales Entry — Van Load #{source_van_load_id}' if source_van_load_id else 'Sales Entry (Van Conversion)'
            hub = _resolve_hub_window(self.window())
            win = StandaloneModuleWindow(widget, title, hub)
            if hub is not None:
                hub._center_and_show_window(win)
            else:
                win.show()
            self._sales_entry_window = win
            QTimer.singleShot(300, lambda: widget.preload_van_items(items, source_van_load_id=source_van_load_id))
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not open Sales Entry:\n{e}')

class VanSelectionPopup(UiMemoryMixin, QDialog):

    def __init__(self, parent, db, logic):
        super().__init__(parent)
        self.db = db
        self.logic = logic
        self.selected_van = None
        self.setup_ui()
        self.load_vans()
        self._init_ui_memory()

    def setup_ui(self):
        p = palette()
        self.setWindowTitle('Manage Vans')
        self.setFixedSize(400, 450)
        self.setStyleSheet(f"QDialog {{ background-color: {p['BG']}; color: {p['TEXT']}; }}")
        layout = QVBoxLayout(self)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search vans...')
        self.search_input.setStyleSheet(theme.sales_compact_input_style() if hasattr(theme, 'sales_compact_input_style') else '')
        self.search_input.textChanged.connect(self.filter_vans)
        self.search_input.installEventFilter(self)
        layout.addWidget(self.search_input)
        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(['Van Name'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(theme.editable_table_style() if hasattr(theme, 'editable_table_style') else '')
        self.table.itemDoubleClicked.connect(self.accept_selection)
        self.table.installEventFilter(self)
        layout.addWidget(self.table)
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton('New Van')
        self.add_btn.clicked.connect(self.add_van)
        self.edit_btn = QPushButton('Edit')
        self.edit_btn.clicked.connect(self.edit_van)
        self.del_btn = QPushButton('Delete')
        self.del_btn.clicked.connect(self.delete_van)
        btn_style = '\n            QPushButton { background-color: #3b82f6; color: white; border-radius: 3px; padding: 4px; font-weight: bold; }\n            QPushButton:hover { background-color: #2563eb; }\n        '
        for btn in (self.add_btn, self.edit_btn, self.del_btn):
            btn.setStyleSheet(btn_style)
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

    def load_vans(self, search_text=''):
        from config import active_company_manager
        company_id = active_company_manager.get_active_company_id()
        if not company_id:
            return
        vans = self.logic.get_vans(company_id)
        if search_text:
            search_text = search_text.lower()
            vans = [v for v in vans if search_text in str(v.get('location_name', '')).lower()]
        self.table.setRowCount(len(vans))
        for i, van in enumerate(vans):
            item = QTableWidgetItem(van.get('location_name', ''))
            item.setData(Qt.UserRole, van.get('id'))
            self.table.setItem(i, 0, item)
        if vans:
            self.table.selectRow(0)
        apply_adjustable_table_columns(self.table)

    def filter_vans(self, text):
        self.load_vans(text)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Down and obj == self.search_input:
                self.table.setFocus()
                if self.table.rowCount() > 0:
                    self.table.selectRow(0)
                return True
            elif event.key() == Qt.Key_Return:
                self.accept_selection()
                return True
            elif event.key() == Qt.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(obj, event)

    def accept_selection(self):
        row = self.table.currentRow()
        if row >= 0:
            item = self.table.item(row, 0)
            if item:
                self.selected_van = {'id': item.data(Qt.UserRole), 'name': item.text()}
                self.accept()

    def add_van(self):
        from config import active_company_manager
        company_id = active_company_manager.get_active_company_id()
        if not company_id:
            return
        dialog = QInputDialog(self)
        dialog.setWindowTitle('New Van')
        dialog.setLabelText('Enter van name:')

        def auto_upper(text):
            upper_text = text.upper()
            if text != upper_text:
                dialog.setTextValue(upper_text)
        dialog.textValueChanged.connect(auto_upper)
        if dialog.exec():
            name = dialog.textValue().strip()
            if name:
                res = self.logic.create_van(company_id, name)
                if not res.get('success'):
                    QMessageBox.warning(self, 'Error', res.get('message', 'Error adding van'))
                self.load_vans(self.search_input.text())

    def edit_van(self):
        from config import active_company_manager
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        van_id = item.data(Qt.UserRole)
        company_id = active_company_manager.get_active_company_id()
        dialog = QInputDialog(self)
        dialog.setWindowTitle('Edit Van')
        dialog.setLabelText('Enter new van name:')
        dialog.setTextValue(item.text())

        def auto_upper(text):
            upper_text = text.upper()
            if text != upper_text:
                dialog.setTextValue(upper_text)
        dialog.textValueChanged.connect(auto_upper)
        if dialog.exec():
            new_name = dialog.textValue().strip()
            if new_name and new_name != item.text():
                res = self.logic.update_van(company_id, van_id, new_name)
                if not res.get('success'):
                    QMessageBox.warning(self, 'Error', res.get('message', 'Error updating van'))
                self.load_vans(self.search_input.text())

    def delete_van(self):
        from config import active_company_manager
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        van_id = item.data(Qt.UserRole)
        company_id = active_company_manager.get_active_company_id()
        if QMessageBox.question(self, 'Delete Van', f"Delete van '{item.text()}'?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            res = self.logic.delete_van(company_id, van_id)
            if not res.get('success'):
                QMessageBox.warning(self, 'Error', res.get('message', 'Error deleting van'))
            self.load_vans(self.search_input.text())