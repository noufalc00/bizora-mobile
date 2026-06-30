# -*- coding: utf-8 -*-
"""
Shared form style standard for topbar fields across all report/voucher pages.

This module provides reusable style constants and helper functions based on
Sales Entry and Purchase Entry master style reference.

Master style source:
- ui/sales_entry_ui.py (delegates to ui/theme.py)
- ui/purchase_entry_ui.py (delegates to ui/theme.py)
- ui/theme.py (actual style definitions)

All topbar fields should use these styles to ensure uniformity across:
- Cash Receipt / Cash Payment / Bank Receipt / Bank Payment / Journal Entry
- Day Book / Ledger / Trial Balance / Stock Report
- Sales Book / Sales Return Book / Purchase Book / Purchase Return Book

IMPORTANT: Future modules must use ThemeManager/form_style_standard helpers.
Do not hardcode dark-only or light-only colors. Use theme_manager.get_colors()
to get current theme colors dynamically.
"""

from PySide6.QtWidgets import QLineEdit, QComboBox, QDateEdit, QPushButton, QLabel

# Import ThemeManager for theme-aware styling
from ui.theme_manager import get_theme_manager


# =============================================================================
# THEME-AWARE STYLE FUNCTIONS
# IMPORTANT: Future modules must use these theme-aware helpers instead of hardcoded colors.
# =============================================================================

def get_topbar_label_style() -> str:
    """Get theme-aware topbar label style."""
    colors = get_theme_manager().get_colors()
    return f"""
        QLabel {{
            color: {colors['label_text']};
            font-weight: bold;
            font-size: 11px;
            padding: 0px 2px;
        }}
    """

def get_topbar_input_style() -> str:
    """Get theme-aware topbar input field style."""
    colors = get_theme_manager().get_colors()
    return f"""
        QLineEdit, QComboBox, QDateEdit {{
            background-color: {colors['input_bg']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
            color: {colors['input_text']};
            font-size: 11px;
            padding: 2px 4px;
        }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
            border: 1px solid {colors['focus_border']};
        }}
        QLineEdit:disabled {{
            background-color: {colors['app_bg']};
            color: {colors['label_text']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 4px solid {colors['border']};
            margin-right: 4px;
        }}
    """

