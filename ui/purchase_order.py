"""
Purchase Order entry widget.

Mirrors Purchase Entry layout and keyboard workflow but persists only to
purchase_orders / purchase_order_items. Does not post stock or ledger entries.
"""

from PySide6.QtWidgets import QMessageBox
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from PySide6.QtCore import QCoreApplication, QDate, QTimer, Qt

from config import active_company_manager
from .purchase_entry import PurchaseEntryWidget
from .purchase_entry_helpers import safe_item_text, safe_float_from_cell
from .purchase_order_ui import PurchaseOrderUIMixin
from ui.party_display import party_matches_text, strip_party_display_code


class PurchaseOrderUI(PurchaseOrderUIMixin, PurchaseEntryWidget):
    """Purchase order document entry (isolated from inventory and creditors ledger)."""
    voucher_type = "purchase_order"
    voucher_number_attr = "purchase_no_input"

    def __init__(self, parent=None, db=None):
        self.current_po_id = None
        self._po_nav_ids = []
        # Accept legacy call pattern PurchaseOrderUI(db) from older main_window code.
        if db is None and parent is not None and not hasattr(parent, "setWindowTitle"):
            db = parent
            parent = None
        super().__init__(parent, db=db)

    def _deferred_initial_load(self):
        """Load creditors/products and assign the next PO number."""
        if self._skip_initial_load:
            return
        if self._initial_load_done or self._deferred_load_started:
            return
        self._deferred_load_started = True
        try:
            self.load_creditors()
            self.load_products()
            self.generate_po_number()
            self._initial_load_done = True
        finally:
            self._deferred_load_started = False

    def generate_purchase_number(self):
        """Alias used by base class hooks; generates PO numbers only."""
        self.generate_po_number()

    def generate_po_number(self):
        """Auto-generate the next purchase order number for the active company."""
        if self.current_po_id:
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return
        if hasattr(self, "purchase_checkbox") and self.purchase_checkbox.isChecked():
            return
        try:
            next_number = self.db.get_next_po_number(active_company["id"])
            self.purchase_no_input.setText(next_number)
        except Exception:
            self.purchase_no_input.setText("001")

    def previous_po(self):
        """Navigate to the previous saved purchase order."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, "Purchase Order", "Please open a company first.")
            return
        company_id = active_company["id"]
        if not self._po_nav_ids:
            self._po_nav_ids = self.db.get_po_nav_ids(company_id)
        if not self._po_nav_ids:
            QMessageBox.information(self, "Purchase Order", "No saved purchase orders found.")
            return
        current_pos = -1
        if self.current_po_id:
            try:
                current_pos = self._po_nav_ids.index(self.current_po_id)
            except ValueError:
                current_pos = -1
        if current_pos > 0:
            self.load_po_by_id(self._po_nav_ids[current_pos - 1])
        elif current_pos == -1:
            self.load_po_by_id(self._po_nav_ids[0])
        else:
            QMessageBox.information(self, "Purchase Order", "This is the first purchase order.")

    def next_po(self):
        """Open a fresh purchase order with the next sequential PO number."""
        self.open_next_numbered_entry()

    def previous_bill(self):
        self.previous_po()

    def next_bill(self):
        self.next_po()

    def load_po_by_id(self, po_id: int) -> None:
        """Load a saved purchase order into the entry form."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return
        company_id = active_company["id"]
        placeholder = self.db._get_placeholder()
        try:
            header_rows = self.db.execute_query(
                f"""
                SELECT id, po_number, date, creditor_name, grand_total, status
                FROM purchase_orders
                WHERE id = {placeholder} AND company_id = {placeholder}
                """,
                (po_id, company_id),
            ) or []
            if not header_rows:
                QMessageBox.warning(self, "Purchase Order", "Purchase order not found.")
                return
            header = header_rows[0]
            item_rows = self.db.execute_query(
                f"""
                SELECT barcode, product_name, qty, rate, discount, tax_amount, net_amount
                FROM purchase_order_items
                WHERE po_id = {placeholder}
                ORDER BY id
                """,
                (po_id,),
            ) or []
        except Exception as exc:
            QMessageBox.critical(self, "Purchase Order", f"Failed to load purchase order: {exc}")
            return

        po_number = str(header.get("po_number", "") if isinstance(header, dict) else header[1] or "")
        order_date = str(header.get("date", "") if isinstance(header, dict) else header[2] or "")
        creditor_name = str(header.get("creditor_name", "") if isinstance(header, dict) else header[3] or "")
        status = str(header.get("status", "Pending") if isinstance(header, dict) else header[5] or "Pending")

        self._is_loading = True
        self.items_table.blockSignals(True)
        self.blockSignals(True)
        self._begin_entry_reset()
        try:
            self.current_po_id = int(po_id)
            self.current_purchase_id = None
            self.purchase_no_input.setText(po_number)
            parsed_date = QDate.fromString(order_date, "yyyy-MM-dd")
            if parsed_date.isValid():
                self.date_input.setDate(parsed_date)
            self.creditor_name_input.blockSignals(True)
            self.creditor_name_input.setText(creditor_name)
            self.creditor_name_input.blockSignals(False)
            matched_creditor = None
            for creditor in getattr(self, "creditors_data", []) or []:
                if party_matches_text(creditor, creditor_name):
                    matched_creditor = creditor
                    break
            if matched_creditor:
                self._apply_creditor_to_fields(matched_creditor)
            else:
                self.selected_creditor_id = None
            if hasattr(self, "status_combo"):
                status_index = self.status_combo.findText(status, Qt.MatchFixedString)
                if status_index >= 0:
                    self.status_combo.setCurrentIndex(status_index)
                else:
                    self.status_combo.setCurrentText(status)
            self.items_table.setRowCount(0)
            self.purchase_items = []
            for line in item_rows:
                self.add_blank_row()
                row = self.items_table.rowCount() - 1
                if isinstance(line, dict):
                    barcode = str(line.get("barcode", "") or "").strip()
                    product_name = str(line.get("product_name", "") or "").strip()
                    qty = float(line.get("qty", 0) or 0)
                    rate = float(line.get("rate", 0) or 0)
                    discount = float(line.get("discount", 0) or 0)
                    tax_amount = float(line.get("tax_amount", 0) or 0)
                    net_amount = float(line.get("net_amount", 0) or 0)
                else:
                    barcode = str(line[0] if len(line) > 0 else "").strip()
                    product_name = str(line[1] if len(line) > 1 else "").strip()
                    qty = float(line[2] or 0) if len(line) > 2 else 0.0
                    rate = float(line[3] or 0) if len(line) > 3 else 0.0
                    discount = float(line[4] or 0) if len(line) > 4 else 0.0
                    tax_amount = float(line[5] or 0) if len(line) > 5 else 0.0
                    net_amount = float(line[6] or 0) if len(line) > 6 else 0.0
                product = None
                if barcode:
                    product = self.db.get_product_by_barcode(company_id, barcode)
                if not product and product_name:
                    product = self.db.get_product_by_exact_name(company_id, product_name)
                name_item = self.items_table.item(row, 2)
                if name_item:
                    name_item.setText(product.get("name", product_name) if product else product_name)
                    if product:
                        name_item.setData(Qt.UserRole, product.get("id"))
                qty_item = self.items_table.item(row, 9)
                if qty_item:
                    qty_item.setText(f"{qty:.3f}")
                rate_item = self.items_table.item(row, 8)
                if rate_item:
                    rate_item.setText(f"{rate:.2f}")
                gross = net_amount + discount
                gross_item = self.items_table.item(row, 10)
                if gross_item:
                    gross_item.setText(f"{gross:.2f}")
                net_item = self.items_table.item(row, 12)
                if net_item:
                    net_item.setText(f"{net_amount:.2f}")
                tax_item = self.items_table.item(row, 13)
                if tax_item:
                    tax_item.setText(f"{tax_amount:.2f}")
                while len(self.purchase_items) <= row:
                    self.purchase_items.append({})
                self.purchase_items[row] = {
                    "product_id": product.get("id") if product else None,
                    "barcode": barcode,
                }
            if hasattr(self, "save_btn"):
                self.save_btn.setText("Update")
            self.calculate_totals()
        finally:
            self.items_table.blockSignals(False)
            self.blockSignals(False)
            self._is_loading = False
            self._end_entry_reset()

    def on_purchase_type_changed(self):
        """PO has no amount-paid workflow; only refresh totals."""
        if getattr(self, "_is_loading", False):
            return
        self.calculate_totals()

    def apply_purchase_payment_mode(self):
        """Purchase orders do not track payments."""
        return

    def update_footer_payment_fields(self, write_amt_recvd=True):
        """Purchase orders do not track creditor payment balances."""
        return

    def refresh_theme(self):
        """Re-apply theme-aware styles after a global theme change."""
        from ui import theme as ui_theme

        super().refresh_theme()
        if hasattr(self, "stock_display"):
            self.stock_display.setStyleSheet(ui_theme.entry_value_style("accent_highlight"))
        if hasattr(self, "code_display"):
            self.code_display.setStyleSheet(ui_theme.entry_footer_value_label_style("input_text"))
        if hasattr(self, "discount_status_display"):
            self.discount_status_display.setStyleSheet(ui_theme.entry_info_value_style())
        for attr in (
            "net_amount_display",
            "net_value_display",
            "cgst_display",
            "sgst_display",
            "igst_display",
            "tax_amount_display",
            "cess_display",
        ):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setStyleSheet(ui_theme.entry_footer_value_label_style("input_text"))
        if hasattr(self, "grand_total_input"):
            self.grand_total_input.setStyleSheet(self.footer_input_readonly_style())
        if hasattr(self, "final_amount_display"):
            self.final_amount_display.setStyleSheet(self.footer_final_display_style())

    def on_amt_paid_edited(self, *args):
        """No amount-paid field on purchase orders."""
        return

    def confirm_remove_purchase(self):
        QMessageBox.information(
            self, "Purchase Order",
            "Remove entire order is not available on the PO screen. Use Reset All.",
        )

    def export_pdf(self):
        QMessageBox.information(
            self, "Purchase Order", "PDF export for purchase orders is not enabled yet."
        )

    def clear_form(self):
        """Reset the PO form and assign a fresh PO number."""
        self._begin_entry_reset()
        try:
            self.current_po_id = None
            self.current_purchase_id = None
            self.purchase_items = []
            self._purchase_nav_ids = []
            self._po_nav_ids = []
            self._amt_paid_user_edited = False
            if hasattr(self, "save_btn"):
                self.save_btn.setText("Save")

            self.purchase_no_input.clear()
            self.date_input.setDate(QDate.currentDate())
            self.purchase_type_combo.setCurrentText("Credit")
            self.series_input.clear()
            self.nature_combo.setCurrentText("Local")
            if hasattr(self, "party_type_combo"):
                self.party_type_combo.setCurrentText("Creditor")
            self.due_date_input.setDate(QDate.currentDate())
            self.creditor_name_input.clear()
            if hasattr(self, "code_input"):
                self.code_input.clear()
            self.address_input.clear()
            self.mobile_input.clear()
            self.gstin_input.clear()
            self.state_combo.setCurrentIndex(0)
            self.supplier_invoice_input.clear()
            self.narration_input.clear()
            self.barcode_input.clear()
            if hasattr(self, "product_input"):
                self.product_input.clear()
            if hasattr(self, "discount_total_input"):
                self.discount_total_input.blockSignals(True)
                self.discount_total_input.setText("0.00")
                self.discount_total_input.blockSignals(False)
            if hasattr(self, "discount_percent_label"):
                self.discount_percent_label.setText("")
            if hasattr(self, "discount_status_display"):
                self.discount_status_display.setText("0%")
            self.round_off_input.setText("0")
            if hasattr(self, "status_combo"):
                self.status_combo.setCurrentText("Pending")
            self.selected_creditor_id = None
            self._party_fields_locked = False
            if hasattr(self, "_unlock_party_fields"):
                self._unlock_party_fields()
            if hasattr(self, "purchase_checkbox"):
                self.purchase_checkbox.setChecked(False)

            self.items_table.setRowCount(0)
            self.purchase_items = []
            for _ in range(10):
                self.add_blank_row()

            self.calculate_totals()
            self.generate_po_number()
            QTimer.singleShot(0, lambda: self.barcode_input.setFocus())
        finally:
            self._end_entry_reset()

    def save(self):
        """Save purchase order header and lines (no stock or ledger posting)."""
        if getattr(self, "_is_loading", False):
            return {"success": False, "message": "Form is loading."}

        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, "Error", "No active company selected.")
            return {"success": False, "message": "No active company selected."}

        company_id = active_company["id"]
        po_number = self.purchase_no_input.text().strip()
        order_date = qdate_to_db(self.date_input.date())
        creditor_name = strip_party_display_code(
            self.creditor_name_input.text().strip()
        )
        status = (
            self.status_combo.currentText().strip()
            if hasattr(self, "status_combo")
            else "Pending"
        )
        grand_total = self._safe_float(self.grand_total_input.text())

        if not creditor_name:
            QMessageBox.warning(self, "Validation Error", "Please enter creditor name.")
            return {"success": False, "message": "Missing creditor name."}
        if not po_number:
            QMessageBox.warning(self, "Validation Error", "Please enter PO number.")
            return {"success": False, "message": "Missing PO number."}

        for row in range(self.items_table.rowCount()):
            product_name = self.safe_item_text(row, 2)
            if product_name and product_name.strip():
                self.recalculate_row(row, source_column=None)

        line_items = []
        for row in range(self.items_table.rowCount()):
            try:
                product_name = self.safe_item_text(row, 2)
                if not product_name or not product_name.strip():
                    continue
                qty = self.safe_float_from_cell(row, 9)
                if qty <= 0:
                    continue
                gross = self.safe_float_from_cell(row, 10)
                net_amount = self.safe_float_from_cell(row, 12)
                meta = self.purchase_items[row] if row < len(self.purchase_items) else {}
                barcode = str(meta.get("barcode", "") or "")
                product_id = meta.get("product_id")
                if not barcode and product_id:
                    product = self.products_dict.get(product_id)
                    if product:
                        barcode = str(product.get("barcode", "") or "")
                line_items.append({
                    "barcode": barcode,
                    "product_name": product_name.strip(),
                    "qty": qty,
                    "rate": self.safe_float_from_cell(row, 8),
                    "discount": round(gross - net_amount, 2),
                    "tax_amount": self.safe_float_from_cell(row, 13),
                    "net_amount": net_amount,
                })
                if row % 5 == 0:
                    QCoreApplication.processEvents()
            except Exception:
                continue

        if not line_items:
            QMessageBox.warning(
                self, "Validation Error",
                "Please add at least one item with a product and quantity.",
            )
            return {"success": False, "message": "No line items."}

        ph = self.db._get_placeholder()
        conn = None
        updating = bool(self.current_po_id)
        try:
            dup_rows = self.db.execute_query(
                f"""
                SELECT id FROM purchase_orders
                WHERE company_id = {ph} AND po_number = {ph}
                """,
                (company_id, po_number),
            )
            if dup_rows:
                existing_id = dup_rows[0].get("id") if isinstance(dup_rows[0], dict) else dup_rows[0][0]
                if not updating or int(existing_id or 0) != int(self.current_po_id):
                    QMessageBox.warning(
                        self, "Validation Error",
                        f"PO number '{po_number}' already exists.",
                    )
                    return {"success": False, "message": "Duplicate PO number."}

            conn = self.db.connect()
            cursor = conn.cursor()
            if updating:
                po_id = int(self.current_po_id)
                cursor.execute(
                    f"""
                    UPDATE purchase_orders
                    SET po_number = {ph},
                        date = {ph},
                        creditor_name = {ph},
                        grand_total = {ph},
                        status = {ph}
                    WHERE id = {ph} AND company_id = {ph}
                    """,
                    (
                        po_number,
                        order_date,
                        creditor_name,
                        grand_total,
                        status,
                        po_id,
                        company_id,
                    ),
                )
                cursor.execute(
                    f"DELETE FROM purchase_order_items WHERE po_id = {ph}",
                    (po_id,),
                )
                success_message = f"Purchase Order {po_number} updated successfully."
            else:
                cursor.execute(
                    f"""
                    INSERT INTO purchase_orders (
                        company_id, po_number, date, creditor_name, grand_total, status
                    ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (
                        company_id,
                        po_number,
                        order_date,
                        creditor_name,
                        grand_total,
                        status,
                    ),
                )
                po_id = (
                    self.db._get_last_insert_id(cursor)
                    if hasattr(self.db, "_get_last_insert_id")
                    else cursor.lastrowid
                )
                success_message = f"Purchase Order {po_number} saved successfully."

            item_sql = f"""
                INSERT INTO purchase_order_items (
                    po_id, barcode, product_name, qty, rate, discount,
                    tax_amount, net_amount
                ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """
            for item in line_items:
                cursor.execute(
                    item_sql,
                    (
                        po_id,
                        item["barcode"],
                        item["product_name"],
                        item["qty"],
                        item["rate"],
                        item["discount"],
                        item["tax_amount"],
                        item["net_amount"],
                    ),
                )

            conn.commit()
            QMessageBox.information(self, "Success", success_message)
            self.clear_form()
            return {"success": True, "po_id": po_id, "po_number": po_number}
        except Exception as exc:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            QMessageBox.critical(self, "Error", f"Failed to save purchase order: {exc}")
            return {"success": False, "message": str(exc)}
        finally:
            if conn:
                self.db.disconnect()