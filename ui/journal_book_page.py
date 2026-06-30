"""
Journal Book page.
Read-only accounting book view for Journal vouchers.
"""
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QDate, QStringListModel, QObject, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QCompleter, QDateEdit, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from db import Database
from bizora_core.journal_book_logic import JournalBookLogic, safe_float
from bizora_core.ledger_logic import LedgerLogic
from ui import theme
from ui.book_report_common import add_labeled_filter_rows, attach_filter_action_row, compact_date_style, compact_input_style, compact_label_style, compact_primary_button_style, compact_topbar_frame_style, create_filter_action_layout, page_background_style, page_heading_style, report_summary_label_style
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class JournalBookWorker(QObject):
    """Load Journal Book rows outside the GUI thread."""
    data_ready = Signal(list)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type, db_path, company_id, from_date, to_date, filters):
        """Store immutable report inputs for background loading."""
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id
        self.from_date = from_date
        self.to_date = to_date
        self.filters = dict(filters or {})

    def run(self):
        """Fetch Journal Book data using a worker-owned database connection."""
        worker_db = None
        try:
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            rows = JournalBookLogic(worker_db).get_journal_book_data(self.company_id, self.from_date, self.to_date, self.filters)
            self.data_ready.emit(rows)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                try:
                    worker_db.force_disconnect()
                except Exception:
                    pass
            self.finished.emit()

