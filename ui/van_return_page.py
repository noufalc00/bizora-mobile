"""Van Return / Van Settlement page."""
from decimal import Decimal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox, QFrame, QAbstractItemView, QHeaderView, QStyledItemDelegate, QStyle, QStyleOptionViewItem
from PySide6.QtGui import QPen, QColor
from PySide6.QtCore import Qt, QDate, QEvent, QTimer, QModelIndex
from config import active_company_manager
from bizora_core.common_finance import to_decimal, money_round, format_money
from bizora_core.van_logic import VanLogic
from ui import theme
from ui.theme_palette import palette
from ui.book_report_common import page_background_style
from ui.sales_entry_delegate import SalesBillDelegate
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin


class CreditTableRowDelegate(QStyledItemDelegate):
    """Draw Sales Entry-style row outline when SL No is clicked on credit rows."""

    def __init__(self, page: "VanReturnWidget"):
        super().__init__(page.credit_table)
        self.page = page

    def paint(self, painter, option, index):
        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.State_Selected
        super().paint(painter, clean_option, index)

        if getattr(self.page, "manually_selected_credit_row", -1) != index.row():
            return

        table = self.page.credit_table
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


class VanReturnWidget(UiMemoryMixin, QWidget):
    """Van Return / Settlement widget."""
    COL_SL = 0
    COL_PRODUCT = 1
    COL_ISSUED = 2
    COL_RETURNED = 3
    COL_SOLD = 4
    COL_RATE = 5
    COL_VALUE = 6
    CCOL_SL = 0
    CCOL_PARTY = 1
    CCOL_BILL = 2
    CCOL_AMOUNT = 3

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.logic = VanLogic(self.db)
        self.vans = []
        self.loads = []
        self.current_load_id = None
        self.current_return_id = None
        self._van_return_nav_ids = []
        self._updating = False
        self.manually_selected_row = -1
        self.manually_selected_credit_row = -1
        self._sales_entry_window = None
        self.setup_ui()
        self._install_event_filters()
        self.load_initial_data()
        self._init_ui_memory()

    def label_style(self):
        return theme.sales_micro_label_style()

    def input_style(self):
        return theme.sales_compact_input_style()

    def credit_table_style(self):
        p = palette()
        return self.table_style() + f"\n            QTableWidget {{\n                selection-background-color: transparent;\n                selection-color: {p['TEXT']};\n            }}\n            QTableWidget::item:selected {{\n                background-color: transparent;\n                color: {p['TEXT']};\n                border: 1px solid {p['BLUE']};\n            }}\n        "

    def button_style(self, color=None):
        p = palette()
        color = color or p['BLUE']
        return f"\n            QPushButton {{\n                background-color: {color};\n                color: white;\n                border: none;\n                border-radius: 3px;\n                padding: 4px 8px;\n                font-weight: bold;\n                font-size: 11px;\n                min-height: 24px;\n            }}\n            QPushButton:hover {{ background-color: {p['FOCUS']}; }}\n            QPushButton:disabled {{ background-color: {p['MUTED']}; color: {p['TEXT']}; }}\n        "

    def table_style(self):
        return theme.editable_table_style()

    def _label(self, text, width=120):
        label = QLabel(text)
        label.setMinimumWidth(80)
        label.setStyleSheet(self.label_style())
        return label

    def setup_ui(self):
        p = palette()
        self.setObjectName('VanReturnWidget')
        self.setStyleSheet(page_background_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        title = QLabel('Van Return Entry / Van Settlement')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"\n            QLabel {{\n                color: {p['BLUE']};\n                background-color: {p['PANEL']};\n                border: 1px solid {p['BORDER']};\n                border-radius: 6px;\n                padding: 8px;\n                font-size: 20px;\n                font-weight: bold;\n            }}\n        ")
        root.addWidget(title)
        top = QFrame()
        top.setStyleSheet(f"QFrame {{ background-color: {p['PANEL_2']}; border: 1px solid {p['BORDER']}; border-radius: 3px; }}")
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(4)
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self.return_no_edit = QLineEdit()
        self.return_no_edit.setReadOnly(True)
        self.return_no_edit.setStyleSheet(self.input_style())
        self.return_no_edit.setFixedWidth(75)
        self.date_edit = QDateEdit()
        configure_qdate_edit(self.date_edit)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setStyleSheet(self.input_style())
        self.date_edit.setFixedWidth(100)
        row1.addWidget(self._label('Return No:'))
        row1.addWidget(self.return_no_edit)
        nav_container = QWidget()
        nav_container.setFixedWidth(18)
        nav_v = QVBoxLayout(nav_container)
        nav_v.setSpacing(1)
        nav_v.setContentsMargins(0, 0, 0, 0)
        self.prev_return_btn = QPushButton('▲')
        self.prev_return_btn.setToolTip('Next Van Return')
        self.prev_return_btn.setStyleSheet(theme.sales_nav_button_style())
        self.prev_return_btn.setFixedSize(18, 11)
        self.prev_return_btn.clicked.connect(self.next_return)
        self.next_return_btn = QPushButton('▼')
        self.next_return_btn.setToolTip('Previous Van Return')
        self.next_return_btn.setStyleSheet(theme.sales_nav_button_style())
        self.next_return_btn.setFixedSize(18, 11)
        self.next_return_btn.clicked.connect(self.previous_return)
        nav_v.addWidget(self.prev_return_btn)
        nav_v.addWidget(self.next_return_btn)
        row1.addWidget(nav_container)
        self.header_reset_btn = QPushButton('Reset')
        self.header_reset_btn.setStyleSheet(theme.sales_compact_button_style())
        self.header_reset_btn.setFixedWidth(50)
        self.header_reset_btn.clicked.connect(self.reset_form)
        row1.addWidget(self.header_reset_btn)
        row1.addWidget(self._label('Date:'))
        row1.addWidget(self.date_edit)
        row1.addStretch()
        top_layout.addLayout(row1)
        row2 = QHBoxLayout()
        row2.setSpacing(4)
        self.van_combo = QComboBox()
        self.van_combo.setStyleSheet(self.input_style())
        self.van_combo.setFixedWidth(250)
        self.van_combo.currentIndexChanged.connect(self.load_open_loads)
        self.load_combo = QComboBox()
        self.load_combo.setStyleSheet(self.input_style())
        self.load_combo.setFixedWidth(210)
        self.load_btn = QPushButton('Load Van Data')
        self.load_btn.setStyleSheet(self.button_style('#475569'))
        self.load_btn.clicked.connect(self.load_selected_van_load)
        self.manage_vans_btn = QPushButton('Manage Vans')
        self.manage_vans_btn.setStyleSheet(self.button_style('#475569'))
        self.manage_vans_btn.clicked.connect(self.manage_vans)
        row2.addWidget(self._label('Select Van:'))
        row2.addWidget(self.van_combo)
        row2.addWidget(self.manage_vans_btn)
        row2.addWidget(self._label('Load No:'))
        row2.addWidget(self.load_combo)
        row2.addWidget(self.load_btn)
        row2.addStretch()
        top_layout.addLayout(row2)
        row3 = QHBoxLayout()
        row3.setSpacing(4)
        self.narration_edit = QLineEdit()
        self.narration_edit.setStyleSheet(self.input_style())
        self.narration_edit.setFixedWidth(380)
        row3.addWidget(self._label('Narration:'))
        row3.addWidget(self.narration_edit)
        row3.addStretch()
        top_layout.addLayout(row3)
        root.addWidget(top)
        section1 = QLabel('Stock Reconciliation')
        section1.setStyleSheet(f"color: {p['YELLOW']}; background-color: {p['PANEL']}; border: 1px solid {p['BORDER']}; border-radius: 5px; padding: 5px; font-weight: bold;")
        root.addWidget(section1)
        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(7)
        self.stock_table.setHorizontalHeaderLabels(['SL No', 'Product', 'Issued Qty', 'Returned Qty', 'Sold Qty', 'Rate', 'Sold Value'])
        self.stock_table.verticalHeader().setVisible(False)
        self.stock_table.setStyleSheet(self.table_style())
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.stock_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.stock_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)
        self.stock_table.horizontalHeader().setSectionResizeMode(self.COL_PRODUCT, QHeaderView.Stretch)
        self.stock_table.setColumnWidth(self.COL_SL, 50)
        self.stock_table.setColumnWidth(self.COL_ISSUED, 100)
        self.stock_table.setColumnWidth(self.COL_RETURNED, 100)
        self.stock_table.setColumnWidth(self.COL_SOLD, 100)
        self.stock_table.setColumnWidth(self.COL_RATE, 100)
        self.stock_table.setColumnWidth(self.COL_VALUE, 110)
        self.stock_table_delegate = SalesBillDelegate(self)
        self.stock_table.setItemDelegate(self.stock_table_delegate)
        self.stock_table.itemChanged.connect(self.on_stock_item_changed)
        self.stock_table.installEventFilter(self)
        self.stock_table.viewport().installEventFilter(self)
        root.addWidget(self.stock_table, 2)
        mid = QHBoxLayout()
        credit_panel = QFrame()
        credit_panel.setStyleSheet(f"QFrame {{ background-color: {p['PANEL']}; border: 1px solid {p['BORDER']}; border-radius: 8px; }}")
        credit_layout = QVBoxLayout(credit_panel)
        credit_layout.setContentsMargins(8, 8, 8, 8)
        credit_title = QLabel('Credit Bills Issued')
        credit_title.setStyleSheet(f"color: {p['YELLOW']}; font-weight: bold; background: transparent;")
        credit_layout.addWidget(credit_title)
        self.credit_table = QTableWidget()
        self.credit_table.setColumnCount(4)
        self.credit_table.setHorizontalHeaderLabels(['SL No', 'Shop/Party', 'Bill No', 'Amount'])
        self.credit_table.verticalHeader().setVisible(False)
        self.credit_table.setStyleSheet(self.credit_table_style())
        self.credit_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.credit_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.credit_table.setEditTriggers(QAbstractItemView.CurrentChanged | QAbstractItemView.SelectedClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)
        self.credit_table.setItemDelegate(CreditTableRowDelegate(self))
        self.credit_table.installEventFilter(self)
        self.credit_table.viewport().installEventFilter(self)
        self.credit_table.itemClicked.connect(self.on_credit_cell_clicked)
        self.credit_table.horizontalHeader().setSectionResizeMode(self.CCOL_PARTY, QHeaderView.Stretch)
        self.credit_table.setColumnWidth(self.CCOL_SL, 60)
        self.credit_table.setColumnWidth(self.CCOL_BILL, 100)
        self.credit_table.setColumnWidth(self.CCOL_AMOUNT, 120)
        self.credit_table.itemChanged.connect(self.on_credit_item_changed)
        credit_layout.addWidget(self.credit_table)
        cr_btns = QHBoxLayout()
        add_row_btn = QPushButton('Add Credit Row')
        add_row_btn.setStyleSheet(self.button_style('#475569'))
        add_row_btn.clicked.connect(self.add_credit_row)
        remove_row_btn = QPushButton('Remove Row')
        remove_row_btn.setStyleSheet(self.button_style(p['RED']))
        remove_row_btn.clicked.connect(self.remove_credit_row)
        cr_btns.addWidget(add_row_btn)
        cr_btns.addWidget(remove_row_btn)
        cr_btns.addStretch()
        credit_layout.addLayout(cr_btns)
        mid.addWidget(credit_panel, 3)
        summary = QFrame()
        summary.setStyleSheet(f"QFrame {{ background-color: {p['PANEL']}; border: 1px solid {p['BORDER']}; border-radius: 8px; }}")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(7)
        self.total_goods_label = self._summary_label('Total Goods Sold Value: ₹0.00')
        self.credit_total_label = self._summary_label('Less Credit Bills: ₹0.00')
        self.expected_cash_label = self._summary_label('Expected Cash: ₹0.00')
        actual_row = QHBoxLayout()
        actual_row.addWidget(self._label('Actual Cash:', 110))
        self.actual_cash_edit = QLineEdit('0.00')
        self.actual_cash_edit.setStyleSheet(self.input_style())
        self.actual_cash_edit.textChanged.connect(self.calculate_summary)
        actual_row.addWidget(self.actual_cash_edit)
        self.shortage_excess_label = self._summary_label('Shortage/Excess: ₹0.00')
        summary_layout.addWidget(self.total_goods_label)
        summary_layout.addWidget(self.credit_total_label)
        summary_layout.addWidget(self.expected_cash_label)
        summary_layout.addLayout(actual_row)
        summary_layout.addWidget(self.shortage_excess_label)
        mid.addWidget(summary, 2)
        root.addLayout(mid, 1)
        footer = QFrame()
        footer.setStyleSheet(f"QFrame {{ background-color: {p['PANEL']}; border: 1px solid {p['BORDER']}; border-radius: 8px; }}")
        footer_layout = QHBoxLayout(footer)
        self.remove_return_btn = QPushButton('Remove Van Return')
        self.remove_return_btn.setStyleSheet(self.button_style(p['RED']))
        self.remove_return_btn.setToolTip('Delete this saved Van Return permanently')
        self.remove_return_btn.clicked.connect(self.remove_van_return)
        footer_layout.addWidget(self.remove_return_btn)
        footer_layout.addStretch()
        self.convert_btn = QPushButton('Convert to Sales')
        self.convert_btn.setStyleSheet(self.button_style('#7c3aed'))
        self.convert_btn.setToolTip('Convert this Van Return into a Sales Bill')
        self.convert_btn.clicked.connect(self.convert_to_sales_bill)
        self.save_button = QPushButton('Save Van Return')
        self.save_button.setStyleSheet(self.button_style(p['GREEN']))
        self.save_button.clicked.connect(self.save_van_return)
        self.reset_button = QPushButton('Reset All')
        self.reset_button.setStyleSheet(self.button_style('#64748b'))
        self.reset_button.clicked.connect(self.reset_form)
        self.exit_button = QPushButton('Exit')
        self.exit_button.setStyleSheet(self.button_style('#475569'))
        self.exit_button.clicked.connect(self.close_window)
        footer_layout.addWidget(self.convert_btn)
        footer_layout.addWidget(self.save_button)
        footer_layout.addWidget(self.reset_button)
        footer_layout.addWidget(self.exit_button)
        root.addWidget(footer)
        self.add_credit_row()
        self.calculate_summary()

    def _summary_label(self, text):
        p = palette()
        label = QLabel(text)
        label.setStyleSheet(f"\n            QLabel {{\n                color: {p['TEXT']};\n                background-color: {p['PANEL_2']};\n                border: 1px solid {p['BORDER']};\n                border-radius: 5px;\n                padding: 8px;\n                font-weight: bold;\n            }}\n        ")
        return label

    def company_id(self):
        return active_company_manager.get_active_company_id()

    def _install_event_filters(self):
        """Install event filters for keyboard navigation."""
        for field_name in ['return_no_edit', 'date_edit', 'van_combo', 'load_combo', 'load_btn', 'narration_edit', 'actual_cash_edit', 'stock_table', 'credit_table']:
            if hasattr(self, field_name):
                getattr(self, field_name).installEventFilter(self)
        if hasattr(self, 'stock_table'):
            self.stock_table.viewport().installEventFilter(self)
        if hasattr(self, 'credit_table'):
            self.credit_table.viewport().installEventFilter(self)

    def load_initial_data(self):
        company_id = self.company_id()
        if not company_id:
            return
        self.logic.ensure_schema()
        self.return_no_edit.setText(self.logic.get_next_van_return_no(company_id))
        self.load_vans()
        self.load_open_loads()
        self.add_credit_row()

    def load_vans(self):
        company_id = self.company_id()
        self.van_combo.blockSignals(True)
        self.van_combo.clear()
        self.vans = self.logic.get_vans(company_id) if company_id else []
        if not self.vans:
            self.van_combo.addItem('-- No Van Found --', None)
        else:
            for van in self.vans:
                self.van_combo.addItem(van.get('location_name', ''), van.get('id'))
        self.van_combo.blockSignals(False)
        self.load_open_loads()

    def load_open_loads(self):
        company_id = self.company_id()
        van_id = self.van_combo.currentData()
        self.load_combo.clear()
        self.loads = []
        if company_id and van_id:
            self.loads = self.logic.get_open_van_loads(company_id, van_id)
        if not self.loads:
            self.load_combo.addItem('-- No Open Load --', None)
        else:
            for load in self.loads:
                self.load_combo.addItem(f"{load.get('load_no')}  {load.get('load_date')}", load.get('id'))

    def manage_vans(self):
        company_id = self.company_id()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        from ui.van_entry_page import VanSelectionPopup
        dialog = VanSelectionPopup(self, self.db, self.logic)
        if dialog.exec() and dialog.selected_van:
            self.load_vans()
            index = self.van_combo.findData(dialog.selected_van['id'])
            if index >= 0:
                self.van_combo.setCurrentIndex(index)

    def load_selected_van_load(self):
        company_id = self.company_id()
        van_id = self.van_combo.currentData()
        load_id = self.load_combo.currentData()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        if not van_id:
            QMessageBox.warning(self, 'No Van', 'Please select a van.')
            return
        result = self.logic.get_van_load_for_return(company_id, van_id, load_id)
        if not result.get('success'):
            QMessageBox.warning(self, 'No Data', result.get('message', 'No open van load found.'))
            return
        self.current_load_id = result['header'].get('id')
        self.populate_stock_table(result.get('items', []))
        self.calculate_summary()

    def populate_stock_table(self, items):
        self._updating = True
        self.stock_table.setRowCount(len(items))
        for row, item in enumerate(items):
            self._set_stock(row, self.COL_SL, str(row + 1), editable=False, align=Qt.AlignCenter)
            prod_item = self._set_stock(row, self.COL_PRODUCT, item.get('product_name', ''), editable=False)
            prod_item.setData(Qt.UserRole, item)
            issued = to_decimal(item.get('load_qty'))
            rate = to_decimal(item.get('rate'))
            self._set_stock(row, self.COL_ISSUED, str(issued), editable=False, align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_stock(row, self.COL_RETURNED, '0.00', editable=True, align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_stock(row, self.COL_SOLD, str(issued), editable=False, align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_stock(row, self.COL_RATE, str(rate), editable=True, align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_stock(row, self.COL_VALUE, str(money_round(issued * rate)), editable=False, align=Qt.AlignRight | Qt.AlignVCenter)
        self._updating = False

    def _set_stock(self, row, col, text, editable=True, align=None):
        item = QTableWidgetItem(str(text))
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if editable:
            flags |= Qt.ItemIsEditable
        item.setFlags(flags)
        if align is not None:
            item.setTextAlignment(align)
        self.stock_table.setItem(row, col, item)
        return item

    def _set_credit(self, row, col, text, editable=True, align=None):
        item = QTableWidgetItem(str(text))
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
        if not editable:
            flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        item.setFlags(flags)
        if align is not None:
            item.setTextAlignment(align)
        self.credit_table.setItem(row, col, item)
        return item

    def recalculate_row(self, row, **kwargs):
        """Called by SalesBillDelegate. Maps to recalculate_stock_row for Van Return."""
        self.recalculate_stock_row(row)

    def on_stock_item_changed(self, item):
        if self._updating or item.column() not in (self.COL_RETURNED, self.COL_RATE):
            return
        row = item.row()
        self.recalculate_stock_row(row)
        self.calculate_summary()

    def on_credit_item_changed(self, item):
        if self._updating:
            return
        if item.column() == self.CCOL_AMOUNT:
            item.setText(str(to_decimal(item.text())))
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.calculate_summary()

    def recalculate_stock_row(self, row):
        self._updating = True
        try:
            issued = to_decimal(self._stock_text(row, self.COL_ISSUED))
            returned = to_decimal(self._stock_text(row, self.COL_RETURNED))
            if returned > issued:
                returned = issued
                self.stock_table.item(row, self.COL_RETURNED).setText(str(returned))
            rate = to_decimal(self._stock_text(row, self.COL_RATE))
            sold = issued - returned
            sold_value = money_round(sold * rate)
            self.stock_table.item(row, self.COL_SOLD).setText(str(sold))
            self.stock_table.item(row, self.COL_VALUE).setText(str(sold_value))
            for col in (self.COL_RETURNED, self.COL_SOLD, self.COL_RATE, self.COL_VALUE):
                it = self.stock_table.item(row, col)
                if it:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        finally:
            self._updating = False

    def calculate_summary(self):
        required = ['actual_cash_edit', 'stock_table', 'credit_table', 'total_goods_label', 'credit_total_label', 'expected_cash_label', 'shortage_excess_label', 'save_button']
        if not all((hasattr(self, name) for name in required)):
            return
        try:
            total_sold = Decimal('0.00')
            for row in range(self.stock_table.rowCount()):
                total_sold += to_decimal(self._stock_text(row, self.COL_VALUE))
            credit_total = Decimal('0.00')
            for row in range(self.credit_table.rowCount()):
                credit_total += to_decimal(self._credit_text(row, self.CCOL_AMOUNT))
            expected_cash = money_round(total_sold - credit_total)
            actual_cash = to_decimal(self.actual_cash_edit.text())
            shortage_excess = money_round(actual_cash - expected_cash)
            self.total_goods_label.setText(f'Total Goods Sold Value: {format_money(total_sold)}')
            self.credit_total_label.setText(f'Less Credit Bills: {format_money(credit_total)}')
            self.expected_cash_label.setText(f'Expected Cash: {format_money(expected_cash)}')
            self.shortage_excess_label.setText(f'Shortage/Excess: {format_money(shortage_excess)}')
            if shortage_excess == Decimal('0.00'):
                self.shortage_excess_label.setStyleSheet(self._summary_ok_style())
                self.save_button.setEnabled(True)
            else:
                self.shortage_excess_label.setStyleSheet(self._summary_bad_style())
                self.save_button.setEnabled(False)
        except Exception as e:
            QMessageBox.warning(self, 'Calculation Error', f'Error calculating summary: {e}')

    def _summary_ok_style(self):
        p = palette()
        return f"color: {p['GREEN']}; background-color: {p['PANEL_2']}; border: 1px solid {p['BORDER']}; border-radius: 5px; padding: 8px; font-weight: bold;"

    def _summary_bad_style(self):
        p = palette()
        return f"color: {p['RED']}; background-color: {p['PANEL_2']}; border: 1px solid {p['BORDER']}; border-radius: 5px; padding: 8px; font-weight: bold;"

    def _stock_text(self, row, col):
        item = self.stock_table.item(row, col)
        return item.text() if item else ''

    def _credit_text(self, row, col):
        item = self.credit_table.item(row, col)
        return item.text() if item else ''

    def add_credit_row(self):
        self._updating = True
        row = self.credit_table.rowCount()
        self.credit_table.insertRow(row)
        self._set_credit(row, self.CCOL_SL, str(row + 1), editable=False, align=Qt.AlignCenter)
        self._set_credit(row, self.CCOL_PARTY, '')
        self._set_credit(row, self.CCOL_BILL, '')
        self._set_credit(row, self.CCOL_AMOUNT, '0.00', align=Qt.AlignRight | Qt.AlignVCenter)
        self._updating = False

    def remove_credit_row(self):
        """Remove a credit row only after SL No click (Sales Entry pattern)."""
        target_row = getattr(self, 'manually_selected_credit_row', -1)
        if target_row < 0:
            QMessageBox.information(
                self,
                'Remove Row',
                'Please click the SL No of the row you want to remove, then press Remove Row.',
            )
            return
        if target_row >= self.credit_table.rowCount():
            self.manually_selected_credit_row = -1
            return
        reply = QMessageBox.question(
            self,
            'Remove Row',
            f'Are you sure you want to remove row {target_row + 1}?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.credit_table.removeRow(target_row)
        self.manually_selected_credit_row = -1
        self.credit_table.clearSelection()
        self.credit_table.viewport().update()
        self.renumber_credit_rows()
        self.calculate_summary()

    def renumber_credit_rows(self):
        for row in range(self.credit_table.rowCount()):
            item = self.credit_table.item(row, self.CCOL_SL)
            if item:
                item.setText(str(row + 1))

    def on_credit_cell_clicked(self, item):
        """Open credit cell editor with full text selected (Sales Entry pattern)."""
        if not item or item.column() == self.CCOL_SL:
            return
        self.manually_selected_credit_row = -1
        self.credit_table.clearSelection()
        self.credit_table.viewport().update()
        self.credit_table.editItem(item)
        QTimer.singleShot(0, self._select_credit_editor_text)

    def _select_credit_editor_text(self):
        editor = self.credit_table.focusWidget()
        if isinstance(editor, QLineEdit):
            theme.prepare_sales_cell_editor(editor)
            editor.selectAll()

    def _move_credit_cell(self, delta):
        row = self.credit_table.currentRow()
        col = self.credit_table.currentColumn()
        if row < 0:
            row, col = (0, self.CCOL_PARTY)
        editable_cols = [self.CCOL_PARTY, self.CCOL_BILL, self.CCOL_AMOUNT]
        if col not in editable_cols:
            col = self.CCOL_PARTY
        index = editable_cols.index(col) + delta
        if index >= len(editable_cols):
            row += 1
            index = 0
            if row >= self.credit_table.rowCount():
                self.add_credit_row()
        elif index < 0:
            row -= 1
            index = len(editable_cols) - 1
            if row < 0:
                row = 0
                index = 0
        new_col = editable_cols[index]
        self.credit_table.setCurrentCell(row, new_col)
        item = self.credit_table.item(row, new_col)
        if item:
            self.credit_table.editItem(item)
            QTimer.singleShot(0, self._select_credit_editor_text)

    def _refresh_return_nav_list(self, company_id):
        try:
            self._van_return_nav_ids = self.logic.get_van_return_ids(company_id)
        except Exception:
            self._van_return_nav_ids = []

    def previous_return(self):
        self._navigate_return(-1)

    def next_return(self):
        self._navigate_return(+1)

    def _navigate_return(self, delta):
        company_id = self.company_id()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        self._refresh_return_nav_list(company_id)
        if not self._van_return_nav_ids:
            QMessageBox.information(self, 'No Returns', 'No saved Van Returns are available yet.')
            return
        if self.current_return_id in self._van_return_nav_ids:
            idx = self._van_return_nav_ids.index(self.current_return_id)
        else:
            idx = len(self._van_return_nav_ids) if delta < 0 else -1
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(self._van_return_nav_ids):
            QMessageBox.information(self, 'End', 'No more Van Returns in this direction.')
            return
        self.load_van_return_by_id(self._van_return_nav_ids[new_idx])

    def load_van_return_by_id(self, return_id):
        company_id = self.company_id()
        result = self.logic.get_van_return_by_id(company_id, return_id)
        if not result.get('success'):
            QMessageBox.warning(self, 'Load Error', result.get('message', 'Unable to load Van Return.'))
            return
        header = result.get('header') or {}
        self.current_return_id = header.get('id')
        self.current_load_id = header.get('van_load_id')
        self.return_no_edit.setText(str(header.get('return_no', '')))
        self.date_edit.setDate(QDate.fromString(str(header.get('return_date', '')), 'yyyy-MM-dd'))
        self.narration_edit.setText(str(header.get('narration') or ''))
        self.actual_cash_edit.setText(str(header.get('cash_received', '0.00')))
        van_idx = self.van_combo.findData(header.get('van_id'))
        if van_idx >= 0:
            self.van_combo.setCurrentIndex(van_idx)
        self.stock_table.setRowCount(0)
        items = result.get('items') or []
        self.stock_table.setRowCount(len(items))
        self._updating = True
        for row, item in enumerate(items):
            self._set_stock(row, self.COL_SL, str(row + 1), editable=False, align=Qt.AlignCenter)
            prod_item = self._set_stock(row, self.COL_PRODUCT, item.get('product_name', ''), editable=False)
            prod_item.setData(Qt.UserRole, {'product_id': item.get('product_id')})
            self._set_stock(row, self.COL_ISSUED, str(item.get('issued_qty', '0.00')), editable=False, align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_stock(row, self.COL_RETURNED, str(item.get('returned_qty', '0.00')), editable=True, align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_stock(row, self.COL_SOLD, str(item.get('sold_qty', '0.00')), editable=False, align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_stock(row, self.COL_RATE, str(item.get('rate', '0.00')), editable=True, align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_stock(row, self.COL_VALUE, str(item.get('sold_value', '0.00')), editable=False, align=Qt.AlignRight | Qt.AlignVCenter)
        self._updating = False
        self.credit_table.setRowCount(0)
        for bill in result.get('credit_bills') or []:
            row = self.credit_table.rowCount()
            self.credit_table.insertRow(row)
            self._set_credit(row, self.CCOL_SL, str(row + 1), editable=False, align=Qt.AlignCenter)
            self._set_credit(row, self.CCOL_PARTY, bill.get('party_name', ''))
            self._set_credit(row, self.CCOL_BILL, bill.get('bill_no', ''))
            self._set_credit(row, self.CCOL_AMOUNT, str(bill.get('amount', '0.00')), align=Qt.AlignRight | Qt.AlignVCenter)
        if self.credit_table.rowCount() == 0:
            self.add_credit_row()
        self.calculate_summary()

    def collect_return_items(self):
        items = []
        for row in range(self.stock_table.rowCount()):
            prod_item = self.stock_table.item(row, self.COL_PRODUCT)
            product = prod_item.data(Qt.UserRole) if prod_item else {}
            items.append({'product_id': product.get('product_id'), 'product_name': self._stock_text(row, self.COL_PRODUCT), 'issued_qty': self._stock_text(row, self.COL_ISSUED), 'returned_qty': self._stock_text(row, self.COL_RETURNED), 'rate': self._stock_text(row, self.COL_RATE)})
        return items

    def collect_credit_bills(self):
        bills = []
        for row in range(self.credit_table.rowCount()):
            amount = to_decimal(self._credit_text(row, self.CCOL_AMOUNT))
            if amount <= 0:
                continue
            bills.append({'party_name': self._credit_text(row, self.CCOL_PARTY), 'bill_no': self._credit_text(row, self.CCOL_BILL), 'amount': amount})
        return bills

    def save_van_return(self):
        company_id = self.company_id()
        van_id = self.van_combo.currentData()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        if not van_id:
            QMessageBox.warning(self, 'No Van', 'Please select a van.')
            return
        if not self.current_load_id:
            QMessageBox.warning(self, 'No Load', 'Please load van data first.')
            return
        result = self.logic.save_van_return(company_id=company_id, van_id=van_id, return_date=qdate_to_db(self.date_edit.date()), van_load_id=self.current_load_id, return_items=self.collect_return_items(), credit_bills=self.collect_credit_bills(), cash_received=self.actual_cash_edit.text(), narration=self.narration_edit.text().strip())
        if result.get('success'):
            QMessageBox.information(self, 'Saved', result.get('message', 'Van Return saved.'))
            self.reset_form()
        else:
            QMessageBox.warning(self, 'Error', result.get('message', 'Failed to save Van Return.'))

    def remove_van_return(self):
        """Safely delete the currently loaded Van Return with confirmation."""
        company_id = self.company_id()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        return_id = self.current_return_id
        if not return_id:
            QMessageBox.warning(self, 'No Van Return Selected', 'Please navigate to a saved Van Return before deleting.\nUse the ▲/▼ buttons to load a previous entry.')
            return
        return_no = self.return_no_edit.text().strip() or str(return_id)
        ans = QMessageBox.question(self, 'Remove Van Return', f"Do you want to remove Van Return  '{return_no}'?\n\nThis will permanently delete:\n  • The Van Return header\n  • All stock reconciliation rows\n  • All credit bill records\n  • Associated stock movements (sold qty will be reversed)\n  • The linked Van Load will be re-opened to 'Loaded' status\n\nThis action cannot be undone.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        result = self.logic.delete_van_return(company_id, return_id)
        if result.get('success'):
            QMessageBox.information(self, 'Deleted', result.get('message', 'Van Return deleted.'))
            self.reset_form()
        else:
            QMessageBox.warning(self, 'Delete Failed', result.get('message', 'Failed to delete Van Return.'))

    def reset_form(self):
        company_id = self.company_id()
        self.current_return_id = None
        self.current_load_id = None
        self.narration_edit.clear()
        self.actual_cash_edit.setText('0.00')
        self.stock_table.setRowCount(0)
        self.credit_table.setRowCount(0)
        self.manually_selected_row = -1
        self.manually_selected_credit_row = -1
        self.add_credit_row()
        if company_id:
            self.return_no_edit.setText(self.logic.get_next_van_return_no(company_id))
        self.load_open_loads()
        self.calculate_summary()

    def close_window(self):
        window = self.window()
        if window:
            window.close()

    def eventFilter(self, obj, event):
        if hasattr(self, 'stock_table') and obj == self.stock_table.viewport() and (event.type() == QEvent.MouseButtonPress):
            if event.button() == Qt.LeftButton:
                item = self.stock_table.itemAt(event.pos())
                if item:
                    clicked_row = item.row()
                    clicked_column = item.column()
                    if clicked_column == 0:
                        self.manually_selected_row = clicked_row
                        self.stock_table.clearSelection()
                        self.stock_table.viewport().update()
                        return True
                    else:
                        self.manually_selected_row = -1
                        self.stock_table.clearSelection()
                        self.stock_table.viewport().update()
                        self.stock_table.editItem(item)
                        return True
        if hasattr(self, 'credit_table') and obj == self.credit_table.viewport() and (event.type() == QEvent.MouseButtonPress):
            if event.button() == Qt.LeftButton:
                item = self.credit_table.itemAt(event.pos())
                if item:
                    clicked_row = item.row()
                    clicked_column = item.column()
                    if clicked_column == self.CCOL_SL:
                        self.manually_selected_credit_row = clicked_row
                        self.credit_table.clearSelection()
                        self.credit_table.viewport().update()
                        return True
                    self.manually_selected_credit_row = -1
                    self.credit_table.clearSelection()
                    self.credit_table.viewport().update()
                    self.credit_table.editItem(item)
                    QTimer.singleShot(0, self._select_credit_editor_text)
                    return True
        if event.type() != QEvent.KeyPress:
            if hasattr(self, 'credit_table') and obj is self.credit_table.viewport() and (event.type() == QEvent.MouseButtonDblClick):
                return True
            return super().eventFilter(obj, event)
        key = event.key()
        enter = key in (Qt.Key_Return, Qt.Key_Enter)
        esc = key == Qt.Key_Escape
        f1 = key == Qt.Key_F1
        if f1:
            if hasattr(self, 'stock_table') and self.stock_table.rowCount() > 0:
                row = self.stock_table.rowCount() - 1
                if hasattr(self, 'stock_table_delegate') and hasattr(self.stock_table_delegate, 'move_to_cell'):
                    self.stock_table_delegate.move_to_cell(row, self.COL_RETURNED)
                else:
                    self.stock_table.setCurrentCell(row, self.COL_RETURNED)
                    idx = self.stock_table.model().index(row, self.COL_RETURNED)
                    if idx.isValid():
                        self.stock_table.edit(idx)
            return True
        if enter:
            if obj is self.return_no_edit:
                self.date_edit.setFocus()
                return True
            if obj is self.date_edit:
                self.van_combo.setFocus()
                return True
            if obj is self.van_combo:
                self.load_combo.setFocus()
                return True
            if obj is self.load_combo:
                self.load_btn.setFocus()
                return True
            if obj is self.load_btn:
                self.load_btn.click()
                self.narration_edit.setFocus()
                return True
            if obj is self.narration_edit:
                if hasattr(self, 'stock_table') and self.stock_table.rowCount() > 0:
                    self.stock_table.setCurrentCell(0, self.COL_RETURNED)
                    idx = self.stock_table.model().index(0, self.COL_RETURNED)
                    if idx.isValid():
                        self.stock_table.edit(idx)
                return True
            if hasattr(self, 'actual_cash_edit') and obj is self.actual_cash_edit:
                self.save_button.setFocus()
                return True
        if esc:
            if obj is self.return_no_edit:
                self.date_edit.setFocus()
                return True
            if obj is self.date_edit:
                self.return_no_edit.setFocus()
                return True
            if obj is self.van_combo:
                self.date_edit.setFocus()
                return True
            if obj is self.load_combo:
                self.van_combo.setFocus()
                return True
            if obj is self.load_btn:
                self.load_combo.setFocus()
                return True
            if obj is self.narration_edit:
                self.load_btn.setFocus()
                return True
            if hasattr(self, 'actual_cash_edit') and obj is self.actual_cash_edit:
                self.narration_edit.setFocus()
                return True
        if hasattr(self, 'stock_table') and obj is self.stock_table:
            if enter:
                row = self.stock_table.currentRow()
                if self.stock_table.currentColumn() == self.COL_RETURNED:
                    if row < self.stock_table.rowCount() - 1:
                        nr = row + 1
                        self.stock_table.setCurrentCell(nr, self.COL_RETURNED)
                        idx = self.stock_table.model().index(nr, self.COL_RETURNED)
                        if idx.isValid():
                            self.stock_table.edit(idx)
                    elif hasattr(self, 'actual_cash_edit'):
                        self.actual_cash_edit.setFocus()
                    return True
            if esc:
                self.stock_table.clearFocus()
                if hasattr(self, 'actual_cash_edit'):
                    self.actual_cash_edit.setFocus()
                return True
        if hasattr(self, 'credit_table') and obj is self.credit_table:
            if enter:
                self._move_credit_cell(1)
                return True
            if esc:
                self.credit_table.clearFocus()
                if hasattr(self, 'actual_cash_edit'):
                    self.actual_cash_edit.setFocus()
                return True
        return super().eventFilter(obj, event)

    def convert_to_sales_bill(self):
        """ERP-style: convert Van Return into a Sales Bill with safe tracking."""
        company_id = self.company_id()
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        return_id = self.current_return_id
        if return_id:
            status = self.logic.get_van_return_conversion_status(company_id, return_id)
            if status.get('converted'):
                ref = status.get('sales_ref', '')
                QMessageBox.warning(self, 'Already Converted', f"Van Return already converted to Sales Bill{(' (' + ref + ')' if ref else '')}.")
                return
        items = []
        if hasattr(self, 'stock_table'):
            for row in range(self.stock_table.rowCount()):
                pi = self.stock_table.item(row, self.COL_PRODUCT)
                if not pi:
                    continue
                sold_item = self.stock_table.item(row, self.COL_SOLD)
                rate_item = self.stock_table.item(row, self.COL_RATE)
                sold_qty = to_decimal(sold_item.text() if sold_item else '0')
                rate = to_decimal(rate_item.text() if rate_item else '0')
                if sold_qty <= 0:
                    continue
                prod = pi.data(Qt.UserRole) or {}
                items.append({'product_id': prod.get('product_id') or prod.get('id'), 'name': prod.get('product_name', pi.text()), 'barcode': prod.get('barcode', ''), 'qty': float(sold_qty), 'rate': float(rate)})
        if not items:
            QMessageBox.warning(self, 'No Items', 'No sold items (Sold Qty > 0) found to convert.')
            return
        if return_id:
            rev = self.logic.reverse_van_return_stock(company_id, return_id)
            if not rev.get('success'):
                QMessageBox.warning(self, 'Stock Reversal Failed', f"Could not reverse stock movements: {rev.get('message')}\nConversion aborted to prevent double posting.")
                return
            self.logic.mark_van_return_converted(company_id, return_id, 'Pending')
        self._open_sales_with_items(items, source_van_return_id=return_id)

    def _open_sales_with_items(self, items, source_van_return_id=None):
        if hasattr(self, '_sales_entry_window') and self._sales_entry_window is not None:
            if self._sales_entry_window.isVisible():
                QMessageBox.warning(self, 'In Progress', 'Conversion is already in progress.')
                self._sales_entry_window.activateWindow()
                return
        try:
            from .sales_entry import SalesEntryWidget
            from .standalone_window import StandaloneModuleWindow, _resolve_hub_window
            widget = SalesEntryWidget(self.db)
            title = f'Sales Entry — Van Return #{source_van_return_id}' if source_van_return_id else 'Sales Entry (Van Conversion)'
            hub = _resolve_hub_window(self.window())
            win = StandaloneModuleWindow(widget, title, hub)
            if hub is not None:
                hub._center_and_show_window(win)
            else:
                win.show()
            self._sales_entry_window = win
            QTimer.singleShot(300, lambda: widget.preload_van_items(items, source_van_return_id=source_van_return_id))
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not open Sales Entry:\n{e}')