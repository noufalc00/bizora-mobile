"""
Account Creation Page

Tabbed UI for creating ledger accounts and account groups.
MVC Pattern: UI only collects user input and passes to AccountCreationEngine.
Compact Ledger-style layout matching existing app design.
"""
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QTabWidget, QFrame, QMessageBox, QDialog, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSizePolicy, QCompleter,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from config import active_company_manager
from bizora_core.account_creation_engine import AccountCreationEngine
from ui import theme
from ui.book_report_common import compact_label_style, compact_input_style, compact_primary_button_style, compact_topbar_frame_style
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.entry_field_helpers import install_click_select_all, install_click_select_all_many
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

_SELECT_ACCOUNT_TYPE = "Select account type"
_SELECT_GROUP = "Select group"
_SELECT_PRIMARY_GROUP = "Select primary group"
_ACCOUNT_TYPE_OPTIONS = [
    "Party (Debtor/Creditor)",
    "Cash/Bank Account",
    "Income Account",
    "Expense Account",
    "Tax Liability (GST)",
    "Capital Account",
    "Stock Account",
]
_ACCOUNT_TYPE_MAPPING = {
    "Party (Debtor/Creditor)": "party",
    "Cash/Bank Account": "cash_bank",
    "Income Account": "income",
    "Expense Account": "expense",
    "Tax Liability (GST)": "tax_liability",
    "Capital Account": "capital",
    "Stock Account": "stock",
}
_ACCOUNT_TYPE_DISPLAY = {value: key for key, value in _ACCOUNT_TYPE_MAPPING.items()}


def _configure_placeholder_combo(combo: QComboBox, placeholder: str, options: list[str]) -> None:
    """Load a combo with a disabled placeholder row followed by real options."""
    combo.clear()
    combo.addItem(placeholder)
    combo.addItems(options)
    combo.setCurrentIndex(0)
    model = combo.model()
    if model is not None:
        placeholder_item = model.item(0)
        if placeholder_item is not None:
            placeholder_item.setEnabled(False)


def _is_placeholder_combo_value(combo: QComboBox, placeholder: str) -> bool:
    """Return True when the combo is still on its placeholder row or text."""
    if combo.currentIndex() <= 0:
        return True
    return (combo.currentText() or "").strip() == placeholder


def _normalized_group_selection(combo: QComboBox) -> str:
    """Return the selected group name, ignoring the placeholder label."""
    group_name = (combo.currentText() or "").strip()
    if not group_name or group_name == _SELECT_GROUP:
        return ""
    return group_name


def _resolve_combo_option(combo: QComboBox, placeholder: str, options: list[str]) -> str:
    """Return a valid option label from a searchable combo, or empty when unset."""
    text = (combo.currentText() or "").strip()
    if not text or text == placeholder:
        return ""
    index = combo.findText(text, Qt.MatchFlag.MatchExactly)
    if index > 0:
        return combo.itemText(index)
    lowered = text.lower()
    for option in options:
        if option.lower() == lowered:
            return option
    return ""


def _configure_searchable_placeholder_combo(
    combo: QComboBox,
    placeholder: str,
    options: list[str],
) -> QCompleter:
    """Load a type-to-search combo with a disabled placeholder row."""
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    _configure_placeholder_combo(combo, placeholder, options)

    completer = QCompleter(combo)
    completer.setModel(combo.model())
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    combo.setCompleter(completer)
    completer.activated.connect(lambda text: combo.setCurrentText(str(text or "")))

    line_edit = combo.lineEdit()
    if line_edit is not None:
        line_edit.setPlaceholderText(placeholder)
        install_click_select_all(line_edit)

    theme.apply_completer_popup_theme(completer)
    theme.apply_combo_dropdown_theme(combo)
    return completer


def _reset_searchable_combo(combo: QComboBox, placeholder: str) -> None:
    """Restore a searchable combo to its placeholder prompt."""
    combo.setCurrentIndex(0)
    line_edit = combo.lineEdit()
    if line_edit is not None:
        line_edit.clear()
        line_edit.setPlaceholderText(placeholder)

