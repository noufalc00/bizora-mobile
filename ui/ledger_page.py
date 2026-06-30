"""
Ledger page with three ledger types and searchable account popup.

This file intentionally keeps db.py untouched. It uses LedgerLogic for all
ledger queries and only repairs the Ledger UI/data-loading behavior.
"""
from datetime import date, timedelta
from PySide6.QtCore import Qt, QDate, QStringListModel, QObject, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QMessageBox, QAbstractItemView, QLineEdit, QDialog, QCompleter, QMenu, QFileDialog, QStyledItemDelegate, QStyle, QStyleOptionViewItem
from config import COLORS, active_company_manager
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
try:
    from config import resolve_active_company_id
except Exception:

    def resolve_active_company_id(db):
        company_id = active_company_manager.get_active_company_id()
        return int(company_id) if company_id else None
from bizora_core.ledger_logic import LedgerLogic
from bizora_core.financial_reporting_engine import FinancialReportingEngine
from bizora_core.export_engine import ExportEngine
from ui.book_report_common import compact_label_style, compact_input_style, compact_date_style, compact_primary_button_style, compact_topbar_frame_style, report_compound_entry_page_style, report_detail_dialog_style, report_page_shell_style, report_filter_frame_style, page_heading_style, report_dialog_heading_style, _report_theme_colors
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_display
from ui.report_preview_utils import table_widget_to_html
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.ui_memory import UiMemoryMixin
from ui import theme
LEDGER_TYPE_SPECS = [
    ('General', 'general', 'primary'),
    ('Cash & Bank', 'cash_bank', 'warning'),
    ('Sundry Debtors', 'sundry_debtors', 'positive'),
    ('Sundry Creditors', 'sundry_creditors', 'negative'),
]

def _resolve_ledger_color(token: str) -> str:
    """Map ledger type token to a theme-aware accent color."""
    palette = theme.chart_palette()
    return palette.get(token, palette['primary'])

class LedgerTypeItemDelegate(QStyledItemDelegate):
    """Paint each ledger-type dropdown row with theme-aware readable colors."""

    def paint(self, painter, option, index):
        """Render list items with accent cues and readable text in light/dark themes."""
        item_data = index.data(Qt.ItemDataRole.UserRole)
        accent_hex = item_data.get('color') if isinstance(item_data, dict) else None
        display_text = str(index.data(Qt.ItemDataRole.DisplayRole) or '')
        colors = theme._theme_colors()
        is_light = theme._is_light_theme()
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = option.rect

        if is_light:
            if is_selected:
                fill = QColor(accent_hex) if accent_hex else QColor(colors['focus_border'])
                text_color = QColor('#FFFFFF')
                painter.fillRect(rect, fill)
            else:
                painter.fillRect(rect, QColor(colors['table_bg']))
                if accent_hex:
                    painter.fillRect(rect.x(), rect.y(), 4, rect.height(), QColor(accent_hex))
                text_color = QColor(colors['input_text'])
            painter.setPen(text_color)
            painter.drawText(
                rect.adjusted(10, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                display_text,
            )
            return

        if accent_hex:
            accent_color = QColor(accent_hex)
            painter.fillRect(rect, accent_color)
            painter.setPen(QColor('#FFFFFF'))
        else:
            painter.fillRect(rect, QColor(colors['table_bg']))
            painter.setPen(QColor(colors['table_text']))
        painter.drawText(
            rect.adjusted(8, 0, -8, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            display_text,
        )

    def sizeHint(self, option, index):
        """Keep dropdown rows tall enough for colored labels."""
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 26))
        return size

class LedgerLoadWorker(QObject):
    """Load ledger report data on a worker-owned database connection."""
    data_ready = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type, db_path, company_id, account_data, from_date, to_date):
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id
        self.account_data = dict(account_data or {})
        self.from_date = from_date
        self.to_date = to_date

    def run(self):
        worker_db = None
        try:
            from db import Database
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            logic = LedgerLogic(worker_db)
            kind = self.account_data.get('kind', '')
            if kind == 'all_general':
                rows = logic.get_general_account_summary(self.company_id, self.from_date, self.to_date)
                self.data_ready.emit({'mode': 'summary', 'summary_kind': 'general', 'rows': rows})
            elif kind == 'all_debtors':
                rows = logic.get_debtor_summary(self.company_id, self.from_date, self.to_date)
                self.data_ready.emit({'mode': 'summary', 'summary_kind': 'debtors', 'rows': rows})
            elif kind == 'all_creditors':
                rows = logic.get_creditor_summary(self.company_id, self.from_date, self.to_date)
                self.data_ready.emit({'mode': 'summary', 'summary_kind': 'creditors', 'rows': rows})
            elif kind == 'all_cash_bank':
                rows = logic.get_cash_bank_summary(self.company_id, self.from_date, self.to_date)
                self.data_ready.emit({'mode': 'summary', 'summary_kind': 'cash_bank', 'rows': rows})
            else:
                account_id = self.account_data.get('id')
                ledger = logic.get_account_ledger(self.company_id, account_id, self.from_date, self.to_date)
                self.data_ready.emit({'mode': 'detail', 'ledger': ledger})
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                worker_db.force_disconnect()
            self.finished.emit()

