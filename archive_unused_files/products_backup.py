# Full products.py (corrected)

import random
import time
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor, QColor

from config import COLORS, active_company_manager
from db import Database


class ProductsWidget(QWidget):

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.current_product_id = None
        self.products_data = []  # Initialize products data storage
        self.setup_ui()
        self.load_products()
        self.clear_form()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Products / Services")
        title.setStyleSheet("font-size:24px; font-weight:bold; color:#60a5fa;")
        layout.addWidget(title)

        # Create navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 10, 0, 10)
        
        self.entry_btn = QPushButton("Product Entry")
        self.entry_btn.setStyleSheet("""
            QPushButton {
                background-color: #60a5fa;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
        """)
        self.entry_btn.clicked.connect(self.show_entry_page)
        
        self.list_btn = QPushButton("Product List")
        self.list_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        self.list_btn.clicked.connect(self.show_list_page)
        
        nav_layout.addWidget(self.entry_btn)
        nav_layout.addWidget(self.list_btn)
        nav_layout.addStretch()
        
        layout.addLayout(nav_layout)

        # Create stacked widget for internal pages
        self.stack_widget = QStackedWidget()
        
        # Create pages
        self.entry_page = self.create_entry_page()
        self.list_page = self.create_list_page()
        
        self.stack_widget.addWidget(self.entry_page)
        self.stack_widget.addWidget(self.list_page)
        
        layout.addWidget(self.stack_widget)

    def show_entry_page(self, clear_form=True):
        """Switch to Product Entry page."""
        self.stack_widget.setCurrentWidget(self.entry_page)
        self.entry_btn.setStyleSheet("""
            QPushButton {
                background-color: #60a5fa;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
        """)
        self.list_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        
        # Clear form when opening normally (not for editing)
        if clear_form:
            self.clear_form()

    def show_list_page(self):
        """Switch to Product List page."""
        self.stack_widget.setCurrentWidget(self.list_page)
        self.list_btn.setStyleSheet("""
            QPushButton {
                background-color: #60a5fa;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
        """)
        self.entry_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        # Refresh product list when switching to list page
        self.load_products()

    def label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("""
            QLabel {
                color: #fbbf24;
                font-size: 16px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 8px 0px;
                margin: 0px;
                min-height: 24px;
                height: 24px;
            }
        """)
        return lbl

    def create_entry_page(self):
        # Create container without scroll area for compact fit
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 5, 10, 10)
        layout.setSpacing(3)

        # Create compact input field style with reduced width
        compact_input_style = """
            QLineEdit {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-height: 16px;
                height: 16px;
                max-width: 110px;
            }
            QLineEdit:focus {
                border-color: #60a5fa;
                outline: none;
            }
        """

        # Create wide input style for fields that need more space
        wide_input_style = """
            QLineEdit {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                border-radius: 3px;
                padding: 5px 8px;
                font-size: 12px;
                min-height: 18px;
                height: 18px;
                max-width: 210px;
                text-align: left;
            }
            QLineEdit:focus {
                border-color: #60a5fa;
                outline: none;
            }
        """

        # Create extra wide input style for Product Name and Description
        extra_wide_input_style = """
            QLineEdit {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-height: 16px;
                height: 16px;
                max-width: 380px;
            }
            QLineEdit:focus {
                border-color: #60a5fa;
                outline: none;
            }
        """

        # Create compact label style
        compact_label_style = """
            QLabel {
                color: #fbbf24;
                font-size: 12px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 1px 0px;
                margin: 0px;
                min-height: 14px;
                height: 14px;
            }
        """

        # Top Section - Product Name (wide)
        name_label = QLabel("Product Name *")
        name_label.setStyleSheet(compact_label_style)
        name_label.setFixedWidth(100)  # Consistent label width
        self.name_input = QLineEdit()
        self.name_input.setStyleSheet(extra_wide_input_style)
        self.name_input.textChanged.connect(lambda text: self.on_text_changed(self.name_input, text))
        layout.addWidget(name_label)
        layout.addWidget(self.name_input)
        layout.addSpacing(3)

        # Barcode + Auto Barcode row
        barcode_row = QHBoxLayout()
        barcode_row.setSpacing(8)
        
        barcode_label = QLabel("Barcode")
        barcode_label.setStyleSheet(compact_label_style)
        barcode_label.setFixedWidth(50)  # Consistent label width
        self.barcode_input = QLineEdit()
        self.barcode_input.setStyleSheet(compact_input_style)
        
        self.auto_barcode = QCheckBox("Auto")
        self.auto_barcode.setStyleSheet("""
            QCheckBox {
                color: #f3f4f6;
                font-size: 12px;
                font-weight: 500;
                min-height: 16px;
                height: 16px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 2px solid #4b5563;
                border-radius: 2px;
                background-color: #374151;
            }
            QCheckBox::indicator:checked {
                background-color: #60a5fa;
                border-color: #60a5fa;
            }
        """)
        self.auto_barcode.setChecked(True)
        self.auto_barcode.toggled.connect(self.auto_barcode_toggle)
        
        barcode_row.addWidget(barcode_label)
        barcode_row.addWidget(self.barcode_input)
        barcode_row.addWidget(self.auto_barcode)
        barcode_row.addStretch()
        layout.addLayout(barcode_row)
        layout.addSpacing(3)

        # HSN row
        hsn_row = QHBoxLayout()
        hsn_row.setSpacing(8)
        
        hsn_label = QLabel("HSN")
        hsn_label.setStyleSheet(compact_label_style)
        hsn_label.setFixedWidth(50)  # Consistent label width
        self.hsn_input = QLineEdit()
        self.hsn_input.setStyleSheet(compact_input_style)
        self.hsn_input.textChanged.connect(lambda text: self.on_text_changed('hsn', text))
        
        hsn_row.addWidget(hsn_label)
        hsn_row.addWidget(self.hsn_input)
        hsn_row.addStretch()
        layout.addLayout(hsn_row)
        layout.addSpacing(3)

        # Color + Size row
        color_size_row = QHBoxLayout()
        color_size_row.setSpacing(8)
        
        color_label = QLabel("Color")
        color_label.setStyleSheet(compact_label_style)
        color_label.setFixedWidth(50)  # Consistent label width
        self.color_input = QLineEdit()
        self.color_input.setStyleSheet(compact_input_style)
        self.color_input.textChanged.connect(lambda text: self.on_text_changed(self.color_input, text))
        
        size_label = QLabel("Size")
        size_label.setStyleSheet(compact_label_style)
        size_label.setFixedWidth(50)  # Consistent label width
        self.size_input = QLineEdit()
        self.size_input.setStyleSheet(compact_input_style)
        self.size_input.textChanged.connect(lambda text: self.on_text_changed(self.size_input, text))
        
        color_size_row.addWidget(color_label)
        color_size_row.addWidget(self.color_input)
        color_size_row.addWidget(size_label)
        color_size_row.addWidget(self.size_input)
        color_size_row.addStretch()
        layout.addLayout(color_size_row)
        layout.addSpacing(3)

        # Unit + Category row
        unit_category_row = QHBoxLayout()
        unit_category_row.setSpacing(8)
        
        unit_label = QLabel("Unit")
        unit_label.setStyleSheet(compact_label_style)
        unit_label.setFixedWidth(50)  # Consistent label width
        self.unit = QComboBox()
        self.unit.addItems(["pcs", "kg", "ltr"])
        self.unit.setStyleSheet("""
            QComboBox {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-height: 16px;
                height: 16px;
                max-width: 80px;
            }
            QComboBox:focus {
                border-color: #60a5fa;
                outline: none;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #f3f4f6;
            }
        """)
        
        category_label = QLabel("Category")
        category_label.setStyleSheet(compact_label_style)
        category_label.setFixedWidth(60)  # Consistent label width
        self.category = QLineEdit()
        self.category.setStyleSheet(wide_input_style)
        self.category.textChanged.connect(lambda text: self.on_text_changed(self.category, text))
        
        unit_category_row.addWidget(unit_label)
        unit_category_row.addWidget(self.unit)

        unit_category_row.addSpacing(10)

        unit_category_row.addWidget(category_label)
        unit_category_row.addSpacing(5)
        unit_category_row.addWidget(self.category)
        unit_category_row.addStretch()
        layout.addLayout(unit_category_row)
        layout.addSpacing(3)


        # Rates Section Header
        section_label = QLabel("Rates")
        section_label.setStyleSheet("""
            QLabel {
                color: #60a5fa;
                font-size: 13px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 2px 0px;
                margin: 0px;
            }
        """)
        layout.addWidget(section_label)
        layout.addSpacing(1)

        percent_label_style = """
            QLabel {
                color: #10b981;
                font-size: 11px;
                font-weight: 600;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
                min-width: 35px;
                max-width: 35px;
            }
        """

        # Purchase Rate + Sale Price row
        rates_row1 = QHBoxLayout()
        rates_row1.setSpacing(8)
        rates_row1.setContentsMargins(0, 0, 0, 0)

        purchase_rate_label = QLabel("Purchase Rate")
        purchase_rate_label.setStyleSheet(compact_label_style)
        purchase_rate_label.setFixedWidth(100)

        self.purchase_rate = QLineEdit()
        self.purchase_rate.setStyleSheet(compact_input_style)
        self.purchase_rate.setFixedWidth(120)
        self.purchase_rate.textChanged.connect(lambda: self.update_percentage_labels())

        # invisible spacer to keep vertical alignment with wholesale % label row
        purchase_rate_percent_spacer = QLabel("")
        purchase_rate_percent_spacer.setFixedWidth(35)
        purchase_rate_percent_spacer.setStyleSheet("background: transparent; border: none;")

        sale_price_label = QLabel("Sale Price")
        sale_price_label.setStyleSheet(compact_label_style)
        sale_price_label.setFixedWidth(70)

        self.sale_price = QLineEdit()
        self.sale_price.setStyleSheet(compact_input_style)
        self.sale_price.setFixedWidth(120)
        self.sale_price.textChanged.connect(lambda: self.update_percentage_labels())

        self.sale_price_percent = QLabel("")
        self.sale_price_percent.setStyleSheet(percent_label_style)
        self.sale_price_percent.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        rates_row1.addWidget(purchase_rate_label)
        rates_row1.addWidget(self.purchase_rate)
        rates_row1.addWidget(purchase_rate_percent_spacer)
        rates_row1.addWidget(sale_price_label)
        rates_row1.addWidget(self.sale_price)
        rates_row1.addWidget(self.sale_price_percent)
        rates_row1.addStretch()
        layout.addLayout(rates_row1)

        # same gap method as CGST / IGST rows
        layout.addSpacing(3)

        # Wholesale Rate + MRP row
        rates_row2 = QHBoxLayout()
        rates_row2.setSpacing(8)
        rates_row2.setContentsMargins(0, 0, 0, 0)

        wholesale_rate_label = QLabel("Wholesale Rate")
        wholesale_rate_label.setStyleSheet(compact_label_style)
        wholesale_rate_label.setFixedWidth(100)

        self.wholesale_rate = QLineEdit()
        self.wholesale_rate.setStyleSheet(compact_input_style)
        self.wholesale_rate.setFixedWidth(120)
        self.wholesale_rate.textChanged.connect(lambda: self.update_percentage_labels())

        self.wholesale_rate_percent = QLabel("")
        self.wholesale_rate_percent.setStyleSheet(percent_label_style)
        self.wholesale_rate_percent.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        mrp_label = QLabel("MRP")
        mrp_label.setStyleSheet(compact_label_style)
        mrp_label.setFixedWidth(70)

        self.mrp = QLineEdit()
        self.mrp.setStyleSheet(compact_input_style)
        self.mrp.setFixedWidth(120)
        self.mrp.textChanged.connect(lambda: self.update_percentage_labels())

        self.mrp_percent = QLabel("")
        self.mrp_percent.setStyleSheet(percent_label_style)
        self.mrp_percent.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        rates_row2.addWidget(wholesale_rate_label)
        rates_row2.addWidget(self.wholesale_rate)
        rates_row2.addWidget(self.wholesale_rate_percent)
        rates_row2.addWidget(mrp_label)
        rates_row2.addWidget(self.mrp)
        rates_row2.addWidget(self.mrp_percent)
        rates_row2.addStretch()
        layout.addLayout(rates_row2)
        layout.addSpacing(3)
        # Taxes Section Header
        taxes_section_label = QLabel("Taxes")
        taxes_section_label.setStyleSheet("""
            QLabel {
                color: #60a5fa;
                font-size: 13px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 2px 0px;
                margin: 0px;
            }
        """)
        layout.addWidget(taxes_section_label)
        layout.addSpacing(1)

        # CGST + SGST row
        taxes_row1 = QHBoxLayout()
        taxes_row1.setSpacing(8)
        
        cgst_label = QLabel("CGST")
        cgst_label.setStyleSheet(compact_label_style)
        cgst_label.setFixedWidth(50)  # Consistent label width
        self.cgst = QLineEdit()
        self.cgst.setStyleSheet(compact_input_style)
        
        sgst_label = QLabel("SGST")
        sgst_label.setStyleSheet(compact_label_style)
        sgst_label.setFixedWidth(50)  # Consistent label width
        self.sgst = QLineEdit()
        self.sgst.setStyleSheet(compact_input_style)
        
        taxes_row1.addWidget(cgst_label)
        taxes_row1.addWidget(self.cgst)
        taxes_row1.addWidget(sgst_label)
        taxes_row1.addWidget(self.sgst)
        taxes_row1.addStretch()
        layout.addLayout(taxes_row1)
        layout.addSpacing(3)

        # IGST + CESS row
        taxes_row2 = QHBoxLayout()
        taxes_row2.setSpacing(8)
        
        igst_label = QLabel("IGST")
        igst_label.setStyleSheet(compact_label_style)
        igst_label.setFixedWidth(50)  # Consistent label width
        self.igst = QLineEdit()
        self.igst.setStyleSheet(compact_input_style)
        
        cess_label = QLabel("CESS")
        cess_label.setStyleSheet(compact_label_style)
        cess_label.setFixedWidth(50)  # Consistent label width
        self.cess = QLineEdit()
        self.cess.setStyleSheet(compact_input_style)
        
        taxes_row2.addWidget(igst_label)
        taxes_row2.addWidget(self.igst)
        taxes_row2.addWidget(cess_label)
        taxes_row2.addWidget(self.cess)
        taxes_row2.addStretch()
        layout.addLayout(taxes_row2)
        layout.addSpacing(3)

        # Stock Section Header
        stock_section_label = QLabel("Stock")
        stock_section_label.setStyleSheet("""
            QLabel {
                color: #60a5fa;
                font-size: 13px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 2px 0px;
                margin: 0px;
            }
        """)
        layout.addWidget(stock_section_label)
        layout.addSpacing(1)

        # Reorder Level + Quantity row
        stock_row = QHBoxLayout()
        stock_row.setSpacing(8)
        
        reorder_level_label = QLabel("Reorder Level")
        reorder_level_label.setStyleSheet(compact_label_style)
        reorder_level_label.setFixedWidth(80)  # Consistent label width
        self.reorder_level = QLineEdit()
        self.reorder_level.setStyleSheet(compact_input_style)
        
        quantity_label = QLabel("Quantity")
        quantity_label.setStyleSheet(compact_label_style)
        quantity_label.setFixedWidth(80)  # Consistent label width
        self.qty = QLineEdit()
        self.qty.setStyleSheet(compact_input_style)
        
        stock_row.addWidget(reorder_level_label)
        stock_row.addWidget(self.reorder_level)
        stock_row.addWidget(quantity_label)
        stock_row.addWidget(self.qty)
        stock_row.addStretch()
        layout.addLayout(stock_row)
        layout.addSpacing(3)

        # Description row (single-line)
        description_label = QLabel("Description")
        description_label.setStyleSheet(compact_label_style)
        description_label.setFixedWidth(80)  # Consistent label width
        self.description = QLineEdit()
        self.description.setStyleSheet(extra_wide_input_style)
        self.description.textChanged.connect(lambda text: self.on_text_changed(self.description, text))
        layout.addWidget(description_label)
        layout.addWidget(self.description)
        layout.addSpacing(3)

        # Action buttons row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(5)
        
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("save_btn")
        self.save_btn.clicked.connect(self.save)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
                min-height: 16px;
                height: 16px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #6b7280;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
                min-height: 16px;
                height: 16px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
            QPushButton:pressed {
                background-color: #374151;
            }
        """)
        clear_btn.clicked.connect(self.clear_form)
        
        actions_row.addWidget(self.save_btn)
        actions_row.addWidget(clear_btn)
        actions_row.addStretch()
        
        layout.addLayout(actions_row)
        layout.addStretch()

        return container


    def create_list_page(self):
        # Create container for the list page
        container = QFrame()
        container.setObjectName("productListOuterFrame")
        container.setStyleSheet("""
            QFrame#productListOuterFrame {
                background-color: #1f2937;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        list_title = QLabel("Product List")
        list_title.setStyleSheet("""
            QLabel {
                color: #fbbf24;
                font-size: 18px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        layout.addWidget(list_title)

        # Search row
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 10)

        search_label = QLabel("Search:")
        search_label.setStyleSheet("""
            QLabel {
                color: #fbbf24;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
                border: none;
                margin-right: 10px;
            }
        """)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by product name or barcode...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
                min-width: 300px;
            }
            QLineEdit:focus {
                border-color: #60a5fa;
                outline: none;
            }
        """)
        self.search_input.textChanged.connect(self.filter_products)

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        # Professional table container using real Qt header
        table_container = QFrame()
        table_container.setObjectName("productListTableContainer")
        table_container.setStyleSheet("""
            QFrame#productListTableContainer {
                background-color: #1f2937;
                border: 1px solid #4b5563;
                border-radius: 6px;
            }
        """)

        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "SL No",
            "Product Name",
            "Barcode",
            "Purchase Rate",
            "Sale Rate",
            "Wholesale Rate",
            "Quantity"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.table.itemDoubleClicked.connect(self.on_table_double_click)
        self.table.setCornerButtonEnabled(False)
        self.table.verticalHeader().setVisible(False)

        # Make table fully flat
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setFrameShadow(QFrame.Plain)
        self.table.setLineWidth(0)
        self.table.setMidLineWidth(0)
        self.table.setContentsMargins(0, 0, 0, 0)
        self.table.setViewportMargins(0, 0, 0, 0)

        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1f2937;
                color: #f3f4f6;
                border: none;
                gridline-color: #4b5563;
                selection-background-color: #60a5fa;
                selection-color: white;
                font-size: 14px;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #4b5563;
            }
            QTableWidget::item:selected {
                background-color: #60a5fa;
                color: white;
            }
            QHeaderView::section {
                background-color: #374151;
                color: #fbbf24;
                font-weight: bold;
                font-size: 14px;
                border: none;
                border-right: 1px solid #4b5563;
                border-bottom: 1px solid #4b5563;
                padding-left: 8px;
                padding-right: 8px;
            }
            QTableCornerButton::section {
                background-color: #374151;
                border: none;
            }
        """)

        header = self.table.horizontalHeader()
        header.setVisible(True)
        header.setFixedHeight(36)
        header.setMinimumHeight(36)
        header.setDefaultSectionSize(36)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setMinimumSectionSize(60)

        # Set fixed column widths as specified
        self.table.setColumnWidth(0, 90)   # SL No
        self.table.setColumnWidth(1, 330)  # Product Name
        self.table.setColumnWidth(2, 130)  # Barcode
        self.table.setColumnWidth(3, 170)  # Purchase Rate
        self.table.setColumnWidth(4, 160)  # Sale Rate
        self.table.setColumnWidth(5, 180)  # Wholesale Rate
        self.table.setColumnWidth(6, 130)  # Quantity
        table_layout.addWidget(self.table)
        layout.addWidget(table_container)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 0)

        edit_btn = QPushButton("Edit Selected")
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #60a5fa;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
        """)
        edit_btn.clicked.connect(self.edit_selected_product)

        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        delete_btn.clicked.connect(self.delete_selected_product)

        button_layout.addWidget(edit_btn)
        button_layout.addWidget(delete_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        return container

    def auto_barcode_toggle(self, checked):
        if checked:
            # Generate sequential barcode based on existing products
            self.generate_sequential_barcode()
            self.barcode_input.setEnabled(False)
            self.barcode_input.setReadOnly(True)
        else:
            self.barcode_input.setEnabled(True)
            self.barcode_input.setReadOnly(False)
            self.barcode_input.clear()

    def generate_sequential_barcode(self):
        """Generate sequential barcode based on existing products for active company."""
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                # No active company, use a simple counter
                current_text = self.barcode_input.text()
                if current_text and current_text.isdigit():
                    next_barcode = str(int(current_text) + 1)
                else:
                    next_barcode = "1"
                self.barcode_input.setText(next_barcode)
                return
            
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(CAST(barcode AS INTEGER)) as max_barcode
                FROM products 
                WHERE company_id = ? AND barcode IS NOT NULL AND barcode != ''
            """, (active_company['id'],))
            
            result = cursor.fetchone()
            conn.close()
            
            if result and result['max_barcode']:
                next_barcode = str(int(result['max_barcode']) + 1)
            else:
                next_barcode = "1"
            
            self.barcode_input.setText(next_barcode)
            
        except Exception as e:
            # Fallback to simple sequential number
            current_text = self.barcode_input.text()
            if current_text and current_text.isdigit():
                next_barcode = str(int(current_text) + 1)
            else:
                next_barcode = str(random.randint(100000, 999999))
            self.barcode_input.setText(next_barcode)

    def get_next_unique_barcode(self, exclude_current_id=None):
        """Get the next unique barcode for the active company."""
        conn = None
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return "1"
            
            conn = self.db.connect()
            cursor = conn.cursor()
            
            # Get all existing barcodes for this company, excluding current product if editing
            if exclude_current_id:
                cursor.execute("""
                    SELECT barcode FROM products 
                    WHERE company_id = ? AND id != ? AND barcode IS NOT NULL AND barcode != ''
                """, (active_company['id'], exclude_current_id))
            else:
                cursor.execute("""
                    SELECT barcode FROM products 
                    WHERE company_id = ? AND barcode IS NOT NULL AND barcode != ''
                """, (active_company['id'],))
            
            existing_barcodes = []
            for row in cursor.fetchall():
                if row['barcode']:
                    try:
                        existing_barcodes.append(int(row['barcode']))
                    except (ValueError, TypeError):
                        pass
            
            # Find the next available sequential number
            next_barcode = 1
            while next_barcode in existing_barcodes:
                next_barcode += 1
            
            return str(next_barcode)
            
        except Exception as e:
            # Fallback to timestamp-based unique number
            return str(int(time.time() * 1000) % 1000000)
        finally:
            if conn:
                conn.close()

    def capitalize_first_letter(self, text):
        """Capitalize first letter of text without disturbing cursor position."""
        if not text:
            return text
        
        # Only capitalize if first character is a letter and it's lowercase
        if len(text) > 0 and text[0].isalpha() and text[0].islower():
            return text[0].upper() + text[1:]
        return text

    def apply_capitalization_to_field(self, field, text):
        """Apply capitalization to field text."""
        if text:
            capitalized_text = self.capitalize_first_letter(text)
            if capitalized_text != text:
                # Get current cursor position
                cursor_pos = field.cursorPosition()
                # Update text without disturbing cursor
                field.blockSignals(True)
                field.setText(capitalized_text)
                field.setCursorPosition(cursor_pos)
                field.blockSignals(False)

    def initialize_field_capitalization(self):
        """Apply capitalization to all relevant fields with existing text."""
        fields_to_capitalize = [
            (self.name_input, 'name'),
            (self.hsn_input, 'hsn'),
            (self.color_input, 'color'),
            (self.size_input, 'size'),
            (self.category, 'category'),
            (self.description, 'description')
        ]
        
        for field, field_name in fields_to_capitalize:
            current_text = field.text()
            if current_text:
                capitalized = self.capitalize_first_letter(current_text)
                if capitalized != current_text:
                    field.setText(capitalized)

    def safe_calculate_expression(self, expression):
        """Safely calculate simple arithmetic expression."""
        try:
            # Remove spaces and validate expression
            expr = expression.replace(" ", "")
            
            # Only allow digits, +, -, *, /, and decimal point
            if not all(c in "0123456789+-*/." for c in expr):
                return None
            
            # Check for valid number/operator pattern
            if not expr or expr[0] in "+-*/" or expr[-1] in "+-*/":
                return None
            
            # Check for consecutive operators
            for i in range(len(expr) - 1):
                if expr[i] in "+-*/" and expr[i + 1] in "+-*/":
                    return None
            
            # Simple evaluation for basic arithmetic
            # Split by operators and calculate step by step
            result = self._evaluate_simple_expression(expr)
            return result
            
        except Exception:
            return None
    
    def _evaluate_simple_expression(self, expr):
        """Evaluate simple arithmetic expression step by step."""
        try:
            # Parse expression into numbers and operators
            parts = []
            current = ""
            i = 0
            
            while i < len(expr):
                if expr[i] in "+-*/":
                    # Add current number to parts
                    if current:
                        parts.append(current)
                    # Add operator
                    parts.append(expr[i])
                    current = ""
                    i += 1
                else:
                    current += expr[i]
                    i += 1
            
            if current:
                parts.append(current)
            
            # First pass: handle * and / (higher precedence)
            i = 0
            while i < len(parts):
                if parts[i] == "*":
                    # Calculate multiplication
                    left = float(parts[i - 1])
                    right = float(parts[i + 1])
                    result = left * right
                    # Replace three elements with result
                    parts[i - 1:i + 2] = [str(result)]
                    i -= 1
                elif parts[i] == "/":
                    # Calculate division (check for division by zero)
                    left = float(parts[i - 1])
                    right = float(parts[i + 1])
                    if right == 0:
                        return None
                    result = left / right
                    # Replace three elements with result
                    parts[i - 1:i + 2] = [str(result)]
                    i -= 1
                i += 1
            
            # Second pass: handle + and - (lower precedence)
            result = float(parts[0])
            i = 1
            while i < len(parts):
                if parts[i] == "+":
                    result += float(parts[i + 1])
                elif parts[i] == "-":
                    result -= float(parts[i + 1])
                i += 2
            
            return result
            
        except Exception:
            return None
    
    def format_calculation_result(self, result):
        """Format calculation result for display."""
        if result is None:
            return None
        
        # If result is whole number, show as integer
        if result == int(result):
            return str(int(result))
        else:
            # Show with appropriate decimal places
            return str(round(result, 2)).rstrip('0').rstrip('.')
    
    def handle_calculator_field(self, field, next_field=None):
        """Handle calculator behavior for a field."""
        text = field.text().strip()
        
        # Handle empty field
        if not text:
            field.setText("0")
            return True
        
        # Try to calculate if it's an expression
        result = self.safe_calculate_expression(text)
        
        if result is not None:
            # Format and set result
            formatted_result = self.format_calculation_result(result)
            field.setText(formatted_result)
            return True
        elif text.replace(".", "").replace("-", "").isdigit():
            # It's a plain number, keep it
            return True
        else:
            # Invalid expression, keep focus
            return False

    def on_text_changed(self, widget, text):
        """Handle text change to capitalize first letter for relevant fields."""
        if widget and hasattr(widget, 'cursorPosition'):
            cursor_pos = widget.cursorPosition()
            # Capitalize first letter
            capitalized_text = self.capitalize_first_letter(text)
            # Update text without disturbing cursor
            if capitalized_text != text:
                widget.blockSignals(True)
                widget.setText(capitalized_text)
                widget.setCursorPosition(cursor_pos)
                widget.blockSignals(False)

    def clear_form(self):
        self.name_input.clear()
        self.hsn_input.clear()
        self.color_input.clear()
        self.size_input.clear()
        self.category.clear()
        self.purchase_rate.clear()
        self.sale_price.clear()
        self.wholesale_rate.clear()
        self.mrp.clear()
        self.cgst.clear()
        self.sgst.clear()
        self.igst.clear()
        self.cess.clear()
        self.reorder_level.clear()
        self.description.clear()
        self.qty.clear()
        
        # Clear percentage labels
        self.sale_price_percent.setText("")
        self.wholesale_rate_percent.setText("")
        self.mrp_percent.setText("")
        
        # Initialize field capitalization
        self.initialize_field_capitalization()
        
        # Reset barcode to auto mode and generate new sequential barcode
        self.auto_barcode.setChecked(True)
        self.barcode_input.setEnabled(False)
        self.barcode_input.setReadOnly(True)
        self.generate_sequential_barcode()
        
        self.current_product_id = None

    def save(self):
        # Check if company is active
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, "No Active Company", "Please open a company first.")
            return
        
        # Validate required fields
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Product/Service Name is required.")
            self.name_input.setFocus()
            return

        conn = None
        try:
            auto_barcode = self.auto_barcode.isChecked()

            if auto_barcode:
                # Generate unique barcode for new product
                if not self.current_product_id:
                    barcode = self.get_next_unique_barcode()
                else:
                    barcode = self.barcode_input.text().strip() or self.get_next_unique_barcode(self.current_product_id)
            else:
                # Manual barcode entry - check uniqueness
                barcode = self.barcode_input.text().strip()
                if not barcode:
                    QMessageBox.warning(self, "Validation Error", "Please enter a barcode or enable Auto Barcode.")
                    self.barcode_input.setFocus()
                    return

            hsn = self.hsn_input.text().strip()
            color = self.color_input.text().strip()
            size = self.size_input.text().strip()
            unit = self.unit.currentText().strip()
            category = self.category.text().strip()
            purchase_rate = float(self.purchase_rate.text() or "0")
            sale_price = float(self.sale_price.text() or "0")
            wholesale_rate = float(self.wholesale_rate.text() or "0")
            mrp = float(self.mrp.text() or "0")
            cgst = float(self.cgst.text() or "0")
            sgst = float(self.sgst.text() or "0")
            igst = float(self.igst.text() or "0")
            cess = float(self.cess.text() or "0")
            reorder_level = float(self.reorder_level.text() or "0")
            description = self.description.text().strip()
            quantity = float(self.qty.text() or "0")
            
            # Stock validation: quantity must never be negative
            quantity = max(0, quantity)

            conn = self.db.connect()
            cursor = conn.cursor()

            if not auto_barcode:
                if self.current_product_id:
                    cursor.execute(
                        "SELECT id FROM products WHERE barcode = ? AND company_id = ? AND id != ?",
                        (barcode, active_company['id'], self.current_product_id)
                    )
                else:
                    cursor.execute(
                        "SELECT id FROM products WHERE barcode = ? AND company_id = ?",
                        (barcode, active_company['id'])
                    )

                if cursor.fetchone():
                    QMessageBox.warning(
                        self,
                        "Duplicate Barcode",
                        f"Barcode '{barcode}' already exists for another product in this company."
                    )
                    return

            if self.current_product_id:
                cursor.execute(
                    '''
                    UPDATE products
                    SET name = ?, barcode = ?, hsn = ?, color = ?, size = ?, unit = ?, category = ?,
                        purchase_rate = ?, sale_price = ?, wholesale_rate = ?, mrp = ?,
                        cgst = ?, sgst = ?, igst = ?, cess = ?, reorder_level = ?,
                        description = ?, quantity = ?, auto_barcode = ?
                    WHERE id = ? AND company_id = ?
                    ''',
                    (
                        name, barcode, hsn, color, size, unit, category,
                        purchase_rate, sale_price, wholesale_rate, mrp,
                        cgst, sgst, igst, cess, reorder_level,
                        description, quantity, 1 if auto_barcode else 0,
                        self.current_product_id, active_company['id']
                    )
                )
            else:
                cursor.execute(
                    '''
                    INSERT INTO products (
                        company_id, name, barcode, hsn, color, size, unit, category,
                        purchase_rate, sale_price, wholesale_rate, mrp,
                        cgst, sgst, igst, cess, reorder_level,
                        description, quantity, auto_barcode
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        active_company['id'], name, barcode, hsn, color, size, unit, category,
                        purchase_rate, sale_price, wholesale_rate, mrp,
                        cgst, sgst, igst, cess, reorder_level,
                        description, quantity, 1 if auto_barcode else 0
                    )
                )

            conn.commit()
            QMessageBox.information(self, "Success", "Product/Service saved successfully.")
            self.clear_form()
            # Set focus to Product Name field after clear
            QTimer.singleShot(0, lambda: self.name_input.setFocus())
            # Stay on Product Entry page - do not auto-switch to Product List
            # Refresh product list in background
            self.load_products()
            # Reapply current search filter if any
            search_term = self.search_input.text().strip()
            if search_term:
                self.filter_products(search_term)

        except ValueError:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please enter valid numeric values for rates, prices, taxes, reorder level, and quantity."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save product: {str(e)}")
        finally:
            if conn:
                conn.close()


    def load_products(self):
        """Load all products from database into memory."""
        conn = None
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                self.products_data = []
                self.render_products([])
                return

            conn = self.db.connect()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, name, barcode, hsn, color, size, unit, category,
                       purchase_rate, sale_price, wholesale_rate, mrp,
                       cgst, sgst, igst, cess, reorder_level, quantity
                FROM products
                WHERE company_id = ?
                ORDER BY 
                    CASE 
                        WHEN barcode IS NULL OR barcode = '' THEN 1 
                        ELSE 0 
                    END,
                    CAST(barcode AS INTEGER)
            """, (active_company['id'],))

            self.products_data = cursor.fetchall()
            
            # Render all products initially
            self.render_products(self.products_data)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load products: {str(e)}")
            self.products_data = []
            self.render_products([])
        finally:
            if conn:
                conn.close()

    def render_products(self, products):
        """Render products in table without heading row."""
        # Table starts directly from product data rows
        self.table.setRowCount(len(products))

        for row, product in enumerate(products):
            sl_no_item = QTableWidgetItem(str(row + 1))
            sl_no_item.setData(Qt.UserRole, product['id'])
            self.table.setItem(row, 0, sl_no_item)

            name_item = QTableWidgetItem(product['name'])
            name_item.setData(Qt.UserRole, product['id'])
            self.table.setItem(row, 1, name_item)

            barcode_item = QTableWidgetItem(product['barcode'] or "")
            barcode_item.setData(Qt.UserRole, product['id'])
            self.table.setItem(row, 2, barcode_item)

            purchase_item = QTableWidgetItem(f"{float(product['purchase_rate']):.2f}")
            purchase_item.setData(Qt.UserRole, product['id'])
            self.table.setItem(row, 3, purchase_item)

            sale_item = QTableWidgetItem(f"{float(product['sale_price']):.2f}")
            sale_item.setData(Qt.UserRole, product['id'])
            self.table.setItem(row, 4, sale_item)

            wholesale_item = QTableWidgetItem(f"{float(product['wholesale_rate']):.2f}")
            wholesale_item.setData(Qt.UserRole, product['id'])
            self.table.setItem(row, 5, wholesale_item)

            quantity = max(0, float(product['quantity']))
            quantity_item = QTableWidgetItem(f"{quantity:.2f}")
            quantity_item.setData(Qt.UserRole, product['id'])
            self.table.setItem(row, 6, quantity_item)

    def filter_products(self, search_term):
        """Filter products in memory based on search term."""
        search_term = search_term.strip()
        
        if not search_term:
            # Show all products if search is empty
            self.render_products(self.products_data)
            return
        
        # Filter products in memory
        filtered_products = []
        for product in self.products_data:
            # Case insensitive search in name and barcode
            name_match = search_term.lower() in (product['name'] or "").lower()
            barcode_match = search_term.lower() in (product['barcode'] or "").lower()
            
            if name_match or barcode_match:
                filtered_products.append(product)
        
        # Render filtered products
        self.render_products(filtered_products)
    
    def on_table_selection_changed(self):
        """Handle table row selection change - normal selection for product rows."""
        # No heading row to handle, normal selection behavior
        pass

    def on_table_double_click(self, item):
        """Handle double-click on table row to edit product."""
        self.edit_selected_product()

    def edit_selected_product(self):
        """Edit the selected product by switching to entry page."""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a product to edit.")
            return

        # Get product ID from UserRole data of the first selected item
        product_id = selected_items[0].data(Qt.UserRole)
        if not product_id:
            QMessageBox.warning(self, "Error", "Unable to identify selected product.")
            return
        
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, barcode, hsn, color, size, unit, category,
                       purchase_rate, sale_price, wholesale_rate, mrp, 
                       cgst, sgst, igst, cess, reorder_level, 
                       description, quantity, auto_barcode
                FROM products 
                WHERE company_id = ? AND id = ?
            """, (active_company['id'], product_id))
            
            product = cursor.fetchone()
            conn.close()
            
            if product:
                self.load_product_to_form(product)
                self.show_entry_page(clear_form=False)  # Switch to entry page for editing
            else:
                QMessageBox.warning(self, "Error", "Product not found.")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load product: {str(e)}")

    def delete_selected_product(self):
        """Delete the selected product."""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a product to delete.")
            return

        # Get product ID and name from selected row
        product_id = selected_items[0].data(Qt.UserRole)
        selected_row = self.table.currentRow()
        product_name_item = self.table.item(selected_row, 1)
        product_name = product_name_item.text() if product_name_item else "selected product"
        
        if not product_id:
            QMessageBox.warning(self, "Error", "Unable to identify selected product.")
            return
        
        conn = None
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            
            # Confirm deletion
            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Are you sure you want to delete '{product_name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM products WHERE id = ? AND company_id = ?", 
                             (product_id, active_company['id']))
                conn.commit()
                
                QMessageBox.information(self, "Success", "Product deleted successfully.")
                # Refresh product list and reapply search filter
                self.load_products()
                search_term = self.search_input.text().strip()
                if search_term:
                    self.filter_products(search_term)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete product: {str(e)}")
        finally:
            if conn:
                conn.close()

    def load_product_to_form(self, product):
        """Load product data into form fields."""
        self.current_product_id = product['id']
        self.name_input.setText(product['name'])
        self.barcode_input.setText(product['barcode'] or "")
        self.hsn_input.setText(product['hsn'] or "")
        self.color_input.setText(product['color'] or "")
        self.size_input.setText(product['size'] or "")
        self.unit.setCurrentText(product['unit'] or "pcs")
        self.category.setText(product['category'] or "")
        self.purchase_rate.setText(str(product['purchase_rate']))
        self.sale_price.setText(str(product['sale_price']))
        self.wholesale_rate.setText(str(product['wholesale_rate']))
        self.mrp.setText(str(product['mrp']))
        self.cgst.setText(str(product['cgst']))
        self.sgst.setText(str(product['sgst']))
        self.igst.setText(str(product['igst']))
        self.cess.setText(str(product['cess']))
        self.reorder_level.setText(str(product['reorder_level']))
        self.description.setText(product['description'] or "")
        self.qty.setText(str(product['quantity']))
        auto_barcode = bool(product['auto_barcode'])
        self.auto_barcode.setChecked(auto_barcode)
        self.barcode_input.setEnabled(not auto_barcode)
        
        # Calculate and update percentage labels
        self.update_percentage_labels()

    def delete_current_product(self):
        """Delete the current product being edited."""
        if not self.current_product_id:
            QMessageBox.warning(self, "No Product", "No product selected for deletion.")
            return
        
        reply = QMessageBox.question(
            self, "Confirm Delete",
            "Are you sure you want to delete this product?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                active_company = active_company_manager.get_active_company()
                if not active_company:
                    return
                
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM products WHERE id = ? AND company_id = ?", 
                             (self.current_product_id, active_company['id']))
                conn.commit()
                conn.close()
                
                QMessageBox.information(self, "Success", "Product deleted successfully.")
                self.clear_form()
                # Refresh product list and reapply search filter
                self.load_products()
                search_term = self.search_input.text().strip()
                if search_term:
                    self.filter_products(search_term)
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete product: {str(e)}")

    def focus_and_force_select(self, widget):
        """Set focus and force select all text with proper timing."""
        widget.setFocus()
        QTimer.singleShot(0, lambda: widget.setSelection(0, len(widget.text())))
    
    def focus_and_select(self, widget):
        """Set focus and select all text with proper timing."""
        widget.setFocus()
        QTimer.singleShot(0, widget.selectAll)
    
    def apply_percentage(self, base_value, percentage_text):
        """Apply percentage to base value."""
        try:
            # Get base value (treat empty as 0)
            if base_value:
                base = float(base_value)
            else:
                base = 0.0
            
            # Parse percentage
            percentage = float(percentage_text)
            
            # Calculate result: base + (base * percentage / 100)
            result = base + (base * percentage / 100)
            
            return result
            
        except (ValueError, TypeError):
            return None
    
    def handle_percentage_field(self, field):
        """Handle percentage calculation for rate fields."""
        text = field.text().strip()
        if not text:
            return False
        
        # Get purchase rate as base
        base_text = self.purchase_rate.text().strip()
        if not base_text:
            base_text = "0"
        
        # Calculate percentage
        result = self.apply_percentage(base_text, text)
        
        if result is not None:
            formatted_result = self.format_calculation_result(result)
            field.setText(formatted_result)
            
            # Update percentage label
            if field == self.sale_price:
                self.sale_price_percent.setText(f"{text}%")
            elif field == self.wholesale_rate:
                self.wholesale_rate_percent.setText(f"{text}%")
            elif field == self.mrp:
                self.mrp_percent.setText(f"{text}%")
            
            return True
        else:
            return False
    
    def update_percentage_labels(self):
        """Update percentage labels based on current field values."""
        try:
            purchase_rate = float(self.purchase_rate.text() or "0")
            
            # Calculate and update sale price percentage
            sale_price = float(self.sale_price.text() or "0")
            if purchase_rate > 0:
                sale_percent = ((sale_price - purchase_rate) / purchase_rate) * 100
                self.sale_price_percent.setText(f"{sale_percent:.1f}%")
            else:
                self.sale_price_percent.setText("")
            
            # Calculate and update wholesale rate percentage
            wholesale_rate = float(self.wholesale_rate.text() or "0")
            if purchase_rate > 0:
                wholesale_percent = ((wholesale_rate - purchase_rate) / purchase_rate) * 100
                self.wholesale_rate_percent.setText(f"{wholesale_percent:.1f}%")
            else:
                self.wholesale_rate_percent.setText("")
            
            # Calculate and update MRP percentage
            mrp = float(self.mrp.text() or "0")
            if purchase_rate > 0:
                mrp_percent = ((mrp - purchase_rate) / purchase_rate) * 100
                self.mrp_percent.setText(f"{mrp_percent:.1f}%")
            else:
                self.mrp_percent.setText("")
                
        except (ValueError, TypeError):
            # Clear percentage labels if there's an error
            self.sale_price_percent.setText("")
            self.wholesale_rate_percent.setText("")
            self.mrp_percent.setText("")
    
    def keyPressEvent(self, event):
        """Handle key press events for Enter and Esc navigation."""
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # Get current focus widget
            focus_widget = self.focusWidget()
            
            # Define tab order for form fields (dynamic based on auto barcode state)
            field_order = [self.name_input]
            
            # Only include barcode in navigation if auto is unchecked
            if not self.auto_barcode.isChecked():
                field_order.append(self.barcode_input)
            
            field_order.extend([
                self.hsn_input,
                self.color_input,
                self.size_input,
                self.unit,
                self.category,
                self.purchase_rate,
                self.sale_price,
                self.wholesale_rate,
                self.mrp,
                self.cgst,
                self.sgst,
                self.igst,
                self.cess,
                self.reorder_level,
                self.description,
                self.qty
            ])
            
            # Check if current field is a calculator field
            calculator_fields = [self.purchase_rate, self.sale_price, self.wholesale_rate, self.mrp, self.qty]
            
            if focus_widget in calculator_fields:
                # Handle calculator behavior
                if self.handle_calculator_field(focus_widget):
                    # If calculation successful, move to next field
                    current_index = field_order.index(focus_widget)
                    if current_index < len(field_order) - 1:
                        next_field = field_order[current_index + 1]
                        self.focus_and_force_select(next_field)
                    else:
                        # If at last field, trigger save
                        self.save()
                # If calculation failed, keep focus in current field
            elif focus_widget in field_order:
                # Normal field navigation
                current_index = field_order.index(focus_widget)
                if current_index < len(field_order) - 1:
                    next_field = field_order[current_index + 1]
                    self.focus_and_force_select(next_field)
                else:
                    # If at last field or special case, trigger save
                    self.save()
            elif focus_widget == self.save_btn:
                # If Save button has focus, trigger save
                self.save()
        elif event.key() == Qt.Key_Down:
            # Handle percentage calculation for rate fields
            focus_widget = self.focusWidget()
            percentage_fields = [self.sale_price, self.wholesale_rate, self.mrp]
            
            if focus_widget in percentage_fields:
                if self.handle_percentage_field(focus_widget):
                    # After percentage calculation, stay in same field and select all
                    self.focus_and_force_select(focus_widget)
                # If percentage calculation failed, keep focus
                # Consume the event to prevent default Down Arrow navigation
                return
            else:
                super().keyPressEvent(event)
        elif event.key() == Qt.Key_Escape:
            # Get current focus widget
            focus_widget = self.focusWidget()
            
            # If Save button has focus, move back to Description
            if focus_widget == self.save_btn:
                self.focus_and_force_select(self.description)
                return
            
            # Define tab order for form fields (dynamic based on auto barcode state)
            field_order = [self.name_input]
            
            # Only include barcode in navigation if auto is unchecked
            if not self.auto_barcode.isChecked():
                field_order.append(self.barcode_input)
            
            field_order.extend([
                self.hsn_input,
                self.color_input,
                self.size_input,
                self.unit,
                self.category,
                self.purchase_rate,
                self.sale_price,
                self.wholesale_rate,
                self.mrp,
                self.cgst,
                self.sgst,
                self.igst,
                self.cess,
                self.reorder_level,
                self.description,
                self.qty
            ])
            
            # Find current field in order and move to previous
            if focus_widget in field_order:
                current_index = field_order.index(focus_widget)
                if current_index > 0:
                    prev_field = field_order[current_index - 1]
                    if isinstance(prev_field, QTextEdit):
                        prev_field.setFocus()
                        prev_field.moveCursor(QTextCursor.End)
                    else:
                        self.focus_and_force_select(prev_field)
        else:
            super().keyPressEvent(event)