class JournalBookPageWidget(UiMemoryMixin, QWidget):
    """UI page for Journal Book - read-only view of Journal vouchers."""
    journal_entry_requested = Signal(int)
    ACCOUNT_TYPES = [('General', 'general'), ('Sundry Debtors', 'sundry_debtors'), ('Sundry Creditors', 'sundry_creditors')]

    def __init__(self, db: Optional[Database]=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.logic = JournalBookLogic(self.db)
        self.ledger_logic = LedgerLogic(self.db)
        self.company_id: Optional[int] = None
        self.current_rows: List[Dict[str, Any]] = []
        self.account_data: List[Dict[str, Any]] = []
        self.account_options: List[Dict[str, Any]] = []
        self.selected_account_data: Optional[Dict[str, Any]] = None
        self.account_model = QStringListModel([])
        self._loading = False
        self._report_thread = None
        self._report_worker = None
        self._build_ui()
        self.refresh()
        self._init_ui_memory()

    def _build_ui(self):
        """Build the Journal Book UI."""
        self.setStyleSheet(page_background_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QLabel('Journal Book')
        header.setStyleSheet(page_heading_style(22))
        root.addWidget(header)
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QGridLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setHorizontalSpacing(8)
        filter_layout.setVerticalSpacing(6)
        self.from_date = QDateEdit()
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        self.to_date = QDateEdit()
        self.to_date.setDate(QDate.currentDate())
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        self.account_type_combo = QComboBox()
        self.account_type_combo.setStyleSheet(compact_input_style())
        self.account_type_combo.setFixedWidth(130)
        for name, value in self.ACCOUNT_TYPES:
            self.account_type_combo.addItem(name, value)
        self.account_type_combo.currentIndexChanged.connect(self.on_account_type_changed)
        theme.apply_combo_dropdown_theme(self.account_type_combo)
        self.account_filter = QComboBox()
        self.account_filter.setEditable(True)
        self.account_filter.setPlaceholderText('All Accounts')
        self.account_filter.setStyleSheet(compact_input_style())
        self.account_filter.setMinimumWidth(180)
        self.account_filter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.account_completer = QCompleter(self.account_model, self.account_filter)
        self.account_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.account_completer.setFilterMode(Qt.MatchContains)
        theme.wire_editable_combo_completer(self.account_filter, self.account_completer)
        self.account_filter.setMaxVisibleItems(25)
        self.account_filter.view().setMinimumWidth(420)
        self.account_filter.currentIndexChanged.connect(self.on_account_selection_changed)
        self.account_filter.lineEdit().returnPressed.connect(self.load_report)
        self.voucher_no_search = QLineEdit()
        self.voucher_no_search.setPlaceholderText('Voucher No')
        self.voucher_no_search.setStyleSheet(compact_input_style())
        self.voucher_no_search.setFixedWidth(80)
        self.voucher_no_search.returnPressed.connect(self.load_report)
        self.narration_search = QLineEdit()
        self.narration_search.setPlaceholderText('Narration Search')
        self.narration_search.setStyleSheet(compact_input_style())
        self.narration_search.setFixedWidth(120)
        self.narration_search.returnPressed.connect(self.load_report)
        self.load_btn = QPushButton('Load')
        self.refresh_btn = QPushButton('Refresh')
        self.load_btn.clicked.connect(self.load_report)
        self.refresh_btn.clicked.connect(self.refresh)
        add_labeled_filter_rows(filter_layout, [[('From', self.from_date), ('To', self.to_date), ('Account Type', self.account_type_combo), ('Account', self.account_filter)], [('Voucher No', self.voucher_no_search), ('Narration', self.narration_search)]])
        action_layout = create_filter_action_layout([self.load_btn, self.refresh_btn])
        attach_filter_action_row(filter_layout, action_layout, row=4)
        root.addWidget(filter_frame)
        self.summary_label = QLabel('Ready')
        self.summary_label.setStyleSheet(report_summary_label_style())
        root.addWidget(self.summary_label)
        self.table = QTableWidget()
        apply_read_only_report_table_selection(self.table)
        self.table.itemDoubleClicked.connect(self.on_row_double_clicked)
        root.addWidget(self.table)

    def refresh(self):
        """Refresh data and filters."""
        from config import active_company_manager
        self.company_id = active_company_manager.get_active_company_id()
        if not self.company_id:
            self.show_no_data('Please open a company first.')
            return
        self.populate_account_options()
        self.load_report()

    def on_account_type_changed(self):
        """Handle account type combo box change."""
        self.populate_account_options()
        self.load_report()

    def on_account_selection_changed(self):
        """Handle account selection change."""
        if self.account_filter.currentIndex() >= 0 and self.account_filter.currentIndex() < len(self.account_options):
            self.selected_account_data = self.account_options[self.account_filter.currentIndex()]
        else:
            self.selected_account_data = None

    def populate_account_options(self):
        """Populate account options with active non-system ledger accounts."""
        if not self.company_id:
            self.account_options = []
            self.selected_account_data = None
            self.account_filter.clear()
            self.account_model.setStringList([])
            self.account_filter.setEnabled(False)
            return
        self.account_filter.setEnabled(True)
        account_type = self.account_type_combo.currentData()
        self.account_options = []
        self.selected_account_data = None
        try:
            self.ledger_logic.ensure_system_accounts(self.company_id)
            rows = self.logic.get_account_choices(self.company_id) or []
        except Exception as exc:
            print(f'Error loading Journal Book account filter options: {exc}')
            rows = []
        if account_type == 'general':
            self.account_options.append({'label': 'All General Accounts', 'id': None, 'kind': 'all_general'})
            general_rows = [row for row in rows if (row.get('account_type') or '').lower() != 'party']
            for row in sorted(general_rows, key=lambda item: (item.get('account_name') or '').lower()):
                self.account_options.append({'label': row.get('account_name') or row.get('name') or '', 'id': row.get('id'), 'kind': 'general'})
        elif account_type == 'sundry_debtors':
            self.account_options.append({'label': 'All Debtors', 'id': None, 'kind': 'all_debtors'})
            debtor_rows = [row for row in rows if (row.get('account_type') or '').lower() == 'party' and (row.get('party_type') or '').lower() in {'debitor', 'debtor', 'both'}]
            for row in sorted(debtor_rows, key=lambda item: (item.get('account_name') or '').lower()):
                self.account_options.append({'label': row.get('account_name') or row.get('name') or '', 'id': row.get('id'), 'party_id': row.get('party_id'), 'kind': 'debtor'})
        elif account_type == 'sundry_creditors':
            self.account_options.append({'label': 'All Creditors', 'id': None, 'kind': 'all_creditors'})
            creditor_rows = [row for row in rows if (row.get('account_type') or '').lower() == 'party' and (row.get('party_type') or '').lower() in {'creditor', 'both'}]
            for row in sorted(creditor_rows, key=lambda item: (item.get('account_name') or '').lower()):
                self.account_options.append({'label': row.get('account_name') or row.get('name') or '', 'id': row.get('id'), 'party_id': row.get('party_id'), 'kind': 'creditor'})
        else:
            self.account_options.append({'label': 'All Accounts', 'id': None, 'kind': 'all'})
            for row in sorted(rows, key=lambda item: (item.get('account_name') or '').lower()):
                self.account_options.append({'label': row.get('account_name') or row.get('name') or '', 'id': row.get('id'), 'kind': row.get('account_type', '').lower()})
        self.account_filter.blockSignals(True)
        self.account_filter.clear()
        labels = [opt.get('label', '') for opt in self.account_options]
        self.account_filter.addItems(labels)
        self.account_model.setStringList(labels)
        if self.account_options:
            self.account_filter.setCurrentIndex(0)
            self.selected_account_data = self.account_options[0]
        self.account_filter.blockSignals(False)

    def load_report(self):
        """Load Journal Book data based on filters."""
        if self._loading:
            return
        if not self.company_id:
            return
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        filters = {}
        account_type = self.account_type_combo.currentData()
        if account_type and account_type != 'general':
            filters['account_type'] = account_type
        if self.selected_account_data and self.selected_account_data.get('id'):
            filters['account_id'] = self.selected_account_data.get('id')
        elif self.account_filter.currentText().strip() and self.account_filter.currentText().strip() != 'All Accounts':
            account_text = self.account_filter.currentText().strip()
            account = next((a for a in self.account_options if a['label'] == account_text), None)
            if account and account.get('id'):
                filters['account_id'] = account.get('id')
        voucher_no = self.voucher_no_search.text().strip()
        if voucher_no:
            filters['voucher_no'] = voucher_no
        narration_search = self.narration_search.text().strip()
        if narration_search:
            filters['narration_search'] = narration_search
        thread = QThread(self)
        worker = JournalBookWorker(getattr(self.db, 'db_type', None), getattr(self.db, 'db_path', None), self.company_id, from_date, to_date, filters)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(self._on_report_ready)
        worker.error.connect(self._on_report_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_report_finished)
        self._report_thread = thread
        self._report_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _set_loading_state(self, is_loading: bool):
        """Disable filters while Journal Book data is loading."""
        self._loading = is_loading
        controls = [self.from_date, self.to_date, self.account_type_combo, self.account_filter, self.voucher_no_search, self.narration_search, self.load_btn, self.refresh_btn]
        for control in controls:
            control.setEnabled(not is_loading)
        self.load_btn.setText('Loading...' if is_loading else 'Load')
        if is_loading:
            self.summary_label.setText('Loading Journal Book...')
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(['Loading'])
            self.table.setItem(0, 0, QTableWidgetItem('Loading Journal Book data...'))

    def _on_report_ready(self, rows: List[Dict[str, Any]]):
        """Populate Journal Book data on the GUI thread."""
        self.current_rows = rows
        total_amount = sum((safe_float(row.get('amount')) for row in self.current_rows))
        self.populate_table(self.current_rows)
        self.summary_label.setText(f'Total Records: {len(self.current_rows)} | Total Amount: ₹{total_amount:,.2f}')

    def _on_report_error(self, message: str):
        """Display worker errors without freezing the GUI thread."""
        self.current_rows = []
        self.show_no_data(f'Failed to load Journal Book: {message}')
        self.summary_label.setText('Journal Book loading failed.')

    def _on_report_finished(self):
        """Clear worker references and restore Journal Book controls."""
        self._report_thread = None
        self._report_worker = None
        self._set_loading_state(False)

    def populate_table(self, data: List[Dict[str, Any]]):
        """Populate table with Journal Book data."""
        columns = ['Date', 'Voucher No', 'Debit Accounts', 'Credit Accounts', 'Amount', 'Narration']
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(data))
        for row_idx, row_data in enumerate(data):
            date_item = QTableWidgetItem(format_display_date(row_data.get('date', '')))
            date_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 0, date_item)
            voucher_no_item = QTableWidgetItem(str(row_data.get('voucher_no', '')))
            voucher_no_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 1, voucher_no_item)
            debit_accounts = str(row_data.get('debit_accounts', '')).replace(',', ', ')
            debit_item = QTableWidgetItem(debit_accounts)
            self.table.setItem(row_idx, 2, debit_item)
            credit_accounts = str(row_data.get('credit_accounts', '')).replace(',', ', ')
            credit_item = QTableWidgetItem(credit_accounts)
            self.table.setItem(row_idx, 3, credit_item)
            amount = safe_float(row_data.get('amount'))
            amount_item = QTableWidgetItem(f'₹{amount:,.2f}')
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 4, amount_item)
            narration = str(row_data.get('narration', ''))
            if row_data.get('remark'):
                narration += f" [{row_data.get('remark')}]"
            narration_item = QTableWidgetItem(narration)
            self.table.setItem(row_idx, 5, narration_item)
        apply_adjustable_table_columns(self.table)

    def on_row_double_clicked(self, item):
        """Handle double-click on table row to open related Journal entry."""
        row = item.row()
        if row < 0 or row >= len(self.current_rows):
            return
        row_data = self.current_rows[row]
        voucher_id = row_data.get('voucher_no')
        if voucher_id:
            print(f'[DEBUG] Opening Journal entry: ID={voucher_id}')
            self.journal_entry_requested.emit(voucher_id)

    def show_no_data(self, message: str):
        """Show no data message in table."""
        self.table.setRowCount(1)
        self.table.setColumnCount(1)
        item = QTableWidgetItem(message)
        item.setForeground(QColor('#fbbf24'))
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(0, 0, item)
        self.table.setSpan(0, 0, 1, 1)
        self.summary_label.setText('No data available')