class LedgerPageWidget(UiMemoryMixin, QWidget):
    """Commercial Ledger page with simplified type filter and account popup."""

    def __init__(self, db=None):
        super().__init__()
        self.db = db
        self.ledger_logic = LedgerLogic(self.db) if self.db else None
        self.reporting_engine = FinancialReportingEngine(self.db) if self.db else None
        self.company_id = resolve_active_company_id(self.db)
        self.account_options = []
        self.selected_account_data = None
        self.account_model = QStringListModel([])
        self._loading = False
        self._ledger_thread = None
        self._ledger_worker = None
        self.setup_ui()
        self.refresh()
        self._init_ui_memory()

    def showEvent(self, event):
        super().showEvent(event)
        self.company_id = resolve_active_company_id(self.db)
        if self.company_id:
            if not self.ledger_logic:
                self.ledger_logic = LedgerLogic(self.db)
            if not self.reporting_engine:
                self.reporting_engine = FinancialReportingEngine(self.db)
        self.populate_account_options()

    def setup_ui(self):
        self.setObjectName('LedgerPageWidget')
        self.setStyleSheet(self.page_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        title = QLabel('Ledger')
        title.setStyleSheet(page_heading_style(24))
        layout.addWidget(title)
        filter_frame = QFrame()
        filter_frame.setObjectName('filterFrame')
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QVBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(8)
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self.label('Type'))
        self.ledger_type_combo = QComboBox()
        self.ledger_type_combo.setFixedWidth(145)
        for name, value, token in LEDGER_TYPE_SPECS:
            accent = _resolve_ledger_color(token)
            self.ledger_type_combo.addItem(name, {'value': value, 'color': accent})
        self.ledger_type_combo.setItemDelegate(LedgerTypeItemDelegate(self.ledger_type_combo))
        theme.apply_combo_dropdown_theme(self.ledger_type_combo)
        self.ledger_type_combo.currentIndexChanged.connect(self.on_ledger_type_changed)
        top_row.addWidget(self.ledger_type_combo)
        top_row.addWidget(self.label('Account'))
        self.account_combo = QComboBox()
        self.account_combo.setStyleSheet(compact_input_style())
        self.account_combo.setFixedWidth(280)
        self.account_combo.setEditable(True)
        self.account_completer = QCompleter(self.account_model, self.account_combo)
        self.account_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.account_completer.setFilterMode(Qt.MatchContains)
        theme.wire_editable_combo_completer(self.account_combo, self.account_completer)
        self.account_combo.currentIndexChanged.connect(self.on_account_selection_changed)
        self.account_combo.setMaxVisibleItems(25)
        self.account_combo.view().setMinimumWidth(420)
        top_row.addWidget(self.account_combo)
        self.load_button = QPushButton('Load')
        self.load_button.setStyleSheet(compact_primary_button_style())
        self.load_button.clicked.connect(self.load_ledger)
        top_row.addWidget(self.load_button)
        top_row.addStretch()
        filter_layout.addLayout(top_row)
        date_row = QHBoxLayout()
        date_row.setSpacing(10)
        thirty_days_ago = date.today() - timedelta(days=30)
        date_row.addWidget(self.label('From'))
        self.from_date_edit = QDateEdit()
        self.from_date_edit.setDate(thirty_days_ago)
        prepare_report_date_edit(self.from_date_edit, style_sheet=compact_date_style())
        date_row.addWidget(self.from_date_edit)
        date_row.addWidget(self.label('To'))
        self.to_date_edit = QDateEdit()
        self.to_date_edit.setDate(date.today())
        prepare_report_date_edit(self.to_date_edit, style_sheet=compact_date_style())
        date_row.addWidget(self.to_date_edit)
        self.export_button = QPushButton('Export')
        self.export_button.setStyleSheet(compact_primary_button_style())
        self.export_button.clicked.connect(self.show_export_menu)
        date_row.addWidget(self.export_button)
        date_row.addStretch()
        filter_layout.addLayout(date_row)
        layout.addWidget(filter_frame)
        self.ledger_table = QTableWidget()
        apply_read_only_report_table_selection(self.ledger_table)
        self.ledger_table.horizontalHeader().setStretchLastSection(True)
        self.ledger_table.doubleClicked.connect(self.on_ledger_double_clicked)
        layout.addWidget(self.ledger_table, 1)
        summary_row = QHBoxLayout()
        self.opening_balance_label = self.summary_label('Opening: 0.00')
        self.total_debit_label = self.summary_label('Debit: 0.00')
        self.total_credit_label = self.summary_label('Credit: 0.00')
        summary_row.addWidget(self.opening_balance_label)
        summary_row.addWidget(self.total_debit_label)
        summary_row.addWidget(self.total_credit_label)
        summary_row.addStretch()
        layout.addLayout(summary_row)
        self.export_menu = QMenu(self)
        self.excel_action = self.export_menu.addAction('Export Excel')
        self.pdf_action = self.export_menu.addAction('Export PDF')
        self.apply_ledger_type_color()

    def page_style(self):
        c = _report_theme_colors()
        filter_extra = f" QFrame#filterFrame {{ background-color: {c['panel_bg']}; border: 1px solid {c['border']}; border-radius: 8px; }} QLabel {{ color: {c['label_text']}; background: transparent; }}"
        return report_compound_entry_page_style() + filter_extra

    def label(self, text):
        item = QLabel(text)
        item.setStyleSheet(compact_label_style())
        return item

    def summary_label(self, text):
        item = QLabel(text)
        c = _report_theme_colors()
        item.setStyleSheet(f"color: {c['input_text']}; font-weight: bold; padding: 6px 12px; background: {c['panel_bg']}; border: 1px solid {c['border']}; border-radius: 6px;")
        return item

    def current_ledger_type(self):
        data = self.ledger_type_combo.currentData()
        return data.get('value', 'general') if isinstance(data, dict) else 'general'

    def current_ledger_color(self):
        data = self.ledger_type_combo.currentData()
        return data.get('color', _resolve_ledger_color('primary')) if isinstance(data, dict) else _resolve_ledger_color('primary')

    def on_ledger_type_changed(self):
        self.apply_ledger_type_color()
        self.populate_account_options()

    def apply_ledger_type_color(self):
        """Color the closed combo with the active type; list rows use the item delegate."""
        color = self.current_ledger_color()
        panel = _report_theme_colors()
        self.ledger_type_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {color};
                color: white;
                border: 1px solid {color};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: bold;
                min-height: 24px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid rgba(255, 255, 255, 0.35);
            }}
            QComboBox QAbstractItemView {{
                background-color: {panel['input_bg']};
                color: {panel['input_text']};
                border: 1px solid {panel['border']};
                outline: none;
                selection-background-color: {panel['focus_border']};
                selection-color: #FFFFFF;
            }}
            """
        )
        theme.apply_combo_dropdown_theme(self.ledger_type_combo)

    def populate_account_options(self):
        self.company_id = resolve_active_company_id(self.db)
        self.account_options = []
        self.selected_account_data = None
        if not self.company_id:
            self.company_id = resolve_active_company_id(self.db)
        if self.company_id and (not self.ledger_logic):
            self.ledger_logic = LedgerLogic(self.db)
        if not self.company_id or not self.ledger_logic:
            self.account_combo.clear()
            self.account_model.setStringList([])
            self.account_combo.setEnabled(False)
            return
        self.account_combo.setEnabled(True)
        ledger_type = self.current_ledger_type()
        try:
            try:
                self.ledger_logic.ensure_system_accounts(self.company_id)
            except Exception:
                pass
            if ledger_type == 'general':
                self.account_options.append({'label': 'All General Accounts', 'id': None, 'kind': 'all_general'})
                rows = self.ledger_logic.get_general_ledger_accounts(self.company_id) or []
                for row in sorted(rows, key=lambda item: (item.get('account_name') or '').lower()):
                    self.account_options.append({'label': row.get('account_name') or row.get('name') or '', 'id': row.get('id'), 'kind': 'general'})
            elif ledger_type == 'cash_bank':
                self.account_options.append({'label': 'All Cash & Bank Accounts', 'id': None, 'kind': 'all_cash_bank'})
                rows = self.ledger_logic.get_cash_bank_ledger_options(self.company_id) or []
                for row in sorted(rows, key=lambda item: (item.get('account_name') or '').lower()):
                    self.account_options.append({'label': row.get('account_name') or row.get('name') or '', 'id': row.get('id'), 'kind': 'cash_bank'})
            elif ledger_type == 'sundry_debtors':
                self.account_options.append({'label': 'All Debtors', 'id': None, 'kind': 'all_debtors'})
                rows = self.ledger_logic.get_debtor_ledger_options(self.company_id) or []
                for row in sorted(rows, key=lambda item: (item.get('account_name') or '').lower()):
                    self.account_options.append({'label': row.get('account_name') or row.get('name') or '', 'id': row.get('id'), 'party_id': row.get('party_id'), 'kind': 'debtor'})
            else:
                self.account_options.append({'label': 'All Creditors', 'id': None, 'kind': 'all_creditors'})
                rows = self.ledger_logic.get_creditor_ledger_options(self.company_id) or []
                for row in sorted(rows, key=lambda item: (item.get('account_name') or '').lower()):
                    self.account_options.append({'label': row.get('account_name') or row.get('name') or '', 'id': row.get('id'), 'party_id': row.get('party_id'), 'kind': 'creditor'})
            self.account_combo.blockSignals(True)
            self.account_combo.clear()
            labels = [opt.get('label', '') for opt in self.account_options]
            self.account_model.setStringList(labels)
            for opt in self.account_options:
                self.account_combo.addItem(opt.get('label', ''), opt)
            if self.account_options:
                self.account_combo.setCurrentIndex(0)
                self.selected_account_data = self.account_options[0]
            self.account_combo.blockSignals(False)
        except Exception as exc:
            self.show_message_row(f'Error loading account list: {exc}')

    def on_account_selection_changed(self, index):
        if index >= 0:
            self.selected_account_data = self.account_combo.itemData(index)

    def set_selected_account(self, account_data, update_text=False):
        """Set the selected account from account data dictionary."""
        if not account_data:
            return
        for i, opt in enumerate(self.account_options):
            if opt.get('id') == account_data.get('id') and opt.get('kind') == account_data.get('kind'):
                self.account_combo.blockSignals(True)
                self.account_combo.setCurrentIndex(i)
                self.selected_account_data = opt
                if update_text:
                    self.account_combo.setCurrentText(account_data.get('label', ''))
                self.account_combo.blockSignals(False)
                return

    def refresh(self):
        self.company_id = resolve_active_company_id(self.db)
        if self.company_id and (not self.ledger_logic):
            self.ledger_logic = LedgerLogic(self.db)
        self.populate_account_options()
        self.reset_summary()
        self.show_message_row('Select a ledger account and click Load.')

    def load_ledger(self):
        if self._loading:
            return
        self.company_id = resolve_active_company_id(self.db)
        if not self.company_id:
            self.show_message_row('Please open a company first.')
            return
        if not self.ledger_logic:
            self.ledger_logic = LedgerLogic(self.db)
        if not self.account_options:
            self.populate_account_options()
        data = self.account_combo.currentData()
        typed_text = self.account_combo.currentText().strip()
        if not data and typed_text:
            for opt in self.account_options:
                if opt.get('label', '').lower() == typed_text.lower():
                    data = opt
                    break
            if not data:
                for opt in self.account_options:
                    if typed_text.lower() in opt.get('label', '').lower():
                        data = opt
                        break
        if not data:
            self.show_message_row('Please select a valid account.')
            return
        from_date = self.from_date_edit.date().toPython()
        to_date = self.to_date_edit.date().toPython()
        if data.get('kind', '') not in ('all_general', 'all_debtors', 'all_creditors', 'all_cash_bank') and (not data.get('id')):
            self.show_message_row('Selected account has no account id.')
            return
        self._start_ledger_worker(data, from_date, to_date)

    def _start_ledger_worker(self, data, from_date, to_date):
        thread = QThread(self)
        worker = LedgerLoadWorker(getattr(self.db, 'db_type', None), getattr(self.db, 'db_path', None), self.company_id, data, from_date, to_date)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(self._handle_ledger_result)
        worker.error.connect(lambda message: self.show_message_row(f'Error loading ledger: {message}'))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._ledger_worker_finished)
        self._ledger_thread = thread
        self._ledger_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _handle_ledger_result(self, result):
        if result.get('mode') == 'summary':
            self.populate_summary(result.get('rows', []), result.get('summary_kind', 'general'))
        else:
            self.populate_detailed(result.get('ledger', {}))

    def _set_loading_state(self, is_loading):
        self._loading = is_loading
        self.load_button.setEnabled(not is_loading)
        self.account_combo.setEnabled(not is_loading)
        self.from_date_edit.setEnabled(not is_loading)
        self.to_date_edit.setEnabled(not is_loading)
        self.load_button.setText('Loading...' if is_loading else 'Load')

    def _ledger_worker_finished(self):
        self._ledger_thread = None
        self._ledger_worker = None
        self._set_loading_state(False)

    def populate_summary(self, rows, summary_kind):
        if summary_kind == 'general':
            headers = ['SL No', 'Account Name', 'Type', 'Opening', 'Debit', 'Credit', 'Closing', 'Dr/Cr']
        elif summary_kind == 'debtors':
            headers = ['SL No', 'Debtor Name', 'Opening', 'Debit', 'Credit', 'Closing', 'Dr/Cr']
        elif summary_kind == 'cash_bank':
            headers = ['SL No', 'Cash/Bank Account', 'Opening', 'Debit', 'Credit', 'Closing', 'Dr/Cr']
        else:
            headers = ['SL No', 'Creditor Name', 'Opening', 'Debit', 'Credit', 'Closing', 'Dr/Cr']
        self.prepare_table(headers)
        if not rows:
            self.show_message_row('No ledger data found for selected account.', len(headers))
            self.reset_summary()
            return
        self.ledger_table.setRowCount(len(rows))
        total_opening = total_debit = total_credit = 0.0
        for row_index, row in enumerate(rows):
            metadata = {'mode': 'summary', 'account_id': row.get('id'), 'account_name': row.get('account_name') or row.get('name') or ''}
            self.set_cell(row_index, 0, str(row_index + 1), metadata=metadata)
            self.set_cell(row_index, 1, row.get('account_name') or row.get('name') or '')
            offset = 0
            if summary_kind == 'general':
                self.set_cell(row_index, 2, row.get('account_type', ''))
                offset = 1
            opening = self.format_balance(row.get('opening_balance', 0.0), row.get('opening_balance_type', 'Dr'))
            closing = self.format_balance(row.get('closing_balance', 0.0), row.get('closing_balance_type', 'Dr'))
            self.set_cell(row_index, 2 + offset, opening, align_right=True)
            self.set_cell(row_index, 3 + offset, self.format_amount(row.get('period_debit', 0.0)), align_right=True, color=theme.semantic_positive_hex())
            self.set_cell(row_index, 4 + offset, self.format_amount(row.get('period_credit', 0.0)), align_right=True, color=theme.semantic_negative_hex())
            self.set_cell(row_index, 5 + offset, closing, align_right=True)
            self.set_cell(row_index, 6 + offset, row.get('closing_balance_type', 'Dr'))
            total_opening += float(row.get('opening_balance') or 0.0)
            total_debit += float(row.get('period_debit') or 0.0)
            total_credit += float(row.get('period_credit') or 0.0)
        self.opening_balance_label.setText(f'Opening: {self.format_amount(total_opening)}')
        self.total_debit_label.setText(f'Debit: {self.format_amount(total_debit)}')
        self.total_credit_label.setText(f'Credit: {self.format_amount(total_credit)}')
        self.resize_table_columns()

    def populate_detailed(self, ledger):
        account = ledger.get('account') if isinstance(ledger, dict) else None
        entries = ledger.get('entries', []) if isinstance(ledger, dict) else []
        account_name = account.get('account_name', 'Selected Account') if account else 'Selected Account'
        headers = ['Date', 'Voucher Type', 'Voucher No', 'Particulars', 'Debit', 'Credit', 'Running Balance']
        self.prepare_table(headers)
        self.ledger_table.setRowCount(len(entries) + 2)
        total_debit = total_credit = 0.0
        opening = float(ledger.get('opening_balance', 0.0) if isinstance(ledger, dict) else 0.0)
        self.set_cell(0, 0, '')
        self.set_cell(0, 1, 'Opening Balance')
        self.set_cell(0, 2, '')
        self.set_cell(0, 3, account_name)
        self.set_cell(0, 4, '')
        self.set_cell(0, 5, '')
        self.set_cell(0, 6, self.format_balance(abs(opening), 'Dr' if opening >= 0 else 'Cr'), align_right=True)
        self.style_statement_row(0)
        closing = opening
        for row_index, entry in enumerate(entries, start=1):
            metadata = {'mode': 'detail', 'voucher_type': entry.get('voucher_type'), 'voucher_id': entry.get('voucher_id'), 'voucher_no': entry.get('voucher_no')}
            debit = float(entry.get('debit') or 0.0)
            credit = float(entry.get('credit') or 0.0)
            running = float(entry.get('running_balance') or 0.0)
            closing = running
            self.set_cell(row_index, 0, format_display_date(entry.get('voucher_date')), metadata=metadata)
            self.set_cell(row_index, 1, self.pretty_voucher_type(entry.get('voucher_type')))
            self.set_cell(row_index, 2, str(entry.get('voucher_no') or ''))
            self.set_cell(row_index, 3, str(entry.get('narration') or ''))
            self.set_cell(row_index, 4, self.format_amount(debit), align_right=True, color=theme.semantic_positive_hex())
            self.set_cell(row_index, 5, self.format_amount(credit), align_right=True, color=theme.semantic_negative_hex())
            self.set_cell(row_index, 6, self.format_balance(abs(running), 'Dr' if running >= 0 else 'Cr'), align_right=True)
            total_debit += debit
            total_credit += credit
        closing_row = len(entries) + 1
        self.set_cell(closing_row, 0, '')
        self.set_cell(closing_row, 1, 'Closing Balance')
        self.set_cell(closing_row, 2, '')
        self.set_cell(closing_row, 3, account_name)
        self.set_cell(closing_row, 4, '')
        self.set_cell(closing_row, 5, '')
        self.set_cell(closing_row, 6, self.format_balance(abs(closing), 'Dr' if closing >= 0 else 'Cr'), align_right=True)
        self.style_statement_row(closing_row)
        self.opening_balance_label.setText(f"Opening: {ledger.get('opening_formatted', '0.00')}")
        self.total_debit_label.setText(f'Debit: {self.format_amount(total_debit)}')
        self.total_credit_label.setText(f'Credit: {self.format_amount(total_credit)}')
        self.resize_table_columns()

    def prepare_table(self, headers):
        self.ledger_table.clear()
        self.ledger_table.setColumnCount(len(headers))
        self.ledger_table.setHorizontalHeaderLabels(headers)
        self.ledger_table.setRowCount(0)

    def show_message_row(self, message, column_count=7):
        self.ledger_table.clear()
        self.ledger_table.setColumnCount(column_count)
        self.ledger_table.setHorizontalHeaderLabels(['Message'] + [''] * (column_count - 1))
        self.ledger_table.setRowCount(1)
        item = QTableWidgetItem(message)
        item.setForeground(QColor(theme.semantic_warning_hex()))
        item.setTextAlignment(Qt.AlignCenter)
        self.ledger_table.setItem(0, 0, item)
        self.ledger_table.setSpan(0, 0, 1, column_count)
        self.ledger_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def set_cell(self, row, col, text, align_right=False, color=None, metadata=None):
        item = QTableWidgetItem(str(text))
        item.setForeground(QColor(color or theme.table_emphasis_text_hex()))
        item.setTextAlignment((Qt.AlignRight if align_right else Qt.AlignLeft) | Qt.AlignVCenter)
        if metadata is not None:
            item.setData(Qt.UserRole, metadata)
        self.ledger_table.setItem(row, col, item)

    def style_statement_row(self, row):
        palette = theme.chart_palette()
        opening_bg = palette['highlight_opening']
        closing_bg = palette['highlight_closing']
        for col in range(self.ledger_table.columnCount()):
            item = self.ledger_table.item(row, col)
            if item:
                item.setBackground(QColor(opening_bg if row == 0 else closing_bg))
                font = item.font()
                font.setBold(True)
                item.setFont(font)

    def resize_table_columns(self):
        apply_adjustable_table_columns(self.ledger_table)

    def reset_summary(self):
        self.opening_balance_label.setText('Opening: 0.00')
        self.total_debit_label.setText('Debit: 0.00')
        self.total_credit_label.setText('Credit: 0.00')

    @staticmethod
    def format_amount(value):
        try:
            return f'{float(value or 0.0):,.2f}'
        except Exception:
            return '0.00'

    @staticmethod
    def format_balance(value, balance_type):
        try:
            value = abs(float(value or 0.0))
        except Exception:
            value = 0.0
        if value < 0.001:
            return '0.00'
        return f"{value:,.2f} {balance_type or 'Dr'}"

    @staticmethod
    def pretty_voucher_type(value):
        value = str(value or '')
        return value.replace('_', ' ').title()

    def on_ledger_double_clicked(self, index):
        row = index.row()
        item = self.ledger_table.item(row, 0)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict):
            return
        if data.get('mode') == 'summary':
            account_id = data.get('account_id')
            label = data.get('account_name', '')
            if account_id:
                kind_map = {
                    'general': 'general',
                    'cash_bank': 'cash_bank',
                    'sundry_debtors': 'debtor',
                    'sundry_creditors': 'creditor',
                }
                detail_kind = kind_map.get(self.current_ledger_type(), 'general')
                self.set_selected_account({'label': label, 'id': account_id, 'kind': detail_kind}, update_text=True)
                self.load_ledger()
            return
        voucher_type = data.get('voucher_type')
        voucher_id = data.get('voucher_id')
        voucher_no = data.get('voucher_no')
        if voucher_type and voucher_id:
            self.show_voucher_detail_dialog(voucher_type, voucher_id, voucher_no)
        else:
            QMessageBox.information(self, 'No Voucher', 'No source voucher is linked with this ledger row.')

    def show_voucher_detail_dialog(self, voucher_type, voucher_id, voucher_no=None):
        details = self.load_voucher_details(voucher_type, voucher_id)
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Voucher Details - {self.pretty_voucher_type(voucher_type)}')
        dialog.setMinimumSize(760, 520)
        dialog.setStyleSheet(report_detail_dialog_style())
        layout = QVBoxLayout(dialog)
        title_row = QHBoxLayout()
        title = QLabel(f'{self.pretty_voucher_type(voucher_type)}  {voucher_no or voucher_id}')
        title.setStyleSheet(report_dialog_heading_style(18))
        title_row.addWidget(title)
        title_row.addStretch()
        open_top_button = QPushButton('Open Original / Edit Voucher')

        def open_original_from_top():
            self.open_voucher_for_edit(voucher_type, voucher_id)
            dialog.accept()
        open_top_button.clicked.connect(open_original_from_top)
        title_row.addWidget(open_top_button)
        layout.addLayout(title_row)
        info = QLabel(details.get('info', ''))
        info.setWordWrap(True)
        c = _report_theme_colors()
        info.setStyleSheet(f"background-color: {c['panel_bg']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 10px; color: {c['input_text']};")
        layout.addWidget(info)
        table = QTableWidget()
        columns = details.get('columns') or ['SL', 'Product', 'HSN', 'Qty', 'Rate', 'Tax', 'Total']
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.verticalHeader().setVisible(False)
        apply_read_only_report_table_selection(table)
        items = details.get('items', [])
        if items:
            table.setRowCount(len(items))
            for row_index, item in enumerate(items):
                if details.get('mode') == 'cash_bank':
                    values = [row_index + 1, item.get('account_name', ''), item.get('towards_voucher_no', ''), self.format_amount(item.get('amount', 0.0)), self.format_amount(item.get('discount', 0.0)), item.get('narration', '')]
                else:
                    values = [item.get('sl_no', row_index + 1), item.get('product_name', item.get('account_name', '')), item.get('hsn', ''), self.format_amount(item.get('quantity', 0.0)), self.format_amount(item.get('rate', 0.0)), self.format_amount(item.get('tax_amount', 0.0)), self.format_amount(item.get('grand_total', 0.0))]
                for col, value in enumerate(values[:len(columns)]):
                    cell = QTableWidgetItem(str(value))
                    if col >= 3 and col != len(columns) - 1:
                        cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    table.setItem(row_index, col, cell)
        else:
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem('No item rows found for this voucher.'))
            table.setSpan(0, 0, 1, len(columns))
        apply_adjustable_table_columns(table, sl_no_column=0)
        layout.addWidget(table, 1)
        button_row = QHBoxLayout()
        button_row.addStretch()
        open_button = QPushButton('Open Original / Edit Voucher')

        def open_original_and_close_detail():
            self.open_voucher_for_edit(voucher_type, voucher_id)
            dialog.accept()
        open_button.clicked.connect(open_original_and_close_detail)
        button_row.addWidget(open_button)
        close_button = QPushButton('Close')
        close_button.clicked.connect(dialog.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)
        dialog.exec()

    def load_voucher_details(self, voucher_type, voucher_id):
        if not self.db or not self.company_id:
            return {'info': 'No database or company is available.', 'items': []}
        ph = self.db._get_placeholder()
        vt = str(voucher_type or '').lower()
        config = self.voucher_table_config(vt)
        if not config:
            return {'info': 'This voucher type is not supported yet.', 'items': []}
        try:
            header_rows = self.db.execute_query(f"\n                SELECT h.*, p.name AS party_name\n                FROM {config['header_table']} h\n                LEFT JOIN parties p ON p.id = h.party_id\n                WHERE h.company_id = {ph} AND h.id = {ph}\n                ", (self.company_id, voucher_id))
            header = header_rows[0] if header_rows else {}
            if config.get('cash_bank'):
                item_rows = self.db.execute_query(f"\n                    SELECT i.*, la.account_name\n                    FROM {config['item_table']} i\n                    LEFT JOIN ledger_accounts la ON la.id = i.account_id\n                    WHERE i.{config['item_fk']} = {ph}\n                    ORDER BY i.id\n                    ", (voucher_id,))
                info = self.format_voucher_info(config, header)
                return {'info': info, 'items': [dict(row) for row in item_rows] if item_rows else [], 'mode': 'cash_bank', 'columns': ['SL', 'Account', 'Towards V.No.', 'Amount', 'Discount', 'Narration']}
            if not config['item_table']:
                info = self.format_voucher_info(config, header)
                return {'info': info, 'items': []}
            if vt in ('journal', 'journal_entry'):
                item_rows = self.db.execute_query(f"\n                    SELECT i.*, la.account_name\n                    FROM {config['item_table']} i\n                    LEFT JOIN ledger_accounts la ON la.id = i.account_id\n                    WHERE i.{config['item_fk']} = {ph}\n                    ORDER BY i.sl_no, i.id\n                    ", (voucher_id,))
            else:
                item_rows = self.db.execute_query(f"\n                    SELECT i.*, pr.name AS product_name, pr.barcode AS barcode\n                    FROM {config['item_table']} i\n                    LEFT JOIN products pr ON pr.id = i.product_id\n                    WHERE i.{config['item_fk']} = {ph}\n                    ORDER BY i.sl_no, i.id\n                    ", (voucher_id,))
            info = self.format_voucher_info(config, header)
            return {'info': info, 'items': [dict(row) for row in item_rows] if item_rows else []}
        except Exception as exc:
            return {'info': f'Error loading voucher details: {exc}', 'items': []}

    def voucher_table_config(self, voucher_type):
        configs = {'sales': {'header_table': 'sales', 'item_table': 'sales_items', 'item_fk': 'sale_id', 'no': 'invoice_number', 'date': 'invoice_date', 'total': 'grand_total', 'paid': 'amount_received'}, 'sale': {'header_table': 'sales', 'item_table': 'sales_items', 'item_fk': 'sale_id', 'no': 'invoice_number', 'date': 'invoice_date', 'total': 'grand_total', 'paid': 'amount_received'}, 'purchase': {'header_table': 'purchases', 'item_table': 'purchase_items', 'item_fk': 'purchase_id', 'no': 'purchase_number', 'date': 'purchase_date', 'total': 'grand_total', 'paid': 'amount_paid'}, 'sales_return': {'header_table': 'sales_returns', 'item_table': 'sales_return_items', 'item_fk': 'sales_return_id', 'no': 'return_no', 'date': 'return_date', 'total': 'grand_total', 'paid': 'amount_refunded_or_adjusted'}, 'purchase_return': {'header_table': 'purchase_returns', 'item_table': 'purchase_return_items', 'item_fk': 'purchase_return_id', 'no': 'return_no', 'date': 'return_date', 'total': 'grand_total', 'paid': 'amount_received_or_adjusted'}, 'cash_receipt': {'header_table': 'cash_receipts', 'item_table': 'cash_receipt_items', 'item_fk': 'receipt_id', 'no': 'voucher_no', 'date': 'voucher_date', 'total': 'total_amount', 'paid': None, 'cash_bank': True}, 'cash_payment': {'header_table': 'cash_payments', 'item_table': 'cash_payment_items', 'item_fk': 'payment_id', 'no': 'voucher_no', 'date': 'voucher_date', 'total': 'total_amount', 'paid': None, 'cash_bank': True}, 'bank_receipt': {'header_table': 'bank_receipts', 'item_table': 'bank_receipt_items', 'item_fk': 'receipt_id', 'no': 'voucher_no', 'date': 'voucher_date', 'total': 'total_amount', 'paid': None, 'cash_bank': True}, 'bank_payment': {'header_table': 'bank_payments', 'item_table': 'bank_payment_items', 'item_fk': 'payment_id', 'no': 'voucher_no', 'date': 'voucher_date', 'total': 'total_amount', 'paid': None, 'cash_bank': True}, 'journal': {'header_table': 'journal_vouchers', 'item_table': 'journal_voucher_lines', 'item_fk': 'journal_id', 'no': 'voucher_no', 'date': 'voucher_date', 'total': None, 'paid': None}, 'journal_entry': {'header_table': 'journal_vouchers', 'item_table': 'journal_voucher_lines', 'item_fk': 'journal_id', 'no': 'voucher_no', 'date': 'voucher_date', 'total': None, 'paid': None}}
        return configs.get(voucher_type)

    def format_voucher_info(self, config, header):
        if not header:
            return 'Voucher header was not found.'
        lines = [f"Voucher No: {header.get(config['no'], '')}", f"Date: {format_display_date(header.get(config['date'], ''))}", f"Party: {header.get('party_name', '')}", f"Narration: {header.get('narration', '') or ''}", f"Tax Total: {self.format_amount(header.get('tax_total', 0.0))}", f"Grand Total: {self.format_amount(header.get(config['total'], 0.0) if config.get('total') else 0.0)}"]
        if config.get('paid'):
            lines.append(f"Paid / Received: {self.format_amount(header.get(config['paid'], 0.0))}")
        if hasattr(header, 'keys') and 'total_discount' in header.keys():
            lines.append(f"Discount: {self.format_amount(header.get('total_discount', 0.0))}")
        return '\n'.join(lines)

    def open_voucher_for_edit(self, voucher_type, voucher_id):
        parent = self.parent()
        while parent:
            if hasattr(parent, 'open_voucher_for_edit'):
                try:
                    parent.open_voucher_for_edit(voucher_type, voucher_id)
                    return
                except Exception as exc:
                    QMessageBox.warning(self, 'Open Original', f'Could not open original voucher: {exc}')
                    return
            parent = parent.parent()
        QMessageBox.information(self, 'Open Original', 'Original voucher opening is not connected in this window yet.')

    def show_export_menu(self):
        """Show export menu at button position. Heavy imports happen only after user picks an option."""
        pos = self.export_button.mapToGlobal(self.export_button.rect().bottomLeft())
        action = self.export_menu.exec(pos)
        if action == self.excel_action:
            self.export_excel()
        elif action == self.pdf_action:
            self.export_pdf()

    def export_excel(self):
        """Export ledger data to Excel using centralized ExportEngine."""
        if self.ledger_table.rowCount() <= 0:
            QMessageBox.information(self, 'No Data', 'Please load ledger data first.')
            return
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save Ledger', 'ledger.xlsx', 'Excel Files (*.xlsx)')
        if not file_path:
            return
        headers = []
        for col in range(self.ledger_table.columnCount()):
            header = self.ledger_table.horizontalHeaderItem(col)
            headers.append(header.text() if header else '')
        data = []
        for row in range(self.ledger_table.rowCount()):
            row_data = []
            for col in range(self.ledger_table.columnCount()):
                item = self.ledger_table.item(row, col)
                row_data.append(item.text() if item else '')
            data.append(row_data)
        export_engine = ExportEngine(self.db)
        result = export_engine.export_table_to_excel('Ledger', headers, data, file_path)
        if result['success']:
            QMessageBox.information(self, 'Export', result['message'])
        else:
            QMessageBox.critical(self, 'Export Error', result['error'])

    def export_pdf(self):
        """Open ledger data in the universal print/PDF preview dialog."""
        if self.ledger_table.rowCount() <= 0:
            QMessageBox.information(self, 'No Data', 'Please load ledger data first.')
            return
        subtitle = f"{self.ledger_type_combo.currentText()} | {self.account_combo.currentText()} | {qdate_to_display(self.from_date_edit.date())} to {qdate_to_display(self.to_date_edit.date())}"
        summary_lines = [self.opening_balance_label.text(), self.total_debit_label.text(), self.total_credit_label.text()]
        html_string = table_widget_to_html(self.ledger_table, 'Ledger', subtitle, summary_lines)
        dialog = UniversalPreviewDialog(html_string, self)
        dialog.exec()