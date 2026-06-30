"""
Popup components for Purchase Return widget.
Contains party and product selection popups.
"""

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt

from ui import theme
from ui.table_header_utils import apply_adjustable_table_columns


class PurchaseReturnPopupMixin:
    """Mixin class containing popup methods for Purchase Return."""

    def show_party_popup(self):
        """Show party selection popup."""
        popup = QDialog(self)
        popup.setWindowTitle("Select Supplier")
        popup.setFixedSize(500, 400)
        popup.setStyleSheet(theme.entry_picker_dialog_style())

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 10, 10, 10)

        # Search input
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_input = QLineEdit()
        search_input.setPlaceholderText("Type to search...")
        search_layout.addWidget(search_label)
        search_layout.addWidget(search_input)
        layout.addLayout(search_layout)

        # Party type filter
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Type:")
        type_filter = QComboBox()
        type_filter.addItems(["All", "Creditor", "Debtor", "Both"])
        type_filter.setCurrentText("Creditor")
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(type_filter)
        layout.addLayout(filter_layout)

        # Party table
        party_table = QTableWidget()
        party_table.setColumnCount(4)
        party_table.setHorizontalHeaderLabels(["Name", "Mobile", "Type", "GSTIN"])
        party_table.horizontalHeader().setStretchLastSection(False)
        apply_adjustable_table_columns(party_table, auto_size=False)
        party_table.verticalHeader().setVisible(False)
        party_table.setSelectionBehavior(QTableWidget.SelectRows)
        party_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(party_table)

        # Load parties
        self.load_parties_to_table(party_table)

        # Search functionality
        def filter_parties():
            search_text = search_input.text().lower()
            type_text = type_filter.currentText()
            stored_type_text = "Debitor" if type_text == "Debtor" else type_text
            for row in range(party_table.rowCount()):
                name_item = party_table.item(row, 0)
                mobile_item = party_table.item(row, 1)
                type_item = party_table.item(row, 2)
                name = name_item.text().lower() if name_item else ""
                mobile = mobile_item.text().lower() if mobile_item else ""
                party_type = type_item.data(Qt.UserRole) if type_item else ""
                match_search = not search_text or search_text in name or search_text in mobile
                match_type = type_text == "All" or stored_type_text == party_type
                party_table.setRowHidden(row, not (match_search and match_type))

        search_input.textChanged.connect(filter_parties)
        type_filter.currentTextChanged.connect(filter_parties)
        filter_parties()  # Apply initial Creditor filter

        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(popup.reject)

        select_btn = QPushButton("Select")
        select_btn.setStyleSheet(theme.entry_select_button_style())
        select_btn.clicked.connect(lambda: self.on_party_selected(party_table, popup))

        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(select_btn)
        layout.addLayout(button_layout)

        # Double click to select
        party_table.doubleClicked.connect(lambda: self.on_party_selected(party_table, popup))

        popup.exec()

    def load_parties_to_table(self, table):
        """Load parties into table from database."""
        company_id = self.get_current_company_id()
        if not company_id:
            return

        parties = self.db.get_parties_by_company(company_id)
        table.setRowCount(0)

        for party in parties:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(party.get('name', '')))
            table.setItem(row, 1, QTableWidgetItem(party.get('mobile_number', '')))
            party_type = party.get('party_type', '')
            party_type_item = QTableWidgetItem("Debtor" if party_type == "Debitor" else party_type)
            party_type_item.setData(Qt.UserRole, party_type)
            table.setItem(row, 2, party_type_item)
            table.setItem(row, 3, QTableWidgetItem(party.get('gstin', '')))
            # Store party_id in UserRole
            table.item(row, 0).setData(Qt.UserRole, party.get('id'))

    def on_party_selected(self, table, popup):
        """Handle party selection from popup."""
        current_row = table.currentRow()
        if current_row >= 0:
            party_id = table.item(current_row, 0).data(Qt.UserRole)
            self.current_party_id = party_id
            party_name = table.item(current_row, 0).text()
            self.supplier_name_input.setText(party_name)

            # Load full party details
            company_id = self.get_current_company_id()
            party_data = self.db.get_party_by_id(company_id, party_id)
            if party_data:
                self.populate_party_details(party_data)

        popup.accept()

    def show_product_popup(self):
        """Show product selection popup."""
        popup = QDialog(self)
        popup.setWindowTitle("Select Product")
        popup.setFixedSize(600, 450)
        popup.setStyleSheet(theme.entry_picker_dialog_style())

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 10, 10, 10)

        # Search input
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_input = QLineEdit()
        search_input.setPlaceholderText("Type to search product name or barcode...")
        search_layout.addWidget(search_label)
        search_layout.addWidget(search_input)
        layout.addLayout(search_layout)

        # Product table
        product_table = QTableWidget()
        product_table.setColumnCount(5)
        product_table.setHorizontalHeaderLabels(["Name", "Barcode", "Code", "Rate", "Stock"])
        product_table.horizontalHeader().setStretchLastSection(False)
        apply_adjustable_table_columns(product_table, auto_size=False)
        product_table.verticalHeader().setVisible(False)
        product_table.setSelectionBehavior(QTableWidget.SelectRows)
        product_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(product_table)

        # Load products
        self.load_products_to_table(product_table)

        # Search functionality
        search_input.textChanged.connect(lambda: self.filter_products(search_input.text(), product_table))

        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(popup.reject)

        select_btn = QPushButton("Select")
        select_btn.setStyleSheet(theme.entry_select_button_style())
        select_btn.clicked.connect(lambda: self.on_product_selected(product_table, popup))

        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(select_btn)
        layout.addLayout(button_layout)

        # Double click to select
        product_table.doubleClicked.connect(lambda: self.on_product_selected(product_table, popup))

        popup.exec()

    def load_products_to_table(self, table):
        """Load products into table from database."""
        company_id = self.get_current_company_id()
        if not company_id:
            return

        products = self.db.get_products_by_company(company_id)
        table.setRowCount(0)

        for product in products:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(product.get('name', '')))
            table.setItem(row, 1, QTableWidgetItem(product.get('barcode', '')))
            table.setItem(row, 2, QTableWidgetItem(product.get('code', '')))
            table.setItem(row, 3, QTableWidgetItem(f"{product.get('rate', 0.0):.2f}"))
            # Use stock movement balance for accurate stock display
            stock_balance = self.get_product_stock(product.get('id'))
            table.setItem(row, 4, QTableWidgetItem(f"{stock_balance:.2f}"))
            # Store product_id in UserRole
            table.item(row, 0).setData(Qt.UserRole, product.get('id'))

    def get_product_stock(self, product_id):
        """Get current stock balance from stock movements."""
        company_id = self.get_current_company_id()
        if not company_id or not product_id:
            return 0.0
        from bizora_core.stock_logic import StockLogic
        stock_logic = StockLogic(self.db)
        balance = stock_logic.get_current_stock(company_id, product_id)
        return balance if balance else 0.0

    def filter_products(self, search_text, table):
        """Filter products table based on search text."""
        search_text = search_text.lower()
        for row in range(table.rowCount()):
            name = table.item(row, 0).text().lower()
            barcode = table.item(row, 1).text().lower()
            match = search_text in name or search_text in barcode
            table.setRowHidden(row, not match)

    def on_product_selected(self, table, popup):
        """Handle product selection from popup."""
        current_row = table.currentRow()
        if current_row >= 0:
            product_id = table.item(current_row, 0).data(Qt.UserRole)
            product_name = table.item(current_row, 0).text()
            self.product_input.setText(product_name)

            # Load full product details
            company_id = self.get_current_company_id()
            product_data = self.db.get_product_by_id(company_id, product_id) if company_id else None
            if product_data:
                stock_balance = self.get_product_stock(product_id)
                self.stock_display.setText(f"{stock_balance:.3f}")
                self.code_display.setText(str(product_data.get('code', '') or ''))
                self.current_product_id = product_id
                self.current_product_data = product_data

        popup.accept()

    def populate_party_details(self, party_data):
        """Populate party details from party data."""
        if not party_data:
            return
        
        self.address_input.setText(party_data.get('address', ''))
        self.mobile_input.setText(party_data.get('mobile_number', ''))
        gstin = party_data.get('gstin', '')
        self.gstin_input.setText(gstin)
        
        # Auto-fill state from party data or GSTIN
        state = party_data.get('state', '')
        if state:
            self.state_combo.setCurrentText(state)
        elif gstin and len(gstin) >= 2:
            state_code = gstin[:2].upper()
            if state_code in self.gst_state_codes:
                derived_state = self.gst_state_codes[state_code]
                self.state_combo.setCurrentText(derived_state)

    def add_new_creditor(self):
        """Open dialog to add new creditor."""
        try:
            from PySide6.QtWidgets import QApplication
            from ui.main_window import MainWindow
            main_window = None
            for w in QApplication.topLevelWidgets():
                if isinstance(w, MainWindow):
                    main_window = w
                    break
            if main_window and hasattr(main_window, 'show_debitor_creditor'):
                main_window.show_debitor_creditor()
            else:
                QMessageBox.information(self, "Add Creditor", "Open the Debtor/Creditor page from the sidebar to add a new creditor.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open creditor dialog: {e}")

    def edit_current_creditor(self):
        """Open dialog to edit current creditor."""
        if not (hasattr(self, 'current_party_id') and self.current_party_id):
            QMessageBox.warning(self, "Warning", "No party selected")
            return
        try:
            from PySide6.QtWidgets import QApplication
            from ui.main_window import MainWindow
            main_window = None
            for w in QApplication.topLevelWidgets():
                if isinstance(w, MainWindow):
                    main_window = w
                    break
            if main_window and hasattr(main_window, 'show_debitor_creditor'):
                main_window.show_debitor_creditor()
            else:
                QMessageBox.information(self, "Edit Creditor", "Open the Debtor/Creditor page from the sidebar to edit a creditor.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open creditor dialog: {e}")