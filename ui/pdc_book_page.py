"""
PDC Book page.
Read-only unified book view for PDC Issue and Receipt.
"""
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QDate, QStringListModel, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QCompleter, QDateEdit, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from db import Database
from bizora_core.pdc_book_logic import PDCBookLogic, safe_float
from ui import theme
from ui.book_report_common import add_labeled_filter_rows, attach_filter_action_row, compact_combo_style, compact_date_style, compact_input_style, compact_label_style, compact_primary_button_style, compact_topbar_frame_style, create_filter_action_layout, page_background_style, page_heading_style, report_summary_label_style
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class PDCBookPageWidget(UiMemoryMixin, QWidget):
    """UI page for PDC Book - unified view of PDC Issue and Receipt."""
    pdc_entry_requested = Signal(str, int)

    def __init__(self, db: Optional[Database]=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.logic = PDCBookLogic(self.db)
        self.company_id: Optional[int] = None
        self.current_rows: List[Dict[str, Any]] = []
        self.party_data: List[Dict[str, Any]] = []
        self.bank_data: List[Dict[str, Any]] = []
        self.party_model = QStringListModel([])
        self.bank_model = QStringListModel([])
        self._build_ui()
        self.refresh()
        self._init_ui_memory()

    def _build_ui(self):
        """Build the PDC Book UI."""
        self.setStyleSheet(page_background_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QLabel('PDC Book')
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
        self.type_filter = QComboBox()
        self.type_filter.addItems(['All', 'Issue', 'Receipt'])
        self.type_filter.setStyleSheet(compact_combo_style())
        self.type_filter.setFixedWidth(80)
        theme.apply_combo_dropdown_theme(self.type_filter)
        self.party_filter = QLineEdit()
        self.party_filter.setPlaceholderText('All Parties')
        self.party_filter.setStyleSheet(compact_input_style())
        self.party_filter.setMinimumWidth(120)
        self.party_filter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.party_completer = QCompleter(self.party_model, self.party_filter)
        self.party_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.party_completer.setFilterMode(Qt.MatchContains)
        theme.wire_line_edit_completer(self.party_filter, self.party_completer)
        self.party_filter.returnPressed.connect(self.load_report)
        self.status_filter = QComboBox()
        self.status_filter.addItems(['All', 'Pending', 'Cleared', 'Bounced', 'Cancelled'])
        self.status_filter.setStyleSheet(compact_combo_style())
        self.status_filter.setFixedWidth(90)
        theme.apply_combo_dropdown_theme(self.status_filter)
        self.bank_filter = QLineEdit()
        self.bank_filter.setPlaceholderText('All Banks')
        self.bank_filter.setStyleSheet(compact_input_style())
        self.bank_filter.setMinimumWidth(120)
        self.bank_filter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.bank_completer = QCompleter(self.bank_model, self.bank_filter)
        self.bank_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.bank_completer.setFilterMode(Qt.MatchContains)
        theme.wire_line_edit_completer(self.bank_filter, self.bank_completer)
        self.bank_filter.returnPressed.connect(self.load_report)
        self.voucher_no_search = QLineEdit()
        self.voucher_no_search.setPlaceholderText('Voucher No')
        self.voucher_no_search.setStyleSheet(compact_input_style())
        self.voucher_no_search.setFixedWidth(80)
        self.load_btn = QPushButton('Load')
        self.refresh_btn = QPushButton('Refresh')
        for btn in (self.load_btn, self.refresh_btn):
            btn.setStyleSheet(compact_primary_button_style())
        self.load_btn.clicked.connect(self.load_report)
        self.refresh_btn.clicked.connect(self.refresh)
        add_labeled_filter_rows(filter_layout, [[('Due Date Range From', self.from_date), ('Due Date Range To', self.to_date), ('Type', self.type_filter), ('Party', self.party_filter)], [('Status', self.status_filter), ('Bank', self.bank_filter), ('Voucher No', self.voucher_no_search)]])
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
        self.party_data = self.logic.get_party_choices(self.company_id)
        self.bank_data = self.logic.get_bank_choices(self.company_id)
        self.party_model.setStringList([p.get('name', '') for p in self.party_data if p.get('name')])
        self.bank_model.setStringList([b.get('account_name', '') for b in self.bank_data if b.get('account_name')])
        self.load_report()

    def load_report(self):
        """Load PDC book data based on filters."""
        if not self.company_id:
            return
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        filters = {}
        type_filter = self.type_filter.currentText()
        if type_filter != 'All':
            filters['transaction_type'] = 'ISSUE' if type_filter == 'Issue' else 'RECEIPT'
        status_filter = self.status_filter.currentText()
        if status_filter != 'All':
            filters['status'] = status_filter.upper()
        party_filter = self.party_filter.text().strip()
        if party_filter and party_filter != 'All Parties':
            party = next((p for p in self.party_data if p.get('name') == party_filter), None)
            if party:
                filters['party_id'] = party.get('id')
        bank_filter = self.bank_filter.text().strip()
        if bank_filter and bank_filter != 'All Banks':
            bank = next((b for b in self.bank_data if b.get('account_name') == bank_filter), None)
            if bank:
                filters['bank_account_id'] = bank.get('id')
        voucher_no = self.voucher_no_search.text().strip()
        if voucher_no:
            filters['voucher_no'] = voucher_no
        self.current_rows = self.logic.get_pdc_book_data(self.company_id, from_date, to_date, filters)
        self.populate_table(self.current_rows)
        total_amount = sum((safe_float(row.get('amount')) for row in self.current_rows))
        self.summary_label.setText(f'Total Records: {len(self.current_rows)} | Total Amount: ₹{total_amount:,.2f}')

    def populate_table(self, data: List[Dict[str, Any]]):
        """Populate table with PDC book data."""
        columns = ['Date', 'Voucher No', 'Type', 'Party', 'Bank', 'Cheque No', 'Amount', 'Due Date', 'Status', 'Narration']
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(data))
        for row_idx, row_data in enumerate(data):
            date_item = QTableWidgetItem(str(row_data.get('date', '')))
            date_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 0, date_item)
            voucher_no_item = QTableWidgetItem(str(row_data.get('voucher_no', '')))
            voucher_no_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 1, voucher_no_item)
            type_item = QTableWidgetItem(str(row_data.get('type', '')))
            type_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 2, type_item)
            party_item = QTableWidgetItem(str(row_data.get('party', '')))
            self.table.setItem(row_idx, 3, party_item)
            bank_item = QTableWidgetItem(str(row_data.get('bank', '')))
            self.table.setItem(row_idx, 4, bank_item)
            cheque_no_item = QTableWidgetItem(str(row_data.get('cheque_no', '')))
            cheque_no_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 5, cheque_no_item)
            amount = safe_float(row_data.get('amount'))
            amount_item = QTableWidgetItem(f'₹{amount:,.2f}')
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 6, amount_item)
            due_date_item = QTableWidgetItem(str(row_data.get('due_date', '')))
            due_date_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 7, due_date_item)
            status = str(row_data.get('status', '')).upper()
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == 'PENDING':
                status_item.setForeground(QColor('#fbbf24'))
            elif status == 'CLEARED':
                status_item.setForeground(QColor('#22c55e'))
            elif status == 'BOUNCED':
                status_item.setForeground(QColor('#ef4444'))
            elif status == 'CANCELLED':
                status_item.setForeground(QColor('#64748b'))
            self.table.setItem(row_idx, 8, status_item)
            narration_item = QTableWidgetItem(str(row_data.get('narration', '')))
            self.table.setItem(row_idx, 9, narration_item)
        apply_adjustable_table_columns(self.table)

    def on_row_double_clicked(self, item):
        """Handle double-click on table row to open related PDC entry."""
        row = item.row()
        if row < 0 or row >= len(self.current_rows):
            return
        row_data = self.current_rows[row]
        pdc_id = row_data.get('voucher_no')
        pdc_type = row_data.get('type')
        if pdc_id and pdc_type:
            print(f'[DEBUG] Opening PDC entry: Type={pdc_type}, ID={pdc_id}')
            self.pdc_entry_requested.emit(pdc_type, pdc_id)

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