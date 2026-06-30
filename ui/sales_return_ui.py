"""
UI building methods for Sales Return widget.
Contains all UI layout building methods and style helpers.
Styled to match Purchase Entry visual standard.
"""

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QDoubleValidator, QTextCharFormat, QColor

from ui import theme
from ui.checkbox_style import create_checkbox
from ui.date_formats import configure_qdate_edit
from .theme import GST_STATE_CODES


class SalesReturnUIMixin:
    """Mixin class containing all UI building and styling methods for Sales Return."""

    def apply_calendar_style(self, date_edit):
        """Apply theme-aware calendar styling to a QDateEdit popup."""
        from ui.date_formats import configure_qdate_edit

        configure_qdate_edit(date_edit, calendar_popup=False)
        from PySide6.QtWidgets import QToolButton
        from PySide6.QtCore import Qt as _Qt

        calendar = date_edit.calendarWidget()
        if calendar is None:
            return

        calendar.setStyleSheet(theme.entry_calendar_style())

        prev_btn = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        if prev_btn:
            prev_btn.setArrowType(_Qt.NoArrow)
            prev_btn.setToolButtonStyle(_Qt.ToolButtonTextOnly)
            prev_btn.setText("<")
            prev_btn.setFixedSize(24, 24)
        next_btn = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        if next_btn:
            next_btn.setArrowType(_Qt.NoArrow)
            next_btn.setToolButtonStyle(_Qt.ToolButtonTextOnly)
            next_btn.setText(">")
            next_btn.setFixedSize(24, 24)

        theme.apply_calendar_day_formats(calendar)


    # ==================== ZONE A - PAGE HEADER STRIP ====================

    def build_page_header_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.header_strip_style())
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(0)

        title_label = QLabel("SALES RETURN")
        title_label.setStyleSheet(self.page_title_style())
        layout.addWidget(title_label)
        layout.addStretch()
        return frame

    # ==================== ZONE B - RETURN COMMAND STRIP ====================

    def build_return_command_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.invoice_command_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(2)
        layout.setContentsMargins(2, 2, 2, 2)

        # Series prefix retained for return-numbering logic but hidden from the
        # top bar (kept as an empty off-screen field so existing logic still works).
        self.series_input = QLineEdit()
        self.series_input.setVisible(False)

        # Return No with navigation buttons
        inv_layout = QHBoxLayout()
        inv_layout.setSpacing(1)
        inv_label = QLabel("Return No")
        inv_label.setStyleSheet(self.micro_label_style())
        self.return_no_input = QLineEdit()
        self.return_no_input.setStyleSheet(self.compact_input_style())
        self.return_no_input.setPlaceholderText("Auto")
        self.return_no_input.setFixedWidth(70)
        self.return_no_input.textEdited.connect(lambda t: self.return_no_input.setText(t.upper()) or self.return_no_input.setCursorPosition(len(t)))
        inv_layout.addWidget(inv_label)
        inv_layout.addWidget(self.return_no_input)

        nav_container = QWidget()
        nav_container.setFixedWidth(18)
        nav_v = QVBoxLayout(nav_container)
        nav_v.setSpacing(1)
        nav_v.setContentsMargins(0, 0, 0, 0)

        prev_btn = QPushButton("▲")
        prev_btn.setStyleSheet(self.nav_button_style())
        prev_btn.setFixedSize(18, 11)
        prev_btn.clicked.connect(self.next_return)
        nav_v.addWidget(prev_btn)

        next_btn = QPushButton("▼")
        next_btn.setStyleSheet(self.nav_button_style())
        next_btn.setFixedSize(18, 11)
        next_btn.clicked.connect(self.previous_return)
        nav_v.addWidget(next_btn)

        inv_layout.addWidget(nav_container)

        self.return_warning_label = QLabel("")
        self.return_warning_label.setVisible(False)
        layout.addLayout(inv_layout)

        # Reset button
        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet(self.compact_button_style())
        reset_btn.setFixedWidth(50)
        reset_btn.clicked.connect(self.clear_form)
        layout.addWidget(reset_btn)

        # Export PDF button
        export_pdf_btn = QPushButton("Export PDF")
        export_pdf_btn.setStyleSheet(theme.sales_primary_button_style())
        export_pdf_btn.setFixedWidth(80)
        export_pdf_btn.clicked.connect(self.export_pdf)
        layout.addWidget(export_pdf_btn)

        # Date
        date_layout = QHBoxLayout()
        date_layout.setSpacing(2)
        date_label = QLabel("Date")
        date_label.setStyleSheet(self.micro_label_style())
        self.date_input = QDateEdit()
        configure_qdate_edit(self.date_input)
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setStyleSheet(self.compact_input_style())
        self.apply_calendar_style(self.date_input)
        self.date_input.setFixedWidth(110)
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.date_input)
        layout.addLayout(date_layout)

        # Return Type
        type_layout = QHBoxLayout()
        type_layout.setSpacing(2)
        type_label = QLabel("Type")
        type_label.setStyleSheet(self.micro_label_style())
        self.return_type_combo = QComboBox()
        self.return_type_combo.addItems(["Cash", "Credit"])
        self.return_type_combo.setStyleSheet(self.compact_input_style())
        self.return_type_combo.setFixedWidth(70)
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.return_type_combo)
        layout.addLayout(type_layout)

        # Nature
        nat_layout = QHBoxLayout()
        nat_layout.setSpacing(2)
        nat_label = QLabel("Nature")
        nat_label.setStyleSheet(self.micro_label_style())
        self.nature_combo = QComboBox()
        self.nature_combo.addItems(["Local", "Inter-state"])
        self.nature_combo.setStyleSheet(self.compact_input_style())
        self.nature_combo.setFixedWidth(88)
        nat_layout.addWidget(nat_label)
        nat_layout.addWidget(self.nature_combo)
        layout.addLayout(nat_layout)

        # Party type
        pty_layout = QHBoxLayout()
        pty_layout.setSpacing(2)
        pty_label = QLabel("Party")
        pty_label.setStyleSheet(self.micro_label_style())
        self.party_type_combo = QComboBox()
        self.party_type_combo.addItems(["", "Debtor", "Creditor", "Both"])
        self.party_type_combo.setCurrentText("Debtor")
        self.party_type_combo.setStyleSheet(self.compact_input_style())
        self.party_type_combo.setFixedWidth(88)
        pty_layout.addWidget(pty_label)
        pty_layout.addWidget(self.party_type_combo)
        layout.addLayout(pty_layout)

        layout.addStretch()
        return frame

    # ==================== ZONE C - CUSTOMER INFORMATION MATRIX ====================

    def build_party_information_matrix(self):
        frame = QFrame()
        frame.setStyleSheet(self.party_matrix_style())
        layout = QVBoxLayout(frame)
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        # Row C1: Name, Address, + Debtor button, Edit Debtor button
        row_c1 = QHBoxLayout()
        row_c1.setSpacing(2)

        party_label = QLabel("Name")
        party_label.setStyleSheet(self.micro_label_style())
        self.customer_name_input = QLineEdit()
        self.customer_name_input.setStyleSheet(self.compact_input_style())
        self.customer_name_input.setMinimumWidth(200)
        self.customer_name_input.setMaximumWidth(380)
        self.customer_name_input.textChanged.connect(self.on_customer_name_changed)
        row_c1.addWidget(party_label)
        row_c1.addWidget(self.customer_name_input)

        addr_label = QLabel("Address")
        addr_label.setStyleSheet(self.micro_label_style())
        self.address_input = QLineEdit()
        self.address_input.setStyleSheet(self.compact_input_style())
        self.address_input.setMinimumWidth(160)
        self.address_input.setMaximumWidth(320)
        row_c1.addWidget(addr_label)
        row_c1.addWidget(self.address_input)

        self.add_debitor_btn = QPushButton("+ Debtor")
        self.add_debitor_btn.setStyleSheet(self.primary_button_style())
        self.add_debitor_btn.setFixedWidth(75)
        self.add_debitor_btn.clicked.connect(self.add_new_debitor)
        row_c1.addWidget(self.add_debitor_btn)

        self.edit_debitor_btn = QPushButton("Edit Debtor")
        self.edit_debitor_btn.setStyleSheet(self.primary_button_style())
        self.edit_debitor_btn.setFixedWidth(80)
        self.edit_debitor_btn.clicked.connect(self.edit_current_debitor)
        row_c1.addWidget(self.edit_debitor_btn)

        row_c1.addStretch()
        layout.addLayout(row_c1)

        # Row C2: Mobile, GSTIN, State
        row_c2 = QHBoxLayout()
        row_c2.setSpacing(2)

        mobile_label = QLabel("Mobile")
        mobile_label.setStyleSheet(self.micro_label_style())
        self.mobile_input = QLineEdit()
        self.mobile_input.setStyleSheet(self.compact_input_style())
        self.mobile_input.setFixedWidth(120)
        row_c2.addWidget(mobile_label)
        row_c2.addWidget(self.mobile_input)

        gstin_label = QLabel("GSTIN")
        gstin_label.setStyleSheet(self.micro_label_style())
        self.gstin_input = QLineEdit()
        self.gstin_input.setStyleSheet(self.compact_input_style())
        self.gstin_input.setFixedWidth(160)
        self.gstin_input.setMaxLength(15)
        self.gstin_input.textChanged.connect(self.on_gstin_changed)
        row_c2.addWidget(gstin_label)
        row_c2.addWidget(self.gstin_input)

        state_label = QLabel("State")
        state_label.setStyleSheet(self.micro_label_style())
        self.state_combo = QComboBox()
        self.state_combo.setEditable(True)
        self.state_combo.setStyleSheet(self.compact_input_style())
        self.state_combo.setFixedWidth(210)
        self.state_combo.addItem("")
        for state in sorted(GST_STATE_CODES.values()):
            self.state_combo.addItem(state)
        row_c2.addWidget(state_label)
        row_c2.addWidget(self.state_combo)

        row_c2.addStretch()
        layout.addLayout(row_c2)

        # Row C3: Original Bill No, Narration
        row_c3 = QHBoxLayout()
        row_c3.setSpacing(2)

        bill_label = QLabel("Original Bill No")
        bill_label.setStyleSheet(self.micro_label_style())
        self.original_bill_input = QLineEdit()
        self.original_bill_input.setStyleSheet(self.compact_input_style())
        self.original_bill_input.setFixedWidth(150)
        self.original_bill_input.textEdited.connect(lambda t: self.original_bill_input.setText(t.upper()) or self.original_bill_input.setCursorPosition(len(t)))
        row_c3.addWidget(bill_label)
        row_c3.addWidget(self.original_bill_input)

        narration_label = QLabel("Narration")
        narration_label.setStyleSheet(self.micro_label_style())
        self.narration_input = QLineEdit()
        self.narration_input.setStyleSheet(self.compact_input_style())
        row_c3.addWidget(narration_label)
        row_c3.addWidget(self.narration_input)
        row_c3.addStretch()
        layout.addLayout(row_c3)

        return frame

    # ==================== ZONE D - PRODUCT ENTRY STRIP ====================

    def build_product_entry_matrix(self):
        frame = QFrame()
        frame.setStyleSheet(self.product_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(3)
        layout.setContentsMargins(4, 4, 4, 4)

        # Barcode input with tick
        code_layout = QHBoxLayout()
        code_layout.setSpacing(0)
        code_layout.setContentsMargins(0, 0, 0, 0)
        self.barcode_tick = create_checkbox(variant="compact")
        self.barcode_tick.setChecked(True)
        code_layout.addWidget(self.barcode_tick)
        barcode_label = QLabel(" Barcode")
        barcode_label.setStyleSheet(self.micro_label_style())
        barcode_label.setFixedWidth(58)
        code_layout.addWidget(barcode_label)
        self.barcode_input = QLineEdit()
        self.barcode_input.setStyleSheet(self.barcode_input_style())
        self.barcode_input.setFixedWidth(120)
        self.barcode_input.returnPressed.connect(self.on_barcode_enter)
        code_layout.addWidget(self.barcode_input)
        layout.addLayout(code_layout)

        prod_layout = QHBoxLayout()
        prod_layout.setSpacing(1)
        product_label = QLabel("Product")
        product_label.setStyleSheet(self.micro_label_style())
        product_label.setFixedWidth(50)
        self.product_input = QLineEdit()
        self.product_input.setStyleSheet(self.compact_input_style())
        self.product_input.setFixedWidth(280)
        self.product_input.returnPressed.connect(self.on_product_enter)
        prod_layout.addWidget(product_label)
        prod_layout.addWidget(self.product_input)
        layout.addLayout(prod_layout)

        # Product filter/display controls: Category, Size, Color
        cat_label = QLabel("Category")
        cat_label.setStyleSheet(self.micro_label_style())
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.setStyleSheet(self.compact_input_style())
        self.category_combo.setFixedWidth(100)
        layout.addWidget(cat_label)
        layout.addWidget(self.category_combo)

        size_label = QLabel("Size")
        size_label.setStyleSheet(self.micro_label_style())
        self.size_combo = QComboBox()
        self.size_combo.setEditable(True)
        self.size_combo.setStyleSheet(self.compact_input_style())
        self.size_combo.setFixedWidth(60)
        layout.addWidget(size_label)
        layout.addWidget(self.size_combo)

        color_label = QLabel("Color")
        color_label.setStyleSheet(self.micro_label_style())
        self.color_combo = QComboBox()
        self.color_combo.setEditable(True)
        self.color_combo.setStyleSheet(self.compact_input_style())
        self.color_combo.setFixedWidth(60)
        layout.addWidget(color_label)
        layout.addWidget(self.color_combo)

        # Rate selector with refresh
        rate_sel_layout = QHBoxLayout()
        rate_sel_layout.setSpacing(2)
        rate_sel_label = QLabel("Rate")
        rate_sel_label.setStyleSheet(self.micro_label_style())
        self.rate_selector_combo = QComboBox()
        self.rate_selector_combo.addItems(["Sales Rate", "Purchase Rate", "Wholesale Rate", "MRP"])
        self.rate_selector_combo.setStyleSheet(self.compact_input_style())
        self.rate_selector_combo.setFixedWidth(110)
        rate_sel_layout.addWidget(rate_sel_label)
        rate_sel_layout.addWidget(self.rate_selector_combo)
        refresh_btn = QPushButton("⟳")
        refresh_btn.setStyleSheet(self.compact_button_style())
        refresh_btn.setFixedWidth(25)
        refresh_btn.clicked.connect(self.on_rate_refresh_clicked)
        rate_sel_layout.addWidget(refresh_btn)
        layout.addLayout(rate_sel_layout)

        layout.addStretch()
        return frame

    # ==================== ZONE E - OPTIONS / STATUS STRIP ====================

    def build_bill_options_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.status_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 2, 4, 2)

        stock_label = QLabel("Stock:")
        stock_label.setStyleSheet(self.status_label_style())
        self.stock_display = QLabel("0.000")
        self.stock_display.setStyleSheet(self.status_value_style())
        layout.addWidget(stock_label)
        layout.addWidget(self.stock_display)

        code_label = QLabel("Code:")
        code_label.setStyleSheet(self.status_label_style())
        self.code_display = QLabel("")
        self.code_display.setStyleSheet(self.status_value_style())
        layout.addWidget(code_label)
        layout.addWidget(self.code_display)

        layout.addStretch()

        from ui.checkbox_style import create_checkbox

        self.divide_tax_tick = create_checkbox("Divide tax from unit rate", variant="status")
        layout.addWidget(self.divide_tax_tick)

        return frame

    # ==================== ZONE F - BILLING TABLE ====================

    def build_items_table(self):
        frame = QFrame()
        frame.setStyleSheet(self.table_zone_style())
        layout = QVBoxLayout(frame)
        layout.setSpacing(0)
        layout.setContentsMargins(4, 4, 4, 4)

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(14)
        self.items_table.setHorizontalHeaderLabels([
            "SL", "Product", "HSN",
            "CGST (%)", "SGST (%)", "IGST (%)", "CESS (%)",
            "Rate", "Qty", "Gross", "Disc", "Net", "Tax", "Total"
        ])
        self.items_table.setStyleSheet(self.table_style())
        self.items_table.horizontalHeader().setStyleSheet(self.table_header_style())
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setAlternatingRowColors(False)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.items_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.items_table.setEditTriggers(
            QAbstractItemView.CurrentChanged |
            QAbstractItemView.SelectedClicked |
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.EditKeyPressed |
            QAbstractItemView.AnyKeyPressed
        )

        self.items_table.setColumnWidth(0, 35)    # SL
        self.items_table.setColumnWidth(1, 250)   # Product
        self.items_table.setColumnWidth(2, 80)    # HSN
        self.items_table.setColumnWidth(3, 50)    # CGST (%)
        self.items_table.setColumnWidth(4, 50)    # SGST (%)
        self.items_table.setColumnWidth(5, 50)    # IGST (%)
        self.items_table.setColumnWidth(6, 50)    # CESS (%)
        self.items_table.setColumnWidth(7, 70)    # Rate
        self.items_table.setColumnWidth(8, 60)    # Qty
        self.items_table.setColumnWidth(9, 80)    # Gross
        self.items_table.setColumnWidth(10, 60)   # Disc
        self.items_table.setColumnWidth(11, 80)   # Net
        self.items_table.setColumnWidth(12, 70)   # Tax
        self.items_table.setColumnWidth(13, 80)   # Total

        layout.addWidget(self.items_table)
        return frame

    # ==================== ZONE G - LOWER CONTROL PANEL / FOOTER ====================

    def build_footer_summary_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.footer_panel_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)
        footer_label_width = 82
        footer_field_width = 86

        # ZONE 1 — ADJUSTMENT / PAYMENT BLOCK
        adj_frame = QFrame()
        adj_frame.setStyleSheet(self.adjustment_zone_style())
        adj_layout = QVBoxLayout(adj_frame)
        adj_layout.setSpacing(2)
        adj_layout.setContentsMargins(6, 6, 6, 6)

        # Grand Total (pre-adjustment)
        gt_layout = QHBoxLayout()
        gt_layout.setSpacing(2)
        gt_label = QLabel("Grand Total")
        gt_label.setStyleSheet(self.footer_label_style())
        gt_label.setFixedWidth(footer_label_width)
        self.grand_total_input = QLineEdit()
        self.grand_total_input.setStyleSheet(self.footer_input_readonly_style())
        self.grand_total_input.setReadOnly(True)
        self.grand_total_input.setFixedWidth(footer_field_width)
        gt_layout.addWidget(gt_label)
        gt_layout.addWidget(self.grand_total_input)
        adj_layout.addLayout(gt_layout)

        # Footer Discount
        disc_layout = QHBoxLayout()
        disc_layout.setSpacing(2)
        disc_label_vbox = QVBoxLayout()
        disc_label_vbox.setSpacing(0)
        disc_label_vbox.setContentsMargins(0, 0, 0, 0)
        self.discount_label = QLabel("Discount")
        self.discount_label.setStyleSheet(self.footer_label_style())
        self.discount_label.setFixedWidth(footer_label_width)
        self.discount_label.setToolTip("Press Down-Arrow inside the Discount box to interpret the value as a percentage.")
        self.discount_percent_label = QLabel("")
        self.discount_percent_label.setFixedWidth(footer_label_width)
        self.discount_percent_label.setStyleSheet(self.discount_percent_hint_style())
        disc_label_vbox.addWidget(self.discount_label)
        disc_label_vbox.addWidget(self.discount_percent_label)
        disc_layout.addLayout(disc_label_vbox)
        self.discount_total_input = QLineEdit()
        self.discount_total_input.setStyleSheet(self.footer_input_style())
        self.discount_total_input.setText("0.00")
        self.discount_total_input.setValidator(QDoubleValidator())
        self.discount_total_input.setFixedWidth(footer_field_width)
        disc_layout.addWidget(self.discount_total_input)
        adj_layout.addLayout(disc_layout)

        # Round Off
        ro_layout = QHBoxLayout()
        ro_layout.setSpacing(2)
        ro_label = QLabel("Round Off")
        ro_label.setStyleSheet(self.footer_label_style())
        ro_label.setFixedWidth(footer_label_width)
        ro_container = QFrame()
        ro_container.setStyleSheet(self.footer_input_style())
        ro_container.setFixedWidth(footer_field_width)
        ro_container_layout = QHBoxLayout(ro_container)
        ro_container_layout.setContentsMargins(2, 0, 2, 0)
        ro_container_layout.setSpacing(2)
        self.round_off_checkbox = create_checkbox(variant="compact")
        self.round_off_checkbox.setFixedSize(14, 14)
        self.round_off_checkbox.setChecked(True)
        self.round_off_input = QLineEdit()
        self.round_off_input.setStyleSheet(self.round_off_input_style())
        self.round_off_input.setText("0.00")
        self.round_off_input.setValidator(QDoubleValidator())
        ro_container_layout.addWidget(self.round_off_checkbox)
        ro_container_layout.addWidget(self.round_off_input)
        ro_layout.addWidget(ro_label)
        ro_layout.addWidget(ro_container)
        adj_layout.addLayout(ro_layout)

        # Net Amount
        na_layout = QHBoxLayout()
        na_layout.setSpacing(2)
        na_label = QLabel("Net Amount")
        na_label.setStyleSheet(self.footer_label_style())
        na_label.setFixedWidth(footer_label_width)
        self.net_amount_display = QLabel("0.00")
        self.net_amount_display.setStyleSheet(self.footer_value_style())
        self.net_amount_display.setFixedWidth(footer_field_width)
        na_layout.addWidget(na_label)
        na_layout.addWidget(self.net_amount_display)
        adj_layout.addLayout(na_layout)

        # Amount Refunded
        ar_layout = QHBoxLayout()
        ar_layout.setSpacing(2)
        ar_label = QLabel("Amt Refunded")
        ar_label.setStyleSheet(self.footer_label_style())
        ar_label.setFixedWidth(footer_label_width)
        self.amount_refunded_input = QLineEdit()
        self.amount_refunded_input.setStyleSheet(self.footer_input_style())
        self.amount_refunded_input.setText("0.00")
        self.amount_refunded_input.setFixedWidth(footer_field_width)
        ar_layout.addWidget(ar_label)
        ar_layout.addWidget(self.amount_refunded_input)
        adj_layout.addLayout(ar_layout)

        # Balance
        bal_layout = QHBoxLayout()
        bal_layout.setSpacing(2)
        bal_label = QLabel("Balance")
        bal_label.setStyleSheet(self.footer_label_style())
        bal_label.setFixedWidth(footer_label_width)
        self.balance_display = QLabel("0.00")
        self.balance_display.setStyleSheet(self.footer_value_style())
        self.balance_display.setFixedWidth(footer_field_width)
        bal_layout.addWidget(bal_label)
        bal_layout.addWidget(self.balance_display)
        adj_layout.addLayout(bal_layout)

        adj_layout.addStretch()
        adj_frame.setFixedWidth(220)
        layout.addWidget(adj_frame)

        # ZONE 2 — TAX SUMMARY BLOCK
        tax_frame = QFrame()
        tax_frame.setStyleSheet(self.tax_zone_style())
        tax_layout = QVBoxLayout(tax_frame)
        tax_layout.setSpacing(2)
        tax_layout.setContentsMargins(6, 6, 6, 6)

        nv_layout = QHBoxLayout()
        nv_layout.setSpacing(2)
        nv_label = QLabel("Net Value")
        nv_label.setStyleSheet(self.footer_label_style())
        nv_label.setFixedWidth(footer_label_width)
        self.net_value_display = QLabel("0.00")
        self.net_value_display.setStyleSheet(self.footer_value_style())
        self.net_value_display.setFixedWidth(footer_field_width)
        nv_layout.addWidget(nv_label)
        nv_layout.addWidget(self.net_value_display)
        tax_layout.addLayout(nv_layout)

        cgst_layout = QHBoxLayout()
        cgst_layout.setSpacing(2)
        cgst_label = QLabel("Add CGST")
        cgst_label.setStyleSheet(self.footer_label_style())
        cgst_label.setFixedWidth(footer_label_width)
        self.cgst_display = QLabel("0.00")
        self.cgst_display.setStyleSheet(self.footer_value_style())
        self.cgst_display.setFixedWidth(footer_field_width)
        cgst_layout.addWidget(cgst_label)
        cgst_layout.addWidget(self.cgst_display)
        tax_layout.addLayout(cgst_layout)

        sgst_layout = QHBoxLayout()
        sgst_layout.setSpacing(2)
        sgst_label = QLabel("Add SGST")
        sgst_label.setStyleSheet(self.footer_label_style())
        sgst_label.setFixedWidth(footer_label_width)
        self.sgst_display = QLabel("0.00")
        self.sgst_display.setStyleSheet(self.footer_value_style())
        self.sgst_display.setFixedWidth(footer_field_width)
        sgst_layout.addWidget(sgst_label)
        sgst_layout.addWidget(self.sgst_display)
        tax_layout.addLayout(sgst_layout)

        igst_layout = QHBoxLayout()
        igst_layout.setSpacing(2)
        igst_label = QLabel("Add IGST")
        igst_label.setStyleSheet(self.footer_label_style())
        igst_label.setFixedWidth(footer_label_width)
        self.igst_display = QLabel("0.00")
        self.igst_display.setStyleSheet(self.footer_value_style())
        self.igst_display.setFixedWidth(footer_field_width)
        igst_layout.addWidget(igst_label)
        igst_layout.addWidget(self.igst_display)
        tax_layout.addLayout(igst_layout)

        ta_layout = QHBoxLayout()
        ta_layout.setSpacing(2)
        ta_label = QLabel("Tax Amount")
        ta_label.setStyleSheet(self.footer_label_style())
        ta_label.setFixedWidth(footer_label_width)
        self.tax_amount_display = QLabel("0.00")
        self.tax_amount_display.setStyleSheet(self.footer_value_style())
        self.tax_amount_display.setFixedWidth(footer_field_width)
        ta_layout.addWidget(ta_label)
        ta_layout.addWidget(self.tax_amount_display)
        tax_layout.addLayout(ta_layout)

        cess_layout = QHBoxLayout()
        cess_layout.setSpacing(2)
        cess_label = QLabel("Cess")
        cess_label.setStyleSheet(self.footer_label_style())
        cess_label.setFixedWidth(footer_label_width)
        self.cess_display = QLabel("0.00")
        self.cess_display.setStyleSheet(self.footer_value_style())
        self.cess_display.setFixedWidth(footer_field_width)
        cess_layout.addWidget(cess_label)
        cess_layout.addWidget(self.cess_display)
        tax_layout.addLayout(cess_layout)

        gt2_layout = QHBoxLayout()
        gt2_layout.setSpacing(2)
        gt2_label = QLabel("Grand Total")
        gt2_label.setStyleSheet(self.footer_label_style())
        gt2_label.setFixedWidth(footer_label_width)
        self.final_amount_display = QLabel("₹ 0.00")
        self.final_amount_display.setStyleSheet(self.footer_final_style())
        self.final_amount_display.setFixedWidth(footer_field_width)
        gt2_layout.addWidget(gt2_label)
        gt2_layout.addWidget(self.final_amount_display)
        tax_layout.addLayout(gt2_layout)

        tax_layout.addStretch()
        tax_frame.setFixedWidth(210)
        layout.addWidget(tax_frame)

        # ZONE 3 — ACTION BUTTONS (vertical stack)
        action_frame = QFrame()
        action_frame.setStyleSheet(self.action_zone_style())
        action_layout = QVBoxLayout(action_frame)
        action_layout.setSpacing(3)
        action_layout.setContentsMargins(4, 4, 4, 4)

        self.ok_btn = QPushButton("Save")
        self.ok_btn.setStyleSheet(self.save_button_style())
        self.ok_btn.clicked.connect(self.save_return)
        self.ok_btn.setToolTip("Save a new return. When viewing a saved return this becomes Update.")
        action_layout.addWidget(self.ok_btn)

        print_btn = QPushButton("Print")
        print_btn.setStyleSheet(self.compact_button_style())
        print_btn.clicked.connect(self.print_return)
        action_layout.addWidget(print_btn)

        reset_btn = QPushButton("Reset All")
        reset_btn.setStyleSheet(self.compact_button_style())
        reset_btn.clicked.connect(self.clear_form)
        action_layout.addWidget(reset_btn)

        del_item_btn = QPushButton("Remove Item")
        del_item_btn.setStyleSheet(self.danger_button_style())
        del_item_btn.clicked.connect(self.remove_current_item)
        action_layout.addWidget(del_item_btn)

        del_return_btn = QPushButton("Remove Return")
        del_return_btn.setStyleSheet(self.danger_button_style())
        del_return_btn.clicked.connect(self.delete_return)
        action_layout.addWidget(del_return_btn)

        action_layout.addStretch()
        action_frame.setFixedWidth(135)
        layout.addWidget(action_frame)

        layout.addStretch(1)

        # Hidden fields for backward compatibility
        self.sub_total_input = QLineEdit()
        self.sub_total_input.setVisible(False)
        self.round_off_display = QLineEdit()
        self.round_off_display.setVisible(False)
        self.grand_total_display = QLineEdit()
        self.grand_total_display.setVisible(False)

        return frame

    # ==================== STYLE METHODS ====================

    def header_strip_style(self):
        return theme.entry_header_strip_style()

    def page_title_style(self):
        return theme.entry_page_title_label_style()

    def invoice_command_strip_style(self):
        return theme.entry_command_strip_style()

    def party_matrix_style(self):
        return theme.entry_section_frame_style()

    def product_strip_style(self):
        return theme.entry_inset_frame_style()

    def options_strip_style(self):
        return theme.entry_section_frame_style()

    def table_zone_style(self):
        return theme.entry_inset_frame_style()

    def footer_panel_style(self):
        return theme.entry_section_frame_style()

    def action_zone_style(self):
        return theme.entry_inset_frame_style()

    def adjustment_zone_style(self):
        return theme.entry_inset_frame_style()

    def tax_zone_style(self):
        return theme.entry_inset_frame_style()

    def compact_input_style(self):
        return theme.sales_compact_input_style()

    def barcode_input_style(self):
        return theme.sales_barcode_input_style()

    def micro_label_style(self):
        return theme.sales_micro_label_style()

    def nav_button_style(self):
        return theme.sales_nav_button_style()

    def compact_button_style(self):
        return theme.sales_compact_button_style()

    def primary_button_style(self):
        return theme.sales_primary_button_style()

    def danger_button_style(self):
        return theme.sales_danger_button_style()

    def save_button_style(self):
        return theme.entry_save_button_style()

    def table_style(self):
        return theme.editable_table_style()

    def table_header_style(self):
        return theme.entry_table_header_style()

    def footer_label_style(self):
        return theme.entry_footer_label_style()

    def footer_input_style(self):
        return theme.entry_footer_input_style()

    def footer_input_readonly_style(self):
        return theme.entry_footer_input_readonly_style()

    def footer_discount_box_style(self):
        return theme.entry_footer_input_style()

    def footer_value_style(self):
        return theme.entry_value_style("input_text")

    def footer_final_style(self):
        return theme.entry_info_value_style()

    def grand_total_green_style(self):
        return theme.entry_value_style("accent_highlight")

    def status_strip_style(self):
        return theme.entry_section_frame_style()

    def status_label_style(self):
        return theme.sales_status_label_style()

    def status_value_style(self):
        return theme.sales_status_value_style()

    def status_checkbox_style(self):
        return theme.sales_status_checkbox_style()

    def nav_box_style(self):
        return theme.sales_nav_box_style()

    def round_off_input_style(self):
        colors = theme._theme_colors()
        return (
            f"QLineEdit {{ background-color: transparent; border: none; "
            f"color: {colors['input_text']}; font-size: 10px; padding: 0px; }}"
        )

    def discount_percent_hint_style(self):
        return theme.entry_micro_hint_style()