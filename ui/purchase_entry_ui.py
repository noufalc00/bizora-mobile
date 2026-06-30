"""
UI building methods for Purchase Entry widget.
Contains all UI layout building methods and style helpers.
"""

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QDoubleValidator

from ui import theme
from ui.checkbox_style import create_checkbox
from ui.date_formats import configure_qdate_edit
from .theme import GST_STATE_CODES


class PurchaseEntryUIMixin:
    """Mixin class containing all UI building and styling methods for Purchase Entry."""
    
    # ==================== ZONE A - PAGE HEADER STRIP ====================

    def build_page_header_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.header_strip_style())
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(0)

        title_label = QLabel("PURCHASE BILL")
        title_label.setStyleSheet(self.page_title_style())
        layout.addWidget(title_label)
        layout.addStretch()
        return frame

    # ==================== ZONE B - TOP PURCHASE COMMAND STRIP ====================

    def build_purchase_command_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.invoice_command_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(3)
        layout.setContentsMargins(4, 3, 4, 3)

        # Purchase No with navigation buttons in compact box
        pur_layout = QHBoxLayout()
        pur_layout.setSpacing(2)
        pur_label = QLabel("Purchase")
        pur_label.setStyleSheet(self.micro_label_style())
        self.purchase_no_input = QLineEdit()
        self.purchase_no_input.setStyleSheet(self.compact_input_style())
        self.purchase_no_input.setPlaceholderText("Auto")
        self.purchase_no_input.setFixedWidth(75)
        pur_layout.addWidget(pur_label)
        pur_layout.addWidget(self.purchase_no_input)

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

        pur_layout.addWidget(nav_container)

        layout.addLayout(pur_layout)

        # Reset button
        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet(self.compact_button_style())
        reset_btn.setFixedWidth(55)
        reset_btn.clicked.connect(self.clear_form)
        layout.addWidget(reset_btn)

        self.import_po_btn = QPushButton("Import PO")
        self.import_po_btn.setStyleSheet(theme.entry_secondary_action_button_style())
        self.import_po_btn.setFixedWidth(72)
        self.import_po_btn.clicked.connect(self.open_import_po_dialog)
        layout.addWidget(self.import_po_btn)

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
        self.date_input.setFixedWidth(110)
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.date_input)
        layout.addLayout(date_layout)

        # Purchase Type
        type_layout = QHBoxLayout()
        type_layout.setSpacing(2)
        type_label = QLabel("Type")
        type_label.setStyleSheet(self.micro_label_style())
        self.purchase_type_combo = QComboBox()
        self.purchase_type_combo.addItems(["Cash", "Credit"])
        self.purchase_type_combo.setStyleSheet(self.compact_input_style())
        self.purchase_type_combo.setFixedWidth(85)
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.purchase_type_combo)
        layout.addLayout(type_layout)

        # Series
        ser_layout = QHBoxLayout()
        ser_layout.setSpacing(2)
        ser_label = QLabel("Series")
        ser_label.setStyleSheet(self.micro_label_style())
        self.series_input = QLineEdit()
        self.series_input.setStyleSheet(self.compact_input_style())
        self.series_input.setFixedWidth(65)
        ser_layout.addWidget(ser_label)
        ser_layout.addWidget(self.series_input)
        layout.addLayout(ser_layout)

        # Nature
        nat_layout = QHBoxLayout()
        nat_layout.setSpacing(2)
        nat_label = QLabel("Nature")
        nat_label.setStyleSheet(self.micro_label_style())
        self.nature_combo = QComboBox()
        self.nature_combo.addItems(["Local", "Inter-state"])
        self.nature_combo.setStyleSheet(self.compact_input_style())
        self.nature_combo.setFixedWidth(115)
        nat_layout.addWidget(nat_label)
        nat_layout.addWidget(self.nature_combo)
        layout.addLayout(nat_layout)

        # Party Type
        pty_layout = QHBoxLayout()
        pty_layout.setSpacing(2)
        pty_label = QLabel("Party")
        pty_label.setStyleSheet(self.micro_label_style())
        self.party_type_combo = QComboBox()
        self.party_type_combo.addItems(["", "Creditor", "Debtor", "Both"])
        self.party_type_combo.setStyleSheet(self.compact_input_style())
        self.party_type_combo.setFixedWidth(115)
        pty_layout.addWidget(pty_label)
        pty_layout.addWidget(self.party_type_combo)
        layout.addLayout(pty_layout)

        # Due Date
        due_layout = QHBoxLayout()
        due_layout.setSpacing(2)
        due_label = QLabel("Due")
        due_label.setStyleSheet(self.micro_label_style())
        self.due_date_input = QDateEdit()
        configure_qdate_edit(self.due_date_input)
        self.due_date_input.setDate(QDate.currentDate().addDays(30))
        self.due_date_input.setCalendarPopup(True)
        self.due_date_input.setStyleSheet(self.compact_input_style())
        self.due_date_input.setFixedWidth(110)
        due_layout.addWidget(due_label)
        due_layout.addWidget(self.due_date_input)
        layout.addLayout(due_layout)

        # Apply dark calendar theme + today highlight to both date pickers.
        self._style_date_calendar(self.date_input)
        self._style_date_calendar(self.due_date_input)

        layout.addStretch()
        return frame

    # ==================== ZONE C - CREDITOR / SUPPLIER INFORMATION MATRIX ====================

    def build_creditor_information_matrix(self):
        frame = QFrame()
        frame.setStyleSheet(self.party_matrix_style())
        layout = QVBoxLayout(frame)
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        # Row C1: Name, Address, + Creditors button, Return button
        row_c1 = QHBoxLayout()
        row_c1.setSpacing(2)

        party_label = QLabel("Name")
        party_label.setStyleSheet(self.micro_label_style())
        self.creditor_name_input = QLineEdit()
        self.creditor_name_input.setStyleSheet(self.compact_input_style())
        self.creditor_name_input.setFixedWidth(380)
        self.creditor_name_input.textChanged.connect(self.on_creditor_name_changed)
        row_c1.addWidget(party_label)
        row_c1.addWidget(self.creditor_name_input)

        # Party short Code (auto-filled from master, editable, local-only override).
        code_label = QLabel("Code")
        code_label.setStyleSheet(self.micro_label_style())
        self.code_input = QLineEdit()
        self.code_input.setStyleSheet(self.compact_input_style())
        self.code_input.setFixedWidth(70)
        self.code_input.setMaxLength(7)
        row_c1.addWidget(code_label)
        row_c1.addWidget(self.code_input)

        addr_label = QLabel("Address")
        addr_label.setStyleSheet(self.micro_label_style())
        self.address_input = QLineEdit()
        self.address_input.setStyleSheet(self.compact_input_style())
        self.address_input.setFixedWidth(320)
        self.address_input.textChanged.connect(self.on_address_changed)
        row_c1.addWidget(addr_label)
        row_c1.addWidget(self.address_input)

        self.add_creditor_btn = QPushButton("+ Creditor")
        self.add_creditor_btn.setStyleSheet(self.primary_button_style())
        self.add_creditor_btn.setFixedWidth(75)
        self.add_creditor_btn.clicked.connect(self.open_creditor_page)
        row_c1.addWidget(self.add_creditor_btn)

        ret_btn = QPushButton("Return")
        ret_btn.setStyleSheet(self.primary_button_style())
        ret_btn.setFixedWidth(60)
        row_c1.addWidget(ret_btn)

        self.purchase_checkbox = create_checkbox("Entry with Specific Purchase No.")
        row_c1.addWidget(self.purchase_checkbox)

        row_c1.addStretch()
        layout.addLayout(row_c1)

        # Row C2: Mobile, GSTIN, State
        row_c2 = QHBoxLayout()
        row_c2.setSpacing(2)

        mobile_label = QLabel("Mobile")
        mobile_label.setStyleSheet(self.micro_label_style())
        self.mobile_input = QLineEdit()
        self.mobile_input.setStyleSheet(self.compact_input_style())
        self.mobile_input.setFixedWidth(110)
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

        # State
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

        # Row C3: Supplier Invoice No, Narration
        row_c3 = QHBoxLayout()
        row_c3.setSpacing(2)
        
        inv_label = QLabel("Invoice No")
        inv_label.setStyleSheet(self.micro_label_style())
        self.supplier_invoice_input = QLineEdit()
        self.supplier_invoice_input.setStyleSheet(self.compact_input_style())
        self.supplier_invoice_input.setFixedWidth(150)
        row_c3.addWidget(inv_label)
        row_c3.addWidget(self.supplier_invoice_input)
        
        narr_label = QLabel("Narration")
        narr_label.setStyleSheet(self.micro_label_style())
        self.narration_input = QLineEdit()
        self.narration_input.setStyleSheet(self.compact_input_style())
        row_c3.addWidget(narr_label)
        row_c3.addWidget(self.narration_input)
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

        # Barcode input (no checkbox)
        code_layout = QHBoxLayout()
        code_layout.setSpacing(1)
        barcode_label = QLabel("Barcode")
        barcode_label.setStyleSheet(self.micro_label_style())
        barcode_label.setFixedWidth(58)
        self.barcode_input = QLineEdit()
        self.barcode_input.setStyleSheet(self.barcode_input_style())
        self.barcode_input.setFixedWidth(120)
        code_layout.addWidget(barcode_label)
        code_layout.addWidget(self.barcode_input)
        layout.addLayout(code_layout)

        # Product input (no Rate field)
        prod_layout = QHBoxLayout()
        prod_layout.setSpacing(1)
        prod_label = QLabel("Product")
        prod_label.setStyleSheet(self.micro_label_style())
        prod_label.setFixedWidth(58)
        self.product_input = QLineEdit()
        self.product_input.setStyleSheet(self.compact_input_style())
        self.product_input.setFixedWidth(300)
        prod_layout.addWidget(prod_label)
        prod_layout.addWidget(self.product_input)

        layout.addLayout(prod_layout)

        # Get Barcode launcher (barcode printing / thermal generation hook).
        self.get_barcode_btn = QPushButton("Get Barcode")
        self.get_barcode_btn.setStyleSheet(self.primary_button_style())
        self.get_barcode_btn.setFixedWidth(95)
        self.get_barcode_btn.clicked.connect(self.open_barcode_printing_page)
        layout.addWidget(self.get_barcode_btn)

        layout.addStretch()

        return frame

    # ==================== ZONE E - BILL OPTIONS / LIVE STATUS STRIP ====================

    def build_bill_options_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.options_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(3)
        layout.setContentsMargins(4, 3, 4, 3)

        # Stock display
        stock_label = QLabel("Stock:")
        stock_label.setStyleSheet(self.micro_label_style())
        self.stock_display = QLabel("0.000")
        self.stock_display.setStyleSheet(theme.entry_value_style("accent_highlight"))
        layout.addWidget(stock_label)
        layout.addWidget(self.stock_display)

        # Code/Barcode display
        code_label = QLabel("Code:")
        code_label.setStyleSheet(self.micro_label_style())
        self.code_display = QLabel("")
        self.code_display.setStyleSheet(theme.entry_value_style("input_text"))
        layout.addWidget(code_label)
        layout.addWidget(self.code_display)

        # Spacer pushes the discount tracker to the far right margin.
        layout.addStretch()

        # Live discount tracker for the active row (equivalent percentage),
        # pinned to the right-hand side of the status line.
        disc_status_label = QLabel("Discount:")
        disc_status_label.setStyleSheet(self.micro_label_style())
        self.discount_status_display = QLabel("0.00%")
        self.discount_status_display.setStyleSheet(theme.entry_info_value_style())
        layout.addWidget(disc_status_label)
        layout.addWidget(self.discount_status_display)

        return frame

    # ==================== ZONE F - MAIN BILLING TABLE ZONE ====================

    def build_billing_table_zone(self):
        frame = QFrame()
        frame.setStyleSheet(self.table_zone_style())
        layout = QVBoxLayout(frame)
        layout.setSpacing(0)
        layout.setContentsMargins(4, 4, 4, 4)

        # Table with headers
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(15)
        self.items_table.setHorizontalHeaderLabels(["SL", "Sales Rate", "Product", "HSN", "CGST%", "SGST%", "IGST%", "CESS%", "Rate", "Qty", "Gross", "Disc", "Net", "Tax", "Total"])
        self.items_table.setStyleSheet(self.table_style())
        self.items_table.horizontalHeader().setStyleSheet(self.table_header_style())
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setAlternatingRowColors(False)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.items_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.items_table.setEditTriggers(
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.EditKeyPressed |
            QAbstractItemView.AnyKeyPressed
        )

        # Set column widths
        self.items_table.setColumnWidth(0, 35)   # SL
        self.items_table.setColumnWidth(1, 65)   # Sales Rate
        self.items_table.setColumnWidth(2, 250)  # Product
        self.items_table.setColumnWidth(3, 80)   # HSN
        self.items_table.setColumnWidth(4, 50)   # CGST%
        self.items_table.setColumnWidth(5, 50)   # SGST%
        self.items_table.setColumnWidth(6, 50)   # IGST%
        self.items_table.setColumnWidth(7, 50)   # CESS%
        self.items_table.setColumnWidth(8, 70)   # Rate
        self.items_table.setColumnWidth(9, 60)   # Qty
        self.items_table.setColumnWidth(10, 80)  # Gross
        self.items_table.setColumnWidth(11, 60)  # Disc
        self.items_table.setColumnWidth(12, 80)  # Net
        self.items_table.setColumnWidth(13, 70)  # Tax
        self.items_table.setColumnWidth(14, 80)  # Total

        layout.addWidget(self.items_table)
        return frame

    # ==================== ZONE G + H - LOWER CONTROL PANEL WITH TOTALS ====================

    def build_lower_control_panel(self):
        """Override to build Purchase Entry specific footer layout."""
        frame = QFrame()
        frame.setStyleSheet(self.footer_panel_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # ZONE 1 — ACTION BUTTONS (TOP-ALIGNED)
        action_frame = QFrame()
        action_frame.setStyleSheet(self.action_zone_style())
        action_layout = QVBoxLayout(action_frame)
        action_layout.setSpacing(3)
        action_layout.setContentsMargins(4, 4, 4, 4)

        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet(self.save_button_style())
        self.save_btn.clicked.connect(self.save)
        action_layout.addWidget(self.save_btn)

        self.print_btn = QPushButton("Print")
        self.print_btn.setStyleSheet(self.compact_button_style())
        self.print_btn.clicked.connect(self.print_invoice)
        action_layout.addWidget(self.print_btn)

        self.reset_all_btn = QPushButton("Reset All")
        self.reset_all_btn.setStyleSheet(self.compact_button_style())
        self.reset_all_btn.clicked.connect(self.clear_form)
        action_layout.addWidget(self.reset_all_btn)

        self.remove_item_btn = QPushButton("Remove Item")
        self.remove_item_btn.setStyleSheet(self.danger_button_style())
        self.remove_item_btn.clicked.connect(self.confirm_remove_item)
        action_layout.addWidget(self.remove_item_btn)

        self.remove_purchase_btn = QPushButton("Remove Purchase")
        self.remove_purchase_btn.setStyleSheet(self.danger_button_style())
        self.remove_purchase_btn.clicked.connect(self.confirm_remove_purchase)
        action_layout.addWidget(self.remove_purchase_btn)

        action_frame.setFixedWidth(135)
        # Action buttons are added LAST so the whole control deck (totals + actions)
        # is pushed to the right-hand side, beneath the Grand Total blocks.
        layout.addStretch(1)

        # ZONE 2 — ADJUSTMENT / PAYMENT BLOCK
        adj_frame = QFrame()
        adj_frame.setStyleSheet(self.adjustment_zone_style())
        adj_layout = QVBoxLayout(adj_frame)
        adj_layout.setSpacing(2)
        adj_layout.setContentsMargins(6, 6, 6, 6)

        # Grand Total
        gt_layout = QHBoxLayout()
        gt_layout.setSpacing(2)
        gt_label = QLabel("Grand Total")
        gt_label.setStyleSheet(self.footer_label_style())
        gt_label.setFixedWidth(100)
        self.grand_total_input = QLineEdit()
        self.grand_total_input.setStyleSheet(self.grand_total_green_style())
        self.grand_total_input.setReadOnly(True)
        self.grand_total_input.setAlignment(Qt.AlignRight)
        gt_layout.addWidget(gt_label)
        gt_layout.addWidget(self.grand_total_input)
        adj_layout.addLayout(gt_layout)

        # Round Off
        ro_layout = QHBoxLayout()
        ro_layout.setSpacing(2)
        ro_label = QLabel("Round Off")
        ro_label.setStyleSheet(self.footer_label_style())
        ro_label.setFixedWidth(100)
        self.round_off_input = QLineEdit()
        self.round_off_input.setStyleSheet(self.footer_input_style())
        self.round_off_input.setText("0.00")
        self.round_off_input.setValidator(QDoubleValidator())
        self.round_off_input.setAlignment(Qt.AlignRight)
        # Round Off control: checked by default → Grand Total snaps to nearest whole.
        self.round_off_checkbox = create_checkbox(variant="compact")
        self.round_off_checkbox.setFixedSize(14, 14)
        self.round_off_checkbox.setChecked(True)
        self.round_off_checkbox.setToolTip("Round Grand Total to the nearest whole number")
        ro_layout.addWidget(ro_label)
        ro_layout.addWidget(self.round_off_input)
        ro_layout.addWidget(self.round_off_checkbox)
        adj_layout.addLayout(ro_layout)

        # Purchase Expense
        pe_layout = QHBoxLayout()
        pe_layout.setSpacing(2)
        pe_label = QLabel("Purchase Expense")
        pe_label.setStyleSheet(self.footer_label_style())
        pe_label.setFixedWidth(100)
        self.purchase_expense_input = QLineEdit()
        # Same green-on-dark box style as the Discount field for visual parity.
        self.purchase_expense_input.setStyleSheet(self.footer_discount_box_style())
        self.purchase_expense_input.setText("0")
        self.purchase_expense_input.setAlignment(Qt.AlignRight)
        pe_layout.addWidget(pe_label)
        pe_layout.addWidget(self.purchase_expense_input)
        adj_layout.addLayout(pe_layout)

        # Freight (hidden for now, can be added to UI later if needed)
        self.freight_input = QLineEdit()
        self.freight_input.setVisible(False)
        self.freight_input.setText("0")

        # Discount (footer-level). Down Arrow inside this box converts the typed
        # number into a percentage of the pre-discount base, mirroring Sales Entry.
        disc_layout = QHBoxLayout()
        disc_layout.setSpacing(2)
        # Label column stacks the "Discount" caption above a tiny percent marker so
        # the percent indicator sits OUTSIDE the input box (mirrors Sales Entry).
        disc_label_vbox = QVBoxLayout()
        disc_label_vbox.setSpacing(0)
        disc_label_vbox.setContentsMargins(0, 0, 0, 0)
        disc_label = QLabel("Discount")
        disc_label.setStyleSheet(self.footer_label_style())
        disc_label.setFixedWidth(100)
        self.discount_percent_label = QLabel("")
        self.discount_percent_label.setStyleSheet(
            "QLabel { color: #8ab4f8; font-size: 7px; padding: 0px; margin: 0px; }"
        )
        self.discount_percent_label.setFixedWidth(100)
        disc_label_vbox.addWidget(disc_label)
        disc_label_vbox.addWidget(self.discount_percent_label)
        self.discount_total_input = QLineEdit()
        self.discount_total_input.setObjectName("footer_discount_field")
        # Green-on-dark box style (matches Purchase Expense for visual parity).
        self.discount_total_input.setStyleSheet(self.footer_discount_box_style())
        self.discount_total_input.setText("0.00")
        self.discount_total_input.setValidator(QDoubleValidator())
        self.discount_total_input.setAlignment(Qt.AlignRight)
        disc_layout.addLayout(disc_label_vbox)
        disc_layout.addWidget(self.discount_total_input)
        adj_layout.addLayout(disc_layout)

        # Net Amount
        na_layout = QHBoxLayout()
        na_layout.setSpacing(2)
        na_label = QLabel("Net Amount")
        na_label.setStyleSheet(self.footer_label_style())
        na_label.setFixedWidth(100)
        self.net_amount_display = QLabel("0.00")
        self.net_amount_display.setStyleSheet(self.footer_value_style())
        na_layout.addWidget(na_label)
        na_layout.addWidget(self.net_amount_display)
        adj_layout.addLayout(na_layout)

        # Amount Paid
        ap_layout = QHBoxLayout()
        ap_layout.setSpacing(2)
        ap_label = QLabel("Amount Paid")
        ap_label.setStyleSheet(self.footer_label_style())
        ap_label.setFixedWidth(100)
        self.amt_paid_input = QLineEdit()
        self.amt_paid_input.setStyleSheet(self.footer_input_style())
        self.amt_paid_input.setFixedWidth(80)
        self.amt_paid_input.textChanged.connect(self.on_amt_paid_edited)
        ap_layout.addWidget(ap_label)
        ap_layout.addWidget(self.amt_paid_input)
        adj_layout.addLayout(ap_layout)

        # Balance
        bal_layout = QHBoxLayout()
        bal_layout.setSpacing(2)
        bal_label = QLabel("Balance")
        bal_label.setStyleSheet(self.footer_label_style())
        bal_label.setFixedWidth(100)
        self.balance_display = QLabel("0.00")
        self.balance_display.setStyleSheet(self.footer_value_style())
        bal_layout.addWidget(bal_label)
        bal_layout.addWidget(self.balance_display)
        adj_layout.addLayout(bal_layout)

        adj_frame.setFixedWidth(200)
        layout.addWidget(adj_frame)

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

        # Grand Total (bottom of tax zone)
        gt2_layout = QHBoxLayout()
        gt2_layout.setSpacing(2)
        gt2_label = QLabel("Grand Total")
        gt2_label.setStyleSheet(self.footer_label_style())
        self.final_amount_display = QLabel("₹ 0.00")
        self.final_amount_display.setStyleSheet(self.grand_total_green_style())
        gt2_layout.addWidget(gt2_label)
        gt2_layout.addWidget(self.final_amount_display)
        tax_layout.addLayout(gt2_layout)

        tax_frame.setFixedWidth(200)
        layout.addWidget(tax_frame)

        # Action buttons pinned to the far right of the footer row.
        layout.addWidget(action_frame)

        # Hidden fields for backward compatibility
        self.sub_total_input = QLineEdit()
        self.sub_total_input.setVisible(False)
        self.tax_total_input = QLineEdit()
        self.tax_total_input.setVisible(False)

        return frame

    def _style_date_calendar(self, date_edit):
        """Apply the dark theme to a QDateEdit calendar popup.

        Task 9: previous/next month selectors render as crisp white arrows.
        Task 10: today's date cell paints with a deep blue (#0056b3) background
        and bold white numerals so it is instantly identifiable.
        """
        from ui.date_formats import configure_qdate_edit

        configure_qdate_edit(date_edit, calendar_popup=False)
        from PySide6.QtWidgets import QToolButton
        from PySide6.QtCore import Qt as _Qt

        calendar = date_edit.calendarWidget()
        if calendar is None:
            return

        calendar.setStyleSheet(theme.entry_calendar_style())

        # Use crisp text characters for the month selectors so they render
        # identically on Windows 10 and Windows 11 (Win10 native arrows are
        # bulkier). Icons are cleared above; arrowType is forced off so only the
        # "<" / ">" glyphs show.
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

    # ==================== STYLE METHODS ====================

    def header_strip_style(self):
        return theme.entry_header_strip_style()

    def page_title_style(self):
        return theme.entry_page_title_label_style()

    def invoice_command_strip_style(self):
        return theme.entry_command_strip_style()

    def micro_label_style(self):
        return theme.sales_micro_label_style()

    def compact_input_style(self):
        return theme.sales_compact_input_style()

    def barcode_input_style(self):
        return theme.sales_barcode_input_style()

    def nav_box_style(self):
        return theme.entry_nav_box_style()

    def nav_button_style(self):
        return theme.sales_nav_button_style()

    def compact_button_style(self):
        return theme.sales_compact_button_style()

    def primary_button_style(self):
        return theme.sales_primary_button_style()

    def danger_button_style(self):
        return theme.sales_danger_button_style()

    def checkbox_style(self):
        return theme.sales_checkbox_style()

    def party_matrix_style(self):
        return theme.entry_section_frame_style()

    def product_strip_style(self):
        return theme.entry_inset_frame_style()

    def options_strip_style(self):
        return theme.entry_section_frame_style()

    def table_zone_style(self):
        return theme.entry_inset_frame_style()

    def table_style(self):
        return theme.editable_table_style()

    def table_header_style(self):
        return theme.entry_table_header_style()

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
        return theme.sales_compact_input_style()

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

    def save_button_style(self):
        return theme.entry_save_button_style()