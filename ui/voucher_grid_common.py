"""Shared voucher-grid UI for Cash/Bank Receipt and Payment pages."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QDate, QObject, QEvent, QTimer, QStringListModel
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QDateEdit, QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QAbstractItemView, QMessageBox, QApplication, QSizePolicy, QStyledItemDelegate, QStyle, QStyleOptionViewItem
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QCompleter
from config import active_company_manager
from bizora_core.cash_bank_voucher_logic import CashBankVoucherLogic
from bizora_core.print_settings_logic import get_print_settings
from utils.a4_voucher_print_helpers import company_print_data, generate_payment_receipt_html
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, prepare_report_date_edit
from ui.ui_memory import UiMemoryMixin
from ui.entry_field_helpers import install_click_select_all

def _voucher_style() -> dict[str, str]:
    from ui import theme
    c = theme._theme_colors()
    return {'bg': c['app_bg'], 'panel': c['panel_bg'], 'field': c['input_bg'], 'border': c['border'], 'text': c['input_text'], 'label': c['accent_label'], 'blue': c['button_primary'], 'green': c['button_success'], 'red': c['button_danger'], 'orange': c['button_warning']}

def _style() -> dict[str, str]:
    return _voucher_style()

def amount_to_float(text: str) -> float:
    try:
        return float(str(text or '0').replace(',', '').strip() or 0)
    except Exception:
        return 0.0

class SearchAccountCombo(QComboBox):
    """Editable account combo with search, placeholder text, and full dropdown list."""

    PLACEHOLDER = "Select Account"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._options: List[Dict[str, Any]] = []
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(210)
        self.setMaxVisibleItems(20)
        self.completer_model = QStringListModel(self)
        self.completer_obj = QCompleter(self.completer_model, self)
        self.completer_obj.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer_obj.setFilterMode(Qt.MatchContains)
        self.completer_obj.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(self.completer_obj)
        self.completer_obj.activated.connect(self._on_completer_activated)
        self.setStyleSheet(self.style_text())
        self.view().setMinimumWidth(380)
        self._apply_popup_theme()
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(self.PLACEHOLDER)
            install_click_select_all(line_edit)

    def _on_completer_activated(self, text: str) -> None:
        """Apply the account label chosen from the completer popup."""
        self.setCurrentText(str(text or ""))

    @staticmethod
    def style_text() -> str:
        from ui import theme
        return theme.sales_compact_input_style()

    def _apply_popup_theme(self) -> None:
        """Keep completer and dropdown lists readable in the active theme."""
        from ui import theme
        theme.apply_completer_popup_theme(self.completer_obj)
        theme.apply_combo_dropdown_theme(self)

    def _clear_selection(self) -> None:
        """Show placeholder text without pre-selecting the first account."""
        self.setCurrentIndex(-1)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.clear()
            line_edit.setPlaceholderText(self.PLACEHOLDER)

    def set_options(self, options: List[Dict[str, Any]], *, preserve_text: bool = False) -> None:
        """Load account options into the dropdown without auto-selecting the first row."""
        current_text = self.currentText().strip() if preserve_text else ""
        self._options = list(options or [])
        self.blockSignals(True)
        self.clear()
        for opt in self._options:
            label = opt.get("label") or opt.get("account_name") or ""
            self.addItem(label, opt)
            self.setItemData(self.count() - 1, label, Qt.ToolTipRole)
        self.completer_model.setStringList([self.itemText(i) for i in range(self.count())])
        if preserve_text and current_text:
            self.setCurrentText(current_text)
        else:
            self._clear_selection()
        self.blockSignals(False)
        self._apply_popup_theme()

    def selected_option(self) -> Optional[Dict[str, Any]]:
        data = self.currentData()
        if isinstance(data, dict):
            return data
        text = self.currentText().strip().lower()
        if not text or text == self.PLACEHOLDER.lower():
            return None
        for opt in self._options:
            label = str(opt.get("label") or opt.get("account_name") or "").strip().lower()
            if label == text:
                return opt
        return None

    def set_account_id(self, account_id: int) -> None:
        for index in range(self.count()):
            data = self.itemData(index)
            if isinstance(data, dict) and int(data.get("id") or 0) == int(account_id):
                self.setCurrentIndex(index)
                return
        for opt in self._options:
            try:
                if int(opt.get("id") or 0) == int(account_id):
                    label = str(opt.get("label") or opt.get("account_name") or "")
                    self.setCurrentText(label)
                    return
            except (TypeError, ValueError):
                continue

class OutstandingBillCombo(QComboBox):
    """Dropdown of pending sales/purchase bills for Tally-style bill allocation."""

    PLACEHOLDER = "Select Bill"
    EMPTY_PLACEHOLDER = "No pending bills"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bills: List[Dict[str, Any]] = []
        self.setMinimumWidth(170)
        self.setMaxVisibleItems(20)
        self.setStyleSheet(SearchAccountCombo.style_text())
        from ui import theme
        theme.apply_combo_dropdown_theme(self)

    def set_bills(self, bills: List[Dict[str, Any]], *, preserve_reference: str = "") -> None:
        """Load only pending bill options for the selected party."""
        current_ref = preserve_reference.strip() or self.bill_reference()
        pending_bills = [
            bill for bill in (bills or [])
            if round(float(bill.get("outstanding") or 0.0), 2) > 0.004
        ]
        self._bills = list(pending_bills)
        self.blockSignals(True)
        self.clear()
        if not self._bills:
            self.addItem(self.EMPTY_PLACEHOLDER, None)
            self.setCurrentIndex(0)
            self.blockSignals(False)
            return
        self.addItem(self.PLACEHOLDER, None)
        for bill in self._bills:
            bill_number = str(bill.get("bill_number") or "").strip()
            display_date = format_display_date(bill.get("display_date") or "")
            outstanding = float(bill.get("outstanding") or 0.0)
            label = f"{bill_number} | {display_date} | Bal {outstanding:.2f}"
            self.addItem(label, bill)
        if current_ref:
            matched = False
            for index in range(self.count()):
                data = self.itemData(index)
                if isinstance(data, dict) and str(data.get("bill_number") or "").strip().lower() == current_ref.lower():
                    self.setCurrentIndex(index)
                    matched = True
                    break
            if not matched and preserve_reference.strip():
                self.addItem(
                    f"{current_ref} | saved",
                    {"bill_number": current_ref, "outstanding": 0.0},
                )
                self.setCurrentIndex(self.count() - 1)
        else:
            self.setCurrentIndex(0)
        self.blockSignals(False)

    def selected_bill(self) -> Optional[Dict[str, Any]]:
        """Return the currently selected outstanding bill payload."""
        data = self.currentData()
        return data if isinstance(data, dict) else None

    def bill_reference(self) -> str:
        """Return the bill number stored on the current selection."""
        bill = self.selected_bill()
        if bill:
            return str(bill.get("bill_number") or "").strip()
        text = self.currentText().strip()
        if not text or text.lower() in {self.PLACEHOLDER.lower(), self.EMPTY_PLACEHOLDER.lower()}:
            return ""
        if " | " in text:
            return text.split(" | ", 1)[0].strip()
        if text.endswith(" | saved"):
            return text[:-8].strip()
        return text

class VoucherGridRowDelegate(QStyledItemDelegate):
    """Draw Sales Entry-style row outline when SL No is clicked."""

    def __init__(self, page: "VoucherGridPage"):
        super().__init__(page.table)
        self.page = page

    def paint(self, painter, option, index):
        """Paint cell content and optional row-outline selection."""
        from ui import theme

        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.State_Selected
        super().paint(painter, clean_option, index)

        if getattr(self.page, "manually_selected_row", -1) != index.row():
            return

        table = self.page.table
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


class VoucherKeyFilter(QObject):
    """Enter/Esc navigation helper for table cell widgets."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page

    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return False
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.page.move_from_widget(obj, 1)
            return True
        if key == Qt.Key_Escape:
            self.page.move_from_widget(obj, -1)
            return True
        return False

