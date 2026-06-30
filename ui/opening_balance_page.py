"""
Opening Balance Page UI.
Provides a unified entry interface for Opening Ledger Balances and Opening Stock.
"""
from decimal import Decimal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFrame, QStyledItemDelegate, QCompleter, QCheckBox, QAbstractItemView
from PySide6.QtCore import Qt, QDate, QStringListModel, QEvent, QTimer, QCoreApplication
from PySide6.QtGui import QColor, QPen
from bizora_core.opening_balance_logic import OpeningBalanceLogic
from bizora_core.common_finance import format_money, to_decimal
from ui import theme
from ui.book_report_common import page_background_style, section_heading_style
from ui.checkbox_style import create_checkbox
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
L_COL_SL = 0
L_COL_LEDGER = 1
L_COL_DR_CR = 2
L_COL_AMOUNT = 3
L_COL_NARR = 4
S_COL_SL = 0
S_COL_BARCODE = 1
S_COL_PRODUCT = 2
S_COL_QTY = 3
S_COL_RATE = 4
S_COL_VALUE = 5

class OpeningLedgerDelegate(QStyledItemDelegate):

    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget

    def paint(self, painter, option, index):
        is_selected = hasattr(self.parent_widget, 'ledger_selected_row') and self.parent_widget.ledger_selected_row == index.row()
        if is_selected:
            option.backgroundBrush = Qt.NoBrush
            super().paint(painter, option, index)
            table = self.parent_widget.ledger_table
            row_rect = table.visualRect(table.model().index(index.row(), 0))
            last_rect = table.visualRect(table.model().index(index.row(), table.columnCount() - 1))
            row_rect.setWidth(last_rect.right() - row_rect.left())
            row_rect.setHeight(last_rect.bottom() - row_rect.top())
            pen = QPen(QColor('#3b82f6'))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(row_rect)
        else:
            super().paint(painter, option, index)

    def createEditor(self, parent, option, index):
        col = index.column()
        editor = QLineEdit(parent)
        theme.prepare_billing_cell_editor(editor)
        table = self.parent_widget.ledger_table
        item = table.item(index.row(), col)
        if item:
            editor.setText(item.text())
        if col == L_COL_LEDGER:
            completer = QCompleter(self.parent_widget.account_names, editor)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            theme.wire_line_edit_completer(editor, completer)
        elif col == L_COL_DR_CR:
            completer = QCompleter(['Dr', 'Cr'], editor)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            theme.wire_line_edit_completer(editor, completer)
        editor.installEventFilter(self)
        QTimer.singleShot(0, editor.selectAll)
        return editor

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def setEditorData(self, editor, index):
        item = self.parent_widget.ledger_table.item(index.row(), index.column())
        if item and (not editor.text()):
            editor.setText(item.text())

    def setModelData(self, editor, model, index):
        text = editor.text().strip()
        if index.column() == L_COL_DR_CR:
            text = 'Dr' if text.lower().startswith('d') else 'Cr'
        was_blocked = self.parent_widget.ledger_table.blockSignals(True)
        model.setData(index, text, Qt.EditRole)
        self.parent_widget.ledger_table.blockSignals(was_blocked)
        if index.column() == L_COL_LEDGER and text:
            row = index.row()
            acc = self.parent_widget.accounts_dict.get(text)
            if acc:
                dr_cr = 'Cr'
                grp = (acc.get('group_name') or '').lower()
                if 'asset' in grp or 'debtor' in grp or 'cash' in grp or ('bank' in grp):
                    dr_cr = 'Dr'
                it = self.parent_widget.ledger_table.item(row, L_COL_DR_CR)
                if it and (not it.text()):
                    it.setText(dr_cr)
        self.parent_widget.calculate_totals()

    def _move_to_cell(self, table, row, col):
        """Safely move to cell and open editor (Sales Entry pattern)."""
        if row < 0 or row >= table.rowCount() or col < 0 or (col >= table.columnCount()):
            return
        table.setCurrentCell(row, col)
        idx = table.model().index(row, col)
        if idx.isValid():
            table.edit(idx)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            table = self.parent_widget.ledger_table
            if key in (Qt.Key_Return, Qt.Key_Enter):
                table.commitData(editor)
                table.closeEditor(editor, QStyledItemDelegate.NoHint)
                r = table.currentRow()
                c = table.currentColumn()
                if c < L_COL_NARR:
                    QTimer.singleShot(0, lambda: self._move_to_cell(table, r, c + 1))
                elif r < table.rowCount() - 1:
                    QTimer.singleShot(0, lambda: self._move_to_cell(table, r + 1, L_COL_LEDGER))
                return True
            elif key == Qt.Key_Escape:
                table.commitData(editor)
                table.closeEditor(editor, QStyledItemDelegate.NoHint)
                r = table.currentRow()
                c = table.currentColumn()
                if c > L_COL_LEDGER:
                    QTimer.singleShot(0, lambda: self._move_to_cell(table, r, c - 1))
                elif r > 0:
                    QTimer.singleShot(0, lambda: self._move_to_cell(table, r - 1, L_COL_NARR))
                return True
            elif key == Qt.Key_Tab:
                return True
        return super().eventFilter(editor, event)

