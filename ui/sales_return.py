"""
Sales Return main widget.
Full implementation: barcode/product flow, table keyboard nav, GST nature,
return type logic, save/update/delete, prev/next navigation.
"""
import json
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidgetItem, QMessageBox, QAbstractItemView
from PySide6.QtCore import Qt, QDate, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from bizora_core.sales_return_logic import SalesReturnLogic
from bizora_core.party_balance_engine import PartyBalanceEngine
from config import active_company_manager
from bizora_core.print_settings_logic import get_print_settings
try:
    from utils.a4_print_engine import print_a4_receipt
except ImportError:
    print_a4_receipt = None
from utils.a4_voucher_print_helpers import company_print_data, generate_transaction_voucher_html
from .sales_return_ui import SalesReturnUIMixin
from .sales_return_calculations import SalesReturnCalculationsMixin
from .sales_return_helpers import SalesReturnHelpersMixin
from .sales_return_popup import SalesReturnPopupMixin
from .sales_return_delegate import SalesReturnDelegate
from ui.party_display import party_matches_text
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
from ui.entry_voucher_mixin import EntryVoucherMixin
from bizora_core.settings_logic import confirm_before_delete_transaction

class SalesReturnPageWidget(EntryVoucherMixin, UiMemoryMixin, QWidget, SalesReturnUIMixin, SalesReturnCalculationsMixin, SalesReturnHelpersMixin, SalesReturnPopupMixin):
    """Main Sales Return widget."""
    voucher_type = "sales_return"
    voucher_number_attr = "return_no_input"

    def __init__(self, main_window, db, company_id=None, opened_from_sales_entry=False, sales_entry_widget=None, sales_grand_total=0.0):
        super().__init__()
        self.main_window = main_window
        self.db = db
        self.company_id = company_id
        self.sales_return_logic = SalesReturnLogic(db)
        self.balance_engine = PartyBalanceEngine(db)
        from bizora_core.product_logic import ProductLogic
        self.product_logic = ProductLogic(db)
        from bizora_core.stock_logic import StockLogic
        self.stock_logic = StockLogic(db)
        self.current_return_id = None
        self.current_party_id = None
        self.current_product_id = None
        self.current_product_data = {}
        self.returns_list = []
        self.current_index = -1
        self.selected_sl_row = -1
        self.manually_selected_row = -1
        self.last_barcode_filled_row = -1
        self._popup_product_selected = False
        self._opened_from_sales_entry = opened_from_sales_entry
        self._sales_entry_widget = sales_entry_widget
        self._sales_entry_original_total = sales_grand_total
        self._on_sales_entry_save_callback = None
        self._sales_entry_window = None
        from . import theme
        self.gst_state_codes = theme.GST_STATE_CODES
        self.setup_ui()
        self.setup_connections()
        self._init_entry_voucher_state()
        self._install_entry_unsaved_guard()
        self._install_voucher_number_lookup()
        self.load_returns_list()
        self._init_ui_memory()

    def setup_ui(self):
        from ui import theme
        self.setStyleSheet(theme.entry_page_background_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        layout.addWidget(self.build_page_header_strip())
        layout.addWidget(self.build_return_command_strip())
        layout.addWidget(self.build_party_information_matrix())
        layout.addWidget(self.build_product_entry_matrix())
        layout.addWidget(self.build_bill_options_strip())
        layout.addWidget(self.build_items_table(), 1)
        layout.addWidget(self.build_footer_summary_strip())
        self._delegate = SalesReturnDelegate(self.items_table, self)
        self.items_table.setItemDelegate(self._delegate)
        self.items_table.installEventFilter(self)
        self.items_table.viewport().installEventFilter(self)
        try:
            from ui.financial_year_guard import apply_financial_year_guard_to_named_dates
            apply_financial_year_guard_to_named_dates(self, 'date_input')
        except Exception:
            pass

    def setup_connections(self):
        self.nature_combo.currentTextChanged.connect(self.on_nature_changed)
        self.return_type_combo.currentTextChanged.connect(self.on_return_type_changed)
        self.amount_refunded_input.editingFinished.connect(self.on_amount_refunded_changed)
        self.round_off_input.editingFinished.connect(self.on_round_off_changed)
        self.round_off_checkbox.setChecked(True)
        self.round_off_checkbox.stateChanged.connect(lambda _state: self.recalculate_summary())
        self.discount_total_input.textChanged.connect(self.on_footer_discount_changed)
        self.discount_total_input.installEventFilter(self)
        self._install_select_all_on_click(self.discount_total_input)
        self.address_input.textChanged.connect(lambda _text: self.capitalize_field(self.address_input))
        self.narration_input.textChanged.connect(self.on_narration_changed)
        self.items_table.itemSelectionChanged.connect(self.on_item_selection_changed)
        self.items_table.itemChanged.connect(self.on_item_changed)
        self.divide_tax_tick.stateChanged.connect(lambda _state: self.recalculate_all_rows())
        self.rate_selector_combo.currentTextChanged.connect(lambda _text: self.on_rate_refresh_clicked())
        self._load_product_filter_options()
        self.barcode_input.returnPressed.connect(self.on_barcode_enter)
        self.product_input.installEventFilter(self)
        self._install_topbar_event_filters()

    def _install_topbar_event_filters(self):
        """Install keyboard navigation filters on the top-bar fields."""
        for field in [self.return_no_input, self.date_input, self.return_type_combo, self.nature_combo, self.party_type_combo, self.customer_name_input, self.address_input, self.mobile_input, self.gstin_input, self.state_combo, self.original_bill_input, self.narration_input, self.barcode_input, self.product_input, self.category_combo, self.size_combo, self.color_combo, self.rate_selector_combo]:
            field.installEventFilter(self)
        if self.state_combo.lineEdit():
            self.state_combo.lineEdit().installEventFilter(self)

    def _topbar_focus_chain(self):
        return [self.return_no_input, self.date_input, self.return_type_combo, self.nature_combo, self.party_type_combo, self.customer_name_input, self.address_input, self.mobile_input, self.gstin_input, self.state_combo, self.original_bill_input, self.narration_input, self.barcode_input, self.product_input, self.category_combo, self.size_combo, self.color_combo, self.rate_selector_combo]

    def _install_select_all_on_click(self, line_edit):
        original_mouse_press = line_edit.mousePressEvent

        def select_all_mouse_press(event):
            original_mouse_press(event)
            QTimer.singleShot(0, line_edit.selectAll)
        line_edit.mousePressEvent = select_all_mouse_press

    def _combo_text(self, combo):
        return combo.currentText().strip() if hasattr(combo, 'currentText') else ''

    def _load_product_filter_options(self):
        company_id = self.get_current_company_id()
        if not company_id:
            return
        try:
            products = self.db.get_products_by_company(company_id)
        except Exception:
            products = []

        def fill_combo(combo, values):
            current = combo.currentText().strip()
            combo.blockSignals(True)
            try:
                combo.clear()
                combo.addItem('')
                for value in sorted({str(v).strip() for v in values if str(v or '').strip()}):
                    combo.addItem(value)
                if current:
                    idx = combo.findText(current, Qt.MatchFixedString)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    else:
                        combo.setEditText(current)
            finally:
                combo.blockSignals(False)
        fill_combo(self.category_combo, [p.get('category') for p in products])
        fill_combo(self.size_combo, [p.get('size') for p in products])
        fill_combo(self.color_combo, [p.get('color') for p in products])

    def _product_matches_top_filters(self, product):
        category = self._combo_text(self.category_combo).lower()
        size = self._combo_text(self.size_combo).lower()
        color = self._combo_text(self.color_combo).lower()
        if category and str(product.get('category', '') or '').strip().lower() != category:
            return False
        if size and str(product.get('size', '') or '').strip().lower() != size:
            return False
        if color and str(product.get('color', '') or '').strip().lower() != color:
            return False
        return True

    def _set_product_filter_values(self, product):
        for combo, field in ((self.category_combo, 'category'), (self.size_combo, 'size'), (self.color_combo, 'color')):
            value = str(product.get(field, '') or '')
            combo.blockSignals(True)
            try:
                idx = combo.findText(value, Qt.MatchFixedString)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setEditText(value)
            finally:
                combo.blockSignals(False)

    def get_product_rate_from_selector(self, product):
        rate_selection = self.rate_selector_combo.currentText()
        if rate_selection == 'Purchase Rate':
            return product.get('purchase_rate', 0)
        if rate_selection == 'Wholesale Rate':
            return product.get('wholesale_rate', 0)
        if rate_selection == 'MRP':
            return product.get('mrp', 0)
        return product.get('sale_price', product.get('rate', 0))

    def on_rate_refresh_clicked(self):
        self.items_table.blockSignals(True)
        try:
            for row in range(self.items_table.rowCount()):
                product_cell = self.items_table.item(row, self.COL_PRODUCT)
                if not product_cell or not product_cell.text().strip():
                    continue
                product_id = product_cell.data(Qt.UserRole)
                company_id = self.get_current_company_id()
                product = self.db.get_product_by_id(company_id, product_id) if company_id and product_id else None
                if not product:
                    continue
                rate_item = self.items_table.item(row, self.COL_RATE)
                if rate_item:
                    rate_item.setText(self.format_num(self.get_product_rate_from_selector(product)))
        finally:
            self.items_table.blockSignals(False)
        self.recalculate_all_rows()

    def _focus_widget(self, widget):
        widget.setFocus()
        if hasattr(widget, 'selectAll') and (not getattr(widget, 'isReadOnly', lambda: False)()):
            widget.selectAll()

    def _focus_next_from_topbar(self, obj):
        chain = self._topbar_focus_chain()
        if obj is self.state_combo.lineEdit():
            obj = self.state_combo
        try:
            idx = chain.index(obj)
        except ValueError:
            return False
        if idx + 1 < len(chain):
            self._focus_widget(chain[idx + 1])
            return True
        return False

    def _focus_previous_from_topbar(self, obj):
        chain = self._topbar_focus_chain()
        if obj is self.state_combo.lineEdit():
            obj = self.state_combo
        try:
            idx = chain.index(obj)
        except ValueError:
            return False
        if idx > 0:
            self._focus_widget(chain[idx - 1])
            return True
        return False

    def _handle_topbar_key(self, obj, event):
        if obj is self.state_combo.lineEdit():
            obj = self.state_combo
        key = event.key()
        if obj is self.customer_name_input and key in (Qt.Key_Return, Qt.Key_Enter):
            self.address_input.setFocus()
            self.address_input.selectAll()
            return True
        if obj is self.customer_name_input and key == Qt.Key_Tab:
            self.show_party_popup()
            self.address_input.setFocus()
            self.address_input.selectAll()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            if obj is self.return_no_input:
                self.load_return_by_no()
                self._focus_next_from_topbar(obj)
                return True
            if obj is self.barcode_input:
                self.on_barcode_enter()
                return True
            if obj is self.product_input:
                self.show_product_popup()
                return True
            self._focus_next_from_topbar(obj)
            return True
        if key == Qt.Key_Backtab:
            self._focus_previous_from_topbar(obj)
            return True
        if key == Qt.Key_Escape:
            if obj is self.product_input:
                self.barcode_input.setFocus()
                self.barcode_input.selectAll()
                return True
            if obj is self.barcode_input:
                self.narration_input.setFocus()
                self.narration_input.selectAll()
                return True
            if self._focus_previous_from_topbar(obj):
                return True
        return False

    def focus_table_cell_editor(self, row: int, col: int):
        """Set current cell, scroll to it, open editor (only for editable cols), select-all text."""
        if row < 0 or row >= self.items_table.rowCount():
            return
        self.items_table.setCurrentCell(row, col)
        item = self.items_table.item(row, col)
        if item:
            self.items_table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
        if col in (self.COL_RATE, self.COL_QTY, self.COL_DISC):
            self.items_table.edit(self.items_table.currentIndex())
            QTimer.singleShot(30, self._select_all_in_current_editor)

    def _scroll_row_into_view(self, row: int) -> None:
        """Scroll a return line so it is fully visible (Sales Entry barcode parity)."""
        if row < 0 or row >= self.items_table.rowCount():
            return
        target_item = self.items_table.item(row, 0)
        if target_item:
            self.items_table.scrollToItem(target_item, QAbstractItemView.PositionAtCenter)

    def _schedule_scroll_row_into_view(self, row: int) -> None:
        """Defer scroll until row insert/layout completes after barcode scans."""
        if row < 0:
            return
        QTimer.singleShot(0, lambda target_row=row: self._scroll_row_into_view(target_row))

    def _select_all_in_current_editor(self):
        editor = self.items_table.focusWidget()
        from PySide6.QtWidgets import QLineEdit
        if isinstance(editor, QLineEdit):
            editor.selectAll()

    def load_returns_list(self):
        company_id = self.get_current_company_id()
        if not company_id:
            return
        result = self.sales_return_logic.get_sales_returns(company_id)
        if result['success']:
            self.returns_list = result['data']

    def load_return_by_no(self):
        return_no = self.return_no_input.text().strip()
        if not return_no:
            return
        company_id = self.get_current_company_id()
        if not company_id:
            return
        from bizora_core.voucher_lookup import find_voucher_id

        return_id = find_voucher_id(self.db, company_id, "sales_return", return_no)
        if return_id:
            self.load_return_by_id(return_id)
            return
        for idx, r in enumerate(self.returns_list):
            if str(r.get('return_no', '')) == return_no:
                self.current_index = idx
                self._load_full_return(r)
                return
        QMessageBox.warning(self, 'Not Found', f"Return No '{return_no}' not found.")

    def load_return_by_id(self, return_id: int):
        """Load a sales return by its ID."""
        company_id = self.get_current_company_id()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        result = self.sales_return_logic.get_sales_return_by_id(company_id, return_id)
        if result.get('success') and result.get('data'):
            self._load_full_return(result['data'])
        else:
            QMessageBox.warning(self, 'Not Found', f'Sales Return ID {return_id} not found.')

    def previous_return(self):
        if not self.returns_list:
            return
        if self.current_index <= 0:
            self.current_index = 0
        else:
            self.current_index -= 1
        self._load_full_return(self.returns_list[self.current_index])

    def next_return(self):
        """Open a fresh return with the next sequential return number."""
        self.open_next_numbered_entry()

    def _install_entry_unsaved_guard(self) -> None:
        """Track edits so closing an entry page can prompt to save."""
        self._install_unsaved_guard(
            [
                self.return_no_input,
                self.customer_name_input,
                self.address_input,
                self.mobile_input,
                self.gstin_input,
                self.narration_input,
                self.original_bill_input,
                self.date_input,
                self.return_type_combo,
                self.nature_combo,
                self.state_combo,
                self.amount_refunded_input if hasattr(self, 'amount_refunded_input') else None,
            ],
            table=self.items_table,
        )

    def _capture_entry_snapshot(self) -> str:
        """Serialize return header and line items for unsaved-close detection."""
        import json

        items = []
        if hasattr(self, 'items_table'):
            for row in range(self.items_table.rowCount()):
                def _cell_text(column: int) -> str:
                    item = self.items_table.item(row, column)
                    return item.text().strip() if item else ''

                items.append({
                    'name': _cell_text(1),
                    'qty': _cell_text(8),
                    'rate': _cell_text(7),
                    'disc': _cell_text(10),
                })
        payload = {
            'return_id': self.current_return_id,
            'return_no': self.return_no_input.text().strip() if hasattr(self, 'return_no_input') else '',
            'customer': self.customer_name_input.text().strip() if hasattr(self, 'customer_name_input') else '',
            'mobile': self.mobile_input.text().strip() if hasattr(self, 'mobile_input') else '',
            'address': self.address_input.text().strip() if hasattr(self, 'address_input') else '',
            'gstin': self.gstin_input.text().strip() if hasattr(self, 'gstin_input') else '',
            'narration': self.narration_input.text().strip() if hasattr(self, 'narration_input') else '',
            'original_bill': self.original_bill_input.text().strip() if hasattr(self, 'original_bill_input') else '',
            'return_type': self.return_type_combo.currentText().strip() if hasattr(self, 'return_type_combo') else '',
            'nature': self.nature_combo.currentText().strip() if hasattr(self, 'nature_combo') else '',
            'state': self.state_combo.currentText().strip() if hasattr(self, 'state_combo') else '',
            'amount_refunded': self.amount_refunded_input.text().strip() if hasattr(self, 'amount_refunded_input') else '',
            'items': items,
        }
        return json.dumps(payload, sort_keys=True, default=str)

    def _load_full_return(self, header_data: dict):
        rid = header_data['id']
        company_id = self.get_current_company_id()
        items_result = self.sales_return_logic.get_sales_return_items(rid)
        items = items_result.get('data', []) if items_result.get('success') else []
        full_data = dict(header_data)
        full_data['items'] = []
        for it in items:
            item = dict(it)
            item['product_name'] = it.get('product_name', '')
            item['cgst'] = float(it.get('cgst', 0.0))
            item['sgst'] = float(it.get('sgst', 0.0))
            item['igst'] = float(it.get('igst', 0.0))
            item['cess'] = float(it.get('cess', 0.0))
            item['rate'] = float(it.get('rate', 0.0))
            item['quantity'] = float(it.get('quantity', 0.0))
            item['gross_value'] = float(it.get('gross_value', 0.0))
            item['discount'] = float(it.get('discount', 0.0))
            item['net_value'] = float(it.get('net_value', 0.0))
            item['tax_amount'] = float(it.get('tax_amount', 0.0))
            item['grand_total'] = float(it.get('grand_total', 0.0))
            full_data['items'].append(item)
        self.load_return_data(full_data)
        self.ok_btn.setText('Update')
        self._update_balance_display()
        self._schedule_entry_baseline_finalize()

    def on_customer_name_changed(self, text):
        self.capitalize_field(self.customer_name_input)
        self._resolve_party_from_customer_text()

    def _resolve_party_from_customer_text(self):
        search_text = self.customer_name_input.text().strip()
        if not search_text:
            self.current_party_id = None
            return
        company_id = self.get_current_company_id()
        if not company_id:
            return
        try:
            for party in self.db.get_parties_by_company(company_id):
                ptype = party.get('party_type', '')
                if ptype not in ('Debitor', 'Both', 'debitor', 'both'):
                    continue
                if party_matches_text(party, search_text):
                    self.current_party_id = party.get('id')
                    self.populate_party_details(party)
                    return
        except Exception:
            return

    def capitalize_field(self, line_edit):
        text = line_edit.text()
        if text and (not text[0].isupper()):
            pos = line_edit.cursorPosition()
            line_edit.blockSignals(True)
            try:
                line_edit.setText(text[0].upper() + text[1:])
                line_edit.setCursorPosition(pos)
            finally:
                line_edit.blockSignals(False)

    def on_narration_changed(self, text):
        self.capitalize_field(self.narration_input)

    def on_gstin_changed(self, text):
        """Auto-uppercase GSTIN and auto-fill State from first 2 digits."""
        filtered = ''.join((c for c in text if c.isalnum()))[:15].upper()
        if filtered != text:
            self.gstin_input.blockSignals(True)
            cur = self.gstin_input.cursorPosition()
            self.gstin_input.setText(filtered)
            self.gstin_input.setCursorPosition(min(cur, len(filtered)))
            self.gstin_input.blockSignals(False)
        if len(filtered) >= 2 and filtered[:2].isdigit():
            state_name = self.gst_state_codes.get(filtered[:2])
            if state_name:
                self.state_combo.blockSignals(True)
                self.state_combo.setCurrentText(state_name)
                self.state_combo.blockSignals(False)
        elif not filtered:
            self.state_combo.blockSignals(True)
            self.state_combo.setCurrentIndex(0)
            self.state_combo.blockSignals(False)

    def on_barcode_enter(self):
        """Handle barcode scan: fill/reuse rows, keep one blank row, scroll like Sales Entry."""
        try:
            barcode = self.barcode_input.text().strip()
            if not barcode:
                self.product_input.setFocus()
                self.product_input.selectAll()
                return
            company_id = self.get_current_company_id()
            if not company_id:
                QMessageBox.warning(self, 'Error', 'No active company selected.')
                return
            product = self.db.get_product_by_barcode(company_id, barcode)
            if not product:
                QMessageBox.warning(self, 'Not Found', f"Barcode '{barcode}' not found.")
                self.barcode_input.selectAll()
                return
            self.current_product_id = product['id']
            self.current_product_data = product
            self._update_top_bar_for_product(product, barcode)
            existing_row = self.find_row_by_barcode(barcode)
            if existing_row >= 0:
                self.increment_row_qty(existing_row)
                self.last_barcode_filled_row = existing_row
                self._complete_barcode_scan(product, barcode)
                return
            blank_row = self.find_blank_row()
            if blank_row >= 0:
                self.fill_blank_row_with_product(blank_row, product)
                self.last_barcode_filled_row = blank_row
            else:
                self.last_barcode_filled_row = self.add_product_row_from_scan(product)
            self._complete_barcode_scan(product, barcode)
        except Exception as e:
            print(f'Error in on_barcode_enter: {str(e)}')
            import traceback
            traceback.print_exc()

    def _update_top_bar_for_product(self, product, barcode_or_code=None):
        """Refresh product strip fields after barcode scan or row selection."""
        if not product:
            return
        code_value = barcode_or_code
        if code_value is None:
            code_value = product.get('code') or product.get('barcode', '')
        if hasattr(self, 'product_input'):
            self.product_input.blockSignals(True)
            self.product_input.setText(product.get('name', ''))
            self.product_input.blockSignals(False)
        if hasattr(self, 'code_display'):
            self.code_display.setText(str(code_value or ''))
        company_id = self.get_current_company_id()
        if company_id and hasattr(self, 'stock_display'):
            try:
                stock = self.stock_logic.get_current_stock(company_id, product['id'])
            except Exception:
                stock = product.get('quantity', 0)
            self.stock_display.setText(str(stock) if stock is not None else '0')

    def _ensure_blank_row_after_barcode_scan(self):
        """Keep one ready blank row after a successful barcode scan."""
        self.add_blank_row()

    def _complete_barcode_scan(self, product, code):
        """Finalize barcode UI and align table scroll with Sales Entry behavior."""
        self.barcode_input.clear()
        self._ensure_blank_row_after_barcode_scan()
        self._schedule_scroll_row_into_view(self.last_barcode_filled_row)
        self.items_table.clearSelection()
        self.barcode_input.setFocus()
        self._update_top_bar_for_product(product, code)
        self.recalculate_summary()

    def on_product_enter(self):
        self._popup_product_selected = False
        self.show_product_popup()

    def add_product_to_items(self):
        if not self.current_product_id:
            return
        product = self.current_product_data
        if not product:
            company_id = self.get_current_company_id()
            if company_id:
                product = self.db.get_product_by_id(company_id, self.current_product_id) or {}
            else:
                return
        row = self.add_product_row_from_scan(product)
        self.last_barcode_filled_row = row
        self.recalculate_summary()
        self.clear_product_fields()
        QTimer.singleShot(0, lambda r=row: self.focus_table_cell_editor(r, self.COL_QTY))

    def add_product_to_items_without_clear(self):
        """Backward-compatible wrapper for popup flows that add the current product."""
        if not self.current_product_id:
            return
        product = self.current_product_data
        if not product:
            company_id = self.get_current_company_id()
            if company_id:
                product = self.db.get_product_by_id(company_id, self.current_product_id) or {}
            else:
                return
        row = self.add_product_row_from_scan(product)
        self.last_barcode_filled_row = row
        self.recalculate_summary()
        self.barcode_input.clear()
        self.barcode_input.setFocus()
        QTimer.singleShot(0, lambda r=row: self.focus_table_cell_editor(r, self.COL_QTY))

    def on_item_selection_changed(self):
        """Keep Qt selection cleared unless a row was chosen via SL No click."""
        if self.manually_selected_row == -1:
            self.items_table.clearSelection()
            return
        try:
            row = self.items_table.currentRow()
            if row < 0:
                return
            product_cell = self.items_table.item(row, self.COL_PRODUCT)
            if not product_cell:
                return
            product_id = product_cell.data(Qt.UserRole)
            if not product_id:
                return
            company_id = self.get_current_company_id()
            if not company_id:
                return
            product = self.db.get_product_by_id(company_id, product_id)
            if product:
                stock = self.stock_logic.get_current_stock(company_id, product_id)
                code_value = product.get('code') if product.get('code') else product.get('barcode', '')
                self.stock_display.setText(str(stock) if stock is not None else '0')
                self.code_display.setText(str(code_value) if code_value is not None else '')
                self.product_input.setText(product.get('name', ''))
        except Exception as e:
            print(f'Error in on_item_selection_changed: {str(e)}')
            import traceback
            traceback.print_exc()

    def on_item_changed(self, item):
        if item is None:
            return
        row = item.row()
        col = item.column()
        if col in (self.COL_RATE, self.COL_QTY, self.COL_DISC):
            delegate = self.items_table.itemDelegate()
            if delegate is not None and getattr(delegate, 'current_editor', None) is not None and (getattr(delegate, 'current_index', None) is not None) and (delegate.current_index.row() == row) and (delegate.current_index.column() == col):
                return
            self._recalculate_row_in_table(row)

    def _recalculate_row_in_table(self, row):
        self.items_table.blockSignals(True)
        try:
            product_cell = self.items_table.item(row, self.COL_PRODUCT)
            if not product_cell or not product_cell.text().strip():
                self.items_table.blockSignals(False)
                return
            rate = self._safe_float(self.items_table.item(row, self.COL_RATE))
            qty = self._safe_float(self.items_table.item(row, self.COL_QTY))
            disc = self._safe_float(self.items_table.item(row, self.COL_DISC))
            cgst_pct = self._safe_pct(self.items_table.item(row, self.COL_CGST))
            sgst_pct = self._safe_pct(self.items_table.item(row, self.COL_SGST))
            igst_pct = self._safe_pct(self.items_table.item(row, self.COL_IGST))
            cess_pct = self._safe_pct(self.items_table.item(row, self.COL_CESS))
            nature = self.nature_combo.currentText()
            totals = self.calculate_row_totals({'rate': rate, 'quantity': qty, 'discount': disc, 'nature': nature, 'cgst_pct': cgst_pct, 'sgst_pct': sgst_pct, 'igst_pct': igst_pct, 'cess_pct': cess_pct})

            def _set(c, val):
                cell = self.items_table.item(row, c)
                if cell:
                    cell.setText(f'{val:.2f}')
                else:
                    ni = QTableWidgetItem(f'{val:.2f}')
                    ni.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.items_table.setItem(row, c, ni)
            _set(self.COL_GROSS, totals['gross_value'])
            _set(self.COL_NET, totals['net_value'])
            _set(self.COL_TAX, totals['tax_amount'])
            _set(self.COL_TOTAL, totals['grand_total'])
        finally:
            self.items_table.blockSignals(False)
        self.recalculate_summary()

    def recalculate_row(self, row):
        self._recalculate_row_in_table(row)

    def recalculate_row_live(self, row, source_col, live_text):
        """Called by delegate on every keystroke for live footer updates.

        Reads live_text for source_col; reads committed table values for all other cols.
        """
        from PySide6.QtWidgets import QTableWidgetItem as _QTI
        product_cell = self.items_table.item(row, self.COL_PRODUCT)
        if not product_cell or not product_cell.text().strip():
            return

        def _sf(cell):
            if cell is None:
                return 0.0
            try:
                return float(cell.text().replace('%', '').replace('₹', '').replace(',', '').strip() or '0')
            except (ValueError, AttributeError):
                return 0.0

        def _live(col, default):
            if col == source_col and live_text is not None:
                t = live_text.strip()
                return float(t) if t else 0.0
            return default
        rate = _live(self.COL_RATE, _sf(self.items_table.item(row, self.COL_RATE)))
        qty = _live(self.COL_QTY, _sf(self.items_table.item(row, self.COL_QTY)))
        disc = _live(self.COL_DISC, _sf(self.items_table.item(row, self.COL_DISC)))
        cgst_pct = _sf(self.items_table.item(row, self.COL_CGST))
        sgst_pct = _sf(self.items_table.item(row, self.COL_SGST))
        igst_pct = _sf(self.items_table.item(row, self.COL_IGST))
        cess_pct = _sf(self.items_table.item(row, self.COL_CESS))
        nature = self.nature_combo.currentText()
        totals = self.calculate_row_totals({'rate': rate, 'quantity': qty, 'discount': disc, 'nature': nature, 'cgst_pct': cgst_pct, 'sgst_pct': sgst_pct, 'igst_pct': igst_pct, 'cess_pct': cess_pct})
        self.items_table.blockSignals(True)
        try:

            def _set(c, val):
                cell = self.items_table.item(row, c)
                if cell:
                    cell.setText(f'{val:.2f}')
                else:
                    ni = _QTI(f'{val:.2f}')
                    ni.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.items_table.setItem(row, c, ni)
            _set(self.COL_GROSS, totals['gross_value'])
            _set(self.COL_NET, totals['net_value'])
            _set(self.COL_TAX, totals['tax_amount'])
            _set(self.COL_TOTAL, totals['grand_total'])
        finally:
            self.items_table.blockSignals(False)
        self.recalculate_summary()

    def on_nature_changed(self):
        nature = self.nature_combo.currentText()
        self.items_table.blockSignals(True)
        for row in range(self.items_table.rowCount()):
            product_cell = self.items_table.item(row, self.COL_PRODUCT)
            if not product_cell or not product_cell.text().strip():
                continue
            product_id = product_cell.data(Qt.UserRole)
            company_id = self.get_current_company_id()
            product = self.db.get_product_by_id(company_id, product_id) if company_id and product_id else {}
            if not product:
                continue
            cgst_pct = float(product.get('cgst', 0.0) or 0.0)
            sgst_pct = float(product.get('sgst', 0.0) or 0.0)
            igst_pct = float(product.get('igst', 0.0) or 0.0)
            cess_pct = float(product.get('cess', 0.0) or 0.0)
            if nature != 'Inter-state':
                igst_pct = 0.0
                active_cgst, active_sgst, active_igst, active_cess = (cgst_pct, sgst_pct, 0.0, cess_pct)
            else:
                active_cgst, active_sgst, active_igst, active_cess = (0.0, 0.0, igst_pct, cess_pct)

            def _set_pct(c, v):
                cell = self.items_table.item(row, c)
                if cell:
                    cell.setText(f'{v:.2f}')
                else:
                    ni = QTableWidgetItem(f'{v:.2f}')
                    ni.setFlags(ni.flags() & ~Qt.ItemIsEditable)
                    ni.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.items_table.setItem(row, c, ni)
            _set_pct(self.COL_CGST, active_cgst)
            _set_pct(self.COL_SGST, active_sgst)
            _set_pct(self.COL_IGST, active_igst)
            _set_pct(self.COL_CESS, active_cess)
        self.items_table.blockSignals(False)
        self.recalculate_all_rows()

    def recalculate_all_rows(self):
        for row in range(self.items_table.rowCount()):
            self._recalculate_row_in_table(row)

    def recalculate_summary(self):
        items = self.get_items_data()
        summary = self.calculate_summary_totals(items)
        self.net_value_display.setText(self.format_num(summary['net_value']))
        self.cgst_display.setText(self.format_num(summary['cgst_total']))
        self.sgst_display.setText(self.format_num(summary['sgst_total']))
        self.igst_display.setText(self.format_num(summary['igst_total']))
        self.cess_display.setText(self.format_num(summary['cess_total']))
        self.tax_amount_display.setText(self.format_num(summary['tax_total']))
        self.grand_total_input.setText(self.format_num(summary['grand_total']))
        round_off_text = self.format_num(summary['round_off'])
        self.round_off_input.blockSignals(True)
        try:
            self.round_off_input.setText(round_off_text)
        finally:
            self.round_off_input.blockSignals(False)
        self.round_off_display.setText(round_off_text)
        final_amount = summary['rounded_total']
        self.net_amount_display.setText(self.format_num(final_amount))
        self.final_amount_display.setText(f'₹ {final_amount:.2f}')
        self._update_refunded_from_type(final_amount)

    def _update_refunded_from_type(self, final_amount: float):
        """Set Amt Refunded and Balance based on return type.

        Cash  → Amt Refunded = final_amount, Balance = 0
        Credit → Amt Refunded = 0.00, Balance = final_amount
        """
        return_type = self.return_type_combo.currentText().strip().lower()
        is_cash = return_type == 'cash'
        self.amount_refunded_input.blockSignals(True)
        try:
            if is_cash:
                self.amount_refunded_input.setText(self.format_num(final_amount))
            else:
                self.amount_refunded_input.setText('0.00')
        finally:
            self.amount_refunded_input.blockSignals(False)
        self._update_balance_display()

    def on_return_type_changed(self, *args):
        """Called when return type combo changes — re-apply refunded logic."""
        try:
            final_amount = float(self.final_amount_display.text().replace('₹', '').replace(',', '').strip() or '0')
        except ValueError:
            final_amount = 0.0
        self._update_refunded_from_type(final_amount)

    def on_amount_refunded_changed(self):
        self._update_balance_display()

    def on_round_off_changed(self):
        self.recalculate_summary()

    def on_footer_discount_changed(self, _text):
        if hasattr(self, 'discount_percent_label'):
            amount = self._safe_text_float(self.discount_total_input.text())
            if amount > 0:
                items = self.get_items_data()
                base = sum((float(item.get('grand_total', 0.0) or 0.0) for item in items))
                if base > 0:
                    pct = amount / base * 100.0
                    pct_disp = f'{pct:.0f}' if float(pct).is_integer() else f'{pct:.2f}'
                    self.discount_percent_label.setText(f'({pct_disp}%)')
                else:
                    self.discount_percent_label.setText('')
            else:
                self.discount_percent_label.setText('')
        self.recalculate_summary()

    def _safe_text_float(self, value, default=0.0):
        try:
            return float(str(value).replace(',', '').replace('₹', '').replace('%', '').strip() or default)
        except (TypeError, ValueError):
            return default

    def apply_discount_percent_mode(self):
        """Treat the footer Discount value as a percent of the pre-discount return total."""
        try:
            pct = self._safe_text_float(self.discount_total_input.text())
            if pct <= 0:
                return
            items = self.get_items_data()
            base = sum((float(item.get('grand_total', 0.0) or 0.0) for item in items))
            if base <= 0:
                return
            if pct > 100:
                pct = 100.0
            amount = round(base * pct / 100.0, 2)
            self.discount_total_input.blockSignals(True)
            try:
                self.discount_total_input.setText(f'{amount:.2f}')
            finally:
                self.discount_total_input.blockSignals(False)
            if hasattr(self, 'discount_percent_label'):
                pct_disp = f'{pct:.0f}' if float(pct).is_integer() else f'{pct:.2f}'
                self.discount_percent_label.setText(f'({pct_disp}%)')
            self.recalculate_summary()
        except Exception:
            pass

    def _update_balance_display(self):
        """Update balance display using PartyBalanceEngine for proper Previous Balance calculation.

        For Sales Return:
        - Previous Balance: Balance before current sales return voucher
        - Closing Balance = Previous Balance - Return Net Amount + Amount Refunded
        """
        try:
            final_amount = float(self.final_amount_display.text().replace('₹', '').replace(',', '').strip() or '0')
        except ValueError:
            final_amount = 0.0
        try:
            refunded = float(self.amount_refunded_input.text() or '0')
        except ValueError:
            refunded = 0.0
        previous_balance = self.get_previous_party_balance()
        closing_balance = self.balance_engine.calculate_closing_balance(previous_balance, final_amount, refunded, 'sales_return')
        self.balance_display.setText(self.format_num(closing_balance))

    def get_previous_party_balance(self):
        """Return the Previous Balance (balance before current voucher) of the selected party.

        Uses PartyBalanceEngine to calculate:
        Previous Balance = party opening_balance + unpaid previous sales - previous receipts/returns

        Excludes current return when editing/viewing old returns via voucher_id.
        Excludes future vouchers (after current voucher date/id).

        Returns 0.00 when no party found / blank / error.
        """
        try:
            if not hasattr(self, 'customer_name_input'):
                return 0.0
            name = self.customer_name_input.text().strip().lower()
            if not name:
                return 0.0
            if not hasattr(self, 'current_party_id') or not self.current_party_id:
                return 0.0
            active_company = None
            if self.main_window and hasattr(self.main_window, 'active_company'):
                active_company = self.main_window.active_company
            if not active_company:
                from config import active_company_manager
                active_company = active_company_manager.get_active_company()
            if not active_company:
                return 0.0
            voucher_id = self.current_return_id
            voucher_date = None
            if voucher_id and hasattr(self, 'return_date_input'):
                voucher_date = qdate_to_db(self.return_date_input.date())
            balance_result = self.balance_engine.get_party_balance_before_voucher(active_company['id'], self.current_party_id, 'sales_return', voucher_id=voucher_id, voucher_date=voucher_date)
            return balance_result.get('previous_balance', 0.0)
        except Exception:
            return 0.0

    def remove_current_item(self):
        target_row = getattr(self, 'manually_selected_row', -1)
        if target_row < 0:
            QMessageBox.information(
                self,
                'Remove Item',
                'Please click the SL No of the item you want to remove, then press Remove Item.',
            )
            return
        row = target_row
        if row >= self.items_table.rowCount():
            self.manually_selected_row = -1
            self.selected_sl_row = -1
            return
        product_cell = self.items_table.item(row, self.COL_PRODUCT)
        product_name = product_cell.text() if product_cell else f'Row {row + 1}'
        reply = QMessageBox.question(self, 'Remove Item', f"Remove '{product_name}' from the table?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.items_table.blockSignals(True)
            self.items_table.removeRow(row)
            for r in range(self.items_table.rowCount()):
                sl = self.items_table.item(r, self.COL_SL)
                if sl:
                    sl.setText(str(r + 1))
            self.items_table.blockSignals(False)
            self.manually_selected_row = -1
            self.selected_sl_row = -1
            self.items_table.clearSelection()
            self.items_table.viewport().update()
            self.recalculate_summary()

    def _validate_party_before_save(self):
        """Require a selected customer before saving non-cash sales returns."""
        return_type = self.return_type_combo.currentText().strip().casefold()
        if 'cash' in return_type:
            return True
        try:
            party_id = int(getattr(self, 'current_party_id', 0) or 0)
        except (TypeError, ValueError):
            party_id = 0
        if party_id > 0:
            return True
        QMessageBox.warning(self, 'Validation Error', 'Please select a Customer/Debtor before saving.')
        self.customer_name_input.setFocus()
        return False

    def _validate_and_collect(self):
        company_id = self.get_current_company_id()
        if not company_id:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return None
        if not self._validate_party_before_save():
            return None
        form_data = self.get_form_data()
        if not form_data['items']:
            QMessageBox.warning(self, 'Error', 'Add at least one item with quantity > 0.')
            return None
        return form_data

    def save_return(self):
        if self.current_return_id:
            self.update_return()
            return
        form_data = self._validate_and_collect()
        if form_data is None:
            return
        result = self.sales_return_logic.save_sales_return(form_data)
        if result['success']:
            return_id = result.get('sales_return_id')
            return_total = 0.0
            items = form_data.get('items', [])
            for item in items:
                item_total = float(item.get('grand_total', 0) or 0)
                return_total += item_total
            QMessageBox.information(self, 'Saved', f"Sales Return saved successfully.\nReturn No: {form_data['return_no']}")
            if self._opened_from_sales_entry and self._on_sales_entry_save_callback and return_id:
                self._on_sales_entry_save_callback(return_id, return_total)
                window = self.window()
                if window:
                    window.close()
                return
            self.load_returns_list()
            self.clear_form()
            self.barcode_input.setFocus()
        else:
            QMessageBox.critical(self, 'Error', result['message'])

    def update_return(self):
        if not self.current_return_id:
            QMessageBox.warning(self, 'Error', 'No return loaded for update.')
            return
        form_data = self._validate_and_collect()
        if form_data is None:
            return
        result = self.sales_return_logic.update_sales_return(self.current_return_id, form_data)
        if result['success']:
            QMessageBox.information(self, 'Updated', 'Sales Return updated successfully.')
            self.load_returns_list()
            self.ok_btn.setText('Save')
            self.current_return_id = None
            self.clear_form()
            self.barcode_input.setFocus()
        else:
            QMessageBox.critical(self, 'Error', result['message'])

    def delete_return(self):
        if not self.current_return_id:
            QMessageBox.warning(self, 'Error', 'No saved return is currently loaded.')
            return
        company_id = self.get_current_company_id()
        if not confirm_before_delete_transaction(
            self,
            'Delete Return',
            'Permanently delete this Sales Return and reverse stock movements?',
            db=self.db,
            company_id=company_id,
        ):
            return
        result = self.sales_return_logic.delete_sales_return(company_id, self.current_return_id)
        if result['success']:
            QMessageBox.information(self, 'Deleted', 'Sales Return deleted successfully.')
            self.load_returns_list()
            self.ok_btn.setText('Save')
            self.clear_form()
        else:
            QMessageBox.critical(self, 'Error', result['message'])

    def export_pdf(self):
        """Open the current Sales Return in the universal preview dialog."""
        if not self.current_return_id:
            QMessageBox.warning(self, 'Export Blocked', 'Please save the voucher before previewing.')
            return
        company_id = active_company_manager.get_active_company_id()
        active_company = active_company_manager.get_active_company()
        if not company_id or not active_company:
            QMessageBox.warning(self, 'Export Blocked', 'No active company selected.')
            return
        form_data = self.get_form_data()
        items = form_data.get('items', [])
        if not items:
            QMessageBox.warning(self, 'Preview Sales Return', 'Please add at least one item with quantity before previewing.')
            return
        try:
            settings = get_print_settings(self.db, company_id)
            html_string = generate_transaction_voucher_html(company_print_data(active_company), self._sales_return_print_data(form_data), items, settings=settings)
            dialog = UniversalPreviewDialog(html_string, self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, 'Preview Failed', f'Could not preview Sales Return:\n{exc}')

    def print_return(self):
        """Silently print the current Sales Return voucher through the A4 engine."""
        company_id = self.get_current_company_id()
        active_company = active_company_manager.get_active_company()
        if not company_id or not active_company:
            QMessageBox.warning(self, 'Print Sales Return', 'Please open a company first.')
            return
        form_data = self.get_form_data()
        items = form_data.get('items', [])
        if not items:
            QMessageBox.warning(self, 'Print Sales Return', 'Please add at least one item with quantity before printing.')
            return
        try:
            if print_a4_receipt is None:
                raise RuntimeError('A4 print engine is not available.')
            settings = get_print_settings(self.db, company_id)
            html_string = generate_transaction_voucher_html(company_print_data(active_company), self._sales_return_print_data(form_data), items, settings=settings)
            printer = self._build_silent_sales_return_printer(settings)
            print_a4_receipt(html_string, printer, settings=settings, paper_size=self._a4_paper_size_from_settings(settings))
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Could not print Sales Return:\n{exc}')

    def _build_silent_sales_return_printer(self, settings: dict) -> QPrinter:
        """Return a QPrinter using the saved normal printer when installed."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        saved_printer_name = self._saved_printer_name(settings, 'normal_printer_name')
        available_printers = self._available_printer_names()
        if saved_printer_name and saved_printer_name in available_printers:
            printer.setPrinterName(saved_printer_name)
        return printer

    def _available_printer_names(self):
        """Return installed Windows printer names for silent print selection."""
        try:
            return {printer.printerName() for printer in QPrinterInfo.availablePrinters() if printer.printerName()}
        except Exception:
            return set()

    def _saved_printer_name(self, settings, preferred_key):
        """Return a saved printer name from metadata or print settings."""
        metadata = self._print_settings_metadata(settings)
        printer_name = str(metadata.get(preferred_key) or '').strip()
        if printer_name:
            return printer_name
        printer_name = str(settings.get(preferred_key) or '').strip()
        if printer_name:
            return printer_name
        return str(settings.get('printer_name', '') or '').strip()

    def _print_settings_metadata(self, settings):
        """Return metadata embedded in saved print layout coordinates."""
        raw_coordinates = settings.get('layout_coordinates', '') or ''
        if not raw_coordinates:
            return {}
        try:
            coordinates = json.loads(raw_coordinates)
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(coordinates, dict):
            return {}
        metadata = coordinates.get('__settings__', {})
        return metadata if isinstance(metadata, dict) else {}

    def _a4_paper_size_from_settings(self, settings):
        """Return saved A4/A5 paper size for Sales Return voucher printing."""
        metadata = self._print_settings_metadata(settings)
        for key in ('a4_paper_size', 'paper_size', 'default_format'):
            value = str(metadata.get(key) or settings.get(key) or '').strip().upper()
            if value in {'A4', 'A5'}:
                return value
        return 'A4'

    def _sales_return_print_data(self, form_data):
        """Return header and totals used by Sales Return A4 HTML."""
        return {'voucher_title': 'SALES RETURN', 'party_label': 'Customer', 'party_name': self.customer_name_input.text().strip() or 'Cash Customer', 'voucher_no': form_data.get('return_no', ''), 'voucher_date': qdate_to_display(self.date_input.date()), 'voucher_type': form_data.get('return_type', ''), 'reference': form_data.get('original_bill_no', ''), 'sub_total': form_data.get('sub_total', 0.0), 'discount_total': form_data.get('discount_total', 0.0), 'tax_total': form_data.get('tax_total', 0.0), 'round_off': form_data.get('round_off', 0.0), 'grand_total': form_data.get('grand_total', 0.0), 'narration': form_data.get('narration', '')}

    def refresh(self):
        self.load_returns_list()
        if self.current_return_id:
            for r in self.returns_list:
                if r['id'] == self.current_return_id:
                    self._load_full_return(r)
                    break

    def _on_f1_edit_qty(self) -> bool:
        """Scroll to the last scanned row and open Qty edit (Sales Entry parity)."""
        target_row = self.last_barcode_filled_row
        if target_row < 0 or target_row >= self.items_table.rowCount():
            target_row = self.items_table.currentRow()
        if target_row < 0:
            return False
        product_id = self._row_product_id(target_row)
        if not product_id:
            return False
        self._scroll_row_into_view(target_row)
        company_id = self.get_current_company_id()
        if company_id:
            product = self.db.get_product_by_id(company_id, product_id)
            if product:
                self._update_top_bar_for_product(product)
        QTimer.singleShot(0, lambda r=target_row: self.focus_table_cell_editor(r, self.COL_QTY))
        return True

    def eventFilter(self, obj, event):
        """Handle table row selection, Esc on table, and product_input."""
        from PySide6.QtCore import QEvent as QEv
        if obj == self.items_table.viewport() and event.type() == QEv.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                item = self.items_table.itemAt(event.pos())
                if item:
                    clicked_row = item.row()
                    clicked_column = item.column()
                    if clicked_column == self.COL_SL:
                        self.manually_selected_row = clicked_row
                        self.selected_sl_row = clicked_row
                        self.items_table.clearSelection()
                        self.items_table.setCurrentCell(clicked_row, clicked_column)
                        self._refresh_row_status_display(clicked_row)
                        self.items_table.viewport().update()
                        return True
                    self.manually_selected_row = -1
                    self.selected_sl_row = -1
                    self.items_table.clearSelection()
                    self._refresh_row_status_display(clicked_row)
                    self.items_table.viewport().update()
                    if clicked_column in (self.COL_RATE, self.COL_QTY, self.COL_DISC):
                        self.focus_table_cell_editor(clicked_row, clicked_column)
                    return True
        if event.type() == QEv.KeyPress and event.key() == Qt.Key_F1:
            if obj is self.items_table or obj in self._topbar_focus_chain():
                if self._on_f1_edit_qty():
                    return True
        if event.type() == QEv.KeyPress and obj in self._topbar_focus_chain():
            if self._handle_topbar_key(obj, event):
                return True
        if self.state_combo.lineEdit() and obj is self.state_combo.lineEdit() and (event.type() == QEv.KeyPress):
            if self._handle_topbar_key(obj, event):
                return True
        if hasattr(self, 'discount_total_input') and obj is self.discount_total_input and (event.type() == QEv.KeyPress) and (event.key() == Qt.Key_Down):
            self.apply_discount_percent_mode()
            return True
        if event.type() == QEv.KeyPress and event.key() == Qt.Key_Escape:
            if obj is self.items_table or obj is self.product_input:
                self.barcode_input.setFocus()
                self.barcode_input.selectAll()
                return True
        return super().eventFilter(obj, event)

    def _refresh_row_status_display(self, row):
        """Refresh product strip fields for the clicked table row."""
        if row < 0:
            return
        product_cell = self.items_table.item(row, self.COL_PRODUCT)
        if not product_cell:
            return
        product_id = product_cell.data(Qt.UserRole)
        if not product_id:
            return
        company_id = self.get_current_company_id()
        if not company_id:
            return
        try:
            product = self.db.get_product_by_id(company_id, product_id)
            if product:
                self._update_top_bar_for_product(product)
        except Exception:
            pass

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F1:
            if self._on_f1_edit_qty():
                return
        if event.key() == Qt.Key_F5:
            self.refresh()
        else:
            super().keyPressEvent(event)