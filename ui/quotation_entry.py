"""
Quotation Entry widget for the Accounting Desktop Application.
Manages quotation creation with compact desktop layout.
Follows Sales Entry visual style but with zero-impact accounting (no ledger/stock posting).
"""
import json
import os
import re
import tempfile
import webbrowser
from urllib.parse import quote
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QDate, QEvent, QTimer, QCoreApplication, QObject
from PySide6.QtGui import QDoubleValidator
import config
from config import active_company_manager
from db import Database
from bizora_core.export_engine import ExportEngine
from bizora_core.print_settings_logic import get_print_settings
from bizora_core.stock_logic import StockLogic
from ui import theme
from ui.checkbox_style import create_checkbox
from .sales_entry_ui import SalesEntryUIMixin
from .sales_entry_delegate import SalesBillDelegate
from .sales_entry_helpers import ensure_row_items_initialized as _ensure_row_items_initialized, safe_float_from_cell as _safe_float_from_cell, safe_item_text as _safe_item_text
from ui.sales_entry_calculations import calculate_totals as _calculate_sales_totals, _write_totals_to_widgets, recalculate_row as _recalculate_sales_row
try:
    from utils.a4_print_engine import generate_a4_html
except ImportError:
    generate_a4_html = None
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.table_header_utils import apply_adjustable_table_columns
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
from ui.entry_voucher_mixin import EntryVoucherMixin

