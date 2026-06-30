"""
Sales Entry widget for the Accounting Desktop Application.
Manages sales invoice creation with compact desktop layout.
Refactored into modular structure for better maintainability.
"""
import json
import re
import sqlite3
import webbrowser
from urllib.parse import quote
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QDate, QEvent, QTimer, Signal, QCoreApplication, QSizeF
from PySide6.QtGui import QDoubleValidator, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from config import active_company_manager
from db import Database
from bizora_core.sales_logic import SalesLogic
from bizora_core.party_logic import PartyLogic
from bizora_core.product_logic import ProductLogic
from bizora_core.party_balance_engine import PartyBalanceEngine
from bizora_core.stock_logic import StockLogic
from bizora_core.print_engine import PrintEngine
from bizora_core.print_settings_logic import get_print_settings
try:
    from utils.a4_print_engine import configure_a4_printer_page, export_a4_pdf, generate_a4_html, print_a4_receipt
except ImportError:
    configure_a4_printer_page = None
    export_a4_pdf = None
    generate_a4_html = None
    print_a4_receipt = None
try:
    from utils.thermal_print_engine import generate_thermal_html, print_thermal_receipt
except ImportError:
    generate_thermal_html = None
    print_thermal_receipt = None
from .sales_entry_ui import SalesEntryUIMixin
from .sales_entry_delegate import SalesBillDelegate
from .sales_entry_helpers import ensure_row_items_initialized as _ensure_row_items_initialized, clear_product_linked_row_data
from .print_settings_dialog import build_invoice_wysiwyg_scene, is_thermal_print_settings, render_wysiwyg_scene_to_printer
from ui.sales_entry_calculations import calculate_totals as _calculate_totals, _write_totals_to_widgets, recalculate_row as _recalculate_row
from .sales_entry_popup import setup_party_completer
from . import theme
from .cash_tender_dialog import CashTenderDialog
from ui.party_display import party_display_name, party_matches_text, strip_party_display_code
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.table_header_utils import apply_adjustable_table_columns
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin, apply_standard_window_chrome
from ui.entry_voucher_mixin import EntryVoucherMixin
from bizora_core.settings_logic import confirm_before_delete_transaction, is_debug_mode_enabled

class TaxSummaryDialog(UiMemoryMixin, QDialog):
    """Quick GST-wise review popup for the current sales bill."""
    INTRASTATE_COLUMNS = ('GST%', 'Net Amt', 'CGST', 'SGST', 'Cess')
    INTERSTATE_COLUMNS = ('GST%', 'Net Amt', 'IGST', 'Cess')

    def __init__(self, tax_data, is_interstate=False, parent=None):
        """Initialize the dialog and populate it with grouped tax data."""
        super().__init__(parent)
        self.is_interstate = bool(is_interstate)
        self.columns = self.INTERSTATE_COLUMNS if self.is_interstate else self.INTRASTATE_COLUMNS
        self.setWindowTitle('Bill Tax Summary')
        self.setMinimumWidth(390 if self.is_interstate else 450)
        self.setModal(True)
        self.setStyleSheet(theme.entry_summary_dialog_style())
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)
        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self._populate_rows(tax_data)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        self._init_ui_memory()

    def _populate_rows(self, tax_data):
        """Write tax summary rows into the dialog table."""
        rows = sorted((tax_data or {}).items(), key=self._sort_key)
        self.table.setRowCount(len(rows))
        for row_index, (tax_key, values) in enumerate(rows):
            gst_rate = tax_key[0] if isinstance(tax_key, tuple) else tax_key
            if self.is_interstate:
                row_values = (self._format_rate(gst_rate), self._format_amount(values.get('taxable_value', 0.0)), self._format_amount(values.get('igst', 0.0)), self._format_amount(values.get('cess', 0.0)))
            else:
                row_values = (self._format_rate(gst_rate), self._format_amount(values.get('taxable_value', 0.0)), self._format_amount(values.get('cgst', 0.0)), self._format_amount(values.get('sgst', 0.0)), self._format_amount(values.get('cess', 0.0)))
            for col_index, value in enumerate(row_values):
                item = QTableWidgetItem(value)
                alignment = Qt.AlignmentFlag.AlignRight
                if col_index == 0:
                    alignment = Qt.AlignmentFlag.AlignCenter
                item.setTextAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_index, col_index, item)

    @staticmethod
    def _sort_key(summary_item):
        """Return a stable sort key for GST/cess grouped summary rows."""
        tax_key = summary_item[0]
        if isinstance(tax_key, tuple):
            return (float(tax_key[0] or 0.0), float(tax_key[1] or 0.0))
        return (float(tax_key or 0.0), 0.0)

    @staticmethod
    def _format_amount(value):
        """Format a numeric amount for display."""
        try:
            return f'{float(value or 0.0):.2f}'
        except (TypeError, ValueError):
            return '0.00'

    @staticmethod
    def _format_rate(value):
        """Format a GST rate without noisy trailing zeroes."""
        try:
            rate = float(value or 0.0)
        except (TypeError, ValueError):
            rate = 0.0
        return f'{rate:.2f}'.rstrip('0').rstrip('.') or '0'

