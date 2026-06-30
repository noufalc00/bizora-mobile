"""
UI building methods for Sales Entry widget.
Contains all UI layout building methods and style helpers.
"""

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QDoubleValidator, QTextCharFormat, QColor

from ui import theme
from ui.checkbox_style import create_checkbox
from ui.date_formats import configure_qdate_edit
from .theme import GST_STATE_CODES


class SalesEntryUIMixin:
    """Mixin class containing all UI building and styling methods for Sales Entry."""

    def apply_calendar_style(self, date_edit):
        """Apply the shared Purchase Entry dark calendar theme to a QDateEdit popup.

        Matches the Purchase Entry calendar exactly: crisp white "<"/">" month
        selectors, a deep-blue (#0056b3) today highlight with bold white numerals,
        high-contrast year dropdown menus, and a navigation bar sized so the full
        4-digit year string is never vertically clipped on Windows 10.
        """
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

        title_label = QLabel("SALES BILL")
        title_label.setStyleSheet(self.page_title_style())
        layout.addWidget(title_label)
        layout.addStretch()
        return frame

    # ==================== ZONE B - TOP INVOICE COMMAND STRIP ====================

    def build_invoice_command_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.invoice_command_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Series prefix is retained for invoice-numbering logic but hidden from the
        # top bar (kept as an empty off-screen field so the rest of the strip fits).
        self.series_input = QLineEdit()
        self.series_input.setVisible(False)

        # Invoice No
        inv_layout = QHBoxLayout()
        inv_layout.setSpacing(1)
        inv_label = QLabel("Invoice")
        inv_label.setStyleSheet(self.micro_label_style())
        self.invoice_no_input = QLineEdit()
        self.invoice_no_input.setStyleSheet(self.compact_input_style())
        self.invoice_no_input.setPlaceholderText("Auto")
        self.invoice_no_input.setFixedWidth(70)
        inv_layout.addWidget(inv_label)
        inv_layout.addWidget(self.invoice_no_input)

        # Navigation buttons - plain vertical stack, no surrounding box
        nav_container = QWidget()
        nav_container.setFixedWidth(18)
        nav_v = QVBoxLayout(nav_container)
        nav_v.setSpacing(1)
        nav_v.setContentsMargins(0, 0, 0, 0)

        prev_btn = QPushButton("▲")
        prev_btn.setStyleSheet(self.nav_button_style())
        prev_btn.setFixedSize(18, 11)
        prev_btn.clicked.connect(self.next_bill)
        nav_v.addWidget(prev_btn)

        next_btn = QPushButton("▼")
        next_btn.setStyleSheet(self.nav_button_style())
        next_btn.setFixedSize(18, 11)
        next_btn.clicked.connect(self.previous_bill)
        nav_v.addWidget(next_btn)

        inv_layout.addWidget(nav_container)
        layout.addLayout(inv_layout)

        # Specific No. Checkbox
        self.invoice_checkbox = create_checkbox("Fixed", variant="default")
        self.invoice_checkbox.setToolTip("Entry with Specific Invoice No.")
        layout.addWidget(self.invoice_checkbox)

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

        # Sales Type
        type_layout = QHBoxLayout()
        type_layout.setSpacing(2)
        type_label = QLabel("Type")
        type_label.setStyleSheet(self.micro_label_style())
        self.sales_type_combo = QComboBox()
        self.sales_type_combo.addItems(["Cash", "Credit"])
        self.sales_type_combo.setStyleSheet(self.compact_input_style())
        self.sales_type_combo.setFixedWidth(75)
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.sales_type_combo)
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

        # Form of Sale
        fos_layout = QHBoxLayout()
        fos_layout.setSpacing(2)
        fos_label = QLabel("Form of Sale")
        fos_label.setStyleSheet(self.micro_label_style())
        self.form_of_sale_combo = QComboBox()
        self.form_of_sale_combo.addItems(["B2B", "B2CS", "B2CL"])
        self.form_of_sale_combo.setCurrentText("B2CS")
        self.form_of_sale_combo.setStyleSheet(self.compact_input_style())
        self.form_of_sale_combo.setFixedWidth(70)
        fos_layout.addWidget(fos_label)
        fos_layout.addWidget(self.form_of_sale_combo)
        layout.addLayout(fos_layout)

        # Party Type
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

        # Due Date
        due_layout = QHBoxLayout()
        due_layout.setSpacing(2)
        due_label = QLabel("Due Date")
        due_label.setStyleSheet(self.micro_label_style())
        self.due_date_input = QDateEdit()
        configure_qdate_edit(self.due_date_input)
        self.due_date_input.setDate(QDate.currentDate().addDays(30))
        self.due_date_input.setCalendarPopup(True)
        self.due_date_input.setStyleSheet(self.compact_input_style())
        self.apply_calendar_style(self.due_date_input)
        self.due_date_input.setFixedWidth(110)
        due_layout.addWidget(due_label)
        due_layout.addWidget(self.due_date_input)
        layout.addLayout(due_layout)

        layout.addStretch()
        return frame

    # ==================== ZONE C - PARTY / CUSTOMER INFORMATION MATRIX ====================

    def build_party_information_matrix(self):
        frame = QFrame()
        frame.setStyleSheet(self.party_matrix_style())
        layout = QVBoxLayout(frame)
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        # Row C1: Name, Address, + Debtors button, Return button
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
        self.address_input.textChanged.connect(self.on_address_changed)
        row_c1.addWidget(addr_label)
        row_c1.addWidget(self.address_input)

        self.add_debtor_btn = QPushButton("+ Debtors")
        self.add_debtor_btn.setStyleSheet(self.primary_button_style())
        self.add_debtor_btn.setFixedSize(82, 26)
        # Open the Debtor/Creditor page in the Masters main menu
        self.add_debtor_btn.clicked.connect(self.open_debitor_creditor_page)
        row_c1.addWidget(self.add_debtor_btn)

        self.return_btn = QPushButton("Return")
        self.return_btn.setStyleSheet(self.primary_button_style())
        self.return_btn.setFixedSize(82, 26)
        row_c1.addWidget(self.return_btn)

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
        self.state_combo.addItems([""])
        for state in sorted(GST_STATE_CODES.values()):
            self.state_combo.addItem(state)
        self.state_combo.currentTextChanged.connect(self.on_state_changed)
        row_c2.addWidget(state_label)
        row_c2.addWidget(self.state_combo)

        row_c2.addStretch()
        layout.addLayout(row_c2)

        # Row C3: Narration and Salesman
        row_c3 = QHBoxLayout()
        row_c3.setSpacing(2)
        narr_label = QLabel("Narration")
        narr_label.setStyleSheet(self.micro_label_style())
        self.narration_input = QLineEdit()
        self.narration_input.setStyleSheet(self.compact_input_style())
        self.narration_input.setFixedWidth(200)
        self.narration_input.setFixedHeight(26)
        row_c3.addWidget(narr_label)
        row_c3.addWidget(self.narration_input)

        salesman_label = QLabel("Salesman:")
        salesman_label.setStyleSheet(self.micro_label_style())
        self.salesman_combo = QComboBox()
        self.salesman_combo.setStyleSheet(self.compact_input_style())
        self.salesman_combo.setFixedWidth(140)
        self.salesman_combo.setFixedHeight(26)
        self.add_salesman_btn = QPushButton()
        self._configure_sales_icon_button(
            self.add_salesman_btn,
            "+",
            "Add new salesman",
        )
        if hasattr(self, "add_new_salesman"):
            self.add_salesman_btn.clicked.connect(self.add_new_salesman)
        else:
            self.add_salesman_btn.setEnabled(False)
            self.add_salesman_btn.setToolTip("Salesman master is not available in this screen")
        row_c3.addWidget(salesman_label)
        row_c3.addWidget(self.salesman_combo)
        row_c3.addWidget(self.add_salesman_btn)
        row_c3.addStretch()
        layout.addLayout(row_c3)

        return frame

    # ==================== ZONE D - PRODUCT ENTRY STRIP ====================

    def build_product_entry_strip(self):
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
        self.barcode_tick.setChecked(True)  # Default ON
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

        # Product search input (opens popup on Enter)
        prod_layout = QHBoxLayout()
        prod_layout.setSpacing(1)
        prod_label = QLabel("Product")
        prod_label.setStyleSheet(self.micro_label_style())
        prod_label.setFixedWidth(50)
        self.product_input = QLineEdit()
        self.product_input.setStyleSheet(self.compact_input_style())
        self.product_input.setFixedWidth(280)
        prod_layout.addWidget(prod_label)
        prod_layout.addWidget(self.product_input)
        layout.addLayout(prod_layout)

        # Display fields: Category, Size, Color
        cat_label = QLabel("Category")
        cat_label.setStyleSheet(self.micro_label_style())
        self.category_display = QLineEdit()
        self.category_display.setStyleSheet(self.compact_input_style())
        self.category_display.setReadOnly(True)
        self.category_display.setFixedWidth(100)
        layout.addWidget(cat_label)
        layout.addWidget(self.category_display)

        size_label = QLabel("Size")
        size_label.setStyleSheet(self.micro_label_style())
        self.size_display = QLineEdit()
        self.size_display.setStyleSheet(self.compact_input_style())
        self.size_display.setReadOnly(True)
        self.size_display.setFixedWidth(60)
        layout.addWidget(size_label)
        layout.addWidget(self.size_display)

        color_label = QLabel("Color")
        color_label.setStyleSheet(self.micro_label_style())
        self.color_display = QLineEdit()
        self.color_display.setStyleSheet(self.compact_input_style())
        self.color_display.setReadOnly(True)
        self.color_display.setFixedWidth(60)
        layout.addWidget(color_label)
        layout.addWidget(self.color_display)

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
        self.rate_refresh_btn = QPushButton()
        self._configure_sales_icon_button(
            self.rate_refresh_btn,
            "⟳",
            "Refresh rate from selected price list",
        )
        self.rate_refresh_btn.clicked.connect(self.on_rate_refresh_clicked)
        rate_sel_layout.addWidget(self.rate_refresh_btn)
        layout.addLayout(rate_sel_layout)

        # Uniform interactive-component height across the whole product bar for
        # crisp, symmetrical vertical alignment.
        for _field in (self.barcode_input, self.product_input, self.category_display,
                       self.size_display, self.color_display, self.rate_selector_combo,
                       self.rate_refresh_btn):
            _field.setFixedHeight(28)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch()
        return frame

    # ==================== ZONE E - BILL OPTIONS / LIVE STATUS STRIP ====================

    def build_status_options_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.status_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Left side: Live info (Stock and Code grouped together)
        stock_label = QLabel("Stock:")
        stock_label.setStyleSheet(self.status_label_style())
        self.stock_display = QLabel("0.000")
        self.stock_display.setStyleSheet(self.status_value_style())
        layout.addWidget(stock_label)
        layout.addWidget(self.stock_display)

        code_display_label = QLabel("Code:")
        code_display_label.setStyleSheet(self.status_label_style())
        self.code_display = QLabel("")
        self.code_display.setStyleSheet(self.status_value_style())
        layout.addWidget(code_display_label)
        layout.addWidget(self.code_display)

        layout.addStretch()

        # Right side: Billing options
        self.divide_tax_tick = create_checkbox("Divide tax from unit rate", variant="status")
        layout.addWidget(self.divide_tax_tick)

        return frame

    # ==================== ZONE F - MAIN BILLING TABLE ZONE ====================

    def build_items_table_zone(self):
        from .sales_entry_delegate import SalesBillDelegate
        
        frame = QFrame()
        frame.setStyleSheet(self.table_zone_style())
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(14)
        self.items_table.setHorizontalHeaderLabels([
            "SL", "Product", "HSN", "CGST (%)", "SGST (%)", "IGST (%)", "CESS (%)",
            "Rate", "Qty", "Gross", "Disc", "Net", "Tax", "Total"
        ])
        self.items_table.setStyleSheet(self.billing_table_style())
        self.items_table.setSelectionBehavior(QTableWidget.SelectItems)
        self.items_table.setSelectionMode(QTableWidget.SingleSelection)
        self.items_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setAlternatingRowColors(False)
        self.items_table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.items_table.cellChanged.connect(self.on_table_cell_changed, type=Qt.QueuedConnection)
        
        # Install custom delegate for outline-only selection and exact keyboard flow
        self.table_delegate = SalesBillDelegate(self)
        self.items_table.setItemDelegate(self.table_delegate)

        # Professional column widths
        self.items_table.setColumnWidth(0, 35)
        self.items_table.setColumnWidth(1, 200)
        self.items_table.setColumnWidth(2, 75)
        self.items_table.setColumnWidth(3, 88)
        self.items_table.setColumnWidth(4, 88)
        self.items_table.setColumnWidth(5, 88)
        self.items_table.setColumnWidth(6, 88)
        self.items_table.setColumnWidth(7, 65)
        self.items_table.setColumnWidth(8, 50)
        self.items_table.setColumnWidth(9, 65)
        self.items_table.setColumnWidth(10, 55)
        self.items_table.setColumnWidth(11, 60)
        self.items_table.setColumnWidth(12, 55)
        self.items_table.setColumnWidth(13, 80)

        layout.addWidget(self.items_table)
        return frame

    # ==================== ZONE G + H - LOWER CONTROL PANEL WITH TOTALS ====================

    def build_lower_control_panel(self):
        frame = QFrame()
        frame.setStyleSheet(self.footer_panel_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # ZONE 1 — ACTION BUTTONS (vertical stack, fixed width)
        action_frame = QFrame()
        action_frame.setStyleSheet(self.action_zone_style())
        action_layout = QVBoxLayout(action_frame)
        action_layout.setSpacing(5)
        action_layout.setContentsMargins(6, 6, 6, 6)

        self.ok_btn = QPushButton("Save")
        self.ok_btn.setStyleSheet(self.save_button_style())
        self.ok_btn.clicked.connect(lambda: self.save(is_manual=True))
        self.ok_btn.setToolTip("Save a new bill. When viewing a saved bill this becomes Update.")
        action_layout.addWidget(self.ok_btn)

        print_btn = QPushButton("Print")
        print_btn.setStyleSheet(self.compact_button_style())
        print_btn.clicked.connect(self.print_invoice)
        action_layout.addWidget(print_btn)

        self.btn_whatsapp = QPushButton("WhatsApp Bill")
        self.btn_whatsapp.setStyleSheet("""
            QPushButton {
                background-color: #25D366;
                color: #ffffff;
                border: none;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 4px 6px;
            }
            QPushButton:hover { background-color: #1ebe57; }
            QPushButton:pressed { background-color: #128C7E; }
        """)
        self.btn_whatsapp.clicked.connect(lambda: self.share_bill("whatsapp"))
        action_layout.addWidget(self.btn_whatsapp)

        self.btn_sms = QPushButton("SMS Bill")
        self.btn_sms.setStyleSheet(theme.entry_secondary_action_button_style())
        self.btn_sms.clicked.connect(lambda: self.share_bill("sms"))
        action_layout.addWidget(self.btn_sms)

        reset_btn = QPushButton("Reset All")
        reset_btn.setStyleSheet(self.compact_button_style())
        reset_btn.clicked.connect(self.clear_form)
        action_layout.addWidget(reset_btn)

        del_item_btn = QPushButton("Remove Item")
        del_item_btn.setStyleSheet(self.danger_button_style())
        del_item_btn.clicked.connect(self.confirm_remove_item)
        action_layout.addWidget(del_item_btn)

        del_bill_btn = QPushButton("Remove Bill")
        del_bill_btn.setStyleSheet(self.danger_button_style())
        del_bill_btn.clicked.connect(self.confirm_remove_bill)
        action_layout.addWidget(del_bill_btn)

        action_layout.addStretch()
        action_frame.setFixedWidth(150)

        # ZONE 2A — BALANCE / PAYMENT BLOCK
        adj_frame = QFrame()
        adj_frame.setStyleSheet(self.adjustment_zone_style())
        adj_layout = QVBoxLayout(adj_frame)
        adj_layout.setSpacing(2)
        adj_layout.setContentsMargins(6, 6, 6, 6)

        # Opening Balance
        ob_layout = QHBoxLayout()
        ob_layout.setSpacing(2)
        ob_label = QLabel("Opening Bal")
        ob_label.setStyleSheet(self.footer_label_style())
        self.db_display = QLineEdit()
        self.db_display.setStyleSheet(self.footer_input_readonly_style())
        self.db_display.setText("0.00")
        self.db_display.setReadOnly(True)
        self.db_display.setFixedWidth(80)
        ob_layout.addWidget(ob_label)
        ob_layout.addWidget(self.db_display)
        adj_layout.addLayout(ob_layout)

        # Closing Balance
        cb_layout = QHBoxLayout()
        cb_layout.setSpacing(2)
        cb_label = QLabel("Closing Bal")
        cb_label.setStyleSheet(self.footer_label_style())
        self.cb_display = QLineEdit()
        self.cb_display.setStyleSheet(self.footer_input_readonly_style())
        self.cb_display.setText("0.00")
        self.cb_display.setReadOnly(True)
        self.cb_display.setFixedWidth(80)
        cb_layout.addWidget(cb_label)
        cb_layout.addWidget(self.cb_display)
        adj_layout.addLayout(cb_layout)

        # Grand Total (pre-adjustment)
        gt_layout = QHBoxLayout()
        gt_layout.setSpacing(2)
        gt_label = QLabel("Grand Total")
        gt_label.setStyleSheet(self.footer_label_style())
        self.grand_total_input = QLineEdit()
        self.grand_total_input.setStyleSheet(self.footer_input_readonly_style())
        self.grand_total_input.setReadOnly(True)
        self.grand_total_input.setFixedWidth(80)
        gt_layout.addWidget(gt_label)
        gt_layout.addWidget(self.grand_total_input)
        adj_layout.addLayout(gt_layout)

        # Amount Received
        ap_layout = QHBoxLayout()
        ap_layout.setSpacing(2)
        ap_label = QLabel("Amt Received")
        ap_label.setStyleSheet(self.footer_label_style())
        self.amount_receive_input = QLineEdit()
        self.amount_receive_input.setStyleSheet(self.footer_input_style())
        self.amount_receive_input.setText("0.00")
        self.amount_receive_input.setFixedWidth(80)
        ap_layout.addWidget(ap_label)
        ap_layout.addWidget(self.amount_receive_input)
        adj_layout.addLayout(ap_layout)

        # Balance
        bal_layout = QHBoxLayout()
        bal_layout.setSpacing(2)
        bal_label = QLabel("Balance")
        bal_label.setStyleSheet(self.footer_label_style())
        self.balance_display = QLabel("0.00")
        self.balance_display.setStyleSheet(self.footer_value_style())
        bal_layout.addWidget(bal_label)
        bal_layout.addWidget(self.balance_display)
        adj_layout.addLayout(bal_layout)

        # Qt treats a single '&' as a mnemonic — escape it as '&&'
        self.print_ob_checkbox = create_checkbox("Print O/B && Amt Rcvd", variant="default")
        adj_layout.addWidget(self.print_ob_checkbox)

        adj_layout.addStretch()
        adj_frame.setFixedWidth(195)
        layout.addWidget(adj_frame)

        # ZONE 2B — ADJUSTMENTS BLOCK (Freight / Round Off / Discount / Net Amount)
        adjb_frame = QFrame()
        adjb_frame.setStyleSheet(self.adjustment_zone_style())
        adjb_layout = QVBoxLayout(adjb_frame)
        adjb_layout.setSpacing(2)
        adjb_layout.setContentsMargins(6, 6, 6, 6)

        # Freight
        fr_layout = QHBoxLayout()
        fr_layout.setSpacing(2)
        fr_label = QLabel("Freight")
        fr_label.setStyleSheet(self.footer_label_style())
        self.freight_input = QLineEdit()
        self.freight_input.setStyleSheet(self.footer_input_style())
        self.freight_input.setText("0.00")
        self.freight_input.setFixedWidth(80)
        fr_layout.addWidget(fr_label)
        fr_layout.addWidget(self.freight_input)
        adjb_layout.addLayout(fr_layout)

        # Round Off
        ro_layout = QHBoxLayout()
        ro_layout.setSpacing(2)
        ro_label = QLabel("Round Off")
        ro_label.setStyleSheet(self.footer_label_style())
        # Create container for input with checkbox inside
        ro_container = QFrame()
        ro_container.setStyleSheet(self.footer_input_style())
        ro_container.setFixedWidth(80)
        ro_container_layout = QHBoxLayout(ro_container)
        ro_container_layout.setSpacing(2)
        ro_container_layout.setContentsMargins(2, 0, 2, 0)
        self.round_off_input = QLineEdit()
        self.round_off_input.setStyleSheet("""QLineEdit {
            background-color: transparent;
            border: none;
            color: #f1f5f9;
            font-size: 10px;
            padding: 0px;
        }""")
        self.round_off_input.setText("0.00")
        self.round_off_input.setValidator(QDoubleValidator())
        self.round_off_input.textChanged.connect(self.calculate_totals)
        self.round_off_checkbox = create_checkbox(variant="compact")
        self.round_off_checkbox.setFixedSize(14, 14)
        self.round_off_checkbox.setChecked(True)
        self.round_off_checkbox.stateChanged.connect(lambda _state: self.calculate_totals())
        ro_container_layout.addWidget(self.round_off_checkbox)
        ro_container_layout.addWidget(self.round_off_input)
        ro_layout.addWidget(ro_label)
        ro_layout.addWidget(ro_container)
        adjb_layout.addLayout(ro_layout)

        # Discount
        disc_layout = QHBoxLayout()
        disc_layout.setSpacing(2)
        disc_label_vbox = QVBoxLayout()
        disc_label_vbox.setSpacing(0)
        disc_label_vbox.setContentsMargins(0, 0, 0, 0)
        self.discount_label = QLabel("Discount")
        self.discount_label.setStyleSheet(self.footer_label_style())
        self.discount_label.setToolTip("Press Down-Arrow inside the Discount box to interpret the value as a percentage.")
        self.discount_percent_label = QLabel("")
        self.discount_percent_label.setStyleSheet("QLabel { color: #8ab4f8; font-size: 7px; padding: 0px; margin: 0px; }")
        disc_label_vbox.addWidget(self.discount_label)
        disc_label_vbox.addWidget(self.discount_percent_label)
        disc_layout.addLayout(disc_label_vbox)
        self.discount_total_input = QLineEdit()
        self.discount_total_input.setStyleSheet(self.footer_input_style())
        self.discount_total_input.setText("0.00")
        self.discount_total_input.setFixedWidth(80)
        disc_layout.addWidget(self.discount_total_input)
        adjb_layout.addLayout(disc_layout)

        # Net Amount
        na_layout = QHBoxLayout()
        na_layout.setSpacing(2)
        na_label = QLabel("Net Amount")
        na_label.setStyleSheet(self.footer_label_style())
        self.net_amount_input = QLineEdit()
        self.net_amount_input.setStyleSheet(self.footer_input_readonly_style())
        self.net_amount_input.setText("0.00")
        self.net_amount_input.setReadOnly(True)
        self.net_amount_input.setFixedWidth(80)
        na_layout.addWidget(na_label)
        na_layout.addWidget(self.net_amount_input)
        adjb_layout.addLayout(na_layout)

        adjb_layout.addStretch()
        adjb_frame.setFixedWidth(175)
        layout.addWidget(adjb_frame)

        # ZONE 3 — TAX SUMMARY BLOCK
        tax_frame = QFrame()
        tax_frame.setStyleSheet(self.tax_zone_style())
        tax_layout = QVBoxLayout(tax_frame)
        tax_layout.setSpacing(2)
        tax_layout.setContentsMargins(6, 6, 6, 6)

        # Net Value
        nv_layout = QHBoxLayout()
        nv_layout.setSpacing(2)
        nv_label = QLabel("Net Value")
        nv_label.setStyleSheet(self.footer_label_style())
        self.net_value_display = QLabel("0.00")
        self.net_value_display.setStyleSheet(self.footer_value_style())
        nv_layout.addWidget(nv_label)
        nv_layout.addWidget(self.net_value_display)
        tax_layout.addLayout(nv_layout)

        # Add CGST
        cgst_layout = QHBoxLayout()
        cgst_layout.setSpacing(2)
        cgst_label = QLabel("Add CGST")
        cgst_label.setStyleSheet(self.footer_label_style())
        self.cgst_display = QLabel("0.00")
        self.cgst_display.setStyleSheet(self.footer_value_style())
        cgst_layout.addWidget(cgst_label)
        cgst_layout.addWidget(self.cgst_display)
        tax_layout.addLayout(cgst_layout)

        # Add SGST
        sgst_layout = QHBoxLayout()
        sgst_layout.setSpacing(2)
        sgst_label = QLabel("Add SGST")
        sgst_label.setStyleSheet(self.footer_label_style())
        self.sgst_display = QLabel("0.00")
        self.sgst_display.setStyleSheet(self.footer_value_style())
        sgst_layout.addWidget(sgst_label)
        sgst_layout.addWidget(self.sgst_display)
        tax_layout.addLayout(sgst_layout)

        # Add IGST
        igst_layout = QHBoxLayout()
        igst_layout.setSpacing(2)
        igst_label = QLabel("Add IGST")
        igst_label.setStyleSheet(self.footer_label_style())
        self.igst_display = QLabel("0.00")
        self.igst_display.setStyleSheet(self.footer_value_style())
        igst_layout.addWidget(igst_label)
        igst_layout.addWidget(self.igst_display)
        tax_layout.addLayout(igst_layout)

        # Tax Amount
        ta_layout = QHBoxLayout()
        ta_layout.setSpacing(2)
        ta_label = QLabel("Tax Amount")
        ta_label.setStyleSheet(self.footer_label_style())
        self.tax_amount_display = QLabel("0.00")
        self.tax_amount_display.setStyleSheet(self.footer_value_style())
        ta_layout.addWidget(ta_label)
        ta_layout.addWidget(self.tax_amount_display)
        tax_layout.addLayout(ta_layout)

        # Cess
        cess_layout = QHBoxLayout()
        cess_layout.setSpacing(2)
        cess_label = QLabel("Cess")
        cess_label.setStyleSheet(self.footer_label_style())
        self.cess_display = QLabel("0.00")
        self.cess_display.setStyleSheet(self.footer_value_style())
        cess_layout.addWidget(cess_label)
        cess_layout.addWidget(self.cess_display)
        tax_layout.addLayout(cess_layout)

        tax_layout.addStretch()
        tax_frame.setFixedWidth(175)
        layout.addWidget(tax_frame)

        # ZONE 4 — GRAND TOTAL (label on top, value below)
        gt_zone = QFrame()
        gt_zone.setStyleSheet(self.adjustment_zone_style())
        gt_zone_layout = QVBoxLayout(gt_zone)
        gt_zone_layout.setSpacing(10)
        gt_zone_layout.setContentsMargins(10, 8, 10, 8)
        gt_heading = QLabel("₹ Grand Total")
        gt_heading.setStyleSheet(self.footer_label_style())
        gt_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gt_zone_layout.addWidget(gt_heading, 0)
        
        # Value display (no rupee sign)
        self.final_amount_display = QLabel("0.00")
        self.final_amount_display.setStyleSheet(self.grand_total_green_style())
        self.final_amount_display.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.final_amount_display.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding
        )
        gt_zone_layout.addWidget(self.final_amount_display)
        
        gt_zone.setMinimumWidth(280)
        gt_zone.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        gt_zone.setMinimumHeight(125)
        layout.addWidget(gt_zone, 2)

        # ZONE 4B — RETURN ADJUSTMENT DISPLAY (hidden by default, shown when return linked)
        self.return_adj_zone = QFrame()
        self.return_adj_zone.setStyleSheet(self.return_adjustment_zone_style())
        self.return_adj_zone_layout = QVBoxLayout(self.return_adj_zone)
        self.return_adj_zone_layout.setSpacing(2)
        self.return_adj_zone_layout.setContentsMargins(8, 6, 8, 6)

        self.return_adj_label = QLabel("Return")
        self.return_adj_label.setStyleSheet(self.footer_label_style())
        self.return_adj_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.return_adj_zone_layout.addWidget(self.return_adj_label, 0)

        self.return_adj_amount = QLabel("0.00")
        self.return_adj_amount.setStyleSheet(self.return_amount_red_style())
        self.return_adj_amount.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.return_adj_amount.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred
        )
        self.return_adj_zone_layout.addWidget(self.return_adj_amount, 1)

        self.net_after_return_label = QLabel("Net After Return")
        self.net_after_return_label.setStyleSheet(self.footer_label_style())
        self.net_after_return_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.return_adj_zone_layout.addWidget(self.net_after_return_label, 0)

        self.net_after_return_amount = QLabel("0.00")
        self.net_after_return_amount.setStyleSheet(self.net_after_return_orange_style())
        self.net_after_return_amount.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.net_after_return_amount.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred
        )
        self.return_adj_zone_layout.addWidget(self.net_after_return_amount, 1)

        self.return_adj_zone.setFixedWidth(160)
        self.return_adj_zone.setMinimumHeight(160)
        self.return_adj_zone.setVisible(False)  # Hidden by default
        layout.addWidget(self.return_adj_zone)

        # ZONE 5 — ACTION BUTTONS (after grand total)
        layout.addWidget(action_frame)

        # Hidden fields for backward compatibility
        self.sub_total_input = QLineEdit("0.00")
        self.sub_total_input.setVisible(False)
        self.tax_total_input = QLineEdit("0.00")
        self.tax_total_input.setVisible(False)
        self.adjustments_input = QLineEdit("0.00")
        self.adjustments_input.setVisible(False)
        if not hasattr(self, 'invoice_checkbox'):
            self.invoice_checkbox = create_checkbox()
            self.invoice_checkbox.setVisible(False)

        return frame

    # ==================== STYLES FOR BILLING WORKSTATION ====================

    def header_strip_style(self):
        return theme.entry_header_strip_style()

    def page_title_style(self):
        return theme.entry_page_title_style()

    def invoice_command_strip_style(self):
        return theme.entry_command_strip_style()

    def party_matrix_style(self):
        return theme.entry_section_frame_style()

    def product_strip_style(self):
        return theme.entry_inset_frame_style()

    def status_strip_style(self):
        return theme.entry_section_frame_style()

    def table_zone_style(self):
        return theme.sales_table_zone_style()

    # ---- Frame styles (delegated to ui.theme) ----

    def bottom_panel_style(self):
        return theme.sales_bottom_panel_style()

    def action_frame_style(self):
        return theme.sales_action_frame_style()

    def adj_frame_style(self):
        return theme.sales_adj_frame_style()

    def totals_frame_style(self):
        return theme.sales_totals_frame_style()

    def grand_total_frame_style(self):
        return theme.sales_grand_total_frame_style()

    # ---- Input / label / button / checkbox styles (delegated) ----

    def compact_input_style(self):
        return theme.sales_compact_input_style()

    def barcode_input_style(self):
        return theme.sales_barcode_input_style()

    def billing_table_style(self):
        return theme.editable_table_style()

    def micro_label_style(self):
        return theme.sales_micro_label_style()

    def status_label_style(self):
        return theme.sales_status_label_style()

    def status_value_style(self):
        return theme.sales_status_value_style()

    def status_checkbox_style(self):
        return theme.sales_status_checkbox_style()

    def checkbox_style(self):
        return theme.sales_checkbox_style()

    def nav_box_style(self):
        return theme.sales_nav_box_style()

    def nav_button_style(self):
        return theme.sales_nav_button_style()

    def compact_button_style(self):
        return theme.sales_compact_button_style()

    def modern_3d_icon_button_style(self):
        return theme.sales_modern_3d_icon_button_style()

    def _configure_sales_icon_button(self, button, symbol, tooltip=""):
        """Apply raised 3D fill styling to compact Sales Entry icon actions."""
        button.setText(symbol)
        button.setObjectName("salesIconButton")
        button.setFlat(False)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(28, 28)
        button.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        button.setStyleSheet(self.modern_3d_icon_button_style())
        if tooltip:
            button.setToolTip(tooltip)

    def primary_button_style(self):
        return theme.sales_primary_button_style()

    def danger_button_style(self):
        return theme.sales_danger_button_style()

    def totals_input_style(self):
        return theme.sales_totals_input_style()

    def grand_label_style(self):
        return theme.sales_grand_label_style()

    def grand_amount_style(self):
        return theme.sales_grand_amount_style()

    # ---- Purchase-matched footer zone styles ----

    def footer_panel_style(self):
        return theme.entry_section_frame_style()

    def action_zone_style(self):
        return theme.entry_inset_frame_style()

    def adjustment_zone_style(self):
        return theme.entry_inset_frame_style()

    def tax_zone_style(self):
        return theme.entry_inset_frame_style()

    def footer_label_style(self):
        return theme.entry_footer_label_style()

    def footer_input_style(self):
        return theme.entry_footer_input_style()

    def footer_combo_style(self):
        return theme.entry_footer_input_style()

    def footer_input_readonly_style(self):
        return theme.entry_footer_input_readonly_style()

    def footer_value_style(self):
        return theme.entry_value_style("input_text")

    def footer_final_style(self):
        return theme.entry_info_value_style()

    def grand_total_green_style(self):
        return theme.entry_grand_total_style()

    def save_button_style(self):
        return theme.entry_save_button_style()

    def return_adjustment_zone_style(self):
        colors = theme._theme_colors()
        return f"""
        QFrame {{
            background-color: {colors['panel_bg']};
            border: 2px solid {colors['button_warning']};
            border-radius: 4px;
        }}
        """

    def return_amount_red_style(self):
        """Red style for return amount (negative value)."""
        return """
        QLabel {
            color: #ef4444;
            font-size: 20px;
            font-weight: bold;
            background: transparent;
            border: none;
            padding: 0px;
        }
        """

    def net_after_return_orange_style(self):
        """Orange/yellow style for net after return amount."""
        return """
        QLabel {
            color: #f97316;
            font-size: 24px;
            font-weight: bold;
            background: transparent;
            border: none;
            padding: 0px;
        }
        """