class OpeningStockDelegate(QStyledItemDelegate):

    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget

    def paint(self, painter, option, index):
        is_selected = hasattr(self.parent_widget, 'stock_selected_row') and self.parent_widget.stock_selected_row == index.row()
        if is_selected:
            option.backgroundBrush = Qt.NoBrush
            super().paint(painter, option, index)
            table = self.parent_widget.stock_table
            row_rect = table.visualRect(table.model().index(index.row(), 0))
            last_rect = table.visualRect(table.model().index(index.row(), table.columnCount() - 1))
            row_rect.setWidth(last_rect.right() - row_rect.left())
            row_rect.setHeight(last_rect.bottom() - row_rect.top())
            pen = QPen(QColor('#3b82f6'))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(row_rect)
        else:
            super().paint(painter, option, index)

    def createEditor(self, parent, option, index):
        col = index.column()
        editor = QLineEdit(parent)
        theme.prepare_billing_cell_editor(editor)
        table = self.parent_widget.stock_table
        item = table.item(index.row(), col)
        if item:
            editor.setText(item.text())
        if col == S_COL_PRODUCT:
            completer = QCompleter(self.parent_widget.product_names, editor)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchStartsWith)
            theme.wire_line_edit_completer(editor, completer)
        elif col in [S_COL_QTY, S_COL_RATE]:
            editor.textEdited.connect(lambda txt, r=index.row(), c=col: self._live_calc(r, txt, c))
        editor.installEventFilter(self)
        QTimer.singleShot(0, editor.selectAll)
        return editor

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def _live_calc(self, row, text, col):
        qty = to_decimal(text) if col == S_COL_QTY else self.parent_widget.safe_dec_stock(row, S_COL_QTY)
        rate = to_decimal(text) if col == S_COL_RATE else self.parent_widget.safe_dec_stock(row, S_COL_RATE)
        val = qty * rate
        it = self.parent_widget.stock_table.item(row, S_COL_VALUE)
        if it:
            was = self.parent_widget.stock_table.blockSignals(True)
            it.setText(str(val.quantize(Decimal('0.01'))))
            self.parent_widget.stock_table.blockSignals(was)
            self.parent_widget.calculate_totals()

    def setEditorData(self, editor, index):
        item = self.parent_widget.stock_table.item(index.row(), index.column())
        if item and (not editor.text()):
            editor.setText(item.text())

    def setModelData(self, editor, model, index):
        text = editor.text().strip()
        was_blocked = self.parent_widget.stock_table.blockSignals(True)
        model.setData(index, text, Qt.EditRole)
        self.parent_widget.stock_table.blockSignals(was_blocked)
        row = index.row()
        col = index.column()
        if col == S_COL_BARCODE and text:
            prod = self.parent_widget.barcode_dict.get(text)
            if prod:
                pname = prod.get('name', '')
                prate = prod.get('sale_price', 0)
                prod_it = self.parent_widget.stock_table.item(row, S_COL_PRODUCT)
                if prod_it:
                    prod_it.setText(pname)
                rate_it = self.parent_widget.stock_table.item(row, S_COL_RATE)
                if rate_it:
                    rate_it.setText(str(prate))
            else:
                for clr_col in (S_COL_PRODUCT, S_COL_QTY, S_COL_RATE, S_COL_VALUE):
                    clr_it = self.parent_widget.stock_table.item(row, clr_col)
                    if clr_it:
                        clr_it.setText('')
                bar_it = self.parent_widget.stock_table.item(row, S_COL_BARCODE)
                if bar_it:
                    bar_it.setText('')
                QMessageBox.warning(self.parent_widget, 'Barcode Not Found', f'No product found for barcode: {text}')
        elif col == S_COL_PRODUCT and text:
            prod = self.parent_widget.products_dict.get(text)
            if prod:
                rate_it = self.parent_widget.stock_table.item(row, S_COL_RATE)
                if rate_it and (not rate_it.text()):
                    rate_it.setText(str(prod.get('sale_price', 0)))
                bar_it = self.parent_widget.stock_table.item(row, S_COL_BARCODE)
                if bar_it and (not bar_it.text()):
                    bar_it.setText(str(prod.get('barcode', '')))
        self._live_calc(row, text, col)
        self.parent_widget.calculate_totals()

    def _move_to_cell(self, table, row, col):
        """Safely move to cell and open editor (Sales Entry pattern)."""
        if row < 0 or row >= table.rowCount() or col < 0 or (col >= table.columnCount()):
            return
        table.setCurrentCell(row, col)
        idx = table.model().index(row, col)
        if idx.isValid():
            table.edit(idx)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            table = self.parent_widget.stock_table
            if key in (Qt.Key_Return, Qt.Key_Enter):
                table.commitData(editor)
                table.closeEditor(editor, QStyledItemDelegate.NoHint)
                r = table.currentRow()
                c = table.currentColumn()
                if c == S_COL_BARCODE:
                    prod_it = table.item(r, S_COL_PRODUCT)
                    if prod_it and prod_it.text().strip():
                        QTimer.singleShot(0, lambda: self._move_to_cell(table, r, S_COL_QTY))
                    else:
                        QTimer.singleShot(0, lambda: self._move_to_cell(table, r, S_COL_PRODUCT))
                elif c < S_COL_RATE:
                    QTimer.singleShot(0, lambda: self._move_to_cell(table, r, c + 1))
                elif r < table.rowCount() - 1:
                    QTimer.singleShot(0, lambda: self._move_to_cell(table, r + 1, S_COL_BARCODE))
                return True
            elif key == Qt.Key_Escape:
                table.commitData(editor)
                table.closeEditor(editor, QStyledItemDelegate.NoHint)
                r = table.currentRow()
                c = table.currentColumn()
                if c > S_COL_BARCODE:
                    QTimer.singleShot(0, lambda: self._move_to_cell(table, r, c - 1))
                elif r > 0:
                    QTimer.singleShot(0, lambda: self._move_to_cell(table, r - 1, S_COL_RATE))
                return True
            elif key == Qt.Key_Tab:
                return True
        return super().eventFilter(editor, event)