class QuotationEntryWidget(EntryVoucherMixin, UiMemoryMixin, SalesEntryUIMixin, QWidget):
    """Quotation Entry widget - zero-impact (no ledger/stock posting)."""
    voucher_type = "quotation"
    voucher_number_attr = "quotation_no_input"

    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self.stock_logic = StockLogic(self.db)
        self.company_id = None
        self.current_quotation_id = None
        self.quotation_items = []
        self.products_data = []
        self.products_dict = {}
        self.products_by_barcode = {}
        self.products_by_name_exact = {}
        self.parties_data = []
        self._quotation_nav_ids = []
        self._calculating = False
        self._loading_row = False
        self._manual_round_off = False
        self._row_discount_total = 0.0
        self._initial_load_done = False
        self._deferred_load_started = False
        self._is_initializing = True
        self._is_loading = False
        self.last_barcode_filled_row = -1
        self._barcode_scan_returns_focus = False
        self.sale_items = self.quotation_items
        self.manually_selected_row = -1
        self._product_entry_context = None
        self.setup_ui()
        self._ensure_product_id_column()
        self.clear_form()
        self._install_event_filters()
        self._wire_signals()
        self._init_entry_voucher_state()
        self._install_entry_unsaved_guard()
        self._install_voucher_number_lookup()
        self._is_initializing = False
        QTimer.singleShot(100, self._load_heavy_data)
        self._init_ui_memory()

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(theme.entry_page_background_style())
        if hasattr(self, "lbl_total_items"):
            colors = theme._theme_colors()
            self.lbl_total_items.setStyleSheet(
                f"QLabel {{ color: {colors['accent_label']}; font-size: 13px; "
                f"font-weight: bold; background: transparent; border: none; }}"
            )
        if hasattr(self, "salesman_combo"):
            self.salesman_combo.setStyleSheet(self.compact_input_style())
        if hasattr(self, "add_salesman_btn"):
            self.add_salesman_btn.setStyleSheet(self.modern_3d_icon_button_style())
        if hasattr(self, "narration_input"):
            self.narration_input.setStyleSheet(self.compact_input_style())
        for date_edit_name in ("date_input", "due_date_input"):
            date_edit = getattr(self, date_edit_name, None)
            if date_edit is not None and hasattr(self, "apply_calendar_style"):
                self.apply_calendar_style(date_edit)

    def load_company(self):
        active = active_company_manager.get_active_company()
        if active:
            self.company_id = active.get('id')
            self.company_state = active.get('state', '')

    def load_parties(self):
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            ph = self.db._get_placeholder()
            query = f"\n                SELECT id, name, party_type, gstin, state, address, mobile_number\n                FROM parties\n                WHERE company_id = {ph} AND party_type IN ('Debitor', 'Both')\n            "
            result = self.db.execute_query(query, (active_company['id'],))
            if result:
                self.parties_data = result
        except Exception as e:
            print(f'Failed to load parties: {e}')

    def load_products(self):
        """Load products into the quotation cache using explicit SQL columns."""
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            ph = self.db._get_placeholder()
            query = f'\n                SELECT id, name, barcode, hsn, sale_price, purchase_rate, wholesale_rate, mrp,\n                       cgst, sgst, igst, cess, unit, quantity, category, size, color\n                FROM products\n                WHERE company_id = {ph}\n            '
            result = self.db.execute_query(query, (active_company['id'],))
            self.products_data = result or []
            self.products_dict = {p['id']: p for p in self.products_data}
            self.products_by_barcode = {str(p.get('barcode') or '').strip(): p for p in self.products_data if str(p.get('barcode') or '').strip()}
            self.products_by_name_exact = {str(p.get('name') or '').strip().lower(): p for p in self.products_data}
        except Exception as e:
            print(f'Failed to load products: {e}')

    def get_next_quotation_no(self):
        """Generate next quotation number for the company."""
        try:
            if not self.company_id:
                return '001'
            return self.db.get_next_voucher_number(self.company_id, 'quotation')
        except Exception as e:
            print(f'Failed to get next quotation no: {e}')
            return '001'

    def build_page_header_strip(self):
        """Build the Quotation Entry header strip with distinct identity styling."""
        frame = QFrame()
        frame.setStyleSheet(theme.entry_header_strip_style())
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        title_label = QLabel('QUOTATION ENTRY')
        title_label.setStyleSheet(theme.entry_page_title_label_style())
        layout.addWidget(title_label)
        layout.addStretch()
        return frame

    def build_party_information_matrix(self):
        """Build the Sales-style party matrix without the Sales Return button."""
        frame = super().build_party_information_matrix()
        if hasattr(self, 'return_btn'):
            parent = self.return_btn.parentWidget()
            if parent and parent.layout():
                parent.layout().removeWidget(self.return_btn)
            self.return_btn.setParent(None)
            self.return_btn.deleteLater()
            delattr(self, 'return_btn')
        return frame

    def build_lower_control_panel(self):
        """Build the Sales Entry footer structure with Quotation grand-total styling."""
        frame = QFrame()
        frame.setStyleSheet(self.footer_panel_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)
        grand_style = theme.entry_grand_total_style()
        action_frame = QFrame()
        action_frame.setStyleSheet(self.action_zone_style())
        action_layout = QVBoxLayout(action_frame)
        action_layout.setSpacing(5)
        action_layout.setContentsMargins(6, 6, 6, 6)
        self.ok_btn = QPushButton('Save')
        self.btn_save = self.ok_btn
        self.save_btn = self.ok_btn
        self.ok_btn.setStyleSheet(self.save_button_style())
        self._make_non_default_button(self.ok_btn)
        self.ok_btn.clicked.connect(lambda: self.save(is_manual=True))
        self.ok_btn.setToolTip('Save quotation without ledger or stock posting.')
        action_layout.addWidget(self.ok_btn)
        for text, slot, style in (('Print', self.print_invoice, self.compact_button_style()), ('WhatsApp Quote', self.send_whatsapp_quote, '\n            QPushButton {\n                background-color: #25D366;\n                color: #ffffff;\n                border: none;\n                border-radius: 3px;\n                font-size: 10px;\n                font-weight: bold;\n                padding: 4px 6px;\n            }\n            QPushButton:hover { background-color: #1ebe57; }\n            QPushButton:pressed { background-color: #128C7E; }\n        '), ('SMS Quote', self.send_sms_quote, self.compact_button_style()), ('Convert to Sale', self.convert_to_sale_action, self.compact_button_style()), ('Reset All', self.clear_form, self.compact_button_style()), ('Remove Item', self.confirm_remove_item, self.danger_button_style()), ('Remove Quote', self.confirm_remove_bill, self.danger_button_style())):
            button = QPushButton(text)
            button.setStyleSheet(style)
            self._make_non_default_button(button)
            button.clicked.connect(slot)
            action_layout.addWidget(button)
            if text == 'WhatsApp Quote':
                self.btn_whatsapp = button
            elif text == 'SMS Quote':
                self.btn_sms = button
            elif text == 'Convert to Sale':
                self.convert_to_sale_btn = button
        action_layout.addStretch()
        action_frame.setFixedWidth(132)
        adj_frame = QFrame()
        adj_frame.setStyleSheet(self.adjustment_zone_style())
        adj_layout = QVBoxLayout(adj_frame)
        adj_layout.setSpacing(2)
        adj_layout.setContentsMargins(6, 6, 6, 6)

        def add_line(parent_layout, label_text, widget):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(2)
            label = QLabel(label_text)
            label.setStyleSheet(self.footer_label_style())
            row_layout.addWidget(label)
            row_layout.addWidget(widget)
            parent_layout.addLayout(row_layout)
        self.grand_total_input = QLineEdit()
        self.grand_total_input.setStyleSheet(self.footer_input_readonly_style())
        self.grand_total_input.setReadOnly(True)
        self.grand_total_input.setFixedWidth(80)
        add_line(adj_layout, 'Grand Total', self.grand_total_input)
        self.payment_mode_combo = QComboBox()
        self.payment_mode_combo.addItems(['Cash', 'Online / UPI', 'Bank Transfer', 'Credit'])
        self.payment_mode_combo.setCurrentText('Credit')
        self.payment_mode_combo.setStyleSheet(self.footer_combo_style())
        self.payment_mode_combo.setFixedWidth(80)
        add_line(adj_layout, 'Payment Mode', self.payment_mode_combo)
        self.amount_receive_input = QLineEdit('0.00')
        self.amount_receive_input.setStyleSheet(self.footer_input_style())
        self.amount_receive_input.setFixedWidth(80)
        add_line(adj_layout, 'Amt Received', self.amount_receive_input)
        adj_layout.addStretch()
        adj_frame.setFixedWidth(175)
        layout.addWidget(adj_frame)
        adjb_frame = QFrame()
        adjb_frame.setStyleSheet(self.adjustment_zone_style())
        adjb_layout = QVBoxLayout(adjb_frame)
        adjb_layout.setSpacing(2)
        adjb_layout.setContentsMargins(6, 6, 6, 6)
        self.freight_input = QLineEdit('0.00')
        self.freight_input.setStyleSheet(self.footer_input_style())
        self.freight_input.setFixedWidth(80)
        add_line(adjb_layout, 'Freight', self.freight_input)
        round_container = QFrame()
        round_container.setStyleSheet(self.footer_input_style())
        round_container.setFixedWidth(80)
        round_layout = QHBoxLayout(round_container)
        round_layout.setSpacing(2)
        round_layout.setContentsMargins(2, 0, 2, 0)
        self.round_off_input = QLineEdit('0.00')
        self.round_off_input.setStyleSheet(theme.footer_transparent_input_style())
        self.round_off_input.setValidator(QDoubleValidator())
        self.round_off_input.textChanged.connect(self.calculate_totals)
        self.round_off_checkbox = create_checkbox(variant='compact')
        self.round_off_checkbox.setFixedSize(14, 14)
        self.round_off_checkbox.setChecked(True)
        self.round_off_checkbox.stateChanged.connect(lambda _state: self.calculate_totals())
        round_layout.addWidget(self.round_off_checkbox)
        round_layout.addWidget(self.round_off_input)
        add_line(adjb_layout, 'Round Off', round_container)
        discount_label_box = QVBoxLayout()
        discount_label_box.setSpacing(0)
        discount_label_box.setContentsMargins(0, 0, 0, 0)
        self.discount_label = QLabel('Discount')
        self.discount_label.setStyleSheet(self.footer_label_style())
        self.discount_label.setToolTip('Press Down-Arrow inside the Discount box to interpret the value as a percentage.')
        self.discount_percent_label = QLabel('')
        self.discount_percent_label.setStyleSheet(theme.discount_percent_micro_label_style())
        discount_label_box.addWidget(self.discount_label)
        discount_label_box.addWidget(self.discount_percent_label)
        discount_layout = QHBoxLayout()
        discount_layout.setSpacing(2)
        discount_layout.addLayout(discount_label_box)
        self.discount_total_input = QLineEdit('0.00')
        self.discount_total_input.setStyleSheet(self.footer_input_style())
        self.discount_total_input.setFixedWidth(80)
        discount_layout.addWidget(self.discount_total_input)
        adjb_layout.addLayout(discount_layout)
        self.net_amount_input = QLineEdit('0.00')
        self.net_amount_input.setStyleSheet(self.footer_input_readonly_style())
        self.net_amount_input.setReadOnly(True)
        self.net_amount_input.setFixedWidth(80)
        add_line(adjb_layout, 'Net Amount', self.net_amount_input)
        adjb_layout.addStretch()
        adjb_frame.setFixedWidth(175)
        layout.addWidget(adjb_frame)
        tax_frame = QFrame()
        tax_frame.setStyleSheet(self.tax_zone_style())
        tax_layout = QVBoxLayout(tax_frame)
        tax_layout.setSpacing(2)
        tax_layout.setContentsMargins(6, 6, 6, 6)
        self.net_value_display = QLabel('0.00')
        self.net_value_display.setStyleSheet(self.footer_value_style())
        add_line(tax_layout, 'Net Value', self.net_value_display)
        self.cgst_display = QLabel('0.00')
        self.cgst_display.setStyleSheet(self.footer_value_style())
        add_line(tax_layout, 'Add CGST', self.cgst_display)
        self.sgst_display = QLabel('0.00')
        self.sgst_display.setStyleSheet(self.footer_value_style())
        add_line(tax_layout, 'Add SGST', self.sgst_display)
        self.igst_display = QLabel('0.00')
        self.igst_display.setStyleSheet(self.footer_value_style())
        add_line(tax_layout, 'Add IGST', self.igst_display)
        self.tax_amount_display = QLabel('0.00')
        self.tax_amount_display.setStyleSheet(self.footer_value_style())
        add_line(tax_layout, 'Tax Amount', self.tax_amount_display)
        self.cess_display = QLabel('0.00')
        self.cess_display.setStyleSheet(self.footer_value_style())
        add_line(tax_layout, 'Cess', self.cess_display)
        tax_layout.addStretch()
        tax_frame.setFixedWidth(175)
        layout.addWidget(tax_frame)
        gt_zone = QFrame()
        gt_zone.setStyleSheet(self.adjustment_zone_style())
        gt_zone_layout = QVBoxLayout(gt_zone)
        gt_zone_layout.setSpacing(10)
        gt_zone_layout.setContentsMargins(10, 8, 10, 8)
        gt_heading = QLabel('₹ Grand Total')
        gt_heading.setStyleSheet(self.footer_label_style())
        gt_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gt_zone_layout.addWidget(gt_heading, 0)
        self.final_amount_display = QLabel('0.00')
        self.final_amount_display.setStyleSheet(grand_style)
        self.final_amount_display.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.final_amount_display.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        gt_zone_layout.addWidget(self.final_amount_display)
        gt_zone.setMinimumWidth(280)
        gt_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        gt_zone.setMinimumHeight(125)
        layout.addWidget(gt_zone, 2)
        self.return_adj_zone = QFrame()
        self.return_adj_zone.setStyleSheet(self.return_adjustment_zone_style())
        return_adj_layout = QVBoxLayout(self.return_adj_zone)
        return_adj_layout.setSpacing(2)
        return_adj_layout.setContentsMargins(8, 6, 8, 6)
        self.return_adj_label = QLabel('Return')
        self.return_adj_label.setStyleSheet(self.footer_label_style())
        self.return_adj_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.return_adj_amount = QLabel('0.00')
        self.return_adj_amount.setStyleSheet(self.return_amount_red_style())
        self.return_adj_amount.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.net_after_return_label = QLabel('Net After Return')
        self.net_after_return_label.setStyleSheet(self.footer_label_style())
        self.net_after_return_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.net_after_return_amount = QLabel('0.00')
        self.net_after_return_amount.setStyleSheet(self.net_after_return_orange_style())
        self.net_after_return_amount.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        for widget in (self.return_adj_label, self.return_adj_amount, self.net_after_return_label, self.net_after_return_amount):
            return_adj_layout.addWidget(widget)
        self.return_adj_zone.setFixedWidth(160)
        self.return_adj_zone.setMinimumHeight(160)
        self.return_adj_zone.setVisible(False)
        layout.addWidget(self.return_adj_zone)
        layout.addWidget(action_frame)
        self.sub_total_input = QLineEdit('0.00')
        self.sub_total_input.setVisible(False)
        self.tax_total_input = QLineEdit('0.00')
        self.tax_total_input.setVisible(False)
        self.adjustments_input = QLineEdit('0.00')
        self.adjustments_input.setVisible(False)
        if not hasattr(self, 'invoice_checkbox'):
            self.invoice_checkbox = create_checkbox()
            self.invoice_checkbox.setVisible(False)
        return frame

    def setup_ui(self):
        """Build a Sales Entry visual twin shell for Quotation Entry."""
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.addWidget(self.build_page_header_strip())
        layout.addWidget(self.build_invoice_command_strip())
        layout.addWidget(self.build_party_information_matrix())
        layout.addWidget(self.build_product_entry_strip())
        layout.addWidget(self.build_status_options_strip())
        layout.addWidget(self.build_items_table_zone(), 1)
        layout.addWidget(self.build_lower_control_panel())
        self.quotation_no_input = self.invoice_no_input
        self.valid_until_input = self.due_date_input
        self.discount_input = self.discount_total_input
        self.round_off_check = self.round_off_checkbox
        self.quotation_type_combo = QComboBox(self)
        self.quotation_type_combo.addItems(['Standard', 'Estimate', 'Proforma'])
        self.quotation_type_combo.setVisible(False)
        self.status_combo = QComboBox(self)
        self.status_combo.addItems(['Draft', 'Sent', 'Pending', 'Accepted', 'Rejected', 'Cancelled'])
        self.status_combo.setCurrentText('Pending')
        self.status_combo.setVisible(False)
        if hasattr(self, 'sales_type_combo'):
            self.sales_type_combo.setCurrentText('Credit')
        if hasattr(self, 'party_type_combo'):
            self.party_type_combo.setCurrentText('Debtor')
        if hasattr(self, 'ok_btn'):
            self.ok_btn.setText('Save')
            self.ok_btn.setToolTip('Save quotation without ledger or stock posting.')
        if hasattr(self, 'btn_whatsapp'):
            self.btn_whatsapp.setText('WhatsApp Quote')
        if hasattr(self, 'btn_sms'):
            self.btn_sms.setText('SMS Quote')
        if hasattr(self, 'return_adj_zone'):
            self.return_adj_zone.setVisible(False)
        if hasattr(self, 'check_stock_tick'):
            self.check_stock_tick.setVisible(False)
        try:
            from ui.financial_year_guard import apply_financial_year_guard_to_named_dates
            apply_financial_year_guard_to_named_dates(self, 'date_input', 'due_date_input')
        except Exception:
            pass
        self.items_table.setRowCount(0)
        self.setStyleSheet(theme.entry_page_background_style() + ' QWidget { font-weight: bold; }')
        return

    def _load_heavy_data(self):
        """Load company, debtor, and product caches after the empty shell is visible."""
        if self._initial_load_done or self._deferred_load_started:
            return
        self._deferred_load_started = True
        try:
            QCoreApplication.processEvents()
            self.load_company()
            QCoreApplication.processEvents()
            self.load_parties()
            QCoreApplication.processEvents()
            self.load_products()
            QCoreApplication.processEvents()
            self.quotation_no_input.setText(self.get_next_quotation_no())
            self._initial_load_done = True
            if hasattr(self, 'barcode_input'):
                self.barcode_input.setFocus()
        finally:
            self._deferred_load_started = False

    def _install_event_filters(self):
        """Install Sales Entry-style keyboard and select-all filters."""
        if hasattr(self, 'items_table'):
            self.items_table.installEventFilter(self)
            self.items_table.viewport().installEventFilter(self)
        for widget in self.findChildren(QLineEdit):
            widget.installEventFilter(self)
        for widget in self.findChildren(QComboBox):
            widget.installEventFilter(self)
            if widget.isEditable() and widget.lineEdit():
                widget.lineEdit().installEventFilter(self)

    def _install_select_all_on_click(self, line_edit):
        """Select all text on mouse click using deferred Qt focus timing."""
        original_mouse_press = line_edit.mousePressEvent

        def select_all_mouse_press(event):
            original_mouse_press(event)
            QTimer.singleShot(0, line_edit.selectAll)
        line_edit.mousePressEvent = select_all_mouse_press

    def _make_non_default_button(self, button):
        """Prevent footer buttons from being triggered by top-bar Enter navigation."""
        button.setAutoDefault(False)
        button.setDefault(False)

    def _wire_signals(self):
        """Connect Quotation Entry signals after the Sales-style shell is drawn."""
        for field in (getattr(self, 'freight_input', None), getattr(self, 'discount_total_input', None)):
            if field:
                field.textChanged.connect(self.on_footer_discount_changed if field == self.discount_total_input else self.calculate_totals)
                self._install_select_all_on_click(field)
        if hasattr(self, 'product_input'):
            self.product_input.returnPressed.connect(self.on_product_enter)
        if hasattr(self, 'divide_tax_tick'):
            self.divide_tax_tick.stateChanged.connect(lambda _state: self.calculate_totals())

    def _set_quotation_edit_mode(self, quotation_id):
        """Mark the form as editing an existing quotation and relabel save."""
        self.current_quotation_id = quotation_id
        for attr_name in ('btn_save', 'save_btn', 'ok_btn'):
            button = getattr(self, attr_name, None)
            if button:
                button.setText('Update')

    def _set_quotation_new_mode(self):
        """Mark the form as a fresh quotation and relabel save."""
        self.current_quotation_id = None
        for attr_name in ('btn_save', 'save_btn', 'ok_btn'):
            button = getattr(self, attr_name, None)
            if button:
                button.setText('Save')

    def next_bill(self):
        """Open a fresh quotation with the next sequential quotation number."""
        self.open_next_numbered_entry()

    def previous_bill(self):
        """Sales Entry UI alias for quotation previous navigation."""
        self.previous_quotation()

    def open_debitor_creditor_page(self):
        """Navigate to the existing Debtor/Creditor creation window."""
        try:
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
        except Exception as exc:
            QMessageBox.warning(self, 'Navigation Error', f'Could not open Debtor/Creditor page: {exc}')

    def _top_bar_navigation_widgets(self):
        """Return the strict Quotation top-bar keyboard navigation order."""
        state_widget = self.state_combo.lineEdit() if self.state_combo.isEditable() else self.state_combo
        return [self.customer_name_input, self.address_input, self.mobile_input, self.gstin_input, state_widget, self.narration_input, self.barcode_input, self.product_input]

    def _focus_top_bar_widget(self, widget):
        """Move focus inside the top-bar flow and select editable text."""
        widget.setFocus()
        if isinstance(widget, QLineEdit):
            widget.selectAll()
        elif isinstance(widget, QComboBox):
            line_edit = widget.lineEdit()
            if line_edit:
                line_edit.selectAll()

    def _handle_top_bar_navigation_key(self, obj, event):
        """Handle accepted Enter/Escape movement for the top-bar-only flow."""
        if event.key() not in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            return False
        nav_widgets = self._top_bar_navigation_widgets()
        state_combo = getattr(self, 'state_combo', None)
        state_line_edit = state_combo.lineEdit() if state_combo and state_combo.isEditable() else None
        target_obj = state_line_edit if obj == state_combo and state_line_edit else obj
        if target_obj not in nav_widgets:
            return False
        index = nav_widgets.index(target_obj)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if target_obj == getattr(self, 'barcode_input', None) and target_obj.text().strip():
                event.accept()
                self.on_barcode_enter()
                return True
            if index < len(nav_widgets) - 1:
                self._focus_top_bar_widget(nav_widgets[index + 1])
                event.accept()
                return True
            return False
        if index > 0:
            self._focus_top_bar_widget(nav_widgets[index - 1])
            event.accept()
            return True
        event.accept()
        return True

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
        """Return the active A4 quotation theme from saved print settings."""
        a4_theme_names = {'GST Standard', 'Modern Clean', 'Elegant Serif', 'Compact Wholesale', 'Bold Corporate', 'Bill of Supply', 'Color Block Header', 'Vibrant Accent', 'Modern Gradient'}
        settings = settings or {}
        metadata = self._print_settings_metadata(settings)
        for key in ('a4_theme', 'default_theme', 'theme'):
            theme_name = str(metadata.get(key) or settings.get(key) or '').strip()
            if theme_name in a4_theme_names:
                return theme_name
        return 'GST Standard'

    def print_invoice(self):
        """Print the current quotation through the shared A4 WebEngine engine."""
        if generate_a4_html is None:
            QMessageBox.critical(self, 'Print Quotation', 'A4 print engine is not available. Please verify a4_print_engine.py.')
            return
        active_company = active_company_manager.get_active_company()
        company_id = active_company.get('id') if active_company else None
        if not company_id:
            QMessageBox.warning(self, 'Print Quotation', 'Please open a company first.')
            return
        try:
            self.calculate_totals()
            cart_data = self._build_a4_quotation_cart_data()
            if not cart_data:
                QMessageBox.warning(self, 'Print Quotation', 'Please add at least one item with quantity before printing.')
                return
            settings = get_print_settings(self.db, company_id)
            default_mode = self._resolve_default_print_mode(settings)
            company_data = self._build_a4_quotation_company_data(active_company)
            totals_data = self._build_a4_quotation_totals_data(cart_data)
            html_string = generate_a4_html(company_data, cart_data, bill_type='TAX_INVOICE', totals_data=totals_data, settings=settings, theme_name=self._a4_theme_name(settings))
            if not html_string:
                QMessageBox.warning(self, 'Print Quotation', 'Could not generate A4 quotation HTML.')
                return
            self._last_a4_quotation_html = html_string
            printer_name = self._saved_printer_name(settings, 'normal_printer_name')
            paper_size = self._a4_paper_size_from_settings(settings)
            if default_mode == 'Thermal Receipt':
                print('[A4_PRINT] Quotation default mode is Thermal Receipt; using A4 route because no thermal quotation renderer is configured.')
            print(f"[A4_PREVIEW] Quotation print button preview default_print_mode='{default_mode}' printer='{printer_name or 'default'}' paper_size='{paper_size}' html_len={len(html_string)} preview_wrapper_present={self._a4_html_has_preview_wrapper(html_string)}")
            dialog = UniversalPreviewDialog(html_string, mode='A4', parent=self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Could not print quotation:\n{exc}')

    def export_pdf(self):
        """Open the current quotation in the universal preview dialog."""
        if not self.current_quotation_id:
            QMessageBox.warning(self, 'Export Quotation', 'Please save the quotation before preview.')
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'Export Quotation', 'No active company selected.')
            return
        if generate_a4_html is None:
            QMessageBox.critical(self, 'Export Quotation', 'A4 preview engine is not available. Please verify a4_print_engine.py.')
            return
        cart_data = self._build_a4_quotation_cart_data()
        if not cart_data:
            QMessageBox.warning(self, 'Export Quotation', 'Please add at least one item with quantity before previewing.')
            return
        try:
            settings = get_print_settings(self.db, active_company['id'])
            html_string = generate_a4_html(self._build_a4_quotation_company_data(active_company), cart_data, totals_data=self._build_a4_quotation_totals_data(cart_data), settings=settings, theme_name=self._a4_theme_name(settings))
            dialog = UniversalPreviewDialog(html_string, self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, 'Preview Failed', f'Could not preview quotation:\n{exc}')

    def _build_a4_quotation_company_data(self, active_company):
        """Return active company details for quotation A4 printing."""
        company_data = dict(active_company or {})
        company_data.setdefault('company_name', company_data.get('business_name', ''))
        company_data.setdefault('name', company_data.get('business_name', ''))
        company_data.setdefault('phone', company_data.get('phone_number', ''))
        return company_data

    def _build_a4_quotation_cart_data(self):
        """Collect live quotation grid rows in the A4 engine item format."""
        cart_data = []
        if not hasattr(self, 'items_table'):
            return cart_data
        for row in range(self.items_table.rowCount()):
            row_meta = self.sale_items[row] if row < len(self.sale_items) else {}
            row_meta = row_meta or {}
            product_name = self.safe_item_text(row, 1, '').strip()
            quantity = self.safe_float_from_cell(row, 8, 0.0)
            if not product_name or quantity <= 0.0:
                continue
            cgst_rate = self.safe_float_from_cell(row, 3, row_meta.get('cgst', 0.0))
            sgst_rate = self.safe_float_from_cell(row, 4, row_meta.get('sgst', 0.0))
            igst_rate = self.safe_float_from_cell(row, 5, row_meta.get('igst', 0.0))
            cess_rate = self.safe_float_from_cell(row, 6, row_meta.get('cess', 0.0))
            gst_rate = cgst_rate + sgst_rate + igst_rate
            cart_data.append({'sl_no': len(cart_data) + 1, 'product_id': row_meta.get('product_id') or self.safe_item_text(row, 14, '').strip(), 'product_name': product_name, 'name': product_name, 'description': product_name, 'hsn': self.safe_item_text(row, 2, row_meta.get('hsn', '')).strip(), 'rate': self.safe_float_from_cell(row, 7, row_meta.get('rate', 0.0)), 'qty': quantity, 'quantity': quantity, 'gross': self.safe_float_from_cell(row, 9, 0.0), 'gross_value': self.safe_float_from_cell(row, 9, 0.0), 'discount': self.safe_float_from_cell(row, 10, 0.0), 'net': self.safe_float_from_cell(row, 11, 0.0), 'net_value': self.safe_float_from_cell(row, 11, 0.0), 'taxable_value': self.safe_float_from_cell(row, 11, 0.0), 'tax_percent': gst_rate, 'gst_rate': gst_rate, 'cgst': cgst_rate, 'sgst': sgst_rate, 'igst': igst_rate, 'cess': cess_rate, 'cess_rate': cess_rate, 'tax_amount': self.safe_float_from_cell(row, 12, 0.0), 'total': self.safe_float_from_cell(row, 13, 0.0), 'grand_total': self.safe_float_from_cell(row, 13, 0.0)})
            QCoreApplication.processEvents()
        return cart_data

    def _build_a4_quotation_totals_data(self, cart_data):
        """Return quotation header, customer, terms, and total values."""
        totals = self.calculate_totals()
        grand_total = self._safe_float(totals.get('grand_total', 0.0), 0.0)
        quotation_type = self.quotation_type_combo.currentText().strip() if hasattr(self, 'quotation_type_combo') else ''
        title = 'PROFORMA QUOTATION' if quotation_type == 'Proforma' else 'QUOTATION / ESTIMATE'
        return {'document_title': title, 'document_number_label': 'Quotation No', 'document_date_label': 'Quotation Date', 'invoice_number': self.quotation_no_input.text().strip(), 'invoice_date': qdate_to_db(self.date_input.date()), 'valid_until': qdate_to_db(self.valid_until_input.date()) if hasattr(self, 'valid_until_input') else '', 'quotation_status': self.status_combo.currentText().strip() if hasattr(self, 'status_combo') else '', 'quotation_type': quotation_type, 'customer_name': self.customer_name_input.text().strip() if hasattr(self, 'customer_name_input') else '', 'mobile': self.mobile_input.text().strip() if hasattr(self, 'mobile_input') else '', 'customer_gstin': self.gstin_input.text().strip() if hasattr(self, 'gstin_input') else '', 'customer_address': self.address_input.text().strip() if hasattr(self, 'address_input') else '', 'state': self.state_combo.currentText().strip() if hasattr(self, 'state_combo') else '', 'sub_total': totals.get('sub_total', 0.0), 'subtotal': totals.get('sub_total', 0.0), 'freight': totals.get('freight', 0.0), 'discount': totals.get('discount_total', 0.0), 'discount_total': totals.get('discount_total', 0.0), 'cgst': totals.get('cgst_total', 0.0), 'sgst': totals.get('sgst_total', 0.0), 'cess': totals.get('cess_total', 0.0), 'cgst_total': totals.get('cgst_total', 0.0), 'sgst_total': totals.get('sgst_total', 0.0), 'igst_total': totals.get('igst_total', 0.0), 'cess_total': totals.get('cess_total', 0.0), 'tax_total': totals.get('tax_total', 0.0), 'round_off': totals.get('round_off', 0.0), 'grand_total': grand_total, 'total': grand_total, 'total_amount': grand_total, 'total_items': sum((self._safe_float(item.get('quantity'), 0.0) for item in cart_data)), 'narration': self.narration_input.text().strip() if hasattr(self, 'narration_input') else ''}

    def _print_settings_metadata(self, settings):
        """Return metadata embedded in saved print layout coordinates."""
        raw_coordinates = settings.get('layout_coordinates', '') or ''
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

    def _resolve_default_print_mode(self, settings):
        """Return the saved global default print mode for quotation printing."""
        try:
            metadata = self._print_settings_metadata(settings)
            default_mode = settings.get('default_print_mode', 'Thermal Receipt')
            if not str(default_mode or '').strip():
                default_mode = 'Thermal Receipt'
            metadata_mode = metadata.get('default_print_mode')
            has_direct_mode = 'default_print_mode' in settings and str(settings.get('default_print_mode') or '').strip()
            if not has_direct_mode and str(metadata_mode or '').strip():
                default_mode = metadata_mode
            normalized_mode = str(default_mode or '').strip()
            if normalized_mode in {'Thermal Receipt', 'A4/A5 Invoice'}:
                return normalized_mode
            mode_key = normalized_mode.lower().replace('-', '_').replace(' ', '_')
            if mode_key in {'a4/a5_invoice', 'a4_a5_invoice', 'a4_invoice', 'a5_invoice', 'a4', 'a5'}:
                return 'A4/A5 Invoice'
            if mode_key in {'thermal_receipt', 'thermal', 'receipt', 'roll', '80mm', '58mm'}:
                return 'Thermal Receipt'
        except Exception as exc:
            print(f'Failed to resolve quotation print mode: {exc}')
        return 'Thermal Receipt'

    def _saved_printer_name(self, settings, preferred_key):
        """Return a saved printer name from layout metadata or legacy settings."""
        metadata = self._print_settings_metadata(settings)
        printer_name = str(metadata.get(preferred_key) or '').strip()
        if printer_name:
            return printer_name
        printer_name = str(settings.get(preferred_key) or '').strip()
        if printer_name:
            return printer_name
        return str(settings.get('printer_name', '') or '').strip()

    def _a4_paper_size_from_settings(self, settings):
        """Return the saved A4 paper size from metadata or legacy fields."""
        try:
            metadata = self._print_settings_metadata(settings)
            for key in ('a4_paper_size', 'paper_size', 'default_format'):
                value = str(metadata.get(key) or settings.get(key) or '').strip().upper()
                if value in {'A4', 'A5'}:
                    return value
        except Exception as exc:
            print(f'Failed to resolve quotation paper size: {exc}')
        return 'A4'

    def _a4_html_has_preview_wrapper(self, html_string):
        """Return whether settings-preview-only HTML is present in print HTML."""
        html_text = str(html_string or '')
        return 'width: 794px' in html_text or 'class="preview-body"' in html_text

    def _quotation_voucher_data(self):
        """Build ExportEngine payload from the current quotation form."""
        totals = self.calculate_totals()
        items = []
        for row in range(self.items_table.rowCount()):
            product = self._cell_text(row, 1).strip()
            if not product:
                continue
            items.append({'name': product, 'quantity': self._safe_float(self._cell_text(row, 8)), 'rate': self._safe_float(self._cell_text(row, 7)), 'amount': self._safe_float(self._cell_text(row, 13))})
        return {'voucher_type': 'Quotation', 'voucher_no': self.quotation_no_input.text().strip(), 'voucher_date': qdate_to_db(self.date_input.date()), 'party_name': self.customer_name_input.text().strip(), 'total_amount': totals.get('sub_total', 0.0), 'tax_amount': totals.get('tax_total', 0.0), 'grand_total': totals.get('grand_total', 0.0), 'tax_breakdown': [{'name': 'CGST', 'amount': totals.get('cgst_total', 0.0)}, {'name': 'SGST', 'amount': totals.get('sgst_total', 0.0)}, {'name': 'IGST', 'amount': totals.get('igst_total', 0.0)}, {'name': 'CESS', 'amount': totals.get('cess_total', 0.0)}], 'items': items}

    def _generate_and_open_quotation_pdf(self, filepath=None, open_pdf=True):
        """Generate a quotation PDF with ReportLab and quotation-only terms."""
        if not self.current_quotation_id:
            QMessageBox.warning(self, 'Print Quotation', 'Please save the quotation before printing.')
            return None
        output_path = filepath
        if not output_path:
            temp_fd, output_path = tempfile.mkstemp(suffix='.pdf')
            os.close(temp_fd)
        result = ExportEngine(self.db).export_quotation_pdf(self._quotation_voucher_data(), output_path, self.company_id)
        if not result.get('success'):
            QMessageBox.critical(self, 'Quotation PDF', result.get('error', 'Failed to generate quotation PDF.'))
            return None
        if open_pdf:
            try:
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(output_path)))
            except Exception:
                pass
        return output_path

    def _normalize_india_mobile(self, raw_mobile):
        """Normalize a customer mobile number for India-first quote sharing."""
        mobile = (raw_mobile or '').strip()
        if not mobile:
            return ('', '')
        if mobile.startswith('+'):
            normalized = '+' + re.sub('\\D', '', mobile[1:])
        else:
            normalized = re.sub('\\D', '', mobile)
        digits = re.sub('\\D', '', normalized)
        if len(digits) == 10:
            digits = f'91{digits}'
            normalized = f'+{digits}'
        elif normalized.startswith('+') and digits:
            normalized = f'+{digits}'
        else:
            normalized = digits
        if len(digits) < 10:
            return ('', '')
        return (normalized, digits)

    def _quote_share_message(self):
        """Build a clean customer-facing quotation share summary."""
        totals = self.calculate_totals()
        customer_name = self.customer_name_input.text().strip() if hasattr(self, 'customer_name_input') else ''
        quote_no = self.quotation_no_input.text().strip() if hasattr(self, 'quotation_no_input') else ''
        grand_total = self._safe_float(totals.get('grand_total', 0.0), 0.0)
        return f"Dear {customer_name or 'Customer'}, Here is your quotation for Rs. {grand_total:.2f}. Quote No: {quote_no or 'Draft'}. Thank you for choosing FAIZAN TEXTILES."

    def _quote_mobile_numbers(self):
        """Return the normalized display and URL-safe mobile numbers after validation."""
        mobile_raw = self.mobile_input.text().strip() if hasattr(self, 'mobile_input') else ''
        if not mobile_raw:
            QMessageBox.warning(self, 'Share Quotation', 'Please enter mobile number first.')
            return ('', '')
        display_mobile, whatsapp_mobile = self._normalize_india_mobile(mobile_raw)
        if not whatsapp_mobile:
            QMessageBox.warning(self, 'Share Quotation', 'Please enter a valid mobile number with at least 10 digits.')
            return ('', '')
        return (display_mobile, whatsapp_mobile)

    def _configured_sms_gateway_url(self, mobile_number, encoded_message):
        """Build a future SMS gateway URL when config.py defines one."""
        template = getattr(config, 'SMS_GATEWAY_URL_TEMPLATE', '') or getattr(config, 'SMS_GATEWAY_URL', '')
        if not template:
            return ''
        if '{' in template:
            return template.format(mobile=mobile_number, phone=mobile_number, message=encoded_message, encoded_message=encoded_message)
        separator = '&' if '?' in template else '?'
        return f'{template}{separator}mobile={mobile_number}&message={encoded_message}'

    def send_whatsapp_quote(self):
        """Open WhatsApp Web with a URL-encoded quotation summary."""
        try:
            _display_mobile, whatsapp_mobile = self._quote_mobile_numbers()
            if not whatsapp_mobile:
                return
            encoded_message = quote(self._quote_share_message())
            url = f'https://web.whatsapp.com/send?phone={whatsapp_mobile}&text={encoded_message}'
            webbrowser.open(url)
        except Exception as exc:
            QMessageBox.warning(self, 'WhatsApp Quotation', f'Could not open WhatsApp quotation link: {exc}')

    def send_sms_quote(self):
        """Open a configured SMS gateway or desktop SMS handler with quote text."""
        try:
            display_mobile, sms_mobile = self._quote_mobile_numbers()
            if not sms_mobile:
                return
            encoded_message = quote(self._quote_share_message())
            url = self._configured_sms_gateway_url(sms_mobile, encoded_message)
            if not url:
                url = f'sms:{display_mobile}?body={encoded_message}'
            webbrowser.open(url)
            QMessageBox.information(self, 'SMS Quotation', 'SMS quotation link opened. Configure SMS_GATEWAY_URL_TEMPLATE in config.py for gateway delivery.')
        except Exception as exc:
            QMessageBox.warning(self, 'SMS Quotation', f'Could not open SMS quotation link: {exc}')

    def share_bill(self, platform):
        """Backward-compatible quote sharing dispatcher."""
        platform_key = (platform or '').strip().lower()
        if platform_key == 'whatsapp':
            self.send_whatsapp_quote()
            return
        if platform_key == 'sms':
            self.send_sms_quote()
            return
        QMessageBox.warning(self, 'Share Quotation', f'Unknown sharing platform: {platform}')

    def confirm_remove_bill(self):
        """Clear the current quotation form after confirmation."""
        reply = QMessageBox.question(self, 'Clear Quotation', 'Clear this quotation from the entry screen?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.clear_form()

    def on_customer_name_changed(self, text):
        """Format customer name and autofill matching debtor details."""
        self._title_case_line_edit(self.customer_name_input, text)
        party = self._find_party(text)
        if party:
            self._apply_party_to_customer_fields(party)

    def on_address_changed(self, text):
        """Apply title case formatting to address text."""
        self._title_case_line_edit(self.address_input, text)

    def on_state_changed(self, _text):
        """Recalculate GST columns when state changes."""
        self.on_nature_changed(self.nature_combo.currentText())

    def on_rate_refresh_clicked(self):
        """Refresh rate on the active row from the selected rate type."""
        row = self.items_table.currentRow()
        if row >= 0 and row < len(self.sale_items):
            product_id = self.sale_items[row].get('product_id')
            product = self.products_dict.get(product_id)
            if product:
                self._set_cell_text(row, 7, f'{self.get_product_rate_from_selector(product):.2f}')
                self.recalculate_row(row, source_column=7, live_value=self._cell_text(row, 7))

    def _with_live_stock(self, product):
        """Return product data enriched with the Sales Entry live-stock shape."""
        if not product:
            return None
        enriched = dict(product)
        product_id = enriched.get('id')
        company_id = self.company_id or active_company_manager.get_active_company_id()
        live_stock = enriched.get('current_stock', enriched.get('quantity', 'N/A'))
        if company_id and product_id not in (None, ''):
            try:
                live_stock = self.stock_logic.get_current_stock(company_id, product_id)
            except Exception:
                live_stock = enriched.get('current_stock', enriched.get('quantity', 'N/A'))
        enriched['current_stock'] = live_stock
        if live_stock != 'N/A':
            enriched['quantity'] = live_stock
        enriched.setdefault('barcode', 'N/A')
        enriched.setdefault('purchase_rate', 'N/A')
        enriched.setdefault('mrp', 'N/A')
        return enriched

    def _format_status_value(self, value, default='N/A'):
        """Format status-strip values without raising on missing product keys."""
        if value in (None, ''):
            return default
        return str(value)

    def _update_top_bar_for_product(self, product, barcode_or_code=None):
        """Refresh quotation status strip using the same product fields as Sales."""
        product = self._with_live_stock(product)
        if not product:
            return
        code_value = barcode_or_code
        if code_value is None:
            code_value = product.get('code') or product.get('barcode', 'N/A')
        if hasattr(self, 'product_input'):
            self.product_input.blockSignals(True)
            self.product_input.setText(self._format_status_value(product.get('name'), ''))
            self.product_input.blockSignals(False)
        if hasattr(self, 'code_display'):
            self.code_display.setText(self._format_status_value(code_value))
        if hasattr(self, 'stock_display'):
            self.stock_display.setText(self._format_status_value(product.get('current_stock')))
            self.stock_display.setStyleSheet(f'color: {theme.semantic_positive_hex()};')
        if hasattr(self, 'category_display'):
            self.category_display.setText(self._format_status_value(product.get('category'), ''))
        if hasattr(self, 'size_display'):
            self.size_display.setText(self._format_status_value(product.get('size'), ''))
        if hasattr(self, 'color_display'):
            self.color_display.setText(self._format_status_value(product.get('color'), ''))

    def on_table_selection_changed(self):
        """Update non-posting product status displays; keep SL row outline only."""
        if self.manually_selected_row == -1:
            self.items_table.clearSelection()
            return
        row = self.items_table.currentRow()
        if row < 0 or row >= len(self.sale_items):
            return
        product_id = self.sale_items[row].get('product_id')
        product = self.products_dict.get(product_id, {}) if product_id else {}
        self._update_top_bar_for_product(product)

    def safe_item_text(self, row, col, default=''):
        """Read a table cell as text using the Sales Entry helper."""
        return _safe_item_text(self.items_table, row, col, default)

    def safe_float_from_cell(self, row, col, default=0.0):
        """Read a table cell as float using the Sales Entry helper."""
        return _safe_float_from_cell(self.items_table, row, col, default)

    def ensure_row_items_initialized(self, row):
        """Ensure a quotation grid row has all Sales Entry columns."""
        _ensure_row_items_initialized(self.items_table, row)

    def recalculate_row(self, row, source_column=None, live_value=None):
        """Recalculate one quotation row with the Sales Entry calculation engine."""
        _recalculate_sales_row(self, row, source_column=source_column, live_value=live_value)

    def get_product_rate_from_selector(self, product):
        """Return the selected quote rate from the Sales Entry rate selector."""
        selector = self.rate_selector_combo.currentText() if hasattr(self, 'rate_selector_combo') else 'Sales Rate'
        if selector == 'Purchase Rate':
            return self._safe_float(product.get('purchase_rate'))
        if selector == 'Wholesale Rate':
            return self._safe_float(product.get('wholesale_rate'))
        if selector == 'MRP':
            return self._safe_float(product.get('mrp'))
        return self._safe_float(product.get('sale_price'))

    def enforce_qty_stock_limit(self, _row, _qty, show_warning=False):
        """Quotations do not reduce or enforce stock."""
        return False

    def update_stock_display_for_row(self, row):
        """Refresh stock label only; quotations never mutate stock."""
        if row < 0 or row >= len(self.sale_items):
            return
        product = self.products_dict.get(self.sale_items[row].get('product_id'), {})
        self._update_top_bar_for_product(product)

    def add_blank_row(self):
        """Dynamic-row guard for the shared delegate; quotations add rows via products."""
        return self.items_table.currentRow()

    def _ensure_product_id_column(self):
        """Ensure the hidden product_id column exists on the active quotation grid."""
        if not hasattr(self, 'items_table'):
            return
        if self.items_table.columnCount() <= 14:
            self.items_table.setColumnCount(15)
        self.items_table.setColumnHidden(14, True)

    def _quotation_item_from_product(self, product, rate, qty):
        """Build the internal quotation item cache entry for a selected product."""
        return {'product_id': product.get('id'), 'hsn': product.get('hsn', ''), 'cgst': self._safe_float(product.get('cgst')), 'sgst': self._safe_float(product.get('sgst')), 'igst': self._safe_float(product.get('igst')), 'cess': self._safe_float(product.get('cess')), 'tax_percent': 0.0, 'rate': rate, 'qty': self._safe_float(qty, 1.0)}

    def _blank_quotation_item(self):
        """Return an empty quotation item for row-cache alignment."""
        return {'product_id': None, 'hsn': '', 'cgst': 0.0, 'sgst': 0.0, 'igst': 0.0, 'cess': 0.0, 'tax_percent': 0.0, 'rate': 0.0, 'qty': 0.0}

    def _set_quotation_item_for_row(self, row, product, rate, qty):
        """Keep quotation_items aligned with the table row populated from Product Entry."""
        while len(self.sale_items) <= row:
            self.sale_items.append(self._blank_quotation_item())
        self.sale_items[row] = self._quotation_item_from_product(product, rate, qty)

    def _cache_product(self, product):
        """Refresh in-memory product lookups with a newly saved product."""
        product = self._with_live_stock(product) or {}
        product_id = product.get('id')
        if product_id:
            self.products_dict[product_id] = product
        barcode_key = str(product.get('barcode') or '').strip()
        if barcode_key:
            self.products_by_barcode[barcode_key] = product
        name_key = str(product.get('name') or '').strip().lower()
        if name_key:
            self.products_by_name_exact[name_key] = product
        for index, cached_product in enumerate(self.products_data):
            if cached_product.get('id') == product_id and product_id:
                self.products_data[index] = product
                break
        else:
            self.products_data.append(product)

    def _populate_product_row(self, row, product, qty=1.0, rate=None, focus_qty=True):
        """Populate an existing quotation row with full product details."""
        if not product:
            return -1
        self._ensure_product_id_column()
        while row >= self.items_table.rowCount():
            self.items_table.insertRow(self.items_table.rowCount())
        self.ensure_row_items_initialized(row)
        rate = self.get_product_rate_from_selector(product) if rate is None else self._safe_float(rate)
        qty = self._safe_float(qty, 1.0)
        if qty <= 0:
            qty = 1.0
        is_local = self.nature_combo.currentText() == 'Local'
        values = {0: str(row + 1), 1: str(product.get('name') or ''), 2: str(product.get('hsn') or ''), 3: f"{self._safe_float(product.get('cgst')):.2f}" if is_local else '0', 4: f"{self._safe_float(product.get('sgst')):.2f}" if is_local else '0', 5: '0' if is_local else f"{self._safe_float(product.get('igst')):.2f}", 6: f"{self._safe_float(product.get('cess')):.2f}", 7: f'{rate:.2f}', 8: f'{qty:.2f}', 9: f'{rate * qty:.2f}', 10: '0.00'}
        for col, value in values.items():
            item = self.items_table.item(row, col)
            item.setText(value)
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if col not in (0, 11, 12, 13):
                flags |= Qt.ItemIsEditable
            item.setFlags(flags)
        for col in (11, 12, 13):
            self.items_table.item(row, col).setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        hidden_item = self.items_table.item(row, 14)
        if hidden_item is None:
            hidden_item = QTableWidgetItem('')
            self.items_table.setItem(row, 14, hidden_item)
        hidden_item.setText(str(product.get('id') or ''))
        hidden_item.setFlags(Qt.NoItemFlags)
        product = self._with_live_stock(product) or product
        self._cache_product(product)
        self._set_quotation_item_for_row(row, product, rate, qty)
        self.last_barcode_filled_row = row
        self.recalculate_row(row)
        self.calculate_totals()
        self._update_top_bar_for_product(product)
        if focus_qty and (not getattr(self, '_barcode_scan_returns_focus', False)):
            QTimer.singleShot(0, lambda r=row: self.focus_table_cell_editor(r, 8))
        return row

    def add_product_row(self, product, qty=1.0, rate=None):
        """Add a quotation row only when a product is selected or scanned."""
        row = self.items_table.rowCount()
        return self._populate_product_row(row, product, qty=qty, rate=rate)

    def show_debtor_search_popup(self):
        """Show a compact debtor popup from Tab on Name."""
        if not self.parties_data:
            self.load_parties()
        popup = QDialog(self)
        popup.setWindowTitle('Select Debtor')
        popup.resize(620, 420)
        popup.setStyleSheet(theme.entry_picker_dialog_style())
        layout = QVBoxLayout(popup)
        search_input = QLineEdit(self.customer_name_input.text().strip())
        search_input.setStyleSheet(self.compact_input_style())
        layout.addWidget(search_input)
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(['Name', 'Mobile', 'GSTIN', 'State'])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)
        layout.addWidget(table)
        visible = []

        def populate(text=''):
            visible.clear()
            table.setRowCount(0)
            needle = text.strip().lower()
            for party in self.parties_data:
                haystack = ' '.join((str(party.get(k) or '') for k in ('name', 'mobile_number', 'gstin', 'state'))).lower()
                if needle and needle not in haystack:
                    continue
                row = table.rowCount()
                table.insertRow(row)
                visible.append(party)
                for col, key in enumerate(('name', 'mobile_number', 'gstin', 'state')):
                    table.setItem(row, col, QTableWidgetItem(str(party.get(key) or '')))
            if table.rowCount():
                table.selectRow(0)

        def choose():
            row = table.currentRow()
            if 0 <= row < len(visible):
                self._apply_party_to_customer_fields(visible[row])
                popup.accept()
                QTimer.singleShot(0, self.address_input.setFocus)
        search_input.textChanged.connect(populate)
        table.itemDoubleClicked.connect(lambda _item: choose())
        search_input.returnPressed.connect(choose)
        populate(search_input.text())
        QTimer.singleShot(0, lambda: (search_input.setFocus(), search_input.selectAll()))
        popup.exec()

    def _apply_party_to_customer_fields(self, party):
        """Copy debtor details into the quotation header fields."""
        self.customer_name_input.blockSignals(True)
        self.customer_name_input.setText(str(party.get('name') or ''))
        self.customer_name_input.blockSignals(False)
        self.mobile_input.setText(str(party.get('mobile_number') or ''))
        self.gstin_input.setText(str(party.get('gstin') or '').upper())
        self.state_combo.setCurrentText(str(party.get('state') or ''))
        self.address_input.setText(str(party.get('address') or ''))

    def _find_party(self, text):
        """Find an exact debtor by typed name."""
        needle = (text or '').strip().lower()
        if not needle:
            return None
        for party in self.parties_data:
            if str(party.get('name') or '').strip().lower() == needle:
                return party
        return None

    def on_barcode_enter(self):
        """Barcode Enter: non-empty adds item; empty moves to Product field."""
        search_text = self.barcode_input.text().strip()
        if not search_text:
            self.product_input.setFocus()
            self.product_input.selectAll()
            return
        product = self._find_product_by_barcode(search_text)
        if not product:
            QMessageBox.warning(self, 'Product Not Found', f'No product found: {search_text}')
            self.barcode_input.clear()
            self.barcode_input.setFocus()
            return
        self._barcode_scan_returns_focus = True
        try:
            self.add_product_row(product)
        finally:
            self._barcode_scan_returns_focus = False
        self._update_top_bar_for_product(product, search_text)
        self.barcode_input.clear()
        self.calculate_grand_totals()
        self.barcode_input.setFocus()

    def on_product_enter(self):
        """Open only the mini product selector from the top-bar Product field."""
        self.show_product_popup()

    def on_nature_changed(self, text):
        """Handle Nature change to update tax columns based on GST type (Local vs Inter-state)."""
        if not text:
            return
        is_local = text == 'Local'
        for row in range(self.items_table.rowCount()):
            product_item = self.items_table.item(row, 1)
            if product_item is None or not product_item.text().strip():
                continue
            hidden_item = self.items_table.item(row, 14)
            if hidden_item is None:
                continue
            product_id = hidden_item.text()
            if not product_id:
                continue
            product = self.products_dict.get(int(product_id)) if product_id.isdigit() else None
            if not product:
                continue
            cgst_val = product.get('cgst', 0)
            sgst_val = product.get('sgst', 0)
            igst_val = product.get('igst', 0)
            if is_local:
                igst_item = self.items_table.item(row, 5)
                if igst_item:
                    igst_item.setText('0')
                cgst_item = self.items_table.item(row, 3)
                if cgst_item:
                    cgst_item.setText(f'{cgst_val:.2f}')
                sgst_item = self.items_table.item(row, 4)
                if sgst_item:
                    sgst_item.setText(f'{sgst_val:.2f}')
            else:
                cgst_item = self.items_table.item(row, 3)
                if cgst_item:
                    cgst_item.setText('0')
                sgst_item = self.items_table.item(row, 4)
                if sgst_item:
                    sgst_item.setText('0')
                igst_item = self.items_table.item(row, 5)
                if igst_item:
                    igst_item.setText(f'{igst_val:.2f}')
        self.calculate_totals()

    def _setup_text_formatting_and_navigation(self):
        """Install field formatting and keyboard navigation without changing app-wide behavior."""
        for field in [self.customer_name_input, self.address_input, self.narration_input, self.product_input]:
            field.textEdited.connect(lambda text, w=field: self._title_case_line_edit(w, text))
            field.installEventFilter(self)
        for field in [self.quotation_no_input, self.mobile_input, self.gstin_input, self.barcode_input]:
            field.installEventFilter(self)
        self.state_combo.installEventFilter(self)
        if self.state_combo.lineEdit():
            self.state_combo.lineEdit().installEventFilter(self)
        for field in [self.freight_input, self.discount_input, self.round_off_input]:
            field.installEventFilter(self)

    def _title_case_line_edit(self, widget, text):
        """Auto-capitalize first letter of each word while preserving cursor position."""
        if getattr(self, '_formatting_text', False):
            return
        formatted = ' '.join((part[:1].upper() + part[1:] for part in text.split(' ')))
        if formatted == text:
            return
        self._formatting_text = True
        pos = widget.cursorPosition()
        widget.setText(formatted)
        widget.setCursorPosition(min(pos, len(formatted)))
        self._formatting_text = False

    def on_gstin_changed(self, text):
        """Force GSTIN uppercase and fill/clear state from first two digits."""
        upper = text.upper()[:15]
        if upper != text:
            pos = self.gstin_input.cursorPosition()
            self.gstin_input.blockSignals(True)
            self.gstin_input.setText(upper)
            self.gstin_input.setCursorPosition(min(pos, len(upper)))
            self.gstin_input.blockSignals(False)
        if not upper:
            self.state_combo.setCurrentText('')
            return
        if len(upper) >= 2:
            state = theme.GST_STATE_CODES.get(upper[:2])
            if state:
                self.state_combo.setCurrentText(state)

    def _find_product(self, search_text, barcode_first=True):
        text = str(search_text or '').strip()
        if not text:
            return None
        text_lower = text.lower()
        if barcode_first:
            for product in self.products_data:
                if str(product.get('barcode', '') or '').strip() == text:
                    return product
        for product in self.products_data:
            if str(product.get('name', '') or '').strip().lower() == text_lower:
                return product
        for product in self.products_data:
            if text_lower in str(product.get('name', '') or '').lower():
                return product
        if not barcode_first:
            for product in self.products_data:
                if str(product.get('barcode', '') or '').strip() == text:
                    return product
        return None

    def _find_product_by_barcode(self, barcode):
        """Fetch product by barcode through the same DB helper pattern as Sales."""
        code = str(barcode or '').strip()
        if not code:
            return None
        try:
            company_id = self.company_id or active_company_manager.get_active_company_id()
            product = self.db.get_product_by_barcode(company_id, code) if company_id else None
            if product:
                product = self._with_live_stock(product)
                self._cache_product(product)
                return product
        except Exception as exc:
            print(f'Failed to query product by barcode: {exc}')
        return self._with_live_stock(self._find_product(code, barcode_first=True))

    def _find_exact_product(self, search_text):
        """Return an exact product match by name or barcode from the quotation cache."""
        text = str(search_text or '').strip()
        if not text:
            return None
        if not self.products_data:
            self.load_products()
        product = self.products_by_name_exact.get(text.lower()) if hasattr(self, 'products_by_name_exact') else None
        if product:
            return self._with_live_stock(product)
        for cached_product in self.products_data:
            if str(cached_product.get('barcode', '') or '').strip() == text:
                return self._with_live_stock(cached_product)
        return None

    def _row_has_committed_product(self, row):
        """Check whether the quotation row is already linked to a saved product."""
        if row < 0:
            return False
        try:
            hidden_item = self.items_table.item(row, 14)
            if hidden_item and hidden_item.text().strip():
                return True
            if row < len(self.sale_items):
                return bool(self.sale_items[row].get('product_id'))
        except Exception:
            return False
        return False

    def open_product_entry_new_from_row(self, row, suggested_name=''):
        """Open full Product Entry in new mode, matching Purchase Entry navigation."""
        try:
            from PySide6.QtWidgets import QApplication
            self._product_entry_context = {'mode': 'new', 'row': row, 'suggested_name': (suggested_name or '').strip()}
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
        except Exception as exc:
            QMessageBox.warning(self, 'Navigation Error', f'Could not open Product Entry: {exc}')

    def receive_product_from_product_page(self, product, qty, row):
        """Receive saved Product Entry data and populate the preserved quotation row."""
        try:
            self.load_products()
            product_id = product.get('id') if product else None
            if product_id and product_id in self.products_dict:
                product = self.products_dict[product_id]
            qty_value = self._safe_float(qty, 1.0)
            if qty_value <= 0:
                qty_value = 1.0
            target_row = row if row is not None and row >= 0 else self.items_table.currentRow()
            if target_row < 0:
                target_row = self.items_table.rowCount()
            populated_row = self._populate_product_row(target_row, product, qty=qty_value)
            self._product_entry_context = None
            self.product_input.clear()
            quote_window = self.window()
            quote_window.show()
            quote_window.raise_()
            quote_window.activateWindow()
            self.focus_table_cell_editor(populated_row, 8)
        except Exception as exc:
            print(f'Error receiving product from product page: {exc}')
            QMessageBox.warning(self, 'Error', f'Failed to load product into quotation table: {exc}')

    def handle_product_cell_enter(self, row, typed_name):
        """Open Product Entry when Product column Enter has an unknown product name."""
        typed_name = (typed_name or '').strip()
        if row < 0:
            return False
        if self._row_has_committed_product(row):
            return False
        exact_product = self._find_exact_product(typed_name)
        if exact_product:
            self._populate_product_row(row, exact_product)
            return True
        self.open_product_entry_new_from_row(row, typed_name)
        return True

    def show_product_popup(self):
        """Show the Sales/Purchase-style mini product selector for quotations."""
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
        search_input.setPlaceholderText('Type to search...')
        top.addWidget(search_lbl)
        top.addWidget(search_input)
        layout.addLayout(top)
        hint = QLabel('Type to search. Max 100 results shown.')
        hint.setStyleSheet(theme.barcode_manager_muted_hint_style())
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
        search_timer = QTimer()
        search_timer.setSingleShot(True)
        search_timer.setInterval(200)

        def do_search():
            """Populate popup rows from the same DB-backed search used by Sales/Purchase."""
            term = search_input.text().strip()
            tbl.setRowCount(0)
            if len(term) < 1:
                return
            try:
                results = self.db.search_products_limited(company_id, term, limit=100)
            except Exception as exc:
                print(f'Quotation product popup search failed: {exc}')
                results = []
            tbl.setUpdatesEnabled(False)
            tbl.blockSignals(True)
            for product in results:
                row = tbl.rowCount()
                tbl.insertRow(row)
                name_item = QTableWidgetItem(str(product.get('name', '') or ''))
                name_item.setData(Qt.UserRole, product.get('id'))
                tbl.setItem(row, 0, name_item)
                tbl.setItem(row, 1, QTableWidgetItem(str(product.get('barcode', '') or '')))
                tbl.setItem(row, 2, QTableWidgetItem(str(product.get('code', '') or product.get('hsn', '') or '')))
                rate = self.get_product_rate_from_selector(product)
                tbl.setItem(row, 3, QTableWidgetItem(f'{rate:.2f}'))
                stock = self._safe_float(product.get('current_stock', product.get('quantity')))
                tbl.setItem(row, 4, QTableWidgetItem(f'{stock:.3f}'))
                QCoreApplication.processEvents()
            tbl.blockSignals(False)
            tbl.setUpdatesEnabled(True)
            if tbl.rowCount() > 0:
                tbl.selectRow(0)
        search_timer.timeout.connect(do_search)
        search_input.textChanged.connect(lambda: search_timer.start())
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
            product_id_item = tbl.item(row, 0)
            product_id = product_id_item.data(Qt.UserRole) if product_id_item else None
            full_product = self.db.get_product_by_id(company_id, product_id) if product_id else None
            if full_product:
                product = self._with_live_stock(full_product)
            else:
                product = self._with_live_stock({'id': product_id, 'name': product_id_item.text() if product_id_item else '', 'barcode': tbl.item(row, 1).text() if tbl.item(row, 1) else '', 'hsn': tbl.item(row, 2).text() if tbl.item(row, 2) else '', 'sale_price': tbl.item(row, 3).text() if tbl.item(row, 3) else '0', 'current_stock': tbl.item(row, 4).text() if tbl.item(row, 4) else 'N/A'})
            if not product:
                return
            added_row = self.add_product_to_table(product)
            self._update_top_bar_for_product(product)
            popup.accept()
            if added_row is None or added_row < 0:
                added_row = self.items_table.rowCount() - 1
            self.focus_table_cell_editor(added_row, 8)

        def move_popup_selection(delta):
            """Move highlighted product row while the search field still has focus."""
            if tbl.rowCount() <= 0:
                return
            row = tbl.currentRow()
            if row < 0:
                row = 0 if delta >= 0 else tbl.rowCount() - 1
            else:
                row = max(0, min(tbl.rowCount() - 1, row + delta))
            tbl.selectRow(row)
            tbl.scrollToItem(tbl.item(row, 0), QAbstractItemView.PositionAtCenter)

        def focus_popup_table():
            if tbl.rowCount() > 0:
                if tbl.currentRow() < 0:
                    tbl.selectRow(0)
                tbl.setFocus()

        class ProductPopupKeyFilter(QObject):
            """Route popup keys before child widgets consume them."""

            def eventFilter(self, watched, event):
                if event.type() != QEvent.KeyPress:
                    return False
                key = event.key()
                if watched == search_input:
                    if key == Qt.Key_Down:
                        move_popup_selection(1)
                        focus_popup_table()
                        return True
                    if key == Qt.Key_Up:
                        move_popup_selection(-1)
                        focus_popup_table()
                        return True
                    if key in (Qt.Key_Return, Qt.Key_Enter):
                        select_product()
                        return True
                    if key == Qt.Key_Escape:
                        popup.reject()
                        return True
                    return False
                if watched == tbl:
                    if key in (Qt.Key_Return, Qt.Key_Enter):
                        select_product()
                        return True
                    if key == Qt.Key_Escape:
                        popup.reject()
                        return True
                return False
        key_filter = ProductPopupKeyFilter(popup)
        search_input.installEventFilter(key_filter)
        tbl.installEventFilter(key_filter)
        tbl.itemDoubleClicked.connect(lambda *_: select_product())
        QTimer.singleShot(0, lambda: (search_input.setFocus(), search_input.selectAll()))
        buttons = QHBoxLayout()
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(popup.reject)
        select_btn = QPushButton('Select')
        select_btn.clicked.connect(select_product)
        buttons.addStretch()
        buttons.addWidget(cancel_btn)
        buttons.addWidget(select_btn)
        layout.addLayout(buttons)
        popup.exec()

    def focus_table_cell_editor(self, row, col):
        if row < 0 or row >= self.items_table.rowCount():
            return
        if col < 0 or col >= self.items_table.columnCount():
            return
        item = self.items_table.item(row, col)
        if item is None:
            item = QTableWidgetItem('')
            self.items_table.setItem(row, col, item)
        self.items_table.clearSelection()
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.items_table.setCurrentCell(row, col)
        item.setSelected(True)
        self.items_table.editItem(item)
        QTimer.singleShot(0, lambda r=row, c=col: self._wire_active_table_editor(r, c))

    def _select_active_editor_text(self):
        editor = QApplication.focusWidget()
        if isinstance(editor, QLineEdit):
            editor.selectAll()

    def _wire_active_table_editor(self, row=None, col=None):
        """Select active cell-editor text and connect live calculation once."""
        editor = QApplication.focusWidget()
        if not isinstance(editor, QLineEdit) or not self.items_table.isAncestorOf(editor):
            return
        editor.selectAll()
        editor.installEventFilter(self)
        # Connect live calc only once per editor; disconnect raises RuntimeWarning
        # when the slot was never connected on a freshly opened cell editor.
        if not getattr(editor, "_quotation_live_calc_wired", False):
            editor.textEdited.connect(self._active_table_editor_text_edited)
            editor._quotation_live_calc_wired = True

    def _active_table_editor_text_edited(self, text):
        """Live-update current table item and footer while a cell editor is active."""
        row = self.items_table.currentRow()
        col = self.items_table.currentColumn()
        if row < 0 or col < 0:
            return
        item = self.items_table.item(row, col)
        if item is None:
            item = QTableWidgetItem('')
            self.items_table.setItem(row, col, item)
        self.items_table.blockSignals(True)
        item.setText(text)
        self.items_table.blockSignals(False)
        self.calculate_totals()

    def _commit_active_table_editor(self):
        """Safely commit the active QLineEdit table editor into its QTableWidgetItem."""
        editor = QApplication.focusWidget()
        if not isinstance(editor, QLineEdit) or not self.items_table.isAncestorOf(editor):
            return
        row = self.items_table.currentRow()
        col = self.items_table.currentColumn()
        if row < 0 or col < 0:
            return
        item = self.items_table.item(row, col)
        if item is None:
            item = QTableWidgetItem('')
            self.items_table.setItem(row, col, item)
        self.items_table.blockSignals(True)
        item.setText(editor.text())
        self.items_table.blockSignals(False)

    def add_product_to_table(self, product):
        """Add product to items table with GST logic matching Sales Entry."""
        return self.add_product_row(product)
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        rate = product.get('sale_price', 0)
        cgst = product.get('cgst', 0)
        sgst = product.get('sgst', 0)
        igst = product.get('igst', 0)
        cess = product.get('cess', 0)
        is_local = self.nature_combo.currentText() == 'Local'
        for col in range(15):
            if self.items_table.item(row, col) is None:
                self.items_table.setItem(row, col, QTableWidgetItem(''))
        sl_item = self.items_table.item(row, 0)
        sl_item.setText(str(row + 1))
        sl_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        product_item = self.items_table.item(row, 1)
        product_item.setText(product.get('name', ''))
        product_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        hsn_item = self.items_table.item(row, 2)
        hsn_item.setText(product.get('hsn', ''))
        hsn_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        cgst_item = self.items_table.item(row, 3)
        cgst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        sgst_item = self.items_table.item(row, 4)
        sgst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        igst_item = self.items_table.item(row, 5)
        igst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        if is_local:
            cgst_item.setText(f'{cgst:.2f}')
            sgst_item.setText(f'{sgst:.2f}')
            igst_item.setText('0')
        else:
            cgst_item.setText('0')
            sgst_item.setText('0')
            igst_item.setText(f'{igst:.2f}')
        cess_item = self.items_table.item(row, 6)
        cess_item.setText(f'{cess:.2f}')
        cess_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        rate_item = self.items_table.item(row, 7)
        rate_item.setText(f'{rate:.2f}')
        rate_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        qty_item = self.items_table.item(row, 8)
        qty_item.setText('1.00')
        qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        gross_item = self.items_table.item(row, 9)
        gross_item.setText(f'{rate:.2f}')
        gross_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        discount_item = self.items_table.item(row, 10)
        discount_item.setText('0.00')
        discount_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        net_item = self.items_table.item(row, 11)
        net_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        tax_item = self.items_table.item(row, 12)
        tax_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        total_item = self.items_table.item(row, 13)
        total_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        hidden_item = self.items_table.item(row, 14)
        hidden_item.setText(str(product.get('id', '')))
        hidden_item.setFlags(Qt.NoItemFlags)
        self.calculate_totals()

    def on_table_cell_clicked(self, row, col):
        """Mirror Sales Entry selection: SL selects row; other cells open editor."""
        if col == 0:
            self.manually_selected_row = row
            self.items_table.clearSelection()
            if row >= 0 and row < len(self.sale_items):
                product_id = self.sale_items[row].get('product_id')
                product = self.products_dict.get(product_id) if product_id else None
                if product:
                    self._update_top_bar_for_product(product)
            self._refresh_manual_row_selection()
            return
        self.manually_selected_row = -1
        self.items_table.clearSelection()
        self._refresh_manual_row_selection()
        self.focus_table_cell_editor(row, col)

    def _refresh_manual_row_selection(self):
        """Repaint the billing grid so SL row-outline selection is visible."""
        if hasattr(self, 'items_table'):
            self.items_table.viewport().update()

    def on_item_changed(self, row, col):
        """Handle editable row changes and refresh line/footer calculations."""
        if self._calculating or self._loading_row:
            return
        if col in (3, 4, 5, 6, 7, 8, 9, 10):
            self.calculate_totals()

    def on_table_cell_changed(self, row, column):
        """Sales Entry table-builder hook for quotation row recalculation."""
        if hasattr(self, 'table_delegate') and self.table_delegate:
            if self.table_delegate.current_editor is not None:
                return
        if column in (3, 4, 5, 6, 7, 8, 9, 10):
            self.recalculate_row(row, source_column=column, live_value=self.safe_item_text(row, column, '0'))
        else:
            self.calculate_totals()

    def calculate_totals(self):
        """Calculate quotation line and footer totals with Sales Entry-style live refresh."""
        if getattr(self, '_is_initializing', False):
            return self._current_totals_dict()
        totals = _calculate_sales_totals(self)
        _write_totals_to_widgets(self, totals)
        self._last_totals = {'sub_total': totals.get('sub_total', 0.0), 'discount_total': totals.get('row_discount_total', 0.0) + self._safe_float(self.discount_total_input.text() if hasattr(self, 'discount_total_input') else 0.0), 'tax_total': totals.get('tax_total', 0.0), 'cgst_total': totals.get('cgst_total', 0.0), 'sgst_total': totals.get('sgst_total', 0.0), 'igst_total': totals.get('igst_total', 0.0), 'cess_total': totals.get('cess_total', 0.0), 'freight': self._safe_float(self.freight_input.text() if hasattr(self, 'freight_input') else 0.0), 'round_off': totals.get('round_off_val', 0.0), 'grand_total': totals.get('grand_total', 0.0)}
        return self._last_totals

    def calculate_grand_totals(self):
        """Compatibility wrapper for barcode flows that expect grand-total refresh."""
        return self.calculate_totals()
        if self._calculating:
            return self._current_totals_dict()
        self._calculating = True
        sub_total = 0.0
        total_tax = 0.0
        total_discount = 0.0
        cgst_total = 0.0
        sgst_total = 0.0
        igst_total = 0.0
        cess_total = 0.0
        is_local = self.nature_combo.currentText() == 'Local'
        current_row = self.items_table.currentRow()
        current_col = self.items_table.currentColumn()
        table_focused = self.items_table.hasFocus() or self._is_table_or_editor(QApplication.focusWidget())
        try:
            self.items_table.blockSignals(True)
            for row in range(self.items_table.rowCount()):
                product_item = self.items_table.item(row, 1)
                if product_item is None or not product_item.text().strip():
                    continue
                qty = self._safe_float(self._cell_text(row, 8))
                rate = self._safe_float(self._cell_text(row, 7))
                discount = self._safe_float(self._cell_text(row, 10))
                cgst = self._safe_float(self._cell_text(row, 3))
                sgst = self._safe_float(self._cell_text(row, 4))
                igst = self._safe_float(self._cell_text(row, 5))
                cess = self._safe_float(self._cell_text(row, 6))
                if is_local:
                    tax = (cgst + sgst) / 100.0
                else:
                    tax = igst / 100.0
                if table_focused and current_row == row and (current_col == 9):
                    gross = self._safe_float(self._cell_text(row, 9))
                    if qty:
                        rate = gross / qty
                        self._set_cell_text(row, 7, f'{rate:.2f}')
                else:
                    gross = qty * rate
                net = max(gross - discount, 0.0)
                tax_amount = net * tax
                cess_amount = net * (cess / 100.0)
                total_tax_row = tax_amount + cess_amount
                total = net + total_tax_row
                for c, v in ((9, gross), (11, net), (12, total_tax_row), (13, total)):
                    if table_focused and current_row == row and (current_col == c):
                        continue
                    self._set_cell_text(row, c, f'{v:.2f}')
                sub_total += net
                total_tax += total_tax_row
                total_discount += discount
                if is_local:
                    cgst_total += tax_amount / 2.0
                    sgst_total += tax_amount / 2.0
                else:
                    igst_total += tax_amount
                cess_total += cess_amount
        finally:
            self.items_table.blockSignals(False)
        footer_discount = self._safe_float(self.discount_input.text()) if hasattr(self, 'discount_input') else 0.0
        freight = self._safe_float(self.freight_input.text()) if hasattr(self, 'freight_input') else 0.0
        raw_total = sub_total + total_tax + freight - footer_discount
        if hasattr(self, 'round_off_check') and self.round_off_check.isChecked() and (not self._manual_round_off):
            rounded_total = int(raw_total)
            round_off = rounded_total - raw_total
            self.round_off_input.blockSignals(True)
            self.round_off_input.setText(f'{round_off:.2f}')
            self.round_off_input.blockSignals(False)
            grand_total = float(rounded_total)
        else:
            round_off = self._safe_float(self.round_off_input.text()) if hasattr(self, 'round_off_input') else 0.0
            grand_total = raw_total + round_off
        if hasattr(self, 'sub_total_value'):
            for field, value in ((self.sub_total_value, sub_total), (self.cgst_value, cgst_total), (self.sgst_value, sgst_total), (self.igst_value, igst_total), (self.cess_value, cess_total), (self.grand_total_value, grand_total)):
                field.blockSignals(True)
                field.setText(f'{value:.2f}')
                field.blockSignals(False)
        self._last_totals = {'sub_total': sub_total, 'discount_total': total_discount + footer_discount, 'tax_total': total_tax, 'cgst_total': cgst_total, 'sgst_total': sgst_total, 'igst_total': igst_total, 'cess_total': cess_total, 'freight': freight, 'round_off': round_off, 'grand_total': grand_total}
        self._calculating = False
        return self._last_totals

    def _current_totals_dict(self):
        return getattr(self, '_last_totals', {'sub_total': 0.0, 'discount_total': 0.0, 'tax_total': 0.0, 'cgst_total': 0.0, 'sgst_total': 0.0, 'igst_total': 0.0, 'cess_total': 0.0, 'freight': 0.0, 'round_off': 0.0, 'grand_total': 0.0})

    def _cell_text(self, row, col):
        item = self.items_table.item(row, col)
        return item.text() if item else ''

    def _set_cell_text(self, row, col, text):
        item = self.items_table.item(row, col)
        if item is None:
            item = QTableWidgetItem('')
            self.items_table.setItem(row, col, item)
        item.setText(str(text))

    def on_footer_discount_changed(self, _text):
        """Show footer discount percent while keeping flat amount as default."""
        if hasattr(self, 'discount_percent_label'):
            amount = self._safe_float(self.discount_total_input.text(), 0.0)
            sub_total = self._safe_float(self.sub_total_input.text(), 0.0) if hasattr(self, 'sub_total_input') else 0.0
            tax_total = self._safe_float(self.tax_total_input.text(), 0.0) if hasattr(self, 'tax_total_input') else 0.0
            row_discount_total = float(getattr(self, '_row_discount_total', 0.0) or 0.0)
            freight = self._safe_float(self.freight_input.text(), 0.0) if hasattr(self, 'freight_input') else 0.0
            base = sub_total - row_discount_total + tax_total + freight
            if amount > 0 and base > 0:
                pct = amount / base * 100.0
                pct_disp = f'{pct:.0f}' if float(pct).is_integer() else f'{pct:.2f}'
                self.discount_percent_label.setText(f'({pct_disp}%)')
            else:
                self.discount_percent_label.setText('')
        self.calculate_totals()

    def apply_discount_percent_mode(self):
        """Convert footer Discount value from percent to flat amount."""
        pct = self._safe_float(self.discount_total_input.text(), 0.0)
        if pct <= 0:
            return
        sub_total = self._safe_float(self.sub_total_input.text(), 0.0) if hasattr(self, 'sub_total_input') else 0.0
        tax_total = self._safe_float(self.tax_total_input.text(), 0.0) if hasattr(self, 'tax_total_input') else 0.0
        row_discount_total = float(getattr(self, '_row_discount_total', 0.0) or 0.0)
        freight = self._safe_float(self.freight_input.text(), 0.0) if hasattr(self, 'freight_input') else 0.0
        base = sub_total - row_discount_total + tax_total + freight
        if base <= 0:
            return
        pct = min(pct, 100.0)
        amount = round(base * pct / 100.0, 2)
        self.discount_total_input.blockSignals(True)
        self.discount_total_input.setText(f'{amount:.2f}')
        self.discount_total_input.blockSignals(False)
        if hasattr(self, 'discount_percent_label'):
            pct_disp = f'{pct:.0f}' if float(pct).is_integer() else f'{pct:.2f}'
            self.discount_percent_label.setText(f'({pct_disp}%)')
        self.calculate_totals()

    def apply_row_discount_percent_mode(self, row):
        """Convert the active row discount cell from percent to flat amount."""
        if row < 0:
            return
        percent = self.safe_float_from_cell(row, 10, 0.0)
        gross = self.safe_float_from_cell(row, 9, 0.0)
        if percent <= 0 or gross <= 0:
            return
        amount = round(gross * min(percent, 100.0) / 100.0, 2)
        self._set_cell_text(row, 10, f'{amount:.2f}')
        self.recalculate_row(row, source_column=10, live_value=str(amount))

    def on_round_off_toggle(self):
        self._manual_round_off = False
        self.calculate_totals()

    def on_round_off_edited(self):
        self._manual_round_off = True
        self.calculate_totals()

    def _safe_float(self, value, default=0.0):
        try:
            return float(value or default)
        except:
            return default

    def eventFilter(self, obj, event):
        """Quotation keyboard flow aligned with Sales Entry where requested."""
        if isinstance(obj, QLineEdit) and event.type() == QEvent.FocusIn and (not obj.isReadOnly()):
            QTimer.singleShot(0, obj.selectAll)
        if event.type() == QEvent.KeyPress:
            if obj == getattr(self, 'customer_name_input', None) and event.key() == Qt.Key_Tab:
                event.accept()
                QTimer.singleShot(0, self.show_debtor_search_popup)
                return True
            if obj == getattr(self, 'discount_total_input', None) and event.key() == Qt.Key_Down:
                event.accept()
                self.apply_discount_percent_mode()
                return True
            if self._is_table_or_editor(obj) and event.key() == Qt.Key_Down and (self.items_table.currentColumn() == 10):
                event.accept()
                self._commit_active_table_editor()
                self.apply_row_discount_percent_mode(self.items_table.currentRow())
                return True
            if self._handle_top_bar_navigation_key(obj, event):
                return True
        if obj == self.items_table.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                item = self.items_table.itemAt(event.pos())
                if item:
                    clicked_row = item.row()
                    clicked_column = item.column()
                    if clicked_column == 0:
                        self.manually_selected_row = clicked_row
                        self.items_table.clearSelection()
                        if clicked_row >= 0 and clicked_row < len(self.sale_items):
                            product_id = self.sale_items[clicked_row].get('product_id')
                            product = self.products_dict.get(product_id) if product_id else None
                            if product:
                                self._update_top_bar_for_product(product)
                        self._refresh_manual_row_selection()
                        return True
                    else:
                        self.manually_selected_row = -1
                        self.items_table.clearSelection()
                        self._refresh_manual_row_selection()
                        if clicked_row >= 0 and clicked_row < len(self.sale_items):
                            product_id = self.sale_items[clicked_row].get('product_id')
                            product = self.products_dict.get(product_id) if product_id else None
                            if product:
                                self._update_top_bar_for_product(product)
                        self.items_table.setCurrentCell(clicked_row, clicked_column)
                        self.items_table.editItem(item)
                        QTimer.singleShot(0, lambda r=clicked_row, c=clicked_column: self._wire_active_table_editor(r, c))
                        return True
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_F1:
                target_row = self.items_table.rowCount() - 1
                if target_row >= 0:
                    self.focus_table_cell_editor(target_row, 8)
                    return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if obj == self.barcode_input:
                    event.accept()
                    self.on_barcode_enter()
                    return True
                if obj == self.product_input:
                    event.accept()
                    self.on_product_enter()
                    return True
                if obj in (self.discount_input, self.freight_input, self.round_off_input):
                    event.accept()
                    self.barcode_input.setFocus()
                    self.barcode_input.selectAll()
                    return True
                if self._is_table_or_editor(obj):
                    event.accept()
                    row = self.items_table.currentRow()
                    col = self.items_table.currentColumn()
                    self._commit_active_table_editor()
                    self.calculate_totals()
                    if col == 1:
                        typed_name = self._cell_text(row, 1).strip()
                        if self.handle_product_cell_enter(row, typed_name):
                            return True
                        self.focus_table_cell_editor(row, 2)
                        return True
                    if col == 2:
                        self.focus_table_cell_editor(row, 3)
                        return True
                    if col == 3:
                        self.focus_table_cell_editor(row, 4)
                        return True
                    if col == 4:
                        self.focus_table_cell_editor(row, 5)
                        return True
                    if col == 5:
                        self.focus_table_cell_editor(row, 6)
                        return True
                    if col == 6:
                        self.focus_table_cell_editor(row, 7)
                        return True
                    if col == 7:
                        self.focus_table_cell_editor(row, 8)
                        return True
                    if col == 8:
                        self.focus_table_cell_editor(row, 9)
                        return True
                    if col == 9:
                        self.focus_table_cell_editor(row, 10)
                        return True
                    if col == 10:
                        self.barcode_input.setFocus()
                        self.barcode_input.selectAll()
                        return True
            if key == Qt.Key_Escape:
                if self._is_table_or_editor(obj):
                    event.accept()
                    row = self.items_table.currentRow()
                    col = self.items_table.currentColumn()
                    reverse_map = {10: 9, 9: 8, 8: 7, 7: 6, 6: 5, 5: 4, 4: 3, 3: 2, 2: 1}
                    if col in reverse_map:
                        self.focus_table_cell_editor(row, reverse_map[col])
                        return True
                    if col == 1:
                        self.barcode_input.setFocus()
                        self.barcode_input.selectAll()
                        return True
        return super().eventFilter(obj, event)

    def _is_table_or_editor(self, obj):
        if obj == self.items_table or obj == self.items_table.viewport():
            return True
        fw = QApplication.focusWidget()
        return isinstance(fw, QLineEdit) and self.items_table.isAncestorOf(fw)

    def confirm_remove_item(self):
        """Ask for confirmation before removing an item row.

        The user must first click the SL No cell of the row (mirrors the
        Rewrite-item selection flow). If no row has been manually selected
        via SL No click, prompt the user to do so and abort.
        """
        target_row = getattr(self, 'manually_selected_row', -1)
        if target_row < 0:
            QMessageBox.information(self, 'Remove Item', 'Please click the SL No of the item you want to remove, then press Remove Item.')
            return
        if target_row >= self.items_table.rowCount():
            self.manually_selected_row = -1
            return
        if self.current_quotation_id:
            confirm_update = QMessageBox.question(self, 'Update Saved Quotation?', 'This is a saved quotation. Removing an item will modify it.\n\nDo you want to update this quotation?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if confirm_update != QMessageBox.Yes:
                return
        reply = QMessageBox.question(self, 'Remove Item', f'Are you sure you want to remove item at row {target_row + 1}?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.items_table.setCurrentCell(target_row, 0)
        self.delete_row()

    def delete_row(self):
        """Delete the currently selected row from the table."""
        current_row = self.items_table.currentRow()
        if current_row >= 0:
            self.items_table.removeRow(current_row)
            if 0 <= current_row < len(self.quotation_items):
                del self.quotation_items[current_row]
            self.manually_selected_row = -1
            self.items_table.clearSelection()
            self._refresh_manual_row_selection()
            for row in range(self.items_table.rowCount()):
                sl_item = QTableWidgetItem(str(row + 1))
                self.items_table.setItem(row, 0, sl_item)
            self.calculate_totals()

    def confirm_reset_all(self):
        """Ask for confirmation before clearing the entire form."""
        reply = QMessageBox.question(self, 'Clear Form', 'Are you sure you want to clear this form?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.clear_form()

    def save(self, is_manual=False):
        """Save quotation as an informational document only."""
        return self.save_quotation()

    def save_quotation(self):
        """Save quotation to database (zero-impact - no ledger/stock posting)."""
        if not self.company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        if self.current_quotation_id is not None:
            return self.update_quotation()
        conn = None
        try:
            totals = self.calculate_totals()
            quotation_no = self.quotation_no_input.text().strip()
            if not quotation_no:
                QMessageBox.warning(self, 'Missing Quotation No', 'Please generate a quotation number before saving.')
                return
            ph = self.db._get_placeholder()
            party_id = None
            customer_name = self.customer_name_input.text().strip()
            for party in self.parties_data:
                if party.get('name', '').strip().lower() == customer_name.lower():
                    party_id = party.get('id')
                    break
            query = f'\n                INSERT INTO quotations (\n                    company_id, quotation_no, quotation_date, party_id, customer_name,\n                    mobile, gstin, state, address, nature, quotation_type, status,\n                    valid_until, narration, sub_total, discount_total, tax_total,\n                    cgst_total, sgst_total, igst_total, cess_total, freight,\n                    round_off, grand_total\n                ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})\n            '
            params = (self.company_id, quotation_no, qdate_to_db(self.date_input.date()), party_id, customer_name, self.mobile_input.text().strip(), self.gstin_input.text().strip().upper(), self.state_combo.currentText(), self.address_input.text().strip(), self.nature_combo.currentText(), self.quotation_type_combo.currentText(), self.status_combo.currentText(), qdate_to_db(self.valid_until_input.date()), self.narration_input.text().strip(), totals['sub_total'], totals['discount_total'], totals['tax_total'], totals['cgst_total'], totals['sgst_total'], totals['igst_total'], totals['cess_total'], totals['freight'], totals['round_off'], totals['grand_total'])
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            quotation_id = self.db._get_last_insert_id(cursor) if hasattr(self.db, '_get_last_insert_id') else cursor.lastrowid
            self._insert_current_items(cursor, quotation_id)
            conn.commit()
            self.current_quotation_id = quotation_id
            self.quotation_no_input.setText(quotation_no)
            QMessageBox.information(self, 'Success', f'Quotation {quotation_no} saved successfully.')
            self.clear_form()
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            QMessageBox.critical(self, 'Error', f'Failed to save quotation: {e}')
        finally:
            if conn:
                self.db.disconnect()

    def _safe_int(self, value, default=0):
        try:
            return int(value or default)
        except:
            return default

    def update_quotation(self):
        """Update existing quotation without touching ledger/stock."""
        if not self.current_quotation_id:
            QMessageBox.warning(self, 'No Quotation', 'No quotation loaded for update.')
            return
        conn = None
        try:
            totals = self.calculate_totals()
            ph = self.db._get_placeholder()
            party_id = None
            customer_name = self.customer_name_input.text().strip()
            for party in self.parties_data:
                if party.get('name', '').strip().lower() == customer_name.lower():
                    party_id = party.get('id')
                    break
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(f'\n                UPDATE quotations SET\n                    quotation_no={ph}, quotation_date={ph}, party_id={ph}, customer_name={ph},\n                    mobile={ph}, gstin={ph}, state={ph}, address={ph}, nature={ph},\n                    quotation_type={ph}, status={ph}, valid_until={ph}, narration={ph},\n                    sub_total={ph}, discount_total={ph}, tax_total={ph}, cgst_total={ph},\n                    sgst_total={ph}, igst_total={ph}, cess_total={ph}, freight={ph},\n                    round_off={ph}, grand_total={ph}, updated_at=CURRENT_TIMESTAMP\n                WHERE id={ph} AND company_id={ph}\n            ', (self.quotation_no_input.text().strip(), qdate_to_db(self.date_input.date()), party_id, customer_name, self.mobile_input.text().strip(), self.gstin_input.text().strip().upper(), self.state_combo.currentText(), self.address_input.text().strip(), self.nature_combo.currentText(), self.quotation_type_combo.currentText(), self.status_combo.currentText(), qdate_to_db(self.valid_until_input.date()), self.narration_input.text().strip(), totals['sub_total'], totals['discount_total'], totals['tax_total'], totals['cgst_total'], totals['sgst_total'], totals['igst_total'], totals['cess_total'], totals['freight'], totals['round_off'], totals['grand_total'], self.current_quotation_id, self.company_id))
            cursor.execute(f'DELETE FROM quotation_items WHERE quotation_id={ph}', (self.current_quotation_id,))
            self._insert_current_items(cursor, self.current_quotation_id)
            conn.commit()
            QMessageBox.information(self, 'Updated', 'Quotation updated successfully.')
            self.clear_form()
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            QMessageBox.critical(self, 'Error', f'Failed to update quotation: {e}')
        finally:
            if conn:
                self.db.disconnect()

    def _insert_current_items(self, cursor, quotation_id):
        """Insert quotation items without touching product stock or ledgers."""
        ph = self.db._get_placeholder()
        item_query = f'\n            INSERT INTO quotation_items (\n                quotation_id, product_id, sl_no, product_name, barcode, hsn,\n                tax_percent, unit, rate, quantity, gross_value, discount,\n                net_value, cgst, sgst, igst, cess, tax_amount, grand_total\n            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})\n        '
        for row in range(self.items_table.rowCount()):
            product_item = self.items_table.item(row, 1)
            if not product_item or not product_item.text().strip():
                continue
            row_data = self.sale_items[row] if row < len(self.sale_items) else {}
            product_id = row_data.get('product_id')
            product = self.products_dict.get(product_id, {}) if product_id else {}
            cgst = self._safe_float(self._cell_text(row, 3))
            sgst = self._safe_float(self._cell_text(row, 4))
            igst = self._safe_float(self._cell_text(row, 5))
            cess = self._safe_float(self._cell_text(row, 6))
            tax_percent = igst + cess if self.nature_combo.currentText() == 'Inter-state' else cgst + sgst + cess
            cursor.execute(item_query, (quotation_id, product_id, row + 1, product_item.text().strip(), product.get('barcode', ''), self._cell_text(row, 2), tax_percent, product.get('unit', ''), self._safe_float(self._cell_text(row, 7)), self._safe_float(self._cell_text(row, 8)), self._safe_float(self._cell_text(row, 9)), self._safe_float(self._cell_text(row, 10)), self._safe_float(self._cell_text(row, 11)), cgst, sgst, igst, cess, self._safe_float(self._cell_text(row, 12)), self._safe_float(self._cell_text(row, 13))))
        return

    def previous_quotation(self):
        """Navigate to previous quotation by id sequence."""
        self._navigate_quotation(-1)

    def next_quotation(self):
        """Navigate to next quotation by id sequence."""
        self._navigate_quotation(1)

    def _load_quotation_nav_ids(self):
        if not self.company_id:
            self._quotation_nav_ids = []
            return
        ph = self.db._get_placeholder()
        rows = self.db.execute_query(f'SELECT id FROM quotations WHERE company_id={ph} ORDER BY id', (self.company_id,)) or []
        self._quotation_nav_ids = [r['id'] for r in rows]

    def _navigate_quotation(self, direction):
        self._load_quotation_nav_ids()
        if not self._quotation_nav_ids:
            QMessageBox.information(self, 'No Quotation', 'No saved quotations found.')
            return
        if self.current_quotation_id in self._quotation_nav_ids:
            idx = self._quotation_nav_ids.index(self.current_quotation_id) + direction
        else:
            idx = len(self._quotation_nav_ids) - 1 if direction < 0 else 0
        idx = max(0, min(idx, len(self._quotation_nav_ids) - 1))
        self.load_quotation_by_id(self._quotation_nav_ids[idx])

    def load_quotation_by_id(self, quotation_id):
        """Load a quotation header and items into the entry page."""
        ph = self.db._get_placeholder()
        rows = self.db.execute_query(f'\n            SELECT id, company_id, quotation_no, quotation_date, party_id, customer_name,\n                   mobile, gstin, state, address, nature, quotation_type, status,\n                   valid_until, narration, sub_total, discount_total, tax_total,\n                   cgst_total, sgst_total, igst_total, cess_total, freight,\n                   round_off, grand_total, converted_sale_id\n            FROM quotations\n            WHERE id={ph}\n        ', (quotation_id,)) or []
        if not rows:
            QMessageBox.warning(self, 'Missing', 'Quotation record not found.')
            return
        header = rows[0]
        items = self.db.execute_query(f'\n            SELECT id, quotation_id, product_id, sl_no, product_name, barcode, hsn,\n                   tax_percent, unit, rate, quantity, gross_value, discount,\n                   net_value, cgst, sgst, igst, cess, tax_amount, grand_total\n            FROM quotation_items\n            WHERE quotation_id={ph}\n            ORDER BY sl_no, id\n            ', (quotation_id,)) or []
        self._loading_row = True
        try:
            self._set_quotation_edit_mode(quotation_id)
            self.quotation_no_input.setText(str(header.get('quotation_no') or ''))
            d = QDate.fromString(str(header.get('quotation_date') or ''), 'yyyy-MM-dd')
            self.date_input.setDate(d if d.isValid() else QDate.currentDate())
            self.quotation_type_combo.setCurrentText(str(header.get('quotation_type') or 'Standard'))
            self.nature_combo.setCurrentText(str(header.get('nature') or 'Local'))
            self.status_combo.setCurrentText(str(header.get('status') or 'Pending'))
            vd = QDate.fromString(str(header.get('valid_until') or ''), 'yyyy-MM-dd')
            self.valid_until_input.setDate(vd if vd.isValid() else QDate.currentDate().addDays(15))
            self.customer_name_input.setText(str(header.get('customer_name') or ''))
            self.mobile_input.setText(str(header.get('mobile') or ''))
            self.gstin_input.setText(str(header.get('gstin') or '').upper())
            self.state_combo.setCurrentText(str(header.get('state') or ''))
            self.address_input.setText(str(header.get('address') or ''))
            self.narration_input.setText(str(header.get('narration') or ''))
            self.freight_input.setText(f"{self._safe_float(header.get('freight')):.2f}")
            self.discount_input.setText('0.00')
            self.round_off_input.setText(f"{self._safe_float(header.get('round_off')):.2f}")
            self._manual_round_off = True
            if hasattr(self, 'round_off_check'):
                self.round_off_check.setChecked(False)
            self.items_table.setRowCount(0)
            for item_data in items:
                self._add_saved_item_to_table(item_data)
        finally:
            self._loading_row = False
        self.calculate_totals()
        self._schedule_entry_baseline_finalize()

    def _add_saved_item_to_table(self, data):
        """Load saved quotation item into table with new GST column structure."""
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        self.ensure_row_items_initialized(row)
        values = {0: str(data.get('sl_no') or row + 1), 1: str(data.get('product_name') or ''), 2: str(data.get('hsn') or ''), 3: f"{self._safe_float(data.get('cgst')):.2f}", 4: f"{self._safe_float(data.get('sgst')):.2f}", 5: f"{self._safe_float(data.get('igst')):.2f}", 6: f"{self._safe_float(data.get('cess')):.2f}", 7: f"{self._safe_float(data.get('rate')):.2f}", 8: f"{self._safe_float(data.get('quantity')):.2f}", 9: f"{self._safe_float(data.get('gross_value')):.2f}", 10: f"{self._safe_float(data.get('discount')):.2f}", 11: f"{self._safe_float(data.get('net_value')):.2f}", 12: f"{self._safe_float(data.get('tax_amount')):.2f}", 13: f"{self._safe_float(data.get('grand_total')):.2f}"}
        for col, value in values.items():
            item = self.items_table.item(row, col)
            item.setText(value)
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if col not in (0, 11, 12, 13):
                flags |= Qt.ItemIsEditable
            item.setFlags(flags)
        self.sale_items.append({'product_id': data.get('product_id'), 'hsn': data.get('hsn', ''), 'cgst': self._safe_float(data.get('cgst')), 'sgst': self._safe_float(data.get('sgst')), 'igst': self._safe_float(data.get('igst')), 'cess': self._safe_float(data.get('cess')), 'tax_percent': self._safe_float(data.get('tax_percent')), 'rate': self._safe_float(data.get('rate')), 'qty': self._safe_float(data.get('quantity'))})
        return
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        for col in range(15):
            if self.items_table.item(row, col) is None:
                self.items_table.setItem(row, col, QTableWidgetItem(''))
        sl_item = self.items_table.item(row, 0)
        sl_item.setText(str(data.get('sl_no') or row + 1))
        sl_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        product_item = self.items_table.item(row, 1)
        product_item.setText(str(data.get('product_name') or ''))
        product_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        hsn_item = self.items_table.item(row, 2)
        hsn_item.setText(str(data.get('hsn') or ''))
        hsn_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        cgst_item = self.items_table.item(row, 3)
        cgst_item.setText(f"{self._safe_float(data.get('cgst')):.2f}")
        cgst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        sgst_item = self.items_table.item(row, 4)
        sgst_item.setText(f"{self._safe_float(data.get('sgst')):.2f}")
        sgst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        igst_item = self.items_table.item(row, 5)
        igst_item.setText(f"{self._safe_float(data.get('igst')):.2f}")
        igst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        cess_item = self.items_table.item(row, 6)
        cess_item.setText(f"{self._safe_float(data.get('cess')):.2f}")
        cess_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        rate_item = self.items_table.item(row, 7)
        rate_item.setText(f"{self._safe_float(data.get('rate')):.2f}")
        rate_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        qty_item = self.items_table.item(row, 8)
        qty_item.setText(f"{self._safe_float(data.get('quantity')):.2f}")
        qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        gross_item = self.items_table.item(row, 9)
        gross_item.setText(f"{self._safe_float(data.get('gross_value')):.2f}")
        gross_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        discount_item = self.items_table.item(row, 10)
        discount_item.setText(f"{self._safe_float(data.get('discount')):.2f}")
        discount_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        net_item = self.items_table.item(row, 11)
        net_item.setText(f"{self._safe_float(data.get('net_value')):.2f}")
        net_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        tax_item = self.items_table.item(row, 12)
        tax_item.setText(f"{self._safe_float(data.get('tax_amount')):.2f}")
        tax_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        total_item = self.items_table.item(row, 13)
        total_item.setText(f"{self._safe_float(data.get('grand_total')):.2f}")
        total_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        hidden_item = self.items_table.item(row, 14)
        hidden_item.setText(str(data.get('product_id') or ''))
        hidden_item.setFlags(Qt.NoItemFlags)

    def _current_quotation_party_details(self):
        """Return current quotation party fields for Sales Entry injection."""
        try:
            state = ''
            if hasattr(self, 'state_combo'):
                state = self.state_combo.currentText().strip()
            return {'party_name': self.customer_name_input.text().strip() if hasattr(self, 'customer_name_input') else '', 'mobile': self.mobile_input.text().strip() if hasattr(self, 'mobile_input') else '', 'address': self.address_input.text().strip() if hasattr(self, 'address_input') else '', 'gstin': self.gstin_input.text().strip() if hasattr(self, 'gstin_input') else '', 'state': state}
        except Exception as exc:
            print(f'Failed to read quotation party details: {exc}')
            return {'party_name': '', 'mobile': '', 'address': '', 'gstin': '', 'state': ''}

    def _product_id_for_quotation_row(self, row):
        """Return product id stored in the quotation row, if available."""
        try:
            product_id = self.safe_item_text(row, 14, '')
            if product_id:
                return product_id
            if row < len(self.sale_items):
                return self.sale_items[row].get('product_id')
        except Exception:
            pass
        return None

    def _product_cache_entry_for_quote_row(self, row, product_name):
        """Build a Sales-compatible product dict from a quotation grid row."""
        product_id = self._product_id_for_quotation_row(row)
        product = {}
        try:
            if product_id not in (None, ''):
                product = self.products_dict.get(int(product_id), {}) or {}
        except (TypeError, ValueError):
            product = self.products_dict.get(product_id, {}) or {}
        if not product and hasattr(self, 'products_by_name_exact'):
            product = self.products_by_name_exact.get(product_name.strip().lower(), {}) or {}
        return {'id': product.get('id', product_id), 'name': product_name, 'barcode': product.get('barcode', ''), 'hsn': self.safe_item_text(row, 2, product.get('hsn', '')), 'sale_price': self.safe_float_from_cell(row, 7, product.get('sale_price', 0)), 'purchase_rate': product.get('purchase_rate', 0), 'wholesale_rate': product.get('wholesale_rate', 0), 'mrp': product.get('mrp', 0), 'cgst': self.safe_float_from_cell(row, 3, product.get('cgst', 0)), 'sgst': self.safe_float_from_cell(row, 4, product.get('sgst', 0)), 'igst': self.safe_float_from_cell(row, 5, product.get('igst', 0)), 'cess': self.safe_float_from_cell(row, 6, product.get('cess', 0)), 'quantity': product.get('quantity', product.get('stock', 0))}

    def _extract_quotation_product_rows(self):
        """Extract valid, committed product rows from the active quotation grid."""
        rows = []
        try:
            for row in range(self.items_table.rowCount()):
                product_name = self.safe_item_text(row, 1, '')
                qty = self.safe_float_from_cell(row, 8, 0.0)
                rate = self.safe_float_from_cell(row, 7, 0.0)
                if not product_name or qty <= 0:
                    continue
                product = self._product_cache_entry_for_quote_row(row, product_name)
                rows.append({'product': product, 'product_name': product_name, 'hsn': self.safe_item_text(row, 2, ''), 'cgst': self.safe_float_from_cell(row, 3, 0.0), 'sgst': self.safe_float_from_cell(row, 4, 0.0), 'igst': self.safe_float_from_cell(row, 5, 0.0), 'cess': self.safe_float_from_cell(row, 6, 0.0), 'rate': rate, 'qty': qty, 'gross': self.safe_float_from_cell(row, 9, rate * qty), 'discount': self.safe_float_from_cell(row, 10, 0.0), 'net': self.safe_float_from_cell(row, 11, 0.0), 'tax_amount': self.safe_float_from_cell(row, 12, 0.0), 'grand_total': self.safe_float_from_cell(row, 13, 0.0)})
        except Exception as exc:
            QMessageBox.critical(self, 'Convert to Sale', f'Failed to read quotation product rows: {exc}')
            return []
        return rows

    def _set_line_edit_text_if_present(self, widget, attr_name, value):
        """Set text on a Sales Entry line edit when that field exists."""
        field = getattr(widget, attr_name, None)
        if field is not None and hasattr(field, 'setText'):
            field.setText(str(value or ''))

    def _set_combo_text_if_present(self, widget, attr_name, value):
        """Set combo text on Sales Entry when that combo exists."""
        combo = getattr(widget, attr_name, None)
        if combo is None or not hasattr(combo, 'setCurrentText'):
            return
        text = str(value or '')
        index = combo.findText(text, Qt.MatchFixedString) if hasattr(combo, 'findText') else -1
        if index >= 0 and hasattr(combo, 'setCurrentIndex'):
            combo.setCurrentIndex(index)
        else:
            combo.setCurrentText(text)

    def _inject_party_details_into_sales(self, sales_widget, party_details):
        """Copy quotation party details into Sales Entry top bar fields."""
        try:
            self._set_line_edit_text_if_present(sales_widget, 'customer_name_input', party_details.get('party_name', ''))
            self._set_line_edit_text_if_present(sales_widget, 'mobile_input', party_details.get('mobile', ''))
            self._set_line_edit_text_if_present(sales_widget, 'address_input', party_details.get('address', ''))
            self._set_line_edit_text_if_present(sales_widget, 'gstin_input', party_details.get('gstin', ''))
            self._set_combo_text_if_present(sales_widget, 'state_combo', party_details.get('state', ''))
            if hasattr(self, 'nature_combo'):
                self._set_combo_text_if_present(sales_widget, 'nature_combo', self.nature_combo.currentText())
        except Exception as exc:
            print(f'Failed to inject quotation party details into Sales Entry: {exc}')

    def _insert_sales_row_from_quotation(self, sales_widget, row_data):
        """Populate one Sales Entry row using Sales Entry APIs where possible."""
        product = dict(row_data.get('product') or {})
        qty = row_data.get('qty', 0.0)
        rate = row_data.get('rate', 0.0)
        try:
            if hasattr(sales_widget, 'add_product_to_table'):
                product_id = product.get('id')
                if product_id not in (None, ''):
                    if not hasattr(sales_widget, 'products_dict'):
                        sales_widget.products_dict = {}
                    sales_widget.products_dict[product_id] = product
                added = sales_widget.add_product_to_table(product, qty=qty, rate=rate)
                row = added[0] if isinstance(added, tuple) else added
            else:
                row = sales_widget.items_table.rowCount()
                sales_widget.items_table.insertRow(row)
                if hasattr(sales_widget, 'ensure_row_items_initialized'):
                    sales_widget.ensure_row_items_initialized(row)
            if row is None or row < 0:
                row = sales_widget.items_table.rowCount() - 1
            table = sales_widget.items_table
            was_blocked = table.blockSignals(True)
            try:
                values = {0: str(row + 1), 1: row_data.get('product_name', ''), 2: row_data.get('hsn', ''), 3: f"{row_data.get('cgst', 0.0):.2f}", 4: f"{row_data.get('sgst', 0.0):.2f}", 5: f"{row_data.get('igst', 0.0):.2f}", 6: f"{row_data.get('cess', 0.0):.2f}", 7: f'{rate:.2f}', 8: f'{qty:.3f}', 9: f"{row_data.get('gross', rate * qty):.2f}", 10: f"{row_data.get('discount', 0.0):.2f}"}
                for col, value in values.items():
                    item = table.item(row, col)
                    if item is None:
                        item = QTableWidgetItem('')
                        table.setItem(row, col, item)
                    item.setText(str(value))
            finally:
                table.blockSignals(was_blocked)
            if row < len(sales_widget.sale_items):
                sales_widget.sale_items[row].update({'product_id': product.get('id'), 'hsn': row_data.get('hsn', ''), 'cgst': row_data.get('cgst', 0.0), 'sgst': row_data.get('sgst', 0.0), 'igst': row_data.get('igst', 0.0), 'cess': row_data.get('cess', 0.0), 'rate': rate})
            if hasattr(sales_widget, 'recalculate_row'):
                sales_widget.recalculate_row(row)
            return True
        except Exception as exc:
            print(f'Failed to insert quotation row into Sales Entry: {exc}')
            return False

    def _copy_quote_footer_adjustments_to_sales(self, sales_widget):
        """Carry quotation footer discount and freight into Sales Entry."""
        try:
            if hasattr(self, 'freight_input'):
                self._set_line_edit_text_if_present(sales_widget, 'freight_input', self.freight_input.text().strip())
            if hasattr(self, 'discount_input'):
                self._set_line_edit_text_if_present(sales_widget, 'discount_total_input', self.discount_input.text().strip())
            if hasattr(self, 'narration_input') and hasattr(sales_widget, 'narration_input'):
                quote_no = self.quotation_no_input.text().strip() if hasattr(self, 'quotation_no_input') else ''
                source_note = f'Converted from Quotation {quote_no}'.strip()
                current_note = self.narration_input.text().strip()
                sales_widget.narration_input.setText(f'{source_note} - {current_note}' if current_note else source_note)
        except Exception as exc:
            print(f'Failed to copy quotation footer adjustments: {exc}')

    def _find_main_window_for_conversion(self):
        """Return the nearest application main window, when available."""
        window = self.window()
        while window is not None:
            if hasattr(window, '_open_module_windows'):
                return window
            window = window.parent() if hasattr(window, 'parent') else None
        return None

    def _show_sales_widget_for_conversion(self, sales_widget):
        """Display Sales Entry and retain references to avoid garbage collection."""
        from .standalone_window import StandaloneModuleWindow
        main_window = self._find_main_window_for_conversion()
        parent = main_window if main_window is not None else self.window()
        window = StandaloneModuleWindow(sales_widget, 'Sales Entry - From Quotation', parent)
        if main_window is not None:
            main_window._center_and_show_window(window)
        else:
            window.show()
        if not hasattr(self, '_converted_sales_windows'):
            self._converted_sales_windows = []
        self._converted_sales_windows.append(window)
        if main_window is not None and hasattr(main_window, '_open_module_windows'):
            sales_windows = [key for key in main_window._open_module_windows.keys() if key.startswith('sales_')]
            window_key = f'sales_{len(sales_windows) + 1}'
            main_window._open_module_windows[window_key] = window
            window.destroyed.connect(lambda _=None, key=window_key: main_window._open_module_windows.pop(key, None))
        window.show()
        window.raise_()
        window.activateWindow()
        return window

    def convert_to_sale_action(self):
        """Convert the current quotation draft into an editable Sales Entry bill."""
        party_details = self._current_quotation_party_details()
        quote_rows = self._extract_quotation_product_rows()
        if not quote_rows:
            QMessageBox.warning(self, 'Convert to Sale', 'Please add at least one valid product row before converting to sale.')
            return
        try:
            from .sales_entry import SalesEntryWidget
            sales_widget = SalesEntryWidget(self.db)
            if not hasattr(sales_widget, 'products_dict'):
                sales_widget.products_dict = {}
            if hasattr(sales_widget, 'clear_form'):
                sales_widget.clear_form()
            self._inject_party_details_into_sales(sales_widget, party_details)
            self._copy_quote_footer_adjustments_to_sales(sales_widget)
            stock_tick = getattr(sales_widget, 'check_stock_tick', None)
            original_stock_check = None
            if stock_tick is not None and hasattr(stock_tick, 'isChecked'):
                original_stock_check = stock_tick.isChecked()
                was_blocked = stock_tick.blockSignals(True)
                try:
                    stock_tick.setChecked(False)
                finally:
                    stock_tick.blockSignals(was_blocked)
            inserted_count = 0
            for row_data in quote_rows:
                if self._insert_sales_row_from_quotation(sales_widget, row_data):
                    inserted_count += 1
                QCoreApplication.processEvents()
            QCoreApplication.processEvents()
            if original_stock_check is not None:
                was_blocked = stock_tick.blockSignals(True)
                try:
                    stock_tick.setChecked(original_stock_check)
                finally:
                    stock_tick.blockSignals(was_blocked)
            if inserted_count == 0:
                QMessageBox.warning(self, 'Convert to Sale', 'No quotation product rows could be copied to Sales Entry.')
                return
            if hasattr(sales_widget, 'calculate_grand_totals'):
                sales_widget.calculate_grand_totals()
            elif hasattr(sales_widget, 'calculate_totals'):
                sales_widget.calculate_totals()
            self._show_sales_widget_for_conversion(sales_widget)
        except Exception as exc:
            QMessageBox.critical(self, 'Convert to Sale', f'Failed to open Sales Entry from quotation: {exc}')

    def convert_to_invoice(self):
        """Backward-compatible alias for older quotation conversion callers."""
        self.convert_to_sale_action()

    def clear_form(self):
        """Clear form for new quotation."""
        self._begin_entry_reset()
        try:
            self._set_quotation_new_mode()
            self.quotation_no_input.setText(self.get_next_quotation_no())
            self.date_input.setDate(QDate.currentDate())
            self.quotation_type_combo.setCurrentText('Standard')
            self.nature_combo.setCurrentText('Local')
            self.status_combo.setCurrentText('Pending')
            self.valid_until_input.setDate(QDate.currentDate().addDays(15))
            self.customer_name_input.clear()
            self.mobile_input.clear()
            self.gstin_input.clear()
            self.state_combo.setCurrentIndex(0)
            self.address_input.clear()
            self.narration_input.clear()
            if hasattr(self, 'barcode_input'):
                self.barcode_input.clear()
            self.product_input.clear()
            self.items_table.setRowCount(0)
            self.manually_selected_row = -1
            self.quotation_items = []
            self.sale_items = self.quotation_items
            self._row_discount_total = 0.0
            if hasattr(self, 'discount_input'):
                self.discount_input.setText('0.00')
            self.freight_input.setText('0.00')
            self._manual_round_off = False
            if hasattr(self, 'round_off_check'):
                self.round_off_check.setChecked(True)
            self.round_off_input.setText('0.00')
            self.calculate_totals()
        finally:
            self._end_entry_reset()

    def _install_entry_unsaved_guard(self) -> None:
        """Track edits so closing an entry page can prompt to save."""
        self._install_unsaved_guard(
            [
                self.quotation_no_input,
                self.customer_name_input,
                self.mobile_input,
                self.address_input,
                self.gstin_input,
                self.narration_input,
                self.date_input,
                self.valid_until_input if hasattr(self, 'valid_until_input') else None,
                self.quotation_type_combo if hasattr(self, 'quotation_type_combo') else None,
                self.nature_combo,
                self.status_combo if hasattr(self, 'status_combo') else None,
                self.state_combo,
                self.freight_input if hasattr(self, 'freight_input') else None,
            ],
            table=self.items_table,
        )

    def _capture_entry_snapshot(self) -> str:
        """Serialize quotation header and line items for unsaved-close detection."""
        import json

        items = []
        if hasattr(self, 'items_table'):
            for row in range(self.items_table.rowCount()):
                row_meta = self.sale_items[row] if row < len(self.sale_items) else {}

                def _cell_text(column: int) -> str:
                    item = self.items_table.item(row, column)
                    return item.text().strip() if item else ''

                items.append({
                    'product_id': row_meta.get('product_id'),
                    'name': _cell_text(1),
                    'qty': _cell_text(8),
                    'rate': _cell_text(7),
                    'disc': _cell_text(10),
                })
        payload = {
            'quotation_id': self.current_quotation_id,
            'quotation_no': self.quotation_no_input.text().strip() if hasattr(self, 'quotation_no_input') else '',
            'customer': self.customer_name_input.text().strip() if hasattr(self, 'customer_name_input') else '',
            'mobile': self.mobile_input.text().strip() if hasattr(self, 'mobile_input') else '',
            'address': self.address_input.text().strip() if hasattr(self, 'address_input') else '',
            'gstin': self.gstin_input.text().strip() if hasattr(self, 'gstin_input') else '',
            'narration': self.narration_input.text().strip() if hasattr(self, 'narration_input') else '',
            'quotation_type': self.quotation_type_combo.currentText().strip() if hasattr(self, 'quotation_type_combo') else '',
            'status': self.status_combo.currentText().strip() if hasattr(self, 'status_combo') else '',
            'nature': self.nature_combo.currentText().strip() if hasattr(self, 'nature_combo') else '',
            'state': self.state_combo.currentText().strip() if hasattr(self, 'state_combo') else '',
            'date': qdate_to_db(self.date_input.date()) if hasattr(self, 'date_input') else '',
            'valid_until': qdate_to_db(self.valid_until_input.date()) if hasattr(self, 'valid_until_input') else '',
            'freight': self.freight_input.text().strip() if hasattr(self, 'freight_input') else '',
            'items': items,
        }
        return json.dumps(payload, sort_keys=True, default=str)