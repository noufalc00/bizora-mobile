"""
Voucher Common UI Helpers.

Shared UI components and helpers for voucher pages.
"""

from PySide6.QtWidgets import (QComboBox, QCompleter, QLineEdit, QDateEdit,
                               QWidget, QHBoxLayout, QLabel, QFrame)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QStandardItemModel, QStandardItem
from typing import List, Dict, Any, Optional, Callable

from ui.book_report_common import compact_date_style, compact_input_style
from ui.entry_field_helpers import install_click_select_all


class AccountComboBox(QComboBox):
    """Editable account combo with search, placeholder text, and full dropdown list."""

    PLACEHOLDER = "Select Account"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accounts: List[Dict[str, Any]] = []
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMinimumWidth(200)

        self._completer = QCompleter(self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(self._completer)
        self._completer.activated.connect(self._on_completer_activated)

        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(self.PLACEHOLDER)
            install_click_select_all(line_edit)

        self._apply_style()
        self._apply_popup_theme()

    def _apply_popup_theme(self) -> None:
        """Keep completer and dropdown lists readable in the active theme."""
        from ui import theme
        theme.apply_completer_popup_theme(self._completer)
        theme.apply_combo_dropdown_theme(self)

    def _on_completer_activated(self, text: str) -> None:
        """Apply the account label chosen from the completer popup."""
        self.setCurrentText(str(text or ""))

    def _apply_style(self):
        """Apply theme-aware input style."""
        from ui import theme
        self.setStyleSheet(theme.sales_compact_input_style())

    def _clear_selection(self) -> None:
        """Show placeholder text without pre-selecting the first account."""
        self.setCurrentIndex(-1)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.clear()
            line_edit.setPlaceholderText(self.PLACEHOLDER)

    def load_accounts(self, accounts: List[Dict[str, Any]]):
        """Load accounts into the dropdown without auto-selecting the first row."""
        self._accounts = list(accounts or [])
        self.blockSignals(True)
        self.clear()
        for account in self._accounts:
            self.addItem(account.get("account_name", ""), account.get("id"))
        self._completer.setModel(self.model())
        self._clear_selection()
        self.blockSignals(False)
        self._apply_popup_theme()

    def get_account_id(self) -> Optional[int]:
        """Return the selected account id from item data or typed text."""
        account_id = self.currentData()
        if account_id is not None:
            try:
                return int(account_id)
            except (TypeError, ValueError):
                pass
        text = self.currentText().strip().lower()
        if not text or text == self.PLACEHOLDER.lower():
            return None
        for account in self._accounts:
            label = str(account.get("account_name") or "").strip().lower()
            if label == text:
                try:
                    return int(account.get("id"))
                except (TypeError, ValueError):
                    return None
        return None

    def set_account_id(self, account_id: int, accounts: Optional[List[Dict[str, Any]]] = None):
        """Set account by ID and keep the full dropdown list available."""
        if accounts is not None:
            self.load_accounts(accounts)
        if account_id is None:
            self._clear_selection()
            return
        for index in range(self.count()):
            item_id = self.itemData(index)
            if item_id is None:
                continue
            try:
                if int(item_id) == int(account_id):
                    self.setCurrentIndex(index)
                    return
            except (TypeError, ValueError):
                continue
        for account in self._accounts:
            try:
                if int(account.get("id") or 0) == int(account_id):
                    self.setCurrentText(str(account.get("account_name") or ""))
                    return
            except (TypeError, ValueError):
                continue


class VoucherTopBar(QWidget):
    """Standard voucher top bar layout.

    Common top bar fields for vouchers:
    - Voucher No
    - Date
    - Account fields
    - Amount
    - Remark
    - Narration
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout()
        self._layout.setSpacing(10)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._fields = {}

    def add_field(self, label: str, widget: QWidget, field_name: str):
        """Add a field to the top bar.

        Args:
            label: Field label
            widget: Field widget
            field_name: Internal field name
        """
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        label_widget = QLabel(label)
        label_widget.setStyleSheet(theme.voucher_topbar_label_style())
        label_widget.setFixedWidth(80)

        layout.addWidget(label_widget)
        layout.addWidget(widget)

        container.setLayout(layout)
        self._layout.addWidget(container)

        self._fields[field_name] = widget

    def add_separator(self):
        """Add vertical separator."""
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet(theme.voucher_topbar_separator_style())
        self._layout.addWidget(separator)

    def get_field(self, field_name: str) -> Optional[QWidget]:
        """Get field widget by name.

        Args:
            field_name: Field name

        Returns:
            Field widget or None
        """
        return self._fields.get(field_name)

    def add_stretch(self):
        """Add stretch to push remaining fields to right."""
        self._layout.addStretch()


def create_date_edit(default_date: Optional[QDate] = None) -> QDateEdit:
    """Create a date edit widget with dark style.

    Args:
        default_date: Default date (defaults to today)

    Returns:
        QDateEdit widget
    """
    date_edit = QDateEdit()
    if default_date:
        date_edit.setDate(default_date)
    else:
        date_edit.setDate(QDate.currentDate())

    date_edit.setCalendarPopup(True)
    from ui.date_formats import prepare_report_date_edit

    prepare_report_date_edit(date_edit, style_sheet=compact_date_style(), calendar_popup=False)

    try:
        from ui.financial_year_guard import apply_financial_year_guard_to_date_edit
        apply_financial_year_guard_to_date_edit(date_edit)
    except Exception:
        pass

    return date_edit


def create_line_edit(placeholder: str = "") -> QLineEdit:
    """Create a line edit widget with dark style.

    Args:
        placeholder: Placeholder text

    Returns:
        QLineEdit widget
    """
    line_edit = QLineEdit()
    line_edit.setPlaceholderText(placeholder)
    line_edit.setStyleSheet(compact_input_style())
    return line_edit


def format_currency(amount: float) -> str:
    """Format amount as currency.

    Args:
        amount: Amount to format

    Returns:
        Formatted currency string
    """
    return f"{amount:,.2f}"


def parse_currency(text: str) -> float:
    """Parse currency string to float.

    Args:
        text: Currency string

    Returns:
        Float value
    """
    try:
        # Remove commas and convert
        cleaned = text.replace(',', '').replace(' ', '')
        return float(cleaned) if cleaned else 0.0
    except (ValueError, AttributeError):
        return 0.0


# ============================================================
# UNIFORM STYLE HELPERS (based on Sales/Purchase Entry master style)
# ============================================================

def common_label_style() -> str:
    """Get common label style for top-bar fields (matches Sales/Purchase Entry)."""
    from ui import theme
    return theme.sales_micro_label_style()


def common_input_style() -> str:
    """Get common input style for top-bar fields (matches Sales/Purchase Entry)."""
    from ui import theme
    return theme.sales_compact_input_style()


def common_combo_style() -> str:
    """Get common combo box style with dropdown styling (matches Sales/Purchase Entry).
    
    Returns:
        CSS stylesheet string
    """
    return common_input_style()


def common_button_style(is_delete: bool = False) -> str:
    """Get common button style (matches Sales/Purchase Entry)."""
    from ui import theme
    return theme.sales_danger_button_style() if is_delete else theme.sales_primary_button_style()


def common_table_style() -> str:
    """Get common table style for history tables."""
    from ui import theme
    return theme.master_table_style()


def create_topbar_field(label_text: str, widget: QWidget) -> QWidget:
    """Create a top-bar field with label and widget.
    
    Args:
        label_text: Label text
        widget: Input widget
        
    Returns:
        Container widget with label and input
    """
    container = QWidget()
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    
    label = QLabel(label_text)
    label.setStyleSheet(common_label_style())
    label.setFixedWidth(100)
    
    widget.setStyleSheet(common_input_style())
    
    layout.addWidget(label)
    layout.addWidget(widget)
    
    container.setLayout(layout)
    return container


def apply_report_window_style(widget: QWidget):
    """Apply uniform style to report/voucher window."""
    from ui.book_report_common import page_background_style, report_filter_frame_style
    widget.setStyleSheet(
        page_background_style()
        + report_filter_frame_style("QFrame")
    )