class OpeningBalanceWidget(UiMemoryMixin, QWidget):

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.logic = OpeningBalanceLogic(db)
        self.company_id = None
        self.accounts_dict = {}
        self.account_names = []
        self.products_dict = {}
        self.product_names = []
        self.barcode_dict = {}
        self.accounts_by_id = {}
        self.products_by_id = {}
        self.ledger_selected_row = -1
        self.stock_selected_row = -1
        self._initial_load_done = False
        self._deferred_load_started = False
        self.init_ui()
        self._init_ui_memory()
        QTimer.singleShot(0, self._start_deferred_load)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.setStyleSheet(page_background_style())
        top_bar = QHBoxLayout()
        lbl_date = QLabel('Date:')
        lbl_date.setStyleSheet(theme.sales_micro_label_style())
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setStyleSheet(theme.sales_compact_input_style())
        theme.apply_date_edit_calendar_theme(self.date_edit)
        lbl_narr = QLabel('Global Narration:')
        lbl_narr.setStyleSheet(theme.sales_micro_label_style())
        self.narr_edit = QLineEdit()
        self.narr_edit.setStyleSheet(theme.sales_compact_input_style())
        self.btn_save = QPushButton('Save Opening Balance')
        self.btn_save.setStyleSheet(theme.sales_compact_button_style())
        self.btn_save.clicked.connect(self.save_voucher)
        top_bar.addWidget(lbl_date)
        top_bar.addWidget(self.date_edit)
        top_bar.addWidget(lbl_narr)
        top_bar.addWidget(self.narr_edit)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_save)
        layout.addLayout(top_bar)
        tables_layout = QHBoxLayout()
        ledger_vbox = QVBoxLayout()
        lbl_ledger = QLabel('1. Opening Ledger Balances')
        lbl_ledger.setStyleSheet(section_heading_style(13))
        ledger_vbox.addWidget(lbl_ledger)
        self.ledger_table = QTableWidget(50, 5)
        self.ledger_table.setHorizontalHeaderLabels(['SL', 'Ledger Name', 'Dr/Cr', 'Amount', 'Narration'])
        self.ledger_table.setStyleSheet(self._billing_table_style())
        self.ledger_table.verticalHeader().setVisible(False)
        self.ledger_table.setAlternatingRowColors(True)
        self.ledger_table.verticalHeader().setDefaultSectionSize(25)
        self.ledger_table.verticalHeader().setMinimumSectionSize(20)
        self.ledger_table.setSelectionMode(QTableWidget.SingleSelection)
        self.ledger_table.setSelectionBehavior(QTableWidget.SelectItems)
        self.ledger_table.setEditTriggers(QAbstractItemView.CurrentChanged | QAbstractItemView.DoubleClicked | QAbstractItemView.AnyKeyPressed)
        self.ledger_table.setItemDelegate(OpeningLedgerDelegate(self))
        header = self.ledger_table.horizontalHeader()
        header.setSectionResizeMode(L_COL_LEDGER, QHeaderView.Stretch)
        self.ledger_table.setColumnWidth(L_COL_SL, 40)
        self.ledger_table.setColumnWidth(L_COL_DR_CR, 50)
        self.ledger_table.setColumnWidth(L_COL_AMOUNT, 100)
        self.ledger_table.setColumnWidth(L_COL_NARR, 150)
        self.ledger_table.currentCellChanged.connect(self.on_ledger_cell_changed)
        self.ledger_table.cellChanged.connect(lambda r, c: self.calculate_totals())
        ledger_vbox.addWidget(self.ledger_table)
        tables_layout.addLayout(ledger_vbox, 1)
        stock_vbox = QVBoxLayout()
        lbl_stock = QLabel('2. Opening Stock')
        lbl_stock.setStyleSheet(section_heading_style(13))
        stock_vbox.addWidget(lbl_stock)
        self.stock_table = QTableWidget(50, 6)
        self.stock_table.setHorizontalHeaderLabels(['SL', 'Barcode', 'Product', 'Qty', 'Rate', 'Value'])
        self.stock_table.setStyleSheet(self._billing_table_style())
        self.stock_table.verticalHeader().setVisible(False)
        self.stock_table.setAlternatingRowColors(True)
        self.stock_table.verticalHeader().setDefaultSectionSize(25)
        self.stock_table.verticalHeader().setMinimumSectionSize(20)
        self.stock_table.setSelectionMode(QTableWidget.SingleSelection)
        self.stock_table.setSelectionBehavior(QTableWidget.SelectItems)
        self.stock_table.setEditTriggers(QAbstractItemView.CurrentChanged | QAbstractItemView.DoubleClicked | QAbstractItemView.AnyKeyPressed)
        self.stock_table.setItemDelegate(OpeningStockDelegate(self))
        header = self.stock_table.horizontalHeader()
        header.setSectionResizeMode(S_COL_PRODUCT, QHeaderView.Stretch)
        self.stock_table.setColumnWidth(S_COL_SL, 40)
        self.stock_table.setColumnWidth(S_COL_BARCODE, 100)
        self.stock_table.setColumnWidth(S_COL_QTY, 60)
        self.stock_table.setColumnWidth(S_COL_RATE, 80)
        self.stock_table.setColumnWidth(S_COL_VALUE, 90)
        self.stock_table.currentCellChanged.connect(self.on_stock_cell_changed)
        self.stock_table.cellChanged.connect(lambda r, c: self.calculate_totals())
        stock_vbox.addWidget(self.stock_table)
        tables_layout.addLayout(stock_vbox, 1)
        layout.addLayout(tables_layout)
        footer = QHBoxLayout()
        self.lbl_t_debit = QLabel('Total Debit: 0.00')
        self.lbl_t_credit = QLabel('Total Credit: 0.00')
        self.lbl_t_stock = QLabel('Stock Value: 0.00')
        self.lbl_diff = QLabel('Difference: 0.00')
        colors = theme._theme_colors()
        lbl_style = f"color: {colors['input_text']}; font-weight: bold; font-size: 13px; padding: 6px 12px; background: {colors['panel_bg']}; border: 1px solid {colors['border']}; border-radius: 6px;"
        for lbl in (self.lbl_t_debit, self.lbl_t_credit, self.lbl_t_stock, self.lbl_diff):
            lbl.setStyleSheet(lbl_style)
            footer.addWidget(lbl)
        self.temp_diff_tick = create_checkbox('Allow Temporary Difference', label_color='#f97316', font_size=11)
        self.temp_diff_tick.setVisible(False)
        self.temp_diff_tick.stateChanged.connect(lambda _: self.calculate_totals())
        footer.addWidget(self.temp_diff_tick)
        footer.addStretch()
        layout.addLayout(footer)
        self.init_table_items()

    def focus_stock_section(self) -> None:
        """Move keyboard focus to the opening stock grid."""
        self.stock_table.setFocus()
        if self.stock_table.rowCount() > 0:
            self.stock_table.setCurrentCell(0, S_COL_PRODUCT)

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        colors = theme._theme_colors()
        self.setStyleSheet(page_background_style())
        lbl_style = (
            f"color: {colors['input_text']}; font-weight: bold; font-size: 13px; "
            f"padding: 6px 12px; background: {colors['panel_bg']}; "
            f"border: 1px solid {colors['border']}; border-radius: 6px;"
        )
        for lbl in (self.lbl_t_debit, self.lbl_t_credit, self.lbl_t_stock, self.lbl_diff):
            lbl.setStyleSheet(lbl_style)
        for widget, style_fn in (
            (self.date_edit, theme.sales_compact_input_style),
            (self.narr_edit, theme.sales_compact_input_style),
            (self.btn_save, theme.sales_compact_button_style),
        ):
            widget.setStyleSheet(style_fn())
        table_style = self._billing_table_style()
        self.ledger_table.setStyleSheet(table_style)
        self.stock_table.setStyleSheet(table_style)

    def _yield_ui_events(self) -> None:
        """Keep Windows responsive while preparing large opening-balance grids."""
        QCoreApplication.processEvents()

    def _start_deferred_load(self) -> None:
        """Load accounts/products after the page frame is visible."""
        if self._initial_load_done or self._deferred_load_started:
            return
        self._deferred_load_started = True
        QTimer.singleShot(50, self._perform_deferred_load)

    def _perform_deferred_load(self) -> None:
        """Fetch master data and any saved opening balance voucher."""
        try:
            self._yield_ui_events()
            self.load_data()
            self._initial_load_done = True
        finally:
            self._deferred_load_started = False

    def init_table_items(self):
        self.ledger_table.setUpdatesEnabled(False)
        self.stock_table.setUpdatesEnabled(False)
        try:
            for r in range(50):
                for c in range(5):
                    it = QTableWidgetItem('' if c != L_COL_SL else str(r + 1))
                    if c == L_COL_SL:
                        it.setFlags(Qt.ItemIsEnabled)
                    self.ledger_table.setItem(r, c, it)
                if r % 10 == 9:
                    self._yield_ui_events()
            for r in range(50):
                for c in range(6):
                    if c == S_COL_SL:
                        it = QTableWidgetItem(str(r + 1))
                        it.setFlags(Qt.ItemIsEnabled)
                    elif c == S_COL_VALUE:
                        it = QTableWidgetItem('')
                        it.setFlags(Qt.ItemIsEnabled)
                    else:
                        it = QTableWidgetItem('')
                    self.stock_table.setItem(r, c, it)
                if r % 10 == 9:
                    self._yield_ui_events()
        finally:
            self.ledger_table.setUpdatesEnabled(True)
            self.stock_table.setUpdatesEnabled(True)

    def _billing_table_style(self):
        """Editable grid style with in-cell edit highlight."""
        return theme.editable_table_style()

    @staticmethod
    def _table_cell_editor_style() -> str:
        return theme.billing_cell_editor_inline_style()

    def _ph(self):
        """Centralized placeholder for MySQL migration safety."""
        return self.db._get_placeholder() if hasattr(self.db, '_get_placeholder') else '?'

    def load_data(self):
        from config import active_company_manager
        self.company_id = active_company_manager.get_active_company_id()
        if not self.company_id:
            return
        ph = self._ph()
        accounts = self.db.execute_query(
            f"""
            SELECT id, account_name, group_name
            FROM ledger_accounts
            WHERE company_id = {ph}
              AND COALESCE(is_active, 1) = 1
            ORDER BY account_name
            """,
            (self.company_id,),
        ) or []
        self.accounts_by_id = {}
        self.accounts_dict = {}
        for row in accounts:
            record = dict(row)
            account_id = record.get('id')
            account_name = str(record.get('account_name') or '').strip()
            if not account_id or not account_name:
                continue
            self.accounts_by_id[int(account_id)] = record
            self.accounts_dict[account_name] = record
        self.account_names = list(self.accounts_dict.keys())

        self._yield_ui_events()
        products = self.db.execute_query(
            f"""
            SELECT id, name, barcode, sale_price
            FROM products
            WHERE company_id = {ph}
            ORDER BY name
            """,
            (self.company_id,),
        ) or []
        self.products_by_id = {}
        self.products_dict = {}
        self.barcode_dict = {}
        for row in products:
            record = dict(row)
            product_id = record.get('id')
            product_name = str(record.get('name') or '').strip()
            if not product_id or not product_name:
                continue
            self.products_by_id[int(product_id)] = record
            self.products_dict[product_name] = record
            barcode = str(record.get('barcode') or '').strip()
            if barcode:
                self.barcode_dict[barcode] = record
        self.product_names = list(self.products_dict.keys())
        self._yield_ui_events()
        self.load_existing()

    def load_existing(self):
        res = self.logic.get_opening_balance(self.company_id)
        if not res['success'] or not res['header']:
            return
        header = res['header']
        self.ledger_table.blockSignals(True)
        self.stock_table.blockSignals(True)
        try:
            self.date_edit.setDate(QDate.fromString(str(header['voucher_date'])[:10], Qt.ISODate))
            self.narr_edit.setText(header['narration'] or '')
            for r, item in enumerate(res['ledger_items']):
                if r >= 50:
                    break
                account = self.accounts_by_id.get(int(item.get('account_id') or 0))
                acc_name = str(account.get('account_name') or '') if account else ''
                self.ledger_table.item(r, L_COL_LEDGER).setText(acc_name)
                dr = to_decimal(item['debit'])
                cr = to_decimal(item['credit'])
                if dr > 0:
                    self.ledger_table.item(r, L_COL_DR_CR).setText('Dr')
                    self.ledger_table.item(r, L_COL_AMOUNT).setText(str(dr))
                else:
                    self.ledger_table.item(r, L_COL_DR_CR).setText('Cr')
                    self.ledger_table.item(r, L_COL_AMOUNT).setText(str(cr))
                self.ledger_table.item(r, L_COL_NARR).setText(item['narration'] or '')
            for r, item in enumerate(res['stock_items']):
                if r >= 50:
                    break
                product = self.products_by_id.get(int(item.get('product_id') or 0))
                if product:
                    self.stock_table.item(r, S_COL_PRODUCT).setText(str(product.get('name') or ''))
                    self.stock_table.item(r, S_COL_BARCODE).setText(str(product.get('barcode') or ''))
                self.stock_table.item(r, S_COL_QTY).setText(str(item['qty']))
                self.stock_table.item(r, S_COL_RATE).setText(str(item['rate']))
                self.stock_table.item(r, S_COL_VALUE).setText(str(item['value']))
        finally:
            self.ledger_table.blockSignals(False)
            self.stock_table.blockSignals(False)
        self.calculate_totals()

    def on_ledger_cell_changed(self, current_row, current_col, prev_row, prev_col):
        if self.ledger_selected_row != current_row:
            self.ledger_selected_row = current_row
            self.ledger_table.viewport().update()

    def on_stock_cell_changed(self, current_row, current_col, prev_row, prev_col):
        if self.stock_selected_row != current_row:
            self.stock_selected_row = current_row
            self.stock_table.viewport().update()

    def safe_dec_ledger(self, row, col):
        it = self.ledger_table.item(row, col)
        return to_decimal(it.text() if it else 0)

    def safe_dec_stock(self, row, col):
        it = self.stock_table.item(row, col)
        return to_decimal(it.text() if it else 0)

    def calculate_totals(self):
        t_debit = Decimal('0.0')
        t_credit = Decimal('0.0')
        t_stock = Decimal('0.0')
        for r in range(self.ledger_table.rowCount()):
            it_name = self.ledger_table.item(r, L_COL_LEDGER)
            if not it_name or not it_name.text().strip():
                continue
            drcr = (self.ledger_table.item(r, L_COL_DR_CR).text() or '').strip().lower()
            amt = self.safe_dec_ledger(r, L_COL_AMOUNT)
            if drcr == 'dr':
                t_debit += amt
            elif drcr == 'cr':
                t_credit += amt
        for r in range(self.stock_table.rowCount()):
            it_name = self.stock_table.item(r, S_COL_PRODUCT)
            if not it_name or not it_name.text().strip():
                continue
            val = self.safe_dec_stock(r, S_COL_VALUE)
            t_stock += val
        diff = t_debit + t_stock - t_credit
        self.lbl_t_debit.setText(f'Total Debit: {format_money(t_debit)}')
        self.lbl_t_credit.setText(f'Total Credit: {format_money(t_credit)}')
        self.lbl_t_stock.setText(f'Stock Value: {format_money(t_stock)}')
        self.lbl_diff.setText(f'Difference: {format_money(diff)}')
        balanced = diff == Decimal('0.0')
        if balanced:
            self.lbl_diff.setStyleSheet(f'color: white; font-size: 14px; font-weight: bold; padding: 5px; background: {theme.semantic_positive_hex()}; border-radius: 4px;')
            self.btn_save.setEnabled(True)
            self.temp_diff_tick.setVisible(False)
        else:
            self.lbl_diff.setStyleSheet(f'color: white; font-size: 14px; font-weight: bold; padding: 5px; background: {theme.semantic_negative_hex()}; border-radius: 4px;')
            self.temp_diff_tick.setVisible(True)
            if self.temp_diff_tick.isChecked():
                self.btn_save.setEnabled(True)
            else:
                self.btn_save.setEnabled(False)

    def save_voucher(self):
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No active company.')
            return
        ledger_items = []
        for r in range(self.ledger_table.rowCount()):
            name = self.ledger_table.item(r, L_COL_LEDGER).text().strip()
            if not name:
                continue
            acc = self.accounts_dict.get(name)
            if not acc:
                QMessageBox.warning(self, 'Error', f'Invalid Ledger at Row {r + 1}: {name}')
                return
            drcr = self.ledger_table.item(r, L_COL_DR_CR).text().strip().lower()
            amt = self.safe_dec_ledger(r, L_COL_AMOUNT)
            narr = self.ledger_table.item(r, L_COL_NARR).text().strip()
            ledger_items.append({'account_id': acc['id'], 'debit': amt if drcr == 'dr' else Decimal('0.0'), 'credit': amt if drcr == 'cr' else Decimal('0.0'), 'narration': narr})
        stock_items = []
        for r in range(self.stock_table.rowCount()):
            name = self.stock_table.item(r, S_COL_PRODUCT).text().strip()
            if not name:
                continue
            prod = self.products_dict.get(name)
            if not prod:
                QMessageBox.warning(self, 'Error', f'Invalid Product at Row {r + 1}: {name}')
                return
            qty = self.safe_dec_stock(r, S_COL_QTY)
            rate = self.safe_dec_stock(r, S_COL_RATE)
            val = self.safe_dec_stock(r, S_COL_VALUE)
            stock_items.append({'product_id': prod['id'], 'qty': qty, 'rate': rate, 'value': val})
        if not ledger_items and (not stock_items):
            QMessageBox.warning(self, 'Error', 'Nothing to save.')
            return
        t_debit = sum((it['debit'] for it in ledger_items), Decimal('0.0'))
        t_credit = sum((it['credit'] for it in ledger_items), Decimal('0.0'))
        t_stock = sum((to_decimal(it['value']) for it in stock_items), Decimal('0.0'))
        diff = t_debit + t_stock - t_credit
        if diff != Decimal('0.0'):
            if not self.temp_diff_tick.isChecked():
                QMessageBox.warning(self, 'Unbalanced', "Debit + Stock must equal Credit. Enable 'Allow Temporary Difference' to proceed.")
                return
            ans = QMessageBox.question(self, 'Temporary Difference', f"Difference of {format_money(abs(diff))} will be transferred to\n'Opening Difference A/c' to maintain accounting balance.\n\nDo you want to continue?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
            diff_acc = self._ensure_difference_account()
            if not diff_acc:
                QMessageBox.critical(self, 'Error', "Could not create 'Opening Difference A/c'. Save aborted.")
                return
            if diff > Decimal('0.0'):
                ledger_items.append({'account_id': diff_acc['id'], 'debit': Decimal('0.0'), 'credit': diff, 'narration': 'Auto: Temporary Opening Difference'})
            else:
                ledger_items.append({'account_id': diff_acc['id'], 'debit': abs(diff), 'credit': Decimal('0.0'), 'narration': 'Auto: Temporary Opening Difference'})
        try:
            if self.logic.has_other_transactions(self.company_id):
                ans = QMessageBox.question(self, 'Other Transactions Exist', 'This company already has other transactions (Sales, Purchase, etc.).\n\nSaving or editing the Opening Balance will affect:\n  • Trial Balance\n  • Stock Valuation\n  • Balance Sheet\n\nDo you want to continue?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if ans != QMessageBox.Yes:
                    return
        except Exception:
            pass
        vdate = qdate_to_db(self.date_edit.date())
        narr = self.narr_edit.text()
        res = self.logic.save_opening_balance(company_id=self.company_id, voucher_date=vdate, ledger_items=ledger_items, stock_items=stock_items, narration=narr)
        if res['success']:
            QMessageBox.information(self, 'Success', 'Opening Balance saved successfully!')
            self.load_data()
        else:
            QMessageBox.critical(self, 'Error', res['message'])

    def _ensure_difference_account(self):
        """Get or create 'Opening Difference A/c' using centralized ledger logic."""
        from bizora_core.ledger_logic import LedgerLogic
        ledger = LedgerLogic(self.db)
        ph = self._ph()
        existing = ledger.get_account_by_name(self.company_id, 'Opening Difference A/c')
        if existing:
            return existing
        acc_id = ledger.create_account(self.company_id, {'account_name': 'Opening Difference A/c', 'account_code': 'OPEN_DIFF', 'account_type': 'capital', 'group_name': 'Suspense', 'opening_balance': 0.0, 'opening_balance_type': 'Dr'})
        if acc_id:
            return ledger.get_account(self.company_id, acc_id)
        return None