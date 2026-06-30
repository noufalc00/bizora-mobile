"""
Read-only Statement of Account page.

Shows a party-wise chronological ledger with opening balance, period debits,
period credits, and running balance. This page performs no writes.
"""
from __future__ import annotations
import csv
import html
from datetime import date
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QStringListModel, QDate, QObject, QThread, Signal
from PySide6.QtGui import QAction, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import QAbstractItemView, QApplication, QComboBox, QCompleter, QDateEdit, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from config import active_company_manager
from db import Database
from ui import theme
from ui.book_report_common import (
    BOOK_REPORT_ACTION_BUTTON_HEIGHT,
    add_labeled_filter_rows,
    attach_filter_action_row,
    compact_date_style,
    compact_input_style,
    compact_label_style,
    compact_primary_button_style,
    compact_topbar_frame_style,
    page_heading_style,
    report_data_table_style,
    report_filter_frame_style,
    report_page_shell_style,
    report_summary_label_style,
)
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class LedgerStatementWorker(QObject):
    """Build party statement rows on a worker-owned database connection."""
    data_ready = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type, db_path, company_id, party, from_date, to_date):
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id
        self.party = dict(party or {})
        self.from_date = from_date
        self.to_date = to_date

    @staticmethod
    def _active_ledger_filter() -> str:
        return "\n              AND le.voucher_type NOT IN (\n                  'sales_void', 'purchase_void', 'sales_return_void', 'purchase_return_void',\n                  'quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote'\n              )\n              AND NOT (\n                  le.voucher_type = 'sales'\n                  AND EXISTS (\n                      SELECT 1 FROM sales s\n                      WHERE s.company_id = le.company_id\n                        AND s.id = le.voucher_id\n                        AND COALESCE(s.status, 'Active') = 'Voided'\n                  )\n              )\n              AND NOT (\n                  le.voucher_type = 'purchase'\n                  AND EXISTS (\n                      SELECT 1 FROM purchases p\n                      WHERE p.company_id = le.company_id\n                        AND p.id = le.voucher_id\n                        AND COALESCE(p.status, 'Active') = 'Voided'\n                  )\n              )\n              AND NOT (\n                  le.voucher_type = 'sales_return'\n                  AND EXISTS (\n                      SELECT 1 FROM sales_returns sr\n                      WHERE sr.company_id = le.company_id\n                        AND sr.id = le.voucher_id\n                        AND COALESCE(sr.status, 'Active') = 'Voided'\n                  )\n              )\n              AND NOT (\n                  le.voucher_type = 'purchase_return'\n                  AND EXISTS (\n                      SELECT 1 FROM purchase_returns pr\n                      WHERE pr.company_id = le.company_id\n                        AND pr.id = le.voucher_id\n                        AND COALESCE(pr.status, 'Active') = 'Voided'\n                  )\n              )\n        "

    @staticmethod
    def _signed_opening(account: Optional[Dict[str, Any]], party: Dict[str, Any]) -> float:
        if account:
            opening = float(account.get('opening_balance') or 0.0)
            opening_type = str(account.get('opening_balance_type') or 'Dr')
        else:
            opening = float(party.get('opening_balance') or 0.0)
            opening_type = 'Cr' if party.get('party_type') == 'Creditor' else 'Dr'
        return opening if opening_type == 'Dr' else -opening

    def run(self):
        worker_db = None
        try:
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            ph = worker_db._get_placeholder()
            account_rows = worker_db.execute_query(f'\n                SELECT id, account_name, opening_balance, opening_balance_type, group_name\n                FROM ledger_accounts\n                WHERE company_id = {ph}\n                  AND account_type = {ph}\n                  AND account_name = {ph}\n                  AND is_active = 1\n                ', (self.company_id, 'party', self.party.get('name')))
            account = dict(account_rows[0]) if account_rows else None
            opening_base = self._signed_opening(account, self.party)
            account_id = int(account.get('id')) if account else None
            if not account_id:
                self.data_ready.emit({'party': self.party, 'opening': opening_base, 'closing': opening_base, 'entries': []})
                return
            opening_rows = worker_db.execute_query(f'\n                SELECT COALESCE(SUM(le.debit), 0.0) AS debit_total,\n                       COALESCE(SUM(le.credit), 0.0) AS credit_total\n                FROM ledger_entries le\n                WHERE le.company_id = {ph}\n                  AND le.account_id = {ph}\n                  AND le.voucher_date < {ph}\n                  {self._active_ledger_filter()}\n                ', (self.company_id, account_id, self.from_date))
            opening_row = dict(opening_rows[0]) if opening_rows else {}
            opening = opening_base + float(opening_row.get('debit_total') or 0.0) - float(opening_row.get('credit_total') or 0.0)
            entry_rows = worker_db.execute_query(f'\n                SELECT DISTINCT le.id,\n                       le.voucher_date,\n                       le.voucher_type,\n                       le.voucher_id,\n                       le.voucher_no,\n                       le.narration,\n                       le.debit,\n                       le.credit\n                FROM ledger_entries le\n                WHERE le.company_id = {ph}\n                  AND le.account_id = {ph}\n                  AND le.voucher_date >= {ph}\n                  AND le.voucher_date <= {ph}\n                  {self._active_ledger_filter()}\n                ORDER BY le.voucher_date, le.id\n                ', (self.company_id, account_id, self.from_date, self.to_date))
            entries = [dict(row) for row in entry_rows or []]
            running = opening
            for entry in entries:
                running += float(entry.get('debit') or 0.0) - float(entry.get('credit') or 0.0)
                entry['running_balance'] = running
            self.data_ready.emit({'party': self.party, 'opening': opening, 'closing': running, 'entries': entries})
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                worker_db.force_disconnect()
            self.finished.emit()

