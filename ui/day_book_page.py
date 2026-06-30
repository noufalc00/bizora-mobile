"""
Day Book Page UI Module

Provides the Day Book interface showing all transactions in chronological order
with drill-down capabilities to original vouchers or filtered book reports.
"""
from typing import Any, Callable, Dict, List, Optional
from PySide6.QtCore import Qt, QDate, QPoint, QObject, QThread, Signal
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QAbstractItemView, QDateEdit, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QMenu
from PySide6.QtGui import QColor
from config import COLORS
from bizora_core.book_report_common import resolve_active_company_id
from ui.book_report_common import BOOK_REPORT_ACTION_BUTTON_HEIGHT, add_labeled_filter_rows, attach_filter_action_row, book_report_special_row_colors, compact_label_style, compact_input_style, compact_date_style, compact_primary_button_style, compact_secondary_button_style, compact_topbar_frame_style, create_filter_action_layout, page_background_style, page_heading_style, report_data_table_style
from bizora_core.day_book_logic import DayBookLogic
from ui.checkbox_style import create_checkbox
from ui.net_sales_book import create_view_net_sales_button, open_net_sales_book_window
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.report_preview_utils import table_widget_to_html
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
DAY_BOOK_HEADERS = ['Date', 'V.No', 'Particulars', 'Debit', 'Credit', 'Voucher Type']

class DayBookWorker(QObject):
    """Load Day Book rows and summary on a worker-owned database connection."""
    data_ready = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type, db_path, company_id, from_date, to_date, summarize_entries=True, summarize_debtors=False):
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id
        self.from_date = from_date
        self.to_date = to_date
        self.summarize_entries = summarize_entries
        self.summarize_debtors = summarize_debtors

    def run(self):
        worker_db = None
        try:
            from db import Database
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            logic = DayBookLogic(worker_db)
            entries_result = logic.get_day_book_entries(self.company_id, self.from_date, self.to_date, self.summarize_entries, self.summarize_debtors)
            if not entries_result.get('success'):
                self.error.emit(entries_result.get('message') or 'Failed to load Day Book')
                return
            summary_result = logic.get_day_book_summary(self.company_id, self.from_date, self.to_date, self.summarize_entries, self.summarize_debtors)
            self.data_ready.emit({'entries': entries_result.get('data', []), 'summary': summary_result.get('data', {}) if summary_result.get('success') else {}})
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                worker_db.force_disconnect()
            self.finished.emit()