class VoucherGridPage(UiMemoryMixin, QWidget):
    """Common page for cash/bank receipt/payment voucher grid."""

    def __init__(self, db, voucher_type: str, title: str, parent=None):
        super().__init__(parent)
        self.db = db
        self.voucher_type = voucher_type
        self.title_text = title
        self.logic = CashBankVoucherLogic(db)
        self.logic.ensure_schema()
        self.company_id = None
        self.current_voucher_id: Optional[int] = None
        self.current_voucher_index: int = -1
        self.vouchers: List[Dict[str, Any]] = []
        self.main_account_type = 'general'
        self.active_tab = 'general'
        self.is_bill_mode = False
        self.row_widgets: Dict[int, Dict[str, Any]] = {}
        self.manually_selected_row = -1
        self.key_filter = VoucherKeyFilter(self)
        self.is_receipt = voucher_type.endswith('receipt')
        self.is_bank = voucher_type.startswith('bank')
        self.discount_allowed = self.is_receipt
        self._build_ui()
        self._init_ui_memory()
        self.prepare_fresh()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {_style()['bg']}; color: {_style()['text']};")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(5)
        title = QLabel(self.title_text)
        s = _style()
        from ui import theme
        c = theme._theme_colors()
        title.setStyleSheet(f"color: {c['heading_text']}; font-size: 18px; font-weight: bold; background: {c['panel_bg']}; border: 1px solid {s['border']}; border-radius: 4px; padding: 5px;")
        root.addWidget(title)
        tab_row = QHBoxLayout()
        self.tab_buttons = []
        for text, value in [('General A/C', 'general'), ('Debtor A/C', 'debtor'), ('Creditor A/C', 'creditor'), ('Bill Receipt' if self.is_receipt else 'Bill Payment', 'bill')]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, v=value: self.set_main_account_type(v))
            btn.setStyleSheet(self.button_style('tab'))
            btn.setMinimumHeight(28)
            btn.setMinimumWidth(100)
            tab_row.addWidget(btn)
            self.tab_buttons.append((btn, value))
        tab_row.addStretch()
        root.addLayout(tab_row)
        header = QFrame()
        header.setStyleSheet(self.top_bar_style())
        h = QHBoxLayout(header)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(4)
        h.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.txt_voucher_no = self.make_line(70)
        self.btn_previous = QPushButton('▲')
        self.btn_previous.setObjectName('voucherNextButton')
        self.btn_next = QPushButton('▼')
        self.btn_next.setObjectName('voucherPreviousButton')
        for nav_btn in (self.btn_previous, self.btn_next):
            nav_btn.setFixedSize(18, 11)
            nav_btn.setStyleSheet(self.nav_button_style())
            nav_btn.setFocusPolicy(Qt.NoFocus)
        self.btn_previous.setToolTip('Next voucher')
        self.btn_next.setToolTip('Previous voucher')
        self.date_voucher = QDateEdit()
        self.date_voucher.setDate(QDate.currentDate())
        prepare_report_date_edit(self.date_voucher, style_sheet=self.input_style())
        self.combo_money_account = SearchAccountCombo()
        self.combo_money_account.setMinimumWidth(180)
        self.combo_money_account.setMaximumWidth(200)
        self.combo_money_account.setStyleSheet(self.combo_input_style())
        self.combo_money_account.currentIndexChanged.connect(self.update_money_balance)
        install_click_select_all(self.combo_money_account)
        self.lbl_money_balance = self.make_balance_label(110)
        voucher_box = QHBoxLayout()
        voucher_box.setSpacing(1)
        voucher_box.setContentsMargins(0, 0, 0, 0)
        voucher_box.addWidget(self.txt_voucher_no)
        nav_container = QWidget()
        nav_container.setFixedWidth(18)
        arrow_box = QVBoxLayout(nav_container)
        arrow_box.setContentsMargins(0, 0, 0, 0)
        arrow_box.setSpacing(1)
        arrow_box.addWidget(self.btn_previous)
        arrow_box.addWidget(self.btn_next)
        voucher_box.addWidget(nav_container)
        from ui import theme
        self.btn_header_reset = QPushButton('Reset')
        self.btn_header_reset.setStyleSheet(theme.sales_compact_button_style())
        self.btn_header_reset.setFixedWidth(50)
        self.btn_header_reset.clicked.connect(self.prepare_fresh)
        voucher_box.addWidget(self.btn_header_reset)
        self.add_inline_labeled(h, 'Voucher No', voucher_box, maximum_width=220)
        self.add_inline_labeled(h, 'Date', self.date_voucher, maximum_width=155)
        self.add_inline_labeled(h, 'Bank Account' if self.is_bank else 'Cash Account', self.combo_money_account, maximum_width=300)
        self.add_inline_labeled(h, 'Bank Balance' if self.is_bank else 'Cash Balance', self.lbl_money_balance, maximum_width=215)
        self.txt_remark = self.make_expanding_line(150)
        install_click_select_all(self.txt_remark)
        self.add_inline_labeled(h, 'Remark', self.txt_remark, stretch=1)
        root.addWidget(header)
        self.table = QTableWidget()
        cols = ['SL No', 'Account', 'Towards V.No.', 'Amount']
        if self.discount_allowed:
            cols.append('Discount')
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setVisible(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(True)
        self.table.setStyleSheet(self.table_style())
        self.table.setItemDelegate(VoucherGridRowDelegate(self))
        self.table.viewport().installEventFilter(self)
        self.table.setMinimumHeight(230)
        self.table.setColumnWidth(0, 52)
        self.table.setColumnWidth(1, 230)
        self.table.setColumnWidth(2, 170)
        self.table.setColumnWidth(3, 150)
        if self.discount_allowed:
            self.table.setColumnWidth(4, 110)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        if self.discount_allowed:
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setFocusPolicy(Qt.StrongFocus)
        root.addWidget(self.table, 1)
        summary = QFrame()
        summary.setStyleSheet(self.panel_style())
        s = QHBoxLayout(summary)
        s.setContentsMargins(8, 6, 8, 6)
        s.setSpacing(18)
        self.lbl_account_balance = self.make_balance_label(130)
        self.lbl_balance_after = self.make_balance_label(130)
        self.lbl_total = self.make_balance_label(115)
        self.lbl_discount = self.make_balance_label(105)
        self.add_labeled(s, 'Acc Balance', self.lbl_account_balance)
        self.add_labeled(s, 'Balance After', self.lbl_balance_after)
        self.add_labeled(s, 'Total', self.lbl_total)
        if self.discount_allowed:
            self.add_labeled(s, 'Discount', self.lbl_discount)
        s.addStretch()
        root.addWidget(summary)
        buttons = QHBoxLayout()
        self.btn_add = QPushButton('Add Account')
        self.btn_add.setToolTip('Open Chart of Accounts (Masters)')
        self.btn_add_line = QPushButton('Add Line')
        self.btn_remove_line = QPushButton('Remove Account')
        self.btn_reset = QPushButton('Reset All')
        self.btn_save = QPushButton('OK / Save')
        self.btn_print = QPushButton('Print')
        self.btn_delete = QPushButton('Remove Voucher')
        self.btn_exit = QPushButton('Exit')
        button_styles = [(self.btn_add, 'primary'), (self.btn_add_line, 'secondary'), (self.btn_remove_line, 'warning'), (self.btn_reset, 'secondary'), (self.btn_save, 'success'), (self.btn_print, 'primary'), (self.btn_delete, 'danger'), (self.btn_exit, 'secondary')]
        for btn, kind in button_styles:
            btn.setStyleSheet(self.button_style(kind))
            btn.setMinimumHeight(34)
        for btn in (self.btn_add, self.btn_add_line, self.btn_remove_line, self.btn_reset):
            buttons.addWidget(btn)
        buttons.addStretch()
        for btn in (self.btn_exit, self.btn_delete, self.btn_print, self.btn_save):
            buttons.addWidget(btn)
        root.addLayout(buttons)
        self.btn_add.clicked.connect(self.open_chart_of_accounts)
        self.btn_add_line.clicked.connect(lambda: self.add_row(focus=True))
        self.btn_remove_line.clicked.connect(self.remove_selected_row)
        self.btn_reset.clicked.connect(self.prepare_fresh)
        self.btn_save.clicked.connect(self.save_or_update)
        self.btn_print.clicked.connect(self.print_voucher)
        self.btn_delete.clicked.connect(self.delete_current)
        self.btn_previous.clicked.connect(self.load_next)
        self.btn_next.clicked.connect(self.load_previous)
        self.btn_exit.clicked.connect(self.close_window)

    def add_inline_labeled(self, layout, label: str, widget, stretch: int=0, maximum_width: Optional[int]=None):
        """Add a compact Sales-style label and field group to the top bar."""
        container = QWidget()
        container.setStyleSheet('background: transparent; border: none;')
        container.setSizePolicy(QSizePolicy.Expanding if stretch else QSizePolicy.Maximum, QSizePolicy.Fixed)
        if maximum_width is not None:
            container.setMaximumWidth(maximum_width)
        box = QHBoxLayout()
        box.setSpacing(2)
        box.setContentsMargins(0, 0, 0, 0)
        container.setLayout(box)
        lab = QLabel(label)
        lab.setStyleSheet(self.micro_label_style())
        box.addWidget(lab)
        if isinstance(widget, QHBoxLayout):
            box.addLayout(widget)
        else:
            box.addWidget(widget, stretch)
        layout.addWidget(container, stretch)

    def add_labeled(self, layout, label: str, widget):
        box = QVBoxLayout()
        box.setSpacing(3)
        lab = QLabel(label)
        lab.setStyleSheet(f"color: {_style()['label']}; font-weight: bold; background: transparent;")
        box.addWidget(lab)
        if isinstance(widget, QHBoxLayout):
            box.addLayout(widget)
        else:
            box.addWidget(widget)
        layout.addLayout(box)

    def make_line(self, width: int) -> QLineEdit:
        line = QLineEdit()
        line.setFixedWidth(width)
        line.setStyleSheet(self.input_style())
        return line

    def make_expanding_line(self, minimum_width: int) -> QLineEdit:
        """Create a top-bar line edit that receives leftover horizontal space."""
        line = QLineEdit()
        line.setMinimumWidth(minimum_width)
        line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        line.setStyleSheet(self.input_style())
        return line

    def make_balance_label(self, width: int) -> QLabel:
        label = QLabel('0.00 Dr')
        label.setFixedWidth(width)
        label.setStyleSheet(self.balance_label_style())
        return label

    @staticmethod
    def input_style() -> str:
        from ui import theme
        return theme.sales_compact_input_style()

    @staticmethod
    def combo_input_style() -> str:
        from ui import theme
        return theme.sales_compact_input_style()

    @staticmethod
    def micro_label_style() -> str:
        from ui import theme
        return theme.sales_micro_label_style()

    @staticmethod
    def balance_label_style() -> str:
        from ui import theme
        return theme.entry_footer_input_readonly_style() + ' QLabel { color: ' + theme._theme_colors()['focus_border'] + '; }'

    @staticmethod
    def nav_button_style() -> str:
        from ui import theme
        return theme.sales_nav_button_style()

    @staticmethod
    def top_bar_style() -> str:
        from ui import theme
        return theme.entry_command_strip_style()

    @staticmethod
    def panel_style() -> str:
        return f"background-color: {_style()['panel']}; border: 1px solid {_style()['border']}; border-radius: 6px;"

    @staticmethod
    def table_style() -> str:
        from ui import theme
        return theme.voucher_grid_table_style()

    @staticmethod
    def button_style(kind: str) -> str:
        colors = {'primary': _style()['blue'], 'success': _style()['green'], 'danger': _style()['red'], 'warning': _style()['orange'], 'secondary': '#475569', 'tab': '#334155'}
        bg = colors.get(kind, '#475569')
        return f"QPushButton {{ background-color: {bg}; color: white; border: none; border-radius: 6px; padding: 6px 12px; font-weight: bold; }} QPushButton:checked {{ background-color: {_style()['blue']}; color: #07111f; }} QPushButton:hover {{ background-color: #2563eb; }}"

    def resolve_company(self) -> Optional[int]:
        cid = active_company_manager.get_active_company_id()
        return int(cid) if cid else None

    def prepare_fresh(self):
        self.company_id = self.resolve_company()
        if not self.company_id:
            return
        self.logic.ensure_schema()
        self.logic.ensure_system_accounts(self.company_id)
        self.current_voucher_id = None
        self.current_voucher_index = -1
        self.manually_selected_row = -1
        self.btn_save.setText('OK / Save')
        self.txt_voucher_no.setText(self.logic.get_next_voucher_no(self.company_id, self.voucher_type))
        self.date_voucher.setDate(QDate.currentDate())
        self.txt_remark.clear()
        self.load_money_accounts()
        self.set_main_account_type('general')
        self.table.setRowCount(0)
        self.row_widgets.clear()
        self.add_row(focus=False)
        self.update_totals()
        self.load_voucher_index()

    def load_money_accounts(self):
        accounts = self.logic.get_money_accounts(self.company_id, self.voucher_type)
        options = [{'id': int(a['id']), 'label': a['account_name'], 'kind': 'money', 'party_id': None} for a in accounts]
        self.combo_money_account.set_options(options)
        if options:
            self.combo_money_account.set_account_id(int(options[0]['id']))
        self.update_money_balance()

    def set_main_account_type(self, main_type: str):
        """Switch account tab and refresh row selectors (including bill allocation mode)."""
        self.active_tab = main_type
        self.is_bill_mode = main_type == 'bill'
        if self.is_bill_mode:
            self.main_account_type = 'debtor' if self.is_receipt else 'creditor'
        else:
            self.main_account_type = main_type
        for btn, value in self.tab_buttons:
            btn.setChecked(value == main_type)
        header_item = self.table.horizontalHeaderItem(2)
        if header_item is not None:
            header_item.setText('Outstanding Bill' if self.is_bill_mode else 'Towards V.No.')
        if not self.company_id:
            return
        options = self.logic.get_account_options(
            self.company_id,
            self.main_account_type,
            voucher_type=self.voucher_type,
            bill_mode=self.is_bill_mode,
        )
        for row in range(self.table.rowCount()):
            combo = self.row_widgets.get(row, {}).get('account')
            if combo:
                combo.set_options(options, preserve_text=True)
            self._refresh_row_towards_widget(row)
        self.update_totals()

    def _resolve_main_window(self):
        """Find MainWindow so standalone voucher windows can open Masters pages."""
        current = self.window()
        while current is not None:
            if hasattr(current, 'show_account_creation'):
                return current
            current = current.parentWidget() if hasattr(current, 'parentWidget') else None
        return None

    def open_chart_of_accounts(self) -> None:
        """Open Chart of Accounts in Masters from receipt/payment pages."""
        main_window = self._resolve_main_window()
        if main_window is None:
            QMessageBox.warning(self, 'Chart of Accounts', 'Could not open Masters from this window.')
            return
        main_window.show_account_creation()

    def _towards_text_from_widget(self, widget) -> str:
        """Read towards/bill reference text from line edit or bill combo."""
        if widget is None:
            return ''
        if isinstance(widget, OutstandingBillCombo):
            return widget.bill_reference()
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        return ''

    def _create_towards_widget(self, row: int):
        """Create towards field as free text or outstanding-bill picker."""
        if self.is_bill_mode:
            combo = OutstandingBillCombo()
            self._prepare_voucher_cell_widget(combo)
            combo.currentIndexChanged.connect(lambda _=None, r=row: self._on_bill_selected(r))
            return combo
        towards = QLineEdit()
        towards.setAlignment(Qt.AlignVCenter)
        towards.setPlaceholderText('Voucher no...')
        self._prepare_voucher_cell_widget(towards)
        return towards

    def _refresh_row_towards_widget(self, row: int) -> None:
        """Swap towards widget when switching between bill allocation and other tabs."""
        widgets = self.row_widgets.get(row, {})
        old_widget = widgets.get('towards')
        preserved_text = self._towards_text_from_widget(old_widget)
        new_widget = self._create_towards_widget(row)
        self.table.setCellWidget(row, 2, new_widget)
        widgets['towards'] = new_widget
        self.row_widgets[row] = widgets
        if self.is_bill_mode:
            combo = widgets.get('account')
            opt = combo.selected_option() if combo else None
            party_id = int(opt.get('party_id') or 0) if opt else 0
            if isinstance(new_widget, OutstandingBillCombo):
                bills = []
                if party_id:
                    bills = (
                        self.logic.get_outstanding_sales_bills(
                            self.company_id,
                            party_id,
                            exclude_voucher_type=self.voucher_type,
                            exclude_voucher_id=self.current_voucher_id,
                        )
                        if self.is_receipt
                        else self.logic.get_outstanding_purchase_bills(
                            self.company_id,
                            party_id,
                            exclude_voucher_type=self.voucher_type,
                            exclude_voucher_id=self.current_voucher_id,
                        )
                    )
                new_widget.set_bills(bills, preserve_reference=preserved_text)
        elif preserved_text and isinstance(new_widget, QLineEdit):
            new_widget.setText(preserved_text)

    def _on_row_account_changed(self, row: int) -> None:
        """Reload outstanding bills when the party/account changes in bill mode."""
        if not self.is_bill_mode or not self.company_id:
            self.update_totals()
            return
        widgets = self.row_widgets.get(row, {})
        combo = widgets.get('account')
        towards = widgets.get('towards')
        opt = combo.selected_option() if combo else None
        party_id = int(opt.get('party_id') or 0) if opt else 0
        if isinstance(towards, OutstandingBillCombo):
            bills = []
            if party_id:
                bills = (
                    self.logic.get_outstanding_sales_bills(
                        self.company_id,
                        party_id,
                        exclude_voucher_type=self.voucher_type,
                        exclude_voucher_id=self.current_voucher_id,
                    )
                    if self.is_receipt
                    else self.logic.get_outstanding_purchase_bills(
                        self.company_id,
                        party_id,
                        exclude_voucher_type=self.voucher_type,
                        exclude_voucher_id=self.current_voucher_id,
                    )
                )
            towards.set_bills(bills)
        self.update_totals()

    def _on_bill_selected(self, row: int) -> None:
        """Auto-fill receipt/payment amount with the selected bill balance."""
        if not self.is_bill_mode:
            return
        widgets = self.row_widgets.get(row, {})
        towards = widgets.get('towards')
        amount_widget = widgets.get('amount')
        if not isinstance(towards, OutstandingBillCombo) or amount_widget is None:
            return
        bill = towards.selected_bill()
        if not bill:
            self.update_totals()
            return
        outstanding = float(bill.get('outstanding') or 0.0)
        current_amount = amount_to_float(amount_widget.text())
        if current_amount <= 0.004 and outstanding > 0:
            amount_widget.setText(f'{outstanding:.2f}')
        self.update_totals()

    def _refresh_sl_numbers(self) -> None:
        """Refresh serial numbers shown in the first grid column."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(row, 0, item)
            item.setText(str(row + 1))

    def _prepare_voucher_cell_widget(self, widget) -> None:
        """Make embedded grid widgets flush like Sales Entry cells."""
        from ui import theme

        widget.setContentsMargins(0, 0, 0, 0)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        widget.setMinimumHeight(0)
        if isinstance(widget, QLineEdit):
            widget.setMinimumWidth(0)
            theme.prepare_voucher_grid_cell_line_edit(widget)
            widget.installEventFilter(self.key_filter)
            install_click_select_all(widget)
            return
        if isinstance(widget, QComboBox):
            widget.setMinimumWidth(0)
            theme.prepare_voucher_grid_cell_combo(widget)
            widget.installEventFilter(self.key_filter)
            install_click_select_all(widget)

    def add_row(self, focus: bool=False, data: Optional[Dict[str, Any]]=None):
        row = self.table.rowCount()
        self.table.insertRow(row)
        selector = QTableWidgetItem(str(row + 1))
        selector.setTextAlignment(Qt.AlignCenter)
        selector.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.setItem(row, 0, selector)
        account = SearchAccountCombo()
        account.set_options(
            self.logic.get_account_options(
                self.company_id,
                self.main_account_type,
                voucher_type=self.voucher_type,
                bill_mode=self.is_bill_mode,
            ) if self.company_id else []
        )
        towards = self._create_towards_widget(row)
        amount = QLineEdit()
        discount = QLineEdit()
        self._prepare_voucher_cell_widget(account)
        for widget in (amount, discount):
            self._prepare_voucher_cell_widget(widget)
        amount.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        discount.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        amount.setPlaceholderText('0.00')
        discount.setPlaceholderText('0.00')
        account.currentIndexChanged.connect(lambda _=None, r=row: self._on_row_account_changed(r))
        account.lineEdit().textEdited.connect(lambda _=None: QTimer.singleShot(0, self.update_totals))
        amount.textChanged.connect(self.update_totals)
        discount.textChanged.connect(self.update_totals)
        self.table.setCellWidget(row, 1, account)
        self.table.setCellWidget(row, 2, towards)
        self.table.setCellWidget(row, 3, amount)
        if self.discount_allowed:
            self.table.setCellWidget(row, 4, discount)
        self.row_widgets[row] = {'account': account, 'towards': towards, 'amount': amount, 'discount': discount}
        if data:
            account.set_account_id(int(data.get('account_id') or 0))
            towards_ref = str(data.get('towards_voucher_no') or data.get('towards_acc') or '')
            if isinstance(towards, OutstandingBillCombo):
                opt = account.selected_option()
                party_id = int(opt.get('party_id') or 0) if opt else 0
                bills: List[Dict[str, Any]] = []
                if party_id and self.company_id:
                    bills = (
                        self.logic.get_outstanding_sales_bills(
                            self.company_id,
                            party_id,
                            exclude_voucher_type=self.voucher_type,
                            exclude_voucher_id=self.current_voucher_id,
                        )
                        if self.is_receipt
                        else self.logic.get_outstanding_purchase_bills(
                            self.company_id,
                            party_id,
                            exclude_voucher_type=self.voucher_type,
                            exclude_voucher_id=self.current_voucher_id,
                        )
                    )
                towards.set_bills(bills, preserve_reference=towards_ref)
            elif isinstance(towards, QLineEdit):
                towards.setText(towards_ref)
            amount.setText(f"{amount_to_float(data.get('amount')):.2f}")
            discount.setText(f"{amount_to_float(data.get('discount')):.2f}")
        self._refresh_sl_numbers()
        if focus:
            account.setFocus()
            line_edit = account.lineEdit()
            if line_edit is not None:
                line_edit.selectAll()
        self.update_totals()

    def rebuild_row_widget_map(self):
        self.row_widgets = {}
        for row in range(self.table.rowCount()):
            self.row_widgets[row] = {'account': self.table.cellWidget(row, 1), 'towards': self.table.cellWidget(row, 2), 'amount': self.table.cellWidget(row, 3), 'discount': self.table.cellWidget(row, 4) if self.discount_allowed else QLineEdit()}

    def remove_selected_row(self):
        """Remove a grid row only after the user clicks its SL No (Sales Entry pattern)."""
        target_row = getattr(self, "manually_selected_row", -1)
        if target_row < 0:
            QMessageBox.information(
                self,
                "Remove Account",
                "Please click the SL No of the account you want to remove, then press Remove Account.",
            )
            return
        if target_row >= self.table.rowCount():
            self.manually_selected_row = -1
            return
        reply = QMessageBox.question(
            self,
            "Remove Account",
            f"Are you sure you want to remove account at row {target_row + 1}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.table.removeRow(target_row)
        self.manually_selected_row = -1
        self.table.clearSelection()
        self.table.viewport().update()
        self.rebuild_row_widget_map()
        self._refresh_sl_numbers()
        if self.table.rowCount() == 0:
            self.add_row(focus=False)
        self.update_totals()

    def _focus_row_widget(self, row: int, column: int) -> None:
        """Focus an embedded cell widget and select all text for immediate overwrite."""
        widget = self.table.cellWidget(row, column)
        if widget is None:
            return
        widget.setFocus()
        if isinstance(widget, QLineEdit):
            QTimer.singleShot(0, widget.selectAll)
            return
        if isinstance(widget, OutstandingBillCombo):
            QTimer.singleShot(0, widget.showPopup)
            return
        if isinstance(widget, QComboBox):
            line_edit = widget.lineEdit()
            if line_edit is not None:
                QTimer.singleShot(0, line_edit.selectAll)

    def eventFilter(self, obj, event):
        """Handle SL No row selection and one-click cell editing like Sales Entry."""
        if obj == self.table.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                item = self.table.itemAt(event.pos())
                if item is not None and item.column() == 0:
                    self.manually_selected_row = item.row()
                    self.table.clearSelection()
                    self.table.viewport().update()
                    return True
                index = self.table.indexAt(event.pos())
                if index.isValid():
                    clicked_row = index.row()
                    clicked_column = index.column()
                    if clicked_column == 0:
                        self.manually_selected_row = clicked_row
                        self.table.clearSelection()
                        self.table.viewport().update()
                        return True
                    self.manually_selected_row = -1
                    self.table.clearSelection()
                    self.table.viewport().update()
                    self._focus_row_widget(clicked_row, clicked_column)
                    return True
        return super().eventFilter(obj, event)

    def ordered_widgets(self) -> List[Any]:
        widgets = []
        for row in range(self.table.rowCount()):
            w = self.row_widgets.get(row, {})
            widgets.extend([w.get('account'), w.get('towards'), w.get('amount')])
            if self.discount_allowed:
                widgets.append(w.get('discount'))
        return [w for w in widgets if w is not None]

    def move_from_widget(self, widget, direction: int):
        widgets = self.ordered_widgets()
        try:
            index = widgets.index(widget)
        except ValueError:
            return
        next_index = index + direction
        if direction > 0 and next_index >= len(widgets):
            self.add_row(focus=False)
            widgets = self.ordered_widgets()
        if 0 <= next_index < len(widgets):
            target = widgets[next_index]
            target.setFocus()
        if isinstance(target, QLineEdit):
            target.selectAll()
        elif isinstance(target, QComboBox):
            line_edit = target.lineEdit()
            if line_edit is not None:
                line_edit.selectAll()
            elif isinstance(target, OutstandingBillCombo):
                target.showPopup()
            else:
                target.showPopup()
        self.update_totals()

    def selected_money_account_id(self) -> Optional[int]:
        opt = self.combo_money_account.selected_option()
        return int(opt['id']) if opt and opt.get('id') else None

    def collect_items(self) -> List[Dict[str, Any]]:
        items = []
        for row in range(self.table.rowCount()):
            w = self.row_widgets.get(row, {})
            combo = w.get('account')
            opt = combo.selected_option() if combo else None
            amount = amount_to_float(w.get('amount').text() if w.get('amount') else '0')
            discount = amount_to_float(w.get('discount').text() if w.get('discount') else '0') if self.discount_allowed else 0.0
            if opt and amount > 0:
                account_kind = 'bill' if self.is_bill_mode else (opt.get('kind') or self.main_account_type)
                items.append({
                    'account_id': opt.get('id'),
                    'party_id': opt.get('party_id'),
                    'account_kind': account_kind,
                    'towards_voucher_no': self._towards_text_from_widget(w.get('towards')),
                    'amount': amount,
                    'discount': discount,
                    'narration': self.txt_remark.text().strip(),
                })
        return items

    def update_money_balance(self):
        if not self.company_id:
            return
        opt = self.combo_money_account.selected_option()
        account_id = int(opt.get('ledger_account_id') or opt.get('id') or 0) if opt else 0
        bal = self.logic.get_account_balance(self.company_id, account_id) if account_id else 0.0
        self.lbl_money_balance.setText(self.logic.format_balance(bal))
        self.update_totals()

    def update_totals(self):
        if not self.company_id:
            return
        items = self.collect_items()
        total = round(sum((i.get('amount', 0.0) for i in items)), 2)
        discount = round(sum((i.get('discount', 0.0) for i in items)), 2)
        self.lbl_total.setText(f'{total:.2f}')
        self.lbl_discount.setText(f'{discount:.2f}')
        row = self.table.currentRow()
        if row < 0 and self.table.rowCount() > 0:
            row = 0
        account_balance = 0.0
        if row >= 0:
            combo = self.row_widgets.get(row, {}).get('account')
            opt = combo.selected_option() if combo else None
            if opt and opt.get('id'):
                account_balance = self.logic.get_account_balance(self.company_id, int(opt['id']))
        row_widgets = self.row_widgets.get(row, {}) if row >= 0 else {}
        row_amount = amount_to_float(row_widgets.get('amount').text()) if row_widgets.get('amount') else 0.0
        row_discount = amount_to_float(row_widgets.get('discount').text()) if row_widgets.get('discount') and self.discount_allowed else 0.0
        balance_after = account_balance - row_amount - row_discount if self.is_receipt else account_balance + row_amount
        self.lbl_account_balance.setText(self.logic.format_balance(account_balance))
        self.lbl_balance_after.setText(self.logic.format_balance(balance_after))

    def save_or_update(self):
        if not self.company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        header = {'voucher_no': self.txt_voucher_no.text().strip(), 'voucher_date': qdate_to_db(self.date_voucher.date()), 'money_account_id': self.selected_money_account_id(), 'remark': self.txt_remark.text().strip(), 'narration': self.txt_remark.text().strip()}
        result = self.logic.save_or_update_voucher(self.company_id, self.voucher_type, header, self.collect_items(), self.current_voucher_id)
        if not result.get('success'):
            QMessageBox.warning(self, 'Save Failed', result.get('message', 'Could not save voucher.'))
            return
        QMessageBox.information(self, 'Saved', 'Voucher saved successfully.')
        self.prepare_fresh()

    def print_voucher(self):
        """Print the current payment/receipt voucher through the A4 engine."""
        if not self.company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        items = self._payment_receipt_print_items()
        if not items:
            QMessageBox.warning(self, 'Print Voucher', 'Please enter at least one account row with amount.')
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'Print Voucher', 'Please open a company first.')
            return
        try:
            settings = get_print_settings(self.db, self.company_id)
            html_string = generate_payment_receipt_html(company_print_data(active_company), self._payment_receipt_print_data(items), items, settings=settings)
            dialog = UniversalPreviewDialog(html_string, mode='A4', parent=self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Could not print voucher:\n{exc}')

    def _payment_receipt_print_items(self) -> List[Dict[str, Any]]:
        """Collect visible voucher rows for payment/receipt HTML."""
        rows = []
        for item in self.collect_items():
            account_name = ''
            for row_widgets in self.row_widgets.values():
                combo = row_widgets.get('account')
                option = combo.selected_option() if combo else None
                if option and int(option.get('id') or 0) == int(item.get('account_id') or 0):
                    account_name = combo.currentText().strip()
                    break
            rows.append({'account_name': account_name or str(item.get('account_id') or ''), 'towards_voucher_no': item.get('towards_voucher_no', ''), 'amount': item.get('amount', 0.0), 'discount': item.get('discount', 0.0)})
        return rows

    def _payment_receipt_print_data(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Return header and totals for payment/receipt A4 HTML."""
        cfg = self.logic.VOUCHERS.get(self.voucher_type, {})
        total_amount = round(sum((amount_to_float(item.get('amount')) for item in items)), 2)
        total_discount = round(sum((amount_to_float(item.get('discount')) for item in items)), 2)
        first_account = items[0].get('account_name', '') if items else ''
        references = [str(item.get('towards_voucher_no') or '').strip() for item in items if str(item.get('towards_voucher_no') or '').strip()]
        return {'voucher_title': cfg.get('voucher_title') or self.title_text, 'party_label': cfg.get('party_label', 'Account').replace('_', ' ').title(), 'party_name': first_account, 'voucher_no': self.txt_voucher_no.text().strip(), 'voucher_date': qdate_to_display(self.date_voucher.date()), 'payment_mode': 'Bank' if self.is_bank else 'Cash', 'reference': ', '.join(references[:3]), 'total_amount': total_amount, 'total_discount': total_discount, 'net_amount': total_amount - total_discount, 'narration': self.txt_remark.text().strip()}

    def load_voucher_index(self):
        if not self.company_id:
            self.vouchers = []
            return
        self.vouchers = self.logic.list_vouchers(self.company_id, self.voucher_type)

    def load_previous(self):
        self.load_voucher_index()
        if not self.vouchers:
            QMessageBox.information(self, 'No Voucher', 'No saved voucher found.')
            return
        if self.current_voucher_id:
            ids = [int(v['id']) for v in self.vouchers]
            try:
                idx = ids.index(int(self.current_voucher_id)) - 1
            except ValueError:
                idx = len(self.vouchers) - 1
        else:
            idx = len(self.vouchers) - 1
        idx = max(0, min(idx, len(self.vouchers) - 1))
        self.load_voucher_by_id(int(self.vouchers[idx]['id']), idx)

    def load_next(self):
        self.load_voucher_index()
        if not self.vouchers:
            QMessageBox.information(self, 'No Voucher', 'No saved voucher found.')
            return
        if self.current_voucher_id:
            ids = [int(v['id']) for v in self.vouchers]
            try:
                idx = ids.index(int(self.current_voucher_id)) + 1
            except ValueError:
                idx = 0
        else:
            idx = 0
        idx = max(0, min(idx, len(self.vouchers) - 1))
        self.load_voucher_by_id(int(self.vouchers[idx]['id']), idx)

    def load_voucher_by_id(self, voucher_id: int, index: int=-1):
        if not self.company_id:
            self.company_id = self.resolve_company()
        result = self.logic.load_voucher(self.company_id, self.voucher_type, voucher_id)
        if not result.get('success'):
            QMessageBox.warning(self, 'Load Failed', result.get('message', 'Could not load voucher.'))
            return
        header = result.get('header', {})
        self.current_voucher_id = voucher_id
        self.current_voucher_index = index
        self.btn_save.setText('Update')
        self.txt_voucher_no.setText(str(header.get('voucher_no') or ''))
        qdate = QDate.fromString(str(header.get('voucher_date') or ''), 'yyyy-MM-dd')
        self.date_voucher.setDate(qdate if qdate.isValid() else QDate.currentDate())
        self.txt_remark.setText(str(header.get('remark') or header.get('narration') or ''))
        money_field = self.logic.VOUCHERS[self.voucher_type]['money_field']
        self.combo_money_account.set_account_id(int(header.get(money_field) or 0))
        self.table.setRowCount(0)
        self.row_widgets.clear()
        items = result.get('items', [])
        kind = str(items[0].get('account_kind') or '').lower() if items else ''
        if kind == 'bill':
            self.set_main_account_type('bill')
        elif kind in ('debtor', 'creditor'):
            self.set_main_account_type(kind)
        else:
            self.set_main_account_type('general')
        for item in items:
            self.add_row(focus=False, data=item)
        if self.table.rowCount() == 0:
            self.add_row(focus=False)
        self.update_totals()

    def delete_current(self):
        if not self.current_voucher_id:
            QMessageBox.information(self, 'No Voucher', 'Please load a saved voucher first.')
            return
        if QMessageBox.question(self, 'Confirm Delete', 'Remove this voucher?') != QMessageBox.Yes:
            return
        result = self.logic.delete_voucher(self.company_id, self.voucher_type, self.current_voucher_id)
        if not result.get('success'):
            QMessageBox.warning(self, 'Delete Failed', result.get('message', 'Could not delete voucher.'))
            return
        QMessageBox.information(self, 'Deleted', 'Voucher removed.')
        self.prepare_fresh()

    def close_window(self):
        window = self.window()
        if window:
            window.close()