def get_topbar_button_style(kind: str = "primary") -> str:
    """Get theme-aware topbar button style by kind."""
    colors = get_theme_manager().get_colors()
    
    button_colors = {
        "primary": colors['button_primary'],
        "success": colors['button_success'],
        "danger": colors['button_danger'],
        "warning": colors['button_warning'],
        "default": colors['border']
    }
    
    bg_color = button_colors.get(kind, colors['button_primary'])
    
    if kind == "default":
        return f"""
            QPushButton {{
                background-color: {colors['panel_bg']};
                color: {colors['input_text']};
                border: 1px solid {colors['border']};
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 3px 6px;
            }}
            QPushButton:hover {{
                background-color: {colors['border']};
            }}
            QPushButton:pressed {{
                background-color: {colors['app_bg']};
            }}
        """
    else:
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 3px 6px;
            }}
            QPushButton:hover {{
                background-color: {get_theme_manager()._darken_color(bg_color, 10)};
            }}
            QPushButton:pressed {{
                background-color: {get_theme_manager()._darken_color(bg_color, 20)};
            }}
        """


# =============================================================================
# LEGACY CONSTANTS (deprecated - use functions above)
# These are kept for backward compatibility but will be removed in future.
# =============================================================================

# ---- Label style (deprecated) ----
TOPBAR_LABEL_STYLE = get_topbar_label_style()

# ---- Input field style (deprecated) ----
TOPBAR_INPUT_STYLE = get_topbar_input_style()

# ---- Button styles (deprecated) ----
TOPBAR_BUTTON_STYLE = get_topbar_button_style("default")
TOPBAR_PRIMARY_BUTTON_STYLE = get_topbar_button_style("primary")
TOPBAR_DANGER_BUTTON_STYLE = get_topbar_button_style("danger")
TOPBAR_SUCCESS_BUTTON_STYLE = get_topbar_button_style("success")

# ---- Field dimensions ----
TOPBAR_FIELD_HEIGHT = 22  # matches Sales/Purchase input height
TOPBAR_LABEL_WIDTH = 50   # typical label width (adjust per field)
TOPBAR_SMALL_FIELD_WIDTH = 65   # Series, etc.
TOPBAR_MEDIUM_FIELD_WIDTH = 95   # Date, Invoice No, etc.
TOPBAR_LARGE_FIELD_WIDTH = 115  # Nature, Party Type, etc.
TOPBAR_XLARGE_FIELD_WIDTH = 210  # State, etc.
TOPBAR_XXLARGE_FIELD_WIDTH = 380 # Party Name, etc.

# ---- Layout spacing ----
TOPBAR_SPACING = 2       # spacing between label and field
TOPBAR_MARGIN = 4       # margin around rows
TOPBAR_ROW_SPACING = 2  # spacing between fields in a row


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def apply_topbar_label_style(widget: QLabel) -> None:
    """Apply topbar label style to a QLabel widget."""
    widget.setStyleSheet(TOPBAR_LABEL_STYLE)


def apply_topbar_input_style(widget: QLineEdit) -> None:
    """Apply topbar input style to a QLineEdit widget."""
    widget.setStyleSheet(TOPBAR_INPUT_STYLE)


def apply_topbar_combo_style(widget: QComboBox) -> None:
    """Apply topbar combo style to a QComboBox widget."""
    widget.setStyleSheet(TOPBAR_INPUT_STYLE)


def apply_topbar_date_style(widget: QDateEdit) -> None:
    """Apply topbar date style to a QDateEdit widget."""
    widget.setStyleSheet(TOPBAR_INPUT_STYLE)


def apply_topbar_button_style(widget: QPushButton, kind: str = "primary") -> None:
    """
    Apply topbar button style to a QPushButton widget.
    
    Args:
        widget: QPushButton to style
        kind: Button type - "primary", "danger", "success", or "default"
    """
    if kind == "primary":
        widget.setStyleSheet(TOPBAR_PRIMARY_BUTTON_STYLE)
    elif kind == "danger":
        widget.setStyleSheet(TOPBAR_DANGER_BUTTON_STYLE)
    elif kind == "success":
        widget.setStyleSheet(TOPBAR_SUCCESS_BUTTON_STYLE)
    else:
        widget.setStyleSheet(TOPBAR_BUTTON_STYLE)


def make_topbar_label(text: str, width: int = TOPBAR_LABEL_WIDTH) -> QLabel:
    """
    Create a topbar label with standard style.
    
    Args:
        text: Label text
        width: Label width in pixels (default: TOPBAR_LABEL_WIDTH)
    
    Returns:
        QLabel with standard topbar style
    """
    label = QLabel(text)
    label.setStyleSheet(TOPBAR_LABEL_STYLE)
    label.setFixedWidth(width)
    return label


def make_topbar_line_edit(placeholder: str = "", width: int = TOPBAR_MEDIUM_FIELD_WIDTH) -> QLineEdit:
    """
    Create a topbar line edit with standard style.
    
    Args:
        placeholder: Placeholder text
        width: Field width in pixels (default: TOPBAR_MEDIUM_FIELD_WIDTH)
    
    Returns:
        QLineEdit with standard topbar style
    """
    field = QLineEdit()
    field.setStyleSheet(TOPBAR_INPUT_STYLE)
    field.setPlaceholderText(placeholder)
    field.setFixedWidth(width)
    return field


def make_topbar_combo(items: list = None, width: int = TOPBAR_LARGE_FIELD_WIDTH) -> QComboBox:
    """
    Create a topbar combo box with standard style.
    
    Args:
        items: List of items to add (default: empty)
        width: Field width in pixels (default: TOPBAR_LARGE_FIELD_WIDTH)
    
    Returns:
        QComboBox with standard topbar style
    """
    combo = QComboBox()
    combo.setStyleSheet(TOPBAR_INPUT_STYLE)
    combo.setFixedWidth(width)
    if items:
        combo.addItems(items)
    return combo


def make_topbar_date_edit(width: int | None = None) -> QDateEdit:
    """
    Create a topbar date edit with standard style.

    Args:
        width: Field width in pixels (defaults to REPORT_DATE_FIELD_WIDTH)

    Returns:
        QDateEdit with standard topbar style
    """
    from PySide6.QtCore import QDate
    from ui.date_formats import prepare_report_date_edit

    date_edit = QDateEdit()
    date_edit.setStyleSheet(TOPBAR_INPUT_STYLE)
    date_edit.setDate(QDate.currentDate())
    prepare_report_date_edit(date_edit, style_sheet=TOPBAR_INPUT_STYLE, width=width)

    return date_edit


def make_topbar_button(text: str, kind: str = "primary", width: int = 0) -> QPushButton:
    """
    Create a topbar button with standard style.
    
    Args:
        text: Button text
        kind: Button type - "primary", "danger", "success", or "default"
        width: Button width in pixels (default: auto-size)
    
    Returns:
        QPushButton with standard topbar style
    """
    button = QPushButton(text)
    apply_topbar_button_style(button, kind)
    if width > 0:
        button.setFixedWidth(width)
    return button