"""
UI building methods for Purchase Return widget.
UI mirrors Purchase Entry exactly - same zones, same fields, same styles.
Function: reverse a purchase (reduce qty from stock, reverse ledger).
"""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QComboBox,
    QDateEdit, QPushButton, QWidget, QTableWidget, QAbstractItemView, QCheckBox
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QDoubleValidator

from ui import theme
from ui.date_formats import configure_qdate_edit
from .theme import GST_STATE_CODES


class PurchaseReturnUIMixin:
    """Mixin containing all UI building and styling methods for Purchase Return."""

    # ==================== ZONE A - PAGE HEADER STRIP ====================

    def build_page_header_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.header_strip_style())
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(0)
        title_label = QLabel("PURCHASE RETURN BILL")
        title_label.setStyleSheet(self.page_title_style())
        layout.addWidget(title_label)
        layout.addStretch()
        return frame

    # ==================== ZONE B - TOP COMMAND STRIP ====================

    def build_return_command_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.invoice_command_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(3)
        layout.setContentsMargins(4, 3, 4, 3)

        # Return No with navigation arrows
        ret_layout = QHBoxLayout()
        ret_layout.setSpacing(2)
        ret_label = QLabel("Return No")
        ret_label.setStyleSheet(self.micro_label_style())
        self.return_no_input = QLineEdit()
        self.return_no_input.setStyleSheet(self.compact_input_style())
        self.return_no_input.setPlaceholderText("Auto")
        self.return_no_input.setFixedWidth(75)
        ret_layout.addWidget(ret_label)
        ret_layout.addWidget(self.return_no_input)

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
        ret_layout.addWidget(nav_container)
        layout.addLayout(ret_layout)

        # Reset button
        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet(self.compact_button_style())
        reset_btn.setFixedWidth(55)
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
        self.date_input.setFixedWidth(95)
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.date_input)
        layout.addLayout(date_layout)

        # Return Type (Cash/Credit)
        type_layout = QHBoxLayout()
        type_layout.setSpacing(2)
        type_label = QLabel("Type")
        type_label.setStyleSheet(self.micro_label_style())
        self.return_type_combo = QComboBox()
        self.return_type_combo.addItems(["Cash", "Credit"])
        self.return_type_combo.setStyleSheet(self.compact_input_style())
        self.return_type_combo.setFixedWidth(85)
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.return_type_combo)
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
        self.party_type_combo.addItems(["", "Creditors", "Debtor", "Both"])
        self._set_default_party_type_to_creditors()
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
        self.due_date_input.setFixedWidth(95)
        due_layout.addWidget(due_label)
        due_layout.addWidget(self.due_date_input)
        layout.addLayout(due_layout)

        layout.addStretch()
        return frame

    # ==================== ZONE C - SUPPLIER INFORMATION MATRIX ====================

    def build_party_information_matrix(self):
        frame = QFrame()
        frame.setStyleSheet(self.party_matrix_style())
        layout = QVBoxLayout(frame)
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        # Row C1: Name, Address, + Creditor button
        row_c1 = QHBoxLayout()
        row_c1.setSpacing(2)

        party_label = QLabel("Name")
        party_label.setStyleSheet(self.micro_label_style())
        self.supplier_name_input = QLineEdit()
        self.supplier_name_input.setStyleSheet(self.compact_input_style())
        self.supplier_name_input.setFixedWidth(380)
        row_c1.addWidget(party_label)
        row_c1.addWidget(self.supplier_name_input)

        addr_label = QLabel("Address")
        addr_label.setStyleSheet(self.micro_label_style())
        self.address_input = QLineEdit()
        self.address_input.setStyleSheet(self.compact_input_style())
        self.address_input.setFixedWidth(320)
        row_c1.addWidget(addr_label)
        row_c1.addWidget(self.address_input)

        self.add_creditor_btn = QPushButton("+ Creditor")
        self.add_creditor_btn.setStyleSheet(self.primary_button_style())
        self.add_creditor_btn.setFixedWidth(75)
        self.add_creditor_btn.clicked.connect(self.add_new_creditor)
        row_c1.addWidget(self.add_creditor_btn)

        self.edit_creditor_btn = QPushButton("Edit Creditor")
        self.edit_creditor_btn.setStyleSheet(self.primary_button_style())
        self.edit_creditor_btn.setFixedWidth(85)
        self.edit_creditor_btn.clicked.connect(self.edit_current_creditor)
        row_c1.addWidget(self.edit_creditor_btn)

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

        state_label = QLabel("State")
        state_label.setStyleSheet(self.micro_label_style())
        self.state_combo = QComboBox()
        self.state_combo.setEditable(True)
        self.state_combo.setStyleSheet(
            self.compact_input_style() + "QComboBox { max-height: 18px; min-height: 18px; }"
        )
        self.state_combo.setFixedWidth(210)
        self.state_combo.addItem("")
        for state in sorted(GST_STATE_CODES.values()):
            self.state_combo.addItem(state)
        self.state_combo.currentTextChanged.connect(self.on_state_changed)
        row_c2.addWidget(state_label)
        row_c2.addWidget(self.state_combo)

        row_c2.addStretch()
        layout.addLayout(row_c2)

        # Row C3: Original Purchase No, Supplier Invoice No, Narration
        row_c3 = QHBoxLayout()
        row_c3.setSpacing(2)

        orig_label = QLabel("Orig. Purchase No")
        orig_label.setStyleSheet(self.micro_label_style())
        self.original_purchase_input = QLineEdit()
        self.original_purchase_input.setStyleSheet(self.compact_input_style())
        self.original_purchase_input.setFixedWidth(150)
        row_c3.addWidget(orig_label)
        row_c3.addWidget(self.original_purchase_input)

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

        barcode_label = QLabel("Barcode")
        barcode_label.setStyleSheet(self.micro_label_style())
        barcode_label.setFixedWidth(58)
        self.barcode_input = QLineEdit()
        self.barcode_input.setStyleSheet(self.barcode_input_style())
        self.barcode_input.setFixedWidth(120)
        self.barcode_input.returnPressed.connect(self.on_barcode_enter)
        layout.addWidget(barcode_label)
        layout.addWidget(self.barcode_input)

        prod_label = QLabel("Product")
        prod_label.setStyleSheet(self.micro_label_style())
        prod_label.setFixedWidth(58)
        self.product_input = QLineEdit()
        self.product_input.setStyleSheet(self.compact_input_style())
        self.product_input.setFixedWidth(300)
        self.product_input.returnPressed.connect(self.on_product_enter)
        layout.addWidget(prod_label)
        layout.addWidget(self.product_input)

        layout.addStretch()
        return frame

    # ==================== ZONE E - BILL OPTIONS / LIVE STATUS STRIP ====================

    def build_bill_options_strip(self):
        frame = QFrame()
        frame.setStyleSheet(self.options_strip_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(3)
        layout.setContentsMargins(4, 3, 4, 3)

        stock_label = QLabel("Stock:")
        stock_label.setStyleSheet(self.micro_label_style())
        self.stock_display = QLabel("0.000")
        self.stock_display.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 11px;")
        layout.addWidget(stock_label)
        layout.addWidget(self.stock_display)

        code_label = QLabel("Code:")
        code_label.setStyleSheet(self.micro_label_style())
        self.code_display = QLabel("")
        self.code_display.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 11px;")
        layout.addWidget(code_label)
        layout.addWidget(self.code_display)

        # Spacer pushes the discount tracker to the far right margin.
        layout.addStretch()

        disc_status_label = QLabel("Discount:")
        disc_status_label.setStyleSheet(self.micro_label_style())
        self.discount_status_display = QLabel("0.00%")
        self.discount_status_display.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")
        layout.addWidget(disc_status_label)
        layout.addWidget(self.discount_status_display)
        return frame

    # ==================== ZONE F - MAIN BILLING TABLE ====================

    def build_items_table(self):
        frame = QFrame()
        frame.setStyleSheet(self.table_zone_style())
        layout = QVBoxLayout(frame)
        layout.setSpacing(0)
        layout.setContentsMargins(4, 4, 4, 4)

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(15)
        self.items_table.setHorizontalHeaderLabels([
            "SL", "Sale Rate", "Product", "HSN",
            "CGST%", "SGST%", "IGST%", "CESS%",
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
            QAbstractItemView.EditKeyPressed
        )

        # Column index constants — mirror purchase entry
        self.COL_SL = 0
        self.COL_SALE_RATE = 1
        self.COL_PRODUCT = 2
        self.COL_HSN = 3
        self.COL_CGST = 4
        self.COL_SGST = 5
        self.COL_IGST = 6
        self.COL_CESS = 7
        self.COL_RATE = 8
        self.COL_QTY = 9
        self.COL_GROSS = 10
        self.COL_DISC = 11
        self.COL_NET = 12
        self.COL_TAX = 13
        self.COL_TOTAL = 14

        self.items_table.setColumnWidth(self.COL_SL, 35)
        self.items_table.setColumnWidth(self.COL_SALE_RATE, 65)
        self.items_table.setColumnWidth(self.COL_PRODUCT, 250)
        self.items_table.setColumnWidth(self.COL_HSN, 80)
        self.items_table.setColumnWidth(self.COL_CGST, 50)
        self.items_table.setColumnWidth(self.COL_SGST, 50)
        self.items_table.setColumnWidth(self.COL_IGST, 50)
        self.items_table.setColumnWidth(self.COL_CESS, 50)
        self.items_table.setColumnWidth(self.COL_RATE, 70)
        self.items_table.setColumnWidth(self.COL_QTY, 60)
        self.items_table.setColumnWidth(self.COL_GROSS, 80)
        self.items_table.setColumnWidth(self.COL_DISC, 60)
        self.items_table.setColumnWidth(self.COL_NET, 80)
        self.items_table.setColumnWidth(self.COL_TAX, 70)
        self.items_table.setColumnWidth(self.COL_TOTAL, 80)

        layout.addWidget(self.items_table)
        return frame

    # ==================== ZONE G+H - LOWER CONTROL PANEL ====================

    def build_lower_control_panel(self):
        frame = QFrame()
        frame.setStyleSheet(self.footer_panel_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # Action buttons are added last so the totals deck and buttons sit on
        # the right side, matching Purchase Entry.
        action_frame = QFrame()
        action_frame.setStyleSheet(self.action_zone_style())
        action_layout = QVBoxLayout(action_frame)
        action_layout.setSpacing(3)
        action_layout.setContentsMargins(4, 4, 4, 4)

        def _safe_button(button):
            button.setAutoDefault(False)
            button.setDefault(False)
            action_layout.addWidget(button)

        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet(self.save_button_style())
        self.save_btn.clicked.connect(self.save_return)
        _safe_button(self.save_btn)

        self.print_btn = QPushButton("Print")
        self.print_btn.setStyleSheet(self.compact_button_style())
        self.print_btn.clicked.connect(self.print_return)
        _safe_button(self.print_btn)

        self.reset_all_btn = QPushButton("Reset All")
        self.reset_all_btn.setStyleSheet(self.compact_button_style())
        self.reset_all_btn.clicked.connect(self.clear_form)
        _safe_button(self.reset_all_btn)

        self.remove_item_btn = QPushButton("Remove Item")
        self.remove_item_btn.setStyleSheet(self.danger_button_style())
        self.remove_item_btn.clicked.connect(self.remove_current_item)
        _safe_button(self.remove_item_btn)

        self.remove_return_btn = QPushButton("Remove Return")
        self.remove_return_btn.setStyleSheet(self.danger_button_style())
        self.remove_return_btn.clicked.connect(self.delete_return)
        _safe_button(self.remove_return_btn)

        action_frame.setFixedWidth(135)
        layout.addStretch(1)

        # Zone 2 — Adjustment / Payment block
        adj_frame = QFrame()
        adj_frame.setStyleSheet(self.adjustment_zone_style())
        adj_layout = QVBoxLayout(adj_frame)
        adj_layout.setSpacing(2)
        adj_layout.setContentsMargins(6, 6, 6, 6)

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
        self.round_off_input.textChanged.connect(self.on_round_off_changed)
        ro_layout.addWidget(ro_label)
        ro_layout.addWidget(self.round_off_input)
        adj_layout.addLayout(ro_layout)

        disc_layout = QHBoxLayout()
        disc_layout.setSpacing(2)
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
        self.discount_total_input.setStyleSheet(self.footer_discount_box_style())
        self.discount_total_input.setText("0.00")
        self.discount_total_input.setValidator(QDoubleValidator())
        self.discount_total_input.setAlignment(Qt.AlignRight)
        self.discount_total_input.textChanged.connect(self.on_footer_discount_changed)
        disc_layout.addLayout(disc_label_vbox)
        disc_layout.addWidget(self.discount_total_input)
        adj_layout.addLayout(disc_layout)

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

        ap_layout = QHBoxLayout()
        ap_layout.setSpacing(2)
        ap_label = QLabel("Amt Refunded")
        ap_label.setStyleSheet(self.footer_label_style())
        ap_label.setFixedWidth(100)
        self.amount_refunded_input = QLineEdit()
        self.amount_refunded_input.setStyleSheet(self.footer_input_style())
        self.amount_refunded_input.setFixedWidth(80)
        self.amount_refunded_input.setText("0.00")
        self.amount_refunded_input.textChanged.connect(self.on_amount_refunded_changed)
        ap_layout.addWidget(ap_label)
        ap_layout.addWidget(self.amount_refunded_input)
        adj_layout.addLayout(ap_layout)

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

        # Zone 3 — Tax summary block
        tax_frame = QFrame()
        tax_frame.setStyleSheet(self.tax_zone_style())
        tax_layout = QVBoxLayout(tax_frame)
        tax_layout.setSpacing(2)
        tax_layout.setContentsMargins(6, 6, 6, 6)

        nv_layout = QHBoxLayout()
        nv_layout.setSpacing(2)
        nv_label = QLabel("Net Value")
        nv_label.setStyleSheet(self.footer_label_style())
        self.net_value_display = QLabel("0.00")
        self.net_value_display.setStyleSheet(self.footer_value_style())
        nv_layout.addWidget(nv_label)
        nv_layout.addWidget(self.net_value_display)
        tax_layout.addLayout(nv_layout)

        cgst_row = QHBoxLayout()
        cgst_row.setSpacing(2)
        cgst_label = QLabel("Add CGST")
        cgst_label.setStyleSheet(self.footer_label_style())
        self.cgst_display = QLabel("0.00")
        self.cgst_display.setStyleSheet(self.footer_value_style())
        cgst_row.addWidget(cgst_label)
        cgst_row.addWidget(self.cgst_display)
        tax_layout.addLayout(cgst_row)

        sgst_row = QHBoxLayout()
        sgst_row.setSpacing(2)
        sgst_label = QLabel("Add SGST")
        sgst_label.setStyleSheet(self.footer_label_style())
        self.sgst_display = QLabel("0.00")
        self.sgst_display.setStyleSheet(self.footer_value_style())
        sgst_row.addWidget(sgst_label)
        sgst_row.addWidget(self.sgst_display)
        tax_layout.addLayout(sgst_row)

        igst_row = QHBoxLayout()
        igst_row.setSpacing(2)
        igst_label = QLabel("Add IGST")
        igst_label.setStyleSheet(self.footer_label_style())
        self.igst_display = QLabel("0.00")
        self.igst_display.setStyleSheet(self.footer_value_style())
        igst_row.addWidget(igst_label)
        igst_row.addWidget(self.igst_display)
        tax_layout.addLayout(igst_row)

        ta_row = QHBoxLayout()
        ta_row.setSpacing(2)
        ta_label = QLabel("Tax Amount")
        ta_label.setStyleSheet(self.footer_label_style())
        self.tax_amount_display = QLabel("0.00")
        self.tax_amount_display.setStyleSheet(self.footer_value_style())
        ta_row.addWidget(ta_label)
        ta_row.addWidget(self.tax_amount_display)
        tax_layout.addLayout(ta_row)

        cess_row = QHBoxLayout()
        cess_row.setSpacing(2)
        cess_label = QLabel("Cess")
        cess_label.setStyleSheet(self.footer_label_style())
        self.cess_display = QLabel("0.00")
        self.cess_display.setStyleSheet(self.footer_value_style())
        cess_row.addWidget(cess_label)
        cess_row.addWidget(self.cess_display)
        tax_layout.addLayout(cess_row)

        gt2_row = QHBoxLayout()
        gt2_row.setSpacing(2)
        gt2_label = QLabel("Grand Total")
        gt2_label.setStyleSheet(self.footer_label_style())
        self.final_amount_display = QLabel("₹ 0.00")
        self.final_amount_display.setStyleSheet(self.grand_total_green_style())
        gt2_row.addWidget(gt2_label)
        gt2_row.addWidget(self.final_amount_display)
        tax_layout.addLayout(gt2_row)

        tax_frame.setFixedWidth(200)
        layout.addWidget(tax_frame)

        # Action buttons pinned to the far right of the footer row.
        layout.addWidget(action_frame)

        self.sub_total_input = QLineEdit()
        self.sub_total_input.setVisible(False)
        self.tax_total_input = QLineEdit()
        self.tax_total_input.setVisible(False)

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