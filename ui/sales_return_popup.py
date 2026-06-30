"""
Popup components for Sales Return widget.
- Party popup: search Debtor/Both parties, dark theme, no preload.
- Product popup: limited search (max 100 results), no preload on open, dark theme.
- Double-click or Enter selects. Prevents duplicate product add guard is in caller.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QMessageBox, QHeaderView
)
from PySide6.QtCore import Qt, QTimer
from ui import theme
from ui.party_display import party_display_name
from ui.table_header_utils import apply_adjustable_table_columns



def _popup_style() -> str:
    return theme.entry_picker_dialog_style()


def _select_btn_style() -> str:
    return theme.entry_select_button_style()


class SalesReturnPopupMixin:
    """Mixin class containing popup methods for Sales Return."""

    # ==================== PARTY POPUP ====================

    def show_party_popup(self):
        company_id = self.get_current_company_id()
        if not company_id:
            QMessageBox.warning(self, "Error", "No active company selected.")
            return

        popup = QDialog(self)
        popup.setWindowTitle("Select Customer / Debtor")
        popup.resize(560, 420)
        popup.setStyleSheet(_popup_style())
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        search_lbl = QLabel("Search:")
        search_input = QLineEdit()
        search_input.setPlaceholderText("Name, code or mobile...")
        search_input.setFixedWidth(250)
        type_lbl = QLabel("Type:")
        type_filter = QComboBox()
        type_filter.addItems(["Debtor", "Both", "All"])
        type_filter.setFixedWidth(100)
        top.addWidget(search_lbl)
        top.addWidget(search_input)
        top.addSpacing(10)
        top.addWidget(type_lbl)
        top.addWidget(type_filter)
        top.addStretch()
        layout.addLayout(top)

        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["Name", "Mobile", "Type", "GSTIN"])
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        apply_adjustable_table_columns(tbl, auto_size=False)
        tbl.setColumnWidth(0, 180)
        tbl.setColumnWidth(1, 110)
        tbl.setColumnWidth(2, 80)
        layout.addWidget(tbl)

        def do_search():
            search_text = search_input.text().strip()
            type_text = type_filter.currentText()
            tbl.setRowCount(0)
            parties = self.db.get_parties_by_company(company_id)
            for party in parties:
                ptype = party.get('party_type', '')
                if type_text == "Debtor" and ptype not in ("Debitor", "debitor", "Debtor", "debtor"):
                    continue
                elif type_text == "Both" and ptype not in ("Both", "both"):
                    continue
                name = party.get('name', '')
                code = str(party.get('party_code', '') or '')
                display_name = party_display_name(party)
                mobile = str(party.get('mobile_number', '') or '')
                if search_text and (search_text.lower() not in name.lower()
                                    and search_text.lower() not in code.lower()
                                    and search_text.lower() not in mobile.lower()):
                    continue
                row = tbl.rowCount()
                tbl.insertRow(row)
                name_item = QTableWidgetItem(display_name)
                name_item.setData(Qt.UserRole, party.get('id'))
                tbl.setItem(row, 0, name_item)
                tbl.setItem(row, 1, QTableWidgetItem(mobile))
                tbl.setItem(row, 2, QTableWidgetItem("Debtor" if ptype == "Debitor" else ptype))
                tbl.setItem(row, 3, QTableWidgetItem(str(party.get('gstin', '') or '')))
            if tbl.rowCount() > 0:
                tbl.selectRow(0)

        do_search()
        search_input.textChanged.connect(do_search)
        type_filter.currentTextChanged.connect(do_search)
        search_input.setFocus()

        def focus_party_table():
            if tbl.rowCount() > 0:
                if tbl.currentRow() < 0:
                    tbl.selectRow(0)
                tbl.setFocus()

        def select_party():
            row = tbl.currentRow()
            if row < 0:
                return
            party_id = tbl.item(row, 0).data(Qt.UserRole)
            self.current_party_id = party_id
            company_id2 = self.get_current_company_id()
            party_data = self.db.get_party_by_id(company_id2, party_id) if company_id2 else None
            if party_data:
                self.populate_party_details(party_data)
            else:
                self.customer_name_input.blockSignals(True)
                self.customer_name_input.setText(tbl.item(row, 0).text())
                self.customer_name_input.blockSignals(False)
            popup.accept()

        tbl.doubleClicked.connect(select_party)

        _party_search_key_press = search_input.keyPressEvent
        def party_search_key_press(event):
            if event.key() in (Qt.Key_Down, Qt.Key_Tab):
                focus_party_table()
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                select_party()
                return
            if event.key() == Qt.Key_Escape:
                popup.reject()
                return
            _party_search_key_press(event)
        search_input.keyPressEvent = party_search_key_press

        _party_table_key_press = tbl.keyPressEvent
        def party_table_key_press(event):
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                select_party()
                return
            if event.key() == Qt.Key_Escape:
                search_input.setFocus()
                search_input.selectAll()
                return
            _party_table_key_press(event)
        tbl.keyPressEvent = party_table_key_press

        btns = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(popup.reject)
        select_btn = QPushButton("Select")
        select_btn.setStyleSheet(_select_btn_style())
        select_btn.clicked.connect(select_party)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(select_btn)
        layout.addLayout(btns)

        def key_press(event):
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                select_party()
            elif event.key() == Qt.Key_Escape:
                popup.reject()
            else:
                QDialog.keyPressEvent(popup, event)

        popup.keyPressEvent = key_press
        popup.exec()

    # ==================== PRODUCT POPUP ====================

    def show_product_popup(self):
        company_id = self.get_current_company_id()
        if not company_id:
            QMessageBox.warning(self, "Error", "No active company selected.")
            return

        popup = QDialog(self)
        popup.setWindowTitle("Select Product")
        popup.resize(620, 440)
        popup.setStyleSheet(_popup_style())
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        search_lbl = QLabel("Search (name / barcode):")
        search_input = QLineEdit()
        search_input.setPlaceholderText("Type at least 1 character…")
        top.addWidget(search_lbl)
        top.addWidget(search_input)
        layout.addLayout(top)

        hint = QLabel("Type to search. Max 100 results shown.")
        hint.setStyleSheet(theme.entry_micro_hint_style())
        layout.addWidget(hint)

        tbl = QTableWidget()
        tbl.setColumnCount(5)
        tbl.setHorizontalHeaderLabels(["Name", "Barcode", "Code", "Rate", "Stock"])
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setColumnWidth(0, 220)
        tbl.setColumnWidth(1, 110)
        tbl.setColumnWidth(2, 80)
        tbl.setColumnWidth(3, 80)
        apply_adjustable_table_columns(tbl, auto_size=False)
        layout.addWidget(tbl)

        _search_timer = QTimer()
        _search_timer.setSingleShot(True)
        _search_timer.setInterval(200)

        def do_search():
            term = search_input.text().strip()
            tbl.setRowCount(0)
            if not term:
                return
            results = self.db.search_products_limited(company_id, term, limit=100)
            if hasattr(self, '_product_matches_top_filters'):
                results = [p for p in results if self._product_matches_top_filters(p)]
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
                if hasattr(self, 'get_product_rate_from_selector'):
                    rate = float(self.get_product_rate_from_selector(product) or 0.0)
                else:
                    rate = float(product.get('sale_price') or product.get('mrp') or
                                 product.get('wholesale_rate') or product.get('purchase_rate') or 0.0)
                tbl.setItem(row, 3, QTableWidgetItem(f"{rate:.2f}"))
                try:
                    stock = float(self.stock_logic.get_current_stock(company_id, product.get('id')) or 0.0)
                except Exception:
                    stock = float(product.get('quantity') or 0.0)
                tbl.setItem(row, 4, QTableWidgetItem(f"{stock:.3f}"))
            tbl.blockSignals(False)
            tbl.setUpdatesEnabled(True)
            if tbl.rowCount() > 0:
                tbl.selectRow(0)

        _search_timer.timeout.connect(do_search)
        search_input.textChanged.connect(lambda: _search_timer.start())
        # Pre-seed with whatever is already typed in product_input
        initial_term = self.product_input.text().strip() if hasattr(self, 'product_input') else ''
        search_input.setText(initial_term)
        search_input.setFocus()
        if initial_term:
            search_input.selectAll()

        def focus_product_table():
            if tbl.rowCount() > 0:
                if tbl.currentRow() < 0:
                    tbl.selectRow(0)
                tbl.setFocus()

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

            self._popup_product_selected = True
            self.current_product_id = product_id
            company_id2 = self.get_current_company_id()
            full_product = self.db.get_product_by_id(company_id2, product_id) if company_id2 else None
            if full_product:
                self.current_product_data = full_product
                if hasattr(self, '_set_product_filter_values'):
                    self._set_product_filter_values(full_product)
            else:
                self.current_product_data = {
                    'id': product_id, 'name': product_name,
                    'rate': rate_val, 'code': code_val
                }

            self.product_input.blockSignals(True)
            self.product_input.setText(product_name)
            self.product_input.blockSignals(False)
            self.stock_display.setText(f"{stock_val:.3f}")
            self.code_display.setText(code_val)
            popup.accept()
            self.add_product_to_items()

        tbl.doubleClicked.connect(select_product)

        _product_search_key_press = search_input.keyPressEvent
        def product_search_key_press(event):
            if event.key() in (Qt.Key_Down, Qt.Key_Tab):
                focus_product_table()
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if tbl.currentRow() < 0 and tbl.rowCount() > 0:
                    tbl.selectRow(0)
                select_product()
                return
            if event.key() == Qt.Key_Escape:
                popup.reject()
                return
            _product_search_key_press(event)
        search_input.keyPressEvent = product_search_key_press

        _product_table_key_press = tbl.keyPressEvent
        def product_table_key_press(event):
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                select_product()
                return
            if event.key() == Qt.Key_Escape:
                search_input.setFocus()
                search_input.selectAll()
                return
            _product_table_key_press(event)
        tbl.keyPressEvent = product_table_key_press

        btns = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(popup.reject)
        select_btn = QPushButton("Select")
        select_btn.setStyleSheet(_select_btn_style())
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

    # ==================== DEBITOR BUTTONS ====================

    def add_new_debitor(self):
        QMessageBox.information(self, "Info",
                                "Add New Debtor - open Debtor/Creditor module to add.")

    def edit_current_debitor(self):
        if hasattr(self, 'current_party_id') and self.current_party_id:
            QMessageBox.information(self, "Info",
                                    "Edit Debtor - open Debtor/Creditor module to edit.")
        else:
            QMessageBox.warning(self, "Warning", "No party selected. Select a customer first.")