class SalesEntryWidget(EntryVoucherMixin, UiMemoryMixin, SalesEntryUIMixin, QWidget):
    window_closed = Signal()
    voucher_type = "sales"
    voucher_number_attr = "invoice_no_input"

    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self.sales_logic = SalesLogic(self.db)
        self.party_logic = PartyLogic(self.db)
        self.product_logic = ProductLogic(self.db)
        self.balance_engine = PartyBalanceEngine(self.db)
        self.stock_logic = StockLogic(self.db)
        self.current_sale_id = None
        self.current_voucher_id = None
        self.sale_items = []
        self.products_data = []
        self.parties_data = []
        self._initial_load_done = False
        self._deferred_load_started = False
        self.last_barcode_filled_row = -1
        self.manually_selected_row = -1
        self._amt_recvd_user_edited = False
        self._suppress_amt_recvd_signal = False
        self.amount_received = 0.0
        self.balance = 0.0
        self.current_payment_mode = 'Cash'
        self._row_discount_total = 0.0
        self._sales_nav_ids = []
        self._update_confirmed = False
        self._invoice_dup_lock = False
        self._invoice_blink_on = False
        self._invoice_blink_timer = QTimer(self)
        self._invoice_blink_timer.setInterval(400)
        self._invoice_blink_timer.timeout.connect(self._toggle_invoice_blink)
        self._linked_sales_return_id = None
        self._linked_sales_return_amount = 0.0
        self._sales_return_window = None
        self._is_saving = False
        self._is_initializing = True
        self._is_loading = False
        self._composition_non_taxable_locked = False
        self.gst_state_codes = theme.GST_STATE_CODES
        self.setup_ui()
        self._configure_sales_entry_table()
        self._restore_stock_check_control()
        self._apply_non_taxable_company_lock()
        self._init_entry_voucher_state()
        self.clear_form()
        self._install_event_filters()
        self._wire_signals()
        self._install_entry_unsaved_guard()
        self._install_voucher_number_lookup()
        self._initialize_state()
        self._setup_customer_completer()
        self.items_table.cellChanged.connect(self.live_cell_qty_lock, type=Qt.QueuedConnection)
        self.items_table.itemChanged.connect(self.live_qty_validation, type=Qt.QueuedConnection)
        self._is_initializing = False
        QTimer.singleShot(100, self._start_deferred_load)
        self._init_ui_memory()

    def _yield_ui_events(self):
        """Keep Windows 10 painting responsive during deferred startup DB work."""
        QCoreApplication.processEvents()

    def billing_table_style(self):
        """Sales Entry grid style with full border highlight on editing cells."""
        return theme.sales_entry_table_style()

    def _configure_sales_entry_table(self):
        """Apply Sales Entry table headers and draggable default column widths."""
        if not hasattr(self, 'items_table'):
            return
        self.items_table.setColumnCount(14)
        self.items_table.setHorizontalHeaderLabels(['SL', 'Product', 'HSN', 'CGST (%)', 'SGST (%)', 'IGST (%)', 'CESS (%)', 'Rate', 'Qty', 'Gross', 'Disc', 'Net', 'Tax', 'Total'])
        header = self.items_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.items_table.setColumnWidth(0, 35)
        self.items_table.setColumnWidth(1, 250)
        self.items_table.setColumnWidth(2, 80)
        self.items_table.setColumnWidth(3, 88)
        self.items_table.setColumnWidth(4, 88)
        self.items_table.setColumnWidth(5, 88)
        self.items_table.setColumnWidth(6, 88)
        self.items_table.setColumnWidth(7, 70)
        self.items_table.setColumnWidth(8, 60)
        self.items_table.setColumnWidth(9, 80)
        self.items_table.setColumnWidth(10, 60)
        self.items_table.setColumnWidth(11, 80)
        self.items_table.setColumnWidth(12, 70)
        self.items_table.setColumnWidth(13, 80)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.items_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _restore_stock_check_control(self):
        """Restore Sales Entry-only option checkboxes without touching UI mixins."""
        if not hasattr(self, 'check_stock_tick'):
            from ui.checkbox_style import create_checkbox
            self.check_stock_tick = create_checkbox('Check Qty of Stock', variant='status')
            self.check_stock_tick.setChecked(True)
        if not hasattr(self, 'non_taxable_checkbox'):
            from ui.checkbox_style import create_checkbox
            self.non_taxable_checkbox = create_checkbox('Non-Taxable (Bill of Supply)', variant='status')
            self.non_taxable_checkbox.setToolTip('Bypass GST calculation and save/print this bill as Bill of Supply.')
        parent_layout = None
        if hasattr(self, 'divide_tax_tick') and self.divide_tax_tick.parentWidget():
            parent_layout = self.divide_tax_tick.parentWidget().layout()
        elif hasattr(self, 'items_table') and self.items_table.parentWidget() and self.items_table.parentWidget().layout():
            parent_layout = self.items_table.parentWidget().layout()
        if parent_layout is None:
            return
        if parent_layout.indexOf(self.check_stock_tick) < 0:
            insert_at = parent_layout.indexOf(self.divide_tax_tick) if hasattr(self, 'divide_tax_tick') else -1
            if insert_at < 0:
                parent_layout.addWidget(self.check_stock_tick)
            else:
                parent_layout.insertWidget(insert_at, self.check_stock_tick)
        if parent_layout.indexOf(self.non_taxable_checkbox) < 0:
            insert_at = parent_layout.indexOf(self.check_stock_tick) + 1
            if insert_at <= 0:
                insert_at = parent_layout.indexOf(self.divide_tax_tick) if hasattr(self, 'divide_tax_tick') else -1
            if insert_at < 0:
                parent_layout.addWidget(self.non_taxable_checkbox)
            else:
                parent_layout.insertWidget(insert_at, self.non_taxable_checkbox)

    def _fetch_active_company_gst_type(self):
        """Return the active company's GST type using strict company scope."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return ''
        company_id = active_company.get('id')
        if not company_id:
            return ''
        try:
            ph = self.db._get_placeholder()
            rows = self.db.execute_query(f'\n                SELECT gst_type\n                FROM companies\n                WHERE id = {ph}\n                ', (company_id,))
            if rows:
                return (rows[0].get('gst_type') or 'Regular').strip()
        except Exception as exc:
            print(f'Failed to fetch active company GST type: {exc}')
        return (active_company.get('gst_type') or 'Regular').strip()

    def _apply_non_taxable_company_lock(self):
        """Lock Bill of Supply mode for Composition companies."""
        if not hasattr(self, 'non_taxable_checkbox'):
            return
        gst_type = self._fetch_active_company_gst_type()
        is_composition = gst_type.lower() == 'composition'
        self._composition_non_taxable_locked = is_composition
        was_blocked = self.non_taxable_checkbox.blockSignals(True)
        try:
            self.non_taxable_checkbox.setChecked(is_composition)
            self.non_taxable_checkbox.setEnabled(not is_composition)
        finally:
            self.non_taxable_checkbox.blockSignals(was_blocked)

    def _start_deferred_load(self):
        """Load heavy party/product caches after the Sales window is visible using true lazy loading."""
        if self._initial_load_done or self._deferred_load_started:
            return
        self._deferred_load_started = True
        QTimer.singleShot(100, self._perform_deferred_load)

    def _perform_deferred_load(self):
        """Actually perform the heavy data loading."""
        try:
            self._yield_ui_events()
            self.load_parties()
            self._yield_ui_events()
            self.load_products()
            self._yield_ui_events()
            self.generate_invoice_number()
            self._yield_ui_events()
            self._setup_customer_completer()
            self._yield_ui_events()
            self._initial_load_done = True
            if hasattr(self, 'barcode_input'):
                self.barcode_input.setFocus()
        finally:
            self._deferred_load_started = False
            if not self._is_entry_edit_mode():
                self._finalize_entry_baseline()

    def _install_event_filters(self):
        """Install event filters for keyboard navigation and select-all-on-focus."""
        if hasattr(self, 'items_table'):
            self.items_table.viewport().installEventFilter(self)
        for field in ['customer_name_input', 'address_input', 'mobile_input', 'gstin_input', 'narration_input', 'barcode_input']:
            if hasattr(self, field):
                getattr(self, field).installEventFilter(self)
        if hasattr(self, 'state_combo'):
            self.state_combo.installEventFilter(self)
            if self.state_combo.lineEdit():
                self.state_combo.lineEdit().installEventFilter(self)
        if hasattr(self, 'discount_total_input'):
            self.discount_total_input.installEventFilter(self)
        for le in self.findChildren(QLineEdit):
            if not le.isReadOnly():
                le.installEventFilter(self)

    def _install_select_all_on_click(self, line_edit):
        original_mouse_press = line_edit.mousePressEvent

        def select_all_mouse_press(event):
            original_mouse_press(event)
            QTimer.singleShot(0, line_edit.selectAll)
        line_edit.mousePressEvent = select_all_mouse_press

    def _wire_signals(self):
        """Connect all Qt signals to their handlers."""
        if hasattr(self, 'nature_combo'):
            self.nature_combo.currentTextChanged.connect(self.on_nature_changed)
        if hasattr(self, 'form_of_sale_combo'):
            self.form_of_sale_combo.currentTextChanged.connect(self.on_form_of_sale_changed)
        if hasattr(self, 'check_stock_tick'):
            self.check_stock_tick.stateChanged.connect(self.on_check_stock_changed)
        if hasattr(self, 'non_taxable_checkbox'):
            self.non_taxable_checkbox.stateChanged.connect(self.on_non_taxable_changed)
        if hasattr(self, 'divide_tax_tick'):
            self.divide_tax_tick.stateChanged.connect(self.on_divide_tax_changed)
        if hasattr(self, 'invoice_checkbox'):
            self.invoice_checkbox.toggled.connect(self.on_invoice_checkbox_toggled)
        if hasattr(self, 'sales_type_combo'):
            self.sales_type_combo.currentTextChanged.connect(self.on_sales_type_changed)
        if hasattr(self, 'customer_name_input'):
            self.customer_name_input.textChanged.connect(self.on_party_name_changed)
        if hasattr(self, 'amount_receive_input'):
            self.amount_receive_input.textEdited.connect(self.on_amt_recvd_edited)
        if hasattr(self, 'product_input'):
            self.product_input.installEventFilter(self)
            self.product_input.returnPressed.connect(self.on_product_enter)
        if hasattr(self, 'narration_input'):
            self.narration_input.textChanged.connect(self.on_narration_changed)
        if hasattr(self, 'return_btn'):
            self.return_btn.clicked.connect(self.on_return_button_clicked)
        if hasattr(self, 'freight_input'):
            self.freight_input.textChanged.connect(self.calculate_totals)
        if hasattr(self, 'discount_total_input'):
            self.discount_total_input.textChanged.connect(self.on_footer_discount_changed)
            self._install_select_all_on_click(self.discount_total_input)
        if hasattr(self, 'invoice_no_input'):
            self.invoice_no_input.textChanged.connect(self.on_invoice_no_changed)
            app = QApplication.instance()
            if app is not None:
                app.focusChanged.connect(self._on_global_focus_changed)
        if hasattr(self, 'series_input'):
            self.series_input.textChanged.connect(self.generate_invoice_number)

    def _install_entry_unsaved_guard(self) -> None:
        """Track edits so closing an entry page can prompt to save."""
        self._install_unsaved_guard(
            [
                self.invoice_no_input,
                self.customer_name_input,
                self.mobile_input,
                self.address_input,
                self.gstin_input,
                self.narration_input,
                self.date_input,
                self.due_date_input,
                self.sales_type_combo,
                self.nature_combo,
                self.state_combo,
                self.freight_input if hasattr(self, 'freight_input') else None,
                self.discount_total_input if hasattr(self, 'discount_total_input') else None,
                self.amount_receive_input if hasattr(self, 'amount_receive_input') else None,
            ],
            table=self.items_table,
        )

    def _capture_entry_snapshot(self) -> str:
        """Serialize bill header and line items for unsaved-close detection."""
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
            'sale_id': self.current_sale_id,
            'invoice': self.invoice_no_input.text().strip() if hasattr(self, 'invoice_no_input') else '',
            'customer': self.customer_name_input.text().strip() if hasattr(self, 'customer_name_input') else '',
            'mobile': self.mobile_input.text().strip() if hasattr(self, 'mobile_input') else '',
            'address': self.address_input.text().strip() if hasattr(self, 'address_input') else '',
            'gstin': self.gstin_input.text().strip() if hasattr(self, 'gstin_input') else '',
            'narration': self.narration_input.text().strip() if hasattr(self, 'narration_input') else '',
            'salesman': self.salesman_combo.currentText().strip() if hasattr(self, 'salesman_combo') else '',
            'sales_type': self.sales_type_combo.currentText().strip() if hasattr(self, 'sales_type_combo') else '',
            'nature': self.nature_combo.currentText().strip() if hasattr(self, 'nature_combo') else '',
            'state': self.state_combo.currentText().strip() if hasattr(self, 'state_combo') else '',
            'series': self.series_input.text().strip() if hasattr(self, 'series_input') else '',
            'date': qdate_to_db(self.date_input.date()) if hasattr(self, 'date_input') else '',
            'due_date': qdate_to_db(self.due_date_input.date()) if hasattr(self, 'due_date_input') else '',
            'freight': self.freight_input.text().strip() if hasattr(self, 'freight_input') else '',
            'discount': self.discount_total_input.text().strip() if hasattr(self, 'discount_total_input') else '',
            'amount_received': self.amount_receive_input.text().strip() if hasattr(self, 'amount_receive_input') else '',
            'items': items,
        }
        return json.dumps(payload, sort_keys=True, default=str)

    def _initialize_state(self):
        """Set initial UI state after wiring signals."""
        self.load_salesmen_combo()
        self._sync_invoice_input_editable()
        self.update_footer_payment_fields()
        self._sync_print_ob_visibility()

    def load_salesmen_combo(self, selected_name: str | None=None) -> None:
        """Populate the salesman selector from the master table."""
        if not hasattr(self, 'salesman_combo'):
            return
        current_name = selected_name
        if current_name is None:
            current_name = self.salesman_combo.currentText().strip()
        self.salesman_combo.blockSignals(True)
        self.salesman_combo.clear()
        self.salesman_combo.addItem('')
        try:
            salesmen = self.db.get_salesmen() or []
            for row in salesmen:
                name = str(row.get('name') or '').strip()
                if name:
                    self.salesman_combo.addItem(name)
        except Exception as exc:
            print(f'Error loading salesmen: {exc}')
        if current_name:
            index = self.salesman_combo.findText(current_name, Qt.MatchFixedString)
            if index >= 0:
                self.salesman_combo.setCurrentIndex(index)
            else:
                self.salesman_combo.setCurrentIndex(0)
        else:
            self.salesman_combo.setCurrentIndex(0)
        self.salesman_combo.blockSignals(False)

    def add_new_salesman(self) -> None:
        """Add a salesman to the master table and select it on the bill."""
        name, accepted = QInputDialog.getText(self, 'Add Salesman', 'Enter Salesman Name:')
        cleaned_name = str(name or '').strip()
        if not accepted or not cleaned_name:
            return
        try:
            salesman_id = self.db.insert_salesman(cleaned_name)
            if salesman_id is None:
                QMessageBox.warning(self, 'Add Salesman', 'Could not save the salesman. Please try again.')
                return
        except Exception as exc:
            QMessageBox.warning(self, 'Add Salesman', f'Could not save the salesman:\n{exc}')
            return
        self.load_salesmen_combo(cleaned_name)

    def refresh_theme(self):
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(theme.entry_page_background_style())
        if hasattr(self, 'lbl_total_items'):
            colors = theme._theme_colors()
            self.lbl_total_items.setStyleSheet(f"\n                QLabel {{\n                    color: {colors['accent_label']};\n                    font-size: 13px;\n                    font-weight: bold;\n                    background: transparent;\n                    border: none;\n                }}\n            ")
        if hasattr(self, 'tax_summary_btn'):
            self.tax_summary_btn.setStyleSheet(theme.sales_primary_button_style())
        if hasattr(self, 'salesman_combo'):
            self.salesman_combo.setStyleSheet(self.compact_input_style())
        if hasattr(self, 'add_salesman_btn'):
            self.add_salesman_btn.setStyleSheet(self.modern_3d_icon_button_style())
        if hasattr(self, 'rate_refresh_btn'):
            self.rate_refresh_btn.setStyleSheet(self.modern_3d_icon_button_style())
        if hasattr(self, 'narration_input'):
            self.narration_input.setStyleSheet(self.compact_input_style())
        for date_edit_name in ('date_input', 'due_date_input'):
            date_edit = getattr(self, date_edit_name, None)
            if date_edit is not None and hasattr(self, 'apply_calendar_style'):
                self.apply_calendar_style(date_edit)
        if hasattr(self, 'items_table'):
            self.items_table.setStyleSheet(self.billing_table_style())
            if hasattr(self, 'update_stock_display_for_row'):
                self.update_stock_display_for_row(self.items_table.currentRow())

    def setup_ui(self):
        self.setStyleSheet(theme.entry_page_background_style())
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(3, 3, 3, 3)
        header_strip = self.build_page_header_strip()
        layout.addWidget(header_strip)
        invoice_strip = self.build_invoice_command_strip()
        layout.addWidget(invoice_strip)
        party_matrix = self.build_party_information_matrix()
        layout.addWidget(party_matrix)
        product_strip = self.build_product_entry_strip()
        layout.addWidget(product_strip)
        status_strip = self.build_status_options_strip()
        layout.addWidget(status_strip)
        table_zone = self.build_items_table_zone()
        layout.addWidget(table_zone, 1)
        bottom_zone = self.build_lower_control_panel()
        self._attach_total_items_label()
        self._attach_tax_summary_button()
        layout.addWidget(bottom_zone)
        try:
            from ui.financial_year_guard import apply_financial_year_guard_to_named_dates
            apply_financial_year_guard_to_named_dates(self, 'date_input', 'due_date_input')
        except Exception:
            pass

    def _attach_total_items_label(self):
        """Add the live total item count beside the grand-total footer display."""
        self.lbl_total_items = QLabel('Total Items: 0')
        colors = theme._theme_colors()
        self.lbl_total_items.setStyleSheet(f"\n            QLabel {{\n                color: {colors['accent_label']};\n                font-size: 13px;\n                font-weight: bold;\n                background: transparent;\n                border: none;\n            }}\n        ")
        self.lbl_total_items.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        grand_total_zone = None
        if hasattr(self, 'final_amount_display'):
            grand_total_zone = self.final_amount_display.parentWidget()
        grand_total_layout = grand_total_zone.layout() if grand_total_zone else None
        if grand_total_layout is not None:
            grand_total_layout.insertWidget(1, self.lbl_total_items, 0)

    def _attach_tax_summary_button(self):
        """Add a compact tax summary button inside the footer tax block."""
        if hasattr(self, 'tax_summary_btn'):
            return
        if not hasattr(self, 'net_value_display'):
            return
        tax_frame = self.net_value_display.parentWidget()
        tax_layout = tax_frame.layout() if tax_frame else None
        if tax_layout is None:
            return
        self.tax_summary_btn = QPushButton('Tax Summary')
        self.tax_summary_btn.setStyleSheet(theme.sales_primary_button_style())
        self.tax_summary_btn.setToolTip('Review GST-wise taxable and tax totals.')
        self.tax_summary_btn.setFixedHeight(24)
        self.tax_summary_btn.clicked.connect(self.show_tax_summary_dialog)
        insert_at = max(0, tax_layout.count() - 1)
        tax_layout.insertWidget(insert_at, self.tax_summary_btn)

    @staticmethod
    def _sale_type_text_is_interstate(value):
        """Return True only for explicit interstate sale type text."""
        normalized = str(value or '').strip().lower()
        if not normalized:
            return False
        compact = normalized.replace('-', '').replace('_', '').replace(' ', '')
        if 'intra' in compact or 'local' in compact:
            return False
        return 'interstate' in compact or 'inter' in compact

    def is_current_sale_interstate(self):
        """Return whether the active Sales Entry bill is interstate."""
        try:
            if hasattr(self, 'nature_combo'):
                nature_text = self.nature_combo.currentText()
                if nature_text:
                    return self._sale_type_text_is_interstate(nature_text)
            for combo_name in ('form_of_sale_combo', 'sales_type_combo'):
                if not hasattr(self, combo_name):
                    continue
                combo_text = getattr(self, combo_name).currentText()
                if self._sale_type_text_is_interstate(combo_text):
                    return True
        except Exception:
            return False
        return False

    def _row_tax_summary_rates(self, row):
        """Read explicit GST and cess rates for one bill row."""
        cgst_rate = self.safe_float_from_cell(row, 3, 0.0)
        sgst_rate = self.safe_float_from_cell(row, 4, 0.0)
        igst_rate = self.safe_float_from_cell(row, 5, 0.0)
        cess_rate = self.safe_float_from_cell(row, 6, 0.0)
        gst_rate = cgst_rate + sgst_rate + igst_rate
        if row < len(self.sale_items):
            row_meta = self.sale_items[row] or {}
            if gst_rate <= 0.0:
                gst_rate = self._safe_float(row_meta.get('gst_rate'), 0.0) or self._safe_float(row_meta.get('gst_percent'), 0.0) or self._safe_float(row_meta.get('tax_percent'), 0.0)
            if cess_rate <= 0.0:
                cess_rate = self._safe_float(row_meta.get('cess_rate'), 0.0) or self._safe_float(row_meta.get('cess_percent'), 0.0) or self._safe_float(row_meta.get('cess'), 0.0)
        return (max(0.0, round(gst_rate, 2)), max(0.0, round(cess_rate, 2)))

    def _build_current_tax_summary_data(self):
        """Build GST-wise taxable and split tax totals from the current grid."""
        tax_data = {}
        if not hasattr(self, 'items_table'):
            return tax_data
        is_non_taxable = bool(hasattr(self, 'non_taxable_checkbox') and self.non_taxable_checkbox.isChecked())
        for row in range(self.items_table.rowCount()):
            row_meta = self.sale_items[row] if row < len(self.sale_items) else {}
            product_id = (row_meta or {}).get('product_id')
            product_name = self.safe_item_text(row, 1, '').strip()
            qty = self.safe_float_from_cell(row, 8, 0.0)
            taxable_value = self.safe_float_from_cell(row, 11, 0.0)
            if taxable_value <= 0.0:
                gross_value = self.safe_float_from_cell(row, 9, 0.0)
                discount = self.safe_float_from_cell(row, 10, 0.0)
                taxable_value = max(0.0, gross_value - discount)
            if not product_id and (not product_name):
                continue
            if qty <= 0.0 and taxable_value <= 0.0:
                continue
            gst_rate = 0.0
            cess_rate = 0.0
            if not is_non_taxable:
                gst_rate, cess_rate = self._row_tax_summary_rates(row)
            base_gst_amount = taxable_value * (gst_rate / 100.0)
            cess_amount = taxable_value * (cess_rate / 100.0)
            cgst_amount = base_gst_amount / 2.0
            sgst_amount = base_gst_amount / 2.0
            igst_amount = base_gst_amount
            if row_meta:
                stored_cgst_amount = self._safe_float(row_meta.get('cgst_amount'), 0.0)
                stored_sgst_amount = self._safe_float(row_meta.get('sgst_amount'), 0.0)
                stored_igst_amount = self._safe_float(row_meta.get('igst_amount'), 0.0)
                stored_cess_amount = self._safe_float(row_meta.get('cess_amount'), 0.0)
                if stored_cgst_amount or stored_sgst_amount or stored_igst_amount or stored_cess_amount:
                    cgst_amount = stored_cgst_amount
                    sgst_amount = stored_sgst_amount
                    igst_amount = stored_igst_amount or stored_cgst_amount + stored_sgst_amount
                    base_gst_amount = stored_cgst_amount + stored_sgst_amount + stored_igst_amount
                    cess_amount = stored_cess_amount
            total_tax = base_gst_amount + cess_amount
            summary_row = tax_data.setdefault((round(gst_rate, 2), round(cess_rate, 2)), {'taxable_value': 0.0, 'cgst': 0.0, 'sgst': 0.0, 'igst': 0.0, 'cess': 0.0, 'total_tax': 0.0})
            summary_row['taxable_value'] += taxable_value
            summary_row['cgst'] += cgst_amount
            summary_row['sgst'] += sgst_amount
            summary_row['igst'] += igst_amount
            summary_row['cess'] += cess_amount
            summary_row['total_tax'] += total_tax
            QCoreApplication.processEvents()
        return tax_data

    def show_tax_summary_dialog(self):
        """Open the current bill's GST-wise tax summary dialog."""
        try:
            self.calculate_totals()
            tax_data = self._build_current_tax_summary_data()
            if not tax_data:
                QMessageBox.information(self, 'Bill Tax Summary', 'Please add at least one item to review tax summary.')
                return
            TaxSummaryDialog(tax_data, self.is_current_sale_interstate(), self).exec()
        except Exception as exc:
            QMessageBox.warning(self, 'Bill Tax Summary', f'Could not prepare tax summary:\n{exc}')

    def _calculate_total_item_count(self):
        """Return summed item quantities for all nonblank sales rows."""
        if not hasattr(self, 'items_table'):
            return 0.0
        total_items = 0.0
        for row in range(self.items_table.rowCount()):
            has_product = False
            if row < len(self.sale_items) and self.sale_items[row]:
                has_product = bool(self.sale_items[row].get('product_id'))
            if not has_product:
                has_product = bool(self.safe_item_text(row, 1, '').strip())
            if not has_product:
                continue
            qty_text = self.safe_item_text(row, 8, '').strip()
            total_items += self._safe_float(qty_text, 1.0 if not qty_text else 0.0)
        return total_items

    def _update_total_items_label(self):
        """Refresh the footer label with the current summed item quantity."""
        if not hasattr(self, 'lbl_total_items'):
            return
        total_items = self._calculate_total_item_count()
        if float(total_items).is_integer():
            total_text = str(int(total_items))
        else:
            total_text = f'{total_items:.3f}'.rstrip('0').rstrip('.')
        self.lbl_total_items.setText(f'Total Items: {total_text}')

    def calculate_totals(self):
        """Wrapper for imported calculate_totals function."""
        if self._is_loading:
            return
        if self._is_initializing:
            return
        is_cash_sale = False
        if hasattr(self, 'sales_type_combo'):
            sales_type = (self.sales_type_combo.currentText() or '').strip().lower()
            is_cash_sale = sales_type == 'cash'
        if is_cash_sale and (not self._suppress_amt_recvd_signal):
            self._amt_recvd_user_edited = False
            print('AUTO SYNC: Reset manual edit flag for cash sale totals change')
        totals = _calculate_totals(self)
        _write_totals_to_widgets(self, totals)
        self._update_total_items_label()
        self.update_return_adjustment_display()
        if hasattr(self, 'update_footer_payment_fields'):
            self.update_footer_payment_fields()
        return totals

    def recalculate_row(self, row, source_column=None, live_value=None):
        """Wrapper for imported recalculate_row function."""
        if not hasattr(self, 'items_table'):
            return
        was_blocked = self.items_table.blockSignals(True)
        self._skip_inline_row_totals = True
        try:
            _recalculate_row(self, row, source_column, live_value)
        finally:
            self._skip_inline_row_totals = False
            self.items_table.blockSignals(was_blocked)
        if not getattr(self, '_deferred_totals_pending', False):
            self._deferred_totals_pending = True
            QTimer.singleShot(0, self._run_deferred_totals)

    def _run_deferred_totals(self):
        self._deferred_totals_pending = False
        self.calculate_totals()

    def safe_item_text(self, row, col, default=''):
        """Get text from table item safely."""
        try:
            item = self.items_table.item(row, col)
            if item is None:
                return default
            return item.text() or default
        except Exception:
            return default

    def safe_float_from_cell(self, row, col, default=0.0):
        """Get float value from table cell safely."""
        try:
            item = self.items_table.item(row, col)
            if item is None:
                return default
            return self._safe_float(item.text(), default)
        except Exception:
            return default

    def ensure_row_items_initialized(self, row):
        """Wrapper for imported ensure_row_items_initialized function."""
        _ensure_row_items_initialized(self.items_table, row)

    def preload_van_items(self, items, source_van_load_id=None, source_van_return_id=None):
        """Pre-load items from a Van Entry or Van Return for conversion to Sales Bill.

        Args:
            items: list of dicts with keys:
                   product_id, name, qty, rate,
                   cgst, sgst, igst, cess (all optional tax fields)
            source_van_load_id:   ID of originating van_load (for narration)
            source_van_return_id: ID of originating van_return (for narration)
        """
        try:
            self.clear_form()
        except Exception:
            pass
        for item in items:
            product = {'id': item.get('product_id'), 'name': item.get('name', ''), 'barcode': item.get('barcode', ''), 'sale_price': float(item.get('rate', 0) or 0), 'purchase_rate': float(item.get('rate', 0) or 0), 'wholesale_rate': float(item.get('rate', 0) or 0), 'mrp': float(item.get('rate', 0) or 0), 'cgst': float(item.get('cgst', 0) or 0), 'sgst': float(item.get('sgst', 0) or 0), 'igst': float(item.get('igst', 0) or 0), 'cess': float(item.get('cess', 0) or 0), 'quantity': float(item.get('quantity', 0) or 0), 'hsn': item.get('hsn', '')}
            qty = float(item.get('qty', 1) or 1)
            rate = float(item.get('rate', 0) or 0)
            try:
                self.add_product_to_table(product, qty=qty, rate=rate)
            except Exception as e:
                print(f"[VAN→SALES] Failed to add item {product.get('name')}: {e}")
        try:
            if source_van_load_id:
                self.narration_input.setText(f'Converted from Van Entry #{source_van_load_id}')
            elif source_van_return_id:
                self.narration_input.setText(f'Converted from Van Return #{source_van_return_id}')
        except Exception:
            pass
        try:
            self.calculate_totals()
        except Exception:
            pass
        print(f'[VAN→SALES] Preloaded {len(items)} items (load_id={source_van_load_id}, return_id={source_van_return_id})')

    def load_parties(self):
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            result = self.party_logic.get_parties(active_company['id'])
            self._yield_ui_events()
            if result['success']:
                self.parties_data = [p for p in result['data'] if p.get('party_type') in ['Debitor', 'Both']]
                self._yield_ui_events()
        except Exception as e:
            print(f'Failed to load parties: {e}')

    def refresh_parties(self):
        """Refresh parties list from database - called after new party is saved."""
        self.load_parties()
        self._setup_customer_completer()

    def load_products(self):
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            result = self.product_logic.get_products(active_company['id'])
            self._yield_ui_events()
            if result['success']:
                self.products_data = result['data']
                self.products_dict = {p['id']: p for p in self.products_data}
                self._yield_ui_events()
                self.products_by_barcode = {}
                self.products_by_name_exact = {}
                for idx, p in enumerate(self.products_data):
                    bc = str(p.get('barcode', '')).strip()
                    if bc:
                        self.products_by_barcode[bc] = p
                    name_key = str(p.get('name', '')).strip().lower()
                    if name_key:
                        self.products_by_name_exact[name_key] = p
                    if idx % 50 == 0:
                        self._yield_ui_events()
            product_ids = [p['id'] for p in self.products_data if p.get('id')]
            self._yield_ui_events()
            balances = self.db.get_stock_balances_for_products(active_company['id'], product_ids)
            self._yield_ui_events()
            for idx, (product_id, new_stock) in enumerate(balances.items()):
                if product_id in self.products_dict:
                    self.products_dict[product_id]['quantity'] = new_stock
                for p in self.products_data:
                    if p.get('id') == product_id:
                        p['quantity'] = new_stock
                        break
                if idx % 50 == 0:
                    self._yield_ui_events()
        except Exception as e:
            print(f'Failed to update affected products stock: {e}')

    def on_gstin_changed(self, text):
        max_gstin_length = 15
        cursor_pos = self.gstin_input.cursorPosition()
        filtered_text = ''.join((char for char in text if char.isalnum()))
        filtered_text = filtered_text[:max_gstin_length]
        upper_text = filtered_text.upper()
        if upper_text != text:
            self.gstin_input.blockSignals(True)
            self.gstin_input.setText(upper_text)
            self.gstin_input.setCursorPosition(min(cursor_pos, len(upper_text)))
            self.gstin_input.blockSignals(False)
        if len(upper_text) >= 2 and upper_text[:2].isdigit():
            state_code = upper_text[:2]
            if state_code in self.gst_state_codes:
                expected_state = self.gst_state_codes[state_code]
                self.state_combo.blockSignals(True)
                self.state_combo.setCurrentText(expected_state)
                self.state_combo.blockSignals(False)
        else:
            self.state_combo.blockSignals(True)
            self.state_combo.setCurrentIndex(0)
            self.state_combo.blockSignals(False)

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

    def on_narration_changed(self, text):
        """Capitalize only the first narration character without changing the rest."""
        if not text:
            return
        new_text = text[0].upper() + text[1:]
        if new_text == text:
            return
        cursor_pos = self.narration_input.cursorPosition()
        self.narration_input.blockSignals(True)
        self.narration_input.setText(new_text)
        self.narration_input.setCursorPosition(min(cursor_pos, len(new_text)))
        self.narration_input.blockSignals(False)

    def on_customer_name_changed(self, text):
        """Handle customer name text change - apply title case formatting."""
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
            cursor_pos = self.customer_name_input.cursorPosition()
            self.customer_name_input.blockSignals(True)
            self.customer_name_input.setText(new_text)
            self.customer_name_input.setCursorPosition(min(cursor_pos, len(new_text)))
            self.customer_name_input.blockSignals(False)

    def _setup_customer_completer(self):
        """Set up party completer for customer name field."""
        if not hasattr(self, 'customer_name_input') or not hasattr(self, 'parties_data'):
            return
        setup_party_completer(self.customer_name_input, self, self.on_party_selected)

    def on_party_selected(self, model_idx, editor):
        """Handle party selection from completer popup."""
        party = model_idx.data(Qt.UserRole)
        if not party:
            return
        self._apply_party_to_customer_fields(party, editor)

    def _apply_party_to_customer_fields(self, party, editor=None):
        """Populate Sales Entry customer fields from a selected debtor party."""
        if not party:
            return
        target_editor = editor or self.customer_name_input
        target_editor.blockSignals(True)
        target_editor.setText(party.get('name', ''))
        target_editor.blockSignals(False)
        if hasattr(self, 'address_input'):
            self.address_input.blockSignals(True)
            self.address_input.setText(party.get('address', ''))
            self.address_input.blockSignals(False)
        if hasattr(self, 'mobile_input'):
            self.mobile_input.blockSignals(True)
            self.mobile_input.setText(party.get('mobile_number', ''))
            self.mobile_input.blockSignals(False)
        if hasattr(self, 'gstin_input'):
            self.gstin_input.blockSignals(True)
            self.gstin_input.setText(party.get('gstin', ''))
            self.gstin_input.blockSignals(False)
        self._mark_entry_dirty()
        self.update_footer_payment_fields()

    def _fetch_all_parties_for_popup(self):
        """Return the full party list (debtors + creditors) for the search popup.

        ``self.parties_data`` is intentionally filtered to Debitor/Both for the
        normal sales flow, so we re-query here to also expose Creditor parties
        when the user explicitly chooses to bill a creditor.
        """
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return list(getattr(self, 'parties_data', []) or [])
            result = self.party_logic.get_parties(active_company['id'])
            if result.get('success'):
                return list(result.get('data') or [])
        except Exception as exc:
            print(f'Failed to load parties for popup: {exc}')
        return list(getattr(self, 'parties_data', []) or [])

    def show_debtor_search_popup(self):
        """Open a modal party search popup from the Customer Name Tab shortcut.

        Includes a Debtors/Creditors switch so a sales bill can also be raised
        against a creditor party when required.
        """
        all_parties = self._fetch_all_parties_for_popup()
        popup = QDialog(self)
        popup.setWindowTitle('Select Party')
        popup.resize(620, 460)
        popup.setModal(True)
        apply_standard_window_chrome(popup)
        popup.setStyleSheet(theme.entry_picker_dialog_style())
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(16)
        debtor_radio = QRadioButton('Debtors')
        creditor_radio = QRadioButton('Creditors')
        debtor_radio.setChecked(True)
        mode_group = QButtonGroup(popup)
        mode_group.addButton(debtor_radio)
        mode_group.addButton(creditor_radio)
        toggle_row.addWidget(debtor_radio)
        toggle_row.addWidget(creditor_radio)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)
        title_label = QLabel('Search Debtor by name, code, or mobile')
        layout.addWidget(title_label)
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type debtor name / code / mobile...')
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
            """Return acceptable party_type values for the active toggle."""
            if creditor_radio.isChecked():
                return ('Creditor', 'Both')
            return ('Debitor', 'Both')

        def populate_rows(filter_text=''):
            visible_parties.clear()
            table.setRowCount(0)
            needle = (filter_text or '').strip().lower()
            allowed_types = current_mode_types()
            for party in all_parties:
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
            self._apply_party_to_customer_fields(party, self.customer_name_input)
            popup.accept()
            QTimer.singleShot(0, self.address_input.setFocus)

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
            """Refresh labels and table when switching Debtors/Creditors."""
            if creditor_radio.isChecked():
                popup.setWindowTitle('Select Creditor')
                title_label.setText('Search Creditor by name, code, or mobile')
                search_input.setPlaceholderText('Type creditor name / code / mobile...')
            else:
                popup.setWindowTitle('Select Debtor')
                title_label.setText('Search Debtor by name, code, or mobile')
                search_input.setPlaceholderText('Type debtor name / code / mobile...')
            populate_rows(search_input.text())
            search_input.setFocus()
        search_input.keyPressEvent = search_key_press
        table.keyPressEvent = table_key_press
        search_input.textChanged.connect(populate_rows)
        debtor_radio.toggled.connect(on_mode_changed)
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
        populate_rows(self.customer_name_input.text())
        QTimer.singleShot(0, lambda: (search_input.setFocus(), search_input.selectAll()))
        popup.exec()

    def on_address_changed(self, text):
        """Handle address text change - apply title case formatting."""
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
            cursor_pos = self.address_input.cursorPosition()
            self.address_input.blockSignals(True)
            self.address_input.setText(new_text)
            self.address_input.setCursorPosition(min(cursor_pos, len(new_text)))
            self.address_input.blockSignals(False)

    def on_divide_tax_changed(self, state):
        """Handle divide_tax_tick state change - recalculate all rows."""
        if not hasattr(self, 'items_table') or not hasattr(self, 'sale_items'):
            return
        if self.items_table.rowCount() == 0 or len(self.sale_items) == 0:
            return
        for row in range(self.items_table.rowCount()):
            if row < len(self.sale_items):
                self.recalculate_row(row)
        self.calculate_totals()

    def on_nature_changed(self, text):
        """Handle Nature change to activate/deactivate tax fields based on GST type."""
        if not text:
            return
        is_local = text == 'Local'
        self._auto_classify_form_of_sale()
        if hasattr(self, 'table_delegate'):
            self.table_delegate.is_local_tax = is_local
        for row in range(self.items_table.rowCount()):
            if row >= len(self.sale_items):
                continue
            product_id = self.sale_items[row].get('product_id')
            product = self.products_dict.get(product_id) if product_id else None
            cgst_val = 0
            sgst_val = 0
            igst_val = 0
            cess_val = 0
            if product:
                cgst_val = product.get('cgst', 0)
                sgst_val = product.get('sgst', 0)
                igst_val = product.get('igst', 0)
                cess_val = product.get('cess', 0)
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
            self.recalculate_row(row)
        self.calculate_totals()

    def on_form_of_sale_changed(self, text):
        """Handle Form of Sale dropdown change - user can override auto-classification."""
        pass

    def _auto_classify_form_of_sale(self):
        """Auto-classify form_of_sale based on GSTIN, state, and grand_total."""
        if not hasattr(self, 'form_of_sale_combo'):
            return
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            company_id = active_company['id']
            company_state = active_company.get('state', '')
            gstin = (self.gstin_input.text() or '').strip()
            customer_state = (self.state_combo.currentText() or '').strip()
            grand_total = self._safe_float((self.grand_total_label.text() or '').replace('Grand Total: ', '').strip(), 0.0)
            if gstin:
                self.form_of_sale_combo.setCurrentText('B2B')
            elif not gstin and customer_state and (customer_state != company_state) and (grand_total > 250000):
                self.form_of_sale_combo.setCurrentText('B2CL')
            else:
                self.form_of_sale_combo.setCurrentText('B2CS')
        except Exception:
            if hasattr(self, 'form_of_sale_combo'):
                self.form_of_sale_combo.setCurrentText('B2CS')

    def on_sales_type_changed(self, _text):
        """Type switched: reset manual-edit flag so defaults apply, then refresh."""
        self._amt_recvd_user_edited = False
        self.update_footer_payment_fields()
        self._sync_print_ob_visibility()

    def get_product_rate_from_selector(self, product):
        sales_rate_selection = self.rate_selector_combo.currentText()
        if sales_rate_selection == 'Sales Rate':
            return product.get('sale_price', 0)
        elif sales_rate_selection == 'Purchase Rate':
            return product.get('purchase_rate', 0)
        elif sales_rate_selection == 'Wholesale Rate':
            return product.get('wholesale_rate', 0)
        elif sales_rate_selection == 'MRP':
            return product.get('mrp', 0)
        else:
            return product.get('sale_price', 0)

    def on_check_stock_changed(self, state):
        """Refresh stock display when Sales Entry stock checking is toggled."""
        if not state:
            current_row = self.items_table.currentRow()
            self.update_stock_display_for_row(current_row)
            return
        self._trigger_stock_check_for_row(self.items_table.currentRow())

    def on_non_taxable_changed(self, _state):
        """Recalculate every row when Bill of Supply mode is toggled."""
        if not hasattr(self, 'items_table') or not hasattr(self, 'sale_items'):
            return
        for row in range(self.items_table.rowCount()):
            if row >= len(self.sale_items):
                continue
            if not self.non_taxable_checkbox.isChecked():
                self._restore_tax_cells_for_row(row)
            self.recalculate_row(row)
        self.calculate_totals()

    def _restore_tax_cells_for_row(self, row):
        """Restore product tax percentages for a row after leaving Bill of Supply mode."""
        if row < 0 or row >= len(self.sale_items):
            return
        row_meta = self.sale_items[row] or {}
        product_id = row_meta.get('product_id')
        product = self.products_dict.get(product_id) if product_id and hasattr(self, 'products_dict') else None
        if not product:
            return
        is_local = not hasattr(self, 'nature_combo') or self.nature_combo.currentText() == 'Local'
        cgst = float(product.get('cgst', 0) or 0)
        sgst = float(product.get('sgst', 0) or 0)
        igst = float(product.get('igst', 0) or 0)
        cess = float(product.get('cess', 0) or 0)
        was_blocked = self.items_table.blockSignals(True)
        try:
            values = {3: cgst if is_local else 0.0, 4: sgst if is_local else 0.0, 5: 0.0 if is_local else igst, 6: cess}
            for col, value in values.items():
                item = self.items_table.item(row, col)
                if item:
                    item.setText(f'{value:.2f}')
        finally:
            self.items_table.blockSignals(was_blocked)

    def find_row_by_barcode(self, barcode):
        """Find row index by barcode in the table."""
        for row in range(self.items_table.rowCount()):
            if row < len(self.sale_items):
                product_id = self.sale_items[row].get('product_id')
                if product_id:
                    product = self.products_dict.get(product_id)
                    if product and product.get('barcode') == barcode:
                        return row
        return -1

    def update_stock_display_for_row(self, row):
        """Update stock_display for a given row with real stock quantity."""
        if not hasattr(self, 'stock_display'):
            return
        if row < 0 or row >= len(self.sale_items):
            self.stock_display.setText('0.000')
            self.stock_display.setStyleSheet(theme.entry_stock_ok_style())
            return
        product_id = self.sale_items[row].get('product_id')
        if not product_id:
            self.stock_display.setText('0.000')
            self.stock_display.setStyleSheet(theme.entry_stock_ok_style())
            return
        product = self.products_dict.get(product_id)
        if not product:
            self.stock_display.setText('0.000')
            self.stock_display.setStyleSheet(theme.entry_stock_ok_style())
            return
        try:
            active_company = active_company_manager.get_active_company()
            if active_company:
                stock_qty = self.stock_logic.get_current_stock(active_company['id'], product_id)
            else:
                stock_qty = float(product.get('quantity', 0) or 0)
        except Exception:
            stock_qty = float(product.get('quantity', 0) or 0)
        self.stock_display.setText(str(f'{stock_qty:.3f}'))
        self.stock_display.setStyleSheet(theme.entry_stock_ok_style())

    def _product_id_for_row(self, row):
        if row < len(self.sale_items) and self.sale_items[row]:
            product_id = self.sale_items[row].get('product_id')
            if product_id:
                return product_id
        product_name = self.safe_item_text(row, 1, '').strip()
        if product_name:
            for product in self.products_data:
                if str(product.get('name', '')).strip().lower() == product_name.lower():
                    return product.get('id')
        return None

    def _available_stock_for_product(self, product_id):
        """Return live available stock for a product using parameterized SQL."""
        if not product_id:
            return 0.0
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return 0.0
            ph = self.db._get_placeholder()
            sale_exclusion = ''
            params = []
            if self.current_sale_id:
                sale_exclusion = f' AND NOT (sm.reference_type = {ph} AND sm.reference_id = {ph})'
                params.extend(['sale', self.current_sale_id])
            params.extend([active_company['id'], product_id])
            query = f'\n                SELECT\n                    COALESCE(SUM(sm.quantity), p.quantity, 0) AS current_stock\n                FROM products p\n                LEFT JOIN stock_movements sm\n                    ON sm.company_id = p.company_id\n                    AND sm.product_id = p.id\n                    {sale_exclusion}\n                WHERE p.company_id = {ph}\n                    AND p.id = {ph}\n                GROUP BY p.id, p.quantity\n            '
            result = self.db.execute_query(query, tuple(params))
            if result:
                return float(result[0]['current_stock'] or 0.0)
        except Exception:
            pass
        return 0.0

    def enforce_qty_stock_limit(self, row, requested_qty=None, editor=None, show_warning=True):
        """Clamp Sales Entry Qty to available stock when stock checking is enabled."""
        if not hasattr(self, 'check_stock_tick') or not self.check_stock_tick.isChecked():
            return False
        if row < 0 or row >= self.items_table.rowCount():
            return False
        product_id = self._product_id_for_row(row)
        if not product_id:
            return False
        if requested_qty is None:
            requested_qty = self._safe_float(self.items_table.item(row, 8).text() if self.items_table.item(row, 8) else '0', 0.0)
        stock_qty = max(0.0, self._available_stock_for_product(product_id))
        if requested_qty <= stock_qty:
            self.update_stock_display_for_row(row)
            return False
        allowed_text = '0.00'
        was_blocked = self.items_table.blockSignals(True)
        try:
            qty_item = self.items_table.item(row, 8)
            if qty_item:
                qty_item.setText(allowed_text)
            if editor is not None:
                editor.blockSignals(True)
                editor.setText(allowed_text)
                editor.selectAll()
                editor.blockSignals(False)
        finally:
            self.items_table.blockSignals(was_blocked)
        self.recalculate_row(row)
        self.calculate_totals()
        self.stock_display.setText(f'OUT OF STOCK ({stock_qty:.3f})')
        self.stock_display.setStyleSheet(theme.entry_stock_alert_style())
        self.items_table.setCurrentCell(row, 8)
        qty_item = self.items_table.item(row, 8)
        if qty_item:
            self.items_table.editItem(qty_item)
        if show_warning:
            QMessageBox.warning(self, 'Out of Stock', f'Out of Stock! Available balance is only: {stock_qty:.3f}. You cannot enter a quantity greater than available stock.')
            self.items_table.setCurrentCell(row, 8)
            if qty_item:
                self.items_table.editItem(qty_item)
        return True

    def live_qty_validation(self, item):
        if item is not None and item.column() == 8:
            QTimer.singleShot(0, lambda r=item.row(): self._trigger_stock_check_for_row(r))

    def live_cell_qty_lock(self, row, col):
        if col == 8:
            QTimer.singleShot(0, lambda r=row: self._trigger_stock_check_for_row(r))

    def _trigger_stock_check_for_row(self, row):
        if not hasattr(self, 'check_stock_tick') or not self.check_stock_tick.isChecked():
            self.calculate_totals()
            return False
        if row < 0 or row >= self.items_table.rowCount():
            return False
        qty = self._safe_float(self.items_table.item(row, 8).text() if self.items_table.item(row, 8) else '0', 0.0)
        return self.enforce_qty_stock_limit(row, qty, show_warning=True)

    def increment_row_qty(self, row):
        """Increment Qty of existing row by 1 and recalculate.

        Returns:
            True if stock check clamps the quantity, otherwise False.
        """
        if row < 0 or row >= self.items_table.rowCount():
            return False
        self.last_barcode_filled_row = row
        self.ensure_row_items_initialized(row)
        try:
            current_qty = self._safe_float(self.items_table.item(row, 8).text() if self.items_table.item(row, 8) else '0', 0.0)
            new_qty = current_qty + 1.0
            self.items_table.item(row, 8).setText(str(new_qty))
            self.recalculate_row(row)
            self.calculate_totals()
            return self._trigger_stock_check_for_row(row)
        except Exception:
            return False

    def add_product_to_table(self, product, qty=None, rate=None):
        """Add product to table, reusing blank row if available.

        Returns:
            Tuple (row, invalid_triggered), where invalid_triggered is True if stock check clamps Qty.
        """
        blank_row = self.find_blank_row()
        if blank_row >= 0:
            invalid_triggered = self.fill_blank_row_with_product(blank_row, product)
            return (blank_row, invalid_triggered)
        if qty is None:
            qty = 1.0
        if rate is None:
            rate = self.get_product_rate_from_selector(product)
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        self.last_barcode_filled_row = row
        for col in range(15):
            if self.items_table.item(row, col) is None:
                self.items_table.setItem(row, col, QTableWidgetItem(''))
        sl_item = self.items_table.item(row, 0)
        sl_item.setText(str(row + 1))
        sl_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        product_item = self.items_table.item(row, 1)
        product_item.setText(product['name'])
        product_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        hsn_item = self.items_table.item(row, 2)
        hsn_item.setText(product.get('hsn', ''))
        hsn_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        is_local = self.nature_combo.currentText() == 'Local'
        cgst_item = self.items_table.item(row, 3)
        cgst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        sgst_item = self.items_table.item(row, 4)
        sgst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        igst_item = self.items_table.item(row, 5)
        igst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        if is_local:
            cgst_item.setText(f"{product.get('cgst', 0):.2f}")
            sgst_item.setText(f"{product.get('sgst', 0):.2f}")
            igst_item.setText('0')
        else:
            cgst_item.setText('0')
            sgst_item.setText('0')
            igst_item.setText(f"{product.get('igst', 0):.2f}")
        cess_item = self.items_table.item(row, 6)
        cess_item.setText(str(product.get('cess', 0)))
        cess_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        rate_item = self.items_table.item(row, 7)
        rate_item.setText(str(rate))
        rate_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        qty_item = self.items_table.item(row, 8)
        qty_item.setText(str(qty))
        qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        gross_item = self.items_table.item(row, 9)
        gross_item.setText(str(rate))
        gross_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        discount_item = self.items_table.item(row, 10)
        discount_item.setText('0')
        discount_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        net_item = self.items_table.item(row, 11)
        net_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        tax_item = self.items_table.item(row, 12)
        tax_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        grand_total_item = self.items_table.item(row, 13)
        grand_total_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        tax_percent = product.get('cgst', 0) + product.get('sgst', 0) + product.get('igst', 0) + product.get('cess', 0)
        self.sale_items.append({'product_id': product['id'], 'hsn': product.get('hsn', ''), 'cgst': product.get('cgst', 0), 'sgst': product.get('sgst', 0), 'igst': product.get('igst', 0), 'cess': product.get('cess', 0), 'tax_percent': tax_percent, 'rate': rate})
        self.recalculate_row(row)
        self.calculate_totals()
        self.on_table_selection_changed()
        self._mark_entry_dirty()
        from PySide6.QtWidgets import QAbstractItemView
        filled_row_item = self.items_table.item(row, 0)
        if filled_row_item:
            self.items_table.scrollToItem(filled_row_item, QAbstractItemView.PositionAtCenter)
        return (row, self._trigger_stock_check_for_row(row))

    def _scroll_row_into_view(self, row: int) -> None:
        """Scroll a sales line so it is fully visible in the items table (F1 parity)."""
        if row < 0 or row >= self.items_table.rowCount():
            return
        from PySide6.QtWidgets import QAbstractItemView
        target_item = self.items_table.item(row, 0)
        if target_item:
            self.items_table.scrollToItem(target_item, QAbstractItemView.PositionAtCenter)

    def _schedule_scroll_row_into_view(self, row: int) -> None:
        """Defer scroll until row insert/layout completes after barcode scans."""
        if row < 0:
            return
        QTimer.singleShot(0, lambda target_row=row: self._scroll_row_into_view(target_row))

    def add_blank_row(self):
        """Add a blank row to the table for manual entry.

        If any unfilled row already exists, return it instead of creating a duplicate.
        """
        existing_blank = self.find_blank_row()
        if existing_blank >= 0:
            return existing_blank
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        was_blocked = self.items_table.blockSignals(True)
        try:
            for col in range(14):
                if self.items_table.item(row, col) is None:
                    self.items_table.setItem(row, col, QTableWidgetItem(''))
            sl_item = self.items_table.item(row, 0)
            sl_item.setText(str(row + 1))
            sl_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            product_item = self.items_table.item(row, 1)
            product_item.setText('')
            product_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            hsn_item = self.items_table.item(row, 2)
            hsn_item.setText('')
            hsn_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            cgst_item = self.items_table.item(row, 3)
            cgst_item.setText('')
            cgst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            sgst_item = self.items_table.item(row, 4)
            sgst_item.setText('')
            sgst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            igst_item = self.items_table.item(row, 5)
            igst_item.setText('')
            igst_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            cess_item = self.items_table.item(row, 6)
            cess_item.setText('')
            cess_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            rate_item = self.items_table.item(row, 7)
            rate_item.setText('')
            rate_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            qty_item = self.items_table.item(row, 8)
            qty_item.setText('')
            qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            gross_item = self.items_table.item(row, 9)
            gross_item.setText('')
            gross_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            discount_item = self.items_table.item(row, 10)
            discount_item.setText('')
            discount_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            net_item = self.items_table.item(row, 11)
            net_item.setText('')
            net_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            tax_item = self.items_table.item(row, 12)
            tax_item.setText('')
            tax_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            grand_total_item = self.items_table.item(row, 13)
            grand_total_item.setText('')
            grand_total_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.sale_items.append({'product_id': None, 'hsn': '', 'cgst': 0, 'sgst': 0, 'igst': 0, 'cess': 0, 'tax_percent': 0, 'rate': 0})
        finally:
            self.items_table.blockSignals(was_blocked)
        self.items_table.clearSelection()
        return row

    def is_last_row_blank(self):
        """Check if the last row in the table is blank (no product)."""
        if self.items_table.rowCount() == 0:
            return False
        last_row = self.items_table.rowCount() - 1
        if last_row >= len(self.sale_items):
            return False
        return self.sale_items[last_row]['product_id'] is None

    def find_blank_row(self):
        """Find the first blank row in the table. Returns row index or -1 if no blank row exists."""
        for row in range(self.items_table.rowCount()):
            if row < len(self.sale_items):
                if self.sale_items[row]['product_id'] is None:
                    return row
        return -1

    def _update_top_bar_for_product(self, product, barcode_or_code=None):
        """Refresh live status strip from product data after barcode scan or F1."""
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
        if hasattr(self, 'category_display'):
            self.category_display.setText(product.get('category', ''))
        if hasattr(self, 'size_display'):
            self.size_display.setText(product.get('size', ''))
        if hasattr(self, 'color_display'):
            self.color_display.setText(product.get('color', ''))
        active_company = active_company_manager.get_active_company()
        if active_company and hasattr(self, 'stock_display'):
            try:
                stock = self.stock_logic.get_current_stock(active_company['id'], product['id'])
            except Exception:
                stock = product.get('quantity', 0)
            self.stock_display.setText(str(stock) if stock is not None else '0')
            self.stock_display.setStyleSheet(theme.entry_stock_ok_style())

    def _reset_barcode_scan_cycle_state(self):
        """Clear stale F1/qty-edit flags so the next barcode scan starts fresh."""
        delegate = self.items_table.itemDelegate()
        if delegate and hasattr(delegate, 'qty_invalid'):
            delegate.qty_invalid = False
        self.manually_selected_row = -1

    def _ensure_blank_row_after_barcode_scan(self):
        """Keep one ready blank row after a successful barcode scan."""
        self.add_blank_row()

    def _complete_barcode_scan(self, product, code, *, invalid_triggered=False):
        """Clear barcode field, refresh status strip, and prepare the next scan row."""
        self.barcode_input.clear()
        if not invalid_triggered:
            self._ensure_blank_row_after_barcode_scan()
            self._schedule_scroll_row_into_view(self.last_barcode_filled_row)
        self.items_table.clearSelection()
        self.barcode_input.setFocus()
        self._update_top_bar_for_product(product, code)

    def on_barcode_enter(self):
        code = str(self.barcode_input.text()).strip()
        if code and self.current_sale_id and (not self._update_confirmed):
            reply = QMessageBox.question(self, 'Update Saved Bill?', 'This is a saved bill. Do you want to update it with new items?\n\nYes — switch to update mode and add items.\nNo — keep the bill unchanged.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                self.barcode_input.clear()
                self.barcode_input.setFocus()
                return
            self._update_confirmed = True
        if not code:
            self.product_input.setFocus()
            return
        if not self.products_data:
            self.load_products()
            if not self.products_data:
                QMessageBox.warning(self, 'No Products', 'No products loaded. Please add products first.')
                self.barcode_input.clear()
                self.barcode_input.setFocus()
                return
        product = None
        if self.barcode_tick.isChecked():
            product = self.products_by_barcode.get(code)
            if not product:
                product = self.products_by_name_exact.get(code.lower())
        else:
            product = self.products_by_barcode.get(code)
        if not product:
            QMessageBox.warning(self, 'Product Not Found', f'No product found: {code}')
            self.barcode_input.clear()
            self.barcode_input.setFocus()
            return
        self._reset_barcode_scan_cycle_state()
        self._update_top_bar_for_product(product, code)
        if self.manually_selected_row >= 0 and self.manually_selected_row < len(self.sale_items):
            target_row = self.manually_selected_row
            if self.sale_items[target_row]['product_id'] is not None:
                reply = QMessageBox.question(self, 'Replace Row', f'Do you want to replace row {target_row + 1}?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.Yes:
                    invalid_triggered = self.fill_blank_row_with_product(target_row, product)
                    self.manually_selected_row = -1
                    self._complete_barcode_scan(product, code, invalid_triggered=invalid_triggered)
                    return
                else:
                    self.manually_selected_row = -1
                    self.barcode_input.clear()
                    self.barcode_input.setFocus()
                    return
            else:
                invalid_triggered = self.fill_blank_row_with_product(target_row, product)
                self.manually_selected_row = -1
                self._complete_barcode_scan(product, code, invalid_triggered=invalid_triggered)
                return
        existing_row = self.find_row_by_barcode(product['barcode'])
        if existing_row >= 0:
            invalid_triggered = self.increment_row_qty(existing_row)
            self._complete_barcode_scan(product, code, invalid_triggered=invalid_triggered)
            return
        blank_row = self.find_blank_row()
        if blank_row >= 0:
            invalid_triggered = self.fill_blank_row_with_product(blank_row, product)
        else:
            _, invalid_triggered = self.add_product_to_table(product)
        self._complete_barcode_scan(product, code, invalid_triggered=invalid_triggered)

    def on_product_enter(self):
        """Handle product input Enter key - open product search popup."""
        self._popup_product_selected = False
        self.show_product_popup()

    def show_product_popup(self):
        """Show product search popup dialog (same pattern as sales return)."""
        from config import active_company_manager
        company_id = active_company_manager.get_active_company_id()
        if not company_id:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView
        from PySide6.QtCore import Qt, QTimer
        popup = QDialog(self)
        popup.setWindowTitle('Select Product')
        popup.resize(620, 440)
        apply_standard_window_chrome(popup)
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
        hint.setStyleSheet(f"color: {theme._theme_colors()['muted_text']}; font-size: 10px; background: transparent; border: none;")
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
                rate = float(product.get('sale_price') or product.get('mrp') or product.get('wholesale_rate') or product.get('purchase_rate') or 0)
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
            company_id2 = active_company_manager.get_active_company_id()
            full_product = self.db.get_product_by_id(company_id2, product_id) if company_id2 else None
            if full_product:
                product = full_product
                product['code'] = product.get('code') or product.get('item_code') or code_val
            else:
                product = {'id': product_id, 'name': product_name, 'rate': rate_val, 'code': code_val}
            self.product_input.blockSignals(True)
            self.product_input.setText(product_name)
            self.product_input.blockSignals(False)
            self.category_display.setText(str(product.get('category', '')))
            self.size_display.setText(str(product.get('size', '')))
            self.color_display.setText(str(product.get('color', '')))
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

        def key_press(event):
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                select_product()
            elif event.key() == Qt.Key_Escape:
                popup.reject()
            else:
                QDialog.keyPressEvent(popup, event)
        popup.keyPressEvent = key_press
        popup.exec()

    def add_product_from_popup(self, product):
        """Add product selected from popup to the items table."""
        added_row, invalid_triggered = self.add_product_to_table(product)
        if added_row >= 0:
            self.product_input.clear()
            self.calculate_totals()
            from .sales_entry_delegate import COL_QTY
            self.items_table.setCurrentCell(added_row, COL_QTY)
            qty_item = self.items_table.item(added_row, COL_QTY)
            if qty_item:
                self.items_table.editItem(qty_item)
            self._update_top_bar_for_product(product, product.get('code') or product.get('item_code') or product.get('barcode'))

    def on_return_button_clicked(self):
        """Handle Return button click - open Sales Return with current context."""
        if self._linked_sales_return_id is not None:
            reply = QMessageBox.question(self, 'Return Already Linked', f'This bill already has a linked return (#{self._linked_sales_return_id}).\n\nDo you want to:\n• YES = Create an additional return\n• NO = Cancel and keep existing return', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        grand_total = self.get_numeric_value(self.grand_total_input)
        customer_name = self.customer_name_input.text().strip()
        customer_id = None
        if customer_name and hasattr(self, 'parties_data'):
            for party in self.parties_data:
                if party_matches_text(party, customer_name):
                    customer_id = party.get('id')
                    break
        self.open_sales_return_window(sales_entry_widget=self, sales_grand_total=grand_total, customer_id=customer_id, customer_name=customer_name, original_invoice_no=self.invoice_no_input.text().strip() if hasattr(self, 'invoice_no_input') else None)

    def open_sales_return_window(self, sales_entry_widget, sales_grand_total, customer_id=None, customer_name=None, original_invoice_no=None):
        """Open Sales Return window with context from Sales Entry.

        Args:
            sales_entry_widget: Reference to this SalesEntryWidget instance
            sales_grand_total: Current grand total from Sales Entry
            customer_id: Optional customer/debtor ID
            customer_name: Optional customer name
            original_invoice_no: Optional original invoice number
        """
        from .sales_return import SalesReturnPageWidget
        from .standalone_window import StandaloneModuleWindow, _resolve_hub_window

        widget = SalesReturnPageWidget(main_window=None, db=self.db, opened_from_sales_entry=True, sales_entry_widget=sales_entry_widget, sales_grand_total=sales_grand_total)
        if customer_id and hasattr(widget, 'current_party_id'):
            widget.current_party_id = customer_id
            if hasattr(widget, 'party_name_input') and customer_name:
                widget.party_name_input.setText(customer_name)
                if hasattr(widget, 'populate_party_details'):
                    party_data = {'id': customer_id, 'name': customer_name}
                    widget.populate_party_details(party_data)
        self._sales_return_window = widget
        hub = _resolve_hub_window(self.window())
        window = StandaloneModuleWindow(
            widget,
            'Sales Return (from Sales Entry)',
            hub,
        )
        widget._on_sales_entry_save_callback = self.apply_sales_return_adjustment
        widget._sales_entry_window = self
        if hub is not None and hasattr(hub, '_center_and_show_window'):
            hub._center_and_show_window(window, fallback_size=(1100, 750))
        else:
            window.show()

    def apply_sales_return_adjustment(self, return_id, return_amount):
        """Apply sales return adjustment to this Sales Entry.

        Called when Sales Return is saved successfully.

        Args:
            return_id: The saved sales return ID
            return_amount: The total return amount
        """
        print(f'[DEBUG] apply_sales_return_adjustment called: return_id={return_id}, amount={return_amount}')
        self._linked_sales_return_id = return_id
        self._linked_sales_return_amount = float(return_amount) if return_amount else 0.0
        print(f'[DEBUG] Stored: _linked_sales_return_id={self._linked_sales_return_id}, _linked_sales_return_amount={self._linked_sales_return_amount}')
        self.update_return_adjustment_display()
        net_after = self.get_net_after_return()
        if net_after < 0:
            net_text = f'-₹ {abs(net_after):.2f}'
        else:
            net_text = f'₹ {net_after:.2f}'
        QMessageBox.information(self, 'Return Linked', f'Sales Return #{return_id} linked successfully.\nReturn Amount: ₹ {self._linked_sales_return_amount:.2f}\nNet After Return: {net_text}')

    def update_return_adjustment_display(self):
        """Update the return adjustment display zone."""
        print(f"[DEBUG] update_return_adjustment_display: has zone={hasattr(self, 'return_adj_zone')}, return_id={self._linked_sales_return_id}, amount={self._linked_sales_return_amount}")
        if not hasattr(self, 'return_adj_zone'):
            print('[DEBUG] No return_adj_zone found!')
            return
        if self._linked_sales_return_id is None:
            print('[DEBUG] Hiding return_adj_zone (no linked return)')
            self.return_adj_zone.setVisible(False)
            return
        print(f'[DEBUG] Showing return_adj_zone with amount={self._linked_sales_return_amount}')
        self.return_adj_zone.setVisible(True)
        self.return_adj_amount.setText(f'-{self._linked_sales_return_amount:.2f}')
        print(f'[DEBUG] Set return_adj_amount text to: -{self._linked_sales_return_amount:.2f}')
        net_after = self.get_net_after_return()
        if net_after < 0:
            self.net_after_return_amount.setText(f'-{abs(net_after):.2f}')
        else:
            self.net_after_return_amount.setText(f'{net_after:.2f}')

    def get_net_after_return(self):
        """Calculate net amount after return adjustment.
        
        Returns:
            Net amount. Can be negative if return > grand total.
        """
        grand_total = self.get_numeric_value(self.grand_total_input)
        if grand_total == 0.0 and hasattr(self, 'final_amount_display'):
            grand_total = self.get_numeric_value(self.final_amount_display)
        net = grand_total - self._linked_sales_return_amount
        return net

    def get_numeric_value(self, widget):
        """Get numeric value from a QLineEdit or QLabel."""
        try:
            if isinstance(widget, QLineEdit):
                text = widget.text().replace('₹', '').replace(',', '').strip()
            else:
                text = str(widget.text() if hasattr(widget, 'text') else widget).replace('₹', '').replace(',', '').strip()
            return float(text) if text else 0.0
        except (ValueError, TypeError):
            return 0.0

    def fill_blank_row_with_product(self, row, product):
        """Fill an existing blank row with product details.

        Returns:
            True if invalid stock warning was triggered (Qty editor is active and locked)
            False if no warning / valid state / no action
        """
        self.last_barcode_filled_row = row
        self.ensure_row_items_initialized(row)
        qty_item = self.items_table.item(row, 8)
        if qty_item:
            qty_item.setText('1')
        else:
            self.items_table.setItem(row, 8, QTableWidgetItem('1'))
        qty_item = self.items_table.item(row, 8)
        qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        rate = self.get_product_rate_from_selector(product)
        product_item = self.items_table.item(row, 1)
        if product_item:
            product_item.setText(product['name'])
        hsn_item = self.items_table.item(row, 2)
        if hsn_item:
            hsn_item.setText(product.get('hsn', ''))
        is_local = self.nature_combo.currentText() == 'Local'
        cgst_item = self.items_table.item(row, 3)
        if cgst_item:
            if is_local:
                cgst_item.setText(f"{product.get('cgst', 0):.2f}")
            else:
                cgst_item.setText('0')
        sgst_item = self.items_table.item(row, 4)
        if sgst_item:
            if is_local:
                sgst_item.setText(f"{product.get('sgst', 0):.2f}")
            else:
                sgst_item.setText('0')
        igst_item = self.items_table.item(row, 5)
        if igst_item:
            if is_local:
                igst_item.setText('0')
            else:
                igst_item.setText(f"{product.get('igst', 0):.2f}")
        cess_item = self.items_table.item(row, 6)
        if cess_item:
            cess_item.setText(str(product.get('cess', 0)))
        rate_item = self.items_table.item(row, 7)
        if rate_item:
            rate_item.setText(str(rate))
        gross_item = self.items_table.item(row, 9)
        if gross_item:
            gross_item.setText(str(rate))
        discount_item = self.items_table.item(row, 10)
        if discount_item:
            discount_item.setText('0')
        tax_percent = product.get('cgst', 0) + product.get('sgst', 0) + product.get('igst', 0) + product.get('cess', 0)
        if row < len(self.sale_items):
            self.sale_items[row]['product_id'] = product['id']
            self.sale_items[row]['hsn'] = product.get('hsn', '')
            self.sale_items[row]['cgst'] = product.get('cgst', 0)
            self.sale_items[row]['sgst'] = product.get('sgst', 0)
            self.sale_items[row]['igst'] = product.get('igst', 0)
            self.sale_items[row]['cess'] = product.get('cess', 0)
            self.sale_items[row]['tax_percent'] = tax_percent
            self.sale_items[row]['rate'] = rate
        self.recalculate_row(row)
        self.calculate_totals()
        self.on_table_selection_changed()
        self._mark_entry_dirty()
        self.items_table.clearSelection()
        from PySide6.QtWidgets import QAbstractItemView
        filled_row_item = self.items_table.item(row, 0)
        if filled_row_item:
            self.items_table.scrollToItem(filled_row_item, QAbstractItemView.PositionAtCenter)
        return self._trigger_stock_check_for_row(row)

    def on_rate_refresh_clicked(self):
        """Update all current rows with the selected rate type."""
        rate_selection = self.rate_selector_combo.currentText()
        was_blocked = self.items_table.blockSignals(True)
        try:
            for row in range(self.items_table.rowCount()):
                if row < len(self.sale_items):
                    product_id = self.sale_items[row].get('product_id')
                    product = self.products_dict.get(product_id) if product_id else None
                    if product:
                        if rate_selection == 'Sales Rate':
                            new_rate = product.get('sale_price', 0)
                        elif rate_selection == 'Purchase Rate':
                            new_rate = product.get('purchase_rate', 0)
                        elif rate_selection == 'Wholesale Rate':
                            new_rate = product.get('wholesale_rate', 0)
                        elif rate_selection == 'MRP':
                            new_rate = product.get('mrp', 0)
                        else:
                            new_rate = product.get('sale_price', 0)
                        rate_item = self.items_table.item(row, 7)
                        if rate_item:
                            rate_item.setText(str(new_rate))
                        else:
                            self.items_table.setItem(row, 7, QTableWidgetItem(str(new_rate)))
                        self.sale_items[row]['rate'] = new_rate
                        self.recalculate_row(row)
            self.calculate_totals()
        finally:
            self.items_table.blockSignals(was_blocked)

    def _refresh_sales_nav_list(self, company_id):
        """Refresh cached list of saved sale ids for prev/next navigation.

        Ordered by id ascending (i.e. chronological insertion order).
        """
        try:
            sales = self.db.get_sales_by_company(company_id) or []
            self._sales_nav_ids = sorted([s['id'] for s in sales if s.get('id') is not None])
        except Exception:
            self._sales_nav_ids = []

    def previous_bill(self):
        self._navigate_bill(-1)

    def next_bill(self):
        """Open a fresh bill with the next sequential invoice number."""
        self.open_next_numbered_entry()

    def _navigate_bill(self, delta):
        """Move one bill in the given direction (-1 previous, +1 next)."""
        active = active_company_manager.get_active_company()
        if not active:
            QMessageBox.warning(self, 'No Active Company', 'Please open a company first.')
            return
        self._refresh_sales_nav_list(active['id'])
        if not getattr(self, '_sales_nav_ids', []):
            QMessageBox.information(self, 'No Bills', 'No saved bills are available yet.')
            return
        if self.current_sale_id in self._sales_nav_ids:
            idx = self._sales_nav_ids.index(self.current_sale_id)
        else:
            if delta > 0:
                QMessageBox.information(self, 'Next Bill', 'You are already on a new blank bill. Save it first, then Next will take you further.')
                return
            idx = len(self._sales_nav_ids)
        new_idx = idx + delta
        if new_idx < 0:
            QMessageBox.information(self, 'Previous Bill', 'This is the first bill.')
            return
        if new_idx >= len(self._sales_nav_ids):
            self.clear_form()
            try:
                next_inv = self._generate_unique_invoice_number(active['id'])
                self.invoice_no_input.setText(next_inv)
            except Exception:
                pass
            self._sync_invoice_input_editable()
            return
        self.load_sale_by_id(self._sales_nav_ids[new_idx])

    def load_sale_by_id(self, sale_id):
        """Load and display a saved sale by its id with one final totals pass."""
        checkbox_signal_state = None
        table_signal_state = None
        previous_loading = getattr(self, '_is_loading', False)
        previous_initializing = getattr(self, '_is_initializing', False)
        fields_to_block = []
        load_completed = False
        sale_columns = ['id', 'invoice_number', 'invoice_date', 'party_id', 'party_name', 'mobile_number', 'address', 'gstin', 'sales_type', 'bill_series', 'nature', 'due_date', 'address', 'gstin', 'state', 'sales_rate', 'narration', 'salesman', 'form_of_sale', 'sub_total', 'discount_total', 'tax_total', 'round_off', 'grand_total', 'amount_received', 'payment_mode', 'status']
        item_columns = ['id', 'sale_id', 'product_id', 'product_name', 'barcode', 'sl_no', 'hsn', 'tax_percent', 'unit', 'rate', 'quantity', 'gross_value', 'discount', 'net_value', 'tax_amount', 'grand_total', 'cgst', 'sgst', 'igst', 'cess', 'cgst_amount', 'sgst_amount', 'igst_amount', 'cess_amount']

        def _value(record, key, default=None, columns=None):
            """Safely read fields from dicts, sqlite rows, objects, or tuples."""
            if record is None:
                return default
            try:
                if hasattr(record, 'get'):
                    return record.get(key, default)
            except (AttributeError, KeyError, IndexError, TypeError):
                pass
            try:
                return record[key]
            except (KeyError, IndexError, TypeError):
                pass
            if columns and isinstance(record, (list, tuple)) and (key in columns):
                idx = columns.index(key)
                if idx < len(record):
                    return record[idx]
            try:
                return getattr(record, key)
            except (AttributeError, TypeError):
                return default

        def _float_value(record, key, default=0.0, columns=None):
            """Safely parse numeric saved values without breaking old bills."""
            try:
                return float(_value(record, key, default, columns) or default)
            except (TypeError, ValueError):
                return float(default)
        try:
            if hasattr(self, 'non_taxable_checkbox'):
                checkbox_signal_state = self.non_taxable_checkbox.blockSignals(True)
            if hasattr(self, 'items_table'):
                table_signal_state = self.items_table.blockSignals(True)
            active = active_company_manager.get_active_company()
            if not active:
                return
            self._is_loading = True
            self._is_initializing = True
            sale = self.db.get_sale_by_id(active['id'], sale_id)
            if not sale:
                QMessageBox.warning(self, 'Load Bill', 'Could not load the selected bill.')
                return
            items = self.db.get_sale_items(sale_id) or []
            fields_to_block = [getattr(self, 'freight_input', None), getattr(self, 'discount_total_input', None), getattr(self, 'round_off_input', None), getattr(self, 'amount_receive_input', None)]
            for w in fields_to_block:
                if w is not None:
                    w.blockSignals(True)
            try:
                self.current_sale_id = _value(sale, 'id', sale_id, sale_columns)
                self.current_voucher_id = self.current_sale_id
                self.invoice_no_input.setText(_value(sale, 'invoice_number', '', sale_columns) or '')
                if hasattr(self, 'invoice_checkbox'):
                    self.invoice_checkbox.setChecked(True)
                inv_date = _value(sale, 'invoice_date', None, sale_columns)
                if inv_date:
                    qd = QDate.fromString(str(inv_date)[:10], 'yyyy-MM-dd')
                    if qd.isValid():
                        self.date_input.setDate(qd)
                sales_type = _value(sale, 'sales_type', 'Tax Invoice', sale_columns) or 'Tax Invoice'
                db_to_ui = {'Sales': 'Cash', 'Tax Invoice': 'Cash', 'Credit Sales': 'Credit', 'Return': 'Return', 'Bill of Supply': 'Cash'}
                ui_type = db_to_ui.get(str(sales_type).strip(), 'Cash')
                i = self.sales_type_combo.findText(ui_type, Qt.MatchFixedString)
                if i >= 0:
                    self.sales_type_combo.setCurrentIndex(i)
                if hasattr(self, 'non_taxable_checkbox'):
                    is_bill_of_supply = str(sales_type).strip().lower() == 'bill of supply'
                    should_check = bool(self._composition_non_taxable_locked or is_bill_of_supply)
                    self.non_taxable_checkbox.setChecked(should_check)
                    self.non_taxable_checkbox.setEnabled(not self._composition_non_taxable_locked)
                self.customer_name_input.setText(_value(sale, 'party_name', '', sale_columns) or '')
                if hasattr(self, 'salesman_combo'):
                    salesman_name = _value(sale, 'salesman', '', sale_columns) or ''
                    self.load_salesmen_combo(salesman_name)
                if hasattr(self, 'series_input'):
                    self.series_input.setText(_value(sale, 'bill_series', '', sale_columns) or '')
                nature = _value(sale, 'nature', '', sale_columns) or ''
                i = self.nature_combo.findText(nature, Qt.MatchFixedString)
                if i >= 0:
                    self.nature_combo.setCurrentIndex(i)
                due = _value(sale, 'due_date', None, sale_columns)
                if due:
                    qd = QDate.fromString(str(due)[:10], 'yyyy-MM-dd')
                    if qd.isValid():
                        self.due_date_input.setDate(qd)
                self.address_input.setText(_value(sale, 'address', '', sale_columns) or '')
                self.gstin_input.setText(_value(sale, 'gstin', '', sale_columns) or '')
                state = _value(sale, 'state', '', sale_columns) or ''
                i = self.state_combo.findText(state, Qt.MatchFixedString)
                if i >= 0:
                    self.state_combo.setCurrentIndex(i)
                if hasattr(self, 'rate_selector_combo'):
                    sr = _value(sale, 'sales_rate', 'Sales Rate', sale_columns) or 'Sales Rate'
                    i = self.rate_selector_combo.findText(sr, Qt.MatchFixedString)
                    if i >= 0:
                        self.rate_selector_combo.setCurrentIndex(i)
                if hasattr(self, 'form_of_sale_combo'):
                    fos = _value(sale, 'form_of_sale', 'B2CS', sale_columns) or 'B2CS'
                    i = self.form_of_sale_combo.findText(fos, Qt.MatchFixedString)
                    if i >= 0:
                        self.form_of_sale_combo.setCurrentIndex(i)
                    else:
                        self.form_of_sale_combo.setCurrentText('B2CS')
                if hasattr(self, 'narration_input'):
                    self.narration_input.setText(_value(sale, 'narration', '', sale_columns) or '')
                self.current_payment_mode = (_value(sale, 'payment_mode', 'Cash', sale_columns) or 'Cash').strip() or 'Cash'
                if hasattr(self, 'amount_receive_input'):
                    saved_amt = _float_value(sale, 'amount_received', 0.0, sale_columns)
                    self.amount_receive_input.setText(f'{saved_amt:.2f}')
                    self._amt_recvd_user_edited = True
                self.items_table.setRowCount(0)
                self.sale_items = []
                for it in items:
                    row = self.items_table.rowCount()
                    self.items_table.insertRow(row)

                    def _set(c, v):
                        self.items_table.setItem(row, c, QTableWidgetItem(str(v)))
                    _set(0, row + 1)
                    _set(1, _value(it, 'product_name', '', item_columns) or '')
                    _set(2, _value(it, 'hsn', '', item_columns) or '')
                    cgst = _float_value(it, 'cgst', 0.0, item_columns)
                    sgst = _float_value(it, 'sgst', 0.0, item_columns)
                    igst = _float_value(it, 'igst', 0.0, item_columns)
                    cess = _float_value(it, 'cess', 0.0, item_columns)
                    tax_percent = _float_value(it, 'tax_percent', 0.0, item_columns)
                    if cgst == 0 and sgst == 0 and (igst == 0) and (tax_percent > 0):
                        if nature == 'Inter-state':
                            igst = tax_percent
                            cgst = 0
                            sgst = 0
                        else:
                            cgst = tax_percent / 2
                            sgst = tax_percent / 2
                            igst = 0
                    _set(3, f'{cgst:.2f}')
                    _set(4, f'{sgst:.2f}')
                    _set(5, f'{igst:.2f}')
                    _set(6, f'{cess:.2f}')
                    _set(7, f"{_float_value(it, 'rate', 0.0, item_columns):.2f}")
                    _set(8, f"{_float_value(it, 'quantity', 0.0, item_columns):.3f}")
                    _set(9, f"{_float_value(it, 'gross_value', 0.0, item_columns):.2f}")
                    _set(10, f"{_float_value(it, 'discount', 0.0, item_columns):.2f}")
                    _set(11, f"{_float_value(it, 'net_value', 0.0, item_columns):.2f}")
                    _set(12, f"{_float_value(it, 'tax_amount', 0.0, item_columns):.2f}")
                    _set(13, f"{_float_value(it, 'grand_total', 0.0, item_columns):.2f}")
                    self.sale_items.append({'product_id': _value(it, 'product_id', None, item_columns), 'hsn': _value(it, 'hsn', '', item_columns) or '', 'tax_percent': tax_percent, 'cgst': cgst, 'sgst': sgst, 'igst': igst, 'cess': cess, 'cgst_amount': _float_value(it, 'cgst_amount', 0.0, item_columns), 'sgst_amount': _float_value(it, 'sgst_amount', 0.0, item_columns), 'igst_amount': _float_value(it, 'igst_amount', 0.0, item_columns), 'cess_amount': _float_value(it, 'cess_amount', 0.0, item_columns), 'rate': _float_value(it, 'rate', 0.0, item_columns)})
                    QCoreApplication.processEvents()
                sub = _float_value(sale, 'sub_total', 0.0, sale_columns)
                disc = _float_value(sale, 'discount_total', 0.0, sale_columns)
                tax = _float_value(sale, 'tax_total', 0.0, sale_columns)
                rnd = _float_value(sale, 'round_off', 0.0, sale_columns)
                gt = _float_value(sale, 'grand_total', 0.0, sale_columns)
                self._row_discount_total = 0.0
                self.sub_total_input.setText(f'{sub:.2f}')
                if hasattr(self, 'freight_input'):
                    self.freight_input.setText('0.00')
                self.discount_total_input.setText(f'{disc:.2f}')
                if hasattr(self, 'discount_percent_label'):
                    self.discount_percent_label.setText('')
                self.tax_total_input.setText(f'{tax:.2f}')
                self.round_off_input.setText(f'{rnd:.2f}')
                self.grand_total_input.setText(f'{gt:.2f}')
                if hasattr(self, 'net_value_display'):
                    self.net_value_display.setText(f'{sub:.2f}')
                if hasattr(self, 'tax_amount_display'):
                    self.tax_amount_display.setText(f'{tax:.2f}')
                if hasattr(self, 'net_amount_input'):
                    self.net_amount_input.setText(f'{gt + rnd:.2f}')
                if hasattr(self, 'final_amount_display'):
                    self.final_amount_display.setText(f'{gt:.2f}')
                cgst_total = 0.0
                sgst_total = 0.0
                igst_total = 0.0
                cess_total = 0.0
                for it in items:
                    cgst_total += _float_value(it, 'cgst_amount', 0.0, item_columns)
                    sgst_total += _float_value(it, 'sgst_amount', 0.0, item_columns)
                    igst_total += _float_value(it, 'igst_amount', 0.0, item_columns)
                    cess_total += _float_value(it, 'cess_amount', 0.0, item_columns)
                if hasattr(self, 'cgst_display'):
                    self.cgst_display.setText(f'{cgst_total:.2f}')
                if hasattr(self, 'sgst_display'):
                    self.sgst_display.setText(f'{sgst_total:.2f}')
                if hasattr(self, 'igst_display'):
                    self.igst_display.setText(f'{igst_total:.2f}')
                if hasattr(self, 'cess_display'):
                    self.cess_display.setText(f'{cess_total:.2f}')
                if hasattr(self, 'update_footer_payment_fields'):
                    try:
                        self.update_footer_payment_fields()
                    except Exception:
                        pass
                self._update_ok_button_label()
                self._update_confirmed = False
                load_completed = True
            except Exception as e:
                print(f'Error loading: {e}')
                raise
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f'Error loading: {e}')
            print('[SalesEntry.load_sale_by_id] EXCEPTION:\n' + tb)
            QMessageBox.critical(self, 'Load Bill', f'Failed to load bill: {type(e).__name__}: {e}\n\n(Details have been printed to the console.)')
        finally:
            for w in fields_to_block:
                if w is not None:
                    w.blockSignals(False)
            self._is_initializing = previous_initializing
            self._is_loading = previous_loading
            if table_signal_state is not None and hasattr(self, 'items_table'):
                self.items_table.blockSignals(False)
            if checkbox_signal_state is not None and hasattr(self, 'non_taxable_checkbox'):
                self.non_taxable_checkbox.blockSignals(False)
        if load_completed:
            self._schedule_entry_baseline_finalize()

    def load_voucher(self, voucher_id: int):
        """
        Standardized voucher loading method for Ledger drill-down.
        
        This method provides a consistent interface for loading vouchers from the Ledger page.
        It sets the current_voucher_id AND current_sale_id for consistency.
        
        Args:
            voucher_id: The sale ID to load
        """
        self.current_voucher_id = voucher_id
        self.current_sale_id = voucher_id
        self.load_sale_by_id(voucher_id)

    def _update_ok_button_label(self):
        """Set OK button text to 'Update' when editing a saved bill, 'OK' otherwise."""
        if hasattr(self, 'ok_btn'):
            self.ok_btn.setText('Update' if self.current_sale_id else 'OK')

    def _is_debug_calculation_enabled(self) -> bool:
        """Return whether verbose sales calculation logging is enabled."""
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return False
            return is_debug_mode_enabled(self.db, active_company['id'])
        except Exception:
            return False

    def _sync_invoice_input_editable(self):
        """The invoice-no input is ALWAYS editable so the user can freely
        correct or delete what they typed (especially when a duplicate
        warning is shown). The 'Entry with Specific Invoice No.' checkbox
        only changes the placeholder and decides — at save time — whether
        to use the user's typed value or an auto-generated one.
        """
        if not hasattr(self, 'invoice_no_input') or not hasattr(self, 'invoice_checkbox'):
            return
        self.invoice_no_input.setReadOnly(False)
        if self.invoice_checkbox.isChecked():
            self.invoice_no_input.setPlaceholderText('Enter invoice no.')
        else:
            self.invoice_no_input.setPlaceholderText('Auto')

    def on_invoice_no_changed(self, _text):
        """Live check: if the currently-typed invoice number already exists
        for another bill in the active company, show an inline red warning
        next to the field and flag the input with a red border.

        The warning is suppressed when the field is empty or when the value
        belongs to the currently loaded saved bill (so no false alarm while
        simply viewing an existing bill).
        """
        if not hasattr(self, 'invoice_no_input'):
            return
        text = self.invoice_no_input.text().strip()

        def _set_valid_style():
            try:
                self.invoice_no_input.setStyleSheet(self.compact_input_style())
            except Exception:
                self.invoice_no_input.setStyleSheet('')
            if hasattr(self, 'invoice_warning_label'):
                self.invoice_warning_label.setVisible(False)
                self.invoice_warning_label.setText('')
        if not text:
            _set_valid_style()
            return
        active = active_company_manager.get_active_company()
        if not active:
            _set_valid_style()
            return
        try:
            exists = self.db.invoice_number_exists(active['id'], text, exclude_sale_id=self.current_sale_id)
        except Exception:
            exists = False
        if exists:
            self._invoice_dup_lock = True
            warn_msg = '⚠ Invoice No already exists — change it or click Reset'
            self.invoice_no_input.setToolTip(warn_msg)
            try:
                pos = self.invoice_no_input.mapToGlobal(self.invoice_no_input.rect().bottomLeft())
                QToolTip.showText(pos, warn_msg, self.invoice_no_input)
            except Exception:
                pass
            if not self.invoice_no_input.hasFocus():
                self.invoice_no_input.setFocus()
            self._invoice_blink_on = False
            self._toggle_invoice_blink()
            if not self._invoice_blink_timer.isActive():
                self._invoice_blink_timer.start()
        else:
            _set_valid_style()
            self.invoice_no_input.setToolTip('')
            try:
                QToolTip.hideText()
            except Exception:
                pass
            self._invoice_dup_lock = False
            if self._invoice_blink_timer.isActive():
                self._invoice_blink_timer.stop()
            self._invoice_blink_on = False

    def _toggle_invoice_blink(self):
        """Alternate the invoice field between a strong red and a subdued red
        to produce a visible blinking effect while the duplicate lock is on.
        """
        if not hasattr(self, 'invoice_no_input'):
            return
        try:
            base = self.compact_input_style() or ''
        except Exception:
            base = ''
        self._invoice_blink_on = not self._invoice_blink_on
        if theme._is_light_theme():
            if self._invoice_blink_on:
                style = base + '\nQLineEdit { border: 2px solid #C62828; background: #FFCDD2; color: #B71C1C; font-weight: bold; }'
            else:
                style = base + '\nQLineEdit { border: 2px solid #C62828; background: #FFF5F5; color: #C62828; font-weight: bold; }'
        elif self._invoice_blink_on:
            style = base + '\nQLineEdit { border: 2px solid #ff0000; background: #ff4d4f; color: #ffffff; font-weight: bold; }'
        else:
            style = base + '\nQLineEdit { border: 2px solid #ff0000; background: #1e293b; color: #ff0000; font-weight: bold; }'
        self.invoice_no_input.setStyleSheet(style)

    def _on_global_focus_changed(self, old, new):
        """If a duplicate invoice number is unresolved, keep focus glued to
        the invoice field. The user can only escape by typing a different
        (unique) number or by clicking Reset.
        """
        if not getattr(self, '_invoice_dup_lock', False):
            return
        if not hasattr(self, 'invoice_no_input'):
            return
        if new is None:
            return
        if new is self.invoice_no_input:
            return
        QTimer.singleShot(0, self.invoice_no_input.setFocus)

    def on_invoice_checkbox_toggled(self, _checked):
        """Handler for the specific-invoice-no checkbox.

        - Toggles read-only state on the invoice no input.
        - If the user just turned the checkbox OFF, clears any typed value and
          auto-generates the next invoice number (mirrors Purchase Entry behavior).
        """
        self._sync_invoice_input_editable()
        if hasattr(self, 'invoice_checkbox') and (not self.invoice_checkbox.isChecked()):
            if hasattr(self, 'invoice_no_input') and (not self.current_sale_id):
                self.invoice_no_input.clear()
                self.generate_invoice_number()

    def on_table_selection_changed(self):
        current_row = self.items_table.currentRow()
        if self.manually_selected_row == -1:
            self.items_table.clearSelection()
            return
        if current_row >= 0 and current_row < len(self.sale_items):
            product_id = self.sale_items[current_row].get('product_id')
            product = self.products_dict.get(product_id) if product_id else None
            if product:
                if hasattr(self, 'code_display'):
                    self.code_display.setText(product.get('barcode', ''))
                if hasattr(self, 'category_display'):
                    self.category_display.setText(product.get('category', ''))
                if hasattr(self, 'size_display'):
                    self.size_display.setText(product.get('size', ''))
                if hasattr(self, 'color_display'):
                    self.color_display.setText(product.get('color', ''))
                self.update_stock_display_for_row(current_row)

    def eventFilter(self, obj, event):
        """Event filter to capture mouse press events and keyboard events on party section fields."""
        if isinstance(obj, QLineEdit) and event.type() == QEvent.FocusIn:
            if not obj.isReadOnly():
                QTimer.singleShot(0, obj.selectAll)
        if hasattr(self, 'discount_total_input') and obj == self.discount_total_input and (event.type() == QEvent.KeyPress) and (event.key() == Qt.Key_Down):
            self.apply_discount_percent_mode()
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
                        self.items_table.viewport().update()
                        if clicked_row >= 0 and clicked_row < len(self.sale_items):
                            product_id = self.sale_items[clicked_row].get('product_id')
                            product = self.products_dict.get(product_id) if product_id else None
                            if product:
                                if hasattr(self, 'code_display'):
                                    self.code_display.setText(product.get('barcode', ''))
                                if hasattr(self, 'category_display'):
                                    self.category_display.setText(product.get('category', ''))
                                if hasattr(self, 'size_display'):
                                    self.size_display.setText(product.get('size', ''))
                                if hasattr(self, 'color_display'):
                                    self.color_display.setText(product.get('color', ''))
                                self.update_stock_display_for_row(clicked_row)
                        return True
                    else:
                        self.manually_selected_row = -1
                        self.items_table.clearSelection()
                        self.items_table.viewport().update()
                        if clicked_row >= 0 and clicked_row < len(self.sale_items):
                            product_id = self.sale_items[clicked_row].get('product_id')
                            product = self.products_dict.get(product_id) if product_id else None
                            if product:
                                if hasattr(self, 'code_display'):
                                    self.code_display.setText(product.get('barcode', ''))
                                if hasattr(self, 'category_display'):
                                    self.category_display.setText(product.get('category', ''))
                                if hasattr(self, 'size_display'):
                                    self.size_display.setText(product.get('size', ''))
                                if hasattr(self, 'color_display'):
                                    self.color_display.setText(product.get('color', ''))
                                self.update_stock_display_for_row(clicked_row)
                        self.items_table.editItem(item)
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
        if event.type() == QEvent.KeyPress and hasattr(self, 'customer_name_input') and (obj == self.customer_name_input) and (event.key() == Qt.Key_Tab):
            QTimer.singleShot(0, self.show_debtor_search_popup)
            return True
        if event.type() == QEvent.KeyPress and (event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter):
            if obj == self.customer_name_input:
                if hasattr(self, 'address_input'):
                    self.address_input.setFocus()
                return True
            elif obj == self.address_input:
                if hasattr(self, 'mobile_input'):
                    self.mobile_input.setFocus()
                return True
            elif obj == self.mobile_input:
                if hasattr(self, 'gstin_input'):
                    self.gstin_input.setFocus()
                return True
            elif obj == self.gstin_input:
                if hasattr(self, 'state_combo'):
                    self.state_combo.setFocus()
                return True
            elif obj == self.state_combo or (hasattr(self, 'state_combo') and obj == self.state_combo.lineEdit()):
                if hasattr(self, 'narration_input'):
                    self.narration_input.setFocus()
                return True
            elif obj == self.narration_input:
                if hasattr(self, 'barcode_input'):
                    self.barcode_input.setFocus()
                return True
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            if obj == self.narration_input:
                if hasattr(self, 'state_combo'):
                    self.state_combo.setFocus()
                return True
            elif obj == self.state_combo or (hasattr(self, 'state_combo') and obj == self.state_combo.lineEdit()):
                if hasattr(self, 'gstin_input'):
                    self.gstin_input.setFocus()
                return True
            elif obj == self.gstin_input:
                if hasattr(self, 'mobile_input'):
                    self.mobile_input.setFocus()
                return True
            elif obj == self.mobile_input:
                if hasattr(self, 'address_input'):
                    self.address_input.setFocus()
                return True
            elif obj == self.address_input:
                if hasattr(self, 'customer_name_input'):
                    self.customer_name_input.setFocus()
                return True
        return super().eventFilter(obj, event)

    def on_table_cell_changed(self, row, column):
        if hasattr(self, 'table_delegate') and self.table_delegate:
            if not self.table_delegate.editor_initialized:
                return
        if column in [3, 4, 5, 6, 7, 8, 9, 10]:
            if hasattr(self, 'table_delegate') and self.table_delegate:
                if self.table_delegate.current_editor is not None and self.table_delegate.current_index is not None and (self.table_delegate.current_index.row() == row) and (self.table_delegate.current_index.column() == column):
                    return
            live_text = self.safe_item_text(row, column, '0')
            self.recalculate_row(row, source_column=column, live_value=live_text)
            self.calculate_totals()

    def delete_row(self):
        current_row = self.items_table.currentRow()
        if current_row >= 0:
            self.items_table.removeRow(current_row)
            if 0 <= current_row < len(self.sale_items):
                del self.sale_items[current_row]
            self.manually_selected_row = -1
            for row in range(self.items_table.rowCount()):
                sl_item = QTableWidgetItem(str(row + 1))
                self.items_table.setItem(row, 0, sl_item)
            self.calculate_totals()
            self._mark_entry_dirty()

    def _generate_and_open_invoice_pdf(self, bill_no=None):
        bill_no = (bill_no or self.invoice_no_input.text()).strip()
        if not bill_no:
            QMessageBox.warning(self, 'Print Invoice', 'Please save or load a bill before printing.')
            return None
        try:
            from utils.invoice_printer import generate_invoice_pdf
            pdf_path = generate_invoice_pdf(bill_no, db=self.db, open_pdf=True)
            return pdf_path
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Could not generate invoice PDF:\n{exc}')
            return None

    def _clean_mobile_for_share(self, raw_mobile: str) -> str:
        """Strip non-digits and prefix India country code when 10 digits are entered."""
        digits = re.sub('\\D', '', raw_mobile or '')
        if len(digits) < 10:
            return ''
        if len(digits) == 10:
            return f'91{digits}'
        return digits

    def share_bill(self, platform: str):
        """
        Open WhatsApp (wa.me) or SMS (sms:) with a pre-filled bill summary.

        Uses OS deep links only — no paid messaging SDKs.
        """
        try:
            customer_name = ''
            if hasattr(self, 'customer_name_input'):
                customer_name = self.customer_name_input.text().strip()
            if not customer_name:
                customer_name = 'Customer'
            mobile_raw = ''
            if hasattr(self, 'mobile_input'):
                mobile_raw = self.mobile_input.text().strip()
            clean_mobile = self._clean_mobile_for_share(mobile_raw)
            if not clean_mobile:
                QMessageBox.warning(self, 'Share Bill', 'Please enter a valid customer mobile number (at least 10 digits) before sharing.')
                return
            bill_no = ''
            if hasattr(self, 'invoice_no_input'):
                bill_no = self.invoice_no_input.text().strip() or '—'
            grand_total = self._safe_float(self.grand_total_input.text() if hasattr(self, 'grand_total_input') else 0.0, 0.0)
            amount_paid = self._safe_float(self.amount_receive_input.text() if hasattr(self, 'amount_receive_input') else 0.0, 0.0)
            balance = self._safe_float(self.balance_display.text() if hasattr(self, 'balance_display') else max(0.0, grand_total - amount_paid), max(0.0, grand_total - amount_paid))
            company = active_company_manager.get_active_company()
            business_name = 'Faizan Pro Accounting'
            if company:
                business_name = company.get('business_name') or company.get('name') or business_name
            message = f'Hello {customer_name}, your bill (No: {bill_no}) at {business_name} is ready.\nTotal Amount: Rs. {grand_total:.2f}\nAmount Paid: Rs. {amount_paid:.2f}\nBalance: Rs. {balance:.2f}\nThank you for your business!'
            encoded_msg = quote(message)
            platform_key = (platform or '').strip().lower()
            if platform_key == 'whatsapp':
                url = f'https://wa.me/{clean_mobile}?text={encoded_msg}'
            elif platform_key == 'sms':
                url = f'sms:{clean_mobile}?body={encoded_msg}'
            else:
                QMessageBox.warning(self, 'Share Bill', f'Unknown sharing platform: {platform}')
                return
            webbrowser.open(url)
        except Exception as exc:
            QMessageBox.warning(self, 'Share Bill', f'Could not open {platform} sharing link:\n{exc}')

    def print_invoice(self, invoice_id=None):
        """Silently print the current saved sales invoice using saved settings."""
        sales_type = ''
        if hasattr(self, 'sales_type_combo'):
            sales_type = (self.sales_type_combo.currentText() or '').strip().lower()
        is_credit = sales_type == 'credit'
        include_ob = bool(is_credit and hasattr(self, 'print_ob_checkbox') and self.print_ob_checkbox.isChecked())
        self._print_include_ob = include_ob
        target_invoice_id = invoice_id or getattr(self, 'current_sale_id', None) or getattr(self, 'current_voucher_id', None)
        if not target_invoice_id:
            QMessageBox.warning(self, 'Print Invoice', 'Please save the bill first or load an existing bill to print.')
            return
        active_company = active_company_manager.get_active_company()
        company_id = active_company.get('id') if active_company else None
        if not company_id:
            QMessageBox.warning(self, 'No Active Company', 'Please open a company first.')
            return
        try:
            settings = get_print_settings(self.db, company_id)
            self._silent_print_saved_sales_receipt(company_id, target_invoice_id, settings)
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Could not print invoice:\n{exc}')

    def _resolve_default_print_mode(self, settings):
        """Return the saved global default print mode for Sales Entry."""
        try:
            metadata = self._print_settings_metadata(settings)
            default_mode = settings.get('default_print_mode', 'Thermal Receipt')
            if not str(default_mode or '').strip():
                default_mode = 'Thermal Receipt'
            metadata_mode = metadata.get('default_print_mode')
            has_direct_mode = 'default_print_mode' in settings and str(settings.get('default_print_mode') or '').strip()
            if not has_direct_mode and str(metadata_mode or '').strip():
                default_mode = metadata_mode
            has_saved_default = bool(str(settings.get('default_print_mode', '') or '').strip() or str(metadata_mode or '').strip())
            normalized_mode = str(default_mode or '').strip()
            if normalized_mode in {'Thermal Receipt', 'A4/A5 Invoice'}:
                return normalized_mode
            mode_key = normalized_mode.lower().replace('-', '_').replace(' ', '_')
            if mode_key in {'a4/a5_invoice', 'a4_a5_invoice', 'a4_invoice', 'a5_invoice', 'a4', 'a5'}:
                return 'A4/A5 Invoice'
            if mode_key in {'thermal_receipt', 'thermal', 'receipt', 'roll', '80mm', '58mm'}:
                return 'Thermal Receipt'
            if not has_saved_default and self._should_print_a4_invoice(settings):
                return 'A4/A5 Invoice'
        except Exception as exc:
            print(f'Failed to resolve default print mode: {exc}')
        return 'Thermal Receipt'

    def _print_saved_invoice_with_wysiwyg(self, target_invoice_id, company_id, settings):
        """Print a saved invoice through the configured thermal/WYSIWYG path."""
        try:
            format_label = settings.get('default_format', 'A4')
            printer_type = settings.get('printer_type', '') or ''
            paper_size = settings.get('paper_size', '') or format_label
            thermal = is_thermal_print_settings(settings)
            printer_name = self._saved_printer_name(settings, 'thermal_printer_name' if thermal else 'normal_printer_name')
            available_printers = self._available_printer_names()
            selected_printer_name = printer_name if printer_name in available_printers else ''
            print_engine = PrintEngine(self.db)
            invoice_data = print_engine.fetch_invoice_data(company_id, target_invoice_id)
            if not invoice_data:
                QMessageBox.warning(self, 'Print Invoice', 'Could not fetch invoice data for the selected bill.')
                return
            self._apply_live_payment_values_to_print_data(invoice_data)
            wysiwyg_scene = build_invoice_wysiwyg_scene(settings, invoice_data, self)
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            if selected_printer_name:
                printer.setPrinterName(selected_printer_name)
            if not thermal:
                self._configure_invoice_printer_page(printer, printer_type, paper_size, format_label)
            render_wysiwyg_scene_to_printer(wysiwyg_scene['scene'], printer, thermal, wysiwyg_scene['content_items'], wysiwyg_scene['paper_rect_item'])
            QMessageBox.information(self, 'Print Invoice', f"Invoice sent to printer '{selected_printer_name}'." if selected_printer_name else 'Invoice sent to the default printer.')
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Could not print invoice:\n{exc}')

    def _should_print_a4_invoice(self, settings):
        """Return True when saved print settings explicitly target A4 output."""
        try:
            metadata = self._print_settings_metadata(settings)
            explicit_mode = self._print_output_mode(settings, metadata)
            if explicit_mode == 'a4':
                return True
            if explicit_mode == 'thermal':
                return False
            if is_thermal_print_settings(settings):
                return False
            settings_found = str(settings.get('_print_settings_found', '1') or '').strip()
            if settings_found == '0' and (not metadata):
                return False
            metadata_paper_size = str(metadata.get('a4_paper_size') or settings.get('a4_paper_size') or '').strip().lower()
            if metadata_paper_size in {'a4', 'a5'}:
                return True
            format_label = (settings.get('default_format', '') or '').strip().lower()
            paper_size = (settings.get('paper_size', '') or '').strip().lower()
            return format_label in {'a4', 'a5', 'a3'} or paper_size in {'a4', 'a5', 'a3'}
        except Exception as exc:
            print(f'Failed to resolve print output mode: {exc}')
            return False

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

    def _print_theme_name(self, settings, keys, default_theme):
        """Return the active print theme from saved metadata or flat settings."""
        settings = settings or {}
        metadata = self._print_settings_metadata(settings)
        for key in keys:
            value = str(metadata.get(key) or settings.get(key) or '').strip()
            if value:
                return value
        return default_theme

    def _a4_theme_name(self, settings):
        """Return the active A4 invoice theme."""
        a4_theme_names = {'GST Standard', 'Modern Clean', 'Elegant Serif', 'Compact Wholesale', 'Bold Corporate', 'Bill of Supply', 'Color Block Header', 'Vibrant Accent', 'Modern Gradient'}
        settings = settings or {}
        metadata = self._print_settings_metadata(settings)
        for key in ('a4_theme', 'default_theme', 'theme'):
            value = str(metadata.get(key) or settings.get(key) or '').strip()
            if value in a4_theme_names:
                return value
        return 'GST Standard'

    def _thermal_theme_name(self, settings):
        """Return the active thermal receipt theme."""
        return self._print_theme_name(settings, ('thermal_theme', 'theme', 'default_theme'), 'Classic POS')

    def _print_output_mode(self, settings, metadata):
        """Return explicit saved output mode, or an empty string when absent."""
        for key in ('default_print_mode', 'print_output_mode', 'output_mode', 'print_mode', 'invoice_print_mode'):
            value = settings.get(key) or metadata.get(key)
            mode = str(value or '').strip().lower().replace('-', '_').replace(' ', '_')
            if mode in {'a4', 'a5', 'a4/a5_invoice', 'a4_a5_invoice', 'a4_invoice', 'a5_invoice', 'regular', 'regular_a4', 'full_size'}:
                return 'a4'
            if mode in {'thermal', 'thermal_receipt', 'receipt', 'roll', '80mm', '58mm'}:
                return 'thermal'
        return ''

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

    def _print_a4_invoice_from_current_bill(self, active_company, settings=None):
        """Generate the current Sales Entry A4 bill and open preview first."""
        if generate_a4_html is None:
            QMessageBox.critical(self, 'Print Invoice', 'A4 print engine is not available. Please verify a4_print_engine.py.')
            return
        try:
            if not active_company or not active_company.get('id'):
                QMessageBox.warning(self, 'Print Invoice', 'Please open a company first.')
                return
            self.calculate_totals()
            bill_type = self._resolve_a4_bill_type(active_company)
            cart_data = self._build_a4_cart_data(bill_type)
            if not cart_data:
                QMessageBox.warning(self, 'Print Invoice', 'Please add at least one item with quantity before printing.')
                return
            company_data = self._build_a4_company_data(active_company)
            totals_data = self._build_a4_totals_data(cart_data, bill_type)
            document_title = self._document_title_from_bill_type(bill_type)
            html_string = generate_a4_html(company_data, cart_data, bill_type=bill_type, totals_data=totals_data, settings=settings, document_title=document_title, theme_name=self._a4_theme_name(settings))
            if not html_string:
                QMessageBox.warning(self, 'Print Invoice', 'Could not generate A4 invoice HTML for the current bill.')
                return
            self._last_a4_invoice_html = html_string
            paper_size = self._a4_paper_size_from_settings(settings or {})
            print(f"[A4_PREVIEW] Sales Entry print button preview default_print_mode='{self._resolve_default_print_mode(settings or {})}' paper_size='{paper_size}' html_len={len(html_string)} preview_wrapper_present={self._a4_html_has_preview_wrapper(html_string)}")
            dialog = UniversalPreviewDialog(html_string, mode='A4', parent=self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Could not preview A4 bill:\n{exc}')

    def _a4_html_has_preview_wrapper(self, html_string):
        """Return whether settings-preview-only HTML is present in print HTML."""
        html_text = str(html_string or '')
        return 'width: 794px' in html_text or 'class="preview-body"' in html_text

    def _a4_paper_size_from_settings(self, settings):
        """Return the saved A4 engine paper size from metadata or legacy fields."""
        try:
            metadata = self._print_settings_metadata(settings)
            for key in ('a4_paper_size', 'paper_size', 'default_format'):
                value = str(metadata.get(key) or settings.get(key) or '').strip().upper()
                if value in {'A4', 'A5'}:
                    return value
        except Exception as exc:
            print(f'Failed to resolve A4 paper size: {exc}')
        return 'A4'

    def _resolve_a4_bill_type(self, active_company):
        """Return the A4 bill type from company and current bill state."""
        try:
            gst_type = (active_company.get('gst_type') or '').strip().lower()
            if not gst_type:
                gst_type = self._fetch_active_company_gst_type().strip().lower()
            is_non_taxable = bool(hasattr(self, 'non_taxable_checkbox') and self.non_taxable_checkbox.isChecked())
            sales_type = self.sales_type_combo.currentText().strip().lower() if hasattr(self, 'sales_type_combo') else ''
            if gst_type == 'composition' or is_non_taxable or 'bill of supply' in sales_type or ('non-tax' in sales_type) or ('non taxable' in sales_type):
                return 'BOS'
        except Exception as exc:
            print(f'Failed to resolve A4 bill type: {exc}')
        return 'TAX_INVOICE'

    def _document_title_from_bill_type(self, bill_type):
        """Return the printable sales document title for the resolved bill type."""
        normalized_bill_type = str(bill_type or '').strip().upper().replace(' ', '_')
        if normalized_bill_type in {'BOS', 'BILL_OF_SUPPLY'}:
            return 'Bill of Supply'
        return 'Tax Invoice'

    def _resolve_saved_bill_type(self, company_data, invoice):
        """Return the saved sale bill type using persisted company and invoice data."""
        try:
            sales_type = str(invoice.get('sales_type') or '').strip().lower()
            gst_type = str(company_data.get('gst_type') or '').strip().lower()
            bill_type = str(invoice.get('bill_type') or invoice.get('document_type') or invoice.get('invoice_type') or '').strip().lower()
            if gst_type == 'composition' or 'bill of supply' in sales_type or 'non-tax' in sales_type or ('non taxable' in sales_type) or (bill_type in {'bos', 'bill_of_supply', 'bill of supply'}):
                return 'BOS'
        except Exception as exc:
            print(f'Failed to resolve saved bill type: {exc}')
        return 'TAX_INVOICE'

    def _build_a4_company_data(self, active_company):
        """Return active company details for the A4 print engine."""
        company_id = active_company.get('id')
        company_data = dict(active_company or {})
        try:
            db_company = self.db.get_company_by_id(company_id)
            if db_company:
                company_data.update(db_company)
        except Exception as exc:
            print(f'Failed to refresh company data for A4 print: {exc}')
        company_data.setdefault('company_name', company_data.get('business_name', ''))
        company_data.setdefault('name', company_data.get('business_name', ''))
        company_data.setdefault('phone', company_data.get('phone_number', ''))
        return company_data

    def _build_a4_cart_data(self, bill_type):
        """Collect current grid rows in the structure expected by A4 printing."""
        cart_data = []
        is_bos = bill_type == 'BOS'
        if not hasattr(self, 'items_table'):
            return cart_data
        for row in range(self.items_table.rowCount()):
            row_meta = self.sale_items[row] if row < len(self.sale_items) else {}
            row_meta = row_meta or {}
            product_name = self.safe_item_text(row, 1, '').strip()
            product_id = row_meta.get('product_id')
            quantity = self.safe_float_from_cell(row, 8, 0.0)
            if not product_id and (not product_name):
                continue
            if quantity <= 0.0:
                continue
            cgst_rate = 0.0 if is_bos else self.safe_float_from_cell(row, 3, 0.0)
            sgst_rate = 0.0 if is_bos else self.safe_float_from_cell(row, 4, 0.0)
            igst_rate = 0.0 if is_bos else self.safe_float_from_cell(row, 5, 0.0)
            cess_rate = 0.0 if is_bos else self.safe_float_from_cell(row, 6, 0.0)
            gst_rate = cgst_rate + sgst_rate + igst_rate
            tax_amount = 0.0 if is_bos else self.safe_float_from_cell(row, 12, 0.0)
            cart_data.append({'sl_no': len(cart_data) + 1, 'product_id': product_id, 'product_name': product_name, 'name': product_name, 'description': product_name, 'barcode': row_meta.get('barcode', ''), 'hsn': self.safe_item_text(row, 2, row_meta.get('hsn', '')).strip(), 'rate': self.safe_float_from_cell(row, 7, row_meta.get('rate', 0.0)), 'qty': quantity, 'quantity': quantity, 'gross': self.safe_float_from_cell(row, 9, 0.0), 'gross_value': self.safe_float_from_cell(row, 9, 0.0), 'discount': self.safe_float_from_cell(row, 10, 0.0), 'net': self.safe_float_from_cell(row, 11, 0.0), 'net_value': self.safe_float_from_cell(row, 11, 0.0), 'taxable_value': self.safe_float_from_cell(row, 11, 0.0), 'tax_percent': gst_rate, 'gst_rate': gst_rate, 'cess_rate': cess_rate, 'cgst': cgst_rate, 'sgst': sgst_rate, 'igst': igst_rate, 'cess': cess_rate, 'cgst_amount': 0.0 if is_bos else row_meta.get('cgst_amount', 0.0), 'sgst_amount': 0.0 if is_bos else row_meta.get('sgst_amount', 0.0), 'igst_amount': 0.0 if is_bos else row_meta.get('igst_amount', 0.0), 'cess_amount': 0.0 if is_bos else row_meta.get('cess_amount', 0.0), 'tax_amount': tax_amount, 'total': self.safe_float_from_cell(row, 13, 0.0), 'grand_total': self.safe_float_from_cell(row, 13, 0.0)})
            QCoreApplication.processEvents()
        return cart_data

    def _build_a4_totals_data(self, cart_data, bill_type):
        """Return invoice, customer, payment, and total values for A4 printing."""
        grand_total = self._safe_float(self.grand_total_input.text() if hasattr(self, 'grand_total_input') else '', 0.0)
        if grand_total == 0.0 and hasattr(self, 'final_amount_display'):
            grand_total = self._safe_float(self.final_amount_display.text(), 0.0)
        amount_received, printed_balance = self._live_print_payment_values(grand_total)
        discount_total = self._safe_float(self.discount_total_input.text() if hasattr(self, 'discount_total_input') else '', 0.0)
        discount_total += self._safe_float(getattr(self, '_row_discount_total', 0.0), 0.0)
        total_items = sum((self._safe_float(item.get('quantity'), 0.0) for item in cart_data))
        return {'bill_type': bill_type, 'document_title': self._document_title_from_bill_type(bill_type), 'invoice_number': self.invoice_no_input.text().strip() if hasattr(self, 'invoice_no_input') else '', 'invoice_date': qdate_to_db(self.date_input.date()) if hasattr(self, 'date_input') else '', 'customer_name': strip_party_display_code(self.customer_name_input.text().strip()) if hasattr(self, 'customer_name_input') else '', 'mobile': self.mobile_input.text().strip() if hasattr(self, 'mobile_input') else '', 'address': self.address_input.text().strip() if hasattr(self, 'address_input') else '', 'gstin': self.gstin_input.text().strip() if hasattr(self, 'gstin_input') else '', 'state': self.state_combo.currentText().strip() if hasattr(self, 'state_combo') else '', 'sales_type': self.sales_type_combo.currentText().strip() if hasattr(self, 'sales_type_combo') else '', 'nature': self.nature_combo.currentText().strip() if hasattr(self, 'nature_combo') else '', 'form_of_sale': self.form_of_sale_combo.currentText().strip() if hasattr(self, 'form_of_sale_combo') else '', 'payment_mode': self._current_payment_mode(), 'sub_total': self._safe_float(self.sub_total_input.text(), 0.0) if hasattr(self, 'sub_total_input') else 0.0, 'freight': self._safe_float(self.freight_input.text(), 0.0) if hasattr(self, 'freight_input') else 0.0, 'discount_total': discount_total, 'net_amount': self._safe_float(self.net_amount_input.text(), 0.0) if hasattr(self, 'net_amount_input') else 0.0, 'net_value': self._safe_float(self.net_value_display.text(), 0.0) if hasattr(self, 'net_value_display') else 0.0, 'cgst_total': 0.0 if bill_type == 'BOS' else self._safe_float(self.cgst_display.text(), 0.0) if hasattr(self, 'cgst_display') else 0.0, 'sgst_total': 0.0 if bill_type == 'BOS' else self._safe_float(self.sgst_display.text(), 0.0) if hasattr(self, 'sgst_display') else 0.0, 'igst_total': 0.0 if bill_type == 'BOS' else self._safe_float(self.igst_display.text(), 0.0) if hasattr(self, 'igst_display') else 0.0, 'cess_total': 0.0 if bill_type == 'BOS' else self._safe_float(self.cess_display.text(), 0.0) if hasattr(self, 'cess_display') else 0.0, 'tax_total': 0.0 if bill_type == 'BOS' else self._safe_float(self.tax_amount_display.text() if hasattr(self, 'tax_amount_display') else '', 0.0), 'round_off': self._safe_float(self.round_off_input.text(), 0.0) if hasattr(self, 'round_off_input') else 0.0, 'grand_total': grand_total, 'amount_received': amount_received, 'tendered_amount': amount_received, 'paid_amount': amount_received, 'balance': printed_balance, 'amount_in_words': self._a4_amount_to_words(grand_total), 'total_items': total_items, 'narration': self.narration_input.text().strip() if hasattr(self, 'narration_input') else ''}

    def _build_thermal_transaction_data(self, active_company, settings):
        """Return current Sales Entry bill data for thermal receipt preview."""
        try:
            self.calculate_totals()
            bill_type = self._resolve_a4_bill_type(active_company or {})
            cart_data = self._build_a4_cart_data(bill_type)
            if not cart_data:
                return {}
            company_data = self._build_a4_company_data(active_company or {})
            company_data.setdefault('company_address', company_data.get('address', ''))
            company_data.setdefault('company_gstin', company_data.get('gstin', ''))
            totals_data = self._build_a4_totals_data(cart_data, bill_type)
            document_title = self._document_title_from_bill_type(bill_type)
            payment_data = {'mode': totals_data.get('payment_mode', ''), 'payment_mode': totals_data.get('payment_mode', ''), 'paid': totals_data.get('amount_received', 0.0), 'amount_paid': totals_data.get('amount_received', 0.0), 'amount_received': totals_data.get('amount_received', 0.0), 'tendered_amount': totals_data.get('amount_received', 0.0), 'paid_amount': totals_data.get('amount_received', 0.0), 'cash_received': totals_data.get('amount_received', 0.0), 'balance': totals_data.get('balance', 0.0), 'balance_amount': totals_data.get('balance', 0.0)}
            footer_text = settings.get('footer_terms') or settings.get('terms_conditions_footer') or settings.get('footer_terms_text') or 'Thank you!'
            return {'document_title': document_title, 'print_settings': settings or {}, 'company': company_data, 'company_name': company_data.get('company_name', ''), 'business_name': company_data.get('business_name', ''), 'company_address': company_data.get('company_address', ''), 'company_gstin': company_data.get('company_gstin', ''), 'phone': company_data.get('phone', ''), 'bill_no': totals_data.get('invoice_number', ''), 'invoice_number': totals_data.get('invoice_number', ''), 'date': totals_data.get('invoice_date', ''), 'bill_date': totals_data.get('invoice_date', ''), 'customer_name': totals_data.get('customer_name', '') or 'Cash Customer', 'party_name': totals_data.get('customer_name', '') or 'Cash Customer', 'customer_mobile': totals_data.get('mobile', ''), 'customer_address': totals_data.get('address', ''), 'customer_gstin': totals_data.get('gstin', ''), 'items': cart_data, 'cart_data': cart_data, 'totals': totals_data, 'payment': payment_data, 'payment_mode': payment_data.get('payment_mode', ''), 'amount_paid': payment_data.get('amount_paid', 0.0), 'amount_received': payment_data.get('amount_received', 0.0), 'balance': payment_data.get('balance', 0.0), 'footer': footer_text, 'footer_text': footer_text}
        except Exception as exc:
            print(f'Failed to build Sales Entry thermal preview data: {exc}')
            return {}

    def _a4_amount_to_words(self, value):
        """Convert a numeric amount into simple Indian currency words."""
        ones = ('Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen')
        tens = ('', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety')

        def below_hundred(number):
            """Return words for a number below one hundred."""
            if number < 20:
                return ones[number]
            suffix = number % 10
            return tens[number // 10] if suffix == 0 else f'{tens[number // 10]} {ones[suffix]}'

        def below_thousand(number):
            """Return words for a number below one thousand."""
            if number < 100:
                return below_hundred(number)
            suffix = number % 100
            words = f'{ones[number // 100]} Hundred'
            return words if suffix == 0 else f'{words} {below_hundred(suffix)}'
        amount = round(self._safe_float(value, 0.0), 2)
        rupees = int(amount)
        paise = int(round((amount - rupees) * 100))
        parts = []
        for divisor, label in ((10000000, 'Crore'), (100000, 'Lakh'), (1000, 'Thousand')):
            chunk = rupees // divisor
            if chunk:
                parts.append(f'{below_thousand(chunk)} {label}')
                rupees %= divisor
        if rupees:
            parts.append(below_thousand(rupees))
        if not parts:
            parts.append('Zero')
        words = f"{' '.join(parts)} Rupees"
        if paise:
            words = f'{words} and {below_hundred(paise)} Paise'
        return f'{words} Only'

    def clear_form(self):
        self._begin_entry_reset()
        try:
            if self._is_debug_calculation_enabled():
                print(f'[SalesEntry.clear_form] Starting clear_form, current_sale_id={self.current_sale_id}')
            self.current_sale_id = None
            self.current_voucher_id = None
            self._amt_recvd_user_edited = False
            self._clear_payment_state()
            self.invoice_no_input.clear()
            if hasattr(self, 'invoice_checkbox'):
                self.invoice_checkbox.blockSignals(True)
                self.invoice_checkbox.setChecked(False)
                self.invoice_checkbox.blockSignals(False)
                self._sync_invoice_input_editable()
            self.generate_invoice_number()
            self.date_input.setDate(QDate.currentDate())
            from bizora_core.entry_type_defaults import apply_entry_type_combo, get_active_company_default_entry_type
            apply_entry_type_combo(
                self.sales_type_combo,
                get_active_company_default_entry_type(self.db, "sales"),
            )
            self.series_input.clear()
            self.nature_combo.setCurrentIndex(0)
            if hasattr(self, 'party_type_combo'):
                idx_debtor = self.party_type_combo.findText('Debtor', Qt.MatchFixedString)
                self.party_type_combo.setCurrentIndex(idx_debtor if idx_debtor >= 0 else 0)
            self.customer_name_input.clear()
            if hasattr(self, 'salesman_combo'):
                self.salesman_combo.setCurrentIndex(0)
            self.mobile_input.clear()
            self.due_date_input.setDate(QDate.currentDate().addDays(30))
            self.address_input.clear()
            self.gstin_input.clear()
            self.state_combo.setCurrentIndex(0)
            if hasattr(self, 'rate_selector_combo'):
                self.rate_selector_combo.setCurrentIndex(0)
            if hasattr(self, 'form_of_sale_combo'):
                self.form_of_sale_combo.setCurrentText('B2CS')
            self.narration_input.clear()
            self.current_payment_mode = 'Cash'
            self.barcode_input.clear()
            self.barcode_tick.setChecked(True)
            if hasattr(self, 'divide_tax_tick'):
                self.divide_tax_tick.blockSignals(True)
                self.divide_tax_tick.setChecked(False)
                self.divide_tax_tick.blockSignals(False)
            self._apply_non_taxable_company_lock()
            if hasattr(self, 'stock_display'):
                self.stock_display.setText('0.000')
            if hasattr(self, 'code_display'):
                self.code_display.setText('')
            if hasattr(self, 'category_display'):
                self.category_display.setText('')
            if hasattr(self, 'size_display'):
                self.size_display.setText('')
            if hasattr(self, 'color_display'):
                self.color_display.setText('')
            self.items_table.setRowCount(0)
            self.sale_items = []
            self._row_discount_total = 0.0
            self._linked_sales_return_id = None
            self._linked_sales_return_amount = 0.0
            self._sales_return_window = None
            if hasattr(self, 'return_adj_zone'):
                self.return_adj_zone.setVisible(False)
            self.sub_total_input.setText('0.00')
            if hasattr(self, 'freight_input'):
                self.freight_input.blockSignals(True)
                self.freight_input.setText('0.00')
                self.freight_input.blockSignals(False)
            if hasattr(self, 'discount_total_input'):
                self.discount_total_input.blockSignals(True)
                self.discount_total_input.setText('0.00')
                self.discount_total_input.blockSignals(False)
            if hasattr(self, 'discount_label'):
                self.discount_label.setText('Discount')
            if hasattr(self, 'discount_percent_label'):
                self.discount_percent_label.setText('')
            if hasattr(self, 'round_off_checkbox'):
                self.round_off_checkbox.blockSignals(True)
                self.round_off_checkbox.setChecked(True)
                self.round_off_checkbox.blockSignals(False)
            self.tax_total_input.setText('0.00')
            self.round_off_input.setText('0.00')
            self.grand_total_input.setText('0.00')
            self._clear_payment_state()
            if hasattr(self, 'final_amount_display'):
                self.final_amount_display.setText('0.00')
            if hasattr(self, 'net_amount_input'):
                self.net_amount_input.setText('0.00')
            if hasattr(self, 'net_value_display'):
                self.net_value_display.setText('0.00')
            if hasattr(self, 'tax_amount_display'):
                self.tax_amount_display.setText('0.00')
            self.calculate_totals()
            self.update_footer_payment_fields()
            self._update_confirmed = False
            self._update_ok_button_label()
            self._invoice_dup_lock = False
            if hasattr(self, '_invoice_blink_timer') and self._invoice_blink_timer.isActive():
                self._invoice_blink_timer.stop()
            if hasattr(self, 'invoice_warning_label'):
                self.invoice_warning_label.setVisible(False)
                self.invoice_warning_label.setText('')
            try:
                self.invoice_no_input.setStyleSheet(self.compact_input_style())
            except Exception:
                pass
            QTimer.singleShot(0, lambda: self.barcode_input.setFocus())
        finally:
            self._end_entry_reset()

    def _available_printer_names(self) -> set:
        """Return installed printer names reported by Qt PrintSupport."""
        try:
            return {printer.printerName() for printer in QPrinterInfo.availablePrinters() if printer.printerName()}
        except Exception:
            return set()

    def _configure_invoice_printer_page(self, printer: QPrinter, printer_type: str, paper_size: str, default_format: str) -> None:
        """Apply practical page size settings for invoice print/export output."""
        clean_type = (printer_type or '').strip()
        clean_paper = (paper_size or default_format or 'A4').strip()
        clean_paper_upper = clean_paper.upper()
        if clean_type == 'Thermal' or clean_paper in {'Thermal', '80mm/3-inch'}:
            try:
                thermal_size = QPageSize(QSizeF(80, 297), QPageSize.Unit.Millimeter, 'Thermal 80mm')
            except Exception:
                thermal_size = QPageSize(QSizeF(80, 297), QPageSize.Millimeter)
            printer.setPageSize(thermal_size)
            return
        if clean_paper_upper == 'A3':
            printer.setPageSize(QPageSize(QPageSize.A3))
            return
        if clean_paper_upper in {'A4', 'A5'} and configure_a4_printer_page is not None:
            configure_a4_printer_page(printer, settings={'a4_paper_size': clean_paper_upper})
            return
        if clean_paper_upper == 'A5':
            printer.setPageSize(QPageSize(QPageSize.A5))
            return
        printer.setPageSize(QPageSize(QPageSize.A4))

    def _generate_sales_invoice_html(self, company_id: int, sale_id: int) -> tuple:
        """Generate invoice HTML and return it with the settings used."""
        settings = get_print_settings(self.db, company_id)
        if generate_a4_html is not None and self._resolve_default_print_mode(settings) == 'A4/A5 Invoice':
            html_content = self._generate_saved_a4_invoice_html(company_id, sale_id, settings)
            if html_content:
                return (html_content, settings)
        format_label = settings.get('default_format', 'A4')
        theme_label = settings.get('default_theme', 'Classic')
        printer_type = settings.get('printer_type', '') or ''
        format_type = 'thermal' if printer_type == 'Thermal' or format_label == 'Thermal' else 'a4'
        theme = 'modern' if theme_label in ('Modern', 'Modern Pink', 'Pink Modern') else 'classic'
        html_content = PrintEngine(self.db).generate_invoice_html(company_id, sale_id, format_type, theme)
        return (html_content, settings)

    def _build_saved_thermal_transaction_data(self, company_id: int, sale_id: int, settings: dict) -> dict:
        """Return saved sales data in the structure expected by thermal printing."""
        try:
            invoice_data = PrintEngine(self.db).fetch_invoice_data(company_id, sale_id)
            if not invoice_data:
                return {}
            company_data = dict(invoice_data.get('company') or {})
            invoice = dict(invoice_data.get('invoice') or {})
            items = list(invoice_data.get('items') or [])
            company_data.setdefault('company_name', company_data.get('business_name', ''))
            company_data.setdefault('name', company_data.get('business_name', ''))
            company_data.setdefault('company_address', company_data.get('address', ''))
            company_data.setdefault('phone', company_data.get('phone_number', ''))
            company_data.setdefault('company_gstin', company_data.get('gstin', ''))
            bill_type = self._resolve_saved_bill_type(company_data, invoice)
            is_bos = bill_type == 'BOS'
            document_title = self._document_title_from_bill_type(bill_type)
            cart_data = []
            for index, item in enumerate(items, start=1):
                cgst_amount = 0.0 if is_bos else self._safe_float(item.get('cgst_amount'), 0.0)
                sgst_amount = 0.0 if is_bos else self._safe_float(item.get('sgst_amount'), 0.0)
                igst_amount = 0.0 if is_bos else self._safe_float(item.get('igst_amount'), 0.0)
                cess_amount = 0.0 if is_bos else self._safe_float(item.get('cess_amount'), 0.0)
                gst_rate = 0.0 if is_bos else self._safe_float(item.get('cgst'), 0.0) + self._safe_float(item.get('sgst'), 0.0) + self._safe_float(item.get('igst'), 0.0)
                cart_data.append({'sl_no': item.get('sl_no') or index, 'product_name': item.get('item_name', ''), 'name': item.get('item_name', ''), 'description': item.get('item_name', ''), 'barcode': item.get('barcode', ''), 'hsn': item.get('hsn', ''), 'quantity': item.get('quantity', 0.0), 'qty': item.get('quantity', 0.0), 'rate': item.get('rate', 0.0), 'gross': item.get('gross_value', 0.0), 'gross_value': item.get('gross_value', 0.0), 'discount': item.get('discount', 0.0), 'net': item.get('net_value', 0.0), 'net_value': item.get('net_value', 0.0), 'taxable_value': item.get('net_value', 0.0), 'tax_percent': gst_rate, 'gst_rate': gst_rate, 'cess_rate': 0.0 if is_bos else item.get('cess', 0.0), 'cgst': 0.0 if is_bos else item.get('cgst', 0.0), 'sgst': 0.0 if is_bos else item.get('sgst', 0.0), 'igst': 0.0 if is_bos else item.get('igst', 0.0), 'cess': 0.0 if is_bos else item.get('cess', 0.0), 'cgst_amount': cgst_amount, 'sgst_amount': sgst_amount, 'igst_amount': igst_amount, 'cess_amount': cess_amount, 'tax_amount': 0.0 if is_bos else item.get('tax_amount', 0.0), 'total': item.get('grand_total', 0.0), 'grand_total': item.get('grand_total', 0.0)})
                QCoreApplication.processEvents()
            grand_total = self._safe_float(invoice.get('grand_total'), 0.0)
            amount_received = self._safe_float(invoice.get('amount_received'), 0.0)
            payment_mode = str(invoice.get('payment_mode') or 'Cash').strip() or 'Cash'
            printed_balance = self._receipt_balance_for_print(payment_mode, amount_received, grand_total)
            customer_address = invoice.get('address') or invoice.get('party_address') or ''
            customer_gstin = invoice.get('gstin') or invoice.get('party_gstin') or ''
            totals_data = {'bill_type': bill_type, 'document_title': document_title, 'invoice_number': invoice.get('invoice_number', ''), 'bill_no': invoice.get('invoice_number', ''), 'invoice_date': invoice.get('invoice_date', ''), 'bill_date': invoice.get('invoice_date', ''), 'customer_name': invoice.get('customer_name') or 'Cash Customer', 'party_name': invoice.get('customer_name') or 'Cash Customer', 'customer_address': customer_address, 'party_address': customer_address, 'customer_gstin': customer_gstin, 'party_gstin': customer_gstin, 'sales_type': invoice.get('sales_type', ''), 'payment_mode': payment_mode, 'subtotal': invoice.get('sub_total', 0.0), 'sub_total': invoice.get('sub_total', 0.0), 'discount': invoice.get('discount_total', 0.0), 'discount_total': invoice.get('discount_total', 0.0), 'cgst': sum((self._safe_float(item.get('cgst_amount'), 0.0) for item in cart_data)), 'sgst': sum((self._safe_float(item.get('sgst_amount'), 0.0) for item in cart_data)), 'igst': sum((self._safe_float(item.get('igst_amount'), 0.0) for item in cart_data)), 'cess': sum((self._safe_float(item.get('cess_amount'), 0.0) for item in cart_data)), 'cgst_total': sum((self._safe_float(item.get('cgst_amount'), 0.0) for item in cart_data)), 'sgst_total': sum((self._safe_float(item.get('sgst_amount'), 0.0) for item in cart_data)), 'igst_total': sum((self._safe_float(item.get('igst_amount'), 0.0) for item in cart_data)), 'cess_total': sum((self._safe_float(item.get('cess_amount'), 0.0) for item in cart_data)), 'tax_total': 0.0 if is_bos else invoice.get('tax_total', 0.0), 'round_off': invoice.get('round_off', 0.0), 'grand_total': grand_total, 'total': grand_total, 'total_amount': grand_total, 'amount_received': amount_received, 'tendered_amount': amount_received, 'paid_amount': amount_received, 'balance': printed_balance, 'amount_in_words': self._a4_amount_to_words(grand_total), 'total_items': sum((self._safe_float(item.get('quantity'), 0.0) for item in cart_data))}
            payment_data = {'mode': totals_data.get('payment_mode', ''), 'payment_mode': totals_data.get('payment_mode', ''), 'paid': amount_received, 'amount_paid': amount_received, 'amount_received': amount_received, 'tendered_amount': amount_received, 'paid_amount': amount_received, 'cash_received': amount_received, 'balance': printed_balance, 'balance_amount': printed_balance}
            footer_text = settings.get('footer_terms') or settings.get('terms_conditions_footer') or settings.get('footer_terms_text') or 'Thank you!'
            return {'document_title': document_title, 'print_settings': settings or {}, 'company': company_data, 'company_name': company_data.get('company_name', ''), 'business_name': company_data.get('business_name', ''), 'company_address': company_data.get('company_address', ''), 'company_gstin': company_data.get('company_gstin', ''), 'phone': company_data.get('phone', ''), 'bill_no': totals_data.get('invoice_number', ''), 'invoice_number': totals_data.get('invoice_number', ''), 'date': totals_data.get('invoice_date', ''), 'bill_date': totals_data.get('invoice_date', ''), 'customer_name': totals_data.get('customer_name', '') or 'Cash Customer', 'party_name': totals_data.get('customer_name', '') or 'Cash Customer', 'customer_mobile': invoice.get('customer_phone', ''), 'customer_address': customer_address, 'customer_gstin': customer_gstin, 'items': cart_data, 'cart_data': cart_data, 'totals': totals_data, 'payment': payment_data, 'payment_mode': payment_data.get('payment_mode', ''), 'amount_paid': payment_data.get('amount_paid', 0.0), 'amount_received': payment_data.get('amount_received', 0.0), 'balance': payment_data.get('balance', 0.0), 'footer': footer_text, 'footer_text': footer_text}
        except Exception as exc:
            print(f'Saved thermal invoice data generation failed: {exc}')
            return {}

    def _generate_saved_thermal_invoice_html(self, company_id: int, sale_id: int, settings: dict) -> str:
        """Generate thermal receipt HTML from the just-saved database sale."""
        try:
            if generate_thermal_html is None:
                raise RuntimeError('Thermal print engine is not available.')
            thermal_data = self._build_saved_thermal_transaction_data(company_id, sale_id, settings)
            if not thermal_data:
                return ''
            document_title = thermal_data.get('document_title') or 'Tax Invoice'
            return generate_thermal_html(thermal_data, type='sales', document_title=document_title, theme_name=self._thermal_theme_name(settings))
        except Exception as exc:
            print(f'Saved thermal invoice HTML generation failed: {exc}')
            return ''

    def _generate_saved_a4_invoice_html(self, company_id: int, sale_id: int, settings: dict) -> str:
        """Generate saved-sale PDF HTML through the same A4 engine as live preview."""
        try:
            invoice_data = PrintEngine(self.db).fetch_invoice_data(company_id, sale_id)
            if not invoice_data:
                return ''
            company_data = dict(invoice_data.get('company') or {})
            invoice = dict(invoice_data.get('invoice') or {})
            items = list(invoice_data.get('items') or [])
            company_data.setdefault('company_name', company_data.get('business_name', ''))
            company_data.setdefault('name', company_data.get('business_name', ''))
            company_data.setdefault('company_address', company_data.get('address', ''))
            company_data.setdefault('phone', company_data.get('phone_number', ''))
            company_data.setdefault('company_gstin', company_data.get('gstin', ''))
            bill_type = self._resolve_saved_bill_type(company_data, invoice)
            is_bos = bill_type == 'BOS'
            document_title = self._document_title_from_bill_type(bill_type)
            cart_data = []
            for index, item in enumerate(items, start=1):
                gst_rate = 0.0 if is_bos else self._safe_float(item.get('cgst'), 0.0) + self._safe_float(item.get('sgst'), 0.0) + self._safe_float(item.get('igst'), 0.0)
                cgst_amount = 0.0 if is_bos else self._safe_float(item.get('cgst_amount'), 0.0)
                sgst_amount = 0.0 if is_bos else self._safe_float(item.get('sgst_amount'), 0.0)
                cart_data.append({'sl_no': item.get('sl_no') or index, 'product_name': item.get('item_name', ''), 'name': item.get('item_name', ''), 'description': item.get('item_name', ''), 'hsn': item.get('hsn', ''), 'quantity': item.get('quantity', 0.0), 'qty': item.get('quantity', 0.0), 'rate': item.get('rate', 0.0), 'gross': item.get('gross_value', 0.0), 'gross_value': item.get('gross_value', 0.0), 'discount': item.get('discount', 0.0), 'net': item.get('net_value', 0.0), 'net_value': item.get('net_value', 0.0), 'taxable_value': item.get('net_value', 0.0), 'tax_percent': gst_rate, 'gst_rate': gst_rate, 'cess_rate': 0.0 if is_bos else item.get('cess', 0.0), 'cgst': cgst_amount, 'sgst': sgst_amount, 'cgst_amount': cgst_amount, 'sgst_amount': sgst_amount, 'igst_amount': 0.0 if is_bos else item.get('igst_amount', 0.0), 'cess_amount': 0.0 if is_bos else item.get('cess_amount', 0.0), 'tax_amount': 0.0 if is_bos else item.get('tax_amount', 0.0), 'total': item.get('grand_total', 0.0), 'grand_total': item.get('grand_total', 0.0)})
                QCoreApplication.processEvents()
            grand_total = self._safe_float(invoice.get('grand_total'), 0.0)
            amount_received = self._safe_float(invoice.get('amount_received'), 0.0)
            payment_mode = str(invoice.get('payment_mode') or 'Cash').strip() or 'Cash'
            printed_balance = self._receipt_balance_for_print(payment_mode, amount_received, grand_total)
            customer_address = invoice.get('address') or invoice.get('party_address') or ''
            customer_gstin = invoice.get('gstin') or invoice.get('party_gstin') or ''
            totals_data = {'bill_type': bill_type, 'document_title': document_title, 'invoice_number': invoice.get('invoice_number', ''), 'bill_no': invoice.get('invoice_number', ''), 'invoice_date': invoice.get('invoice_date', ''), 'bill_date': invoice.get('invoice_date', ''), 'customer_name': invoice.get('customer_name') or 'Cash Customer', 'party_name': invoice.get('customer_name') or 'Cash Customer', 'customer_address': customer_address, 'party_address': customer_address, 'customer_gstin': customer_gstin, 'party_gstin': customer_gstin, 'sales_type': invoice.get('sales_type', ''), 'payment_mode': payment_mode, 'subtotal': invoice.get('sub_total', 0.0), 'sub_total': invoice.get('sub_total', 0.0), 'taxable_total': invoice.get('sub_total', 0.0), 'discount': invoice.get('discount_total', 0.0), 'discount_total': invoice.get('discount_total', 0.0), 'cgst': sum((self._safe_float(item.get('cgst_amount'), 0.0) for item in cart_data)), 'sgst': sum((self._safe_float(item.get('sgst_amount'), 0.0) for item in cart_data)), 'cess': sum((self._safe_float(item.get('cess_amount'), 0.0) for item in cart_data)), 'cgst_total': sum((self._safe_float(item.get('cgst_amount'), 0.0) for item in cart_data)), 'sgst_total': sum((self._safe_float(item.get('sgst_amount'), 0.0) for item in cart_data)), 'cess_total': sum((self._safe_float(item.get('cess_amount'), 0.0) for item in cart_data)), 'tax_total': 0.0 if is_bos else invoice.get('tax_total', 0.0), 'round_off': invoice.get('round_off', 0.0), 'grand_total': grand_total, 'total': grand_total, 'total_amount': grand_total, 'amount_received': amount_received, 'tendered_amount': amount_received, 'paid_amount': amount_received, 'balance': printed_balance, 'amount_in_words': self._a4_amount_to_words(grand_total), 'total_items': sum((self._safe_float(item.get('quantity'), 0.0) for item in cart_data))}
            return generate_a4_html(company_data, cart_data, bill_type=bill_type, totals_data=totals_data, settings=settings, document_title=document_title, theme_name=self._a4_theme_name(settings))
        except Exception as exc:
            print(f'Saved A4 invoice HTML generation failed: {exc}')
            return ''

    def _build_silent_sales_printer(self, settings: dict, default_mode: str) -> QPrinter:
        """Return a QPrinter using saved Sales printer names when installed."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        preferred_key = 'thermal_printer_name' if default_mode == 'Thermal Receipt' else 'normal_printer_name'
        saved_printer_name = self._saved_printer_name(settings, preferred_key)
        if saved_printer_name and saved_printer_name in self._available_printer_names():
            printer.setPrinterName(saved_printer_name)
        return printer

    def _silent_print_saved_sales_receipt(self, company_id: int, sale_id: int, settings: dict=None) -> None:
        """Print a saved sale directly without opening UniversalPreviewDialog."""
        try:
            settings = settings or get_print_settings(self.db, company_id)
            default_mode = self._resolve_default_print_mode(settings)
            printer = self._build_silent_sales_printer(settings, default_mode)
            if default_mode == 'Thermal Receipt':
                if print_thermal_receipt is None:
                    raise RuntimeError('Thermal print engine is not available.')
                html_content = self._generate_saved_thermal_invoice_html(company_id, sale_id, settings)
                if not html_content:
                    raise RuntimeError('Could not generate thermal receipt HTML.')
                print_thermal_receipt(html_content, printer)
                return
            if print_a4_receipt is None or generate_a4_html is None:
                raise RuntimeError('A4 print engine is not available.')
            html_content = self._generate_saved_a4_invoice_html(company_id, sale_id, settings)
            if not html_content:
                raise RuntimeError('Could not generate A4 invoice HTML.')
            print_a4_receipt(html_content, printer, settings=settings, paper_size=self._a4_paper_size_from_settings(settings))
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Bill was saved, but automatic receipt printing failed:\n{exc}')

    def _open_sales_invoice_preview(self, company_id: int, sale_id: int, active_company: dict, settings: dict) -> None:
        """Generate sales invoice HTML and show UniversalPreviewDialog first."""
        default_mode = self._resolve_default_print_mode(settings)
        if default_mode == 'Thermal Receipt':
            if generate_thermal_html is None:
                raise RuntimeError('Thermal preview engine is not available. Please verify thermal_print_engine.py.')
            thermal_data = self._build_saved_thermal_transaction_data(company_id, sale_id, settings)
            if not thermal_data:
                QMessageBox.warning(self, 'Preview Invoice', 'Could not load saved thermal receipt data for the selected bill.')
                return
            document_title = thermal_data.get('document_title') or 'Tax Invoice'
            thermal_html = generate_thermal_html(thermal_data, type='sales', document_title=document_title, theme_name=self._thermal_theme_name(settings))
            if not thermal_html:
                QMessageBox.warning(self, 'Preview Invoice', 'Could not generate thermal receipt HTML for the selected bill.')
                return
            print(f"[THERMAL_PREVIEW] Sales Entry print button preview default_print_mode='{default_mode}' html_len={len(thermal_html)} items={len(thermal_data.get('items') or [])} bill_no='{thermal_data.get('bill_no', '')}'")
            dialog = UniversalPreviewDialog(thermal_html, mode='Thermal', parent=self)
            dialog.exec()
            return
        html_content = ''
        if generate_a4_html is not None:
            html_content = self._generate_saved_a4_invoice_html(company_id, sale_id, settings)
        if not html_content:
            html_content, settings = self._generate_sales_invoice_html(company_id, sale_id)
        if not html_content:
            QMessageBox.warning(self, 'Preview Invoice', 'Could not generate invoice HTML for the selected bill.')
            return
        self._last_a4_invoice_html = html_content
        print(f"[A4_PREVIEW] Sales Entry print button preview default_print_mode='{default_mode}' paper_size='{self._a4_paper_size_from_settings(settings)}' html_len={len(html_content)} preview_wrapper_present={self._a4_html_has_preview_wrapper(html_content)}")
        dialog = UniversalPreviewDialog(html_content, mode='A4', parent=self)
        dialog.exec()

    def export_pdf(self):
        """Open the current sales invoice in the universal preview dialog."""
        bill_no = self.invoice_no_input.text().strip() if hasattr(self, 'invoice_no_input') else ''
        if not self.current_sale_id or not bill_no:
            QMessageBox.warning(self, 'Export Blocked', 'Please save the bill first or load an existing bill to preview.')
            return
        company_id = active_company_manager.get_active_company_id()
        if not company_id:
            QMessageBox.warning(self, 'Export Blocked', 'No active company selected.')
            return
        try:
            settings = get_print_settings(self.db, company_id)
            default_mode = self._resolve_default_print_mode(settings)
            if default_mode == 'Thermal Receipt':
                if generate_thermal_html is None:
                    raise RuntimeError('Thermal preview engine is not available. Please verify thermal_print_engine.py.')
                thermal_data = self._build_saved_thermal_transaction_data(company_id, self.current_sale_id, settings)
                if not thermal_data:
                    QMessageBox.warning(self, 'Preview Invoice', 'Could not load saved thermal receipt data for the selected bill.')
                    return
                document_title = thermal_data.get('document_title') or 'Tax Invoice'
                thermal_html = generate_thermal_html(thermal_data, type='sales', document_title=document_title, theme_name=self._thermal_theme_name(settings))
                if not thermal_html:
                    QMessageBox.warning(self, 'Preview Invoice', 'Could not generate thermal receipt HTML for the selected bill.')
                    return
                print(f"[THERMAL_PREVIEW] Sales Entry universal preview default_print_mode='{default_mode}' html_len={len(thermal_html)} items={len(thermal_data.get('items') or [])} bill_no='{thermal_data.get('bill_no', '')}'")
                dialog = UniversalPreviewDialog(thermal_html, mode='Thermal', parent=self)
                dialog.exec()
                return
            html_content = ''
            if generate_a4_html is not None:
                html_content = self._generate_saved_a4_invoice_html(company_id, self.current_sale_id, settings)
            if not html_content:
                html_content, settings = self._generate_sales_invoice_html(company_id, self.current_sale_id)
            if not html_content:
                QMessageBox.warning(self, 'Preview Invoice', 'Could not generate invoice HTML for the selected bill.')
                return
            self._last_a4_invoice_html = html_content
            print(f"[A4_PREVIEW] Sales Entry universal preview default_print_mode='{default_mode}' paper_size='{self._a4_paper_size_from_settings(settings)}' html_len={len(html_content)} preview_wrapper_present={self._a4_html_has_preview_wrapper(html_content)}")
            dialog = UniversalPreviewDialog(html_content, mode='A4', parent=self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, 'Preview Invoice', f'Could not preview invoice:\n{exc}')

    def _export_sales_invoice_pdf(self, company_id: int, sale_id: int, file_path: str) -> None:
        """Export the rendered sales invoice HTML to a PDF file."""
        try:
            html_content, settings = self._generate_sales_invoice_html(company_id, sale_id)
            if not html_content:
                QMessageBox.warning(self, 'Export PDF', 'Could not generate invoice HTML for the selected bill.')
                return
            self._last_a4_invoice_html = html_content
            if export_a4_pdf is None:
                raise RuntimeError('A4 PDF export engine is not available.')
            print(f"[A4_PRINT] Sales Entry PDF export route default_print_mode='{self._resolve_default_print_mode(settings)}' paper_size='{self._a4_paper_size_from_settings(settings)}' html_len={len(html_content)} preview_wrapper_present={self._a4_html_has_preview_wrapper(html_content)}")
            export_a4_pdf(html_content, file_path, settings=settings, paper_size=self._a4_paper_size_from_settings(settings))
            QMessageBox.information(self, 'Export PDF', f'Invoice exported to:\n{file_path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Export PDF', f'Could not export PDF:\n{exc}')

    def _fetch_sales_invoice_export_rows(self, company_id: int, sale_id: int) -> tuple:
        """Fetch one sales header and its items with company-scoped joins."""
        ph = self.db._get_placeholder()
        header_rows = self.db.execute_query(f"\n            SELECT\n                s.id,\n                s.invoice_number,\n                s.invoice_date,\n                s.sales_type,\n                s.sub_total,\n                s.discount_total,\n                s.tax_total,\n                s.round_off,\n                s.grand_total,\n                s.amount_received,\n                s.payment_mode,\n                COALESCE(p.name, '') AS customer_name\n            FROM sales s\n            LEFT JOIN parties p\n                ON p.id = s.party_id\n               AND p.company_id = s.company_id\n            WHERE s.company_id = {ph}\n              AND s.id = {ph}\n            ", (company_id, sale_id))
        item_rows = self.db.execute_query(f"\n            SELECT\n                si.sl_no,\n                COALESCE(pr.name, '') AS item_name,\n                si.hsn,\n                si.unit,\n                si.quantity,\n                si.rate,\n                si.gross_value,\n                si.discount,\n                si.net_value,\n                si.tax_amount,\n                si.grand_total,\n                si.cgst_amount,\n                si.sgst_amount,\n                si.igst_amount,\n                si.cess_amount\n            FROM sales_items si\n            INNER JOIN sales s\n                ON s.id = si.sale_id\n               AND s.company_id = {ph}\n               AND s.id = {ph}\n            LEFT JOIN products pr\n                ON pr.id = si.product_id\n               AND pr.company_id = s.company_id\n            ORDER BY si.sl_no, si.id\n            ", (company_id, sale_id))
        return (header_rows[0] if header_rows else None, item_rows)

    def _export_sales_invoice_xlsx(self, company_id: int, sale_id: int, file_path: str) -> None:
        """Export the saved invoice grid to XLSX using available Excel libraries."""
        try:
            header, items = self._fetch_sales_invoice_export_rows(company_id, sale_id)
            if not header:
                QMessageBox.warning(self, 'Export Excel', 'Could not find the selected bill.')
                return
            try:
                import openpyxl
                from openpyxl.styles import Font
                workbook = openpyxl.Workbook()
                sheet = workbook.active
                sheet.title = 'Sales Invoice'
                sheet.append(['Invoice No', header.get('invoice_number', '')])
                sheet.append(['Date', header.get('invoice_date', '')])
                sheet.append(['Customer', header.get('customer_name', '')])
                sheet.append(['Sales Type', header.get('sales_type', '')])
                sheet.append([])
                columns = ['SL No', 'Item', 'HSN', 'Unit', 'Qty', 'Rate', 'Gross', 'Discount', 'Net', 'Tax', 'Grand Total', 'CGST', 'SGST', 'IGST', 'CESS']
                sheet.append(columns)
                for cell in sheet[sheet.max_row]:
                    cell.font = Font(bold=True)
                for item in items:
                    sheet.append([item.get('sl_no', ''), item.get('item_name', ''), item.get('hsn', ''), item.get('unit', ''), item.get('quantity', 0), item.get('rate', 0), item.get('gross_value', 0), item.get('discount', 0), item.get('net_value', 0), item.get('tax_amount', 0), item.get('grand_total', 0), item.get('cgst_amount', 0), item.get('sgst_amount', 0), item.get('igst_amount', 0), item.get('cess_amount', 0)])
                sheet.append([])
                sheet.append(['Sub Total', header.get('sub_total', 0)])
                sheet.append(['Discount', header.get('discount_total', 0)])
                sheet.append(['Tax Total', header.get('tax_total', 0)])
                sheet.append(['Round Off', header.get('round_off', 0)])
                sheet.append(['Grand Total', header.get('grand_total', 0)])
                workbook.save(file_path)
                QMessageBox.information(self, 'Export Excel', f'Invoice exported to:\n{file_path}')
                return
            except ImportError:
                pass
            try:
                import pandas as pd
            except ImportError:
                QMessageBox.warning(self, 'Export Excel', 'Excel export requires openpyxl or pandas. Neither dependency is installed.')
                return
            rows = [{'SL No': item.get('sl_no', ''), 'Item': item.get('item_name', ''), 'HSN': item.get('hsn', ''), 'Unit': item.get('unit', ''), 'Qty': item.get('quantity', 0), 'Rate': item.get('rate', 0), 'Gross': item.get('gross_value', 0), 'Discount': item.get('discount', 0), 'Net': item.get('net_value', 0), 'Tax': item.get('tax_amount', 0), 'Grand Total': item.get('grand_total', 0), 'CGST': item.get('cgst_amount', 0), 'SGST': item.get('sgst_amount', 0), 'IGST': item.get('igst_amount', 0), 'CESS': item.get('cess_amount', 0)} for item in items]
            with pd.ExcelWriter(file_path) as writer:
                pd.DataFrame(rows).to_excel(writer, sheet_name='Sales Invoice', index=False)
                pd.DataFrame([{'Field': 'Invoice No', 'Value': header.get('invoice_number', '')}, {'Field': 'Date', 'Value': header.get('invoice_date', '')}, {'Field': 'Customer', 'Value': header.get('customer_name', '')}, {'Field': 'Grand Total', 'Value': header.get('grand_total', 0)}]).to_excel(writer, sheet_name='Summary', index=False)
            QMessageBox.information(self, 'Export Excel', f'Invoice exported to:\n{file_path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Export Excel', f'Could not export Excel:\n{exc}')

    def on_footer_discount_changed(self, _text):
        """Footer Discount text changed: auto-compute effective % of the current
        base and display it in the small sub-label, then recalculate totals.

        Base = sub_total - row_discount + tax + freight.
        If the entered value is 0 or the base is 0, the % label is cleared.
        """
        if hasattr(self, 'discount_percent_label'):
            amount = self._safe_float(self.discount_total_input.text(), 0.0)
            if amount > 0:
                sub_total = self._safe_float(self.sub_total_input.text(), 0.0) if hasattr(self, 'sub_total_input') else 0.0
                tax_total = self._safe_float(self.tax_total_input.text(), 0.0) if hasattr(self, 'tax_total_input') else 0.0
                row_discount_total = float(getattr(self, '_row_discount_total', 0.0) or 0.0)
                freight = self._safe_float(self.freight_input.text(), 0.0) if hasattr(self, 'freight_input') else 0.0
                base = sub_total - row_discount_total + tax_total + freight
                if base > 0:
                    pct = amount / base * 100.0
                    pct_disp = f'{pct:.0f}' if float(pct).is_integer() else f'{pct:.2f}'
                    self.discount_percent_label.setText(f'({pct_disp}%)')
                else:
                    self.discount_percent_label.setText('')
            else:
                self.discount_percent_label.setText('')
        self.calculate_totals()

    def apply_discount_percent_mode(self):
        """Interpret current footer Discount value as a percentage of the pre-discount base.

        Base = sub_total - row_discount + tax + freight.
        Converts the entered number into an actual discount amount and updates
        the Discount label with the percent value (e.g. "Discount (10%)").
        """
        try:
            _sf = self._safe_float
            pct = _sf(self.discount_total_input.text(), 0.0)
            if pct <= 0:
                return
            sub_total = _sf(self.sub_total_input.text(), 0.0) if hasattr(self, 'sub_total_input') else 0.0
            tax_total = _sf(self.tax_total_input.text(), 0.0) if hasattr(self, 'tax_total_input') else 0.0
            row_discount_total = float(getattr(self, '_row_discount_total', 0.0) or 0.0)
            freight = _sf(self.freight_input.text(), 0.0) if hasattr(self, 'freight_input') else 0.0
            base = sub_total - row_discount_total + tax_total + freight
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
        except Exception:
            pass

    def open_debitor_creditor_page(self):
        """Navigate to the Debtor/Creditor page (Masters menu) in the main window."""
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

    def confirm_remove_bill(self):
        """Ask for confirmation before removing the current bill.

        If it's a saved bill, delete it from the database.
        The invoice number is cleared (not overwritten) - user can manually
        specify a number using "Entry with Specific Invoice No" option.
        """
        if self.current_sale_id:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                QMessageBox.warning(self, 'No Active Company', 'Please open a company first.')
                return
            if not confirm_before_delete_transaction(
                self,
                'Remove Saved Bill',
                'This will permanently delete this bill from the database.\n\nAre you sure you want to remove this bill?',
                db=self.db,
                company_id=active_company['id'],
            ):
                return
            result = self.sales_logic.delete_sale(active_company['id'], self.current_sale_id)
            if result['success']:
                QMessageBox.information(self, 'Success', 'Bill removed successfully.')
                try:
                    self.load_products()
                except Exception:
                    pass
                self.clear_form()
            else:
                QMessageBox.critical(self, 'Error', f"Failed to remove bill: {result['message']}")
        else:
            reply = QMessageBox.question(self, 'Clear Form', 'Are you sure you want to clear this form?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.clear_form()

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
        if self.current_sale_id and (not self._update_confirmed):
            confirm_update = QMessageBox.question(self, 'Update Saved Bill?', 'This is a saved bill. Removing an item will modify it.\n\nDo you want to update this bill?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if confirm_update != QMessageBox.Yes:
                return
            self._update_confirmed = True
        reply = QMessageBox.question(self, 'Remove Item', f'Are you sure you want to remove item at row {target_row + 1}?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.items_table.setCurrentCell(target_row, 0)
        self.delete_row()

    @staticmethod
    def _safe_float(text, default=0.0):
        """Parse text to float safely; blank/invalid returns default."""
        try:
            s = str(text).strip().replace(',', '').replace('₹', '')
            if not s:
                return default
            return float(s)
        except (ValueError, TypeError):
            return default

    def _current_payment_mode(self):
        """Return the active payment mode captured from Cash Tender."""
        mode = str(getattr(self, 'current_payment_mode', 'Cash') or '').strip()
        return mode or 'Cash'

    def _clear_payment_state(self):
        """Reset cached and visible payment values for a fresh sales bill."""
        self.amount_received = 0.0
        self.balance = 0.0
        if hasattr(self, 'amount_receive_input'):
            self._suppress_amt_recvd_signal = True
            self.amount_receive_input.blockSignals(True)
            try:
                self.amount_receive_input.setText('0.00')
            finally:
                self.amount_receive_input.blockSignals(False)
                self._suppress_amt_recvd_signal = False
        if hasattr(self, 'balance_display'):
            self.balance_display.setText('0.00')

    def _live_print_payment_values(self, fallback_grand_total=0.0):
        """Return Amount Received and receipt balance from current payment state."""
        grand_total = self._safe_float(self.grand_total_input.text() if hasattr(self, 'grand_total_input') else '', fallback_grand_total)
        received_text = self.amount_receive_input.text() if hasattr(self, 'amount_receive_input') else ''
        amount_received = self._safe_float(received_text, grand_total)
        payment_mode = self._current_payment_mode()
        sales_type = self.sales_type_combo.currentText().strip().lower() if hasattr(self, 'sales_type_combo') else ''
        if amount_received == 0.0 and grand_total > 0.0 and (payment_mode.strip().lower() == 'cash') and (sales_type not in ('credit', 'credit sales')):
            amount_received = grand_total
        printed_balance = self._receipt_balance_for_print(payment_mode, amount_received, grand_total)
        self.amount_received = amount_received
        self.balance = printed_balance
        return (amount_received, printed_balance)

    def _receipt_balance_for_print(self, payment_mode, amount_received, grand_total):
        """Return cash change for receipts, or zero for non-cash payment modes."""
        mode_text = str(payment_mode or 'Cash').strip().lower()
        if mode_text == 'cash':
            return self._safe_float(amount_received, 0.0) - self._safe_float(grand_total, 0.0)
        return 0.0

    def _apply_live_payment_values_to_print_data(self, invoice_data):
        """Inject live UI payment values into invoice data before rendering."""
        try:
            invoice = invoice_data.get('invoice') or {}
            if not isinstance(invoice, dict):
                return
            fallback_grand_total = self._safe_float(invoice.get('grand_total'), 0.0)
            amount_received, printed_balance = self._live_print_payment_values(fallback_grand_total)
            invoice['amount_received'] = amount_received
            invoice['tendered_amount'] = amount_received
            invoice['paid_amount'] = amount_received
            invoice['balance'] = printed_balance
            invoice['printed_balance'] = printed_balance
            invoice['payment_mode'] = invoice.get('payment_mode') or self._current_payment_mode()
            invoice['nature'] = self.nature_combo.currentText().strip() if hasattr(self, 'nature_combo') else invoice.get('nature', '')
            invoice['is_interstate'] = self.is_current_sale_interstate()
            invoice_data['invoice'] = invoice
        except Exception as exc:
            print(f'Failed to apply live payment values for print: {exc}')

    def get_selected_party_old_balance(self):
        """Return the Previous Balance (balance before current voucher) of the selected party.

        Uses PartyBalanceEngine to calculate:
        Previous Balance = party opening_balance + unpaid previous sales - previous receipts/returns

        Excludes current bill when editing/viewing old bills via voucher_id.
        Excludes future bills (after current voucher date/id).

        Matches party name case-insensitively against self.parties_data.
        Returns 0.00 when no party found / blank / error.
        """
        try:
            if not hasattr(self, 'customer_name_input'):
                return 0.0
            name = self.customer_name_input.text().strip()
            if not name:
                return 0.0
            if not getattr(self, 'parties_data', None):
                return 0.0
            for p in self.parties_data:
                if party_matches_text(p, name):
                    party_id = p.get('id')
                    if party_id:
                        active = active_company_manager.get_active_company()
                        if active:
                            voucher_id = self.current_sale_id if hasattr(self, 'current_sale_id') else None
                            voucher_date = None
                            if voucher_id and hasattr(self, 'invoice_date_input'):
                                voucher_date = qdate_to_db(self.invoice_date_input.date())
                            balance_result = self.balance_engine.get_party_balance_before_voucher(active['id'], party_id, 'sales', voucher_id=voucher_id, voucher_date=voucher_date)
                            return balance_result.get('previous_balance', 0.0)
                    return self._safe_float(p.get('opening_balance'), 0.0)
            return 0.0
        except Exception:
            return 0.0

    def update_footer_payment_fields(self, write_amt_recvd=True):
        """Recompute and write Opening Balance, Previous Balance, Closing Balance, and (optionally) Amt Recvd.

        Rules:
          - Opening Balance: Only from party master (parties.opening_balance), never changes while browsing.
          - Previous Balance: Balance before current voucher (excludes current and future bills).
          - Cash: Amt Recvd auto = Grand Total (always forced).
          - Credit (default state): Amt Recvd = 0.00 until user manually edits it.
          - Credit (user-edited): preserve user's Amt Recvd value.
          - Closing Balance = Previous Balance + Current Bill Amount - Amount Received.

        When called from the user's own edit of Amt Recvd, pass
        write_amt_recvd=False so we don't overwrite the field mid-typing
        (which would reset the cursor and block further input).
        """
        if self._is_debug_calculation_enabled():
            print(f'[SalesEntry.update_footer_payment_fields] Starting, current_sale_id={self.current_sale_id}')
        if not hasattr(self, 'amount_receive_input'):
            return
        grand_total = self._safe_float(getattr(self, 'grand_total_input', None).text() if hasattr(self, 'grand_total_input') else 0.0, 0.0)
        sales_type = ''
        if hasattr(self, 'sales_type_combo'):
            sales_type = (self.sales_type_combo.currentText() or '').strip().lower()
        previous_balance = self.get_selected_party_old_balance()
        opening_balance = 0.0
        if hasattr(self, 'customer_name_input'):
            name = self.customer_name_input.text().strip()
            if name and getattr(self, 'parties_data', None):
                for p in self.parties_data:
                    if party_matches_text(p, name):
                        opening_balance = self._safe_float(p.get('opening_balance'), 0.0)
                        break
        is_cash_sale = sales_type in ('cash', 'sales', 'sale')
        if is_cash_sale:
            if self._amt_recvd_user_edited:
                amt_recvd = self._safe_float(self.amount_receive_input.text(), 0.0)
                print('AUTO SYNC: Using manual amount_received =', amt_recvd)
            else:
                amt_recvd = grand_total
                print('AUTO SYNC GRAND TOTAL =', grand_total)
                print('AUTO SYNC AMOUNT RECEIVED =', amt_recvd)
        elif self._amt_recvd_user_edited:
            amt_recvd = self._safe_float(self.amount_receive_input.text(), 0.0)
        else:
            amt_recvd = 0.0
        amt_recvd_for_calc = amt_recvd if amt_recvd <= grand_total else grand_total
        closing_balance = self.balance_engine.calculate_closing_balance(previous_balance, grand_total, amt_recvd_for_calc, 'sales')
        if write_amt_recvd:
            self._suppress_amt_recvd_signal = True
            self.amount_receive_input.blockSignals(True)
            try:
                self.amount_receive_input.setText(f'{amt_recvd_for_calc:.2f}')
            finally:
                self.amount_receive_input.blockSignals(False)
                self._suppress_amt_recvd_signal = False
        if hasattr(self, 'db_display'):
            self.db_display.setText(f'{previous_balance:.2f}')
        if hasattr(self, 'cb_display'):
            self.cb_display.setText(f'{closing_balance:.2f}')
        if hasattr(self, 'balance_display'):
            self.balance_display.setText(f'{closing_balance:.2f}')
        self.amount_received = amt_recvd_for_calc
        self.balance = closing_balance

    def on_sales_type_changed(self, _text):
        """Type switched: reset manual-edit flag so defaults apply, then refresh."""
        self._amt_recvd_user_edited = False
        self.update_footer_payment_fields()
        self._sync_print_ob_visibility()

    def _sync_print_ob_visibility(self):
        """The 'Print O/B & Amt Rcvd' checkbox is always visible (so the
        label is never missing from the foot bar) but is only ENABLED for
        Credit bills. For Cash bills it is force-unchecked and disabled —
        Cash sales have no outstanding balance concept.
        """
        if not hasattr(self, 'print_ob_checkbox'):
            return
        self.print_ob_checkbox.setVisible(True)
        sales_type = ''
        if hasattr(self, 'sales_type_combo'):
            sales_type = (self.sales_type_combo.currentText() or '').strip().lower()
        is_credit = sales_type == 'credit'
        self.print_ob_checkbox.setEnabled(is_credit)
        if not is_credit:
            self.print_ob_checkbox.blockSignals(True)
            self.print_ob_checkbox.setChecked(False)
            self.print_ob_checkbox.blockSignals(False)

    def on_party_name_changed(self, _text):
        """Party name changed: refresh O/B and recompute balance safely."""
        self.update_footer_payment_fields()

    def on_amt_recvd_edited(self, _text):
        """User manually edited Amt Recvd (only credit mode is meaningful).

        We pass write_amt_recvd=False so we do NOT rewrite the field while the
        user is still typing (which would reset the cursor and block input).
        Only C/B and Balance are refreshed live.
        """
        if self._suppress_amt_recvd_signal:
            return
        sales_type = ''
        if hasattr(self, 'sales_type_combo'):
            sales_type = (self.sales_type_combo.currentText() or '').strip().lower()
        if sales_type == 'cash':
            self.update_footer_payment_fields(write_amt_recvd=True)
            return
        self._amt_recvd_user_edited = True
        self.update_footer_payment_fields(write_amt_recvd=False)

    def generate_invoice_number(self):
        """Auto-generate sales invoice number based on series.
        Mirrors Purchase Entry logic for consistency.
        """
        active = active_company_manager.get_active_company()
        if not active:
            return
        if hasattr(self, 'invoice_checkbox') and self.invoice_checkbox.isChecked():
            print('LAST SALES INVOICE = (manual mode, skipping auto-generation)')
            return
        series = self.series_input.text().strip()
        print(f"[DEBUG] generate_invoice_number called: company_id={active['id']}, series='{series}'")
        try:
            self._yield_ui_events()
            next_num = self.db.get_next_sale_number(active['id'], series)
            self._yield_ui_events()
            print(f'LAST SALES INVOICE = {next_num}')
            print(f'NEXT SALES INVOICE = {next_num}')
            print(f'DISPLAYED INVOICE = {next_num}')
            self.invoice_no_input.setText(next_num)
        except Exception as e:
            if self._is_debug_calculation_enabled():
                print(f'Error generating invoice number: {e}')
            fallback_num = self._generate_unique_invoice_number(active['id'])
            print(f'LAST SALES INVOICE = (DB error, using fallback)')
            print(f'NEXT SALES INVOICE = {fallback_num}')
            print(f'DISPLAYED INVOICE = {fallback_num}')
            self.invoice_no_input.setText(fallback_num)

    def _generate_unique_invoice_number(self, company_id):
        """Generate a unique invoice number when auto-generation needs a fallback."""
        try:
            from bizora_core.invoice_numbering import (
                format_voucher_number,
                get_invoice_prefix,
                get_max_voucher_sequence,
                get_next_voucher_number,
            )

            prefix = get_invoice_prefix(self.db, company_id)
            start_sequence = get_max_voucher_sequence(self.db, company_id, "sales", prefix) + 1
            for sequence in range(start_sequence, start_sequence + 1000):
                if sequence % 25 == 0:
                    self._yield_ui_events()
                candidate = format_voucher_number(prefix, sequence)
                if not self.db.invoice_number_exists(company_id, candidate):
                    return candidate
            return get_next_voucher_number(self.db, company_id, "sales")
        except Exception:
            return "001"

    def _resolve_party_id(self, customer_name, ui_sales_type, company_id):
        """Resolve party_id for the given customer name (case-insensitive).

        - If name is blank and sale is Cash, use 'Cash Customer' as the default party.
        - Look up the party in the current DB. If found, return its id.
        - If not found, auto-create a Debitor party with that name and return its id.
        - Returns None only if creation fails outright.
        """
        name = (customer_name or '').strip()
        if not name:
            name = 'Cash Customer'
        try:
            parties = self.db.get_parties_by_company(company_id) or []
            for p in parties:
                if party_matches_text(p, name):
                    return p['id']
            clean_name = strip_party_display_code(name)
            create_result = self.party_logic.save_party(company_id, {'name': clean_name, 'party_type': 'Debitor', 'opening_balance': 0.0})
            if not create_result.get('success'):
                return None
            parties = self.db.get_parties_by_company(company_id) or []
            self.parties_data = parties
            for p in parties:
                if party_matches_text(p, clean_name):
                    return p['id']
        except Exception:
            return None
        return None

    def _first_tender_value(self, source, keys, default=None):
        """Read the first present Cash Tender value from dicts or objects."""
        if source is None:
            return default
        for key in keys:
            try:
                if hasattr(source, 'get'):
                    value = source.get(key, None)
                    if value not in (None, ''):
                        return value
            except (AttributeError, TypeError):
                pass
            try:
                value = getattr(source, key)
                if value not in (None, ''):
                    return value
            except (AttributeError, TypeError):
                pass
        return default

    def _normalize_cash_tender_values(self, raw_values, current_grand_total):
        """Normalize dict/tuple/object Cash Tender return payloads."""
        if isinstance(raw_values, (list, tuple)):
            raw_values = {'cash_received': raw_values[0] if len(raw_values) >= 1 else 0.0, 'payment_mode': raw_values[1] if len(raw_values) >= 2 else 'Cash', 'balance_returned': raw_values[2] if len(raw_values) >= 3 else None}
        bill_amount = self._safe_float(self._first_tender_value(raw_values, ('bill_amount', 'total_amount')), current_grand_total)
        cash_received = self._safe_float(self._first_tender_value(raw_values, ('tendered_amount', 'cash_received', 'amount_received', 'tendered')), 0.0)
        payment_mode = str(self._first_tender_value(raw_values, ('payment_mode', 'mode'), 'Cash') or 'Cash').strip() or 'Cash'
        balance_returned = self._first_tender_value(raw_values, ('balance_returned', 'change', 'balance'), None)
        if balance_returned is None:
            balance_returned = cash_received - bill_amount if payment_mode.lower() == 'cash' else 0.0
        else:
            balance_returned = self._safe_float(balance_returned, 0.0)
        return {'bill_amount': bill_amount, 'cash_received': cash_received, 'tendered_amount': cash_received, 'amount_received': cash_received, 'payment_mode': payment_mode, 'balance_returned': balance_returned, 'balance': balance_returned}

    def _resolve_ledger_amount_received(self, final_grand_total, sales_type_lc):
        """
        Return the bill settlement posted to ledger and debtor balance.

        Cash Tender records physical notes handed over; that value must not
        replace the ledger settlement on cash or credit bills.
        """
        is_cash_sale = sales_type_lc in ('cash', 'sales', 'sale')
        if is_cash_sale:
            return self._safe_float(final_grand_total, 0.0)
        if self._amt_recvd_user_edited:
            return self._safe_float(self.amount_receive_input.text(), 0.0)
        return 0.0

    def _default_tender_values(self, current_grand_total, payment_mode='Cash'):
        """Return neutral tender payload when the dialog is skipped."""
        balance_returned = self._receipt_balance_for_print(payment_mode, 0.0, current_grand_total)
        return {
            'bill_amount': current_grand_total,
            'cash_received': 0.0,
            'tendered_amount': 0.0,
            'amount_received': 0.0,
            'payment_mode': payment_mode,
            'balance_returned': balance_returned,
            'balance': balance_returned,
        }

    def _should_prompt_cash_tender(self, sales_type_lc: str) -> bool:
        """
        Return True when the Cash Tender dialog should open on save.

        Credit bills skip tender unless the user entered an amount received,
        because pure credit sales have no cash collection step.
        """
        is_credit_sale = sales_type_lc in ('credit', 'credit sales')
        if not is_credit_sale:
            return True

        amount_received = self._safe_float(
            self.amount_receive_input.text() if hasattr(self, 'amount_receive_input') else '0',
            0.0,
        )
        return amount_received > 0.0

    def _collect_cash_tender_values(self, current_grand_total):
        """Show Cash Tender and return payment values for the sale save."""
        try:
            active_company = active_company_manager.get_active_company()
            company_id = active_company.get('id') if active_company else None
            if company_id and hasattr(self.db, 'is_cash_tender_enabled'):
                if not self.db.is_cash_tender_enabled(company_id):
                    payment_mode = self._current_payment_mode()
                    return self._default_tender_values(current_grand_total, payment_mode)

            sales_type_lc = ''
            if hasattr(self, 'sales_type_combo'):
                sales_type_lc = (self.sales_type_combo.currentText() or '').strip().lower()
            if not self._should_prompt_cash_tender(sales_type_lc):
                payment_mode = self._current_payment_mode()
                return self._default_tender_values(current_grand_total, payment_mode)

            QCoreApplication.processEvents()
            dialog = CashTenderDialog(current_grand_total, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                payment_mode = 'Cash'
                return self._default_tender_values(current_grand_total, payment_mode)
            raw_values = None
            for method_name in ('get_data', 'get_values', 'get_tender_values', 'get_result'):
                method = getattr(dialog, method_name, None)
                if callable(method):
                    raw_values = method()
                    break
            if raw_values is None:
                raw_values = {'cash_received': getattr(dialog, 'cash_received', 0.0), 'payment_mode': getattr(dialog, 'payment_mode', 'Cash'), 'balance_returned': getattr(dialog, 'balance_returned', 0.0), 'bill_amount': getattr(dialog, 'bill_amount', current_grand_total)}
            values = self._normalize_cash_tender_values(raw_values, current_grand_total)
            self.current_payment_mode = values['payment_mode']
            return values
        except Exception as exc:
            print(f'Cash Tender collection error: {exc}')
            return None

    def _handle_cash_tender_after_save(self, saved_bill_no, current_grand_total, tender_values=None):
        """Record accepted Cash Tender history after sale save completes."""
        try:
            if not saved_bill_no:
                return
            if not hasattr(self.db, 'save_cash_tender'):
                return
            if not tender_values:
                return
            cash_received = self._safe_float(tender_values.get('cash_received'), 0.0)
            if cash_received <= 0:
                return
            bill_amount = self._safe_float(tender_values.get('bill_amount'), current_grand_total)
            balance_returned = self._safe_float(tender_values.get('balance_returned'), 0.0)
            payment_mode = (tender_values.get('payment_mode') or 'Cash').strip() or 'Cash'
            self.db.save_cash_tender(saved_bill_no, bill_amount, cash_received, balance_returned, payment_mode)
        except Exception as exc:
            print(f'Cash Tender post-save handling error: {exc}')

    def save(self, is_manual: bool=True):
        if not is_manual:
            print('[DEBUG] Save blocked: Not a manual trigger')
            return
        if self._is_loading:
            print('[DEBUG] Save blocked: Voucher is loading.')
            return
        if self._is_saving:
            print('[DEBUG] Save blocked: Already saving.')
            return
        self.items_table.blockSignals(True)
        if hasattr(self, 'ok_btn'):
            self.ok_btn.blockSignals(True)
        self._is_saving = True
        try:
            if self._is_debug_calculation_enabled():
                print(f'[SalesEntry.save] Starting save for current_sale_id={self.current_sale_id}')
            active_company = active_company_manager.get_active_company()
            if not active_company:
                QMessageBox.warning(self, 'No Active Company', 'Please open a company first.')
                return
            customer_name = self.customer_name_input.text().strip()
            ui_sales_type = (self.sales_type_combo.currentText() or '').strip()
            sales_type_lc = ui_sales_type.lower()
            is_non_taxable_bill = bool(hasattr(self, 'non_taxable_checkbox') and self.non_taxable_checkbox.isChecked())
            if sales_type_lc != 'cash' and (not customer_name):
                QMessageBox.warning(self, 'Please select customer', 'Please select a customer for a Credit bill.')
                return
            if self.items_table.rowCount() == 0:
                QMessageBox.warning(self, 'Validation Error', 'Please add at least one item.')
                return
            for row in range(self.items_table.rowCount()):
                if row >= len(self.sale_items):
                    continue
                row_meta = self.sale_items[row] or {}
                product_id = row_meta.get('product_id')
                if not product_id:
                    continue
                qty = self._safe_float(self.items_table.item(row, 8).text() if self.items_table.item(row, 8) else '0', 0.0)
                if qty <= 0:
                    QMessageBox.warning(self, 'Validation Error', f'Row {row + 1}: Quantity must be greater than 0. Please enter a valid quantity.')
                    self.items_table.setCurrentCell(row, 8)
                    self.items_table.editItem(self.items_table.item(row, 8))
                    return
                if hasattr(self, 'check_stock_tick') and self.check_stock_tick.isChecked():
                    available_stock = max(0.0, self._available_stock_for_product(product_id))
                    if qty > available_stock:
                        item_name = self.items_table.item(row, 1).text() if self.items_table.item(row, 1) else 'selected item'
                        QMessageBox.warning(self, 'Out of Stock', f'Row {row + 1} ({item_name}) is invalid. Out of Stock! Available balance is only: {available_stock:.3f}. You cannot enter a quantity greater than available stock.')
                        self.items_table.setCurrentCell(row, 8)
                        self.items_table.editItem(self.items_table.item(row, 8))
                        return
            use_specific = bool(hasattr(self, 'invoice_checkbox') and self.invoice_checkbox.isChecked())
            typed = self.invoice_no_input.text().strip()
            if use_specific:
                if not typed:
                    QMessageBox.warning(self, 'Invoice Number Required', "'Entry with Specific Invoice No.' is ticked. Please enter an invoice number.")
                    self.invoice_no_input.setFocus()
                    return
            self.calculate_totals()
            calculated_totals = self.calculate_totals()
            if calculated_totals is None:
                calculated_totals = {'grand_total': 0.0}
            final_grand_total = calculated_totals.get('grand_total', 0.0)
            is_cash_sale = sales_type_lc in ('cash', 'sales', 'sale')
            if is_cash_sale and (not self._amt_recvd_user_edited):
                self.amount_receive_input.setText(f'{final_grand_total:.2f}')
                amount_received = final_grand_total
                print('FINAL GRAND TOTAL =', final_grand_total)
                print('FINAL AMOUNT RECEIVED =', amount_received)
            else:
                amount_received = self._safe_float(self.amount_receive_input.text(), 0.0)
                print('FINAL GRAND TOTAL =', final_grand_total)
                print('FINAL AMOUNT RECEIVED =', amount_received)

            def _cell_float(r, c, default=0.0):
                try:
                    it = self.items_table.item(r, c)
                    if it is None:
                        return default
                    return self._safe_float(it.text(), default)
                except Exception:
                    return default
            sale_items = []
            for row in range(self.items_table.rowCount()):
                if row >= len(self.sale_items):
                    continue
                row_meta = self.sale_items[row] or {}
                product_id = row_meta.get('product_id')
                qty = _cell_float(row, 8)
                if not product_id or qty <= 0:
                    continue
                cgst_amount = 0.0 if is_non_taxable_bill else row_meta.get('cgst_amount', 0.0)
                sgst_amount = 0.0 if is_non_taxable_bill else row_meta.get('sgst_amount', 0.0)
                igst_amount = 0.0 if is_non_taxable_bill else row_meta.get('igst_amount', 0.0)
                cess_amount = 0.0 if is_non_taxable_bill else row_meta.get('cess_amount', 0.0)
                tax_percent = 0.0 if is_non_taxable_bill else row_meta.get('tax_percent', 0.0)
                cgst_percent = 0.0 if is_non_taxable_bill else _cell_float(row, 3)
                sgst_percent = 0.0 if is_non_taxable_bill else _cell_float(row, 4)
                igst_percent = 0.0 if is_non_taxable_bill else _cell_float(row, 5)
                cess_percent = 0.0 if is_non_taxable_bill else _cell_float(row, 6)
                tax_amount = 0.0 if is_non_taxable_bill else _cell_float(row, 12)
                sale_items.append({'sl_no': len(sale_items) + 1, 'product_id': product_id, 'hsn': row_meta.get('hsn', ''), 'tax_percent': tax_percent, 'cgst': cgst_percent, 'sgst': sgst_percent, 'igst': igst_percent, 'cess': cess_percent, 'cgst_amount': cgst_amount, 'sgst_amount': sgst_amount, 'igst_amount': igst_amount, 'cess_amount': cess_amount, 'rate': row_meta.get('rate', 0.0), 'quantity': qty, 'gross_value': _cell_float(row, 9), 'discount': _cell_float(row, 10), 'net_value': _cell_float(row, 11), 'tax_amount': tax_amount, 'grand_total': _cell_float(row, 13)})
            if not sale_items:
                QMessageBox.warning(self, 'Validation Error', 'Please add at least one item with a product and quantity.')
                return
            tender_values = self._collect_cash_tender_values(final_grand_total)
            if tender_values is None:
                return {'success': False, 'cancelled': True, 'message': 'Cash Tender cancelled'}
            payment_mode = (tender_values.get('payment_mode') or self._current_payment_mode()).strip() or 'Cash'
            self.current_payment_mode = payment_mode
            amount_received = self._resolve_ledger_amount_received(final_grand_total, sales_type_lc)
            if hasattr(self, 'amount_receive_input'):
                self.amount_receive_input.setText(f'{amount_received:.2f}')
            party_id = self._resolve_party_id(customer_name, ui_sales_type, active_company['id'])
            if not party_id:
                QMessageBox.warning(self, 'Customer Error', 'Could not resolve/create the customer party.')
                return
            db_sales_type_map = {'cash': 'Sales', 'credit': 'Credit Sales', 'return': 'Return'}
            db_sales_type = db_sales_type_map.get(sales_type_lc, 'Sales')
            if is_non_taxable_bill:
                db_sales_type = 'Bill of Supply'
            if use_specific:
                invoice_number = typed
            elif self.current_sale_id and typed:
                invoice_number = typed
            else:
                invoice_number = self._generate_unique_invoice_number(active_company['id'])
            print('### SALES SAVE START ###')
            print('### VALIDATION BYPASSED ###')
            print('### SAVE PAYLOAD BUILT ###')
            sale_data = {'invoice_number': invoice_number, 'invoice_date': qdate_to_db(self.date_input.date()), 'party_id': party_id, 'sales_type': db_sales_type, 'bill_series': self.series_input.text(), 'nature': self.nature_combo.currentText(), 'due_date': qdate_to_db(self.due_date_input.date()), 'address': self.address_input.text(), 'gstin': self.gstin_input.text(), 'state': self.state_combo.currentText(), 'sales_rate': self.rate_selector_combo.currentText() if hasattr(self, 'rate_selector_combo') else 'Sales Rate', 'narration': self.narration_input.text(), 'salesman': self.salesman_combo.currentText().strip() if hasattr(self, 'salesman_combo') else '', 'form_of_sale': self.form_of_sale_combo.currentText() if hasattr(self, 'form_of_sale_combo') else 'B2CS', 'sub_total': calculated_totals.get('sub_total', 0.0), 'discount_total': float(getattr(self, '_row_discount_total', 0.0) or 0.0) + self._safe_float(self.discount_total_input.text(), 0.0), 'tax_total': 0.0 if is_non_taxable_bill else calculated_totals.get('tax_total', 0.0), 'round_off': calculated_totals.get('round_off_val', 0.0), 'grand_total': final_grand_total, 'amount_received': amount_received, 'payment_mode': payment_mode}
            print('### ENGINE SAVE START ###')
            max_retries = 3
            for attempt in range(max_retries):
                print(f'Engine save attempt {attempt + 1}')
                result = self.sales_logic.save_sale(active_company['id'], sale_data, sale_items, self.current_sale_id)
                if result['success']:
                    print('### ENGINE SAVE SUCCESS ###')
                    break
                error_msg = result.get('message', '').lower()
                if 'duplicate' in error_msg or ('invoice' in error_msg and 'exists' in error_msg):
                    if not use_specific and (not self.current_sale_id):
                        invoice_number = self._generate_unique_invoice_number(active_company['id'])
                        sale_data['invoice_number'] = invoice_number
                        continue
                    else:
                        QMessageBox.warning(self, 'Invoice Number Conflict', f"The invoice number '{invoice_number}' is already in use.\n\nPlease choose a different number or uncheck 'Entry with Specific Invoice No.' to auto-generate.")
                        return
                else:
                    break
            if result['success']:
                new_sale_id = None
                data = result.get('data')
                if isinstance(data, dict):
                    new_sale_id = data.get('sale_id')
                try:
                    affected_product_ids = {item.get('product_id') for item in sale_items if item.get('product_id')}
                    self.update_affected_products_stock(affected_product_ids)
                except Exception:
                    pass
                if tender_values:
                    self._handle_cash_tender_after_save(invoice_number, final_grand_total, tender_values)
                saved_sale_id = new_sale_id or self.current_sale_id
                if saved_sale_id:
                    print_reply = QMessageBox.question(self, 'Bill Saved', 'Bill saved successfully!\n\nDo you want to print the bill?', QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                    if print_reply == QMessageBox.Yes:
                        self._silent_print_saved_sales_receipt(active_company['id'], saved_sale_id)
                self.clear_form()
                from ui.dashboard_refresh import request_dashboard_refresh
                request_dashboard_refresh()
                return {'success': True, 'sale_id': new_sale_id, 'invoice_number': invoice_number}
            else:
                QMessageBox.warning(self, 'Error', result['message'])
                return {'success': False, 'message': result.get('message', '')}
        except sqlite3.Error as e:
            import traceback
            tb = traceback.format_exc()
            print('[SalesEntry.save] DATABASE EXCEPTION:\n' + tb)
            QMessageBox.critical(self, 'Database Error', f'Failed to save sale: {str(e)}')
            return {'success': False, 'message': str(e)}
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print('[SalesEntry.save] EXCEPTION:\n' + tb)
            QMessageBox.critical(self, 'Error', f'Failed to save sale: {type(e).__name__}: {e}\n\n(Details have been printed to the console.)')
        finally:
            self._is_saving = False
            self.items_table.blockSignals(False)
            if hasattr(self, 'ok_btn'):
                self.ok_btn.blockSignals(False)

    def closeEvent(self, event):
        """Handle window close event to notify parent."""
        if not self._confirm_close_with_unsaved_guard(event):
            return
        self.window_closed.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F1:
            target_row = self.last_barcode_filled_row
            if target_row < 0 or target_row >= self.items_table.rowCount():
                target_row = self.items_table.currentRow()
            if target_row >= 0:
                self._scroll_row_into_view(target_row)
                if target_row < len(self.sale_items):
                    product_id = self.sale_items[target_row].get('product_id')
                    product = self.products_dict.get(product_id) if product_id else None
                    if product:
                        self._update_top_bar_for_product(product)
                qty_item = self.items_table.item(target_row, 8)
                if qty_item:
                    self.items_table.editItem(qty_item)
            return
        super().keyPressEvent(event)