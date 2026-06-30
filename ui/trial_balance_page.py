"""
Trial Balance Page Widget

Displays Trial Balance computed entirely from ledger_accounts + ledger_entries.
Matches the dark professional theme used across the application.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QLineEdit, QSizePolicy, QMessageBox, QAbstractItemView, QFileDialog
from PySide6.QtCore import Qt, QDate, QTimer
from PySide6.QtGui import QFont, QColor
from config import COLORS, active_company_manager, resolve_active_company_id
from bizora_core.financial_reporting_engine import FinancialReportingEngine, FILTER_MAP
from bizora_core.export_engine import ExportEngine
from ui import theme
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.book_report_common import compact_label_style, compact_input_style, compact_date_style, compact_primary_button_style, compact_secondary_button_style, compact_topbar_frame_style, page_background_style, page_heading_style
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin
COL_SL = 0
COL_ACCOUNT = 1
COL_TYPE = 2
COL_OB_DR = 3
COL_OB_CR = 4
COL_PER_DR = 5
COL_PER_CR = 6
COL_CL_DR = 7
COL_CL_CR = 8
COL_COUNT = 9
HEADERS = ['#', 'Ledger Account', 'Type', 'Opening\nDebit', 'Opening\nCredit', 'Period\nDebit', 'Period\nCredit', 'Closing\nDebit', 'Closing\nCredit']

def _fmt(v: float) -> str:
    """Format monetary value; blank for zero."""
    return f'{v:,.2f}' if v > 0.001 else ''

def _fmt_total(v: float) -> str:
    return f'{v:,.2f}'

class TrialBalancePageWidget(UiMemoryMixin, QWidget):
    """Trial Balance report page."""

    def __init__(self, db=None):
        super().__init__()
        self.db = db
        self._reporting_engine = FinancialReportingEngine(db) if db else None
        self._company_id = None
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._on_search_timer)
        self._setup_ui()
        self._init_ui_memory()

    def _setup_ui(self):
        self.setStyleSheet(page_background_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        title_lbl = QLabel('Trial Balance')
        title_lbl.setStyleSheet(page_heading_style(22))
        root.addWidget(title_lbl)
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_summary_frame())
        root.addWidget(self._build_table(), 1)

    def _build_filter_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(compact_topbar_frame_style())
        lay = QHBoxLayout(bar)
        lay.setSpacing(12)
        lay.setContentsMargins(10, 6, 10, 6)
        today = QDate.currentDate()
        fy_start = QDate(today.year() if today.month() >= 4 else today.year() - 1, 4, 1)
        from_label = QLabel('From:')
        from_label.setStyleSheet(compact_label_style())
        lay.addWidget(from_label)
        self.from_date = QDateEdit(calendarPopup=True)
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        self.from_date.setFixedWidth(110)
        self.from_date.setDate(fy_start)
        lay.addWidget(self.from_date)
        to_label = QLabel('To:')
        to_label.setStyleSheet(compact_label_style())
        lay.addWidget(to_label)
        self.to_date = QDateEdit(calendarPopup=True)
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        self.to_date.setFixedWidth(110)
        self.to_date.setDate(today)
        lay.addWidget(self.to_date)
        type_label = QLabel('Type:')
        type_label.setStyleSheet(compact_label_style())
        lay.addWidget(type_label)
        self.type_combo = QComboBox()
        self.type_combo.setStyleSheet(compact_input_style())
        self.type_combo.setFixedWidth(115)
        for label in FILTER_MAP.keys():
            self.type_combo.addItem(label)
        lay.addWidget(self.type_combo)
        search_label = QLabel('Search:')
        search_label.setStyleSheet(compact_label_style())
        lay.addWidget(search_label)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText('Account name…')
        self.search_box.setStyleSheet(compact_input_style())
        self.search_box.setFixedWidth(200)
        self.search_box.textChanged.connect(self._search_timer.start)
        lay.addWidget(self.search_box)
        self.load_btn = QPushButton('Load')
        self.load_btn.setStyleSheet(compact_primary_button_style())
        self.load_btn.clicked.connect(self.load_trial_balance)
        lay.addWidget(self.load_btn)
        self.export_btn = QPushButton('Export Excel')
        self.export_btn.setStyleSheet(compact_primary_button_style())
        self.export_btn.clicked.connect(self._export_excel)
        lay.addWidget(self.export_btn)
        lay.addStretch()
        return bar

    def _build_summary_frame(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"QFrame{{background:{COLORS['surface']};border:1px solid {COLORS['border']};border-radius:6px;}}")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(30)

        def _stat(title):
            col = QVBoxLayout()
            lbl_t = QLabel(title)
            lbl_t.setStyleSheet(f"color:{COLORS['text_secondary']};font-size:11px;")
            lbl_v = QLabel('0.00')
            lbl_v.setStyleSheet(f"color:{COLORS['text_primary']};font-size:14px;font-weight:bold;")
            col.addWidget(lbl_t)
            col.addWidget(lbl_v)
            lay.addLayout(col)
            return lbl_v
        self.lbl_ob_dr = _stat('Opening Debit')
        self.lbl_ob_cr = _stat('Opening Credit')
        self._add_vsep(lay)
        self.lbl_per_dr = _stat('Period Debit')
        self.lbl_per_cr = _stat('Period Credit')
        self._add_vsep(lay)
        self.lbl_cl_dr = _stat('Closing Debit')
        self.lbl_cl_cr = _stat('Closing Credit')
        self._add_vsep(lay)
        self.lbl_status = QLabel('—')
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet(f"font-size:15px;font-weight:bold;color:{COLORS['text_secondary']};border:1px solid {COLORS['border']};border-radius:4px;padding:6px 14px;")
        lay.addWidget(self.lbl_status)
        lay.addStretch()
        return frame

    @staticmethod
    def _add_vsep(lay):
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color:{COLORS['border']};")
        lay.addWidget(sep)

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget(0, COL_COUNT)
        self.table.setHorizontalHeaderLabels(HEADERS)
        apply_read_only_report_table_selection(self.table)
        self.table.setWordWrap(False)
        return self.table

    def refresh(self):
        """Called when company changes or window is focused."""
        self._company_id = resolve_active_company_id(self.db)
        if self._company_id and self.db and (not self._reporting_engine):
            self._reporting_engine = FinancialReportingEngine(self.db)
        self.table.setRowCount(0)
        self._reset_summary()

    def load_trial_balance(self):
        """Load and display trial balance for current filters."""
        print(f'[TRIAL BALANCE DEBUG] load_trial_balance called')
        self._company_id = resolve_active_company_id(self.db)
        print(f'[TRIAL BALANCE DEBUG] active_company_id: {self._company_id}')
        if not self._company_id:
            print(f'[TRIAL BALANCE DEBUG] No company selected')
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        if not self._reporting_engine:
            self._reporting_engine = FinancialReportingEngine(self.db)
        from_date = self.from_date.date().toPython()
        to_date = self.to_date.date().toPython()
        type_filter = self.type_combo.currentText()
        search = self.search_box.text().strip()
        print(f'[TRIAL BALANCE DEBUG] from_date: {from_date}, to_date: {to_date}')
        print(f'[TRIAL BALANCE DEBUG] type_filter: {type_filter}')
        print(f'[TRIAL BALANCE DEBUG] search: {search}')
        result = self._reporting_engine.generate_trial_balance(self._company_id, from_date, to_date, account_type_filter=type_filter if type_filter != 'All' else None, search_term=search or None)
        rows = result['rows']
        totals = result['totals']
        print(f'[TRIAL BALANCE DEBUG] rows returned from engine: {len(rows)}')
        print(f"[TRIAL BALANCE DEBUG] rows sample: {(rows[:3] if rows else 'None')}")
        print(f'[TRIAL BALANCE DEBUG] totals: {totals}')
        self._populate_table(rows)
        print(f'[TRIAL BALANCE DEBUG] rows inserted into table: {self.table.rowCount()}')
        self._update_summary(totals)

    def _on_search_timer(self):
        """Debounced search — reload if data already displayed."""
        if self.table.rowCount() > 0 or self._company_id:
            self.load_trial_balance()

    def _populate_table(self, rows):
        print(f'[TRIAL BALANCE DEBUG] _populate_table called with {len(rows)} rows')
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        if not rows:
            print(f'[TRIAL BALANCE DEBUG] No rows found, showing message row')
            self.table.setRowCount(1)
            self.table.setColumnCount(9)
            self.table.setHorizontalHeaderLabels(['SL No', 'Ledger Account', 'Account Type', 'Opening Debit', 'Opening Credit', 'Period Debit', 'Period Credit', 'Closing Debit', 'Closing Credit'])
            self.table.setItem(0, 0, QTableWidgetItem(''))
            self.table.setItem(0, 1, QTableWidgetItem('No trial balance data found.'))
            for col in range(2, 9):
                self.table.setItem(0, col, QTableWidgetItem(''))
            self.table.setUpdatesEnabled(True)
            apply_adjustable_table_columns(self.table, sl_no_column=COL_SL)
            return
        colors = theme._theme_colors()
        type_color = {'cash_bank': colors['button_primary'], 'party': colors['focus_border'], 'income': theme.semantic_positive_hex(), 'expense': theme.semantic_negative_hex(), 'tax_liability': theme.semantic_warning_hex(), 'capital': colors['accent_label'], 'stock': colors['label_text']}
        for row_data in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._set_item(row, COL_SL, str(row_data['sl']), Qt.AlignCenter)
            self._set_item(row, COL_ACCOUNT, row_data['account_name'])
            atype = row_data['account_type']
            cat = row_data['category']
            ti = QTableWidgetItem(cat)
            ti.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            color = type_color.get(atype, COLORS['text_secondary'])
            ti.setForeground(QColor(color))
            self.table.setItem(row, COL_TYPE, ti)
            self._set_amount(row, COL_OB_DR, row_data['ob_dr'])
            self._set_amount(row, COL_OB_CR, row_data['ob_cr'])
            self._set_amount(row, COL_PER_DR, row_data['period_dr'])
            self._set_amount(row, COL_PER_CR, row_data['period_cr'])
            self._set_amount(row, COL_CL_DR, row_data['closing_dr'])
            self._set_amount(row, COL_CL_CR, row_data['closing_cr'])
        self.table.setUpdatesEnabled(True)
        apply_adjustable_table_columns(self.table, sl_no_column=COL_SL)

    def _set_item(self, row, col, text, align=Qt.AlignLeft | Qt.AlignVCenter):
        item = QTableWidgetItem(text)
        item.setTextAlignment(align)
        self.table.setItem(row, col, item)

    def _set_amount(self, row, col, value: float):
        text = _fmt(value)
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if value > 0.001:
            item.setForeground(QColor(COLORS['text_primary']))
        self.table.setItem(row, col, item)

    def _update_summary(self, totals: dict):
        self.lbl_ob_dr.setText(_fmt_total(totals['ob_dr']))
        self.lbl_ob_cr.setText(_fmt_total(totals['ob_cr']))
        self.lbl_per_dr.setText(_fmt_total(totals['period_dr']))
        self.lbl_per_cr.setText(_fmt_total(totals['period_cr']))
        self.lbl_cl_dr.setText(_fmt_total(totals['closing_dr']))
        self.lbl_cl_cr.setText(_fmt_total(totals['closing_cr']))
        if totals['balanced']:
            self.lbl_status.setText('BALANCED ✓')
            self.lbl_status.setStyleSheet(f'font-size:14px;font-weight:bold;color:{theme.semantic_positive_hex()};border:1px solid {theme.semantic_positive_hex()};border-radius:4px;padding:6px 14px;')
        else:
            diff = totals['difference']
            self.lbl_status.setText(f'NOT BALANCED\n±{diff:,.2f}')
            self.lbl_status.setStyleSheet(f'font-size:13px;font-weight:bold;color:{theme.semantic_negative_hex()};border:1px solid {theme.semantic_negative_hex()};border-radius:4px;padding:6px 14px;')

    def _reset_summary(self):
        for lbl in (self.lbl_ob_dr, self.lbl_ob_cr, self.lbl_per_dr, self.lbl_per_cr, self.lbl_cl_dr, self.lbl_cl_cr):
            lbl.setText('0.00')
        self.lbl_status.setText('—')
        self.lbl_status.setStyleSheet(f"font-size:15px;font-weight:bold;color:{COLORS['text_secondary']};border:1px solid {COLORS['border']};border-radius:4px;padding:6px 14px;")

    def _export_excel(self):
        """Export trial balance to Excel using centralized ExportEngine."""
        if self.table.rowCount() == 0:
            QMessageBox.information(self, 'No Data', 'Load trial balance first.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save Trial Balance', 'trial_balance.xlsx', 'Excel Files (*.xlsx)')
        if not path:
            return
        headers = [h.replace('\n', ' ') for h in HEADERS]
        data = []
        for row_i in range(self.table.rowCount()):
            row_data = []
            for col_i in range(COL_COUNT):
                item = self.table.item(row_i, col_i)
                val = item.text().replace(',', '') if item else ''
                if col_i >= COL_OB_DR:
                    try:
                        val = float(val) if val else 0.0
                    except ValueError:
                        pass
                row_data.append(val)
            data.append(row_data)
        export_engine = ExportEngine(self.db)
        result = export_engine.export_table_to_excel('Trial Balance', headers, data, path)
        if result['success']:
            QMessageBox.information(self, 'Exported', result['message'])
        else:
            QMessageBox.critical(self, 'Export Failed', result['error'])