class CreateGroupDialog(UiMemoryMixin, QDialog):
    """Quick dialog to create a new account group."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.group_name = ''
        self._init_ui()
        self._init_ui_memory()

    def _init_ui(self):
        """Initialize the dialog UI."""
        self.setWindowTitle('Create Account Group')
        self.setModal(True)
        self.setFixedWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        label = QLabel('Group Name:')
        label.setStyleSheet(compact_label_style())
        layout.addWidget(label)
        self.group_name_edit = QLineEdit()
        self.group_name_edit.setStyleSheet(compact_input_style())
        self.group_name_edit.setPlaceholderText('e.g., Salary, Rent, Utilities')
        install_click_select_all(self.group_name_edit)
        layout.addWidget(self.group_name_edit)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.setStyleSheet(theme.sales_primary_button_style())
        layout.addWidget(button_box)

    def _capitalize_first_letter(self, text):
        """Auto-capitalize first letter of input."""
        if text:
            cursor_pos = self.group_name_edit.cursorPosition()
            capitalized = text[0].upper() + text[1:] if len(text) > 0 else text
            if text != capitalized:
                self.group_name_edit.blockSignals(True)
                self.group_name_edit.setText(capitalized)
                self.group_name_edit.setCursorPosition(cursor_pos)
                self.group_name_edit.blockSignals(False)

    def accept(self):
        """Validate and accept the dialog."""
        group_name = self.group_name_edit.text().strip()
        if not group_name:
            QMessageBox.warning(self, 'Validation Error', 'Group name cannot be empty.')
            return
        self.group_name = group_name
        super().accept()

class EditAccountDialog(UiMemoryMixin, QDialog):
    """Dialog to edit an existing ledger account."""

    def __init__(self, account_data: dict, parent=None):
        super().__init__(parent)
        self.account_data = account_data
        self.account_name = account_data.get('account_name', '')
        self.account_type = account_data.get('account_type', '')
        self.group_name = account_data.get('group_name', '')
        self.opening_balance = account_data.get('opening_balance', 0.0)
        self.balance_type = account_data.get('opening_balance_type', 'Dr')
        self.account_code = account_data.get('account_code', '')
        self._init_ui()
        self._init_ui_memory()

    def _init_ui(self):
        """Initialize the dialog UI."""
        self.setWindowTitle('Edit Account')
        self.setModal(True)
        self.setFixedWidth(450)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        name_label = QLabel('Account Name *')
        name_label.setStyleSheet(compact_label_style())
        layout.addWidget(name_label)
        self.name_edit = QLineEdit()
        self.name_edit.setStyleSheet(compact_input_style())
        self.name_edit.setText(self.account_name)
        self.name_edit.textChanged.connect(lambda: self._capitalize_first_letter_field(self.name_edit))
        install_click_select_all(self.name_edit)
        layout.addWidget(self.name_edit)
        type_label = QLabel('Account Type *')
        type_label.setStyleSheet(compact_label_style())
        layout.addWidget(type_label)
        self.type_combo = QComboBox()
        self.type_combo.setStyleSheet(compact_input_style())
        _configure_searchable_placeholder_combo(
            self.type_combo,
            _SELECT_ACCOUNT_TYPE,
            _ACCOUNT_TYPE_OPTIONS,
        )
        display_type = _ACCOUNT_TYPE_DISPLAY.get(self.account_type, self.account_type)
        index = self.type_combo.findText(display_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        layout.addWidget(self.type_combo)
        group_label = QLabel('Under Group')
        group_label.setStyleSheet(compact_label_style())
        layout.addWidget(group_label)
        self.group_edit = QLineEdit()
        self.group_edit.setStyleSheet(compact_input_style())
        self.group_edit.setText(self.group_name)
        self.group_edit.textChanged.connect(lambda: self._capitalize_first_letter_field(self.group_edit))
        install_click_select_all(self.group_edit)
        layout.addWidget(self.group_edit)
        balance_label = QLabel('Opening Balance')
        balance_label.setStyleSheet(compact_label_style())
        layout.addWidget(balance_label)
        balance_row = QHBoxLayout()
        self.balance_edit = QLineEdit()
        self.balance_edit.setStyleSheet(compact_input_style())
        self.balance_edit.setText(str(self.opening_balance))
        self.balance_edit.setFixedWidth(150)
        install_click_select_all(self.balance_edit)
        balance_row.addWidget(self.balance_edit)
        self.balance_type_combo = QComboBox()
        self.balance_type_combo.setStyleSheet(compact_input_style())
        self.balance_type_combo.addItems(['Dr', 'Cr'])
        self.balance_type_combo.setCurrentText(self.balance_type)
        self.balance_type_combo.setFixedWidth(60)
        theme.apply_combo_dropdown_theme(self.balance_type_combo)
        balance_row.addWidget(self.balance_type_combo)
        balance_row.addStretch()
        layout.addLayout(balance_row)
        code_label = QLabel('Account Code (Optional)')
        code_label.setStyleSheet(compact_label_style())
        layout.addWidget(code_label)
        self.code_edit = QLineEdit()
        self.code_edit.setStyleSheet(compact_input_style())
        self.code_edit.setText(self.account_code)
        self.code_edit.textChanged.connect(lambda: self._capitalize_first_letter_field(self.code_edit))
        install_click_select_all(self.code_edit)
        layout.addWidget(self.code_edit)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.setStyleSheet(theme.sales_primary_button_style())
        layout.addWidget(button_box)

    def _capitalize_first_letter_field(self, field):
        """Auto-capitalize first letter of input field."""
        text = field.text()
        if text:
            cursor_pos = field.cursorPosition()
            capitalized = text[0].upper() + text[1:] if len(text) > 0 else text
            if text != capitalized:
                field.blockSignals(True)
                field.setText(capitalized)
                field.setCursorPosition(cursor_pos)
                field.blockSignals(False)

    def accept(self):
        """Validate and accept the dialog."""
        self.account_name = self.name_edit.text().strip()
        if _is_placeholder_combo_value(self.type_combo, _SELECT_ACCOUNT_TYPE):
            QMessageBox.warning(self, 'Validation Error', 'Please select an account type.')
            return
        selected_type_label = _resolve_combo_option(
            self.type_combo,
            _SELECT_ACCOUNT_TYPE,
            _ACCOUNT_TYPE_OPTIONS,
        )
        if not selected_type_label:
            QMessageBox.warning(self, 'Validation Error', 'Please select a valid account type.')
            return
        self.group_name = self.group_edit.text().strip()
        balance_str = self.balance_edit.text().strip()
        self.balance_type = self.balance_type_combo.currentText()
        self.account_code = self.code_edit.text().strip()
        if not self.account_name:
            QMessageBox.warning(self, 'Validation Error', 'Account name is required.')
            return
        self.account_type = _ACCOUNT_TYPE_MAPPING.get(selected_type_label)
        try:
            self.opening_balance = float(balance_str) if balance_str else 0.0
        except ValueError:
            QMessageBox.warning(self, 'Validation Error', 'Opening balance must be a valid number.')
            return
        super().accept()

class AccountCreationPageWidget(UiMemoryMixin, QWidget):
    """Account creation page with tabbed layout for Ledger Accounts and Groups."""

    def __init__(self, db=None):
        super().__init__()
        self.db = db
        self.account_engine = AccountCreationEngine(self.db) if self.db else None
        self.company_id = active_company_manager.get_active_company_id()
        self._init_ui()
        self._load_data()
        self._init_ui_memory(table_attrs=("accounts_table",))
        self._load_accounts_table()

    def showEvent(self, event):
        """Refresh data when page is shown."""
        super().showEvent(event)
        self.company_id = active_company_manager.get_active_company_id()
        if self.company_id and (not self.account_engine):
            self.account_engine = AccountCreationEngine(self.db)
        self._load_data()
        self._load_accounts_table()

    def _init_ui(self):
        """Initialize the UI layout - compact Ledger style."""
        self.setStyleSheet(theme.master_page_background_style())
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        title = QLabel('Chart of Accounts')
        title.setStyleSheet(theme.master_page_title_style(24))
        main_layout.addWidget(title)
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(theme.master_tab_widget_style())
        self.ledger_account_tab = self._create_ledger_account_tab()
        self.tab_widget.addTab(self.ledger_account_tab, 'Create Ledger Account')
        self.account_group_tab = self._create_account_group_tab()
        self.tab_widget.addTab(self.account_group_tab, 'Create Account Group')
        self.view_accounts_tab = self._create_view_accounts_tab()
        self.tab_widget.addTab(self.view_accounts_tab, 'View/Edit Accounts')
        main_layout.addWidget(self.tab_widget, 1)
        install_click_select_all_many([
            self.account_name_edit,
            self.opening_balance_edit,
            self.account_code_edit,
            self.group_name_edit,
        ])

    def _create_ledger_account_tab(self) -> QWidget:
        """Create the ledger account creation tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_label = QLabel('Account Name *')
        name_label.setStyleSheet(compact_label_style())
        name_label.setFixedWidth(100)
        self.account_name_edit = QLineEdit()
        self.account_name_edit.setStyleSheet(compact_input_style())
        self.account_name_edit.setPlaceholderText('e.g., John Smith, HDFC Bank, Office Rent')
        self.account_name_edit.textChanged.connect(lambda: self._capitalize_first_letter_field(self.account_name_edit))
        self.account_name_edit.setFixedWidth(300)
        name_row.addWidget(name_label)
        name_row.addWidget(self.account_name_edit)
        name_row.addStretch()
        layout.addLayout(name_row)
        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        type_label = QLabel('Account Type *')
        type_label.setStyleSheet(compact_label_style())
        type_label.setFixedWidth(100)
        self.account_type_combo = QComboBox()
        self.account_type_combo.setStyleSheet(compact_input_style())
        _configure_searchable_placeholder_combo(
            self.account_type_combo,
            _SELECT_ACCOUNT_TYPE,
            _ACCOUNT_TYPE_OPTIONS,
        )
        self.account_type_combo.setFixedWidth(300)
        type_row.addWidget(type_label)
        type_row.addWidget(self.account_type_combo)
        type_row.addStretch()
        layout.addLayout(type_row)
        group_row = QHBoxLayout()
        group_row.setSpacing(8)
        group_label = QLabel('Under Group')
        group_label.setStyleSheet(compact_label_style())
        group_label.setFixedWidth(100)
        self.group_combo = QComboBox()
        self.group_combo.setStyleSheet(compact_input_style())
        self.group_combo.setFixedWidth(300)
        _configure_searchable_placeholder_combo(self.group_combo, _SELECT_GROUP, [])
        add_group_btn = QPushButton('Create Account Group')
        add_group_btn.setStyleSheet(theme.sales_compact_button_style())
        add_group_btn.clicked.connect(self._show_create_group_dialog)
        group_row.addWidget(group_label)
        group_row.addWidget(self.group_combo)
        group_row.addWidget(add_group_btn)
        group_row.addStretch()
        layout.addLayout(group_row)
        balance_row = QHBoxLayout()
        balance_row.setSpacing(8)
        balance_label = QLabel('Opening Balance')
        balance_label.setStyleSheet(compact_label_style())
        balance_label.setFixedWidth(100)
        self.opening_balance_edit = QLineEdit()
        self.opening_balance_edit.setStyleSheet(compact_input_style())
        self.opening_balance_edit.setPlaceholderText('0.00')
        self.opening_balance_edit.setFixedWidth(120)
        balance_row.addWidget(balance_label)
        balance_row.addWidget(self.opening_balance_edit)
        balance_row.addStretch()
        layout.addLayout(balance_row)
        code_row = QHBoxLayout()
        code_row.setSpacing(8)
        code_label = QLabel('Account Code')
        code_label.setStyleSheet(compact_label_style())
        code_label.setFixedWidth(100)
        optional_label = QLabel('(Optional)')
        optional_label.setStyleSheet(compact_label_style())
        optional_label.setFixedWidth(60)
        self.account_code_edit = QLineEdit()
        self.account_code_edit.setStyleSheet(compact_input_style())
        self.account_code_edit.setPlaceholderText('e.g., SAL-001, BNK-002')
        self.account_code_edit.textChanged.connect(lambda: self._capitalize_first_letter_field(self.account_code_edit))
        self.account_code_edit.setFixedWidth(300)
        code_row.addWidget(code_label)
        code_row.addWidget(optional_label)
        code_row.addWidget(self.account_code_edit)
        code_row.addStretch()
        layout.addLayout(code_row)
        layout.addStretch()
        create_btn = QPushButton('Create Ledger Account')
        create_btn.setStyleSheet(compact_primary_button_style())
        create_btn.clicked.connect(self._create_ledger_account)
        layout.addWidget(create_btn)
        return tab

    def _create_account_group_tab(self) -> QWidget:
        """Create the account group creation tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        name_label = QLabel('Group Name *')
        name_label.setStyleSheet(compact_label_style())
        name_label.setFixedWidth(120)
        layout.addWidget(name_label)
        self.group_name_edit = QLineEdit()
        self.group_name_edit.setStyleSheet(compact_input_style())
        self.group_name_edit.setPlaceholderText('e.g., Salary, Rent, Utilities')
        self.group_name_edit.textChanged.connect(lambda: self._capitalize_first_letter_field(self.group_name_edit))
        self.group_name_edit.setFixedWidth(250)
        layout.addWidget(self.group_name_edit)
        primary_label = QLabel('Under Primary Group *')
        primary_label.setStyleSheet(compact_label_style())
        primary_label.setFixedWidth(120)
        layout.addWidget(primary_label)
        self.primary_group_combo = QComboBox()
        self.primary_group_combo.setStyleSheet(compact_input_style())
        _configure_searchable_placeholder_combo(
            self.primary_group_combo,
            _SELECT_PRIMARY_GROUP,
            _ACCOUNT_TYPE_OPTIONS,
        )
        self.primary_group_combo.setFixedWidth(250)
        layout.addWidget(self.primary_group_combo)
        layout.addStretch()
        create_btn = QPushButton('Create Account Group')
        create_btn.setStyleSheet(compact_primary_button_style())
        create_btn.clicked.connect(self._create_account_group)
        layout.addWidget(create_btn)
        return tab

    def _create_view_accounts_tab(self) -> QWidget:
        """Create the view/edit accounts tab with table of all accounts."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        refresh_btn = QPushButton('Refresh Accounts')
        refresh_btn.setStyleSheet(compact_primary_button_style())
        refresh_btn.clicked.connect(self._load_accounts_table)
        layout.addWidget(refresh_btn)
        self.accounts_table = QTableWidget()
        apply_read_only_report_table_selection(self.accounts_table)
        self.accounts_table.verticalHeader().setDefaultSectionSize(45)
        layout.addWidget(self.accounts_table, 1)
        return tab

    def _load_accounts_table(self):
        """Load all accounts into the table."""
        if not self.account_engine or not self.company_id:
            return
        try:
            accounts = self.account_engine.get_all_accounts(self.company_id)
            headers = ['ID', 'Account Name', 'Type', 'Group', 'Opening Balance', 'Balance Type', 'Code', 'Actions']
            self.accounts_table.setColumnCount(len(headers))
            self.accounts_table.setHorizontalHeaderLabels(headers)
            self.accounts_table.setRowCount(len(accounts))
            for row, account in enumerate(accounts):
                self.accounts_table.setItem(row, 0, QTableWidgetItem(str(account.get('id', ''))))
                self.accounts_table.setItem(row, 1, QTableWidgetItem(account.get('account_name', '')))
                self.accounts_table.setItem(row, 2, QTableWidgetItem(account.get('account_type', '')))
                self.accounts_table.setItem(row, 3, QTableWidgetItem(account.get('group_name', '')))
                self.accounts_table.setItem(row, 4, QTableWidgetItem(str(account.get('opening_balance', 0.0))))
                self.accounts_table.setItem(row, 5, QTableWidgetItem(account.get('opening_balance_type', 'Dr')))
                self.accounts_table.setItem(row, 6, QTableWidgetItem(account.get('account_code', '')))
                is_system_value = account.get('is_system', 0)
                is_system = int(is_system_value) == 1 if is_system_value is not None else False
                colors = theme._theme_colors()
                text_color = QColor(colors['input_text'])
                user_bg = QColor(colors['panel_bg']) if theme._is_light_theme() else QColor('#1e3a5f')
                user_text = QColor(colors['input_text']) if theme._is_light_theme() else QColor('#ffffff')
                for col in range(7):
                    item = self.accounts_table.item(row, col)
                    if item:
                        item.setForeground(text_color)
                if not is_system:
                    for col in range(7):
                        item = self.accounts_table.item(row, col)
                        if item:
                            item.setBackground(user_bg)
                            item.setForeground(user_text)
                action_widget = QWidget()
                action_widget.setStyleSheet('background-color: transparent;')
                action_layout = QHBoxLayout(action_widget)
                action_layout.setContentsMargins(0, 0, 0, 0)
                action_layout.setSpacing(2)
                action_layout.setAlignment(Qt.AlignVCenter)
                if not is_system:
                    edit_btn = QPushButton('Edit')
                    edit_btn.setMinimumSize(62, 28)
                    edit_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    edit_btn.setStyleSheet(theme.master_primary_action_button_style('4px 8px', 12))
                    edit_btn.clicked.connect(lambda checked, acc=account: self._edit_account(acc))
                    action_layout.addWidget(edit_btn, 1)
                    delete_btn = QPushButton('Delete')
                    delete_btn.setMinimumSize(70, 28)
                    delete_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    delete_btn.setStyleSheet(theme.sales_danger_button_style())
                    delete_btn.clicked.connect(lambda checked, acc=account: self._delete_account(acc))
                    action_layout.addWidget(delete_btn, 1)
                else:
                    system_label = QLabel('🔒 System')
                    system_label.setAlignment(Qt.AlignCenter)
                    system_label.setStyleSheet(f"\n                        QLabel {{\n                            color: {theme._theme_colors()['accent_label']};\n                            font-weight: bold;\n                            font-size: 12px;\n                            padding: 4px 8px;\n                            margin: 0px;\n                            background-color: {theme._theme_colors()['panel_bg']};\n                            border: 1px solid {theme._theme_colors()['border']};\n                            border-radius: 4px;\n                        }}\n                    ")
                    action_layout.addWidget(system_label, 1)
                self.accounts_table.setCellWidget(row, 7, action_widget)
            apply_adjustable_table_columns(self.accounts_table, fixed_columns={7: 160})
            self._restore_memory_table(self.accounts_table, "accounts_table")
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to load accounts: {str(e)}')

    def _edit_account(self, account: dict):
        """Open edit dialog for the selected account."""
        is_system = account.get('is_system', 0) == 1
        if is_system:
            QMessageBox.warning(self, 'Access Denied', 'System-defined accounts cannot be edited. You can only edit accounts you have created.')
            return
        dialog = EditAccountDialog(account, self)
        if dialog.exec() == QDialog.Accepted:
            result = self.account_engine.update_ledger_account(account_id=account['id'], company_id=self.company_id, account_name=dialog.account_name, account_type=dialog.account_type, group_name=dialog.group_name or None, opening_balance=dialog.opening_balance, opening_balance_type=dialog.balance_type, account_code=dialog.account_code or None)
            if result['success']:
                QMessageBox.information(self, 'Success', result['message'])
                self._load_accounts_table()
                self._load_data()
            else:
                QMessageBox.critical(self, 'Error', result['error'])

    def _delete_account(self, account: dict):
        """Delete the selected account with confirmation."""
        is_system = account.get('is_system', 0) == 1
        if is_system:
            QMessageBox.warning(self, 'Access Denied', 'System-defined accounts cannot be deleted. You can only delete accounts you have created.')
            return
        reply = QMessageBox.question(self, 'Confirm Delete', f"Are you sure you want to delete account '{account['account_name']}'?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            result = self.account_engine.delete_ledger_account(account_id=account['id'], company_id=self.company_id)
            if result['success']:
                QMessageBox.information(self, 'Success', result['message'])
                self._load_accounts_table()
                self._load_data()
            else:
                QMessageBox.critical(self, 'Error', result['error'])

    def _load_data(self):
        """Load existing groups into dropdowns."""
        if not self.account_engine or not self.company_id:
            return
        try:
            groups = self.account_engine.get_account_groups(self.company_id)
            current_text = _normalized_group_selection(self.group_combo)
            group_names = [group['group_name'] for group in groups]
            _configure_searchable_placeholder_combo(self.group_combo, _SELECT_GROUP, group_names)
            if current_text:
                index = self.group_combo.findText(current_text)
                if index >= 0:
                    self.group_combo.setCurrentIndex(index)
        except Exception as e:
            print(f'Error loading account groups: {e}')

    def _capitalize_first_letter_field(self, field):
        """Auto-capitalize first letter of input field."""
        text = field.text()
        if text:
            cursor_pos = field.cursorPosition()
            capitalized = text[0].upper() + text[1:] if len(text) > 0 else text
            if text != capitalized:
                field.blockSignals(True)
                field.setText(capitalized)
                field.setCursorPosition(cursor_pos)
                field.blockSignals(False)

    def _show_create_group_dialog(self):
        """Show dialog to create a new group."""
        dialog = CreateGroupDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.group_combo.addItem(dialog.group_name)
            self.group_combo.setCurrentText(dialog.group_name)

    def _create_ledger_account(self):
        """Create a new ledger account."""
        if not self.account_engine or not self.company_id:
            QMessageBox.warning(self, 'Error', 'No active company. Please open a company first.')
            return
        account_name = self.account_name_edit.text().strip()
        if _is_placeholder_combo_value(self.account_type_combo, _SELECT_ACCOUNT_TYPE):
            QMessageBox.warning(self, 'Validation Error', 'Please select an account type.')
            return
        account_type_display = _resolve_combo_option(
            self.account_type_combo,
            _SELECT_ACCOUNT_TYPE,
            _ACCOUNT_TYPE_OPTIONS,
        )
        if not account_type_display:
            QMessageBox.warning(self, 'Validation Error', 'Please select a valid account type.')
            return
        group_name = _normalized_group_selection(self.group_combo)
        opening_balance_str = self.opening_balance_edit.text().strip()
        opening_balance = float(opening_balance_str) if opening_balance_str else 0.0
        balance_type = 'Dr'
        account_code = self.account_code_edit.text().strip() or None
        if not account_name:
            QMessageBox.warning(self, 'Validation Error', 'Account name is required.')
            return
        account_type = _ACCOUNT_TYPE_MAPPING.get(account_type_display)
        if not account_type:
            QMessageBox.warning(self, 'Validation Error', 'Please select a valid account type.')
            return
        result = self.account_engine.create_ledger_account(company_id=self.company_id, account_name=account_name, account_type=account_type, group_name=group_name if group_name else None, opening_balance=opening_balance, opening_balance_type=balance_type, account_code=account_code)
        if result['success']:
            QMessageBox.information(self, 'Success', result['message'])
            self.account_name_edit.clear()
            _reset_searchable_combo(self.account_type_combo, _SELECT_ACCOUNT_TYPE)
            _reset_searchable_combo(self.group_combo, _SELECT_GROUP)
            self.opening_balance_edit.clear()
            self.account_code_edit.clear()
            self._load_data()
        else:
            QMessageBox.critical(self, 'Error', result['error'])

    def _create_account_group(self):
        """Create a new account group (adds to group dropdown)."""
        group_name = self.group_name_edit.text().strip()
        if not group_name:
            QMessageBox.warning(self, 'Validation Error', 'Group name is required.')
            return
        if _is_placeholder_combo_value(self.primary_group_combo, _SELECT_PRIMARY_GROUP):
            QMessageBox.warning(self, 'Validation Error', 'Please select a primary group.')
            return
        primary_group = _resolve_combo_option(
            self.primary_group_combo,
            _SELECT_PRIMARY_GROUP,
            _ACCOUNT_TYPE_OPTIONS,
        )
        if not primary_group:
            QMessageBox.warning(self, 'Validation Error', 'Please select a valid primary group.')
            return
        self.group_combo.addItem(group_name)
        self.group_combo.setCurrentText(group_name)
        QMessageBox.information(self, 'Success', f"Group '{group_name}' added. You can now create ledger accounts under this group.")
        self.group_name_edit.clear()
        _reset_searchable_combo(self.primary_group_combo, _SELECT_PRIMARY_GROUP)
        self.tab_widget.setCurrentIndex(0)