class DayBookPageWidget(UiMemoryMixin, QWidget):
    """Day Book page showing all transactions in chronological order."""

    def __init__(self, db=None, parent=None):
        """
        Initialize Day Book page.

        Args:
            db: Database connection
            parent: Parent widget
        """
        super().__init__(parent)
        self.db = db
        self.company_id: Optional[int] = None
        self.day_book_logic = None
        self.current_rows: List[Dict[str, Any]] = []
        self._is_loading = False
        self._day_book_thread = None
        self._day_book_worker = None
        self._net_sales_window = None
        self._build_ui()
        self._init_ui_memory(table_attrs=("table",))

    def _build_ui(self):
        """Build the Day Book UI."""
        self.setStyleSheet(page_background_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QLabel('Day Book')
        header.setStyleSheet(page_heading_style(22))
        root.addWidget(header)
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QGridLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setHorizontalSpacing(12)
        filter_layout.setVerticalSpacing(8)
        self.from_date = QDateEdit()
        self.from_date.setDate(QDate.currentDate())
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        self.to_date = QDateEdit()
        self.to_date.setDate(QDate.currentDate())
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        self.load_btn = QPushButton('Load')
        self.refresh_btn = QPushButton('Refresh')
        self.export_btn = QPushButton('Export')
        self.preview_btn = QPushButton('Preview')
        self.summarise_entries_checkbox = create_checkbox('Summarise Entries', font_size=13, spacing=6)
        self.summarise_entries_checkbox.setChecked(True)
        self.summarise_debtors_checkbox = create_checkbox('Summarise Debtors', font_size=13, spacing=6)
        for checkbox in (self.summarise_entries_checkbox, self.summarise_debtors_checkbox):
            checkbox.setMinimumWidth(165)
            checkbox.stateChanged.connect(self.load_day_book)
        action_height = BOOK_REPORT_ACTION_BUTTON_HEIGHT
        for btn in (self.load_btn, self.refresh_btn, self.export_btn, self.preview_btn):
            btn.setStyleSheet(compact_primary_button_style())
            btn.setFixedHeight(action_height)
            btn.setMinimumWidth(68)
        self.load_btn.clicked.connect(self.load_day_book)
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn.clicked.connect(self.show_export_menu)
        self.preview_btn.clicked.connect(self.show_preview)
        self.net_sales_btn = create_view_net_sales_button(action_height=action_height)
        self.net_sales_btn.clicked.connect(self.open_net_sales_book)
        add_labeled_filter_rows(filter_layout, [[('From', self.from_date), ('To', self.to_date)]])
        filter_layout.setColumnStretch(1, 0)
        filter_layout.setColumnStretch(2, 1)
        options_layout = QHBoxLayout()
        options_layout.setSpacing(12)
        options_layout.setContentsMargins(0, 4, 0, 0)
        options_layout.addWidget(self.net_sales_btn)
        options_layout.addWidget(self.summarise_entries_checkbox)
        options_layout.addWidget(self.summarise_debtors_checkbox)
        options_layout.addStretch()
        attach_filter_action_row(filter_layout, options_layout, row=2)
        action_layout = create_filter_action_layout([self.load_btn, self.refresh_btn, self.export_btn, self.preview_btn])
        attach_filter_action_row(filter_layout, action_layout, row=3)
        root.addWidget(filter_frame)
        summary_frame = QFrame()
        summary_frame.setStyleSheet(compact_topbar_frame_style())
        summary_layout = QGridLayout(summary_frame)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setHorizontalSpacing(15)
        summary_layout.setVerticalSpacing(8)
        self.cash_sales_label = QLabel('Cash Sales: 0.00')
        self.credit_sales_label = QLabel('Credit Sales: 0.00')
        self.cash_purchase_label = QLabel('Cash Purchase: 0.00')
        self.credit_purchase_label = QLabel('Credit Purchase: 0.00')
        self.sales_return_label = QLabel('Sales Return: 0.00')
        self.purchase_return_label = QLabel('Purchase Return: 0.00')
        self.debitors_btn = QPushButton('Debtors Summary')
        self.creditors_btn = QPushButton('Creditors Summary')
        for label in (self.cash_sales_label, self.credit_sales_label, self.cash_purchase_label, self.credit_purchase_label, self.sales_return_label, self.purchase_return_label):
            label.setStyleSheet(compact_label_style())
            label.setMinimumWidth(170)
        for btn in (self.debitors_btn, self.creditors_btn):
            btn.setStyleSheet(compact_secondary_button_style())
            btn.setMinimumHeight(38)
            btn.setMinimumWidth(150)
        self.debitors_btn.clicked.connect(self.show_debitor_summary)
        self.creditors_btn.clicked.connect(self.show_creditor_summary)
        summary_layout.addWidget(self.cash_sales_label, 0, 0)
        summary_layout.addWidget(self.credit_sales_label, 0, 1)
        summary_layout.addWidget(self.cash_purchase_label, 0, 2)
        summary_layout.addWidget(self.credit_purchase_label, 0, 3)
        summary_layout.addWidget(self.sales_return_label, 1, 0)
        summary_layout.addWidget(self.purchase_return_label, 1, 1)
        summary_layout.addWidget(self.debitors_btn, 1, 2)
        summary_layout.addWidget(self.creditors_btn, 1, 3)
        root.addWidget(summary_frame)
        self.export_menu = QMenu(self)
        self.excel_action = self.export_menu.addAction('Export Excel')
        self.pdf_action = self.export_menu.addAction('Export PDF')
        self.csv_action = self.export_menu.addAction('Export CSV')
        self._export_menu_warmed = False
        self.table = QTableWidget()
        self.table.setStyleSheet(report_data_table_style())
        apply_read_only_report_table_selection(self.table)
        self.table.cellDoubleClicked.connect(self.handle_row_double_click)
        self.table.setColumnCount(len(DAY_BOOK_HEADERS))
        self.table.setHorizontalHeaderLabels(DAY_BOOK_HEADERS)
        root.addWidget(self.table)
        self.refresh()

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(page_background_style())
        self.table.setStyleSheet(report_data_table_style())
        for label in (
            self.cash_sales_label,
            self.credit_sales_label,
            self.cash_purchase_label,
            self.credit_purchase_label,
            self.sales_return_label,
            self.purchase_return_label,
        ):
            label.setStyleSheet(compact_label_style())
        for widget, style_fn in (
            (self.from_date, compact_date_style),
            (self.to_date, compact_date_style),
        ):
            prepare_report_date_edit(widget, style_sheet=style_fn())
        for btn in (self.load_btn, self.refresh_btn, self.export_btn, self.preview_btn):
            btn.setStyleSheet(compact_primary_button_style())
        for btn in (self.debitors_btn, self.creditors_btn):
            btn.setStyleSheet(compact_secondary_button_style())
        if self.current_rows:
            self.populate_table(self.current_rows)

    def refresh(self):
        """Refresh Day Book data."""
        self.company_id = resolve_active_company_id(self.db)
        print(f'[Day Book UI] refresh called, company_id: {self.company_id}')
        if not self.company_id:
            self.show_no_data('Please open a company first.')
            return
        if self.day_book_logic is None:
            self.day_book_logic = DayBookLogic(self.db)
        self.load_day_book()

    def open_net_sales_book(self) -> None:
        """Open Net Sales Book in a standalone popup window."""
        from db import DB_PATH
        db_path = getattr(self.db, 'db_path', None) or DB_PATH
        self._net_sales_window = open_net_sales_book_window(self, db_path=db_path, existing_window=self._net_sales_window)

    def load_day_book(self):
        """Load Day Book entries for selected date range."""
        if not self.company_id:
            return
        if self._is_loading:
            print(f'[Day Book UI] Load already in progress, skipping')
            return
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        summarize_entries = self.summarise_entries_checkbox.isChecked()
        summarize_debtors = self.summarise_debtors_checkbox.isChecked()
        print(f'[Day Book UI] load_day_book called: from_date={from_date}, to_date={to_date}')
        self._start_day_book_worker(from_date, to_date, summarize_entries, summarize_debtors)

    def _start_day_book_worker(self, from_date: str, to_date: str, summarize_entries: bool, summarize_debtors: bool):
        thread = QThread(self)
        worker = DayBookWorker(getattr(self.db, 'db_type', None), getattr(self.db, 'db_path', None), self.company_id, from_date, to_date, summarize_entries, summarize_debtors)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(self._handle_day_book_result)
        worker.error.connect(lambda message: QMessageBox.warning(self, 'Error', message))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._day_book_worker_finished)
        self._day_book_thread = thread
        self._day_book_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _handle_day_book_result(self, result: Dict[str, Any]):
        entries = result.get('entries', [])
        print(f'[Day Book UI] Loaded {len(entries)} entries')
        self.current_rows = entries
        self.populate_table(entries)
        self.update_summary_labels(result.get('summary', {}))
        if len(entries) == 0:
            self.show_no_data('No Day Book entries found in selected date range.')

    def _set_loading_state(self, is_loading: bool):
        self._is_loading = is_loading
        self.load_btn.setEnabled(not is_loading)
        self.refresh_btn.setEnabled(not is_loading)
        self.from_date.setEnabled(not is_loading)
        self.to_date.setEnabled(not is_loading)
        self.summarise_entries_checkbox.setEnabled(not is_loading)
        self.summarise_debtors_checkbox.setEnabled(not is_loading)
        self.load_btn.setText('Loading...' if is_loading else 'Load')

    def _day_book_worker_finished(self):
        self._day_book_thread = None
        self._day_book_worker = None
        self._set_loading_state(False)

    def populate_table(self, entries: List[Dict[str, Any]]):
        """Populate table with user-defined Day Book rows."""
        self.table.setColumnCount(len(DAY_BOOK_HEADERS))
        self.table.setHorizontalHeaderLabels(DAY_BOOK_HEADERS)
        self.table.setRowCount(len(entries))
        row_colors = book_report_special_row_colors()
        special_colors = {
            'opening': QColor(row_colors['opening']),
            'total': QColor(row_colors['total']),
            'closing_balance': QColor(row_colors['closing_balance']),
            'separator': QColor(row_colors['separator_bg']),
        }
        highlight_fg = QColor(row_colors['highlight_fg'])
        for row_idx, entry in enumerate(entries):
            row_type = entry.get('row_type', 'activity')
            raw_date = entry.get('date', '')
            date_text = format_display_date(raw_date)
            if row_idx > 0 and row_type not in ('opening', 'separator'):
                prev = entries[row_idx - 1]
                if prev.get('date') == raw_date:
                    date_text = ''
            values = [date_text, entry.get('voucher_no', ''), entry.get('particulars', ''), f"{entry.get('debit', 0.0):.2f}" if entry.get('debit', 0.0) else '', f"{entry.get('credit', 0.0):.2f}" if entry.get('credit', 0.0) else '', entry.get('voucher_type') or entry.get('entry_type', '')]
            bg = special_colors.get(row_type)
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, entry)
                if col in (3, 4):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if bg is not None:
                    item.setBackground(bg)
                    if row_type in ('opening', 'total', 'closing_balance'):
                        item.setForeground(highlight_fg)
                if row_type in ('opening', 'total', 'closing_balance'):
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                if row_type == 'separator':
                    item.setForeground(QColor(row_colors['separator_fg']))
                self.table.setItem(row_idx, col, item)
        apply_adjustable_table_columns(self.table)
        self._restore_memory_table(self.table, "table")

    def update_summary_labels(self, summary: Dict[str, Any]):
        """Update summary labels with Day Book totals."""
        self.cash_sales_label.setText(f"Opening: {summary.get('opening_balance', 0.0):.2f}")
        self.credit_sales_label.setText(f"Receipts (Dr): {summary.get('day_debit_total', 0.0):.2f}")
        self.cash_purchase_label.setText(f"Payments (Cr): {summary.get('day_credit_total', 0.0):.2f}")
        self.credit_purchase_label.setText(f"Cash/Bank Dr: {summary.get('cash_bank_debit_total', 0.0):.2f}")
        self.sales_return_label.setText(f"Cash/Bank Cr: {summary.get('cash_bank_credit_total', 0.0):.2f}")
        self.purchase_return_label.setText(f"Closing: {summary.get('closing_balance', 0.0):.2f}")

    def _clean_pdf_text(self, value: Any) -> str:
        """Return single-line text safe for fixed PDF table columns."""
        return ' '.join(str(value or '').replace('\r', '\n').replace('\t', ' ').split())

    def _build_pdf_row(self, values: List[Any]) -> List[str]:
        """Build one strict six-column PDF row with sanitized text cells."""
        source_values = list(values)
        if len(source_values) == 4:
            combined_text = str(source_values[1] or '').replace('\r', '\n')
            combined_parts = combined_text.split('\n', 1)
            if len(combined_parts) == 2:
                source_values = [source_values[0], combined_parts[0], combined_parts[1], source_values[2], source_values[3], '']
        normalized_values = list(source_values[:6])
        if len(normalized_values) < 6:
            normalized_values.extend([''] * (6 - len(normalized_values)))
        voucher_no = self._clean_pdf_text(normalized_values[1])
        row = [self._clean_pdf_text(normalized_values[0]), voucher_no, self._clean_pdf_particulars(normalized_values[2], voucher_no), self._clean_pdf_text(normalized_values[3]), self._clean_pdf_text(normalized_values[4]), self._clean_pdf_text(normalized_values[5])]
        assert len(row) == 6
        return row

    def _clean_pdf_particulars(self, particulars: Any, voucher_no: Any) -> str:
        """Keep voucher numbers out of particulars while removing line breaks."""
        voucher_text = self._clean_pdf_text(voucher_no)
        raw_lines = str(particulars or '').replace('\r', '\n').split('\n')
        cleaned_lines = []
        for line in raw_lines:
            cleaned_line = self._clean_pdf_text(line)
            if not cleaned_line:
                continue
            line_key = cleaned_line.lower()
            voucher_key = voucher_text.lower()
            voucher_labels = (voucher_key, f'voucher no: {voucher_key}', f'voucher no. {voucher_key}', f'voucher: {voucher_key}')
            if voucher_text and line_key in voucher_labels:
                continue
            cleaned_lines.append(cleaned_line)
        return self._clean_pdf_text(' '.join(cleaned_lines))

    def _format_pdf_amount(self, value: Any) -> str:
        """Format Day Book money values without allowing blank numeric cells."""
        try:
            return f'{float(value or 0.0):.2f}'
        except (TypeError, ValueError):
            return '0.00'

    def _build_pdf_table_values(self, entries: List[Dict[str, Any]]) -> List[List[str]]:
        """Build strict Date, V.No, Particulars, Debit, Credit, Voucher Type PDF rows."""
        table_values = [self._build_pdf_row(DAY_BOOK_HEADERS)]
        for entry in entries:
            row = self._build_pdf_row([entry.get('date', ''), entry.get('voucher_no', ''), entry.get('particulars', ''), self._format_pdf_amount(entry.get('debit', 0.0)), self._format_pdf_amount(entry.get('credit', 0.0)), entry.get('voucher_type') or entry.get('entry_type', '')])
            table_values.append(row)
            assert len(table_values[-1]) == 6
        return table_values

    def _pdf_column_widths(self) -> List[int]:
        """Return six fixed Day Book PDF column widths."""
        return [65, 80, 330, 80, 80, 95]

    def on_row_double_clicked(self, item: QTableWidgetItem):
        """Handle double-click on a row for drill-down."""
        entry = item.data(Qt.UserRole)
        if not entry:
            return
        drilldown_mode = entry.get('drilldown_mode', '')
        voucher_type = entry.get('voucher_type', '')
        voucher_id = entry.get('voucher_id')
        entry_date = entry.get('date', '')
        main_window = self.parent()
        while main_window and (not hasattr(main_window, 'open_voucher_for_edit')):
            main_window = main_window.parent()
        if drilldown_mode == 'open_voucher' and voucher_id:
            if main_window and hasattr(main_window, 'open_voucher_for_edit'):
                main_window.open_voucher_for_edit(voucher_type, voucher_id)
            else:
                QMessageBox.information(self, 'Info', f'Opening voucher {voucher_type} #{voucher_id} is not connected.')
        elif drilldown_mode == 'open_sales_book':
            if main_window:
                from_date = qdate_to_db(self.from_date.date())
                to_date = qdate_to_db(self.to_date.date())
                self.open_book_with_filter(main_window, 'Sales Book', from_date, to_date)
        elif drilldown_mode == 'open_purchase_book':
            if main_window:
                from_date = qdate_to_db(self.from_date.date())
                to_date = qdate_to_db(self.to_date.date())
                self.open_book_with_filter(main_window, 'Purchase Book', from_date, to_date)
        else:
            QMessageBox.information(self, 'Info', 'This action is not yet supported.')

    def _find_main_window(self):
        """Return the nearest parent that can route module pages."""
        main_window = self.parent()
        while main_window:
            if hasattr(main_window, 'sidebar') or hasattr(main_window, '_open_module_windows'):
                return main_window
            main_window = main_window.parent()
        return None

    def _book_name_for_voucher_type(self, voucher_type: str) -> str:
        """Map a voucher type label to the matching book report name."""
        normalized_type = str(voucher_type or '').strip().lower().replace('-', '_').replace(' ', '_')
        if not normalized_type:
            return ''
        if 'sales_return' in normalized_type or normalized_type in ('sale_return', 'return_sales'):
            return 'Sales Return Book'
        if 'purchase_return' in normalized_type or normalized_type in ('return_purchase',):
            return 'Purchase Return Book'
        if normalized_type.startswith('sales') or normalized_type in ('sale', 'cash_sale', 'credit_sale'):
            return 'Sales Book'
        if normalized_type.startswith('purchase') or normalized_type in ('cash_purchase', 'credit_purchase'):
            return 'Purchase Book'
        return ''

    def handle_row_double_click(self, row: int, column: int):
        """Open the related book report filtered to the clicked row date."""
        del column
        if row < 0:
            return
        first_item = self.table.item(row, 0)
        row_item = first_item or self.table.item(row, 1) or self.table.item(row, 2)
        entry = row_item.data(Qt.UserRole) if row_item else None
        if not entry:
            return
        if entry.get('row_type') in ('opening', 'total', 'closing_balance', 'separator'):
            return
        entry_date = str(entry.get('date') or '').strip()
        voucher_type = str(entry.get('voucher_type') or entry.get('entry_type') or '').strip()
        book_name = self._book_name_for_voucher_type(voucher_type)
        if not entry_date or not book_name:
            return
        main_window = self._find_main_window()
        if main_window:
            self.open_book_with_filter(main_window, book_name, entry_date, entry_date)

    def open_book_with_filter(self, main_window, book_name: str, from_date: str, to_date: str):
        """Open a book page with date filter applied."""
        if hasattr(main_window, 'sidebar'):
            main_window.sidebar.page_changed.emit(book_name)
        if hasattr(main_window, '_open_module_windows'):
            for window_key, window in main_window._open_module_windows.items():
                if book_name.lower().replace(' ', '_') in window_key.lower():
                    widget = window.centralWidget()
                    if widget:
                        if hasattr(widget, 'from_date') and hasattr(widget, 'to_date'):
                            try:
                                widget.from_date.setDate(QDate.fromString(from_date, 'yyyy-MM-dd'))
                                widget.to_date.setDate(QDate.fromString(to_date, 'yyyy-MM-dd'))
                                if hasattr(widget, 'load_report'):
                                    widget.load_report()
                                elif hasattr(widget, 'load_data'):
                                    widget.load_data()
                                elif hasattr(widget, 'refresh'):
                                    widget.refresh()
                            except:
                                pass
                    break

    def show_export_menu(self):
        """Show export menu instantly without heavy work."""
        if not self._export_menu_warmed:
            self.export_menu.popup(QPoint(0, 0))
            self.export_menu.hide()
            self._export_menu_warmed = True
        pos = self.export_btn.mapToGlobal(self.export_btn.rect().bottomLeft())
        action = self.export_menu.exec(pos)
        if action == self.excel_action:
            self.export_excel()
        elif action == self.pdf_action:
            self.export_pdf()
        elif action == self.csv_action:
            self.export_csv()

    def export_excel(self):
        """Export Day Book to Excel using openpyxl."""
        if not self.current_rows:
            QMessageBox.information(self, 'No Data', 'No data to export.')
            return
        try:
            from openpyxl import Workbook
        except Exception:
            QMessageBox.information(self, 'Export', 'openpyxl is not installed.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export Excel', 'day_book.xlsx', 'Excel Files (*.xlsx)')
        if not path:
            return
        try:
            wb = Workbook()
            ws = wb.active
            ws.title = 'Day Book'
            ws.append(DAY_BOOK_HEADERS)
            for entry in self.current_rows:
                row = [entry.get('date', ''), entry.get('voucher_no', ''), entry.get('particulars', ''), entry.get('debit', 0.0), entry.get('credit', 0.0), entry.get('voucher_type') or entry.get('entry_type', '')]
                ws.append(row)
            wb.save(path)
            QMessageBox.information(self, 'Export', f'Exported to {path}')
        except Exception as e:
            QMessageBox.warning(self, 'Export Error', f'Failed to export: {str(e)}')

    def export_pdf(self):
        """Open Day Book in the universal print/PDF preview dialog."""
        if not self.current_rows:
            QMessageBox.information(self, 'No Data', 'No data to export.')
            return
        html_string = self._build_preview_html()
        dialog = UniversalPreviewDialog(html_string, self)
        dialog.exec()

    def export_csv(self):
        """Export Day Book to CSV using Python csv module."""
        if not self.current_rows:
            QMessageBox.information(self, 'No Data', 'No data to export.')
            return
        import csv
        path, _ = QFileDialog.getSaveFileName(self, 'Export CSV', 'day_book.csv', 'CSV Files (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(DAY_BOOK_HEADERS)
                for entry in self.current_rows:
                    row = [entry.get('date', ''), entry.get('voucher_no', ''), entry.get('particulars', ''), str(entry.get('debit', 0.0)), str(entry.get('credit', 0.0)), entry.get('voucher_type') or entry.get('entry_type', '')]
                    writer.writerow(row)
            QMessageBox.information(self, 'Export', f'Exported to {path}')
        except Exception as e:
            QMessageBox.warning(self, 'Export Error', f'Failed to export: {str(e)}')

    def show_preview(self):
        """Show Day Book in the universal print/PDF preview dialog."""
        if not self.current_rows:
            QMessageBox.information(self, 'No Data', 'No data to preview.')
            return
        dialog = UniversalPreviewDialog(self._build_preview_html(), self)
        dialog.exec()

    def _build_preview_html(self) -> str:
        """Build Day Book preview HTML from the currently visible table."""
        subtitle = f"{qdate_to_display(self.from_date.date())} to {qdate_to_display(self.to_date.date())}"
        summary_lines = [self.cash_sales_label.text(), self.credit_sales_label.text(), self.cash_purchase_label.text(), self.credit_purchase_label.text(), self.sales_return_label.text(), self.purchase_return_label.text()]
        if self.summarise_entries_checkbox.isChecked():
            summary_lines.append('Summarise Entries: Yes')
        if self.summarise_debtors_checkbox.isChecked():
            summary_lines.append('Summarise Debtors: Yes')
        return table_widget_to_html(self.table, 'Day Book', subtitle, summary_lines)

    def show_debitor_summary(self):
        """Show debitor summary dialog."""
        if not self.company_id:
            QMessageBox.information(self, 'Info', 'Please open a company first.')
            return
        dialog = PartySummaryDialog('Debtor Summary', [], self, from_date=self.from_date.date(), to_date=self.to_date.date(), load_callback=lambda start, end: self.day_book_logic.get_debitor_summary(self.company_id, start, end))
        dialog.exec()

    def show_creditor_summary(self):
        """Show creditor summary dialog."""
        if not self.company_id:
            QMessageBox.information(self, 'Info', 'Please open a company first.')
            return
        dialog = PartySummaryDialog('Creditor Summary', [], self, from_date=self.from_date.date(), to_date=self.to_date.date(), load_callback=lambda start, end: self.day_book_logic.get_creditor_summary(self.company_id, start, end))
        dialog.exec()

    def show_no_data(self, message: str):
        """Show no data message in table."""
        self.table.setRowCount(1)
        self.table.setItem(0, 0, QTableWidgetItem(message))
        self.table.setSpan(0, 0, 1, self.table.columnCount())

    def set_date_range(self, from_date: str, to_date: str):
        """Set date range programmatically."""
        try:
            self.from_date.setDate(QDate.fromString(from_date, 'yyyy-MM-dd'))
            self.to_date.setDate(QDate.fromString(to_date, 'yyyy-MM-dd'))
        except:
            pass

class DayBookPreviewDialog(UiMemoryMixin, QDialog):
    """Read-only Day Book preview dialog."""

    def __init__(self, entries: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.entries = entries
        self.setWindowTitle('Day Book Preview')
        self.setMinimumSize(900, 600)
        self._build_ui()
        self._init_ui_memory()

    def _build_ui(self):
        """Build preview dialog UI."""
        self.setStyleSheet(page_background_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        header = QLabel('Day Book Preview (Read-Only)')
        header.setStyleSheet(page_heading_style(18))
        layout.addWidget(header)
        self.table = QTableWidget()
        apply_read_only_report_table_selection(self.table)
        self.table.setColumnCount(len(DAY_BOOK_HEADERS))
        self.table.setHorizontalHeaderLabels(DAY_BOOK_HEADERS)
        self.populate_table()
        layout.addWidget(self.table)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        print_btn = QPushButton('Print')
        export_btn = QPushButton('Export')
        close_btn = QPushButton('Close')
        for btn in (print_btn, export_btn, close_btn):
            btn.setStyleSheet(compact_primary_button_style())
        print_btn.clicked.connect(self.print_preview)
        export_btn.clicked.connect(self.export_preview)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(print_btn)
        button_layout.addWidget(export_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

    def populate_table(self):
        """Populate table with entries."""
        self.table.setRowCount(len(self.entries))
        for row_idx, entry in enumerate(self.entries):
            date_item = QTableWidgetItem(format_display_date(entry.get('date', '')))
            voucher_no_item = QTableWidgetItem(entry.get('voucher_no', ''))
            particulars_item = QTableWidgetItem(entry.get('particulars', ''))
            debit = entry.get('debit', 0.0)
            credit = entry.get('credit', 0.0)
            debit_item = QTableWidgetItem(f'{debit:.2f}' if debit else '')
            credit_item = QTableWidgetItem(f'{credit:.2f}' if credit else '')
            voucher_type_item = QTableWidgetItem(entry.get('voucher_type') or entry.get('entry_type', ''))
            debit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            credit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 0, date_item)
            self.table.setItem(row_idx, 1, voucher_no_item)
            self.table.setItem(row_idx, 2, particulars_item)
            self.table.setItem(row_idx, 3, debit_item)
            self.table.setItem(row_idx, 4, credit_item)
            self.table.setItem(row_idx, 5, voucher_type_item)
        apply_adjustable_table_columns(self.table)

    def print_preview(self):
        """Print preview using QPrinter."""
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec() == QPrintDialog.DialogCode.Accepted:
                QMessageBox.information(self, 'Print', 'Print functionality requires additional implementation.')
        except Exception as e:
            QMessageBox.warning(self, 'Print Error', f'Failed to print: {str(e)}')

    def export_preview(self):
        """Export preview data."""
        parent = self.parent()
        if parent and hasattr(parent, 'export_excel'):
            parent.export_excel()
        elif parent and hasattr(parent, 'export_csv'):
            parent.export_csv()
        else:
            QMessageBox.information(self, 'Export', 'Export functionality not available.')

class PartySummaryDialog(UiMemoryMixin, QDialog):
    """Dialog showing debitor or creditor summary."""

    def __init__(self, title: str, entries: List[Dict[str, Any]], parent=None, from_date: Optional[Any]=None, to_date: Optional[Any]=None, load_callback: Optional[Callable[[str, str], Dict[str, Any]]]=None):
        """Initialize the party summary dialog with optional date-range loading."""
        super().__init__(parent)
        self.title = title
        self.entries = entries
        self.initial_from_date = self._coerce_qdate(from_date)
        self.initial_to_date = self._coerce_qdate(to_date)
        self.load_callback = load_callback
        self.setWindowTitle(title)
        self.setMinimumSize(700, 500)
        self._build_ui()
        self._init_ui_memory()

    def _coerce_qdate(self, value: Optional[Any]) -> QDate:
        """Convert supported date values to a valid QDate."""
        if isinstance(value, QDate) and value.isValid():
            return value
        if isinstance(value, str):
            parsed = QDate.fromString(value[:10], 'yyyy-MM-dd')
            if parsed.isValid():
                return parsed
        return QDate.currentDate()

    def _build_ui(self):
        """Build summary dialog UI."""
        self.setStyleSheet(page_background_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        header = QLabel(self.title)
        header.setStyleSheet(page_heading_style(18))
        layout.addWidget(header)
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(10)
        from_label = QLabel('From Date:')
        from_label.setStyleSheet(compact_label_style())
        self.from_date = QDateEdit()
        self.from_date.setDate(self.initial_from_date)
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        to_label = QLabel('To Date:')
        to_label.setStyleSheet(compact_label_style())
        self.to_date = QDateEdit()
        self.to_date.setDate(self.initial_to_date)
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        self.load_btn = QPushButton('Load/Refresh')
        self.load_btn.setStyleSheet(compact_primary_button_style())
        self.load_btn.setMinimumHeight(32)
        self.load_btn.setMinimumWidth(110)
        self.load_btn.clicked.connect(self.load_summary)
        filter_layout.addWidget(from_label)
        filter_layout.addWidget(self.from_date)
        filter_layout.addWidget(to_label)
        filter_layout.addWidget(self.to_date)
        filter_layout.addWidget(self.load_btn)
        filter_layout.addStretch()
        layout.addWidget(filter_frame)
        self.table = QTableWidget()
        apply_read_only_report_table_selection(self.table)
        columns = ['Party Name', 'Opening Balance', 'Debit', 'Credit', 'Closing Balance']
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.populate_table()
        layout.addWidget(self.table)
        if self.load_callback:
            self.load_summary()
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton('Close')
        close_btn.setStyleSheet(compact_primary_button_style())
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

    def populate_table(self):
        """Populate table with summary entries."""
        self.table.setRowCount(len(self.entries))
        for row_idx, entry in enumerate(self.entries):
            party_name_item = QTableWidgetItem(entry.get('party_name', ''))
            opening_item = QTableWidgetItem(f"{entry.get('opening_balance', 0.0):.2f}")
            debit_item = QTableWidgetItem(f"{entry.get('debit', 0.0):.2f}")
            credit_item = QTableWidgetItem(f"{entry.get('credit', 0.0):.2f}")
            closing_item = QTableWidgetItem(f"{entry.get('closing_balance', 0.0):.2f}")
            self.table.setItem(row_idx, 0, party_name_item)
            self.table.setItem(row_idx, 1, opening_item)
            self.table.setItem(row_idx, 2, debit_item)
            self.table.setItem(row_idx, 3, credit_item)
            self.table.setItem(row_idx, 4, closing_item)
        apply_adjustable_table_columns(self.table)

    def load_summary(self):
        """Load summary rows for the currently selected date range."""
        if not self.load_callback:
            self.populate_table()
            return
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        try:
            result = self.load_callback(from_date, to_date)
        except Exception as exc:
            QMessageBox.warning(self, 'Error', f'Failed to load {self.title}: {str(exc)}')
            return
        if not result.get('success'):
            QMessageBox.warning(self, 'Error', result.get('message', f'Failed to load {self.title}'))
            return
        self.entries = result.get('data', [])
        self.populate_table()