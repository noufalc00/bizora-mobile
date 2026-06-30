"""
Stock Value Page Widget.

Displays inventory valuation based on selected rate basis.
Read-only report using existing stock movement system.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QCheckBox, QPushButton, QGridLayout, QMessageBox, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from config import COLORS, resolve_active_company_id
from bizora_core.stock_value_logic import StockValueLogic
from bizora_core.product_logic import ProductLogic
from db import Database
from ui import theme
from ui.book_report_common import add_labeled_filter_rows, attach_filter_action_row, compact_label_style, compact_input_style, compact_primary_button_style, compact_topbar_frame_style, create_filter_action_layout
from ui.theme import sales_barcode_input_style
from ui.checkbox_style import create_checkbox
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class StockValuePageWidget(UiMemoryMixin, QWidget):
    """Widget for displaying stock value inventory valuation."""

    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self.db = db or Database()
        self.logic = StockValueLogic(self.db)
        self.company_id = resolve_active_company_id(self.db)
        self.current_valuation = []
        self.rate_basis = 'purchase_rate'
        self.selected_product_id = None
        self.setup_ui()
        self.load_categories()
        self.load_locations()
        self.load_report()
        self._init_ui_memory(table_attrs=("table",))

    def setup_ui(self):
        """Setup the stock value page UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        header_layout = QHBoxLayout()
        title_label = QLabel('Stock Value')
        title_label.setStyleSheet(f"\n            QLabel {{\n                font-size: 24px;\n                font-weight: bold;\n                color: {COLORS['text_primary']};\n            }}\n        ")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        refresh_btn = QPushButton('Refresh')
        refresh_btn.setStyleSheet(compact_primary_button_style())
        refresh_btn.clicked.connect(self.load_report)
        header_layout.addWidget(refresh_btn)
        layout.addLayout(header_layout)
        self.setup_filters(layout)
        self.setup_table(layout)
        self.setup_totals(layout)

    def setup_filters(self, parent_layout):
        """Setup filter section (grid layout like Daily Stock Register)."""
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QVBoxLayout(filter_frame)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(10)
        top_row = QGridLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setHorizontalSpacing(8)
        top_row.setVerticalSpacing(6)
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText('Enter product name...')
        self.product_search.setMinimumWidth(140)
        self.product_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.product_search.setStyleSheet(compact_input_style())
        self.product_search.returnPressed.connect(self.on_product_search)
        self.barcode_search = QLineEdit()
        self.barcode_search.setPlaceholderText('Scan barcode...')
        self.barcode_search.setFixedWidth(120)
        self.barcode_search.setStyleSheet(sales_barcode_input_style())
        self.barcode_search.returnPressed.connect(self.on_barcode_search)
        self.category_combo = QComboBox()
        self.category_combo.addItem('All')
        self.category_combo.setFixedWidth(120)
        self.category_combo.setStyleSheet(compact_input_style())
        self.category_combo.currentTextChanged.connect(self.load_report)
        self.location_combo = QComboBox()
        self.location_combo.addItem('All')
        self.location_combo.setFixedWidth(120)
        self.location_combo.setStyleSheet(compact_input_style())
        self.location_combo.currentTextChanged.connect(self.load_report)
        self.rate_combo = QComboBox()
        self.rate_combo.addItems(['Purchase Rate', 'Sales Rate', 'Wholesale Rate', 'MRP'])
        self.rate_combo.setCurrentText('Purchase Rate')
        self.rate_combo.setFixedWidth(115)
        self.rate_combo.setStyleSheet(compact_input_style())
        self.rate_combo.currentTextChanged.connect(self.on_rate_basis_changed)
        add_labeled_filter_rows(top_row, [[('Product', self.product_search), ('Barcode', self.barcode_search), ('Category', self.category_combo), ('Location', self.location_combo)], [('Rate Basis', self.rate_combo)]])
        filter_layout.addLayout(top_row)
        self.hide_zero_checkbox = create_checkbox('Hide Zero Stock', variant='status')
        self.hide_zero_checkbox.stateChanged.connect(self.load_report)
        show_all_btn = QPushButton('Show All Stock Value')
        show_all_btn.clicked.connect(self.show_all_stock)
        action_layout = create_filter_action_layout([show_all_btn])
        action_layout.insertWidget(0, self.hide_zero_checkbox)
        attach_filter_action_row(top_row, action_layout, row=4)
        parent_layout.addWidget(filter_frame)

    def setup_table(self, parent_layout):
        """Setup stock value table (Ledger style)."""
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(['Barcode', 'Product Name', 'Category', 'Unit', 'Current Qty', 'Rate', 'Stock Value'])
        apply_read_only_report_table_selection(self.table)
        self.table.verticalHeader().setDefaultSectionSize(28)
        parent_layout.addWidget(self.table)

    def setup_totals(self, parent_layout):
        """Setup total section."""
        total_frame = QFrame()
        total_frame.setStyleSheet(compact_topbar_frame_style())
        total_layout = QHBoxLayout(total_frame)
        total_layout.setSpacing(20)
        total_layout.setContentsMargins(15, 10, 15, 10)
        qty_label = QLabel('Total Qty:')
        qty_label.setStyleSheet(compact_label_style())
        self.total_qty_label = QLabel('0.00')
        self.total_qty_label.setStyleSheet('color: #f1f5f9; font-size: 14px; font-weight: bold;')
        total_layout.addWidget(qty_label)
        total_layout.addWidget(self.total_qty_label)
        total_layout.addStretch()
        value_label = QLabel('Total Inventory Value:')
        value_label.setStyleSheet(compact_label_style())
        self.total_value_label = QLabel('₹0.00')
        self.total_value_label.setStyleSheet('\n            QLabel {\n                color: #10b981;\n                font-size: 18px;\n                font-weight: bold;\n                background: transparent;\n            }\n        ')
        total_layout.addWidget(value_label)
        total_layout.addWidget(self.total_value_label)
        parent_layout.addWidget(total_frame)

    def load_categories(self):
        """Load categories into combo box."""
        categories = self.logic.get_categories(self.company_id)
        for category in categories:
            self.category_combo.addItem(category)

    def load_locations(self):
        """Load locations into combo box."""
        locations = self.logic.get_locations(self.company_id)
        for location in locations:
            self.location_combo.addItem(location)

    def on_rate_basis_changed(self, text):
        """Handle rate basis combo change."""
        rate_map = {'Purchase Rate': 'purchase_rate', 'Sales Rate': 'sale_price', 'Wholesale Rate': 'wholesale_rate', 'MRP': 'mrp'}
        self.rate_basis = rate_map.get(text, 'purchase_rate')
        self.load_report()

    def on_product_search(self):
        """Apply the typed product filter when Enter is pressed."""
        self.load_report()

    def show_all_stock(self):
        """Show all stock value by clearing all filters."""
        self.product_search.clear()
        self.barcode_search.clear()
        self.category_combo.setCurrentText('All')
        self.location_combo.setCurrentText('All')
        self.hide_zero_checkbox.setChecked(False)
        self.selected_product_id = None
        self.load_report()

    def on_barcode_search(self):
        """Handle barcode search - auto-select product."""
        barcode = self.barcode_search.text().strip()
        if not barcode:
            return
        try:
            product = self.logic.get_product_by_barcode(self.company_id, barcode)
            if product:
                self.selected_product_id = product['id']
                self.product_search.setText(product.get('name', ''))
            else:
                self.selected_product_id = None
            self.load_report()
        except Exception as e:
            print(f'Error searching by barcode: {e}')

    def _resolve_product_filters(self):
        """Build product_id / product_name filters from the top bar fields."""
        product_text = self.product_search.text().strip()
        barcode_text = self.barcode_search.text().strip() or None
        product_id = None
        product_name = None

        if not product_text and not barcode_text:
            self.selected_product_id = None
            return None, None

        product = self.logic.resolve_product(
            self.company_id,
            product_text,
            barcode=barcode_text,
        )
        if product:
            product_id = int(product['id'])
            self.selected_product_id = product_id
            self.product_search.setText(str(product.get('name') or product_text))
            return product_id, None

        self.selected_product_id = None
        if product_text:
            product_name = product_text
        return product_id, product_name

    def load_report(self):
        """Load stock value report."""
        if not self.company_id:
            return
        product_id, product_name = self._resolve_product_filters()
        barcode = self.barcode_search.text().strip() or None
        if product_id:
            barcode = None
        category = self.category_combo.currentText()
        if category == 'All':
            category = None
        location = self.location_combo.currentText()
        if location == 'All':
            location = None
        hide_zero = self.hide_zero_checkbox.isChecked()
        self.current_valuation = self.logic.get_stock_valuation(
            company_id=self.company_id,
            rate_basis=self.rate_basis,
            product_id=product_id,
            product_name=product_name,
            barcode=barcode,
            category=category,
            location=location,
            hide_zero_stock=hide_zero,
        )
        self.populate_table()
        self.update_totals()

    def populate_table(self):
        """Populate table with valuation data."""
        self.table.setRowCount(0)
        for record in self.current_valuation:
            row = self.table.rowCount()
            self.table.insertRow(row)
            barcode_item = QTableWidgetItem(str(record['barcode']))
            barcode_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row, 0, barcode_item)
            name_item = QTableWidgetItem(record['name'])
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row, 1, name_item)
            category_item = QTableWidgetItem(record['category'])
            category_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row, 2, category_item)
            unit_item = QTableWidgetItem(record['unit'])
            unit_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row, 3, unit_item)
            qty_item = QTableWidgetItem(f"{record['current_qty']:.2f}")
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 4, qty_item)
            rate_item = QTableWidgetItem(f"₹{record['rate']:.2f}")
            rate_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 5, rate_item)
            value_item = QTableWidgetItem(f"₹{record['stock_value']:.2f}")
            value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 6, value_item)
        if self.table.rowCount() == 0:
            self.table.insertRow(0)
            empty_item = QTableWidgetItem('No Stock Data Available')
            empty_item.setTextAlignment(Qt.AlignCenter)
            empty_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(0, 0, empty_item)
            self.table.setSpan(0, 0, 1, 7)
        apply_adjustable_table_columns(self.table)
        self._restore_memory_table(self.table, "table")

    def update_totals(self):
        """Update total labels."""
        totals = self.logic.get_stock_valuation_totals(self.current_valuation)
        self.total_qty_label.setText(f"{totals['total_qty']:.2f}")
        self.total_value_label.setText(f"₹{totals['total_value']:.2f}")

    def refresh(self):
        """Refresh the report."""
        self.load_categories()
        self.load_locations()
        self.load_report()