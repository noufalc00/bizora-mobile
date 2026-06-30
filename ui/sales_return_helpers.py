"""
Helper functions for Sales Return widget.
Contains utility methods for data handling and UI operations.
Column map for 14-col table:
  0=SL, 1=Product, 2=HSN, 3=CGST (%), 4=SGST (%), 5=IGST (%), 6=CESS (%),
  7=Rate, 8=Qty, 9=Gross, 10=Disc, 11=Net, 12=Tax, 13=Total
"""

from typing import Dict, Any, List, Optional
from PySide6.QtWidgets import QTableWidgetItem
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from PySide6.QtCore import Qt, QDate


class SalesReturnHelpersMixin:
    """Mixin class containing helper methods for Sales Return."""

    # Column indices
    COL_SL = 0
    COL_PRODUCT = 1
    COL_HSN = 2
    COL_CGST = 3
    COL_SGST = 4
    COL_IGST = 5
    COL_CESS = 6
    COL_RATE = 7
    COL_QTY = 8
    COL_GROSS = 9
    COL_DISC = 10
    COL_NET = 11
    COL_TAX = 12
    COL_TOTAL = 13

    def format_currency(self, amount) -> str:
        try:
            return f"₹{float(amount):.2f}"
        except (TypeError, ValueError):
            return "₹0.00"

    def format_num(self, amount) -> str:
        try:
            return f"{float(amount):.2f}"
        except (TypeError, ValueError):
            return "0.00"

    def get_current_company_id(self) -> Optional[int]:
        if hasattr(self, 'company_id') and self.company_id:
            return self.company_id
        from config import active_company_manager
        active = active_company_manager.get_active_company()
        if active:
            self.company_id = active['id']
            return self.company_id
        return None

    def get_next_return_no(self) -> str:
        company_id = self.get_current_company_id()
        if company_id:
            return self.sales_return_logic.get_next_return_no(company_id)
        return "001"

    def populate_party_details(self, party_data: Dict[str, Any]):
        self.customer_name_input.blockSignals(True)
        self.customer_name_input.setText(party_data.get('name', ''))
        self.customer_name_input.blockSignals(False)
        self.address_input.setText(party_data.get('address', ''))
        self.mobile_input.setText(str(party_data.get('mobile_number', '') or ''))
        self.gstin_input.setText(str(party_data.get('gstin', '') or ''))
        state_val = str(party_data.get('state', '') or '')
        idx = self.state_combo.findText(state_val)
        if idx >= 0:
            self.state_combo.setCurrentIndex(idx)
        else:
            self.state_combo.setEditText(state_val)

    def clear_party_fields(self):
        self.current_party_id = None
        self.customer_name_input.blockSignals(True)
        self.customer_name_input.clear()
        self.customer_name_input.blockSignals(False)
        self.address_input.clear()
        self.mobile_input.clear()
        self.gstin_input.clear()
        self.state_combo.setCurrentIndex(0)

    def clear_product_fields(self):
        self.current_product_id = None
        self.current_product_data = {}
        self.barcode_input.clear()
        self.product_input.clear()
        self.stock_display.setText("")
        self.code_display.setText("")

    def clear_form(self):
        self._begin_entry_reset()
        try:
            self.items_table.blockSignals(True)
            self.return_no_input.clear()
            self.return_no_input.setPlaceholderText("Auto")
            self.date_input.setDate(QDate.currentDate())
            from bizora_core.entry_type_defaults import apply_entry_type_combo, get_active_company_default_entry_type
            apply_entry_type_combo(
                self.return_type_combo,
                get_active_company_default_entry_type(self.db, "sales_return"),
            )
            self.nature_combo.setCurrentIndex(0)
            if hasattr(self, 'party_type_combo'):
                idx_debtor = self.party_type_combo.findText("Debtor", Qt.MatchFixedString)
                self.party_type_combo.setCurrentIndex(idx_debtor if idx_debtor >= 0 else 0)
            self.series_input.clear()
            self.original_bill_input.clear()
            self.narration_input.clear()
            self.clear_party_fields()
            self.clear_product_fields()
            self.items_table.setRowCount(0)
            self.items_table.blockSignals(False)
            self.current_return_id = None
            self.selected_sl_row = -1
            self.manually_selected_row = -1
            self._reset_footer_displays()
            next_no = self.get_next_return_no()
            self.return_no_input.setText(next_no)
            self.return_no_input.setPlaceholderText(f"Auto ({next_no})")
        finally:
            self._end_entry_reset()

    def _reset_footer_displays(self):
        self.grand_total_input.setText("")
        if hasattr(self, 'discount_total_input'):
            self.discount_total_input.setText("0.00")
        if hasattr(self, 'round_off_checkbox'):
            self.round_off_checkbox.blockSignals(True)
            self.round_off_checkbox.setChecked(True)
            self.round_off_checkbox.blockSignals(False)
        self.round_off_input.setText("0.00")
        self.net_amount_display.setText("0.00")
        self.amount_refunded_input.setText("0.00")
        self.balance_display.setText("0.00")
        self.net_value_display.setText("0.00")
        self.cgst_display.setText("0.00")
        self.sgst_display.setText("0.00")
        self.igst_display.setText("0.00")
        self.tax_amount_display.setText("0.00")
        self.cess_display.setText("0.00")
        self.final_amount_display.setText("₹ 0.00")
        self.grand_total_display.setText("")
        self.round_off_display.setText("0.00")

    def _safe_float(self, cell) -> float:
        if cell is None:
            return 0.0
        try:
            return float(cell.text().replace(',', '').replace('₹', '').strip() or '0')
        except (ValueError, AttributeError):
            return 0.0

    def _safe_pct(self, cell) -> float:
        if cell is None:
            return 0.0
        try:
            return float(cell.text().replace('%', '').strip() or '0')
        except (ValueError, AttributeError):
            return 0.0

    def get_form_data(self) -> Dict[str, Any]:
        company_id = self.get_current_company_id()
        return_no = self.return_no_input.text().strip() or self.get_next_return_no()

        try:
            amount_refunded = float(self.amount_refunded_input.text() or '0')
        except ValueError:
            amount_refunded = 0.0
        try:
            round_off = float(self.round_off_input.text() or '0')
        except ValueError:
            round_off = 0.0

        items = self.get_items_data()
        summary = self.calculate_summary_totals(items)
        final_amount = round(summary['rounded_total'], 2)
        round_off = float(summary.get('round_off', round_off) or 0.0)
        balance = round(final_amount - amount_refunded, 2)

        return {
            'company_id': company_id,
            'return_no': return_no,
            'return_date': qdate_to_db(self.date_input.date()),
            'original_bill_id': None,
            'original_bill_no': self.original_bill_input.text().strip(),
            'party_id': getattr(self, 'current_party_id', None),
            'return_type': self.return_type_combo.currentText(),
            'nature': self.nature_combo.currentText(),
            'narration': self.narration_input.text().strip(),
            'sub_total': summary['sub_total'],
            'discount_total': summary['discount_total'],
            'tax_total': summary['tax_total'],
            'round_off': round_off,
            'freight': 0.0,  # TODO: Add freight input field to Sales Return UI
            'grand_total': final_amount,
            'amount_refunded_or_adjusted': amount_refunded,
            'balance_adjustment': balance,
            'items': items
        }

    def get_items_data(self) -> List[Dict[str, Any]]:
        items = []
        for row in range(self.items_table.rowCount()):
            product_cell = self.items_table.item(row, self.COL_PRODUCT)
            if not product_cell or not product_cell.text().strip():
                continue
            product_id = product_cell.data(Qt.UserRole)
            qty = self._safe_float(self.items_table.item(row, self.COL_QTY))
            if not product_id or qty <= 0:
                continue

            # Get tax percentages
            cgst_pct = self._safe_pct(self.items_table.item(row, self.COL_CGST))
            sgst_pct = self._safe_pct(self.items_table.item(row, self.COL_SGST))
            igst_pct = self._safe_pct(self.items_table.item(row, self.COL_IGST))
            cess_pct = self._safe_pct(self.items_table.item(row, self.COL_CESS))

            # Get net value to calculate tax amounts
            net_value = self._safe_float(self.items_table.item(row, self.COL_NET))

            # Determine GST nature
            nature_str = "Local"
            if hasattr(self, 'nature_combo'):
                nature_str = self.nature_combo.currentText()
            is_inter_state = 'inter' in nature_str.lower()

            # Calculate GST split amounts based on nature
            if is_inter_state:
                # Inter-state: IGST + CESS only
                cgst_amt = 0.0
                sgst_amt = 0.0
                igst_amt = net_value * (igst_pct / 100.0)
                cess_amt = net_value * (cess_pct / 100.0)
            else:
                # Local: CGST + SGST + CESS
                cgst_amt = net_value * (cgst_pct / 100.0)
                sgst_amt = net_value * (sgst_pct / 100.0)
                igst_amt = 0.0
                cess_amt = net_value * (cess_pct / 100.0)

            item = {
                'product_id': product_id,
                'product_name': product_cell.text(),
                'sl_no': row + 1,
                'hsn': self.items_table.item(row, self.COL_HSN).text() if self.items_table.item(row, self.COL_HSN) else '',
                'cgst': cgst_pct,
                'sgst': sgst_pct,
                'igst': igst_pct,
                'cess': cess_pct,
                'tax_percent': (cgst_pct + sgst_pct + igst_pct + cess_pct),
                'rate': self._safe_float(self.items_table.item(row, self.COL_RATE)),
                'quantity': qty,
                'gross_value': self._safe_float(self.items_table.item(row, self.COL_GROSS)),
                'discount': self._safe_float(self.items_table.item(row, self.COL_DISC)),
                'net_value': net_value,
                'cgst_amt': cgst_amt,
                'sgst_amt': sgst_amt,
                'igst_amt': igst_amt,
                'cess_amt': cess_amt,
                'tax_amount': self._safe_float(self.items_table.item(row, self.COL_TAX)),
                'grand_total': self._safe_float(self.items_table.item(row, self.COL_TOTAL))
            }
            items.append(item)
        return items

    def add_item_to_table(self, item: Dict[str, Any], sl_no: int):
        self.items_table.blockSignals(True)
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)

        sl_item = QTableWidgetItem(str(sl_no))
        sl_item.setFlags(sl_item.flags() & ~Qt.ItemIsEditable)
        sl_item.setTextAlignment(Qt.AlignCenter)
        self.items_table.setItem(row, self.COL_SL, sl_item)

        prod_item = QTableWidgetItem(item.get('product_name', ''))
        prod_item.setData(Qt.UserRole, item.get('product_id'))
        prod_item.setFlags(prod_item.flags() & ~Qt.ItemIsEditable)
        self.items_table.setItem(row, self.COL_PRODUCT, prod_item)

        hsn_item = QTableWidgetItem(str(item.get('hsn', '')))
        hsn_item.setFlags(hsn_item.flags() & ~Qt.ItemIsEditable)
        self.items_table.setItem(row, self.COL_HSN, hsn_item)

        cgst_item = QTableWidgetItem(f"{item.get('cgst', 0.0):.2f}")
        cgst_item.setFlags(cgst_item.flags() & ~Qt.ItemIsEditable)
        cgst_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_CGST, cgst_item)

        sgst_item = QTableWidgetItem(f"{item.get('sgst', 0.0):.2f}")
        sgst_item.setFlags(sgst_item.flags() & ~Qt.ItemIsEditable)
        sgst_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_SGST, sgst_item)

        igst_item = QTableWidgetItem(f"{item.get('igst', 0.0):.2f}")
        igst_item.setFlags(igst_item.flags() & ~Qt.ItemIsEditable)
        igst_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_IGST, igst_item)

        cess_item = QTableWidgetItem(f"{item.get('cess', 0.0):.2f}")
        cess_item.setFlags(cess_item.flags() & ~Qt.ItemIsEditable)
        cess_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_CESS, cess_item)

        rate_item = QTableWidgetItem(self.format_num(item.get('rate', 0.0)))
        rate_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_RATE, rate_item)

        qty_item = QTableWidgetItem(self.format_num(item.get('quantity', 0.0)))
        qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_QTY, qty_item)

        gross_item = QTableWidgetItem(self.format_num(item.get('gross_value', 0.0)))
        gross_item.setFlags(gross_item.flags() & ~Qt.ItemIsEditable)
        gross_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_GROSS, gross_item)

        disc_item = QTableWidgetItem(self.format_num(item.get('discount', 0.0)))
        disc_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_DISC, disc_item)

        net_item = QTableWidgetItem(self.format_num(item.get('net_value', 0.0)))
        net_item.setFlags(net_item.flags() & ~Qt.ItemIsEditable)
        net_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_NET, net_item)

        tax_item = QTableWidgetItem(self.format_num(item.get('tax_amount', 0.0)))
        tax_item.setFlags(tax_item.flags() & ~Qt.ItemIsEditable)
        tax_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_TAX, tax_item)

        total_item = QTableWidgetItem(self.format_num(item.get('grand_total', 0.0)))
        total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
        total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_TOTAL, total_item)

        self.items_table.blockSignals(False)

    def _row_product_id(self, row: int):
        """Return product_id stored on a table row, or None when blank."""
        product_cell = self.items_table.item(row, self.COL_PRODUCT)
        if not product_cell:
            return None
        product_id = product_cell.data(Qt.UserRole)
        return product_id if product_id else None

    def find_blank_row(self) -> int:
        """Return the first unfilled row index, or -1 when every row has a product."""
        for row in range(self.items_table.rowCount()):
            product_cell = self.items_table.item(row, self.COL_PRODUCT)
            if not product_cell or not str(product_cell.text() or '').strip():
                if not self._row_product_id(row):
                    return row
        return -1

    def add_blank_row(self) -> int:
        """Insert one blank row when no unfilled row already exists."""
        existing_blank = self.find_blank_row()
        if existing_blank >= 0:
            return existing_blank
        row = self.items_table.rowCount()
        self.items_table.blockSignals(True)
        try:
            self.items_table.insertRow(row)
            sl_item = QTableWidgetItem(str(row + 1))
            sl_item.setFlags(sl_item.flags() & ~Qt.ItemIsEditable)
            sl_item.setTextAlignment(Qt.AlignCenter)
            self.items_table.setItem(row, self.COL_SL, sl_item)

            prod_item = QTableWidgetItem('')
            prod_item.setData(Qt.UserRole, None)
            prod_item.setFlags(prod_item.flags() & ~Qt.ItemIsEditable)
            self.items_table.setItem(row, self.COL_PRODUCT, prod_item)

            read_only_cols = (
                self.COL_HSN, self.COL_CGST, self.COL_SGST, self.COL_IGST, self.COL_CESS,
                self.COL_GROSS, self.COL_NET, self.COL_TAX, self.COL_TOTAL,
            )
            editable_cols = (self.COL_RATE, self.COL_QTY, self.COL_DISC)
            for col in read_only_cols:
                cell = QTableWidgetItem('')
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col != self.COL_HSN:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.items_table.setItem(row, col, cell)
            for col in editable_cols:
                cell = QTableWidgetItem('')
                cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.items_table.setItem(row, col, cell)
        finally:
            self.items_table.blockSignals(False)
        self.items_table.clearSelection()
        return row

    def find_row_by_barcode(self, barcode: str) -> int:
        """Find an existing line with the same product barcode."""
        barcode_text = str(barcode or '').strip()
        if not barcode_text:
            return -1
        company_id = self.get_current_company_id()
        if not company_id:
            return -1
        for row in range(self.items_table.rowCount()):
            product_id = self._row_product_id(row)
            if not product_id:
                continue
            product = self.db.get_product_by_id(company_id, product_id)
            if product and str(product.get('barcode', '') or '').strip() == barcode_text:
                return row
        return -1

    def increment_row_qty(self, row: int) -> None:
        """Increase quantity on an existing scanned line by one."""
        if row < 0 or row >= self.items_table.rowCount():
            return
        qty_item = self.items_table.item(row, self.COL_QTY)
        current_qty = self._safe_float(qty_item)
        if qty_item:
            qty_item.setText(self.format_num(current_qty + 1.0))
        self._recalculate_row_in_table(row)

    def build_item_data_from_product(self, product: Dict[str, Any], quantity: float = 1.0) -> Dict[str, Any]:
        """Build one return-table row payload from a product master record."""
        nature = self.nature_combo.currentText()
        cgst_pct = float(product.get('cgst', 0.0) or 0.0)
        sgst_pct = float(product.get('sgst', 0.0) or 0.0)
        igst_pct = float(product.get('igst', 0.0) or 0.0)
        cess_pct = float(product.get('cess', 0.0) or 0.0)
        if nature != 'Inter-state':
            igst_pct = 0.0
        else:
            cgst_pct = 0.0
            sgst_pct = 0.0
        if hasattr(self, '_set_product_filter_values'):
            self._set_product_filter_values(product)
        rate = float(self.get_product_rate_from_selector(product) or 0.0)
        discount = 0.0
        totals = self.calculate_row_totals({
            'rate': rate,
            'quantity': quantity,
            'discount': discount,
            'nature': nature,
            'cgst_pct': cgst_pct,
            'sgst_pct': sgst_pct,
            'igst_pct': igst_pct,
            'cess_pct': cess_pct,
        })
        return {
            'product_id': product.get('id'),
            'product_name': product.get('name', ''),
            'hsn': product.get('hsn', '') or '',
            'cgst': cgst_pct,
            'sgst': sgst_pct,
            'igst': igst_pct,
            'cess': cess_pct,
            'cgst_amount': totals.get('cgst_amt', 0.0),
            'sgst_amount': totals.get('sgst_amt', 0.0),
            'igst_amount': totals.get('igst_amt', 0.0),
            'cess_amount': totals.get('cess_amt', 0.0),
            'rate': rate,
            'quantity': quantity,
            'discount': discount,
            'gross_value': totals['gross_value'],
            'net_value': totals['net_value'],
            'tax_amount': totals['tax_amount'],
            'grand_total': totals['grand_total'],
        }

    def fill_blank_row_with_product(self, row: int, product: Dict[str, Any]) -> None:
        """Fill an existing blank row with product details."""
        item_data = self.build_item_data_from_product(product, quantity=1.0)
        self.items_table.blockSignals(True)
        try:
            sl_item = self.items_table.item(row, self.COL_SL)
            if sl_item:
                sl_item.setText(str(row + 1))
            prod_item = self.items_table.item(row, self.COL_PRODUCT)
            if prod_item:
                prod_item.setText(item_data['product_name'])
                prod_item.setData(Qt.UserRole, item_data['product_id'])
            hsn_item = self.items_table.item(row, self.COL_HSN)
            if hsn_item:
                hsn_item.setText(item_data['hsn'])
            for col, key in (
                (self.COL_CGST, 'cgst'),
                (self.COL_SGST, 'sgst'),
                (self.COL_IGST, 'igst'),
                (self.COL_CESS, 'cess'),
            ):
                cell = self.items_table.item(row, col)
                if cell:
                    cell.setText(f"{item_data[key]:.2f}")
            for col, key in (
                (self.COL_RATE, 'rate'),
                (self.COL_QTY, 'quantity'),
                (self.COL_DISC, 'discount'),
                (self.COL_GROSS, 'gross_value'),
                (self.COL_NET, 'net_value'),
                (self.COL_TAX, 'tax_amount'),
                (self.COL_TOTAL, 'grand_total'),
            ):
                cell = self.items_table.item(row, col)
                if cell:
                    cell.setText(self.format_num(item_data[key]))
        finally:
            self.items_table.blockSignals(False)
        self.recalculate_summary()

    def add_product_row_from_scan(self, product: Dict[str, Any]) -> int:
        """Append a product row or reuse the first blank row."""
        blank_row = self.find_blank_row()
        if blank_row >= 0:
            self.fill_blank_row_with_product(blank_row, product)
            return blank_row
        item_data = self.build_item_data_from_product(product, quantity=1.0)
        row = self.items_table.rowCount()
        self.add_item_to_table(item_data, row + 1)
        return row

    def load_return_data(self, return_data: Dict[str, Any]):
        self.current_return_id = return_data['id']
        self.return_no_input.setText(return_data.get('return_no', ''))
        date_str = return_data.get('return_date', '')
        if date_str:
            parsed = QDate.fromString(date_str, 'yyyy-MM-dd')
            if parsed.isValid():
                self.date_input.setDate(parsed)
        self.return_type_combo.setCurrentText(return_data.get('return_type', 'Cash'))
        self.nature_combo.setCurrentText(return_data.get('nature', 'Local'))
        self.original_bill_input.setText(return_data.get('original_bill_no', '') or '')
        self.narration_input.setText(return_data.get('narration', '') or '')

        if return_data.get('party_id'):
            self.current_party_id = return_data['party_id']
            self.populate_party_details({
                'name': return_data.get('party_name', ''),
                'address': return_data.get('address', ''),
                'mobile_number': return_data.get('mobile_number', ''),
                'gstin': return_data.get('gstin', ''),
                'state': return_data.get('state', '')
            })

        self.items_table.blockSignals(True)
        self.items_table.setRowCount(0)
        items = return_data.get('items', [])
        for idx, item in enumerate(items):
            self.add_item_to_table(item, idx + 1)
        self.items_table.blockSignals(False)

        if hasattr(self, 'discount_total_input'):
            saved_discount_total = float(return_data.get('discount_total', 0.0) or 0.0)
            row_discount_total = sum(float(item.get('discount', 0.0) or 0.0) for item in items)
            footer_discount = max(0.0, saved_discount_total - row_discount_total)
            self.discount_total_input.blockSignals(True)
            try:
                self.discount_total_input.setText(self.format_num(footer_discount))
            finally:
                self.discount_total_input.blockSignals(False)

        self.recalculate_summary()
        # Restore the saved amount_refunded from DB, overriding what recalculate_summary set.
        # Block signals so this write doesn't recurse into _update_balance_display prematurely.
        amt_ref = return_data.get('amount_refunded_or_adjusted', 0.0)
        self.amount_refunded_input.blockSignals(True)
        try:
            self.amount_refunded_input.setText(self.format_num(amt_ref))
        finally:
            self.amount_refunded_input.blockSignals(False)
        # Now recompute balance against the restored amount.
        if hasattr(self, '_update_balance_display'):
            self._update_balance_display()

    def update_summary_display(self, return_data: Optional[Dict[str, Any]] = None):
        self._reset_footer_displays()