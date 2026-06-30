"""
Purchase Return main widget.
Full implementation: barcode/product flow, table keyboard nav, GST nature,
return type logic, save/update/delete, prev/next navigation, stock effects.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidgetItem, QMessageBox, QAbstractItemView, QLineEdit, QDoubleSpinBox
from PySide6.QtCore import Qt, QDate, QTimer, QEvent, QCoreApplication
from PySide6.QtGui import QKeyEvent
import time
from config import active_company_manager
from bizora_core.purchase_return_logic import PurchaseReturnLogic
from bizora_core.party_balance_engine import PartyBalanceEngine
from bizora_core.print_settings_logic import get_print_settings
from utils.a4_voucher_print_helpers import company_print_data, generate_transaction_voucher_html
from .purchase_return_ui import PurchaseReturnUIMixin
from .purchase_return_calculations import PurchaseReturnCalculationsMixin
from .purchase_return_helpers import PurchaseReturnHelpersMixin
from .purchase_return_popup import PurchaseReturnPopupMixin
from .purchase_return_delegate import PurchaseReturnDelegate
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
from ui.entry_voucher_mixin import EntryVoucherMixin
from bizora_core.settings_logic import confirm_before_delete_transaction

class PurchaseReturnPageWidget(EntryVoucherMixin, UiMemoryMixin, QWidget, PurchaseReturnUIMixin, PurchaseReturnCalculationsMixin, PurchaseReturnHelpersMixin, PurchaseReturnPopupMixin):
    """Main Purchase Return widget."""
    voucher_type = "purchase_return"
    voucher_number_attr = "return_no_input"

    def __init__(self, main_window, db, company_id=None):
        super().__init__()
        self.main_window = main_window
        self.db = db
        self.company_id = company_id
        self.purchase_return_logic = PurchaseReturnLogic(db)
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
        self._popup_product_selected = False
        self._amt_refunded_user_edited = False
        self.creditors_data = []
        self._last_creditor_refresh_time = 0.0
        self._creditor_selection_in_progress = False
        self._initial_load_done = False
        self._deferred_load_started = False
        from . import theme
        self.gst_state_codes = theme.GST_STATE_CODES
        self.setup_ui()
        self.setup_connections()
        self._init_entry_voucher_state()
        self._install_entry_unsaved_guard()
        self._install_voucher_number_lookup()
        QTimer.singleShot(100, self._load_heavy_data)
        self._init_ui_memory()

    def _load_heavy_data(self):
        """Load database-backed values after the first paint completes."""
        if self._initial_load_done or self._deferred_load_started:
            return
        self._deferred_load_started = True
        try:
            self.load_creditors()
            QCoreApplication.processEvents()
            self.load_returns_list()
            QCoreApplication.processEvents()
            self._prepare_new_return_number()
            self._initial_load_done = True
        finally:
            self._deferred_load_started = False

    def _prepare_new_return_number(self):
        """Fill the next return number only after deferred DB loading."""
        if self.current_return_id:
            return
        if self.return_no_input.text().strip():
            return
        self.return_no_input.setText(self.get_next_return_no())

    def setup_ui(self):
        from ui import theme
        self.setStyleSheet(theme.entry_page_background_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        layout.addWidget(self.build_page_header_strip())
        layout.addWidget(self.build_return_command_strip())
        layout.addWidget(self.build_party_information_matrix())
        layout.addWidget(self.build_product_entry_strip())
        layout.addWidget(self.build_bill_options_strip())
        layout.addWidget(self.build_items_table(), 1)
        layout.addWidget(self.build_lower_control_panel())
        self._delegate = PurchaseReturnDelegate(self.items_table, self)
        self.items_table.setItemDelegate(self._delegate)
        self.items_table.installEventFilter(self)
        try:
            from ui.financial_year_guard import apply_financial_year_guard_to_named_dates
            apply_financial_year_guard_to_named_dates(self, 'date_input', 'due_date_input')
        except Exception:
            pass

    def setup_connections(self):
        self.nature_combo.currentTextChanged.connect(self.on_nature_changed)
        self.return_type_combo.currentTextChanged.connect(self.on_return_type_changed)
        self.items_table.itemSelectionChanged.connect(self.on_item_selection_changed)
        self.items_table.itemChanged.connect(self.on_item_changed)
        self.items_table.cellClicked.connect(self.on_cell_clicked)
        self.supplier_name_input.textChanged.connect(self._handle_party_name_changed)
        self.barcode_input.returnPressed.connect(self.on_barcode_enter)
        self.product_input.installEventFilter(self)
        self.barcode_input.installEventFilter(self)
        for widget in self._top_bar_navigation_fields():
            if widget is not None:
                widget.installEventFilter(self)
        state_editor = self.state_combo.lineEdit() if self.state_combo.isEditable() else None
        if state_editor is not None:
            state_editor.installEventFilter(self)
        self.round_off_input.textChanged.connect(self.on_round_off_changed)
        self.amount_refunded_input.textChanged.connect(self.on_amount_refunded_changed)
        self._setup_creditor_completer()
        self._install_select_all_event_filters()

    def _install_select_all_event_filters(self):
        """Register all Purchase Return text and numeric inputs for select-all focus."""
        for widget in self.findChildren(QLineEdit):
            widget.installEventFilter(self)
        for widget in self.findChildren(QDoubleSpinBox):
            widget.installEventFilter(self)

    def _select_all_text_on_focus(self, widget):
        """Defer text selection so mouse focus does not place the cursor afterward."""
        if isinstance(widget, QLineEdit):
            if not widget.isReadOnly():
                QTimer.singleShot(0, widget.selectAll)
            return
        if isinstance(widget, QDoubleSpinBox):
            if hasattr(widget, 'isReadOnly') and widget.isReadOnly():
                return
            if hasattr(widget, 'selectAll'):
                QTimer.singleShot(0, widget.selectAll)
                return
            editor = widget.lineEdit()
            if editor is not None and (not editor.isReadOnly()):
                QTimer.singleShot(0, editor.selectAll)

    def _top_bar_navigation_fields(self):
        """Return Purchase Return top-bar fields in forward keyboard order."""
        return [self.supplier_name_input, self.address_input, self.mobile_input, self.gstin_input, self.state_combo, self.original_purchase_input, self.supplier_invoice_input, self.narration_input, self.barcode_input]

    def _normalize_top_bar_navigation_obj(self, obj):
        """Map editable combo internals back to their top-bar field widget."""
        if obj == self.state_combo:
            return self.state_combo
        state_editor = self.state_combo.lineEdit() if self.state_combo.isEditable() else None
        if state_editor is not None and obj == state_editor:
            return self.state_combo
        return obj

    def _focus_top_bar_field(self, widget):
        """Move focus to a top-bar field and select editable text."""
        widget.setFocus(Qt.TabFocusReason)
        if isinstance(widget, QLineEdit):
            widget.selectAll()
            return
        if widget == self.state_combo and self.state_combo.isEditable():
            editor = self.state_combo.lineEdit()
            if editor is not None:
                editor.setFocus(Qt.TabFocusReason)
                editor.selectAll()

    def _handle_top_bar_navigation_key(self, obj, key):
        """Handle Tab popup trigger plus Enter/Escape top-bar navigation."""
        field = self._normalize_top_bar_navigation_obj(obj)
        fields = self._top_bar_navigation_fields()
        if field not in fields:
            return False
        if field == self.supplier_name_input and key == Qt.Key_Tab:
            QTimer.singleShot(0, self.show_party_popup)
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter):
            index = fields.index(field)
            if index < len(fields) - 1:
                self._focus_top_bar_field(fields[index + 1])
                return True
            return False
        if key == Qt.Key_Escape:
            index = fields.index(field)
            if index > 0:
                self._focus_top_bar_field(fields[index - 1])
                return True
            return True
        return False

    def showEvent(self, event):
        """Refresh creditors when widget is shown."""
        super().showEvent(event)
        if not self._initial_load_done:
            return
        current_time = time.time()
        if current_time - self._last_creditor_refresh_time > 2.0:
            self.load_creditors()

    def changeEvent(self, event):
        """Refresh creditors on window activation."""
        super().changeEvent(event)
        if not self._initial_load_done:
            return
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            current_time = time.time()
            if current_time - self._last_creditor_refresh_time > 1.0:
                self.load_creditors()

    def load_creditors(self):
        """Load Creditor/Both parties from DB into self.creditors_data and refresh completer."""
        from config import active_company_manager
        from bizora_core.party_logic import PartyLogic
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return
        if not hasattr(self, '_party_logic'):
            self._party_logic = PartyLogic(self.db)
        result = self._party_logic.get_parties(active_company['id'])
        QCoreApplication.processEvents()
        if isinstance(result, dict) and 'data' in result:
            all_parties = result['data']
        elif isinstance(result, list):
            all_parties = result
        else:
            all_parties = []
        self.creditors_data = [p for p in all_parties if isinstance(p, dict) and p.get('party_type', '').lower() in ('creditor', 'both', '')]
        self._setup_creditor_completer()
        self._last_creditor_refresh_time = time.time()
        QCoreApplication.processEvents()

    def refresh_creditors(self):
        """Public slot — called by MainWindow after party_saved signal."""
        self.load_creditors()

    def _setup_creditor_completer(self):
        """Wire the creditor name completer onto supplier_name_input."""
        from .purchase_entry_popup import setup_creditor_completer
        setup_creditor_completer(self.supplier_name_input, self, self._on_creditor_selected)

    def _set_default_party_type_to_creditors(self):
        """Select Creditors in the party type combo after it is populated."""
        index = self.party_type_combo.findText('Creditors', Qt.MatchFixedString)
        if index < 0:
            for item_index in range(self.party_type_combo.count()):
                item_text = self.party_type_combo.itemText(item_index)
                normalized = item_text.casefold().rstrip('s')
                if normalized == 'creditor':
                    index = item_index
                    break
        if index >= 0:
            self.party_type_combo.setCurrentIndex(index)

    def _handle_party_name_changed(self, text):
        """Clear dependent party fields when party name is exactly empty."""
        if text == '':
            self.current_party_id = None
            self.address_input.clear()
            self.mobile_input.clear()
            self.gstin_input.clear()
            self.state_combo.setCurrentIndex(0)
            return
        self._on_supplier_name_changed_guard(text)

    def _on_supplier_name_changed_guard(self, text):
        """Only apply title-case when not in the middle of creditor selection."""
        if self._creditor_selection_in_progress:
            return
        self.on_supplier_name_changed(text)

    def _on_creditor_selected(self, model_idx, editor):
        """Handle creditor selection from the completer dropdown."""
        from PySide6.QtCore import Qt
        creditor = model_idx.data(Qt.UserRole)
        if not creditor:
            return
        self._creditor_selection_in_progress = True
        try:
            if isinstance(creditor, dict):
                self.current_party_id = creditor.get('id')
                self.supplier_name_input.blockSignals(True)
                self.supplier_name_input.setText(creditor.get('name', ''))
                self.supplier_name_input.blockSignals(False)
                self.address_input.setText(creditor.get('address', '') or '')
                self.mobile_input.setText(creditor.get('mobile_number', '') or '')
                gstin = creditor.get('gstin', '') or ''
                self.gstin_input.blockSignals(True)
                self.gstin_input.setText(gstin)
                self.gstin_input.blockSignals(False)
                state = creditor.get('state', '') or ''
                if state:
                    self.state_combo.blockSignals(True)
                    self.state_combo.setCurrentText(state)
                    self.state_combo.blockSignals(False)
                elif gstin and len(gstin) >= 2:
                    state_code = gstin[:2].upper()
                    derived = self.gst_state_codes.get(state_code, '')
                    if derived:
                        self.state_combo.blockSignals(True)
                        self.state_combo.setCurrentText(derived)
                        self.state_combo.blockSignals(False)
            else:
                self.supplier_name_input.blockSignals(True)
                self.supplier_name_input.setText(str(creditor))
                self.supplier_name_input.blockSignals(False)
        finally:
            self._creditor_selection_in_progress = False
        self._update_balance_display()

    def focus_table_cell_editor(self, row: int, col: int):
        """Set current cell, scroll to it, open editor with text fully selected."""
        if row < 0 or row >= self.items_table.rowCount():
            return
        self.items_table.setCurrentCell(row, col)
        item = self.items_table.item(row, col)
        if item:
            self.items_table.scrollToItem(item)
        self.items_table.setFocus()
        editable = (self.COL_HSN, self.COL_CGST, self.COL_SGST, self.COL_IGST, self.COL_CESS, self.COL_RATE, self.COL_QTY, self.COL_GROSS, self.COL_DISC)
        if col in editable:
            self.items_table.edit(self.items_table.currentIndex())
            QTimer.singleShot(30, self._select_all_in_current_editor)

    def _select_all_in_current_editor(self):
        from PySide6.QtWidgets import QLineEdit
        editor = self.items_table.focusWidget()
        if isinstance(editor, QLineEdit):
            editor.selectAll()

    def load_returns_list(self):
        company_id = self.get_current_company_id()
        if not company_id:
            return
        result = self.purchase_return_logic.get_purchase_returns(company_id)
        QCoreApplication.processEvents()
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

        return_id = find_voucher_id(self.db, company_id, "purchase_return", return_no)
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
        """Load a purchase return by its ID."""
        company_id = self.get_current_company_id()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        result = self.purchase_return_logic.get_purchase_return_by_id(company_id, return_id)
        if result.get('success') and result.get('data'):
            self._load_full_return(result['data'])
        else:
            QMessageBox.warning(self, 'Not Found', f'Purchase Return ID {return_id} not found.')

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
                self.supplier_name_input,
                self.address_input,
                self.mobile_input,
                self.gstin_input,
                self.narration_input,
                self.original_purchase_input,
                self.supplier_invoice_input,
                self.date_input,
                self.return_type_combo,
                self.nature_combo,
                self.state_combo,
                self.amount_refunded_input if hasattr(self, 'amount_refunded_input') else None,
            ],
            table=self.items_table,
        )

    def _load_full_return(self, header_data: dict):
        rid = header_data['id']
        items_result = self.purchase_return_logic.get_purchase_return_items(rid)
        items = items_result.get('data', []) if items_result.get('success') else []
        full_data = dict(header_data)
        full_data['items'] = []
        for it in items:
            item = {'product_id': it.get('product_id'), 'product_name': it.get('product_name', ''), 'hsn': it.get('hsn', '') or '', 'sale_rate': float(it.get('sale_rate', 0.0) or 0.0), 'cgst': float(it.get('cgst', 0.0) or 0.0), 'sgst': float(it.get('sgst', 0.0) or 0.0), 'igst': float(it.get('igst', 0.0) or 0.0), 'cess': float(it.get('cess', 0.0) or 0.0), 'rate': float(it.get('rate', 0.0) or 0.0), 'quantity': float(it.get('quantity', 0.0) or 0.0), 'gross_value': float(it.get('gross_value', 0.0) or 0.0), 'discount': float(it.get('discount', 0.0) or 0.0), 'net_value': float(it.get('net_value', 0.0) or 0.0), 'cgst_amt': float(it.get('cgst_amount', 0.0) or 0.0), 'sgst_amt': float(it.get('sgst_amount', 0.0) or 0.0), 'igst_amt': float(it.get('igst_amount', 0.0) or 0.0), 'cess_amt': float(it.get('cess_amount', 0.0) or 0.0), 'tax_amount': float(it.get('tax_amount', 0.0) or 0.0), 'grand_total': float(it.get('grand_total', 0.0) or 0.0)}
            full_data['items'].append(item)
        self.load_return_data(full_data)
        self.save_btn.setText('Update')
        self._update_balance_display()

    def on_supplier_name_changed(self, text):
        """Handle supplier name text change - apply title case formatting."""
        if not text:
            return
        was_blocked = self.supplier_name_input.blockSignals(True)
        try:
            self.supplier_name_input.setText(text.title())
        finally:
            self.supplier_name_input.blockSignals(was_blocked)

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

    def on_state_changed(self, text):
        """Handle state change - auto-detect nature from state code."""
        if not text:
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return
        company_state = ''
        if text == company_state:
            self.nature_combo.setCurrentText('Local')
        else:
            self.nature_combo.setCurrentText('Inter-state')

    def on_barcode_enter(self):
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
            if product:
                self.current_product_id = product['id']
                self.current_product_data = product
                self.product_input.blockSignals(True)
                self.product_input.setText(product['name'])
                self.product_input.blockSignals(False)
                stock = self.stock_logic.get_current_stock(company_id, product['id'])
                code_value = product.get('code') if product.get('code') else barcode
                self.stock_display.setText(str(stock) if stock is not None else '0')
                self.code_display.setText(str(code_value) if code_value is not None else '')
                self.barcode_input.clear()
                self.add_product_to_items_without_clear()
            else:
                QMessageBox.warning(self, 'Not Found', f"Barcode '{barcode}' not found.")
                self.barcode_input.selectAll()
        except Exception as e:
            print(f'Error in on_barcode_enter: {str(e)}')
            import traceback
            traceback.print_exc()

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
        rate = float(product.get('purchase_rate') or product.get('cost_price') or product.get('sale_price') or 0.0)
        quantity = 1.0
        discount = 0.0
        totals = self.calculate_row_totals({'rate': rate, 'quantity': quantity, 'discount': discount, 'nature': nature, 'cgst_pct': cgst_pct, 'sgst_pct': sgst_pct, 'igst_pct': igst_pct, 'cess_pct': cess_pct})
        sale_rate = float(product.get('sale_price') or 0.0)
        item_data = {'product_id': product.get('id') or self.current_product_id, 'product_name': product.get('name', ''), 'sale_rate': sale_rate, 'hsn': product.get('hsn', '') or '', 'cgst': cgst_pct, 'sgst': sgst_pct, 'igst': igst_pct, 'cess': cess_pct, 'rate': rate, 'quantity': quantity, 'discount': discount, 'gross_value': totals['gross_value'], 'net_value': totals['net_value'], 'tax_amount': totals['tax_amount'], 'grand_total': totals['grand_total']}
        sl_no = self.items_table.rowCount() + 1
        self.add_item_to_table(item_data, sl_no)
        self.recalculate_summary()
        self.clear_product_fields()
        last_row = self.items_table.rowCount() - 1
        QTimer.singleShot(0, lambda r=last_row: self.focus_table_cell_editor(r, self.COL_QTY))

    def add_product_to_items_without_clear(self):
        """Add product to items without clearing stock/code displays (for scanner)."""
        if not self.current_product_id:
            return
        product = self.current_product_data
        if not product:
            company_id = self.get_current_company_id()
            if company_id:
                product = self.db.get_product_by_id(company_id, self.current_product_id) or {}
            else:
                return
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
        rate = float(product.get('purchase_rate') or product.get('cost_price') or product.get('sale_price') or 0.0)
        quantity = 1.0
        discount = 0.0
        totals = self.calculate_row_totals({'rate': rate, 'quantity': quantity, 'discount': discount, 'nature': nature, 'cgst_pct': cgst_pct, 'sgst_pct': sgst_pct, 'igst_pct': igst_pct, 'cess_pct': cess_pct})
        sale_rate = float(product.get('sale_price') or 0.0)
        item_data = {'product_id': product.get('id') or self.current_product_id, 'product_name': product.get('name', ''), 'sale_rate': sale_rate, 'hsn': product.get('hsn', '') or '', 'cgst': cgst_pct, 'sgst': sgst_pct, 'igst': igst_pct, 'cess': cess_pct, 'rate': rate, 'quantity': quantity, 'discount': discount, 'gross_value': totals['gross_value'], 'net_value': totals['net_value'], 'tax_amount': totals['tax_amount'], 'grand_total': totals['grand_total']}
        sl_no = self.items_table.rowCount() + 1
        self.add_item_to_table(item_data, sl_no)
        self.recalculate_summary()
        self.barcode_input.clear()
        self.product_input.clear()
        self.current_product_id = None
        self.current_product_data = {}
        last_row = self.items_table.rowCount() - 1
        QTimer.singleShot(0, lambda r=last_row: self.focus_table_cell_editor(r, self.COL_QTY))

    def on_cell_clicked(self, row, col):
        if col == self.COL_SL:
            self.selected_sl_row = row
            self.manually_selected_row = row
            self.items_table.viewport().update()
        else:
            if self.manually_selected_row != -1:
                self.manually_selected_row = -1
                self.items_table.viewport().update()
            self.selected_sl_row = -1

    def on_item_selection_changed(self):
        try:
            row = self.items_table.currentRow()
            if row < 0:
                return
            if hasattr(self, 'update_discount_status_label'):
                self.update_discount_status_label(row)
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
        if col in (self.COL_RATE, self.COL_QTY, self.COL_GROSS, self.COL_DISC, self.COL_CGST, self.COL_SGST, self.COL_IGST, self.COL_CESS):
            delegate = self.items_table.itemDelegate()
            if delegate is not None and getattr(delegate, 'current_editor', None) is not None and (getattr(delegate, 'current_index', None) is not None) and (delegate.current_index.row() == row) and (delegate.current_index.column() == col):
                return
            self._recalculate_row_in_table(row)

    def _recalculate_row_in_table(self, row, source_column=None, live_value=None):
        """Recalculate row using billing engine.

        source_column: the column being edited (so we use live_value for that col
                       and stale table data for all others).
        live_value:    the string value currently in the editor (not yet committed).
        Returns BillingRowResult so the caller can pass it to recalculate_summary.
        """
        from bizora_core.calculations import BillingRowInput, GstNature, TaxMode, calculate_billing_row, safe_float
        product_cell = self.items_table.item(row, self.COL_PRODUCT)
        if not product_cell or not product_cell.text().strip():
            return None

        def _sf(item):
            """Float from table item, stripping % and currency symbols."""
            if item is None:
                return 0.0
            try:
                return float(item.text().replace('%', '').replace('₹', '').replace(',', '').strip() or '0')
            except (ValueError, AttributeError):
                return 0.0

        def _live(col, default):
            """Return live_value as float if source_column matches, else table value.
            Empty string (user deleted all text) is treated as 0, not as 'keep old value'.
            """
            if source_column == col and live_value is not None:
                text = live_value.strip()
                return float(text) if text else 0.0
            return default
        rate_cell = _sf(self.items_table.item(row, self.COL_RATE))
        qty_cell = _sf(self.items_table.item(row, self.COL_QTY))
        disc_cell = _sf(self.items_table.item(row, self.COL_DISC))
        gross_cell = _sf(self.items_table.item(row, self.COL_GROSS))
        cgst_cell = _sf(self.items_table.item(row, self.COL_CGST))
        sgst_cell = _sf(self.items_table.item(row, self.COL_SGST))
        igst_cell = _sf(self.items_table.item(row, self.COL_IGST))
        cess_cell = _sf(self.items_table.item(row, self.COL_CESS))
        rate = _live(self.COL_RATE, rate_cell)
        qty = _live(self.COL_QTY, qty_cell)
        disc = _live(self.COL_DISC, disc_cell)
        cgst = _live(self.COL_CGST, cgst_cell)
        sgst = _live(self.COL_SGST, sgst_cell)
        igst = _live(self.COL_IGST, igst_cell)
        cess = _live(self.COL_CESS, cess_cell)
        if source_column == self.COL_GROSS and live_value is not None:
            text = live_value.strip()
            gross = float(text) if text else 0.0
            if qty > 0:
                rate = gross / qty
        elif source_column in (self.COL_RATE, self.COL_QTY, None):
            gross = rate * qty
        else:
            gross = rate * qty
        nature_str = self.nature_combo.currentText() if hasattr(self, 'nature_combo') else 'Local'
        nature = GstNature.INTER_STATE if nature_str == 'Inter-state' else GstNature.LOCAL
        row_input = BillingRowInput(qty=qty, rate=rate, discount=disc, cgst_percent=cgst, sgst_percent=sgst, igst_percent=igst, cess_percent=cess, nature=nature, tax_mode=TaxMode.ADDITIVE)
        result = calculate_billing_row(row_input)
        table = self.items_table
        was_blocked = table.blockSignals(True)
        try:

            def _set(col, val, fmt='{:.2f}'):
                cell = table.item(row, col)
                if cell:
                    cell.setText(fmt.format(val))
                else:
                    ni = QTableWidgetItem(fmt.format(val))
                    ni.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    table.setItem(row, col, ni)
            if source_column != self.COL_RATE:
                _set(self.COL_RATE, rate)
            if source_column != self.COL_QTY:
                _set(self.COL_QTY, qty, '{:.3f}')
            if source_column != self.COL_GROSS:
                _set(self.COL_GROSS, result.gross)
            if source_column != self.COL_DISC:
                _set(self.COL_DISC, disc)
            _set(self.COL_NET, result.taxable_value)
            _set(self.COL_TAX, result.total_tax)
            _set(self.COL_TOTAL, result.row_total)
        finally:
            table.blockSignals(was_blocked)
        self.recalculate_summary(live_row=row, live_row_result=result)
        if hasattr(self, 'update_discount_status_label'):
            self.update_discount_status_label(row)
        return result

    def recalculate_row(self, row, source_column=None, live_value=None):
        """Public API called by delegate _on_editor_changed."""
        self._recalculate_row_in_table(row, source_column=source_column, live_value=live_value)

    def safe_item_text(self, row, col, default=''):
        """Return table cell text safely for delegate calculations."""
        item = self.items_table.item(row, col)
        return item.text() if item else default

    def safe_float_from_cell(self, row, col, default=0.0):
        """Return a numeric value from a table cell, ignoring symbols."""
        item = self.items_table.item(row, col)
        if item is None:
            return default
        try:
            text = item.text().replace('%', '').replace('₹', '').replace(',', '').strip()
            return float(text) if text else default
        except (ValueError, AttributeError):
            return default

    def update_discount_status_label(self, row):
        """Display the active row's equivalent discount percentage in the top bar."""
        if not hasattr(self, 'discount_status_display'):
            return
        if row is None or row < 0:
            return
        gross = self.safe_float_from_cell(row, self.COL_GROSS, 0.0)
        disc_amount = self.safe_float_from_cell(row, self.COL_DISC, 0.0)
        pct = disc_amount / gross * 100.0 if gross > 0 else 0.0
        self.discount_status_display.setText(f'{pct:.2f}%')

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
                    cell.setText(f'{v:.2f}%')
                else:
                    ni = QTableWidgetItem(f'{v:.2f}%')
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

    def recalculate_summary(self, live_row=None, live_row_result=None):
        """Rebuild all footer totals from table rows using the billing engine.

        live_row:        row index being edited (use live_row_result instead of stale cells)
        live_row_result: BillingRowResult for the live row
        """
        from bizora_core.calculations import BillingRowInput, BillingRowResult, GstNature, TaxMode, calculate_billing_row, quick_calculate_footer, safe_float
        nature_str = self.nature_combo.currentText() if hasattr(self, 'nature_combo') else 'Local'
        nature = GstNature.INTER_STATE if nature_str == 'Inter-state' else GstNature.LOCAL
        row_results = []
        for row in range(self.items_table.rowCount()):
            if live_row is not None and row == live_row and (live_row_result is not None):
                if live_row_result.is_valid:
                    row_results.append(live_row_result)
                continue
            product_cell = self.items_table.item(row, self.COL_PRODUCT)
            if not product_cell or not product_cell.text().strip():
                continue

            def _sf(col, r=row):
                item = self.items_table.item(r, col)
                if item is None:
                    return 0.0
                try:
                    return float(item.text().replace('%', '').replace('₹', '').replace(',', '').strip() or '0')
                except (ValueError, AttributeError):
                    return 0.0
            qty = _sf(self.COL_QTY)
            rate = _sf(self.COL_RATE)
            if qty <= 0 and rate <= 0:
                continue
            row_input = BillingRowInput(qty=qty, rate=rate, discount=_sf(self.COL_DISC), cgst_percent=_sf(self.COL_CGST), sgst_percent=_sf(self.COL_SGST), igst_percent=_sf(self.COL_IGST), cess_percent=_sf(self.COL_CESS), nature=nature, tax_mode=TaxMode.ADDITIVE)
            result = calculate_billing_row(row_input)
            if result.is_valid:
                row_results.append(result)
        try:
            round_off = float(self.round_off_input.text() or '0')
        except ValueError:
            round_off = 0.0
        footer_discount = self._safe_text_float(self.discount_total_input.text() if hasattr(self, 'discount_total_input') else '0')
        footer = quick_calculate_footer(rows=row_results, freight=0.0, footer_discount=footer_discount, round_off_enabled=False)
        grand_total_before_round = footer.final_total
        final_amount = round(grand_total_before_round + round_off, 2)
        display_updates = ((self.net_value_display, self.format_num(footer.subtotal)), (self.cgst_display, self.format_num(footer.cgst_total)), (self.sgst_display, self.format_num(footer.sgst_total)), (self.igst_display, self.format_num(footer.igst_total)), (self.cess_display, self.format_num(footer.cess_total)), (self.tax_amount_display, self.format_num(footer.tax_total)), (self.grand_total_input, self.format_num(grand_total_before_round)), (self.net_amount_display, self.format_num(final_amount)), (self.final_amount_display, f'₹ {final_amount:.2f}'))
        for widget, value in display_updates:
            was_blocked = widget.blockSignals(True)
            try:
                widget.setText(value)
            finally:
                widget.blockSignals(was_blocked)
        if hasattr(self, 'sub_total_input'):
            was_blocked = self.sub_total_input.blockSignals(True)
            try:
                self.sub_total_input.setText(self.format_num(footer.subtotal))
            finally:
                self.sub_total_input.blockSignals(was_blocked)
        if hasattr(self, 'tax_total_input'):
            was_blocked = self.tax_total_input.blockSignals(True)
            try:
                self.tax_total_input.setText(self.format_num(footer.tax_total))
            finally:
                self.tax_total_input.blockSignals(was_blocked)
        self._update_refunded_from_type(final_amount)
        QCoreApplication.processEvents()

    def _safe_text_float(self, text, default=0.0):
        """Parse a plain/currency/percent text value to float safely."""
        try:
            clean_text = str(text).replace('%', '').replace('₹', '').replace(',', '').strip()
            return float(clean_text) if clean_text else default
        except (TypeError, ValueError):
            return default

    def _discount_base_value(self):
        """Return the pre-footer-discount total used for percent conversion."""
        base = 0.0
        for row in range(self.items_table.rowCount()):
            product_cell = self.items_table.item(row, self.COL_PRODUCT)
            if not product_cell or not product_cell.text().strip():
                continue
            base += self.safe_float_from_cell(row, self.COL_TOTAL, 0.0)
        if base > 0:
            return base
        grand_total = self._safe_text_float(self.grand_total_input.text()) if hasattr(self, 'grand_total_input') else 0.0
        discount = self._safe_text_float(self.discount_total_input.text()) if hasattr(self, 'discount_total_input') else 0.0
        round_off = self._safe_text_float(self.round_off_input.text()) if hasattr(self, 'round_off_input') else 0.0
        return max(grand_total + discount - round_off, 0.0)

    def on_footer_discount_changed(self, _text):
        """Refresh footer discount percentage label and recalculate totals."""
        if hasattr(self, 'discount_percent_label') and hasattr(self, 'discount_total_input'):
            amount = self._safe_text_float(self.discount_total_input.text(), 0.0)
            if amount > 0:
                base = self._discount_base_value()
                if base > 0:
                    pct = amount / base * 100.0
                    pct_disp = f'{pct:.0f}' if float(pct).is_integer() else f'{pct:.2f}'
                    self.discount_percent_label.setText(f'({pct_disp}%)')
                else:
                    self.discount_percent_label.setText('')
            else:
                self.discount_percent_label.setText('')
        self.recalculate_summary()

    def calculate_grand_totals(self):
        """Recalculate all Purchase Return footer totals after value changes."""
        self.recalculate_summary()

    def apply_discount_percent_mode(self):
        """Convert the footer Discount entry from percent to a flat amount.

        Down Arrow inside the footer Discount field treats the typed value as a
        percentage of the pre-footer-discount return total, then immediately
        refreshes the final balance.
        """
        try:
            if not hasattr(self, 'discount_total_input'):
                return
            percent = self._safe_text_float(self.discount_total_input.text(), 0.0)
            if percent <= 0:
                return
            base_value = self._discount_base_value()
            if base_value <= 0:
                return
            if percent > 100:
                percent = 100.0
            discount_amount = round(base_value * percent / 100.0, 2)
            self.discount_total_input.blockSignals(True)
            try:
                self.discount_total_input.setText(f'{discount_amount:.2f}')
            finally:
                self.discount_total_input.blockSignals(False)
            if hasattr(self, 'discount_percent_label'):
                pct_disp = f'{percent:.0f}' if float(percent).is_integer() else f'{percent:.2f}'
                self.discount_percent_label.setText(f'({pct_disp}%)')
            self.calculate_grand_totals()
        except Exception as exc:
            print(f'Failed to apply purchase return footer discount percent mode: {exc}')

    def _update_refunded_from_type(self, final_amount: float):
        """Set Amt Refunded and Balance based on return type.

        Cash / Cash Return  → Amt Refunded = Net Return Amount, Balance = 0
        Credit / Credit Return → Amt Refunded = 0.00, Balance = Net Return Amount
        """
        return_type = self.return_type_combo.currentText().strip().lower()
        is_cash = return_type in ('cash', 'cash return')
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

    def _amt_refunded_edited(self):
        self._amt_refunded_user_edited = True
        self._update_balance_display()

    def _update_balance_display(self):
        """Update balance display using PartyBalanceEngine for proper Previous Balance calculation.

        For Purchase Return:
        - Previous Balance: Balance before current purchase return voucher
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
        closing_balance = self.balance_engine.calculate_closing_balance(previous_balance, final_amount, refunded, 'purchase_return')
        self.balance_display.setText(self.format_num(closing_balance))

    def get_previous_party_balance(self):
        """Return the Previous Balance (balance before current voucher) of the selected party.

        Uses PartyBalanceEngine to calculate:
        Previous Balance = party opening_balance + unpaid previous purchases - previous payments/returns

        Excludes current return when editing/viewing old returns via voucher_id.
        Excludes future vouchers (after current voucher date/id).

        Returns 0.00 when no party found / blank / error.
        """
        try:
            if not hasattr(self, 'supplier_name_input'):
                return 0.0
            name = self.supplier_name_input.text().strip().lower()
            if not name:
                return 0.0
            if not hasattr(self, 'current_party_id') or not self.current_party_id:
                return 0.0
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return 0.0
            voucher_id = self.current_return_id
            voucher_date = None
            if voucher_id and hasattr(self, 'return_date_input'):
                voucher_date = qdate_to_db(self.return_date_input.date())
            balance_result = self.balance_engine.get_party_balance_before_voucher(active_company['id'], self.current_party_id, 'purchase_return', voucher_id=voucher_id, voucher_date=voucher_date)
            return balance_result.get('previous_balance', 0.0)
        except Exception:
            return 0.0

    def remove_current_item(self):
        if self.selected_sl_row < 0:
            QMessageBox.information(self, 'Select Row', 'Click on the SL No cell of the row you want to remove first.')
            return
        row = self.selected_sl_row
        if row >= self.items_table.rowCount():
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
            self.selected_sl_row = -1
            self.recalculate_summary()

    def _validate_party_before_save(self):
        """Require a selected supplier before saving non-cash purchase returns."""
        return_type = self.return_type_combo.currentText().strip().casefold()
        if 'cash' in return_type:
            return True
        try:
            party_id = int(getattr(self, 'current_party_id', 0) or 0)
        except (TypeError, ValueError):
            party_id = 0
        if party_id > 0:
            return True
        QMessageBox.warning(self, 'Validation Error', 'Please select a Supplier/Creditor before saving.')
        self.supplier_name_input.setFocus()
        return False

    def _validate_and_collect(self):
        company_id = self.get_current_company_id()
        if not company_id:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return None
        if not self._validate_party_before_save():
            return None
        form_data = self.get_form_data()
        party_resolution = self.purchase_return_logic.resolve_purchase_return_party_id(form_data)
        if not party_resolution.get('success'):
            QMessageBox.warning(self, 'Party Required', party_resolution.get('message', 'Please select a party.'))
            self.supplier_name_input.setFocus()
            return None
        if not form_data['items']:
            QMessageBox.warning(self, 'Error', 'Add at least one item with quantity > 0.')
            return None
        validation = self.purchase_return_logic.validate_purchase_return_data(form_data, current_purchase_return_id=self.current_return_id)
        if not validation.get('success'):
            QMessageBox.warning(self, 'Validation Error', validation.get('message', 'Please correct the purchase return details.'))
            return None
        return form_data

    def save_return(self):
        if self.current_return_id:
            self.update_return()
            return
        form_data = self._validate_and_collect()
        if form_data is None:
            return
        result = self.purchase_return_logic.save_purchase_return(form_data)
        if result['success']:
            self.current_return_id = result.get('purchase_return_id')
            QMessageBox.information(self, 'Saved', f"Purchase Return saved successfully.\nReturn No: {form_data['return_no']}")
            self.load_returns_list()
            self.clear_form()
            self._prepare_new_return_number()
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
        result = self.purchase_return_logic.update_purchase_return(self.current_return_id, form_data)
        if result['success']:
            QMessageBox.information(self, 'Updated', 'Purchase Return updated successfully.')
            self.load_returns_list()
            self.save_btn.setText('Save')
            self.current_return_id = None
            self.clear_form()
            self._prepare_new_return_number()
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
            'Permanently delete this Purchase Return and reverse stock movements?',
            db=self.db,
            company_id=company_id,
        ):
            return
        result = self.purchase_return_logic.delete_purchase_return(company_id, self.current_return_id)
        if result['success']:
            QMessageBox.information(self, 'Deleted', 'Purchase Return deleted successfully.')
            self.load_returns_list()
            self.save_btn.setText('Save')
            self.clear_form()
        else:
            QMessageBox.critical(self, 'Error', result['message'])

    def export_pdf(self):
        """Open the current Purchase Return in the universal preview dialog."""
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
            QMessageBox.warning(self, 'Preview Purchase Return', 'Please add at least one item with quantity before previewing.')
            return
        try:
            settings = get_print_settings(self.db, company_id)
            html_string = generate_transaction_voucher_html(company_print_data(active_company), self._purchase_return_print_data(form_data), items, settings=settings)
            dialog = UniversalPreviewDialog(html_string, self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, 'Preview Failed', f'Could not preview Purchase Return:\n{exc}')

    def print_return(self):
        """Print the current Purchase Return voucher through the shared A4 engine."""
        company_id = self.get_current_company_id()
        active_company = active_company_manager.get_active_company()
        if not company_id or not active_company:
            QMessageBox.warning(self, 'Print Purchase Return', 'Please open a company first.')
            return
        form_data = self.get_form_data()
        items = form_data.get('items', [])
        if not items:
            QMessageBox.warning(self, 'Print Purchase Return', 'Please add at least one item with quantity before printing.')
            return
        try:
            settings = get_print_settings(self.db, company_id)
            html_string = generate_transaction_voucher_html(company_print_data(active_company), self._purchase_return_print_data(form_data), items, settings=settings)
            dialog = UniversalPreviewDialog(html_string, mode='A4', parent=self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Could not print Purchase Return:\n{exc}')

    def _purchase_return_print_data(self, form_data):
        """Return header and totals used by Purchase Return A4 HTML."""
        return {'voucher_title': 'PURCHASE RETURN', 'party_label': 'Supplier', 'party_name': self.supplier_name_input.text().strip() or 'Cash Supplier', 'voucher_no': form_data.get('return_no', ''), 'voucher_date': qdate_to_display(self.date_input.date()), 'voucher_type': form_data.get('return_type', ''), 'reference': form_data.get('original_purchase_no', ''), 'sub_total': form_data.get('sub_total', 0.0), 'discount_total': form_data.get('discount_total', 0.0), 'tax_total': form_data.get('tax_total', 0.0), 'round_off': form_data.get('round_off', 0.0), 'grand_total': form_data.get('grand_total', 0.0), 'narration': form_data.get('narration', '')}

    def refresh(self):
        self.load_returns_list()
        if self.current_return_id:
            for r in self.returns_list:
                if r['id'] == self.current_return_id:
                    self._load_full_return(r)
                    break

    def eventFilter(self, obj, event):
        """Handle Esc on table/product_input and F1 on barcode_input."""
        from PySide6.QtCore import QEvent as QEv
        if isinstance(obj, (QLineEdit, QDoubleSpinBox)) and event.type() == QEv.FocusIn:
            self._select_all_text_on_focus(obj)
        if event.type() == QEv.KeyPress:
            key = event.key()
            if hasattr(self, 'discount_total_input') and obj is self.discount_total_input and (key == Qt.Key_Down):
                self.apply_discount_percent_mode()
                return True
            if self._handle_top_bar_navigation_key(obj, key):
                return True
            if key == Qt.Key_Escape:
                if obj is self.items_table or obj is self.product_input:
                    self.barcode_input.setFocus()
                    self.barcode_input.selectAll()
                    return True
            elif key == Qt.Key_F1:
                if obj is self.barcode_input:
                    last_row = -1
                    for r in range(self.items_table.rowCount() - 1, -1, -1):
                        cell = self.items_table.item(r, self.COL_PRODUCT)
                        if cell and cell.text().strip():
                            last_row = r
                            break
                    if last_row >= 0:
                        self.focus_table_cell_editor(last_row, self.COL_QTY)
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F5:
            self.refresh()
        else:
            super().keyPressEvent(event)