class LedgerStatementPageWidget(UiMemoryMixin, QWidget):
    """Read-only party statement page."""

    def __init__(self, db: Optional[Database]=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.company_id = self._active_company_id()
        self.parties: List[Dict[str, Any]] = []
        self.party_model = QStringListModel([])
        self._loading = False
        self._statement_thread = None
        self._statement_worker = None
        self.setWindowTitle('Statement of Account')
        self._build_ui()
        self.load_parties()
        self._init_ui_memory(table_attrs=("table",))

    def _active_company_id(self) -> Optional[int]:
        company_id = active_company_manager.get_active_company_id()
        return int(company_id) if company_id else None

    def _ph(self) -> str:
        return self.db._get_placeholder()

    def _build_ui(self) -> None:
        self.setObjectName('LedgerStatementPageWidget')
        self.setStyleSheet(self._page_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        self.title_label = QLabel('Statement of Account')
        self.title_label.setStyleSheet(page_heading_style(22))
        layout.addWidget(self.title_label)
        layout.addWidget(self._build_controls())
        layout.addWidget(self._build_summary())
        layout.addWidget(self._build_table(), 1)

    def _build_controls(self) -> QWidget:
        """Build the filter bar with labels above fields for even alignment."""
        frame = QFrame()
        frame.setObjectName('controlFrame')
        frame.setStyleSheet(compact_topbar_frame_style())
        grid = QGridLayout(frame)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        self.party_type_filter = QComboBox()
        self.party_type_filter.setStyleSheet(compact_input_style())
        self.party_type_filter.setMinimumWidth(150)
        self.party_type_filter.setFixedHeight(BOOK_REPORT_ACTION_BUTTON_HEIGHT)
        self.party_type_filter.addItems(['All', 'Debtors (Customers)', 'Creditors (Suppliers)'])
        self.party_type_filter.currentTextChanged.connect(self.load_parties)
        theme.apply_combo_dropdown_theme(self.party_type_filter)

        self.party_combo = QComboBox()
        self.party_combo.setStyleSheet(compact_input_style())
        self.party_combo.setEditable(True)
        self.party_combo.setMinimumWidth(260)
        self.party_combo.setFixedHeight(BOOK_REPORT_ACTION_BUTTON_HEIGHT)
        self.party_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.party_completer = QCompleter(self.party_model, self.party_combo)
        self.party_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.party_completer.setFilterMode(Qt.MatchContains)
        self.party_combo.setCompleter(self.party_completer)
        theme.apply_combo_dropdown_theme(self.party_combo)

        self.from_date = QDateEdit()
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        self.from_date.setFixedHeight(BOOK_REPORT_ACTION_BUTTON_HEIGHT)

        self.to_date = QDateEdit()
        self.to_date.setDate(QDate.currentDate())
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        self.to_date.setFixedHeight(BOOK_REPORT_ACTION_BUTTON_HEIGHT)

        add_labeled_filter_rows(
            grid,
            [[
                ('Party Type', self.party_type_filter),
                ('Party', self.party_combo),
                ('From', self.from_date),
                ('To', self.to_date),
            ]],
        )

        self.generate_btn = QPushButton('Generate Statement')
        self.generate_btn.setStyleSheet(compact_primary_button_style())
        self.generate_btn.setFixedHeight(BOOK_REPORT_ACTION_BUTTON_HEIGHT)
        self.generate_btn.setMinimumWidth(140)
        self.generate_btn.clicked.connect(self.generate_statement)

        self.export_btn = self._create_export_button()
        self.export_btn.setFixedHeight(BOOK_REPORT_ACTION_BUTTON_HEIGHT)
        self.export_btn.setMinimumWidth(88)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        action_layout.setContentsMargins(0, 4, 0, 0)
        action_layout.addWidget(self.generate_btn)
        action_layout.addWidget(self.export_btn)
        action_layout.addStretch()
        attach_filter_action_row(grid, action_layout, row=2)
        return frame

    def _create_export_button(self) -> QPushButton:
        button = QPushButton('Export ▼')
        button.setStyleSheet(self._export_button_style())
        menu = QMenu(button)
        pdf_action = QAction('Export to PDF', self)
        excel_action = QAction('Export to Excel', self)
        csv_action = QAction('Export to CSV', self)
        pdf_action.triggered.connect(self.export_to_pdf)
        excel_action.triggered.connect(self.export_to_excel)
        csv_action.triggered.connect(self.export_to_csv)
        menu.addAction(pdf_action)
        menu.addAction(excel_action)
        menu.addAction(csv_action)
        button.setMenu(menu)
        return button

    @staticmethod
    def _export_button_style() -> str:
        return '\n            QPushButton {\n                background-color: #2196F3;\n                color: white;\n                border-radius: 4px;\n                padding: 5px 15px;\n                font-weight: bold;\n            }\n            QPushButton:hover { background-color: #1976D2; }\n            QPushButton::menu-indicator { image: none; width: 0px; }\n        '

    def _build_summary(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName('summaryFrame')
        grid = QGridLayout(frame)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(5)
        self.party_name_label = QLabel('Party: -')
        self.contact_label = QLabel('Contact: -')
        self.address_label = QLabel('Address: -')
        self.outstanding_label = QLabel('Total Outstanding: 0.00')
        self.outstanding_label.setStyleSheet(report_summary_label_style())
        grid.addWidget(self.party_name_label, 0, 0)
        grid.addWidget(self.contact_label, 0, 1)
        grid.addWidget(self.outstanding_label, 0, 2)
        grid.addWidget(self.address_label, 1, 0, 1, 3)
        return frame

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['Date', 'Particulars', 'Debit (Dr)', 'Credit (Cr)', 'Running Balance'])
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        apply_read_only_report_table_selection(self.table)
        self.table.itemDoubleClicked.connect(self.open_selected_transaction)
        return self.table

    def load_parties(self) -> None:
        self.company_id = self._active_company_id()
        if not self.company_id:
            self.parties = []
            self.party_combo.clear()
            self.party_model.setStringList([])
            return
        ph = self._ph()
        type_filter = self.party_type_filter.currentText() if hasattr(self, 'party_type_filter') else 'All'
        type_clause = ''
        params: List[Any] = [self.company_id]
        if type_filter == 'Debtors (Customers)':
            type_clause = f'AND party_type IN ({ph}, {ph})'
            params.extend(['Debitor', 'Both'])
        elif type_filter == 'Creditors (Suppliers)':
            type_clause = f'AND party_type IN ({ph}, {ph})'
            params.extend(['Creditor', 'Both'])
        rows = self.db.execute_query(f'\n            SELECT id, name, party_type, opening_balance, mobile_number, email, address, gstin\n            FROM parties\n            WHERE company_id = {ph}\n              {type_clause}\n            ORDER BY name\n            ', tuple(params))
        self.parties = [dict(row) for row in rows or []]
        self.party_combo.blockSignals(True)
        self.party_combo.clear()
        for party in self.parties:
            self.party_combo.addItem(str(party.get('name') or ''), party)
        self.party_combo.blockSignals(False)
        self.party_model.setStringList([str(p.get('name') or '') for p in self.parties])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.load_parties()

    def _selected_party(self) -> Optional[Dict[str, Any]]:
        current_text = self.party_combo.currentText().strip()
        if not current_text:
            return None
        for party in self.parties:
            if str(party.get('name') or '').strip().lower() == current_text.lower():
                return party
        data = self.party_combo.currentData()
        return dict(data) if isinstance(data, dict) else None

    def _party_ledger_account(self, party: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ph = self._ph()
        rows = self.db.execute_query(f'\n            SELECT id, account_name, opening_balance, opening_balance_type, group_name\n            FROM ledger_accounts\n            WHERE company_id = {ph}\n              AND account_type = {ph}\n              AND account_name = {ph}\n              AND is_active = 1\n            ', (self.company_id, 'party', party.get('name')))
        if rows:
            return dict(rows[0])
        return None

    @staticmethod
    def _active_ledger_filter() -> str:
        """Filter out voided source vouchers and formal void reversal rows."""
        return "\n              AND le.voucher_type NOT IN (\n                  'sales_void', 'purchase_void', 'sales_return_void', 'purchase_return_void',\n                  'quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote'\n              )\n              AND NOT (\n                  le.voucher_type = 'sales'\n                  AND EXISTS (\n                      SELECT 1 FROM sales s\n                      WHERE s.company_id = le.company_id\n                        AND s.id = le.voucher_id\n                        AND COALESCE(s.status, 'Active') = 'Voided'\n                  )\n              )\n              AND NOT (\n                  le.voucher_type = 'purchase'\n                  AND EXISTS (\n                      SELECT 1 FROM purchases p\n                      WHERE p.company_id = le.company_id\n                        AND p.id = le.voucher_id\n                        AND COALESCE(p.status, 'Active') = 'Voided'\n                  )\n              )\n              AND NOT (\n                  le.voucher_type = 'sales_return'\n                  AND EXISTS (\n                      SELECT 1 FROM sales_returns sr\n                      WHERE sr.company_id = le.company_id\n                        AND sr.id = le.voucher_id\n                        AND COALESCE(sr.status, 'Active') = 'Voided'\n                  )\n              )\n              AND NOT (\n                  le.voucher_type = 'purchase_return'\n                  AND EXISTS (\n                      SELECT 1 FROM purchase_returns pr\n                      WHERE pr.company_id = le.company_id\n                        AND pr.id = le.voucher_id\n                        AND COALESCE(pr.status, 'Active') = 'Voided'\n                  )\n              )\n        "

    @staticmethod
    def _signed_opening(account: Optional[Dict[str, Any]], party: Dict[str, Any]) -> float:
        if account:
            opening = float(account.get('opening_balance') or 0.0)
            opening_type = str(account.get('opening_balance_type') or 'Dr')
        else:
            opening = float(party.get('opening_balance') or 0.0)
            opening_type = 'Cr' if party.get('party_type') == 'Creditor' else 'Dr'
        return opening if opening_type == 'Dr' else -opening

    def _balance_before(self, account_id: int, from_date: str, opening: float) -> float:
        ph = self._ph()
        rows = self.db.execute_query(f'\n            SELECT COALESCE(SUM(le.debit), 0.0) AS debit_total,\n                   COALESCE(SUM(le.credit), 0.0) AS credit_total\n            FROM ledger_entries le\n            WHERE le.company_id = {ph}\n              AND le.account_id = {ph}\n              AND le.voucher_date < {ph}\n              {self._active_ledger_filter()}\n            ', (self.company_id, account_id, from_date))
        row = dict(rows[0]) if rows else {}
        return opening + float(row.get('debit_total') or 0.0) - float(row.get('credit_total') or 0.0)

    def _ledger_entries(self, account_id: int, from_date: str, to_date: str) -> List[Dict[str, Any]]:
        ph = self._ph()
        rows = self.db.execute_query(f'\n            SELECT DISTINCT le.id,\n                   le.voucher_date,\n                   le.voucher_type,\n                   le.voucher_id,\n                   le.voucher_no,\n                   le.narration,\n                   le.debit,\n                   le.credit\n            FROM ledger_entries le\n            WHERE le.company_id = {ph}\n              AND le.account_id = {ph}\n              AND le.voucher_date >= {ph}\n              AND le.voucher_date <= {ph}\n              {self._active_ledger_filter()}\n            ORDER BY le.voucher_date, le.id\n            ', (self.company_id, account_id, from_date, to_date))
        return [dict(row) for row in rows or []]

    def _closing_balance(self, account_id: int, to_date: str, opening: float) -> float:
        ph = self._ph()
        rows = self.db.execute_query(f'\n            SELECT COALESCE(SUM(le.debit), 0.0) AS debit_total,\n                   COALESCE(SUM(le.credit), 0.0) AS credit_total\n            FROM ledger_entries le\n            WHERE le.company_id = {ph}\n              AND le.account_id = {ph}\n              AND le.voucher_date <= {ph}\n              {self._active_ledger_filter()}\n            ', (self.company_id, account_id, to_date))
        row = dict(rows[0]) if rows else {}
        return opening + float(row.get('debit_total') or 0.0) - float(row.get('credit_total') or 0.0)

    def generate_statement(self) -> None:
        if self._loading:
            return
        self.company_id = self._active_company_id()
        if not self.company_id:
            QMessageBox.warning(self, 'No Active Company', 'Please open a company first.')
            return
        party = self._selected_party()
        if not party:
            QMessageBox.information(self, 'Select Party', 'Please select a party.')
            return
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        if from_date > to_date:
            QMessageBox.warning(self, 'Invalid Date Range', 'From Date cannot be after To Date.')
            return
        self._update_summary(party, 0.0)
        self._start_statement_worker(party, from_date, to_date)

    def _start_statement_worker(self, party: Dict[str, Any], from_date: str, to_date: str) -> None:
        thread = QThread(self)
        worker = LedgerStatementWorker(getattr(self.db, 'db_type', None), getattr(self.db, 'db_path', None), self.company_id, party, from_date, to_date)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(lambda result, start=from_date: self._handle_statement_result(result, start))
        worker.error.connect(lambda message: QMessageBox.warning(self, 'Statement Error', message))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._statement_worker_finished)
        self._statement_thread = thread
        self._statement_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _handle_statement_result(self, result: Dict[str, Any], from_date: str) -> None:
        self._populate_statement(from_date, float(result.get('opening') or 0.0), result.get('entries', []))
        self._update_summary(result.get('party', {}), float(result.get('closing') or 0.0))

    def _set_loading_state(self, is_loading: bool) -> None:
        self._loading = is_loading
        self.generate_btn.setEnabled(not is_loading)
        self.export_btn.setEnabled(not is_loading)
        self.party_combo.setEnabled(not is_loading)
        self.party_type_filter.setEnabled(not is_loading)
        self.from_date.setEnabled(not is_loading)
        self.to_date.setEnabled(not is_loading)
        self.generate_btn.setText('Loading...' if is_loading else 'Generate Statement')

    def _statement_worker_finished(self) -> None:
        self._statement_thread = None
        self._statement_worker = None
        self._set_loading_state(False)

    def _populate_statement(self, from_date: str, opening: float, entries: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(len(entries) + 2)
        running = opening
        self._set_row(0, from_date, 'Opening Balance', 0.0, 0.0, running, None)
        for index, entry in enumerate(entries, start=1):
            debit = float(entry.get('debit') or 0.0)
            credit = float(entry.get('credit') or 0.0)
            running += debit - credit
            self._set_row(index, format_display_date(entry.get('voucher_date')), self._particulars(entry), debit, credit, running, entry)
        self._set_row(len(entries) + 1, '', 'Closing Balance', 0.0, 0.0, running, None)
        self._apply_table_layout_after_populate()

    def _apply_table_layout_after_populate(self) -> None:
        """Apply resizable columns, restore saved widths, and fill the viewport."""
        apply_adjustable_table_columns(self.table, auto_size=False)
        self._restore_memory_table(self.table, "table")

        settings = getattr(self, "settings", None)
        header_key = f"{self.__class__.__name__}/tableHeaderState"
        has_saved_layout = bool(settings and settings.value(header_key))
        if not has_saved_layout:
            viewport_w = max(self.table.viewport().width(), 900)
            self.table.setColumnWidth(0, int(viewport_w * 0.12))
            self.table.setColumnWidth(1, int(viewport_w * 0.40))
            self.table.setColumnWidth(2, int(viewport_w * 0.16))
            self.table.setColumnWidth(3, int(viewport_w * 0.16))
            self.table.setColumnWidth(4, max(int(viewport_w * 0.16), 120))

        header = self.table.horizontalHeader()
        if has_saved_layout:
            header.setStretchLastSection(False)
            return

        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)

    def _set_row(self, row: int, row_date: str, particulars: str, debit: float, credit: float, balance: float, entry: Optional[Dict[str, Any]]=None) -> None:
        date_item = QTableWidgetItem(row_date)
        if entry:
            date_item.setData(Qt.UserRole, dict(entry))
        self.table.setItem(row, 0, date_item)
        self.table.setItem(row, 1, QTableWidgetItem(particulars))
        debit_item = QTableWidgetItem('' if debit == 0 else f'{debit:.2f}')
        credit_item = QTableWidgetItem('' if credit == 0 else f'{credit:.2f}')
        balance_item = QTableWidgetItem(self._format_balance(balance))
        for item in (debit_item, credit_item, balance_item):
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 2, debit_item)
        self.table.setItem(row, 3, credit_item)
        self.table.setItem(row, 4, balance_item)
        if particulars in ('Opening Balance', 'Closing Balance'):
            for col in range(5):
                item = self.table.item(row, col)
                if item:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

    def export_to_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, 'Export Ledger Statement', 'ledger_statement.csv', 'CSV Files (*.csv);;All Files (*)')
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.writer(handle)
                writer.writerow([self.table.horizontalHeaderItem(col).text() for col in range(self.table.columnCount())])
                for row in range(self.table.rowCount()):
                    writer.writerow([self.table.item(row, col).text() if self.table.item(row, col) else '' for col in range(self.table.columnCount())])
            QMessageBox.information(self, 'Export Complete', f'Ledger statement exported to:\n{path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Export Failed', str(exc))

    def export_to_pdf(self) -> None:
        """Open the statement in the universal print/PDF preview dialog."""
        if self.table.rowCount() <= 0:
            QMessageBox.information(self, 'No Data', 'Please load statement data first.')
            return
        dialog = UniversalPreviewDialog(self._table_html('Statement of Account'), self)
        dialog.exec()

    def export_to_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, 'Export Ledger Statement Excel', 'ledger_statement.xlsx', 'Excel Files (*.xlsx);;All Files (*)')
        if not path:
            return
        if not path.lower().endswith('.xlsx'):
            path += '.xlsx'
        try:
            from openpyxl import Workbook
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = 'Ledger Statement'
            for row in self._table_rows(include_headers=True):
                sheet.append(row)
            workbook.save(path)
            QMessageBox.information(self, 'Export Complete', f'Excel file exported to:\n{path}')
        except ImportError:
            self._write_csv_fallback(path)
            QMessageBox.warning(self, 'Excel Library Missing', 'openpyxl is not installed. A CSV-formatted fallback was saved with the selected filename.')
        except Exception as exc:
            QMessageBox.critical(self, 'Export Failed', str(exc))

    def _write_csv_fallback(self, path: str) -> None:
        with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.writer(handle)
            writer.writerows(self._table_rows(include_headers=True))

    def _table_rows(self, include_headers: bool=False) -> list:
        rows = []
        if include_headers:
            rows.append([self.table.horizontalHeaderItem(col).text() for col in range(self.table.columnCount())])
        for row in range(self.table.rowCount()):
            rows.append([self.table.item(row, col).text() if self.table.item(row, col) else '' for col in range(self.table.columnCount())])
        return rows

    def _table_html(self, title: str) -> str:
        summary = '<br>'.join((html.escape(label.text()) for label in (self.party_name_label, self.contact_label, self.address_label, self.outstanding_label)))
        header_cells = ''.join((f'<th>{html.escape(self.table.horizontalHeaderItem(col).text())}</th>' for col in range(self.table.columnCount())))
        body_rows = []
        for row in range(self.table.rowCount()):
            cells = ''.join((f"<td>{html.escape(self.table.item(row, col).text() if self.table.item(row, col) else '')}</td>" for col in range(self.table.columnCount())))
            body_rows.append(f'<tr>{cells}</tr>')
        return f"""\n        <html>\n        <head>\n        <style>\n            body {{ font-family: Arial, sans-serif; font-size: 10pt; }}\n            h1 {{ color: #1976D2; font-size: 18pt; }}\n            .summary {{ margin-bottom: 12px; color: #333333; }}\n            table {{ border-collapse: collapse; width: 100%; }}\n            th {{ background: #2196F3; color: white; padding: 6px; border: 1px solid #90CAF9; }}\n            td {{ padding: 5px; border: 1px solid #cccccc; }}\n        </style>\n        </head>\n        <body>\n            <h1>{html.escape(title)}</h1>\n            <div class="summary">{summary}</div>\n            <table>\n                <thead><tr>{header_cells}</tr></thead>\n                <tbody>{''.join(body_rows)}</tbody>\n            </table>\n        </body>\n        </html>\n        """

    def _main_window(self):
        widget = self
        while widget is not None:
            if hasattr(widget, 'open_voucher_for_edit'):
                return widget
            widget = widget.parent()
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'open_voucher_for_edit'):
                return widget
        return None

    def open_selected_transaction(self, _item=None) -> None:
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        item = self.table.item(current_row, 0)
        entry = item.data(Qt.UserRole) if item else None
        if not isinstance(entry, dict):
            return
        voucher_type = str(entry.get('voucher_type') or '')
        voucher_id = entry.get('voucher_id')
        if not voucher_type or not voucher_id:
            return
        main_window = self._main_window()
        if not main_window:
            QMessageBox.warning(self, 'Navigation Error', 'Main window navigation is not available.')
            return
        main_window.open_voucher_for_edit(voucher_type, int(voucher_id))

    @staticmethod
    def _format_balance(value: float) -> str:
        suffix = 'Dr' if value >= 0 else 'Cr'
        return f'{abs(value):.2f} {suffix}'

    @staticmethod
    def _particulars(entry: Dict[str, Any]) -> str:
        labels = {'sales': 'Sale', 'purchase': 'Purchase', 'sales_return': 'Sales Return', 'purchase_return': 'Purchase Return', 'cash_receipt': 'Cash Receipt', 'cash_payment': 'Cash Payment', 'bank_receipt': 'Bank Receipt', 'bank_payment': 'Bank Payment', 'sales_void': 'Sales Void Reversal', 'purchase_void': 'Purchase Void Reversal', 'sales_return_void': 'Sales Return Void Reversal', 'purchase_return_void': 'Purchase Return Void Reversal', 'journal': 'Journal'}
        voucher_type = str(entry.get('voucher_type') or '')
        label = labels.get(voucher_type, voucher_type.replace('_', ' ').title() or 'Voucher')
        voucher_no = str(entry.get('voucher_no') or '').strip()
        if voucher_no:
            return f'{label} - #{voucher_no}'
        narration = str(entry.get('narration') or '').strip()
        return f'{label} - {narration}' if narration else label

    def _update_summary(self, party: Dict[str, Any], closing_balance: float) -> None:
        name = str(party.get('name') or '')
        mobile = str(party.get('mobile_number') or '')
        email = str(party.get('email') or '')
        gstin = str(party.get('gstin') or '')
        address = str(party.get('address') or '')
        contact_parts = [part for part in (mobile, email, f'GSTIN: {gstin}' if gstin else '') if part]
        self.party_name_label.setText(f'Party: {name}')
        self.contact_label.setText(f"Contact: {(' | '.join(contact_parts) if contact_parts else '-')}")
        self.address_label.setText(f"Address: {(address if address else '-')}")
        self.outstanding_label.setText(f'Total Outstanding: {self._format_balance(closing_balance)}')

    def _page_style(self) -> str:
        from ui.book_report_common import _report_theme_colors
        colors = _report_theme_colors()
        selection_text = colors['input_text'] if theme._is_light_theme() else '#FFFFFF'
        return (
            report_page_shell_style('LedgerStatementPageWidget')
            + report_filter_frame_style('QFrame#controlFrame')
            + report_filter_frame_style('QFrame#summaryFrame')
            + report_data_table_style()
            + f"""
            QTableWidget::item:selected, QTableView::item:selected {{
                background-color: {colors['focus_border']};
                color: {selection_text};
            }}
            """
        )

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(self._page_style())
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(page_heading_style(22))
        if hasattr(self, 'outstanding_label'):
            self.outstanding_label.setStyleSheet(report_summary_label_style())
        if hasattr(self, 'table'):
            self.table.setStyleSheet(theme.ledger_report_table_style())
        control_style = compact_input_style()
        date_style = compact_date_style()
        label_style = compact_label_style()
        button_style = compact_primary_button_style()
        for label in self.findChildren(QLabel):
            if label is self.title_label:
                continue
            if label is self.outstanding_label:
                continue
            label.setStyleSheet(label_style)
        if hasattr(self, 'party_type_filter'):
            self.party_type_filter.setStyleSheet(control_style)
            theme.apply_combo_dropdown_theme(self.party_type_filter)
        if hasattr(self, 'party_combo'):
            self.party_combo.setStyleSheet(control_style)
            theme.apply_combo_dropdown_theme(self.party_combo)
        if hasattr(self, 'from_date'):
            prepare_report_date_edit(self.from_date, style_sheet=date_style)
        if hasattr(self, 'to_date'):
            prepare_report_date_edit(self.to_date, style_sheet=date_style)
        if hasattr(self, 'generate_btn'):
            self.generate_btn.setStyleSheet(button_style)
LedgerStatementPage = LedgerStatementPageWidget