"""
Stock Adjustment UI Mixin

Provides UI layout for Stock Adjustment module.
Matches visual style of Sales Entry, Purchase Entry, Opening Balance.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QDateEdit, QPushButton, QTableWidget, QHeaderView, QFrame,
    QCheckBox, QAbstractItemView
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QDoubleValidator

from ui import theme
from ui.checkbox_style import create_checkbox
from ui.date_formats import configure_qdate_edit
from ui.table_header_utils import apply_adjustable_table_columns


class StockAdjustmentUIMixin:
    """UI mixin for Stock Adjustment module."""
    
    def setup_ui(self):
        """Build the complete Stock Adjustment UI."""
        self.setStyleSheet(theme.entry_page_background_style())
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)
        
        # Header section (voucher command strip)
        header_frame = self.build_header_section()
        main_layout.addWidget(header_frame)
        
        # Product entry strip (barcode, product, stock, rate)
        product_entry_frame = self.build_product_entry_strip()
        main_layout.addWidget(product_entry_frame)
        
        # Table section
        table_layout = self.build_table_section()
        main_layout.addLayout(table_layout)
        
        # Footer section
        footer_layout = self.build_footer_section()
        main_layout.addLayout(footer_layout)

        try:
            from ui.financial_year_guard import apply_financial_year_guard_to_named_dates
            apply_financial_year_guard_to_named_dates(self, "date_input")
        except Exception:
            pass
    
    def build_header_section(self):
        """Build header section with voucher no, date, narration, navigation next to voucher."""
        frame = QFrame()
        frame.setStyleSheet(theme.entry_header_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 4, 6, 4)
        
        # Voucher No with navigation buttons (like Sales Entry)
        voucher_layout = QHBoxLayout()
        voucher_layout.setSpacing(2)
        
        voucher_label = QLabel("Voucher")
        voucher_label.setStyleSheet(theme.sales_micro_label_style())
        voucher_label.setFixedWidth(45)
        voucher_layout.addWidget(voucher_label)
        
        self.voucher_no_input = QLineEdit()
        self.voucher_no_input.setReadOnly(True)
        self.voucher_no_input.setPlaceholderText("Auto")
        self.voucher_no_input.setFixedWidth(100)
        self.voucher_no_input.setStyleSheet(theme.sales_compact_input_style())
        voucher_layout.addWidget(self.voucher_no_input)
        
        # Navigation buttons - vertical stack next to voucher (like Sales Entry)
        nav_container = QWidget()
        nav_container.setFixedWidth(18)
        nav_v = QVBoxLayout(nav_container)
        nav_v.setSpacing(1)
        nav_v.setContentsMargins(0, 0, 0, 0)
        
        self.prev_btn = QPushButton("▲")
        self.prev_btn.setStyleSheet(theme.sales_nav_button_style())
        self.prev_btn.setFixedSize(18, 11)
        nav_v.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("▼")
        self.next_btn.setStyleSheet(theme.sales_nav_button_style())
        self.next_btn.setFixedSize(18, 11)
        nav_v.addWidget(self.next_btn)
        
        voucher_layout.addWidget(nav_container)
        layout.addLayout(voucher_layout)
        
        # Date
        date_layout = QHBoxLayout()
        date_layout.setSpacing(2)
        date_label = QLabel("Dt")
        date_label.setStyleSheet(theme.sales_micro_label_style())
        date_label.setFixedWidth(20)
        date_layout.addWidget(date_label)
        
        self.date_input = QDateEdit()
        configure_qdate_edit(self.date_input)
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setFixedWidth(90)
        self.date_input.setStyleSheet(theme.sales_compact_input_style())
        date_layout.addWidget(self.date_input)
        layout.addLayout(date_layout)
        
        # Narration
        narration_layout = QHBoxLayout()
        narration_layout.setSpacing(2)
        narration_label = QLabel("Narration")
        narration_label.setStyleSheet(theme.sales_micro_label_style())
        narration_label.setFixedWidth(55)
        narration_layout.addWidget(narration_label)
        
        self.narration_input = QLineEdit()
        self.narration_input.setPlaceholderText("Enter narration...")
        self.narration_input.setMinimumWidth(200)
        self.narration_input.setStyleSheet(theme.sales_compact_input_style())
        narration_layout.addWidget(self.narration_input)
        layout.addLayout(narration_layout)
        
        layout.addStretch()
        
        return frame
    
    def build_product_entry_strip(self):
        """Build product entry strip with barcode, product, stock display, rate display."""
        frame = QFrame()
        frame.setStyleSheet(theme.entry_header_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 4, 6, 4)
        
        # Barcode input
        barcode_layout = QHBoxLayout()
        barcode_layout.setSpacing(2)
        barcode_label = QLabel("Barcode")
        barcode_label.setStyleSheet(theme.sales_micro_label_style())
        barcode_label.setFixedWidth(50)
        barcode_layout.addWidget(barcode_label)
        
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan barcode...")
        self.barcode_input.setFixedWidth(120)
        self.barcode_input.setStyleSheet(theme.sales_barcode_input_style())
        barcode_layout.addWidget(self.barcode_input)
        layout.addLayout(barcode_layout)
        
        # Product input
        product_layout = QHBoxLayout()
        product_layout.setSpacing(2)
        product_label = QLabel("Product")
        product_label.setStyleSheet(theme.sales_micro_label_style())
        product_label.setFixedWidth(50)
        product_layout.addWidget(product_label)
        
        self.product_input = QLineEdit()
        self.product_input.setPlaceholderText("Enter product name...")
        self.product_input.setMinimumWidth(250)
        self.product_input.setStyleSheet(theme.sales_compact_input_style())
        product_layout.addWidget(self.product_input)
        layout.addLayout(product_layout)
        
        # Stock display (read-only)
        stock_layout = QHBoxLayout()
        stock_layout.setSpacing(2)
        stock_label = QLabel("Stock")
        stock_label.setStyleSheet(theme.sales_micro_label_style())
        stock_label.setFixedWidth(35)
        stock_layout.addWidget(stock_label)
        
        self.stock_display = QLineEdit()
        self.stock_display.setReadOnly(True)
        self.stock_display.setFixedWidth(80)
        self.stock_display.setStyleSheet(theme.entry_footer_input_readonly_style())
        stock_layout.addWidget(self.stock_display)
        layout.addLayout(stock_layout)
        
        # Rate display (read-only)
        rate_layout = QHBoxLayout()
        rate_layout.setSpacing(2)
        rate_label = QLabel("Rate")
        rate_label.setStyleSheet(theme.sales_micro_label_style())
        rate_label.setFixedWidth(30)
        rate_layout.addWidget(rate_label)
        
        self.rate_display = QLineEdit()
        self.rate_display.setReadOnly(True)
        self.rate_display.setFixedWidth(70)
        self.rate_display.setStyleSheet(theme.entry_footer_input_readonly_style())
        rate_layout.addWidget(self.rate_display)
        layout.addLayout(rate_layout)
        
        layout.addStretch()
        
        return frame
    
    def build_table_section(self):
        """Build table section with items table (matches Ledger/Sales Entry style)."""
        layout = QVBoxLayout()
        layout.setSpacing(4)
        
        # Items table
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(9)
        self.items_table.setHorizontalHeaderLabels([
            "Sl No", "Barcode", "Product", "System Qty", "Physical Qty",
            "Difference Qty", "Rate", "Value", "Reason"
        ])
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setSelectionBehavior(QTableWidget.SelectItems)
        self.items_table.setSelectionMode(QTableWidget.SingleSelection)
        self.items_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed)
        self.items_table.setAlternatingRowColors(False)
        self.items_table.setStyleSheet(theme.editable_table_style())
        self.items_table.verticalHeader().setDefaultSectionSize(42)
        self.items_table.verticalHeader().setMinimumSectionSize(40)
        self.items_table.horizontalHeader().setFixedHeight(30)
        
        # Set column widths
        self.items_table.setColumnWidth(0, 50)   # Sl No
        self.items_table.setColumnWidth(1, 110)  # Barcode
        self.items_table.setColumnWidth(2, 200)  # Product
        self.items_table.setColumnWidth(3, 90)   # System Qty
        self.items_table.setColumnWidth(4, 90)   # Physical Qty
        self.items_table.setColumnWidth(5, 100)  # Difference Qty
        self.items_table.setColumnWidth(6, 70)   # Rate
        self.items_table.setColumnWidth(7, 80)   # Value
        
        layout.addWidget(self.items_table)
        
        return layout
    
    def build_footer_section(self):
        """Build footer section with totals and action buttons."""
        layout = QHBoxLayout()
        layout.setSpacing(12)
        
        # Totals section
        totals_layout = QVBoxLayout()
        totals_layout.setSpacing(2)
        
        # Total Increase
        increase_layout = QHBoxLayout()
        increase_label = QLabel("Total Increase:")
        increase_label.setStyleSheet(theme.entry_value_style("accent_highlight"))
        self.total_increase_label = QLabel("0.00")
        self.total_increase_label.setStyleSheet(theme.entry_value_style("accent_highlight"))
        increase_layout.addWidget(increase_label)
        increase_layout.addWidget(self.total_increase_label)
        increase_layout.addStretch()
        totals_layout.addLayout(increase_layout)
        
        # Total Decrease
        decrease_layout = QHBoxLayout()
        decrease_label = QLabel("Total Decrease:")
        decrease_label.setStyleSheet(theme.entry_value_style("button_danger"))
        self.total_decrease_label = QLabel("0.00")
        self.total_decrease_label.setStyleSheet(theme.entry_value_style("button_danger"))
        decrease_layout.addWidget(decrease_label)
        decrease_layout.addWidget(self.total_decrease_label)
        decrease_layout.addStretch()
        totals_layout.addLayout(decrease_layout)
        
        # Net Adjustment
        net_layout = QHBoxLayout()
        net_label = QLabel("Net Adjustment:")
        net_label.setStyleSheet(theme.sales_micro_label_style())
        self.net_adjustment_label = QLabel("0.00")
        self.net_adjustment_label.setStyleSheet(theme.entry_value_style("accent_label"))
        net_layout.addWidget(net_label)
        net_layout.addWidget(self.net_adjustment_label)
        net_layout.addStretch()
        totals_layout.addLayout(net_layout)
        
        layout.addLayout(totals_layout)
        
        layout.addStretch()

        self.qty_only_checkbox = create_checkbox(
            "Adjust Qty Only (No Value Effect)",
            variant="status",
        )
        layout.addWidget(self.qty_only_checkbox)
        
        # Action buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)
        
        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet(theme.entry_save_button_style())
        
        self.remove_item_btn = QPushButton("Remove Item")
        self.remove_item_btn.setStyleSheet(theme.sales_danger_button_style())
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setStyleSheet(theme.sales_compact_button_style())
        
        buttons_layout.addWidget(self.save_btn)
        buttons_layout.addWidget(self.remove_item_btn)
        buttons_layout.addWidget(self.clear_btn)
        layout.addLayout(buttons_layout)
        
        return layout