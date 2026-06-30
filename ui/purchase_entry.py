"""
Purchase Entry widget for the Accounting Desktop Application.
Manages purchase invoice creation with compact desktop layout.
Modular architecture following Sales Entry pattern.
"""
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QDate, QEvent, QTimer, Signal, QCoreApplication
from PySide6.QtGui import QDoubleValidator
import json
import sqlite3
from config import active_company_manager
from db import Database
from bizora_core.party_logic import PartyLogic
from bizora_core.product_logic import ProductLogic
from bizora_core.party_balance_engine import PartyBalanceEngine
from bizora_core.stock_logic import StockLogic
from bizora_core.print_settings_logic import get_print_settings
from utils.a4_print_engine import generate_a4_html
from utils.a4_voucher_print_helpers import company_print_data
from .purchase_entry_ui import PurchaseEntryUIMixin
from .purchase_entry_helpers import safe_item_text, safe_float_from_cell, ensure_row_items_initialized
from .purchase_entry_delegate import PurchaseBillDelegate, COL_QTY, COL_RATE
from .theme import GST_STATE_CODES
from .purchase_entry_calculations import recalculate_row as _recalculate_row, calculate_totals as _calculate_totals
from .purchase_entry_popup import setup_creditor_completer
from .purchase_po_import import POSelectionDialog
from . import theme
from ui.party_display import party_matches_text, strip_party_display_code, party_display_name
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.table_header_utils import apply_adjustable_table_columns
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
from ui.entry_voucher_mixin import EntryVoucherMixin
from bizora_core.settings_logic import confirm_before_delete_transaction

