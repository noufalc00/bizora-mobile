"""
Helper functions for Purchase Return widget.
Contains utility methods for data handling and UI operations.
"""

from typing import Dict, Any, List, Optional
from PySide6.QtCore import Qt, QDate, QCoreApplication
from PySide6.QtWidgets import QTableWidgetItem
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display


class PurchaseReturnHelpersMixin:
    """Mixin class containing helper methods for Purchase Return."""

    # Column index constants for 15-column layout
    COL_SL = 0
    COL_SALE_RATE = 1
    COL_PRODUCT = 2
    COL_HSN = 3
    COL_CGST = 4
    COL_SGST = 5
    COL_IGST = 6
    COL_CESS = 7
    COL_RATE = 8
    COL_QTY = 9
    COL_GROSS = 10
    COL_DISC = 11
    COL_NET = 12
    COL_TAX = 13
    COL_TOTAL = 14

    def format_currency(self, amount: float) -> str:
        """Format amount as currency string."""
        return f"₹{amount:.2f}"

    def format_num(self, value: float) -> str:
        """Format number for display (2 decimals)."""
        return f"{value:.2f}"

    def get_current_company_id(self) -> Optional[int]:
        """Get current company ID from parent."""
        if hasattr(self, 'company_id') and self.company_id:
            return self.company_id
        from config import active_company_manager
        active = active_company_manager.get_active_company()
        if active:
            self.company_id = active['id']
            return self.company_id
        return None

    def get_next_return_no(self) -> str:
        """Generate next return number."""
        company_id = self.get_current_company_id()
        if company_id:
            return self.purchase_return_logic.get_next_return_no(company_id)
        return "001"

    def populate_party_details(self, party_data: Dict[str, Any]):
        """Populate party fields from party data."""
        self.supplier_name_input.setText(party_data.get('name', ''))
        self.address_input.setText(party_data.get('address', ''))
        self.mobile_input.setText(party_data.get('mobile_number', ''))
        self.gstin_input.blockSignals(True)
        self.gstin_input.setText(party_data.get('gstin', ''))
        self.gstin_input.blockSignals(False)
        state = party_data.get('state', '')
        self.state_combo.blockSignals(True)
        self.state_combo.setCurrentText(state)
        self.state_combo.blockSignals(False)

    def clear_party_fields(self):
        """Clear all party input fields."""
        self.supplier_name_input.clear()
        self.address_input.clear()
        self.mobile_input.clear()
        self.gstin_input.clear()
        self.state_combo.setCurrentIndex(0)

    def clear_product_fields(self):
        """Clear all product input fields."""
        self.barcode_input.clear()
        self.product_input.clear()
        self.stock_display.setText("0")
        self.code_display.setText("")

    def clear_form(self):
        """Clear entire form for new entry."""
        self._begin_entry_reset()
        try:
            self.return_no_input.clear()
            self.return_no_input.setPlaceholderText("Auto")
            self.date_input.setDate(QDate.currentDate())
            from bizora_core.entry_type_defaults import apply_entry_type_combo, get_active_company_default_entry_type
            apply_entry_type_combo(
                self.return_type_combo,
                get_active_company_default_entry_type(self.db, "purchase_return"),
            )
            self.nature_combo.setCurrentIndex(0)
            self.original_purchase_input.clear()
            self.supplier_invoice_input.clear()
            self.narration_input.clear()
            for field_name in ('round_off_input', 'discount_total_input', 'amount_refunded_input'):
                field = getattr(self, field_name, None)
                if field is None:
                    continue
                was_blocked = field.blockSignals(True)
                try:
                    field.setText("0.00")
                finally:
                    field.blockSignals(was_blocked)
            if hasattr(self, 'discount_percent_label'):
                self.discount_percent_label.setText("")
            if hasattr(self, 'discount_status_display'):
                self.discount_status_display.setText("0.00%")
            self.clear_party_fields()
            self.clear_product_fields()
            was_blocked = self.items_table.blockSignals(True)
            try:
                self.items_table.setRowCount(0)
            finally:
                self.items_table.blockSignals(was_blocked)
            QCoreApplication.processEvents()
            self.update_summary_display()
            self.current_return_id = None
            self.current_party_id = None
            self.current_product_id = None
            self.current_product_data = {}
            next_no = self.get_next_return_no()
            self.return_no_input.setText(next_no)
            self.return_no_input.setPlaceholderText(f"Auto ({next_no})")
        finally:
            self._end_entry_reset()

    def get_form_data(self) -> Dict[str, Any]:
        """Collect all form data into a dictionary."""
        company_id = self.get_current_company_id()
        return_no = self.return_no_input.text().strip() or self.get_next_return_no()
        try:
            round_off = float(self.round_off_input.text() or '0')
        except ValueError:
            round_off = 0.0
        try:
            amount_refunded = float(self.amount_refunded_input.text() or '0')
        except ValueError:
            amount_refunded = 0.0
        try:
            footer_discount = float(self.discount_total_input.text() or '0') if hasattr(self, 'discount_total_input') else 0.0
        except ValueError:
            footer_discount = 0.0
        items = self.get_items_data()
        sub_total = sum(i.get('net_value', 0.0) for i in items)
        discount_total = sum(i.get('discount', 0.0) for i in items) + footer_discount
        cgst_total = sum(i.get('cgst_amount', 0.0) for i in items)
        sgst_total = sum(i.get('sgst_amount', 0.0) for i in items)
        igst_total = sum(i.get('igst_amount', 0.0) for i in items)
        cess_total = sum(i.get('cess_amount', 0.0) for i in items)
        tax_total = sum(i.get('tax_amount', 0.0) for i in items)
        grand_total_items = sum(i.get('grand_total', 0.0) for i in items)
        final_total = round(grand_total_items - footer_discount + round_off, 2)

        return {
            'company_id': company_id,
            'return_no': return_no,
            'return_date': qdate_to_db(self.date_input.date()),
            'due_date': qdate_to_db(self.due_date_input.date()),
            'original_purchase_id': None,
            'original_purchase_no': self.original_purchase_input.text(),
            'party_id': self.current_party_id if hasattr(self, 'current_party_id') else None,
            'return_type': self.return_type_combo.currentText(),
            'nature': self.nature_combo.currentText(),
            'series': self.series_input.text(),
            'supplier_invoice_no': self.supplier_invoice_input.text(),
            'narration': self.narration_input.text(),
            'sub_total': sub_total,
            'discount_total': discount_total,
            'cgst_total': cgst_total,
            'sgst_total': sgst_total,
            'igst_total': igst_total,
            'cess_total': cess_total,
            'tax_total': tax_total,
            'round_off': round_off,
            'freight': 0.0,  # TODO: Add freight input field to Purchase Return UI
            'grand_total': final_total,
            'amount_received_or_adjusted': amount_refunded,
            'balance_adjustment': round(final_total - amount_refunded, 2),
            'items': items
        }

    def get_items_data(self) -> List[Dict[str, Any]]:
        """Collect all items from table (15-column layout)."""
        items = []
        for row in range(self.items_table.rowCount()):
            def _t(c): return self.items_table.item(row, c).text() if self.items_table.item(row, c) else ''
            def _f(c):
                try: return float(_t(c).replace('%', '').strip() or '0')
                except ValueError: return 0.0
            product_cell = self.items_table.item(row, self.COL_PRODUCT)
            if not product_cell or not product_cell.text().strip():
                continue

            # Get tax percentages
            cgst_pct = _f(self.COL_CGST)
            sgst_pct = _f(self.COL_SGST)
            igst_pct = _f(self.COL_IGST)
            cess_pct = _f(self.COL_CESS)

            # Get net value to calculate tax amounts
            net_value = _f(self.COL_NET)

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
                'product_id': product_cell.data(Qt.UserRole),
                'sl_no': row + 1,
                'sale_rate': _f(self.COL_SALE_RATE),
                'product_name': _t(self.COL_PRODUCT),
                'hsn': _t(self.COL_HSN),
                'cgst': cgst_pct,
                'sgst': sgst_pct,
                'igst': igst_pct,
                'cess': cess_pct,
                'rate': _f(self.COL_RATE),
                'quantity': _f(self.COL_QTY),
                'gross_value': _f(self.COL_GROSS),
                'discount': _f(self.COL_DISC),
                'net_value': net_value,
                'cgst_amt': cgst_amt,
                'sgst_amt': sgst_amt,
                'igst_amt': igst_amt,
                'cess_amt': cess_amt,
                'cgst_amount': cgst_amt,
                'sgst_amount': sgst_amt,
                'igst_amount': igst_amt,
                'cess_amount': cess_amt,
                'tax_amount': _f(self.COL_TAX),
                'grand_total': _f(self.COL_TOTAL),
            }
            items.append(item)
        return items

    def load_return_data(self, return_data: Dict[str, Any]):
        """Load return data into form."""
        self.current_return_id = return_data['id']
        self.return_no_input.setText(return_data.get('return_no', ''))
        self.date_input.setDate(QDate.fromString(return_data.get('return_date', ''), 'yyyy-MM-dd'))
        self.return_type_combo.setCurrentText(return_data.get('return_type', 'Cash'))
        self.nature_combo.setCurrentText(return_data.get('nature', 'Local'))
        self.original_purchase_input.setText(return_data.get('original_purchase_no', ''))
        self.supplier_invoice_input.setText(return_data.get('supplier_invoice_no', ''))
        self.narration_input.setText(return_data.get('narration', ''))

        # Load party
        if return_data.get('party_id'):
            self.current_party_id = return_data['party_id']
            party_data = {
                'name': return_data.get('party_name', ''),
                'address': return_data.get('address', ''),
                'mobile_number': return_data.get('mobile_number', ''),
                'gstin': return_data.get('gstin', ''),
                'state': return_data.get('state', '')
            }
            self.populate_party_details(party_data)

        # Load items without firing per-cell recalculation while rows are rebuilt.
        was_blocked = self.items_table.blockSignals(True)
        try:
            self.items_table.setRowCount(0)
            items = return_data.get('items', [])
            for idx, item in enumerate(items):
                self.add_item_to_table(item, idx + 1)
                if idx % 4 == 0:
                    QCoreApplication.processEvents()
        finally:
            self.items_table.blockSignals(was_blocked)

        row_discount_total = sum(float(item.get('discount', 0.0) or 0.0) for item in return_data.get('items', []))
        saved_discount_total = float(return_data.get('discount_total', 0.0) or 0.0)
        footer_discount = max(saved_discount_total - row_discount_total, 0.0)
        if hasattr(self, 'discount_total_input'):
            was_blocked = self.discount_total_input.blockSignals(True)
            try:
                self.discount_total_input.setText(self.format_num(footer_discount))
            finally:
                self.discount_total_input.blockSignals(was_blocked)
        if hasattr(self, 'discount_percent_label'):
            self.discount_percent_label.setText("")

        # Update summary from DB-saved totals
        self.update_summary_display(return_data)

        # Restore saved amount_refunded from DB (update_summary_display doesn't set it).
        # Block signals to prevent on_amount_refunded_changed from overwriting balance prematurely.
        amt_ref = float(return_data.get('amount_received_or_adjusted', 0.0) or 0.0)
        self.amount_refunded_input.blockSignals(True)
        try:
            self.amount_refunded_input.setText(self.format_num(amt_ref))
        finally:
            self.amount_refunded_input.blockSignals(False)

        # Recompute live footer (recalculate_summary will call _update_refunded_from_type
        # which may overwrite amount_refunded based on return type — so restore again after).
        self.recalculate_summary()

        # Restore the DB amount_refunded value that recalculate_summary may have overridden.
        self.amount_refunded_input.blockSignals(True)
        try:
            self.amount_refunded_input.setText(self.format_num(amt_ref))
        finally:
            self.amount_refunded_input.blockSignals(False)
        # Recompute balance against the restored amount.
        if hasattr(self, '_update_balance_display'):
            self._update_balance_display()

    def add_item_to_table(self, item: Dict[str, Any], sl_no: int):
        """Add a single item to the 15-column items table."""
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)

        def _set(col, text, align=Qt.AlignRight | Qt.AlignVCenter, flags=None):
            wi = QTableWidgetItem(str(text))
            wi.setTextAlignment(align)
            if flags is not None:
                wi.setFlags(flags)
            self.items_table.setItem(row, col, wi)

        _set(self.COL_SL, str(sl_no), Qt.AlignCenter | Qt.AlignVCenter)
        _set(self.COL_SALE_RATE, f"{item.get('sale_rate', 0.0):.2f}")

        product_wi = QTableWidgetItem(item.get('product_name', ''))
        product_wi.setData(Qt.UserRole, item.get('product_id'))
        self.items_table.setItem(row, self.COL_PRODUCT, product_wi)

        _set(self.COL_HSN, item.get('hsn', ''), Qt.AlignLeft | Qt.AlignVCenter)
        _set(self.COL_CGST, f"{item.get('cgst', 0.0):.2f}%")
        _set(self.COL_SGST, f"{item.get('sgst', 0.0):.2f}%")
        _set(self.COL_IGST, f"{item.get('igst', 0.0):.2f}%")
        _set(self.COL_CESS, f"{item.get('cess', 0.0):.2f}%")
        _set(self.COL_RATE, f"{item.get('rate', 0.0):.2f}")
        _set(self.COL_QTY, f"{item.get('quantity', 0.0):.3f}")
        _set(self.COL_GROSS, f"{item.get('gross_value', 0.0):.2f}")
        _set(self.COL_DISC, f"{item.get('discount', 0.0):.2f}")
        _set(self.COL_NET, f"{item.get('net_value', 0.0):.2f}")
        _set(self.COL_TAX, f"{item.get('tax_amount', 0.0):.2f}")
        _set(self.COL_TOTAL, f"{item.get('grand_total', 0.0):.2f}")

    def update_summary_display(self, return_data: Optional[Dict[str, Any]] = None):
        """Update summary display with calculated totals."""
        if return_data:
            self.net_value_display.setText(self.format_num(return_data.get('sub_total', 0.0)))
            self.tax_amount_display.setText(self.format_num(return_data.get('tax_total', 0.0)))
            self.grand_total_input.setText(self.format_num(return_data.get('grand_total', 0.0)))
            self.round_off_input.setText(self.format_num(return_data.get('round_off', 0.0)))
            self.balance_display.setText(self.format_num(return_data.get('balance_adjustment', 0.0)))
            final = return_data.get('grand_total', 0.0)
            self.net_amount_display.setText(self.format_num(final))
            self.final_amount_display.setText(f"₹ {final:.2f}")
        else:
            self.net_value_display.setText("0.00")
            self.tax_amount_display.setText("0.00")
            self.cgst_display.setText("0.00")
            self.sgst_display.setText("0.00")
            self.igst_display.setText("0.00")
            self.cess_display.setText("0.00")
            self.grand_total_input.setText("0.00")
            self.net_amount_display.setText("0.00")
            self.balance_display.setText("0.00")
            self.final_amount_display.setText("₹ 0.00")
            if hasattr(self, 'discount_total_input'):
                self.discount_total_input.setText("0.00")
            if hasattr(self, 'discount_percent_label'):
                self.discount_percent_label.setText("")
            if hasattr(self, 'discount_status_display'):
                self.discount_status_display.setText("0.00%")

    def _safe_float(self, item) -> float:
        """Safely extract float from table item."""
        if item is None:
            return 0.0
        try:
            text = item.text().replace('%', '').replace('₹', '').replace(',', '').strip()
            return float(text) if text else 0.0
        except (ValueError, AttributeError):
            return 0.0

    def _safe_pct(self, item) -> float:
        """Safely extract percentage from table item."""
        if item is None:
            return 0.0
        try:
            text = item.text().replace('%', '').strip()
            return float(text) if text else 0.0
        except (ValueError, AttributeError):
            return 0.0