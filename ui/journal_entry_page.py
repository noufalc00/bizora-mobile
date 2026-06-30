"""
Journal Entry Page UI.

Top bar fields:
- Voucher No
- Date
- Remark
- Narration

Lines table:
- Account (searchable)
- Debit
- Credit
- Narration
- Add/Delete line buttons
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFrame, QAbstractItemView, QStyledItemDelegate, QStyle, QStyleOptionViewItem, QLineEdit, QComboBox
from PySide6.QtCore import Qt, QDate, QEvent, QTimer
from PySide6.QtGui import QKeyEvent, QPen, QColor
from ui.voucher_common import VoucherTopBar, AccountComboBox, create_date_edit, create_line_edit, parse_currency, format_currency
from bizora_core.common_finance import MONEY_ZERO, to_decimal
from bizora_core.journal_entry_logic import JournalEntryLogic
from bizora_core.ledger_logic import LedgerLogic
from ui import theme
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
from ui.entry_field_helpers import install_click_select_all


class JournalLineRowDelegate(QStyledItemDelegate):
    """Draw Sales Entry-style row outline when SL No is clicked."""

    def __init__(self, page: "JournalEntryPageWidget"):
        super().__init__(page.lines_table)
        self.page = page

    def paint(self, painter, option, index):
        """Paint SL cell and optional full-row outline selection."""
        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.State_Selected
        super().paint(painter, clean_option, index)

        if getattr(self.page, "manually_selected_row", -1) != index.row():
            return

        table = self.page.lines_table
        rect = option.rect
        pen = QPen(QColor(theme.grid_selection_pen_color()))
        pen.setWidth(2)
        painter.save()
        painter.setPen(pen)
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if index.column() == 0:
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
        if index.column() == table.columnCount() - 1:
            painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.restore()


class JournalEntryPageWidget(UiMemoryMixin, QWidget):
    """Journal Entry voucher page."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.logic = JournalEntryLogic(db)
        self.ledger_logic = LedgerLogic(db)
        self.current_voucher_id = None
        self.company_id = None
        self.all_accounts = []
        self.manually_selected_row = -1
        self._init_ui()
        self._load_company()
        self._init_ui_memory()

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.setStyleSheet(theme.entry_page_background_style())
        self.setLayout(layout)
        top_bar_frame = QFrame()
        top_bar_frame.setStyleSheet(theme.entry_header_strip_style())
        top_bar_layout = QHBoxLayout(top_bar_frame)
        top_bar_layout.setSpacing(8)
        top_bar_layout.setContentsMargins(8, 6, 8, 6)
        voucher_layout = QHBoxLayout()
        voucher_layout.setSpacing(2)
        voucher_label = QLabel('Voucher No:')
        voucher_label.setStyleSheet(theme.sales_micro_label_style())
        self.txt_voucher_no = create_line_edit('JV-0001')
        self.txt_voucher_no.setFixedWidth(70)
        voucher_layout.addWidget(voucher_label)
        voucher_layout.addWidget(self.txt_voucher_no)
        nav_container = QWidget()
        nav_container.setFixedWidth(18)
        nav_v = QVBoxLayout(nav_container)
        nav_v.setSpacing(1)
        nav_v.setContentsMargins(0, 0, 0, 0)
        self.btn_prev_voucher = QPushButton('▲')
        self.btn_prev_voucher.setStyleSheet(self.nav_button_style())
        self.btn_prev_voucher.setFixedSize(18, 11)
        self.btn_prev_voucher.clicked.connect(self._on_next_voucher)
        nav_v.addWidget(self.btn_prev_voucher)
        self.btn_next_voucher = QPushButton('▼')
        self.btn_next_voucher.setStyleSheet(self.nav_button_style())
        self.btn_next_voucher.setFixedSize(18, 11)
        self.btn_next_voucher.clicked.connect(self._on_previous_voucher)
        nav_v.addWidget(self.btn_next_voucher)
        voucher_layout.addWidget(nav_container)
        reset_btn = QPushButton('Reset')
        reset_btn.setStyleSheet(theme.sales_compact_button_style())
        reset_btn.setFixedWidth(50)
        reset_btn.clicked.connect(self._on_clear)
        voucher_layout.addWidget(reset_btn)
        top_bar_layout.addLayout(voucher_layout)
        date_layout = QHBoxLayout()
        date_layout.setSpacing(2)
        date_label = QLabel('Date:')
        date_label.setStyleSheet(theme.sales_micro_label_style())
        self.date_voucher = create_date_edit()
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.date_voucher)
        top_bar_layout.addLayout(date_layout)
        remark_layout = QHBoxLayout()
        remark_layout.setSpacing(2)
        remark_label = QLabel('Remark:')
        remark_label.setStyleSheet(theme.sales_micro_label_style())
        self.txt_remark = create_line_edit()
        self.txt_remark.setFixedWidth(200)
        remark_layout.addWidget(remark_label)
        remark_layout.addWidget(self.txt_remark)
        top_bar_layout.addLayout(remark_layout)
        top_bar_layout.addStretch()
        layout.addWidget(top_bar_frame)
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet(f"background-color: {theme._theme_colors()['border']};")
        layout.addWidget(separator)
        lines_label = QLabel('Journal Lines')
        lines_label.setStyleSheet(theme.sales_micro_label_style())
        layout.addWidget(lines_label)
        self.lines_table = QTableWidget()
        self._setup_lines_table()
        layout.addWidget(self.lines_table)
        line_buttons = QHBoxLayout()
        self.btn_add_line = QPushButton('Add Line')
        self.btn_delete_line = QPushButton('Delete Line')
        self._style_line_buttons()
        line_buttons.addWidget(self.btn_add_line)
        line_buttons.addWidget(self.btn_delete_line)
        line_buttons.addStretch()
        layout.addLayout(line_buttons)
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        separator2.setStyleSheet(f"background-color: {theme._theme_colors()['border']};")
        layout.addWidget(separator2)
        summary_layout = QHBoxLayout()
        self.lbl_total_debit = QLabel('Total Debit: 0.00')
        self.lbl_total_credit = QLabel('Total Credit: 0.00')
        self.lbl_difference = QLabel('Difference: 0.00')
        self._style_summary_labels()
        summary_layout.addWidget(self.lbl_total_debit)
        summary_layout.addWidget(self.lbl_total_credit)
        summary_layout.addWidget(self.lbl_difference)
        summary_layout.addStretch()
        layout.addLayout(summary_layout)
        button_bar = QHBoxLayout()
        self.btn_save = QPushButton('Save')
        self.btn_update = QPushButton('Update')
        self.btn_delete = QPushButton('Delete')
        self.btn_clear = QPushButton('Clear')
        self._style_buttons()
        button_bar.addWidget(self.btn_save)
        button_bar.addWidget(self.btn_update)
        button_bar.addWidget(self.btn_delete)
        button_bar.addWidget(self.btn_clear)
        button_bar.addStretch()
        layout.addLayout(button_bar)
        self.history_table = QTableWidget()
        self._setup_history_table()
        layout.addWidget(self.history_table)
        self._connect_signals()

    def nav_button_style(self):
        """Navigation button style (Sales Entry pattern)."""
        return theme.sales_nav_button_style()

    def _setup_lines_table(self):
        """Setup lines table."""
        self.lines_table.setColumnCount(5)
        self.lines_table.setHorizontalHeaderLabels(['SL No', 'Account', 'Debit', 'Credit', 'Narration'])
        self.lines_table.setColumnWidth(0, 52)
        self.lines_table.setColumnWidth(1, 280)
        self.lines_table.setColumnWidth(2, 110)
        self.lines_table.setColumnWidth(3, 110)
        self.lines_table.setColumnWidth(4, 300)
        apply_adjustable_table_columns(self.lines_table, auto_size=False)
        self.lines_table.horizontalHeader().setVisible(True)
        self.lines_table.verticalHeader().setVisible(False)
        self.lines_table.setAlternatingRowColors(True)
        self.lines_table.setSelectionBehavior(QTableWidget.SelectItems)
        self.lines_table.setSelectionMode(QTableWidget.SingleSelection)
        self.lines_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lines_table.verticalHeader().setDefaultSectionSize(40)
        self.lines_table.setStyleSheet(theme.sales_billing_table_style())
        self.lines_table.horizontalHeader().setStyleSheet(theme.entry_table_header_style())
        self.lines_table.setFocusPolicy(Qt.StrongFocus)
        self.lines_table.setItemDelegate(JournalLineRowDelegate(self))
        self.lines_table.viewport().installEventFilter(self)

    def _setup_history_table(self):
        """Setup history table."""
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(['Voucher No', 'Date', 'Remark', 'Narration'])
        apply_read_only_report_table_selection(self.history_table)

    def _style_line_buttons(self):
        """Style line buttons."""
        self.btn_add_line.setStyleSheet(theme.sales_primary_button_style())
        self.btn_delete_line.setStyleSheet(theme.sales_danger_button_style())

    def _style_summary_labels(self):
        """Style summary labels."""
        colors = theme._theme_colors()
        label_style = f"\n            QLabel {{\n                color: {colors['input_text']};\n                font-size: 12px;\n                padding: 5px;\n                background-color: {colors['panel_bg']};\n                border: 1px solid {colors['border']};\n                border-radius: 4px;\n            }}\n        "
        self.lbl_total_debit.setStyleSheet(label_style)
        self.lbl_total_credit.setStyleSheet(label_style)
        self.lbl_difference.setStyleSheet(label_style)

    def _style_buttons(self):
        """Style buttons."""
        self.btn_save.setStyleSheet(theme.sales_primary_button_style())
        self.btn_update.setStyleSheet(theme.sales_primary_button_style())
        self.btn_delete.setStyleSheet(theme.sales_danger_button_style())
        self.btn_clear.setStyleSheet(theme.sales_compact_button_style())

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(theme.entry_page_background_style())
        self._style_line_buttons()
        self._style_summary_labels()
        self._style_buttons()
        if hasattr(self, 'lines_table'):
            self.lines_table.setStyleSheet(theme.sales_billing_table_style())
            self.lines_table.horizontalHeader().setStyleSheet(theme.entry_table_header_style())
        if hasattr(self, 'history_table'):
            self.history_table.setStyleSheet(theme.sales_billing_table_style())
            self.history_table.horizontalHeader().setStyleSheet(theme.entry_table_header_style())

    def _connect_signals(self):
        """Connect signals."""
        self.btn_save.clicked.connect(self._on_save)
        self.btn_update.clicked.connect(self._on_update)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_add_line.clicked.connect(self._on_add_line)
        self.btn_delete_line.clicked.connect(self._on_delete_line)
        self.history_table.itemSelectionChanged.connect(self._on_history_selection)
        self.lines_table.itemChanged.connect(self._on_line_changed)

    def _load_company(self):
        """Load active company."""
        try:
            from config import active_company_manager
            self.company_id = active_company_manager.get_active_company_id()
            if self.company_id:
                self._load_data()
            else:
                QMessageBox.warning(self, 'No Company', 'Please open a company first.')
        except Exception as e:
            print(f'Error loading company: {e}')

    def _load_data(self):
        """Load dropdown data and history."""
        if not self.company_id:
            return
        self.ledger_logic.ensure_system_accounts(self.company_id)
        self.all_accounts = self.logic.get_non_system_accounts(self.company_id)
        next_voucher = self.logic.get_next_voucher_no(self.company_id)
        self.txt_voucher_no.setText(next_voucher)
        self._load_history()
        self._on_new()

    def _load_history(self):
        """Load voucher history."""
        if not self.company_id:
            return
        journals = self.logic.get_journal_entries(self.company_id)
        self.history_table.setRowCount(0)
        for journal in journals:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            self.history_table.setItem(row, 0, QTableWidgetItem(journal.get('voucher_no', '')))
            self.history_table.setItem(row, 1, QTableWidgetItem(format_display_date(journal.get('voucher_date', ''))))
            self.history_table.setItem(row, 2, QTableWidgetItem(journal.get('remark', '')))
            self.history_table.setItem(row, 3, QTableWidgetItem(journal.get('narration', '')))
            self.history_table.item(row, 0).setData(Qt.UserRole, journal['id'])
        apply_adjustable_table_columns(self.history_table)

    def _on_new(self):
        """Handle New button (Clear form for new entry)."""
        self._clear_form()
        next_voucher = self.logic.get_next_voucher_no(self.company_id)
        self.txt_voucher_no.setText(next_voucher)
        self.current_voucher_id = None
        self.manually_selected_row = -1
        self.lines_table.setRowCount(0)
        self._add_line()
        self._update_totals()
        self.btn_save.setVisible(True)
        self.btn_update.setVisible(False)

    def _on_next_voucher(self):
        """Handle ▲ button - go to next voucher (newer)."""
        current_row = self.history_table.currentRow()
        if current_row < self.history_table.rowCount() - 1:
            self.history_table.selectRow(current_row + 1)

    def _on_previous_voucher(self):
        """Handle ▼ button - go to previous voucher (older)."""
        current_row = self.history_table.currentRow()
        if current_row > 0:
            self.history_table.selectRow(current_row - 1)

    def _on_add_line(self):
        """Handle Add Line button."""
        self._add_line()

    def _add_line(self, account_id=None, debit=0.0, credit=0.0, narration=''):
        """Add a new line to the table."""
        row = self.lines_table.rowCount()
        self.lines_table.insertRow(row)
        sl_item = QTableWidgetItem(str(row + 1))
        sl_item.setTextAlignment(Qt.AlignCenter)
        sl_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.lines_table.setItem(row, 0, sl_item)
        account_combo = AccountComboBox()
        account_combo.load_accounts(self.all_accounts)
        if account_id:
            account_combo.set_account_id(int(account_id))
        self.lines_table.setCellWidget(row, 1, account_combo)
        debit_edit = create_line_edit()
        debit_edit.setPlaceholderText('0.00')
        theme.prepare_sales_cell_editor(debit_edit)
        self.lines_table.setCellWidget(row, 2, debit_edit)
        credit_edit = create_line_edit()
        credit_edit.setPlaceholderText('0.00')
        theme.prepare_sales_cell_editor(credit_edit)
        self.lines_table.setCellWidget(row, 3, credit_edit)
        narration_edit = create_line_edit()
        narration_edit.setPlaceholderText('Narration...')
        theme.prepare_sales_cell_editor(narration_edit)
        self.lines_table.setCellWidget(row, 4, narration_edit)
        debit_edit.setText(format_currency(debit) if debit else '')
        credit_edit.setText(format_currency(credit) if credit else '')
        narration_edit.setText(str(narration or ''))
        debit_edit.textChanged.connect(self._update_totals)
        credit_edit.textChanged.connect(self._update_totals)
        for widget in (account_combo, debit_edit, credit_edit, narration_edit):
            widget.installEventFilter(self)
            install_click_select_all(widget)

    def _refresh_line_sl_numbers(self) -> None:
        """Refresh serial numbers in the SL No column."""
        for row in range(self.lines_table.rowCount()):
            item = self.lines_table.item(row, 0)
            if item is None:
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.lines_table.setItem(row, 0, item)
            item.setText(str(row + 1))

    def _focus_line_widget(self, row: int, column: int) -> None:
        """Focus an embedded journal line widget and select all text."""
        widget = self.lines_table.cellWidget(row, column)
        if widget is None:
            return
        widget.setFocus()
        if isinstance(widget, QLineEdit):
            QTimer.singleShot(0, widget.selectAll)
            return
        if isinstance(widget, QComboBox):
            line_edit = widget.lineEdit()
            if line_edit is not None:
                QTimer.singleShot(0, line_edit.selectAll)

    def _on_delete_line(self):
        """Handle Delete Line button using SL No selection (Sales Entry pattern)."""
        target_row = getattr(self, 'manually_selected_row', -1)
        if target_row < 0:
            QMessageBox.information(
                self,
                'Delete Line',
                'Please click the SL No of the line you want to delete, then press Delete Line.',
            )
            return
        if target_row >= self.lines_table.rowCount():
            self.manually_selected_row = -1
            return
        reply = QMessageBox.question(
            self,
            'Delete Line',
            f'Are you sure you want to delete line {target_row + 1}?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.lines_table.removeRow(target_row)
        self.manually_selected_row = -1
        self.lines_table.clearSelection()
        self.lines_table.viewport().update()
        self._refresh_line_sl_numbers()
        self._update_totals()

    def _on_line_changed(self, item):
        """Handle line item change."""
        self._update_totals()

    def _update_totals(self):
        """Update total debit/credit labels."""
        total_debit = MONEY_ZERO
        total_credit = MONEY_ZERO
        for row in range(self.lines_table.rowCount()):
            debit_edit = self.lines_table.cellWidget(row, 2)
            credit_edit = self.lines_table.cellWidget(row, 3)
            if debit_edit:
                total_debit += to_decimal(debit_edit.text())
            if credit_edit:
                total_credit += to_decimal(credit_edit.text())
        difference = total_debit - total_credit
        self.lbl_total_debit.setText(f'Total Debit: {format_currency(total_debit)}')
        self.lbl_total_credit.setText(f'Total Credit: {format_currency(total_credit)}')
        self.lbl_difference.setText(f'Difference: {format_currency(abs(difference))}')
        if total_debit != total_credit:
            self.lbl_difference.setStyleSheet('\n                QLabel {\n                    color: #ffffff;\n                    font-size: 12px;\n                    padding: 5px;\n                    background-color: #a80000;\n                    border-radius: 4px;\n                }\n            ')
        else:
            self.lbl_difference.setStyleSheet('\n                QLabel {\n                    color: #ffffff;\n                    font-size: 12px;\n                    padding: 5px;\n                    background-color: #107c10;\n                    border-radius: 4px;\n                }\n            ')

    def _get_lines(self) -> list:
        """Get lines from table."""
        lines = []
        for row in range(self.lines_table.rowCount()):
            account_combo = self.lines_table.cellWidget(row, 1)
            debit_edit = self.lines_table.cellWidget(row, 2)
            credit_edit = self.lines_table.cellWidget(row, 3)
            narration_edit = self.lines_table.cellWidget(row, 4)
            account_id = account_combo.get_account_id() if account_combo else None
            debit = MONEY_ZERO
            credit = MONEY_ZERO
            if debit_edit:
                debit = to_decimal(debit_edit.text())
            if credit_edit:
                credit = to_decimal(credit_edit.text())
            narration = narration_edit.text() if narration_edit else ''
            if account_id and (debit > MONEY_ZERO or credit > MONEY_ZERO):
                lines.append({'account_id': account_id, 'debit': float(debit), 'credit': float(credit), 'narration': narration, 'sl_no': row + 1})
        return lines

    def _on_save(self):
        """Handle Save button."""
        if not self.company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        lines = self._get_lines()
        if not lines:
            QMessageBox.warning(self, 'Validation', 'Please add at least one line with account and amount.')
            return
        total_debit = sum((to_decimal(l['debit']) for l in lines), MONEY_ZERO)
        total_credit = sum((to_decimal(l['credit']) for l in lines), MONEY_ZERO)
        if total_debit != total_credit:
            QMessageBox.warning(self, 'Validation', 'Debit and Credit must be equal.')
            return
        voucher_no = self.txt_voucher_no.text()
        voucher_date = qdate_to_db(self.date_voucher.date())
        remark = self.txt_remark.text()
        narration = ''
        result = self.logic.save_journal_entry(company_id=self.company_id, voucher_no=voucher_no, voucher_date=voucher_date, lines=lines, remark=remark, narration=narration)
        if result['success']:
            self.current_voucher_id = result['data']['id']
            self.txt_voucher_no.setText(result['data'].get('voucher_no', voucher_no))
            QMessageBox.information(self, 'Success', result['message'])
            self._load_history()
            self._on_new()
        else:
            QMessageBox.critical(self, 'Error', result['message'])

    def _on_update(self):
        """Handle Update button."""
        if not self.current_voucher_id:
            QMessageBox.warning(self, 'No Voucher', 'No voucher selected for update.')
            return
        if not self.company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        lines = self._get_lines()
        if not lines:
            QMessageBox.warning(self, 'Validation', 'Please add at least one line with account and amount.')
            return
        total_debit = sum((to_decimal(l['debit']) for l in lines), MONEY_ZERO)
        total_credit = sum((to_decimal(l['credit']) for l in lines), MONEY_ZERO)
        if total_debit != total_credit:
            QMessageBox.warning(self, 'Validation', 'Debit and Credit must be equal.')
            return
        voucher_no = self.txt_voucher_no.text()
        voucher_date = qdate_to_db(self.date_voucher.date())
        remark = self.txt_remark.text()
        narration = ''
        result = self.logic.update_journal_entry(journal_id=self.current_voucher_id, company_id=self.company_id, voucher_no=voucher_no, voucher_date=voucher_date, lines=lines, remark=remark, narration=narration)
        if result['success']:
            self.txt_voucher_no.setText(result['data'].get('voucher_no', voucher_no))
            QMessageBox.information(self, 'Success', result['message'])
            self._load_history()
        else:
            QMessageBox.critical(self, 'Error', result['message'])

    def _on_delete(self):
        """Handle Delete button."""
        if not self.current_voucher_id:
            QMessageBox.warning(self, 'No Voucher', 'No voucher selected for delete.')
            return
        reply = QMessageBox.question(self, 'Confirm Delete', 'Are you sure you want to delete this voucher?', QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            result = self.logic.delete_journal_entry(self.current_voucher_id, self.company_id)
            if result['success']:
                QMessageBox.information(self, 'Success', result['message'])
                self._load_history()
                self._on_new()
            else:
                QMessageBox.critical(self, 'Error', result['message'])

    def _on_clear(self):
        """Handle Clear button."""
        self._clear_form()
        self.current_voucher_id = None
        self.btn_save.setVisible(True)
        self.btn_update.setVisible(False)

    def _on_history_selection(self):
        """Handle history table selection."""
        selected_items = self.history_table.selectedItems()
        if not selected_items:
            return
        row = self.history_table.currentRow()
        voucher_id = self.history_table.item(row, 0).data(Qt.UserRole)
        if voucher_id:
            self._load_voucher(voucher_id)

    def _load_voucher(self, voucher_id: int):
        """Load voucher data into form."""
        voucher = self.logic.get_journal_voucher_by_id(voucher_id)
        if not voucher:
            return
        self.txt_voucher_no.setText(voucher.get('voucher_no', ''))
        self.date_voucher.setDate(QDate.fromString(voucher.get('voucher_date', ''), Qt.ISODate))
        self.txt_remark.setText(voucher.get('remark', ''))
        self.lines_table.setRowCount(0)
        lines = self.logic.get_journal_lines(voucher_id)
        for line in lines:
            self._add_line(account_id=line.get('account_id'), debit=line.get('debit', 0.0), credit=line.get('credit', 0.0), narration=line.get('narration', ''))
        self.btn_save.setVisible(False)
        self.btn_update.setVisible(True)

    def _clear_form(self):
        """Clear form fields."""
        self.txt_voucher_no.clear()
        self.date_voucher.setDate(QDate.currentDate())
        self.txt_remark.clear()
        self.manually_selected_row = -1
        self.lines_table.setRowCount(0)
        self._update_totals()

    def load_journal_for_edit(self, voucher_id: int):
        """Load journal entry for editing from Journal Book double-click."""
        print(f'[DEBUG] Loading journal entry for edit: ID={voucher_id}')
        if not self.company_id:
            from config import active_company_manager
            self.company_id = active_company_manager.get_active_company_id()
        if self.company_id:
            self._load_voucher(voucher_id)

    def eventFilter(self, obj, event):
        """Handle SL No row selection, one-click cell editing, and Enter/Esc navigation."""
        if obj == self.lines_table.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                item = self.lines_table.itemAt(event.pos())
                if item is not None and item.column() == 0:
                    self.manually_selected_row = item.row()
                    self.lines_table.clearSelection()
                    self.lines_table.viewport().update()
                    return True
                index = self.lines_table.indexAt(event.pos())
                if index.isValid():
                    clicked_row = index.row()
                    clicked_column = index.column()
                    if clicked_column == 0:
                        self.manually_selected_row = clicked_row
                        self.lines_table.clearSelection()
                        self.lines_table.viewport().update()
                        return True
                    self.manually_selected_row = -1
                    self.lines_table.clearSelection()
                    self.lines_table.viewport().update()
                    self._focus_line_widget(clicked_row, clicked_column)
                    return True
        if event.type() == QKeyEvent.KeyPress:
            if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                if obj in [self.lines_table.cellWidget(row, col) for row in range(self.lines_table.rowCount()) for col in range(1, 5)]:
                    current_row = self.lines_table.currentRow()
                    current_col = -1
                    for col in range(1, 5):
                        if self.lines_table.cellWidget(current_row, col) == obj:
                            current_col = col
                            break
                    if current_col == 1:
                        next_widget = self.lines_table.cellWidget(current_row, 2)
                        if next_widget:
                            next_widget.setFocus()
                            if hasattr(next_widget, 'selectAll'):
                                next_widget.selectAll()
                    elif current_col == 2:
                        next_widget = self.lines_table.cellWidget(current_row, 3)
                        if next_widget:
                            next_widget.setFocus()
                            next_widget.selectAll()
                    elif current_col == 3:
                        next_widget = self.lines_table.cellWidget(current_row, 4)
                        if next_widget:
                            next_widget.setFocus()
                            next_widget.selectAll()
                    elif current_col == 4:
                        if current_row < self.lines_table.rowCount() - 1:
                            next_widget = self.lines_table.cellWidget(current_row + 1, 1)
                            if next_widget:
                                next_widget.setFocus()
                                line_edit = next_widget.lineEdit() if hasattr(next_widget, 'lineEdit') else None
                                if line_edit is not None:
                                    line_edit.selectAll()
                        else:
                            self._add_line()
                            next_widget = self.lines_table.cellWidget(self.lines_table.rowCount() - 1, 1)
                            if next_widget:
                                next_widget.setFocus()
                                line_edit = next_widget.lineEdit() if hasattr(next_widget, 'lineEdit') else None
                                if line_edit is not None:
                                    line_edit.selectAll()
                    return True
            elif event.key() == Qt.Key_Escape:
                if obj in [self.lines_table.cellWidget(row, col) for row in range(self.lines_table.rowCount()) for col in range(1, 5)]:
                    current_row = self.lines_table.currentRow()
                    current_col = -1
                    for col in range(1, 5):
                        if self.lines_table.cellWidget(current_row, col) == obj:
                            current_col = col
                            break
                    if current_col == 4:
                        next_widget = self.lines_table.cellWidget(current_row, 3)
                        if next_widget:
                            next_widget.setFocus()
                    elif current_col == 3:
                        next_widget = self.lines_table.cellWidget(current_row, 2)
                        if next_widget:
                            next_widget.setFocus()
                    elif current_col == 2:
                        next_widget = self.lines_table.cellWidget(current_row, 1)
                        if next_widget:
                            next_widget.setFocus()
                    return True
        return super().eventFilter(obj, event)

    def refresh(self):
        """Refresh page."""
        self._load_company()