class PurchaseEntryWidget(EntryVoucherMixin, UiMemoryMixin, PurchaseEntryUIMixin, QWidget):
    DEFAULT_PREFILLED_ROWS = 15
    window_closed = Signal()
    voucher_type = "purchase"
    voucher_number_attr = "purchase_no_input"

    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self.db = db or Database()
        self.product_logic = ProductLogic(self.db)
        self.party_logic = PartyLogic(self.db)
        self.balance_engine = PartyBalanceEngine(self.db)
        self.stock_logic = StockLogic(self.db)
        self.purchase_logic = None
        self.purchase_items = []
        self.selected_creditor_id = None
        self._party_fields_locked = False
        self.gst_state_codes = GST_STATE_CODES
        self._editing_creditor = False
        self._creditor_refresh_pending = False
        self.manually_selected_row = -1
        self.is_local_tax = True
        self._product_selection_in_progress = False
        self._product_search_selection_committed = False
        self.products_data = []
        self.product_count = 0
        self._large_product_mode = False
        self.products_dict = {}
        self.products_by_barcode = {}
        self.products_by_name_exact = {}
        self.creditors_data = []
        self._row_discount_total = 0.0
        self._creditor_selection_in_progress = False
        self._product_entry_context = None
        self._creditor_refresh_timer = None
        self._last_creditor_refresh_time = 0
        self._amt_paid_user_edited = False
        self._updating_amt_paid_programmatically = False
        self._is_loading = False
        self.active_loaded_po_id = None
        self._initial_load_done = False
        self._deferred_load_started = False
        self._skip_initial_load = False
        self._suppress_initial_purchase_number = False
        self.setup_ui()
        self._suppress_initial_purchase_number = True
        try:
            self.clear_form()
        finally:
            self._suppress_initial_purchase_number = False
        self._wire_signals()
        self._init_entry_voucher_state()
        self._install_entry_unsaved_guard()
        self._install_voucher_number_lookup()
        QTimer.singleShot(100, self._deferred_initial_load)
        self._init_ui_memory()

    def _deferred_initial_load(self):
        """Deferred initial load of heavy data to allow window to appear quickly."""
        if self._skip_initial_load:
            return
        if self._initial_load_done or self._deferred_load_started:
            return
        self._deferred_load_started = True
        try:
            self.load_creditors()
            self.load_products()
            self.generate_purchase_number()
            self._initial_load_done = True
        finally:
            self._deferred_load_started = False

    def _get_purchase_logic(self):
        """Lazy load purchase_logic."""
        if self.purchase_logic is None:
            from bizora_core.purchase_logic import PurchaseLogic
            self.purchase_logic = PurchaseLogic(self.db)
        return self.purchase_logic

    def showEvent(self, event):
        """Handle show event - refresh creditor if returning from edit."""
        super().showEvent(event)
        if not self._initial_load_done:
            return
        import time
        current_time = time.time()
        if self._creditor_refresh_pending or current_time - self._last_creditor_refresh_time > 2.0:
            self._creditor_refresh_pending = False
            self.load_creditors()
            self._last_creditor_refresh_time = current_time

    def changeEvent(self, event):
        """Handle change event - detect window activation."""
        super().changeEvent(event)
        if not self._initial_load_done:
            return
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            import time
            current_time = time.time()
            if current_time - self._last_creditor_refresh_time > 1.0:
                self.load_creditors()
                self._last_creditor_refresh_time = current_time

    def _delayed_creditor_refresh(self):
        """Delayed refresh of creditor to ensure UI is ready."""
        if self._editing_creditor and self.selected_creditor_id:
            self.refresh_selected_creditor_from_db()
            self._editing_creditor = False
        elif self._editing_creditor:
            self.load_creditors()
            self._editing_creditor = False

    def _start_creditor_refresh_timer(self):
        """Start a timer to periodically refresh creditors list after editing."""
        if self._creditor_refresh_timer:
            self._creditor_refresh_timer.stop()
            self._creditor_refresh_timer.deleteLater()
        self._creditor_refresh_timer = QTimer(self)
        self._creditor_refresh_timer.setInterval(1000)
        self._creditor_refresh_timer.timeout.connect(self._check_and_refresh_creditors)
        self._creditor_refresh_count = 0
        self._creditor_refresh_timer.start()

    def _check_and_refresh_creditors(self):
        """Check if we should refresh creditors and stop timer after 10 checks."""
        self._creditor_refresh_count += 1
        self.load_creditors()
        if self._creditor_refresh_count >= 10:
            if self._creditor_refresh_timer:
                self._creditor_refresh_timer.stop()
                self._creditor_refresh_timer = None
            self._editing_creditor = False

    def _wire_signals(self):
        """Wire up all signal connections once only."""
        if getattr(self, '_signals_wired', False):
            return
        self._signals_wired = True
        self.items_table.cellChanged.connect(self.on_table_cell_changed)
        self.items_table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.nature_combo.currentTextChanged.connect(self.on_nature_changed)
        self.purchase_type_combo.currentTextChanged.connect(self.on_purchase_type_changed)
        self.barcode_input.returnPressed.connect(self.on_barcode_enter)
        self.product_input.returnPressed.connect(self.on_product_enter)
        self.purchase_checkbox.toggled.connect(self.on_purchase_checkbox_toggled)
        if hasattr(self, 'round_off_input'):
            self.round_off_input.textChanged.connect(self.on_footer_discount_changed)
        if hasattr(self, 'discount_total_input'):
            self.discount_total_input.textChanged.connect(self.on_footer_discount_changed)
            self.discount_total_input.installEventFilter(self)
        if hasattr(self, 'round_off_checkbox'):
            self.round_off_checkbox.stateChanged.connect(self.on_round_off_toggled)
        if hasattr(self, 'purchase_expense_input'):
            self.purchase_expense_input.textChanged.connect(self.on_purchase_expense_changed)
        if hasattr(self, 'amt_paid_input'):
            self.amt_paid_input.editingFinished.connect(self.on_amt_paid_edited)
        self.items_table.installEventFilter(self)
        self.items_table.viewport().installEventFilter(self)
        setup_creditor_completer(self.creditor_name_input, self, self.on_creditor_selected)
        from .purchase_entry_popup import setup_product_completer
        setup_product_completer(self.product_input, self, None, self.on_product_selected)
        self.creditor_name_input.textChanged.connect(self.on_creditor_name_changed)
        self.creditor_name_input.editingFinished.connect(self.on_creditor_editing_finished)
        self.creditor_name_input.mousePressEvent = self._on_creditor_mouse_press
        self.creditor_name_input.focusInEvent = self._on_creditor_focus_in
        self.address_input.textChanged.connect(self.on_address_changed)
        self.narration_input.textChanged.connect(self.on_narration_changed)
        if hasattr(self, 'code_input'):
            self.code_input.textChanged.connect(self.on_code_changed)
        for widget in (self.creditor_name_input, getattr(self, 'code_input', None), self.address_input, self.mobile_input, self.gstin_input, self.state_combo, self.narration_input, self.barcode_input, self.product_input, getattr(self, 'purchase_no_input', None), getattr(self, 'supplier_invoice_input', None), getattr(self, 'round_off_input', None), getattr(self, 'purchase_expense_input', None), getattr(self, 'amt_paid_input', None)):
            if widget is not None:
                widget.installEventFilter(self)

    def _install_entry_unsaved_guard(self) -> None:
        """Track edits so closing an entry page can prompt to save."""
        self._install_unsaved_guard(
            [
                self.purchase_no_input,
                self.creditor_name_input,
                self.address_input,
                self.mobile_input,
                self.gstin_input,
                self.narration_input,
                self.supplier_invoice_input,
                self.date_input,
                self.due_date_input,
                self.purchase_type_combo,
                self.nature_combo,
                self.state_combo,
                self.amt_paid_input if hasattr(self, 'amt_paid_input') else None,
                self.round_off_input if hasattr(self, 'round_off_input') else None,
                self.discount_total_input if hasattr(self, 'discount_total_input') else None,
            ],
            table=self.items_table,
        )

    def _capture_entry_snapshot(self) -> str:
        """Serialize purchase header and line items for unsaved-close detection."""
        import json

        items = []
        if hasattr(self, 'items_table'):
            for row in range(self.items_table.rowCount()):
                row_meta = self.purchase_items[row] if row < len(self.purchase_items) else {}

                def _cell_text(column: int) -> str:
                    item = self.items_table.item(row, column)
                    return item.text().strip() if item else ''

                items.append({
                    'product_id': row_meta.get('product_id'),
                    'name': _cell_text(2),
                    'qty': _cell_text(9),
                    'rate': _cell_text(8),
                    'disc': _cell_text(11),
                })
        payload = {
            'purchase_id': self.current_purchase_id,
            'purchase_no': self.purchase_no_input.text().strip() if hasattr(self, 'purchase_no_input') else '',
            'creditor': self.creditor_name_input.text().strip() if hasattr(self, 'creditor_name_input') else '',
            'mobile': self.mobile_input.text().strip() if hasattr(self, 'mobile_input') else '',
            'address': self.address_input.text().strip() if hasattr(self, 'address_input') else '',
            'gstin': self.gstin_input.text().strip() if hasattr(self, 'gstin_input') else '',
            'narration': self.narration_input.text().strip() if hasattr(self, 'narration_input') else '',
            'supplier_invoice': self.supplier_invoice_input.text().strip() if hasattr(self, 'supplier_invoice_input') else '',
            'purchase_type': self.purchase_type_combo.currentText().strip() if hasattr(self, 'purchase_type_combo') else '',
            'nature': self.nature_combo.currentText().strip() if hasattr(self, 'nature_combo') else '',
            'state': self.state_combo.currentText().strip() if hasattr(self, 'state_combo') else '',
            'series': self.series_input.text().strip() if hasattr(self, 'series_input') else '',
            'date': qdate_to_db(self.date_input.date()) if hasattr(self, 'date_input') else '',
            'due_date': qdate_to_db(self.due_date_input.date()) if hasattr(self, 'due_date_input') else '',
            'round_off': self.round_off_input.text().strip() if hasattr(self, 'round_off_input') else '',
            'amount_paid': self.amt_paid_input.text().strip() if hasattr(self, 'amt_paid_input') else '',
            'items': items,
        }
        return json.dumps(payload, sort_keys=True, default=str)

    def setup_ui(self):
        """Build the Purchase Entry UI."""
        from ui import theme as ui_theme
        self.setStyleSheet(ui_theme.entry_page_background_style())
        base_font = self.font()
        base_font.setBold(True)
        self.setFont(base_font)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.build_page_header_strip())
        layout.addWidget(self.build_purchase_command_strip())
        layout.addWidget(self.build_creditor_information_matrix())
        layout.addWidget(self.build_product_entry_strip())
        layout.addWidget(self.build_bill_options_strip())
        layout.addWidget(self.build_billing_table_zone())
        self.table = self.items_table
        layout.addWidget(self.build_lower_control_panel())
        self.items_table.setItemDelegate(PurchaseBillDelegate(self))
        self.items_table.viewport().installEventFilter(self)
        try:
            from ui.financial_year_guard import apply_financial_year_guard_to_named_dates
            apply_financial_year_guard_to_named_dates(self, 'date_input', 'due_date_input')
        except Exception:
            pass

    def refresh_theme(self):
        """Re-apply theme-aware styles after a global theme change."""
        from ui import theme as ui_theme
        self.setStyleSheet(ui_theme.entry_page_background_style())
        if hasattr(self, 'stock_display'):
            self.stock_display.setStyleSheet(ui_theme.entry_value_style('accent_highlight'))

    def load_creditors(self):
        """Load creditors from database - handle dict or list return, case-insensitive filtering."""
        try:
            active_company = active_company_manager.get_active_company()
            if active_company:
                result = self.party_logic.get_parties(active_company['id'])
                if isinstance(result, dict) and 'data' in result:
                    all_parties = result['data']
                elif isinstance(result, list):
                    all_parties = result
                else:
                    all_parties = []
                self.creditors_data = []
                for party in all_parties:
                    if not isinstance(party, dict):
                        continue
                    party_type = party.get('party_type', '')
                    if party_type and isinstance(party_type, str):
                        if party_type.lower() in ['creditor', 'both']:
                            self.creditors_data.append(party)
                    elif not party_type:
                        self.creditors_data.append(party)
                from .purchase_entry_popup import setup_creditor_completer
                setup_creditor_completer(self.creditor_name_input, self, self.on_creditor_selected)
                import time
                self._last_creditor_refresh_time = time.time()
        except Exception as exc:
            print(f'Failed to load purchase creditors: {exc}')

    def load_products(self):
        """Load products from database - only for small datasets."""
        try:
            active_company = active_company_manager.get_active_company()
            if active_company:
                count_result = self.product_logic.get_product_count(active_company['id'])
                product_count = count_result.get('data', 0) if isinstance(count_result, dict) else 0
                self.product_count = product_count
                self._large_product_mode = product_count >= 1000
                if product_count < 1000:
                    result = self.product_logic.get_products(active_company['id'])
                    if isinstance(result, dict) and 'data' in result:
                        products = result['data']
                    elif isinstance(result, list):
                        products = result
                    else:
                        products = []
                    self.products_data = products
                    self.products_dict = {}
                    self.products_by_barcode = {}
                    self.products_by_name_exact = {}
                    for product in products:
                        if product.get('id'):
                            self.products_dict[product['id']] = product
                        if product.get('barcode'):
                            self.products_by_barcode[product['barcode']] = product
                        if product.get('name'):
                            self.products_by_name_exact[product['name']] = product
                else:
                    self.products_data = []
                    self.products_dict = {}
                    self.products_by_barcode = {}
                    self.products_by_name_exact = {}
        except Exception as exc:
            print(f'Failed to load purchase products: {exc}')

    def update_affected_products_stock(self, affected_product_ids):
        """Update stock quantities only for affected products after a purchase.

        Uses batch query to get all balances in a single database call.
        """
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            product_ids = [pid for pid in affected_product_ids if pid]
            if not product_ids:
                return
            balances = self.db.get_stock_balances_for_products(active_company['id'], product_ids)
            for product_id, new_stock in balances.items():
                if product_id in self.products_dict:
                    self.products_dict[product_id]['quantity'] = new_stock
                for p in self.products_data:
                    if p.get('id') == product_id:
                        p['quantity'] = new_stock
                        break
        except Exception as e:
            print(f'Failed to update affected products stock: {e}')

    def on_nature_changed(self, text):
        """Apply Indian GST purchase nature rules live for all product rows.

        Local: use product CGST + SGST, IGST must be 0.
        Inter-state: use product IGST, CGST and SGST must be 0.
        CESS is preserved in both cases.
        """
        self.is_local_tax = 'inter' not in str(text).strip().lower()
        for row in range(self.items_table.rowCount()):
            if row >= len(self.purchase_items):
                continue
            item_data = self.purchase_items[row]
            if not item_data.get('product_id'):
                continue
            product = self._get_product_for_row(row)
            self._apply_nature_tax_to_row(row, product)
            self.recalculate_row(row)
        self.calculate_totals()

    def on_purchase_type_changed(self):
        """Handle purchase type combo change (Cash/Credit)."""
        if getattr(self, '_is_loading', False):
            return
        p_type = self.purchase_type_combo.currentText().lower()
        if 'credit' in p_type:
            self._amt_paid_user_edited = False
            self._updating_amt_paid_programmatically = True
            self.amt_paid_input.setText('0.00')
            self._updating_amt_paid_programmatically = False
            self.amt_paid_input.setEnabled(False)
        else:
            self.amt_paid_input.setEnabled(True)
        self.calculate_totals()

    def generate_purchase_number(self):
        """Auto-generate purchase number based on series."""
        if self.current_purchase_id:
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return
        if self.purchase_checkbox.isChecked():
            return
        series = self.series_input.text()
        next_number = self.db.get_next_purchase_number(active_company['id'], series)
        self.purchase_no_input.setText(next_number)

    def on_purchase_checkbox_toggled(self, checked):
        """Handle purchase number checkbox toggle."""
        if checked:
            self.purchase_no_input.setPlaceholderText('')
        else:
            self.purchase_no_input.setPlaceholderText('Auto')
            self.generate_purchase_number()

    def _update_purchase_top_bar_for_product(self, product, barcode=None):
        """Refresh live status strip from product data after barcode scan."""
        if not product:
            return
        if hasattr(self, 'product_input'):
            self.product_input.blockSignals(True)
            self.product_input.setText(product.get('name', ''))
            self.product_input.blockSignals(False)
        code_value = product.get('code') if product.get('code') else barcode or product.get('barcode', '')
        if hasattr(self, 'code_display'):
            self.code_display.setText(str(code_value or ''))
        active_company = active_company_manager.get_active_company()
        if active_company and hasattr(self, 'stock_display'):
            try:
                stock = self.stock_logic.get_current_stock(active_company['id'], product['id'])
            except Exception:
                stock = product.get('quantity', 0)
            self.stock_display.setText(str(stock) if stock is not None else '0')

    def _reset_barcode_scan_cycle_state(self):
        """Clear stale qty-edit flags so the next barcode scan starts fresh."""
        self.manually_selected_row = -1

    def on_barcode_enter(self):
        """Handle barcode input Enter key."""
        barcode = self.barcode_input.text().strip()
        if not barcode:
            self.product_input.setFocus()
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return
        product = None
        result = self.product_logic.get_product_by_barcode(active_company['id'], barcode)
        if result and result.get('success') and result.get('data'):
            product = result['data']
        elif self.products_data:
            for p in self.products_data:
                if str(p.get('barcode')) == barcode:
                    product = p
                    break
        if product:
            self._reset_barcode_scan_cycle_state()
            self._update_purchase_top_bar_for_product(product, barcode)
            added_row = self._add_product_to_table_with_row(product, default_qty=0)
            if added_row >= 0:
                self.barcode_input.clear()
                self.calculate_totals()
                self._update_purchase_top_bar_for_product(product, barcode)
                self.focus_table_cell_editor(added_row, COL_QTY)
        else:
            QMessageBox.warning(self, 'Product Not Found', f'No product found with barcode: {barcode}')
            self.barcode_input.clear()

    def focus_table_cell_editor(self, row, col):
        """Focus table cell editor and select all text with a single mouse click."""
        if row < 0 or col < 0:
            return
        ensure_row_items_initialized(self.items_table, row)
        item = self.items_table.item(row, col)
        if not item:
            return
        self.manually_selected_row = -1
        self.items_table.clearSelection()
        self.items_table.setCurrentCell(row, col)
        self.items_table.scrollToItem(item)
        self.items_table.setFocus(Qt.MouseFocusReason)
        self.items_table.editItem(item)
        QTimer.singleShot(0, self._select_current_editor)
        QTimer.singleShot(50, self._select_current_editor)
        QTimer.singleShot(120, self._select_current_editor)

    def _select_current_editor(self):
        """Select all text in the current table editor."""
        editor = self.items_table.focusWidget()
        if editor and isinstance(editor, QLineEdit):
            editor.setFocus(Qt.MouseFocusReason)
            editor.selectAll()

    def _select_disc_field_text(self, row, col):
        """Select all text in the Disc field editor with proper focus."""
        item = self.items_table.item(row, col)
        if item:
            self.items_table.setCurrentCell(row, col)
            self.items_table.scrollToItem(item)
            self.items_table.editItem(item)
            QTimer.singleShot(0, self._select_current_editor)

    def _activate_and_focus_disc(self, row):
        """Activate window and focus Disc field."""
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        QTimer.singleShot(200, lambda: self._focus_disc_after_activation(row))

    def _focus_disc_after_activation(self, row):
        """Focus Disc field after window activation."""
        self.raise_()
        self.activateWindow()
        self.items_table.setFocus()
        from .purchase_entry_delegate import PurchaseBillDelegate, COL_DISC
        delegate = self.items_table.itemDelegate()
        if hasattr(delegate, 'move_to_cell_and_select_all'):
            delegate.move_to_cell_and_select_all(row, COL_DISC)

    def _force_disc_focus_with_editor(self, row):
        """Force Disc field focus with editor open."""
        from PySide6.QtWidgets import QApplication
        QApplication.instance().setActiveWindow(self)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        QTimer.singleShot(300, lambda: self._open_disc_editor(row))

    def _open_disc_editor(self, row):
        """Open Disc field editor."""
        from .purchase_entry_delegate import PurchaseBillDelegate, COL_DISC
        self.raise_()
        self.activateWindow()
        self.items_table.setFocus()
        self.items_table.setCurrentCell(row, COL_DISC)
        item = self.items_table.item(row, COL_DISC)
        if item:
            self.items_table.scrollToItem(item)
            self.items_table.editItem(item)

    def _simulate_disc_click(self, row):
        """Simulate mouse click on Disc field to force editor focus."""
        from .purchase_entry_delegate import PurchaseBillDelegate, COL_DISC
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        original_flags = self.windowFlags()
        self.setWindowFlags(original_flags | Qt.WindowStaysOnTopHint)
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        QApplication.instance().setActiveWindow(self)
        self.setFocus()
        self.items_table.setCurrentCell(row, COL_DISC)
        item = self.items_table.item(row, COL_DISC)
        if item:
            self.items_table.scrollToItem(item)
            rect = self.items_table.visualItemRect(item)
            center = rect.center()
            press_event = QMouseEvent(QMouseEvent.MouseButtonPress, center, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            release_event = QMouseEvent(QMouseEvent.MouseButtonRelease, center, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            QApplication.postEvent(self.items_table.viewport(), press_event)
            QApplication.postEvent(self.items_table.viewport(), release_event)
            QTimer.singleShot(100, lambda: self._force_disc_focus_after_click(row, original_flags))

    def _force_disc_focus_after_click(self, row, original_flags):
        """Force Disc field focus after simulated click."""
        from .purchase_entry_delegate import PurchaseBillDelegate, COL_DISC
        from PySide6.QtCore import Qt
        self.setWindowFlags(original_flags)
        self.show()
        self.raise_()
        self.activateWindow()
        self.items_table.setFocus()
        item = self.items_table.item(row, COL_DISC)
        if item:
            self.items_table.editItem(item)
            QTimer.singleShot(100, self._force_editor_focus_simple)

    def _force_editor_focus_simple(self):
        """Force editor focus with simple approach."""
        from PySide6.QtWidgets import QApplication
        self.activateWindow()
        self.raise_()
        editor = self.items_table.focusWidget()
        if editor and isinstance(editor, QLineEdit):
            editor.setFocus()
            editor.selectAll()
            QApplication.instance().focusWidget()

    def _focus_and_select_qty(self, row):
        """Focus Qty field and select all text."""
        self.focus_table_cell_editor(row, 8)

    def open_product_entry_edit_from_row(self, row, product_id):
        """Open Product Entry in edit mode for the specified product."""
        try:
            from PySide6.QtWidgets import QApplication
            main_window = self.window()
            if main_window and hasattr(main_window, 'show_products'):
                main_window.show_products()
                for widget in QApplication.topLevelWidgets():
                    from .products import ProductsWidget
                    products_widget = widget.findChild(ProductsWidget)
                    if products_widget and hasattr(products_widget, 'open_for_edit_from_purchase'):
                        products_widget.open_for_edit_from_purchase(product_id, self, row)
                        break
                return
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'show_products'):
                    widget.show_products()
                    widget.raise_()
                    widget.activateWindow()
                    for top_widget in QApplication.topLevelWidgets():
                        from .products import ProductsWidget
                        products_widget = top_widget.findChild(ProductsWidget)
                        if products_widget and hasattr(products_widget, 'open_for_edit_from_purchase'):
                            products_widget.open_for_edit_from_purchase(product_id, self, row)
                            break
                    return
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'stack_widget') and hasattr(widget, 'products_widget'):
                    if hasattr(widget.products_widget, 'open_for_edit_from_purchase'):
                        widget.products_widget.open_for_edit_from_purchase(product_id, self, row)
                    widget.stack_widget.setCurrentWidget(widget.products_widget)
                    widget.raise_()
                    widget.activateWindow()
                    return
        except Exception as e:
            QMessageBox.warning(self, 'Navigation Error', f'Could not open Product Entry: {e}')

    def open_product_entry_new_from_row(self, row, suggested_name=''):
        """Open Product Entry in new mode for adding a new product."""
        try:
            from PySide6.QtWidgets import QApplication
            main_window = self.window()
            if main_window and hasattr(main_window, 'show_products'):
                main_window.show_products()
                for widget in QApplication.topLevelWidgets():
                    from .products import ProductsWidget
                    products_widget = widget.findChild(ProductsWidget)
                    if products_widget and hasattr(products_widget, 'open_for_new_from_purchase'):
                        products_widget.open_for_new_from_purchase(self, row, suggested_name)
                        break
                return
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'show_products'):
                    widget.show_products()
                    widget.raise_()
                    widget.activateWindow()
                    for top_widget in QApplication.topLevelWidgets():
                        from .products import ProductsWidget
                        products_widget = top_widget.findChild(ProductsWidget)
                        if products_widget and hasattr(products_widget, 'open_for_new_from_purchase'):
                            products_widget.open_for_new_from_purchase(self, row, suggested_name)
                            break
                    return
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'stack_widget') and hasattr(widget, 'products_widget'):
                    if hasattr(widget.products_widget, 'open_for_new_from_purchase'):
                        widget.products_widget.open_for_new_from_purchase(self, row, suggested_name)
                    widget.stack_widget.setCurrentWidget(widget.products_widget)
                    widget.raise_()
                    widget.activateWindow()
                    return
        except Exception as e:
            QMessageBox.warning(self, 'Navigation Error', f'Could not open Product Entry: {e}')

    def receive_product_from_product_page(self, product, qty, row):
        """Receive product data from Product Entry page and populate table row."""
        try:
            table = self.items_table
            qty_value = 0.0
            if qty:
                try:
                    qty_value = float(qty) if qty else 0.0
                except (ValueError, TypeError):
                    qty_value = 0.0
            sales_rate = float(product.get('sale_price', 0) or product.get('sales_rate', 0) or 0)
            sr_item = table.item(row, 1)
            if sr_item:
                sr_item.setText(f'{sales_rate:.2f}')
            product_item = table.item(row, 2)
            if product_item:
                product_item.setText(product.get('name', ''))
            hsn_item = table.item(row, 3)
            if hsn_item:
                hsn_item.setText(product.get('hsn', ''))
            rate_item = table.item(row, 8)
            if rate_item:
                rate_item.setText(str(product.get('purchase_rate', 0)))
            qty_item = table.item(row, 9)
            if qty_item:
                qty_item.setText(str(qty_value))
            if row < len(self.purchase_items):
                self.purchase_items[row]['product_id'] = product.get('id')
                self.purchase_items[row]['name'] = product.get('name', '')
                self.purchase_items[row]['hsn'] = product.get('hsn', '')
                self.purchase_items[row]['hsn_code'] = product.get('hsn', '')
                self.purchase_items[row]['supplier_code'] = self._current_supplier_code()
                self.purchase_items[row]['source_cgst'] = float(product.get('cgst', 0) or 0)
                self.purchase_items[row]['source_sgst'] = float(product.get('sgst', 0) or 0)
                self.purchase_items[row]['source_igst'] = float(product.get('igst', 0) or 0)
                self.purchase_items[row]['source_cess'] = float(product.get('cess', 0) or 0)
                self.purchase_items[row]['rate'] = float(product.get('purchase_rate', 0) or 0)
                self.purchase_items[row]['quantity'] = qty_value
            product_id = product.get('id')
            if product_id:
                self.products_dict[product_id] = product
                for i, p in enumerate(self.products_data):
                    if p.get('id') == product_id:
                        self.products_data[i] = product
                        break
            self._apply_nature_tax_to_row(row, product)
            from .purchase_entry_delegate import COL_QTY
            self.recalculate_row(row, source_column=COL_QTY, live_value=qty_value)
            self.calculate_totals()
            self.apply_purchase_payment_mode()
            self._product_entry_context = None
            if qty_value > 0:
                from .purchase_entry_delegate import COL_DISC
                delegate = self.items_table.itemDelegate()
                if hasattr(delegate, 'move_to_cell_and_select_all'):
                    delegate.move_to_cell_and_select_all(row, COL_DISC)
                else:
                    self.focus_table_cell_editor(row, COL_DISC)
            else:
                self.focus_table_cell_editor(row, 9)
        except Exception as e:
            print(f'Error receiving product from product page: {e}')
            QMessageBox.warning(self, 'Error', f'Failed to load product into purchase table: {e}')

    def _add_product_to_table_with_row(self, product, custom_rate=None, default_qty=0):
        """Add product to table and return the row index."""
        if not product:
            return -1
        row_product = dict(product)
        row_product['_custom_rate'] = custom_rate
        row_product['_default_qty'] = default_qty
        return self.add_product_row(row_product)

    def on_product_enter(self):
        """Handle product input Enter key - open the unified product search popup.

        The popup seeds its search box with whatever is already typed in the
        Product field, so matching items filter instantly. This mirrors the Sales
        Entry workflow exactly.
        """
        if self._product_search_selection_committed:
            self._product_search_selection_committed = False
            return
        self.show_product_popup()

    def on_product_selected(self, index, model_idx, editor):
        """Handle product selection from completer popup."""
        if self._product_selection_in_progress:
            return
        product = model_idx.data(Qt.UserRole)
        if product:
            self._product_selection_in_progress = True
            try:
                added_row = self._add_product_to_table_with_row(product, default_qty=0)
                self.product_input.clear()
                if added_row >= 0:
                    self.focus_table_cell_editor(added_row, 8)
            finally:
                self._product_selection_in_progress = False
                self._product_search_selection_committed = False

    def add_product_to_table(self, product, custom_rate=None):
        """Add product to table at first blank row or new row."""
        return self._add_product_to_table_with_row(product, custom_rate)

    def on_creditor_selected(self, model_idx, editor):
        """Handle creditor selection from completer popup."""
        creditor = model_idx.data(Qt.UserRole)
        if creditor:
            self._apply_creditor_to_fields(creditor)

    def _apply_creditor_to_fields(self, creditor):
        """Populate the Purchase party section from a selected creditor record.

        Shared by the inline completer and the Tab-key search popup so both
        entry paths behave identically. The Code box is filled from the stored
        ``party_code`` but stays user-editable; manual edits are confined to the
        active bill layout and never touch the party master profile.
        """
        if not creditor:
            return
        self._creditor_selection_in_progress = True
        try:
            if isinstance(creditor, dict):
                self.creditor_name_input.blockSignals(True)
                self.creditor_name_input.setText(creditor.get('name', ''))
                self.creditor_name_input.blockSignals(False)
                if hasattr(self, 'code_input'):
                    self.code_input.blockSignals(True)
                    self.code_input.setText(str(creditor.get('party_code', '') or ''))
                    self.code_input.blockSignals(False)
                self.address_input.blockSignals(True)
                self.address_input.setText(creditor.get('address', ''))
                self.address_input.blockSignals(False)
                self.mobile_input.blockSignals(True)
                self.mobile_input.setText(creditor.get('mobile_number', ''))
                self.mobile_input.blockSignals(False)
                gstin = creditor.get('gstin', '')
                self.gstin_input.blockSignals(True)
                self.gstin_input.setText(gstin)
                self.gstin_input.blockSignals(False)
                self.selected_creditor_id = creditor.get('id')
                state = creditor.get('state', '')
                if state:
                    self.state_combo.setCurrentText(state)
                elif gstin and len(gstin) >= 2:
                    state_code = gstin[:2].upper()
                    if state_code in self.gst_state_codes:
                        derived_state = self.gst_state_codes[state_code]
                        self.state_combo.setCurrentText(derived_state)
                self._lock_party_fields()
            else:
                self.creditor_name_input.blockSignals(True)
                self.creditor_name_input.setText(str(creditor))
                self.creditor_name_input.blockSignals(False)
        finally:
            self._creditor_selection_in_progress = False

    def _fetch_all_parties_for_popup(self):
        """Return the full party list (debtors + creditors) for the search popup."""
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return list(getattr(self, 'creditors_data', []) or [])
            result = self.party_logic.get_parties(active_company['id'])
            if isinstance(result, dict) and result.get('success'):
                return list(result.get('data') or [])
            if isinstance(result, list):
                return list(result)
        except Exception as exc:
            print(f'Failed to load parties for popup: {exc}')
        return list(getattr(self, 'creditors_data', []) or [])

    def show_creditor_search_popup(self):
        """Open a modal party search popup from the Party Name Tab shortcut.

        Defaults to Creditor accounts (the normal purchase counterparties) but a
        Debtors/Creditors switch lets the user raise a purchase against a debtor
        when required. Focus is locked into the search box on launch.
        """
        all_parties = self._fetch_all_parties_for_popup()
        popup = QDialog(self)
        popup.setWindowTitle('Select Creditor')
        popup.resize(620, 460)
        popup.setModal(True)
        popup.setStyleSheet(theme.entry_picker_dialog_style())
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(16)
        creditor_radio = QRadioButton('Creditors')
        debtor_radio = QRadioButton('Debtors')
        creditor_radio.setChecked(True)
        mode_group = QButtonGroup(popup)
        mode_group.addButton(creditor_radio)
        mode_group.addButton(debtor_radio)
        toggle_row.addWidget(creditor_radio)
        toggle_row.addWidget(debtor_radio)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)
        title_label = QLabel('Search Creditor by name, code, or mobile')
        layout.addWidget(title_label)
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type creditor name / code / mobile...')
        layout.addWidget(search_input)
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(['Name', 'Code', 'Mobile', 'Type', 'Balance'])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setColumnWidth(0, 250)
        table.setColumnWidth(1, 90)
        table.setColumnWidth(2, 120)
        table.setColumnWidth(3, 90)
        apply_adjustable_table_columns(table, auto_size=False)
        layout.addWidget(table)
        visible_parties = []

        def current_mode_types():
            if debtor_radio.isChecked():
                return ('Debtor', 'Debitor', 'Both')
            return ('Creditor', 'Both')

        def populate_rows(filter_text=''):
            visible_parties.clear()
            table.setRowCount(0)
            needle = (filter_text or '').strip().lower()
            allowed_types = current_mode_types()
            for party in all_parties:
                if not isinstance(party, dict):
                    continue
                if (party.get('party_type') or '') not in allowed_types:
                    continue
                searchable = ' '.join([str(party.get('name') or ''), str(party.get('party_code') or ''), str(party.get('mobile_number') or ''), str(party_display_name(party) or '')]).lower()
                if needle and needle not in searchable:
                    continue
                row = table.rowCount()
                table.insertRow(row)
                visible_parties.append(party)
                values = [party_display_name(party), party.get('party_code') or '', party.get('mobile_number') or '', party.get('party_type') or '', f"{float(party.get('opening_balance') or 0):.2f}"]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.UserRole, party)
                    table.setItem(row, col, item)
            if table.rowCount() > 0:
                table.selectRow(0)

        def selected_party():
            row = table.currentRow()
            if row < 0 or row >= len(visible_parties):
                return None
            return visible_parties[row]

        def choose_party():
            party = selected_party()
            if not party:
                return
            self._apply_creditor_to_fields(party)
            popup.accept()
            if hasattr(self, 'barcode_input'):
                QTimer.singleShot(0, self.barcode_input.setFocus)

        def focus_table():
            if table.rowCount() > 0:
                if table.currentRow() < 0:
                    table.selectRow(0)
                table.setFocus()

        def search_key_press(event):
            if event.key() == Qt.Key_Down:
                focus_table()
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                choose_party()
                return
            if event.key() == Qt.Key_Escape:
                popup.reject()
                return
            QLineEdit.keyPressEvent(search_input, event)

        def table_key_press(event):
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                choose_party()
                return
            if event.key() == Qt.Key_Escape:
                popup.reject()
                return
            QTableWidget.keyPressEvent(table, event)

        def on_mode_changed():
            if debtor_radio.isChecked():
                popup.setWindowTitle('Select Debtor')
                title_label.setText('Search Debtor by name, code, or mobile')
                search_input.setPlaceholderText('Type debtor name / code / mobile...')
            else:
                popup.setWindowTitle('Select Creditor')
                title_label.setText('Search Creditor by name, code, or mobile')
                search_input.setPlaceholderText('Type creditor name / code / mobile...')
            populate_rows(search_input.text())
            search_input.setFocus()
        search_input.keyPressEvent = search_key_press
        table.keyPressEvent = table_key_press
        search_input.textChanged.connect(populate_rows)
        creditor_radio.toggled.connect(on_mode_changed)
        table.itemDoubleClicked.connect(lambda _item: choose_party())
        buttons = QHBoxLayout()
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(popup.reject)
        select_btn = QPushButton('Select')
        select_btn.setStyleSheet(theme.entry_select_button_style())
        select_btn.clicked.connect(choose_party)
        buttons.addStretch()
        buttons.addWidget(cancel_btn)
        buttons.addWidget(select_btn)
        layout.addLayout(buttons)
        populate_rows(self.creditor_name_input.text())
        QTimer.singleShot(0, lambda: (search_input.setFocus(), search_input.selectAll()))
        popup.exec()

    def show_product_popup(self):
        """Show the unified product search popup (identical to Sales Entry).

        Uses the debounced DB-backed ``search_products_limited`` lookup so it loads
        instantly for both small and large catalogs without freezing the UI thread.
        """
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        company_id = active_company['id']
        popup = QDialog(self)
        popup.setWindowTitle('Select Product')
        popup.resize(620, 440)
        popup.setStyleSheet(theme.entry_picker_dialog_style())
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)
        top = QHBoxLayout()
        search_lbl = QLabel('Search (name / barcode):')
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type to search…')
        top.addWidget(search_lbl)
        top.addWidget(search_input)
        layout.addLayout(top)
        hint = QLabel('Type to search. Max 100 results shown.')
        hint.setStyleSheet('color: #64748b; font-size: 10px;')
        layout.addWidget(hint)
        tbl = QTableWidget()
        tbl.setColumnCount(5)
        tbl.setHorizontalHeaderLabels(['Name', 'Barcode', 'Code', 'Rate', 'Stock'])
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
            if len(term) < 1:
                return
            results = self.db.search_products_limited(company_id, term, limit=100)
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
                rate = float(product.get('purchase_rate') or product.get('sale_price') or product.get('wholesale_rate') or 0)
                tbl.setItem(row, 3, QTableWidgetItem(f'{rate:.2f}'))
                try:
                    stock = float(self.stock_logic.get_current_stock(company_id, product.get('id')) or 0.0)
                except Exception:
                    stock = float(product.get('quantity') or 0.0)
                tbl.setItem(row, 4, QTableWidgetItem(f'{stock:.3f}'))
            tbl.blockSignals(False)
            tbl.setUpdatesEnabled(True)
            if tbl.rowCount() > 0:
                tbl.selectRow(0)
        _search_timer.timeout.connect(do_search)
        search_input.textChanged.connect(lambda: _search_timer.start())
        initial_term = self.product_input.text().strip() if hasattr(self, 'product_input') else ''
        search_input.setText(initial_term)
        search_input.setFocus()
        if initial_term:
            search_input.selectAll()
            do_search()

        def select_product():
            row = tbl.currentRow()
            if row < 0:
                return
            product_id = tbl.item(row, 0).data(Qt.UserRole)
            full_product = self.db.get_product_by_id(company_id, product_id) if product_id else None
            if full_product:
                product = full_product
            else:
                product = {'id': product_id, 'name': tbl.item(row, 0).text()}
            popup.accept()
            self.add_product_from_popup(product)

        def focus_popup_table():
            if tbl.rowCount() > 0:
                if tbl.currentRow() < 0:
                    tbl.selectRow(0)
                tbl.setFocus()

        def search_key_press(event):
            if event.key() == Qt.Key_Down:
                focus_popup_table()
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                select_product()
                return
            if event.key() == Qt.Key_Escape:
                popup.reject()
                return
            QLineEdit.keyPressEvent(search_input, event)

        def table_key_press(event):
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                select_product()
                return
            if event.key() == Qt.Key_Escape:
                popup.reject()
                return
            QTableWidget.keyPressEvent(tbl, event)
        search_input.keyPressEvent = search_key_press
        tbl.keyPressEvent = table_key_press
        tbl.doubleClicked.connect(select_product)
        btns = QHBoxLayout()
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(popup.reject)
        select_btn = QPushButton('Select')
        select_btn.setStyleSheet(theme.entry_select_button_style())
        select_btn.clicked.connect(select_product)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(select_btn)
        layout.addLayout(btns)
        popup.exec()

    def add_product_from_popup(self, product):
        """Add a product chosen from the unified popup into the items table."""
        if not product:
            return
        added_row = self._add_product_to_table_with_row(product, default_qty=0)
        if hasattr(self, 'product_input'):
            self.product_input.clear()
        if added_row is not None and added_row >= 0:
            self.calculate_totals()
            self.focus_table_cell_editor(added_row, 8)

    def _lock_party_fields(self):
        """Lock party detail fields after creditor selection (except name field)."""
        self._party_fields_locked = True
        self.address_input.setReadOnly(True)
        self.mobile_input.setReadOnly(True)
        self.gstin_input.setReadOnly(True)
        self.state_combo.setEnabled(False)

    def _unlock_party_fields(self):
        """Unlock party detail fields for editing or new creditor selection."""
        self._party_fields_locked = False
        self.creditor_name_input.setReadOnly(False)
        self.address_input.setReadOnly(False)
        self.mobile_input.setReadOnly(False)
        self.gstin_input.setReadOnly(False)
        self.state_combo.setEnabled(True)

    def on_edit_creditor_clicked(self):
        """Handle Edit Creditor button click."""
        if not self.selected_creditor_id:
            QMessageBox.warning(self, 'No Creditor Selected', 'Please select a creditor first.')
            return
        self._editing_creditor = True
        try:
            from PySide6.QtWidgets import QApplication
            main_window = self.window()
            if main_window and hasattr(main_window, 'show_debitor_creditor'):
                main_window.show_debitor_creditor()
                for widget in QApplication.topLevelWidgets():
                    from .debitor_creditor import DebitorCreditorWidget
                    dc_widget = widget.findChild(DebitorCreditorWidget)
                    if dc_widget and hasattr(dc_widget, 'load_party_for_edit'):
                        dc_widget.load_party_for_edit(self.selected_creditor_id)
                        break
                self._start_creditor_refresh_timer()
                return
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'show_debitor_creditor'):
                    widget.show_debitor_creditor()
                    widget.raise_()
                    widget.activateWindow()
                    for top_widget in QApplication.topLevelWidgets():
                        from .debitor_creditor import DebitorCreditorWidget
                        dc_widget = top_widget.findChild(DebitorCreditorWidget)
                        if dc_widget and hasattr(dc_widget, 'load_party_for_edit'):
                            dc_widget.load_party_for_edit(self.selected_creditor_id)
                            break
                    self._start_creditor_refresh_timer()
                    return
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'stack_widget') and hasattr(widget, 'debitor_creditor_widget'):
                    if hasattr(widget.debitor_creditor_widget, 'load_party_for_edit'):
                        widget.debitor_creditor_widget.load_party_for_edit(self.selected_creditor_id)
                    widget.stack_widget.setCurrentWidget(widget.debitor_creditor_widget)
                    widget.raise_()
                    widget.activateWindow()
                    self._start_creditor_refresh_timer()
                    return
        except Exception as e:
            QMessageBox.warning(self, 'Navigation Error', f'Could not open Debtor/Creditor page: {e}')
            self._editing_creditor = False

    def refresh_selected_creditor_from_db(self):
        """Refresh the selected creditor from database without resetting purchase bill/table."""
        if not self.selected_creditor_id:
            return
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            self.load_creditors()
            from .purchase_entry_popup import setup_creditor_completer
            setup_creditor_completer(self.creditor_name_input, self, self.on_creditor_selected)
            result = self.party_logic.get_party_by_id(active_company['id'], self.selected_creditor_id)
            if result['success'] and result['data']:
                creditor = result['data']
                self._creditor_selection_in_progress = True
                self.creditor_name_input.setText(creditor.get('name', ''))
                self.address_input.setText(creditor.get('address', ''))
                self.mobile_input.setText(creditor.get('mobile_number', ''))
                gstin = creditor.get('gstin', '')
                self.gstin_input.setText(gstin)
                state = creditor.get('state', '')
                if state:
                    self.state_combo.setCurrentText(state)
                elif gstin and len(gstin) >= 2:
                    state_code = gstin[:2].upper()
                    if state_code in self.gst_state_codes:
                        derived_state = self.gst_state_codes[state_code]
                        self.state_combo.setCurrentText(derived_state)
                self._creditor_selection_in_progress = False
        except Exception as e:
            print(f'Error refreshing creditor from DB: {e}')
            self._creditor_selection_in_progress = False

    def on_address_changed(self, text):
        """Handle address text change - apply title case formatting."""
        if not text:
            return
        was_blocked = self.address_input.blockSignals(True)
        try:
            self.address_input.setText(text.title())
        finally:
            self.address_input.blockSignals(was_blocked)

    def on_gstin_changed(self, text):
        """Handle GSTIN text change - convert to uppercase and validate."""
        was_blocked = self.gstin_input.blockSignals(True)
        try:
            self.gstin_input.setText(text.upper())
            if not text or not text.strip():
                self.state_combo.blockSignals(True)
                self.state_combo.setCurrentText('')
                self.state_combo.blockSignals(False)
                return
            if len(text) >= 2:
                state_code = text[:2].upper()
                if not self.state_combo.currentText():
                    state_name = self.get_state_name_from_code(state_code)
                    if state_name:
                        self.state_combo.setCurrentText(state_name)
        finally:
            self.gstin_input.blockSignals(was_blocked)

    def get_state_name_from_code(self, state_code):
        """Get state name from GSTIN state code using shared GST_STATE_CODES."""
        return self.gst_state_codes.get(state_code)

    def on_state_changed(self, text):
        if not text:
            return
        words = text.split(' ')
        capitalized_words = []
        for word in words:
            if word:
                capitalized_words.append(word[:1].upper() + word[1:])
            else:
                capitalized_words.append('')
        new_text = ' '.join(capitalized_words)
        if new_text != text:
            cursor_pos = self.state_combo.cursorPosition()
            self.state_combo.blockSignals(True)
            self.state_combo.setText(new_text)
            self.state_combo.setCursorPosition(min(cursor_pos, len(new_text)))
            self.state_combo.blockSignals(False)

    def on_creditor_name_changed(self, text):
        """Handle creditor name text change - apply title case and unlock for new creditor selection."""
        if not text or not text.strip():
            if not self._creditor_selection_in_progress:
                self._clear_party_linked_fields()
            return
        if self._party_fields_locked and self.selected_creditor_id and (not self._creditor_selection_in_progress):
            self._unlock_party_fields()
            self.selected_creditor_id = None
            self.address_input.clear()
            self.mobile_input.clear()
            self.gstin_input.clear()
            self.state_combo.setCurrentIndex(0)
            from .purchase_entry_popup import setup_creditor_completer
            setup_creditor_completer(self.creditor_name_input, self, self.on_creditor_selected)
        if not self._creditor_selection_in_progress:
            was_blocked = self.creditor_name_input.blockSignals(True)
            try:
                self.creditor_name_input.setText(text.title())
            finally:
                self.creditor_name_input.blockSignals(was_blocked)

    def _clear_party_linked_fields(self):
        """Blank every party-linked field after the Name box is emptied.

        Signals are blocked during the reset to avoid recursive textChanged loops
        and to keep the cleanup stable on the Windows UI thread.
        """
        self.selected_creditor_id = None
        if getattr(self, '_party_fields_locked', False) and hasattr(self, '_unlock_party_fields'):
            self._unlock_party_fields()
        for widget in (getattr(self, 'code_input', None), getattr(self, 'address_input', None), getattr(self, 'mobile_input', None), getattr(self, 'gstin_input', None)):
            if widget is not None:
                widget.blockSignals(True)
                widget.clear()
                widget.blockSignals(False)
        if hasattr(self, 'state_combo'):
            self.state_combo.blockSignals(True)
            self.state_combo.setCurrentIndex(0)
            self.state_combo.blockSignals(False)
        if hasattr(self, 'update_footer_payment_fields'):
            self.update_footer_payment_fields()

    def on_creditor_editing_finished(self):
        """Handle creditor name editing finished - refresh creditors list to get latest data."""
        QTimer.singleShot(50, self.load_creditors)

    def _on_creditor_mouse_press(self, event):
        """Handle creditor name input mouse press - refresh creditors list to get latest data."""
        self.load_creditors()
        QLineEdit.mousePressEvent(self.creditor_name_input, event)

    def _on_creditor_focus_in(self, event):
        """Handle creditor name input focus in - refresh creditors list to get latest data."""
        self.load_creditors()
        QLineEdit.focusInEvent(self.creditor_name_input, event)

    def on_code_changed(self, text):
        """Force the Party Code into uppercase as the user types.

        Signals are blocked while rewriting so the mutator never re-enters itself,
        and the caret is restored to keep typing smooth.
        """
        if not text:
            return
        upper = text.upper()
        if upper != text:
            cursor_pos = self.code_input.cursorPosition()
            self.code_input.blockSignals(True)
            self.code_input.setText(upper)
            self.code_input.setCursorPosition(min(cursor_pos, len(upper)))
            self.code_input.blockSignals(False)

    def on_narration_changed(self, text):
        """Handle narration text change - apply title case formatting."""
        if not text:
            return
        was_blocked = self.narration_input.blockSignals(True)
        try:
            self.narration_input.setText(text.title())
        finally:
            self.narration_input.blockSignals(was_blocked)

    def on_table_selection_changed(self):
        """Keep Qt selection from forcing full-row blue selection.

        Manual row selection is controlled only by clicking the SL column.
        Normal editable-cell clicks open an editor and must not mark the whole row.
        Also updates top bar labels with selected row's product info.
        """
        if getattr(self, '_suppress_table_selection_changed', False):
            return
        self.items_table.clearSelection()
        self.items_table.viewport().update()
        if self.manually_selected_row == -1:
            return
        current_row = self.items_table.currentRow()
        if current_row >= 0:
            self._update_purchase_row_status_display(current_row)

    def on_table_cell_changed(self, row, column):
        """Handle table cell change."""
        if column == 2:
            product_name = self.safe_item_text(row, 2)
            if product_name and product_name.strip():
                active_company = active_company_manager.get_active_company()
                if active_company:
                    product = self.db.get_product_by_exact_name(active_company['id'], product_name)
                    if product:
                        product_item = self.items_table.item(row, 2)
                        if product_item:
                            product_item.setData(Qt.UserRole, product.get('id'))
                        if row < len(self.purchase_items):
                            self.purchase_items[row]['product_id'] = product.get('id')
                            self.purchase_items[row]['name'] = product.get('name', '')
                            self.purchase_items[row]['hsn'] = product.get('hsn', '')
                            self.purchase_items[row]['hsn_code'] = product.get('hsn', '')
                            self.purchase_items[row]['supplier_code'] = self._current_supplier_code()
                            self.purchase_items[row]['source_cgst'] = float(product.get('cgst', 0) or 0)
                            self.purchase_items[row]['source_sgst'] = float(product.get('sgst', 0) or 0)
                            self.purchase_items[row]['source_igst'] = float(product.get('igst', 0) or 0)
                            self.purchase_items[row]['source_cess'] = float(product.get('cess', 0) or 0)
                        self._apply_nature_tax_to_row(row, product)
                        self.recalculate_row(row, source_column=column)
        if column in [4, 5, 6, 7, 8, 9, 10, 11]:
            self.recalculate_row(row, source_column=column, live_value=self.safe_item_text(row, column))

    def add_product_row(self, product_data):
        """Fill the first blank product row or append a populated row if needed."""
        if not product_data:
            return -1

        def to_float(value, default=0.0):
            try:
                return float(value or default)
            except (TypeError, ValueError):
                return default
        current_row = self.find_blank_row()
        if current_row < 0:
            current_row = self.add_blank_row()
        was_blocked = self.table.blockSignals(True)
        try:
            ensure_row_items_initialized(self.table, current_row)
            sl_item = self.table.item(current_row, 0)
            if sl_item:
                sl_item.setText(str(current_row + 1))
            sales_rate = to_float(product_data.get('sale_price') or product_data.get('sales_rate'))
            custom_rate = product_data.get('_custom_rate')
            rate = to_float(custom_rate if custom_rate is not None else product_data.get('purchase_rate'))
            qty_value = to_float(product_data.get('_default_qty'))
            values = {1: f'{sales_rate:.2f}', 2: product_data.get('name', ''), 3: product_data.get('hsn', ''), 8: f'{rate:.2f}', 9: '' if qty_value == 0 else f'{qty_value:.2f}'}
            for col, text in values.items():
                item = self.table.item(current_row, col)
                if item:
                    item.setText(str(text))
                    if col == 2:
                        item.setData(Qt.UserRole, product_data.get('id'))
            from PySide6.QtGui import QColor
            sr_item = self.table.item(current_row, 1)
            if sr_item:
                sr_item.setBackground(QColor(theme.table_row_bg_color()))
                sr_item.setForeground(QColor('#64748b'))
                sr_item.setFlags(sr_item.flags() & ~Qt.ItemIsEditable)
            while len(self.purchase_items) <= current_row:
                self.purchase_items.append(self._blank_purchase_item())
            self.purchase_items[current_row] = {**self._blank_purchase_item(), 'product_id': product_data.get('id'), 'name': product_data.get('name', ''), 'hsn': product_data.get('hsn', ''), 'hsn_code': product_data.get('hsn', ''), 'supplier_code': self._current_supplier_code(), 'source_cgst': to_float(product_data.get('cgst')), 'source_sgst': to_float(product_data.get('sgst')), 'source_igst': to_float(product_data.get('igst')), 'source_cess': to_float(product_data.get('cess')), 'rate': rate, 'quantity': qty_value}
        finally:
            self.table.blockSignals(was_blocked)
        product_id = product_data.get('id')
        if product_id:
            self.products_dict[product_id] = product_data
        self._apply_nature_tax_to_row(current_row, product_data)
        self.recalculate_row(current_row, source_column=COL_QTY, live_value=qty_value)
        self.calculate_grand_totals()
        self.focus_table_cell_editor(current_row, COL_RATE)
        return current_row

    def add_blank_row(self):
        """Add a blank row to the table and return its row index."""
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        for col in range(15):
            item = QTableWidgetItem('')
            self.items_table.setItem(row, col, item)
        self.purchase_items.append(self._blank_purchase_item())
        sl_item = self.items_table.item(row, 0)
        if sl_item:
            sl_item.setText(str(row + 1))
        sr_item = self.items_table.item(row, 1)
        if sr_item:
            from PySide6.QtGui import QColor
            sr_item.setBackground(QColor(theme.table_row_bg_color()))
            sr_item.setForeground(QColor('#64748b'))
            sr_item.setFlags(sr_item.flags() & ~Qt.ItemIsEditable)
        return row

    def _blank_purchase_item(self):
        """Return metadata for an empty prefilled purchase row."""
        return {'product_id': None, 'name': '', 'hsn': '', 'hsn_code': '', 'supplier_code': '', 'source_cgst': 0, 'source_sgst': 0, 'source_igst': 0, 'source_cess': 0, 'cgst': 0, 'sgst': 0, 'igst': 0, 'cess': 0, 'rate': 0, 'tax_percent': 0, 'quantity': 0, 'cgst_amount': 0, 'sgst_amount': 0, 'igst_amount': 0, 'cess_amount': 0, 'disc_mode': 'flat'}

    def _ensure_prefilled_blank_rows(self, minimum_rows=None):
        """Ensure the purchase grid has the standard blank editable rows."""
        target_rows = minimum_rows or self.DEFAULT_PREFILLED_ROWS
        was_blocked = self.items_table.blockSignals(True)
        try:
            while self.items_table.rowCount() < target_rows:
                self.add_blank_row()
        finally:
            self.items_table.blockSignals(was_blocked)

    def find_blank_row(self):
        """Return the first row without a committed product identity."""
        for row in range(self.items_table.rowCount()):
            if not self._row_has_committed_product(row):
                return row
        return -1

    def _row_has_committed_product(self, row):
        """Return True when a row is linked to a valid product identity."""
        if row < 0:
            return False
        if row < len(self.purchase_items) and self.purchase_items[row].get('product_id'):
            return True
        product_item = self.items_table.item(row, 2)
        if product_item and product_item.data(Qt.UserRole):
            return True
        return False

    def _clear_uncommitted_product_cell(self, row):
        """Clear stray typed Product text when it is not linked to a product."""
        if row < 0 or row >= self.items_table.rowCount():
            return
        if self._row_has_committed_product(row):
            return
        product_item = self.items_table.item(row, 2)
        if not product_item or not product_item.text().strip():
            return
        was_blocked = self.items_table.blockSignals(True)
        try:
            for col in range(1, 15):
                item = self.items_table.item(row, col)
                if item:
                    item.setText('')
                    if col == 2:
                        item.setData(Qt.UserRole, None)
        finally:
            self.items_table.blockSignals(was_blocked)
        if row < len(self.purchase_items):
            self.purchase_items[row] = self._blank_purchase_item()
        self.recalculate_row(row, source_column=None)
        self.calculate_grand_totals()

    def _clear_all_uncommitted_product_cells(self, except_row=None):
        """Clear any typed product text that was abandoned without Enter."""
        for row in range(self.items_table.rowCount()):
            if except_row is not None and row == except_row:
                continue
            self._clear_uncommitted_product_cell(row)

    def handle_product_cell_enter(self, row, typed_name):
        """Open Product Entry with typed Product text when row is not linked."""
        typed_name = (typed_name or '').strip()
        if row < 0 or row >= self.items_table.rowCount():
            return False
        if self._row_has_committed_product(row):
            return False
        if not typed_name:
            return False
        self.open_product_entry_new_from_row(row, typed_name)
        return True

    def recalculate_row(self, row, source_column=None, live_value=None):
        """Wrapper for recalculate_row function."""
        _recalculate_row(self, row, source_column, live_value)

    def calculate_totals(self):
        """Wrapper for calculate_totals function."""
        if getattr(self, '_is_loading', False):
            return
        _calculate_totals(self)

    def calculate_grand_totals(self):
        """Recalculate all purchase footer totals after table row changes."""
        self.calculate_totals()

    def safe_item_text(self, row, col, default=''):
        """Wrapper for safe_item_text function."""
        return safe_item_text(self.items_table, row, col, default)

    def safe_float_from_cell(self, row, col, default=0.0):
        """Wrapper for safe_float_from_cell function."""
        return safe_float_from_cell(self.items_table, row, col, default)

    def ensure_row_items_initialized(self, row):
        """Wrapper for ensure_row_items_initialized function."""
        ensure_row_items_initialized(self.items_table, row)

    def _refresh_save_button_text(self):
        """Show 'Update' when a saved bill is loaded, 'Save' for a fresh entry."""
        if hasattr(self, 'save_btn'):
            self.save_btn.setText('Update' if getattr(self, 'current_purchase_id', None) else 'Save')

    def open_import_po_dialog(self):
        """Open pending PO picker and load the chosen order into the bill grid."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'Import PO', 'Please open a company first.')
            return
        dialog = POSelectionDialog(self.db, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_po_id:
            return
        self.load_purchase_order_into_bill(dialog.selected_po_id)

    def load_purchase_order_into_bill(self, po_id: int):
        """Populate creditor and grid rows from a pending purchase order."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return
        company_id = active_company['id']
        ph = self.db._get_placeholder()
        try:
            header_rows = self.db.execute_query(f'\n                SELECT id, po_number, date, creditor_name, grand_total, status\n                FROM purchase_orders\n                WHERE id = {ph} AND company_id = {ph} AND status = {ph}\n                ', (po_id, company_id, 'Pending'))
            if not header_rows:
                QMessageBox.warning(self, 'Import PO', 'Purchase order not found or is no longer pending.')
                return
            header = header_rows[0]
            if isinstance(header, dict):
                creditor_name = str(header.get('creditor_name', '') or '').strip()
                po_number = str(header.get('po_number', '') or '')
            else:
                creditor_name = str(header[3] if len(header) > 3 else '').strip()
                po_number = str(header[1] if len(header) > 1 else '')
            item_rows = self.db.execute_query(f'\n                SELECT barcode, product_name, qty, rate, discount,\n                       tax_amount, net_amount\n                FROM purchase_order_items\n                WHERE po_id = {ph}\n                ORDER BY id\n                ', (po_id,)) or []
        except Exception as exc:
            QMessageBox.critical(self, 'Import PO', f'Failed to read purchase order: {exc}')
            return
        if not item_rows:
            QMessageBox.warning(self, 'Import PO', 'This purchase order has no line items.')
            return
        self._is_loading = True
        self.items_table.blockSignals(True)
        self.blockSignals(True)
        try:
            self.current_purchase_id = None
            self.active_loaded_po_id = int(po_id)
            self._refresh_save_button_text()
            self.creditor_name_input.blockSignals(True)
            self.creditor_name_input.setText(creditor_name)
            self.creditor_name_input.blockSignals(False)
            matched_creditor = None
            for creditor in getattr(self, 'creditors_data', []) or []:
                if party_matches_text(creditor, creditor_name):
                    matched_creditor = creditor
                    break
            if matched_creditor:
                self._apply_creditor_to_fields(matched_creditor)
            else:
                self.selected_creditor_id = None
            if po_number and hasattr(self, 'supplier_invoice_input'):
                self.supplier_invoice_input.setText(f'PO-{po_number}')
            self.items_table.setRowCount(0)
            self.purchase_items = []
            unresolved = []
            for idx, line in enumerate(item_rows):
                if isinstance(line, dict):
                    barcode = str(line.get('barcode', '') or '').strip()
                    product_name = str(line.get('product_name', '') or '').strip()
                    qty = float(line.get('qty', 0) or 0)
                    rate = float(line.get('rate', 0) or 0)
                    discount = float(line.get('discount', 0) or 0)
                else:
                    barcode = str(line[0] if len(line) > 0 else '').strip()
                    product_name = str(line[1] if len(line) > 1 else '').strip()
                    qty = float(line[2] or 0) if len(line) > 2 else 0.0
                    rate = float(line[3] or 0) if len(line) > 3 else 0.0
                    discount = float(line[4] or 0) if len(line) > 4 else 0.0
                product = None
                if barcode:
                    product = self.db.get_product_by_barcode(company_id, barcode)
                if not product and product_name:
                    product = self.db.get_product_by_exact_name(company_id, product_name)
                self.add_blank_row()
                row = idx
                if product:
                    sales_rate = float(product.get('sale_price', 0) or product.get('sales_rate', 0) or 0)
                    product_id = product.get('id')
                    name_item = self.items_table.item(row, 2)
                    if name_item:
                        name_item.setText(product.get('name', product_name))
                        name_item.setData(Qt.UserRole, product_id)
                    sr_item = self.items_table.item(row, 1)
                    if sr_item:
                        sr_item.setText(f'{sales_rate:.2f}')
                    hsn_item = self.items_table.item(row, 3)
                    if hsn_item:
                        hsn_item.setText(str(product.get('hsn', '') or ''))
                    self.purchase_items[row] = {'product_id': product_id, 'name': product.get('name', product_name), 'hsn': product.get('hsn', ''), 'hsn_code': product.get('hsn', ''), 'supplier_code': self._current_supplier_code(), 'source_cgst': float(product.get('cgst', 0) or 0), 'source_sgst': float(product.get('sgst', 0) or 0), 'source_igst': float(product.get('igst', 0) or 0), 'source_cess': float(product.get('cess', 0) or 0), 'cgst': 0, 'sgst': 0, 'igst': 0, 'cess': 0, 'rate': rate, 'tax_percent': 0, 'quantity': qty, 'disc_mode': 'flat'}
                    self._apply_nature_tax_to_row(row, product)
                else:
                    name_item = self.items_table.item(row, 2)
                    if name_item:
                        name_item.setText(product_name)
                    unresolved.append(product_name or barcode or f'Line {idx + 1}')
                rate_item = self.items_table.item(row, 8)
                if rate_item:
                    rate_item.setText(f'{rate:.2f}')
                qty_item = self.items_table.item(row, 9)
                if qty_item:
                    qty_item.setText(f'{qty:.2f}' if qty else '')
                disc_item = self.items_table.item(row, 11)
                if disc_item:
                    disc_item.setText(f'{discount:.2f}')
                if idx % 3 == 0:
                    QCoreApplication.processEvents()
        finally:
            self.items_table.blockSignals(False)
            self.blockSignals(False)
            self._is_loading = False
        self._ensure_prefilled_blank_rows(max(self.DEFAULT_PREFILLED_ROWS, len(item_rows)))
        for row in range(self.items_table.rowCount()):
            if self.safe_item_text(row, 2).strip():
                self.recalculate_row(row, source_column=None)
                if row % 4 == 0:
                    QCoreApplication.processEvents()
        self.calculate_totals()
        if unresolved:
            QMessageBox.warning(self, 'Import PO', 'Some lines could not be matched to products in your master list:\n' + '\n'.join(unresolved[:8]) + ('\n...' if len(unresolved) > 8 else ''))
        QMessageBox.information(self, 'Import PO', f'Purchase Order {po_number} loaded. Save the bill to complete conversion.')

    def clear_form(self):
        """Clear all form fields and reset to blank state."""
        self._begin_entry_reset()
        try:
            self.current_purchase_id = None
            self.active_loaded_po_id = None
            self.purchase_items = []
            self._purchase_nav_ids = []
            self._amt_paid_user_edited = False
            self._refresh_save_button_text()
            self.purchase_no_input.clear()
            self.date_input.setDate(QDate.currentDate())
            from bizora_core.entry_type_defaults import apply_entry_type_combo, get_active_company_default_entry_type
            apply_entry_type_combo(
                self.purchase_type_combo,
                get_active_company_default_entry_type(self.db, "purchase"),
            )
            self.series_input.clear()
            self.nature_combo.setCurrentText('Local')
            self.party_type_combo.setCurrentText('Creditor')
            self.due_date_input.setDate(QDate.currentDate())
            self.creditor_name_input.clear()
            if hasattr(self, 'code_input'):
                self.code_input.clear()
            self.address_input.clear()
            self.mobile_input.clear()
            self.gstin_input.clear()
            self.state_combo.setCurrentIndex(0)
            self.supplier_invoice_input.clear()
            self.narration_input.clear()
            self.barcode_input.clear()
            if hasattr(self, 'product_input'):
                self.product_input.clear()
            if hasattr(self, 'discount_total_input'):
                self.discount_total_input.blockSignals(True)
                self.discount_total_input.setText('0.00')
                self.discount_total_input.blockSignals(False)
            if hasattr(self, 'discount_percent_label'):
                self.discount_percent_label.setText('')
            if hasattr(self, 'discount_status_display'):
                self.discount_status_display.setText('0%')
            self.round_off_input.setText('0')
            self.amt_paid_input.setText('0')
            self.selected_creditor_id = None
            self._party_fields_locked = False
            if hasattr(self, '_unlock_party_fields'):
                self._unlock_party_fields()
            if hasattr(self, 'purchase_checkbox'):
                self.purchase_checkbox.setChecked(False)
            self.items_table.setRowCount(0)
            self.purchase_items = []
            self._ensure_prefilled_blank_rows()
            self.calculate_grand_totals()
            if not getattr(self, '_suppress_initial_purchase_number', False):
                self.generate_purchase_number()
            QTimer.singleShot(0, lambda: self.barcode_input.setFocus())
        finally:
            self._end_entry_reset()

    def _print_settings_metadata(self, settings):
        """Return metadata embedded in saved print layout coordinates."""
        raw_coordinates = (settings or {}).get('layout_coordinates', '') or ''
        if not raw_coordinates:
            return {}
        try:
            coordinates = json.loads(raw_coordinates)
        except (TypeError, json.JSONDecodeError) as exc:
            print(f'Invalid print settings metadata JSON: {exc}')
            return {}
        if not isinstance(coordinates, dict):
            return {}
        metadata = coordinates.get('__settings__', {})
        return metadata if isinstance(metadata, dict) else {}

    def _a4_theme_name(self, settings):
        """Return the active A4 invoice theme from saved print settings."""
        a4_theme_names = {'GST Standard', 'Modern Clean', 'Elegant Serif', 'Compact Wholesale', 'Bold Corporate', 'Bill of Supply', 'Color Block Header', 'Vibrant Accent', 'Modern Gradient'}
        settings = settings or {}
        metadata = self._print_settings_metadata(settings)
        for key in ('a4_theme', 'default_theme', 'theme'):
            theme_name = str(metadata.get(key) or settings.get(key) or '').strip()
            if theme_name in a4_theme_names:
                return theme_name
        return 'GST Standard'

    def export_pdf(self):
        """Open the current purchase invoice in the universal preview dialog."""
        if not self.current_purchase_id:
            QMessageBox.warning(self, 'Export Blocked', 'Please save the voucher before previewing.')
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'Export Blocked', 'No active company selected.')
            return
        cart_data = self._build_purchase_a4_cart_data()
        if not cart_data:
            QMessageBox.warning(self, 'Preview Purchase', 'Please add at least one item with quantity before previewing.')
            return
        try:
            settings = get_print_settings(self.db, active_company['id'])
            html_string = generate_a4_html(company_print_data(active_company), cart_data, totals_data=self._build_purchase_a4_totals_data(cart_data), settings=settings, theme_name=self._a4_theme_name(settings))
            dialog = UniversalPreviewDialog(html_string, self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, 'Preview Failed', f'Could not preview purchase bill:\n{exc}')

    def previous_bill(self):
        """Navigate to previous purchase."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return
        if not self._purchase_nav_ids:
            self._purchase_nav_ids = self.db.get_purchase_nav_ids(active_company['id'])
        if not self._purchase_nav_ids:
            QMessageBox.information(self, 'Info', 'No purchases found.')
            return
        current_pos = -1
        if self.current_purchase_id:
            try:
                current_pos = self._purchase_nav_ids.index(self.current_purchase_id)
            except ValueError:
                current_pos = -1
        if current_pos > 0:
            prev_id = self._purchase_nav_ids[current_pos - 1]
            self.load_purchase(prev_id)
        elif current_pos == -1:
            self.load_purchase(self._purchase_nav_ids[0])
        else:
            QMessageBox.information(self, 'Info', 'This is the first purchase.')

    def next_bill(self):
        """Open a fresh purchase with the next sequential purchase number."""
        self.open_next_numbered_entry()

    def load_purchase(self, purchase_id):
        """Load a purchase into the form."""
        self._is_loading = True
        self.items_table.blockSignals(True)
        self.blockSignals(True)
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            purchase_logic = self._get_purchase_logic()
            result = purchase_logic.get_purchase_by_id(active_company['id'], purchase_id)
            if not result or not result.get('success') or (not result.get('data')):
                QMessageBox.warning(self, 'Error', 'Purchase not found.')
                return
            purchase = result['data']
            self.current_purchase_id = purchase_id
            self.active_loaded_po_id = None
            self.purchase_no_input.setText(purchase.get('purchase_number', ''))
            self.date_input.setDate(QDate.fromString(purchase.get('purchase_date', ''), 'yyyy-MM-dd'))
            self.purchase_type_combo.setCurrentText(purchase.get('purchase_type', 'Cash'))
            self.series_input.setText(purchase.get('bill_series', ''))
            self.nature_combo.setCurrentText(purchase.get('nature', 'Local'))
            self.party_type_combo.setCurrentText('Creditor')
            self.due_date_input.setDate(QDate.fromString(purchase.get('due_date', ''), 'yyyy-MM-dd'))
            self.purchase_checkbox.setChecked(True)
            self.purchase_no_input.setPlaceholderText('')
            creditor_id = purchase.get('party_id')
            creditor = self.db.get_party_by_id(active_company['id'], creditor_id)
            if creditor:
                self.creditor_name_input.setText(creditor.get('name', ''))
                if hasattr(self, 'code_input'):
                    self.code_input.setText(str(creditor.get('party_code', '') or ''))
                self.address_input.setText(creditor.get('address', ''))
                self.mobile_input.setText(creditor.get('mobile_number', ''))
                self.gstin_input.setText(creditor.get('gstin', ''))
                self.state_combo.setCurrentText(creditor.get('state', ''))
            self.narration_input.setText(purchase.get('narration', ''))
            self.supplier_invoice_input.setText(purchase.get('supplier_invoice_no', ''))
            self.round_off_input.setText(str(purchase.get('round_off', 0)))
            self.amt_paid_input.setText(str(purchase.get('amount_paid', 0)))
            self._amt_paid_user_edited = False
            self.items_table.setRowCount(0)
            self.purchase_items = []
            purchase_logic = self._get_purchase_logic()
            items_result = purchase_logic.get_purchase_items(purchase_id)
            purchase_items_data = items_result.get('data', []) if items_result and items_result.get('success') else []
            for idx, item in enumerate(purchase_items_data):
                self.add_blank_row()
                row = idx
                product_id = item.get('product_id')
                product = self.db.get_product_by_id(active_company['id'], product_id)
                if product:
                    product_name_item = self.items_table.item(row, 2)
                    if product_name_item:
                        product_name_item.setText(product.get('name', ''))
                        product_name_item.setData(Qt.UserRole, product_id)
                    sales_rate = float(product.get('sale_price', 0) or product.get('sales_rate', 0) or 0)
                    sr_item = self.items_table.item(row, 1)
                    if sr_item:
                        sr_item.setText(f'{sales_rate:.2f}')
                nature = purchase.get('nature', 'Local')
                cgst = float(item.get('cgst', 0))
                sgst = float(item.get('sgst', 0))
                igst = float(item.get('igst', 0))
                cess = float(item.get('cess', 0))
                tax_percent = float(item.get('tax_percent', 0))
                if cgst == 0 and sgst == 0 and (igst == 0) and (tax_percent > 0):
                    if nature == 'Inter-state':
                        igst = tax_percent
                        cgst = 0
                        sgst = 0
                    else:
                        cgst = tax_percent / 2
                        sgst = tax_percent / 2
                        igst = 0
                self.items_table.item(row, 3).setText(item.get('hsn', ''))
                self.items_table.item(row, 4).setText(f'{cgst:.2f}')
                self.items_table.item(row, 5).setText(f'{sgst:.2f}')
                self.items_table.item(row, 6).setText(f'{igst:.2f}')
                self.items_table.item(row, 7).setText(f'{cess:.2f}')
                self.items_table.item(row, 8).setText(str(item.get('rate', 0)))
                self.items_table.item(row, 9).setText(str(item.get('quantity', 0)))
                self.items_table.item(row, 10).setText(str(item.get('gross_value', 0)))
                _disc_amt = float(item.get('discount', 0) or 0)
                self.items_table.item(row, 11).setText(f'{_disc_amt:.2f}')
                self.items_table.item(row, 12).setText(str(item.get('net_value', 0)))
                self.items_table.item(row, 13).setText(str(item.get('tax_amount', 0)))
                self.items_table.item(row, 14).setText(str(item.get('grand_total', 0)))
                self.purchase_items[row] = {'product_id': product_id, 'name': product.get('name', '') if product else '', 'hsn': item.get('hsn', ''), 'hsn_code': item.get('hsn', ''), 'supplier_code': self._current_supplier_code(), 'source_cgst': cgst, 'source_sgst': sgst, 'source_igst': igst, 'source_cess': cess, 'cgst': cgst, 'sgst': sgst, 'igst': igst, 'cess': cess, 'cgst_amount': float(item.get('cgst_amount', 0)), 'sgst_amount': float(item.get('sgst_amount', 0)), 'igst_amount': float(item.get('igst_amount', 0)), 'cess_amount': float(item.get('cess_amount', 0)), 'rate': item.get('rate', 0), 'tax_percent': tax_percent, 'quantity': float(item.get('quantity', 0)), 'disc_mode': 'flat'}
            self._ensure_prefilled_blank_rows(max(self.DEFAULT_PREFILLED_ROWS, len(purchase_items_data)))
            self._is_loading = False
            self.calculate_grand_totals()
            self._is_loading = True
        finally:
            self.items_table.blockSignals(False)
            self.blockSignals(False)
            self._is_loading = False
            self._refresh_save_button_text()
            self._schedule_entry_baseline_finalize()

    def load_voucher(self, voucher_id: int):
        """
        Standardized voucher loading method for Ledger drill-down.
        
        This method provides a consistent interface for loading vouchers from the Ledger page.
        It sets the current_voucher_id and current_purchase_id and delegates to the existing load_purchase method.
        
        Args:
            voucher_id: The purchase ID to load
        """
        self._skip_initial_load = True
        self.current_voucher_id = voucher_id
        self.current_purchase_id = voucher_id
        self.load_purchase(voucher_id)

    def confirm_remove_purchase(self):
        """Confirm and remove current purchase."""
        if self.current_purchase_id:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                QMessageBox.information(self, 'Info', 'Please open a company first.')
                return
            if not confirm_before_delete_transaction(
                self,
                'Confirm Remove',
                'Are you sure you want to remove this purchase?',
                db=self.db,
                company_id=active_company['id'],
            ):
                return
            purchase_logic = self._get_purchase_logic()
            result = purchase_logic.delete_purchase(active_company['id'], self.current_purchase_id)
            if result['success']:
                QMessageBox.information(self, 'Success', result['message'])
                self.clear_form()
                self._purchase_nav_ids = self.db.get_purchase_nav_ids(active_company['id'])
            else:
                QMessageBox.warning(self, 'Error', result['message'])
        else:
            QMessageBox.information(self, 'Info', 'No purchase to remove.')

    def confirm_remove_item(self):
        """Confirm and remove selected item - only works if SL No was clicked first."""
        row = getattr(self, 'manually_selected_row', -1)
        if row < 0 or row >= self.items_table.rowCount():
            QMessageBox.information(self, 'Remove Item', 'Please click the SL No of the item you want to remove, then press Remove Item.')
            return
        product_name = self.safe_item_text(row, 2)
        if not product_name:
            QMessageBox.information(self, 'Remove Item', 'Selected row is blank.')
            return
        reply = QMessageBox.question(self, 'Confirm Remove Item', f'Are you sure you want to remove row {row + 1}?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.delete_row(row)
        self.manually_selected_row = -1
        self.items_table.clearSelection()
        self.items_table.viewport().update()
        self.calculate_grand_totals()

    def delete_row(self, row):
        """Delete specified row from table."""
        if row < 0 or row >= self.table.rowCount():
            return
        self.table.removeRow(row)
        if row < len(self.purchase_items):
            del self.purchase_items[row]
        for r in range(self.table.rowCount()):
            sl_item = self.table.item(r, 0)
            if sl_item:
                sl_item.setText(str(r + 1))
        self._ensure_prefilled_blank_rows()
        self.calculate_grand_totals()
        if self.table.rowCount() > 0:
            focus_row = min(row, self.table.rowCount() - 1)
            self.table.setCurrentCell(focus_row, COL_RATE)
        elif hasattr(self, 'barcode_input'):
            self.barcode_input.setFocus()

    def _current_supplier_code(self):
        """Return the current purchase party short code for barcode labels."""
        try:
            if hasattr(self, 'code_input'):
                return (self.code_input.text() or '').strip().upper()
        except Exception:
            return ''
        return ''

    def _purchase_row_supplier_code(self, row):
        """Return any supplier short code already stored on a purchase row."""
        try:
            if 0 <= row < len(self.purchase_items):
                return str(self.purchase_items[row].get('supplier_code', '') or '').strip().upper()
        except Exception:
            return ''
        return ''

    def print_invoice(self):
        """Print the current purchase bill through the shared A4 engine."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'Print Purchase', 'Please open a company first.')
            return
        cart_data = self._build_purchase_a4_cart_data()
        if not cart_data:
            QMessageBox.warning(self, 'Print Purchase', 'Please add at least one item with quantity before printing.')
            return
        try:
            settings = get_print_settings(self.db, active_company['id'])
            html_string = generate_a4_html(company_print_data(active_company), cart_data, totals_data=self._build_purchase_a4_totals_data(cart_data), settings=settings, theme_name=self._a4_theme_name(settings))
            dialog = UniversalPreviewDialog(html_string, mode='A4', parent=self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Could not print purchase bill:\n{exc}')

    def _build_purchase_a4_cart_data(self):
        """Collect non-empty purchase rows for A4 invoice HTML."""
        rows = []
        for row in range(self.items_table.rowCount()):
            product_name = self.safe_item_text(row, 2)
            quantity = self.safe_float_from_cell(row, 9, 0.0)
            if not product_name or quantity <= 0:
                continue
            rows.append({'sl_no': len(rows) + 1, 'product_name': product_name, 'name': product_name, 'hsn': self.safe_item_text(row, 3), 'cgst': self.safe_float_from_cell(row, 4, 0.0), 'sgst': self.safe_float_from_cell(row, 5, 0.0), 'igst': self.safe_float_from_cell(row, 6, 0.0), 'cess': self.safe_float_from_cell(row, 7, 0.0), 'rate': self.safe_float_from_cell(row, 8, 0.0), 'quantity': quantity, 'gross_value': self.safe_float_from_cell(row, 10, 0.0), 'discount': self.safe_float_from_cell(row, 11, 0.0), 'net_value': self.safe_float_from_cell(row, 12, 0.0), 'tax_amount': self.safe_float_from_cell(row, 13, 0.0), 'grand_total': self.safe_float_from_cell(row, 14, 0.0)})
        return rows

    def _build_purchase_a4_totals_data(self, cart_data):
        """Return A4 header and totals for the current purchase bill."""
        return {'customer_name': strip_party_display_code(self.creditor_name_input.text().strip()) or 'Cash Supplier', 'customer_address': self.address_input.text().strip(), 'customer_gstin': self.gstin_input.text().strip(), 'invoice_number': self.purchase_no_input.text().strip(), 'invoice_date': qdate_to_display(self.date_input.date()), 'voucher_no': self.purchase_no_input.text().strip(), 'voucher_type': self.purchase_type_combo.currentText().strip(), 'reference': self.supplier_invoice_input.text().strip(), 'sub_total': sum((float(item.get('gross_value') or 0.0) for item in cart_data)), 'discount_total': sum((float(item.get('discount') or 0.0) for item in cart_data)), 'tax_total': sum((float(item.get('tax_amount') or 0.0) for item in cart_data)), 'round_off': self._safe_float(self.round_off_input.text(), 0.0), 'grand_total': self._safe_float(self.grand_total_input.text(), 0.0), 'amount_received': self._safe_float(self.amt_paid_input.text(), 0.0), 'narration': self.narration_input.text().strip()}

    def _collect_barcode_rows(self):
        """Build barcode-label rows from the current purchase bill lines.

        Extracts product details, prices, the line sequence index, print
        quantities (matching the purchased amount) and the supplier shortcode
        (creditor party code) so the labels are ready to print without retyping.
        """
        rows = []
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return rows
        from .barcode_manager import normalized_supplier_code
        header_supplier_code = self._current_supplier_code()
        for r in range(self.items_table.rowCount()):
            try:
                product_id = None
                if r < len(self.purchase_items):
                    product_id = self.purchase_items[r].get('product_id')
                if not product_id:
                    continue
                try:
                    product = self.db.get_product_by_id(active_company['id'], product_id) or {}
                except Exception:
                    product = {}
                purchase_price = self.safe_float_from_cell(r, 8, 0.0)
                if purchase_price <= 0:
                    purchase_price = float(product.get('purchase_rate', 0) or 0)
                mrp = self.safe_float_from_cell(r, 1, 0.0)
                if mrp <= 0:
                    mrp = float(product.get('mrp', 0) or product.get('sale_price', 0) or 0)
                qty = int(self.safe_float_from_cell(r, 9, 0.0))
                if qty <= 0:
                    qty = 1
                name = self.safe_item_text(r, 2, '') or str(product.get('name', '') or '')
                row_supplier_code = normalized_supplier_code(header_supplier_code, self._purchase_row_supplier_code(r), product)
                rows.append({'barcode': str(product.get('barcode', '') or ''), 'product_name': name, 'supplier_code': row_supplier_code, 'purchase_price': purchase_price, 'mrp': mrp, 'item_index': r + 1, 'print_qty': qty})
            except Exception:
                continue
        return rows

    def open_barcode_printing_page(self):
        """Launch the Barcode Printing Manager pre-filled with this bill's items."""
        try:
            from .barcode_manager import BarcodeManagerWindow
        except Exception as exc:
            QMessageBox.warning(self, 'Get Barcode', f'Barcode module unavailable: {exc}')
            return
        rows = self._collect_barcode_rows()
        self._barcode_window = BarcodeManagerWindow(parent=self, db=self.db, rows=rows)
        self._barcode_window.show()
        self._barcode_window.raise_()
        self._barcode_window.activateWindow()

    def on_footer_discount_changed(self, text):
        """Handle footer discount/round-off change.

        Refreshes the small percent sub-label next to the Discount box so the
        operator can see the effective percentage of the pre-discount base, then
        recalculates the bill totals. Base = sub_total - row_discount + tax + freight.
        """
        if hasattr(self, 'discount_percent_label') and hasattr(self, 'discount_total_input'):
            amount = self._safe_float(self.discount_total_input.text(), 0.0)
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
        self.calculate_totals()

    def _discount_base_value(self):
        """Return the pre-discount base used for footer discount percentage math."""
        sub_total = self._safe_float(self.sub_total_input.text(), 0.0) if hasattr(self, 'sub_total_input') else 0.0
        tax_total = self._safe_float(self.tax_total_input.text(), 0.0) if hasattr(self, 'tax_total_input') else 0.0
        row_discount_total = float(getattr(self, '_row_discount_total', 0.0) or 0.0)
        freight = self._safe_float(self.freight_input.text(), 0.0) if hasattr(self, 'freight_input') else 0.0
        return sub_total - row_discount_total + tax_total + freight

    def apply_discount_percent_mode(self):
        """Interpret the current footer Discount value as a percentage of the base.

        Triggered by the Down Arrow inside the Discount box. Converts the entered
        number into an actual cash discount amount, clamps the percentage to 100,
        and shows the percent in the small sub-label. Mirrors the Sales Entry page.
        """
        try:
            if not hasattr(self, 'discount_total_input'):
                return
            pct = self._safe_float(self.discount_total_input.text(), 0.0)
            if pct <= 0:
                return
            base = self._discount_base_value()
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
            self.calculate_totals()
        except Exception as exc:
            print(f'Failed to apply footer discount percent mode: {exc}')

    def on_purchase_expense_changed(self, text):
        """Handle purchase expense change - recalculate totals."""
        self.calculate_totals()

    def on_round_off_toggled(self, _state):
        """Recalculate totals when the Round Off control is toggled.

        When checked, the footer engine snaps the Grand Total to the nearest whole
        integer; when unchecked, exact decimal values are preserved.
        """
        self.calculate_totals()

    def on_amt_paid_edited(self, *args):
        """Handle amount paid field edit. Accepts *args for signal compatibility."""
        if self._updating_amt_paid_programmatically:
            return
        self._amt_paid_user_edited = True
        self.update_footer_payment_fields(write_amt_recvd=False)

    def update_footer_payment_fields(self, write_amt_recvd=True):
        """Update payment-related footer fields based on purchase type using PartyBalanceEngine.

        Rules:
          - Opening Balance: Only from party master (parties.opening_balance), never changes while browsing.
          - Previous Balance: Balance before current voucher (excludes current and future bills).
          - Cash: Amount Paid auto = Grand Total (always forced).
          - Credit (default state): Amount Paid = 0.00 until user manually edits it.
          - Credit (user-edited): preserve user's Amount Paid value.
          - Closing Payable = Previous Balance + Purchase Net Amount - Amount Paid.
        """
        grand_total = self._safe_float(self.grand_total_input.text())
        purchase_type = self.purchase_type_combo.currentText()
        previous_balance = self.get_previous_creditor_balance()
        if purchase_type == 'Cash':
            amt_paid = grand_total
        elif getattr(self, '_amt_paid_user_edited', False):
            amt_paid = self._safe_float(self.amt_paid_input.text())
        else:
            amt_paid = 0.0
        amt_paid_for_calc = amt_paid if amt_paid <= grand_total else grand_total
        closing_balance = self.balance_engine.calculate_closing_balance(previous_balance, grand_total, amt_paid_for_calc, 'purchase')
        if write_amt_recvd:
            if purchase_type == 'Cash':
                if not getattr(self, '_amt_paid_user_edited', False):
                    self._updating_amt_paid_programmatically = True
                    self.amt_paid_input.setText(f'{amt_paid_for_calc:.2f}')
                    self._updating_amt_paid_programmatically = False
            elif purchase_type == 'Credit':
                if not getattr(self, '_amt_paid_user_edited', False):
                    self._updating_amt_paid_programmatically = True
                    self.amt_paid_input.setText('0.00')
                    self._updating_amt_paid_programmatically = False
        if hasattr(self, 'balance_display'):
            self.balance_display.setText(f'{closing_balance:.2f}')

    def get_previous_creditor_balance(self):
        """Return the Previous Balance (balance before current voucher) of the selected creditor.

        Uses PartyBalanceEngine to calculate:
        Previous Balance = party opening_balance + unpaid previous purchases - previous payments/returns

        Excludes current bill when editing/viewing old bills via voucher_id.
        Excludes future bills (after current voucher date/id).

        Returns 0.00 when no creditor found / blank / error.
        """
        try:
            if not hasattr(self, 'creditor_name_input'):
                return 0.0
            name = self.creditor_name_input.text().strip()
            if not name:
                return 0.0
            if not getattr(self, 'creditors_data', None):
                return 0.0
            for c in self.creditors_data:
                if party_matches_text(c, name):
                    party_id = c.get('id')
                    if party_id:
                        active = active_company_manager.get_active_company()
                        if active:
                            voucher_id = self.current_purchase_id if hasattr(self, 'current_purchase_id') else None
                            voucher_date = None
                            if voucher_id and hasattr(self, 'bill_date_input'):
                                voucher_date = qdate_to_db(self.bill_date_input.date())
                            balance_result = self.balance_engine.get_party_balance_before_voucher(active['id'], party_id, 'purchase', voucher_id=voucher_id, voucher_date=voucher_date)
                            return balance_result.get('previous_balance', 0.0)
                    return self._safe_float(c.get('opening_balance'), 0.0)
            return 0.0
        except Exception:
            return 0.0

    def apply_purchase_payment_mode(self):
        """Apply payment mode based on purchase type (Cash/Credit)."""
        grand_total = self._safe_float(self.grand_total_input.text())
        purchase_type = self.purchase_type_combo.currentText()
        if purchase_type == 'Cash':
            self._updating_amt_paid_programmatically = True
            self.amt_paid_input.setText(f'{grand_total:.2f}')
            self._updating_amt_paid_programmatically = False
            self.balance_display.setText('0.00')
        elif purchase_type == 'Credit':
            if not getattr(self, '_amt_paid_user_edited', False):
                self._updating_amt_paid_programmatically = True
                self.amt_paid_input.setText('0.00')
                self._updating_amt_paid_programmatically = False
            amt_paid = self._safe_float(self.amt_paid_input.text())
            balance = grand_total - amt_paid
            self.balance_display.setText(f'{balance:.2f}')

    def _safe_float(self, text, default=0.0):
        """Parse text to float safely."""
        try:
            return float(str(text).strip().replace(',', '').replace('₹', ''))
        except (ValueError, TypeError):
            return default

    def open_creditor_page(self):
        """Open Debtor/Creditor module for adding new creditor."""
        self._creditor_refresh_pending = True
        self._last_creditor_refresh_time = 0
        try:
            from PySide6.QtWidgets import QApplication
            main_window = self.window()
            if main_window and hasattr(main_window, 'show_debitor_creditor'):
                main_window.show_debitor_creditor()
                return
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'show_debitor_creditor'):
                    widget.show_debitor_creditor()
                    widget.raise_()
                    widget.activateWindow()
                    return
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'stack_widget') and hasattr(widget, 'debitor_creditor_widget'):
                    if hasattr(widget.debitor_creditor_widget, 'load_parties'):
                        widget.debitor_creditor_widget.load_parties()
                    widget.stack_widget.setCurrentWidget(widget.debitor_creditor_widget)
                    widget.raise_()
                    widget.activateWindow()
                    return
            QMessageBox.warning(self, 'Navigation Error', 'Debtor/Creditor page is not available from this window.')
        except Exception as e:
            QMessageBox.warning(self, 'Navigation Error', f'Could not open Debtor/Creditor page: {e}')

    def save(self):
        """Save purchase bill."""
        if getattr(self, '_is_loading', False):
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        purchase_no = self.purchase_no_input.text()
        date = qdate_to_db(self.date_input.date())
        purchase_type = self.purchase_type_combo.currentText()
        series = self.series_input.text()
        nature = self.nature_combo.currentText()
        creditor_name = self.creditor_name_input.text()
        address = self.address_input.text()
        mobile = self.mobile_input.text()
        gstin = self.gstin_input.text()
        state = self.state_combo.currentText()
        supplier_invoice_no = self.supplier_invoice_input.text()
        due_date = qdate_to_db(self.due_date_input.date())
        narration = self.narration_input.text()
        is_credit_purchase = 'credit' in str(purchase_type or '').strip().casefold()
        creditor_name = strip_party_display_code(creditor_name.strip())
        if is_credit_purchase and (not creditor_name):
            QMessageBox.warning(self, 'Validation Error', 'Please select a valid supplier/creditor.')
            self.creditor_name_input.setFocus()
            return
        if not purchase_no:
            QMessageBox.warning(self, 'Validation Error', 'Please enter purchase number.')
            return
        if not self.creditors_data:
            self.load_creditors()
        creditor = None
        if creditor_name:
            for c in self.creditors_data:
                if party_matches_text(c, creditor_name):
                    creditor = c
                    break
        party_id = None
        if creditor:
            party_id = creditor.get('id')
        elif creditor_name:
            ph = self.db._get_placeholder()
            result = self.db.execute_query(f'SELECT id, name FROM parties WHERE company_id = {ph} AND (TRIM(name) = {ph} OR TRIM(party_code) = {ph})', (active_company['id'], creditor_name, creditor_name.upper()[:7]))
            if result:
                party_id = result[0]['id']
                creditor_name = result[0]['name']
                self.load_creditors()
            else:
                new_creditor_data = {'name': creditor_name, 'party_type': 'Creditor', 'opening_balance': 0.0, 'mobile_number': mobile, 'address': address, 'gstin': gstin, 'credit_limit': 0.0, 'contact_person': '', 'notes': ''}
                try:
                    party_id = self.db.insert_party(active_company['id'], new_creditor_data)
                except Exception as e:
                    error_msg = str(e)
                    print(f'[DEBUG] insert_party failed: {error_msg}')
                    if 'UNIQUE constraint' in error_msg:
                        print(f'[DEBUG] Retrying to find creditor: {creditor_name}')
                        result = self.db.execute_query(f'SELECT id, name FROM parties WHERE TRIM(name) = {ph} AND company_id = {ph}', (creditor_name, active_company['id']))
                        if result:
                            party_id = result[0]['id']
                            creditor_name = result[0]['name']
                            print(f'[DEBUG] Found existing creditor: id={party_id}, name={creditor_name}')
                            self.load_creditors()
                        else:
                            result = self.db.execute_query(f'SELECT id, name FROM parties WHERE name = {ph} AND company_id = {ph}', (creditor_name, active_company['id']))
                            if result:
                                party_id = result[0]['id']
                                creditor_name = result[0]['name']
                                print(f'[DEBUG] Found existing creditor (exact match): id={party_id}, name={creditor_name}')
                                self.load_creditors()
                            else:
                                QMessageBox.warning(self, 'Error', f'Failed to create or find creditor: {error_msg}')
                                return
                    else:
                        QMessageBox.warning(self, 'Error', f'Failed to create creditor: {error_msg}')
                        return
                if not party_id:
                    QMessageBox.warning(self, 'Error', 'Failed to create creditor.')
                    return
        for row in range(self.items_table.rowCount()):
            product_name = self.safe_item_text(row, 2)
            if product_name and product_name.strip() and self._row_has_committed_product(row):
                self.recalculate_row(row, source_column=None)
        purchase_items = []
        for row in range(self.items_table.rowCount()):
            product_name = self.safe_item_text(row, 2)
            if product_name and self._row_has_committed_product(row):
                qty = self.safe_float_from_cell(row, 9)
                if qty > 0:
                    row_meta = self.purchase_items[row] if row < len(self.purchase_items) else {}
                    product_item = self.items_table.item(row, 2)
                    product_id = product_item.data(Qt.UserRole) if product_item else None
                    if product_id is None:
                        product_id = row_meta.get('product_id')
                    if not product_id and product_name:
                        active_company = active_company_manager.get_active_company()
                        if active_company:
                            product = self.db.get_product_by_exact_name(active_company['id'], product_name)
                            if product:
                                product_id = product.get('id')
                                if product_item:
                                    product_item.setData(Qt.UserRole, product_id)
                    if not product_id:
                        continue
                    cgst_amount = row_meta.get('cgst_amount', 0.0)
                    sgst_amount = row_meta.get('sgst_amount', 0.0)
                    igst_amount = row_meta.get('igst_amount', 0.0)
                    cess_amount = row_meta.get('cess_amount', 0.0)
                    purchase_items.append({'sl_no': row + 1, 'product_id': product_id, 'hsn': self.safe_item_text(row, 3), 'tax_percent': self.safe_float_from_cell(row, 4) + self.safe_float_from_cell(row, 5) + self.safe_float_from_cell(row, 6) + self.safe_float_from_cell(row, 7), 'cgst': self.safe_float_from_cell(row, 4), 'sgst': self.safe_float_from_cell(row, 5), 'igst': self.safe_float_from_cell(row, 6), 'cess': self.safe_float_from_cell(row, 7), 'cgst_amount': cgst_amount, 'sgst_amount': sgst_amount, 'igst_amount': igst_amount, 'cess_amount': cess_amount, 'unit': '', 'rate': self.safe_float_from_cell(row, 8), 'quantity': qty, 'gross_value': self.safe_float_from_cell(row, 10), 'discount': round(self.safe_float_from_cell(row, 10) - self.safe_float_from_cell(row, 12), 2), 'net_value': self.safe_float_from_cell(row, 12), 'tax_amount': self.safe_float_from_cell(row, 13), 'grand_total': self.safe_float_from_cell(row, 14)})
        if not purchase_items:
            QMessageBox.warning(self, 'Validation Error', 'Please add at least one item with a product and quantity.')
            return
        if self.db.purchase_number_exists(active_company['id'], purchase_no, self.current_purchase_id):
            QMessageBox.warning(self, 'Validation Error', f"Purchase number '{purchase_no}' already exists.")
            return
        sub_total = 0.0
        discount_total = 0.0
        tax_total = 0.0
        for item in purchase_items:
            sub_total += item.get('gross_value', 0.0)
            discount_total += item.get('discount', 0.0)
            tax_total += item.get('tax_amount', 0.0)
        purchase_data = {'purchase_number': purchase_no, 'purchase_date': date, 'party_id': party_id, 'purchase_type': purchase_type, 'bill_series': series, 'nature': nature, 'due_date': due_date, 'address': address, 'gstin': gstin, 'state': state, 'supplier_invoice_no': supplier_invoice_no, 'narration': narration, 'sub_total': sub_total, 'discount_total': discount_total, 'tax_total': tax_total, 'round_off': self._safe_float(self.round_off_input.text()), 'purchase_expense': self._safe_float(self.purchase_expense_input.text()) if hasattr(self, 'purchase_expense_input') else 0.0, 'freight': self._safe_float(self.freight_input.text()) if hasattr(self, 'freight_input') else 0.0, 'grand_total': self._safe_float(self.grand_total_input.text()), 'amount_paid': self._safe_float(self.amt_paid_input.text())}
        purchase_logic = self._get_purchase_logic()
        try:
            result = purchase_logic.save_purchase(active_company['id'], purchase_data, purchase_items, self.current_purchase_id)
        except sqlite3.Error as e:
            QMessageBox.critical(self, 'Database Error', f'Failed to save purchase: {str(e)}')
            return
        if result['success']:
            po_id_to_close = getattr(self, 'active_loaded_po_id', None)
            if po_id_to_close:
                try:
                    ph = self.db._get_placeholder()
                    self.db.execute_update(f"\n                        UPDATE purchase_orders\n                        SET status = 'Completed'\n                        WHERE id = {ph} AND company_id = {ph}\n                        ", (po_id_to_close, active_company['id']))
                except Exception as exc:
                    QMessageBox.warning(self, 'PO Status', f'Bill saved, but PO could not be marked completed: {exc}')
                self.active_loaded_po_id = None
            QMessageBox.information(self, 'Success', result['message'])
            self._purchase_nav_ids = self.db.get_purchase_nav_ids(active_company['id'])
            if not self.current_purchase_id and result.get('data', {}).get('purchase_id'):
                self.current_purchase_id = result['data']['purchase_id']
            self.clear_form()
        else:
            QMessageBox.warning(self, 'Error', result['message'])

    def _get_product_for_row(self, row):
        """Return product data for a purchase row, with stored source tax fallback."""
        if row < 0 or row >= len(self.purchase_items):
            return {}
        item_data = self.purchase_items[row]
        product_id = item_data.get('product_id')
        product = None
        if product_id:
            product = self.products_dict.get(product_id)
            if not product:
                for p in getattr(self, 'products_data', []):
                    if p.get('id') == product_id:
                        product = p
                        break
        if not product:
            product = {'id': product_id, 'name': item_data.get('name', self.safe_item_text(row, 1)), 'hsn': item_data.get('hsn', item_data.get('hsn_code', self.safe_item_text(row, 2))), 'purchase_rate': item_data.get('rate', self.safe_float_from_cell(row, 7)), 'cgst': item_data.get('source_cgst', item_data.get('cgst', 0)), 'sgst': item_data.get('source_sgst', item_data.get('sgst', 0)), 'igst': item_data.get('source_igst', item_data.get('igst', 0)), 'cess': item_data.get('source_cess', item_data.get('cess', 0))}
        return product

    def _apply_nature_tax_to_row(self, row, product):
        """Apply Indian GST purchase tax rule to a row.

        Product master may store CGST, SGST, IGST and CESS together.
        Purchase Entry must choose the active taxes by Nature:
        - Local: CGST + SGST + CESS, IGST = 0
        - Inter-state: IGST + CESS, CGST = SGST = 0
        """
        if row < 0 or row >= self.items_table.rowCount():
            return
        if row >= len(self.purchase_items):
            return
        if not product:
            product = self._get_product_for_row(row)
        if not product:
            return

        def to_float(value):
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0
        source_cgst = to_float(product.get('cgst', self.purchase_items[row].get('source_cgst', 0)))
        source_sgst = to_float(product.get('sgst', self.purchase_items[row].get('source_sgst', 0)))
        source_igst = to_float(product.get('igst', self.purchase_items[row].get('source_igst', 0)))
        source_cess = to_float(product.get('cess', self.purchase_items[row].get('source_cess', 0)))
        is_inter = 'inter' in self.nature_combo.currentText().strip().lower()
        if is_inter:
            cgst = 0.0
            sgst = 0.0
            igst = source_igst
        else:
            cgst = source_cgst
            sgst = source_sgst
            igst = 0.0
        cess = source_cess
        was_blocked = self.items_table.blockSignals(True)
        try:
            for col, value in ((4, cgst), (5, sgst), (6, igst), (7, cess)):
                cell = self.items_table.item(row, col)
                if cell:
                    cell.setText(f'{value:.2f}')
        finally:
            self.items_table.blockSignals(was_blocked)
        self.purchase_items[row].update({'source_cgst': source_cgst, 'source_sgst': source_sgst, 'source_igst': source_igst, 'source_cess': source_cess, 'cgst': cgst, 'sgst': sgst, 'igst': igst, 'cess': cess, 'tax_percent': igst + cess if is_inter else cgst + sgst + cess})

    def update_discount_status_label(self, row):
        """Push the active row's equivalent discount percentage to the top bar.

        Works regardless of the row's Disc mode (flat or percentage) by deriving
        the effective percentage from the resolved Gross and Net cells.
        """
        if not hasattr(self, 'discount_status_display'):
            return
        if row is None or row < 0:
            return
        gross = self.safe_float_from_cell(row, 10, 0.0)
        net = self.safe_float_from_cell(row, 12, 0.0)
        disc_amount = gross - net
        if disc_amount < 0:
            disc_amount = 0.0
        pct = disc_amount / gross * 100.0 if gross > 0 else 0.0
        self.discount_status_display.setText(f'{pct:.2f}%')

    def _update_purchase_row_status_display(self, row):
        """Update Code and Stock displays for the given purchase row."""
        if row < 0 or row >= len(self.purchase_items):
            return
        self.update_discount_status_label(row)
        product_id = self.purchase_items[row].get('product_id')
        product = None
        if product_id:
            product = self.products_dict.get(product_id)
            if not product:
                for p in getattr(self, 'products_data', []):
                    if p.get('id') == product_id:
                        product = p
                        break
        if product:
            if hasattr(self, 'product_input'):
                self.product_input.blockSignals(True)
                self.product_input.setText(product.get('name', ''))
                self.product_input.blockSignals(False)
            if hasattr(self, 'code_display'):
                self.code_display.setText(str(product.get('barcode', '') or ''))
            if hasattr(self, 'stock_display'):
                try:
                    active_company = active_company_manager.get_active_company()
                    if active_company and product_id:
                        stock_qty = self.stock_logic.get_current_stock(active_company['id'], product_id)
                    else:
                        stock_qty = float(product.get('quantity', 0) or 0)
                except (TypeError, ValueError, Exception):
                    stock_qty = 0.0
                self.stock_display.setText(str(f'{stock_qty:.3f}'))

    def eventFilter(self, obj, event):
        """Unified event filter for Purchase Entry.

        - Editable table cells open editor with select-all on one click.
        - SL column click marks the row for Remove Item only.
        - No row is deleted from a mouse click.
        - Locked party fields stay protected.
        - Enter key moves forward through editable cells.
        - Esc key moves backward.
        """
        if isinstance(obj, QLineEdit) and event.type() == QEvent.FocusIn:
            if not obj.isReadOnly():
                QTimer.singleShot(0, obj.selectAll)
        if event.type() == QEvent.KeyPress and hasattr(self, 'creditor_name_input') and (obj == self.creditor_name_input) and (event.key() == Qt.Key_Tab):
            QTimer.singleShot(0, self.show_creditor_search_popup)
            return True
        if event.type() == QEvent.KeyPress and hasattr(self, 'product_input') and (obj == self.product_input):
            if event.key() == Qt.Key_Escape:
                self.product_input.clear()
                if hasattr(self, 'barcode_input'):
                    self.barcode_input.setFocus()
                return True
            if event.key() == Qt.Key_Down:
                self.show_product_popup()
                return True
        if hasattr(self, 'discount_total_input') and obj == self.discount_total_input and (event.type() == QEvent.KeyPress) and (event.key() == Qt.Key_Down):
            self.apply_discount_percent_mode()
            return True
        if obj == self.items_table.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                item = self.items_table.itemAt(event.pos())
                if not item:
                    return False
                clicked_row = item.row()
                clicked_column = item.column()
                previous_row = self.items_table.currentRow()
                previous_column = self.items_table.currentColumn()
                if previous_column == 2 and previous_row >= 0 and (previous_row != clicked_row or clicked_column != 2):
                    self._clear_uncommitted_product_cell(previous_row)
                if clicked_column == 0:
                    self.manually_selected_row = clicked_row
                    self.items_table.clearSelection()
                    self.items_table.setCurrentCell(clicked_row, clicked_column)
                    self._update_purchase_row_status_display(clicked_row)
                    self.items_table.viewport().update()
                    return True
                self.manually_selected_row = -1
                self.items_table.clearSelection()
                self._update_purchase_row_status_display(clicked_row)
                self.items_table.viewport().update()
                self.focus_table_cell_editor(clicked_row, clicked_column)
                return True
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_F2:
            current_row = self.items_table.currentRow()
            current_col = self.items_table.currentColumn()
            if current_col == 8:
                self.on_f2_in_qty_field(current_row)
                return True
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Delete:
            if obj == self.items_table or obj == self.items_table.viewport():
                row = getattr(self, 'manually_selected_row', -1)
                if row < 0:
                    row = self.items_table.currentRow()
                if 0 <= row < self.items_table.rowCount():
                    self.delete_row(row)
                    self.manually_selected_row = -1
                    self.items_table.clearSelection()
                    self.items_table.viewport().update()
                    return True
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Return:
            if obj == self.items_table or obj == self.items_table.viewport():
                current_row = self.items_table.currentRow()
                current_col = self.items_table.currentColumn()
                if current_col == 2:
                    product_text = self.safe_item_text(current_row, 2)
                    if self.handle_product_cell_enter(current_row, product_text):
                        return True
                editable_columns = [4, 5, 6, 7, 8, 9, 10, 11]
                if current_col in editable_columns:
                    next_col_index = editable_columns.index(current_col) + 1
                    if next_col_index < len(editable_columns):
                        next_col = editable_columns[next_col_index]
                        self.focus_table_cell_editor(current_row, next_col)
                        return True
                    else:
                        next_row = current_row + 1
                        if next_row < self.items_table.rowCount():
                            self.focus_table_cell_editor(next_row, editable_columns[0])
                            return True
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            if obj == self.items_table or obj == self.items_table.viewport():
                current_row = self.items_table.currentRow()
                current_col = self.items_table.currentColumn()
                editable_columns = [4, 5, 6, 7, 8, 9, 10, 11]
                if current_col in editable_columns:
                    prev_col_index = editable_columns.index(current_col) - 1
                    if prev_col_index >= 0:
                        prev_col = editable_columns[prev_col_index]
                        self.focus_table_cell_editor(current_row, prev_col)
                        return True
                    else:
                        prev_row = current_row - 1
                        if prev_row >= 0:
                            self.focus_table_cell_editor(prev_row, editable_columns[-1])
                            return True
        if self._party_fields_locked and event.type() in (QEvent.KeyPress, QEvent.MouseButtonPress):
            if obj in (self.address_input, self.mobile_input, self.gstin_input, self.state_combo):
                QMessageBox.information(self, 'Field Locked', 'Update creditor using Edit Creditor.')
                return True
        return super().eventFilter(obj, event)

    def on_sl_no_clicked(self, row):
        """Mark a row from the SL column. Deletion is only from Remove Item button."""
        if row < 0 or row >= self.items_table.rowCount():
            return
        self.manually_selected_row = row
        self.items_table.clearSelection()
        self.items_table.setCurrentCell(row, 0)
        self._update_purchase_row_status_display(row)
        self.items_table.viewport().update()

    def on_f2_in_qty_field(self, row):
        """Handle F2 key press in Qty field to open Product Entry in edit mode."""
        product_id = None
        if row < len(self.purchase_items):
            product_id = self.purchase_items[row].get('product_id')
        if not product_id:
            QMessageBox.warning(self, 'No Product', 'No product selected in this row.')
            return
        self._product_entry_context = {'mode': 'edit', 'row': row, 'product_id': product_id}
        self.open_product_entry_edit_from_row(row, product_id)

    def closeEvent(self, event):
        """Handle window close event."""
        if not self._confirm_close_with_unsaved_guard(event):
            return
        self.window_closed.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        """Handle key press events."""
        super().keyPressEvent(event)