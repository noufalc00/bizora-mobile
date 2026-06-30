"""
Shared UI theme module for the Accounting Desktop application.

This module centralises the per-widget stylesheet fragments and small
parsing helpers that were previously duplicated across several UI files.

Design goals:
  - Single source of truth for widget-level colours / typography.
  - No behavioural change for existing widgets — the style strings
    returned here are byte-equivalent to the in-file versions they
    replace.
  - Safe, side-effect-free helpers. No Qt objects are created here.

Two colour families are used by the app:
  * "master" palette — #374151 background, #fbbf24 label — used by the
    Products, Debitor/Creditor and Bank Account master pages.
  * "sales"  palette — #334155 background, #fbbf24 label — used by the
    Sales Entry widget (see sales_entry_ui.py).

When you add a new master-data page, prefer the master_* helpers.
When you add or change a Sales Entry sub-block, use the sales_* helpers.
"""

from __future__ import annotations

from ui.checkbox_style import (
    CheckBox3D,
    RadioButton3D,
    app_checkbox_style,
    checkbox_indicator_style,
    create_app_checkbox,
    create_app_radio_button,
    create_checkbox,
    create_radio_button,
    labeled_checkbox_style,
    sales_checkbox_style,
    sales_compact_checkbox_style,
    sales_status_checkbox_style,
)
from ui.scrollbar_style import scrollbar_stylesheet


def _theme_colors() -> dict[str, str]:
    """Return active theme color tokens."""
    try:
        from ui.theme_manager import get_theme_manager
        return get_theme_manager().get_colors()
    except Exception:
        from utils.theme_manager import ThemeManager
        return ThemeManager.get_colors("dark")


def _is_light_theme() -> bool:
    try:
        from ui.theme_manager import get_theme_manager
        return get_theme_manager().get_current_theme() == "light"
    except Exception:
        return False


def is_bold_fonts_enabled(master_db_path: str | None = None) -> bool:
    """Return True when the global bold-font preference is enabled."""
    try:
        from utils.theme_manager import ThemeManager, global_theme_manager

        resolved = ThemeManager.resolve_master_db_path(master_db_path)
        return global_theme_manager.get_effective_bold_fonts(resolved)
    except Exception:
        return False


def font_weight_value(master_db_path: str | None = None) -> str:
    """Return the active global font-weight token for dynamic QSS helpers."""
    return "bold" if is_bold_fonts_enabled(master_db_path) else "normal"


def legacy_colors() -> dict[str, str]:
    """Map active theme tokens to legacy COLORS keys used by older modules."""
    c = _theme_colors()
    light = _is_light_theme()
    alt = c.get("surface_alt", c["app_bg"])
    return {
        "primary": c["button_primary"],
        "primary_dark": c["focus_border"],
        "primary_light": c["heading_text"] if light else "#1565C0",
        "background": c["app_bg"],
        "surface": c["panel_bg"],
        "card": c["card_bg"],
        "sidebar": c.get("nav_item_bg", c["panel_bg"]),
        "text_primary": c["input_text"],
        "text_secondary": c["label_text"] if light else c["muted_text"],
        "text_disabled": c["muted_text"],
        "success": c["button_success"],
        "warning": c["button_warning"],
        "error": c["button_danger"],
        "info": c["button_primary"],
        "border": c["border"],
        "border_light": c["border"],
        "border_focus": c["focus_border"],
        "scrollbar_track": c.get("scrollbar_track", alt),
        "scrollbar_handle": c.get("scrollbar_handle", c["border"]),
        "scrollbar_handle_hover": c.get("scrollbar_handle_hover", c["focus_border"]),
        "scrollbar_handle_pressed": c.get("scrollbar_handle_pressed", c["focus_border"]),
        "button_default": c["panel_bg"],
        "button_hover": alt,
        "button_pressed": c["app_bg"],
    }


# =============================================================================
# Shared constants
# =============================================================================

GST_STATE_CODES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli",
    "27": "Maharashtra",
    "28": "Andhra Pradesh",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh (New)",
}


# =============================================================================
# Safe parsing helpers
# =============================================================================

def safe_float(value, default: float = 0.0) -> float:
    """Return float(value) or ``default`` on any parse / type error.

    Accepts ``None``, empty strings, numeric types, and strings with
    surrounding whitespace or a trailing percent sign.
    """
    if value is None:
        return default
    try:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().rstrip('%').strip()
        if not text:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    """Return int(value) or ``default`` on any parse / type error."""
    if value is None:
        return default
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        text = str(value).strip()
        if not text:
            return default
        # Allow "12.0" style strings by going through float first.
        return int(float(text))
    except (TypeError, ValueError):
        return default


# =============================================================================
# Master-data palette (products / debitor-creditor / bank accounts)
# =============================================================================

_MASTER_INPUT_BASE = """
    QLineEdit {{
        background-color: {bg};
        color: {text};
        border: 1px solid {border};
        border-radius: 3px;
        padding: {padding};
        font-size: 12px;
        min-height: {min_height}px;
        height: {height}px;
        max-width: {max_width}px;{extra}
    }}
    QLineEdit:focus {{
        border-color: {focus};
        outline: none;
    }}
"""


def _master_input_kwargs(max_width: int, padding: str, min_height: int, height: int, extra: str = "") -> dict:
    colors = _theme_colors()
    return {
        "bg": colors["input_bg"],
        "text": colors["input_text"],
        "border": colors["border"],
        "focus": colors["focus_border"],
        "padding": padding,
        "min_height": min_height,
        "height": height,
        "max_width": max_width,
        "extra": extra,
    }


def master_input_style(max_width: int = 110) -> str:
    """Compact input field (default 110 px wide). Matches the legacy
    ``compact_input_style`` used in products / debitor_creditor /
    bank_accounts pages.
    """
    return _MASTER_INPUT_BASE.format(**_master_input_kwargs(110, "4px 8px", 16, 16))


def master_wide_input_style() -> str:
    """Wide input field (~210 px). Legacy ``wide_input_style``."""
    return _MASTER_INPUT_BASE.format(
        **_master_input_kwargs(210, "5px 8px", 18, 18, extra="\n        text-align: left;")
    )


def master_extra_wide_input_style() -> str:
    """Extra-wide input field (~380 px). Legacy ``extra_wide_input_style``."""
    return _MASTER_INPUT_BASE.format(**_master_input_kwargs(380, "4px 8px", 16, 16))


def master_label_style() -> str:
    """Compact master-data label."""
    colors = _theme_colors()
    return f"""
        QLabel {{
            color: {colors['accent_label']};
            font-size: 12px;
            font-weight: bold;
            background: transparent;
            border: none;
            padding: 1px 0px;
            margin: 0px;
            min-height: 14px;
            height: 14px;
        }}
    """


# =============================================================================
# Sales Entry palette
# =============================================================================
# These functions are used by sales_entry_ui.py / sales_entry.py as thin
# wrappers. Method names on the widget classes remain unchanged so the
# ~100+ call sites keep working.

def sales_compact_input_style() -> str:
    colors = _theme_colors()
    disabled_bg = colors["app_bg"]
    disabled_text = colors["label_text"] if _is_light_theme() else colors["muted_text"]
    arrow = colors["label_text"] if _is_light_theme() else colors["muted_text"]
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
            background-color: {disabled_bg};
            color: {disabled_text};
        }}
        QComboBox::drop-down, QDateEdit::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            border: none;
            width: 20px;
        }}
        QComboBox::down-arrow, QDateEdit::down-arrow {{
            image: none;
            width: 0px;
            height: 0px;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 4px solid {arrow};
            margin-right: 4px;
        }}
    """


def sales_barcode_input_style() -> str:
    colors = _theme_colors()
    accent = colors["accent_label"]
    return f"""
        QLineEdit {{
            background-color: {colors['input_bg']};
            border: 1px solid {accent};
            border-radius: 3px;
            color: {accent};
            font-size: 11px;
            font-weight: bold;
            padding: 2px 4px;
        }}
        QLineEdit:focus {{
            border: 1px solid {accent};
        }}
    """


def sales_totals_input_style() -> str:
    colors = _theme_colors()
    return f"""
        QLineEdit {{
            background-color: {colors['input_bg']};
            color: {colors['accent_highlight']};
            border: 1px solid {colors['border']};
            border-radius: 2px;
            padding: 3px 6px;
            font-size: 11px;
            font-weight: bold;
            min-height: 22px;
        }}
        QLineEdit:disabled {{
            background-color: {colors['app_bg']};
            color: {colors['muted_text']};
        }}
    """


def sales_micro_label_style() -> str:
    colors = _theme_colors()
    return f"""
    QLabel {{
        color: {colors['accent_label']};
        font-weight: bold;
        font-size: 11px;
        padding: 0px 2px;
        background: transparent;
        border: none;
    }}
    """


def sales_status_label_style() -> str:
    colors = _theme_colors()
    color = colors["label_text"] if _is_light_theme() else colors["muted_text"]
    return f"""
    QLabel {{
        color: {color};
        font-size: 11px;
        font-weight: bold;
        background: transparent;
        border: none;
    }}
    """


def sales_status_value_style() -> str:
    colors = _theme_colors()
    return (
        f"color: {colors['accent_highlight']}; font-weight: bold; font-size: 11px; "
        "background: transparent; border: none;"
    )


def sales_grand_label_style() -> str:
    colors = _theme_colors()
    return (
        f"font-size:11px; font-weight:bold; color:{colors['input_text']}; "
        "background:transparent; border:none;"
    )


def sales_grand_amount_style() -> str:
    colors = _theme_colors()
    return (
        f"font-size:22px; font-weight:bold; color:{colors['accent_highlight']}; "
        "background:transparent; border:none;"
    )


# ---- Sales Entry frame styles -----------------------------------------------

def _basic_dark_frame(bg: str | None = None, border: str | None = None, radius: int = 3) -> str:
    colors = _theme_colors()
    bg = bg or colors["panel_bg"]
    border = border or colors["border"]
    return f"""
        QFrame {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: {radius}px;
        }}
    """


def sales_bottom_panel_style() -> str:
    return _basic_dark_frame()


def sales_table_zone_style() -> str:
    return _basic_dark_frame()


def sales_action_frame_style() -> str:
    colors = _theme_colors()
    return _basic_dark_frame(bg=colors["app_bg"])


def sales_adj_frame_style() -> str:
    colors = _theme_colors()
    return _basic_dark_frame(bg=colors["app_bg"])


def sales_totals_frame_style() -> str:
    colors = _theme_colors()
    return _basic_dark_frame(bg=colors["app_bg"])


def sales_grand_total_frame_style() -> str:
    colors = _theme_colors()
    if _is_light_theme():
        bg = "#E8F5E9"
        border = colors["accent_highlight"]
    else:
        bg = "#064e3b"
        border = colors["accent_highlight"]
    return f"""
        QFrame {{
            background-color: {bg};
            border: 2px solid {border};
            border-radius: 4px;
        }}
    """


def sales_nav_box_style() -> str:
    return """
        QFrame {
            background-color: transparent;
            border: none;
        }
    """


# ---- Sales Entry button styles ----------------------------------------------

def sales_nav_button_style() -> str:
    colors = _theme_colors()
    return f"""
        QPushButton {{
            background-color: transparent;
            color: {colors['muted_text']};
            border: none;
            font-size: 7px;
            font-weight: bold;
            padding: 0px;
        }}
        QPushButton:hover {{
            color: {colors['accent_label']};
            background-color: transparent;
        }}
        QPushButton:pressed {{
            color: {colors['input_text']};
            background-color: transparent;
        }}
    """


def sales_billing_table_style(*, inline_cell_editors: bool = True) -> str:
    colors = _theme_colors()
    alt = colors["app_bg"] if _is_light_theme() else "#111c2e"
    cell_editor_bg = colors["panel_bg"] if _is_light_theme() else "#334155"
    cell_editor_hover = colors["border"] if _is_light_theme() else "#475569"
    edit_cell_bg = billing_cell_edit_background()
    if inline_cell_editors:
        line_edit_rules = f"""
        QTableWidget QLineEdit {{
            background-color: {edit_cell_bg};
            color: {colors['table_text']};
            border: 2px solid {colors['focus_border']};
            border-radius: 0px;
            padding: 0px 2px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            min-height: 0px;
            selection-background-color: {colors['focus_border']};
            selection-color: #FFFFFF;
        }}
        QTableWidget QLineEdit:focus {{
            background-color: {edit_cell_bg};
            border: 2px solid {colors['focus_border']};
        }}
        QTableWidget QLineEdit:disabled {{
            background-color: {colors['table_bg']};
            color: {colors['muted_text']};
        }}
        """
    else:
        line_edit_rules = f"""
        QTableWidget QLineEdit {{
            background-color: {cell_editor_bg};
            color: {colors['input_text']};
            border: 1px solid {colors['focus_border']};
            border-radius: 2px;
            padding: 2px 4px;
            font-size: 10px;
            min-height: 20px;
        }}
        QTableWidget QLineEdit:focus {{
            background-color: {cell_editor_hover};
            border: 1px solid {colors['focus_border']};
        }}
        QTableWidget QLineEdit:disabled {{
            background-color: {colors['input_bg']};
            color: {colors['muted_text']};
        }}
        """
    return f"""
        QTableWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            border: none;
            gridline-color: {colors['border']};
            font-size: 11px;
            font-weight: bold;
            selection-background-color: transparent;
            selection-color: {colors['table_text']};
            alternate-background-color: {alt};
        }}
        QTableWidget::item {{
            padding: 3px 5px;
            border-bottom: 1px solid {colors['border']};
            min-height: 24px;
        }}
        QTableWidget::item:selected {{
            background-color: transparent;
            color: {colors['table_text']};
            border: 2px solid {colors['focus_border']};
            border-radius: 2px;
        }}
        QTableWidget::item:focus {{
            background-color: {edit_cell_bg if inline_cell_editors else 'transparent'};
            border: 2px solid {colors['focus_border']};
        }}
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['heading_text']};
            padding: 4px 6px;
            border: none;
            border-bottom: 2px solid {colors['border']};
            border-right: 1px solid {colors['border']};
            font-weight: bold;
            font-size: 11px;
            min-height: 26px;
        }}
        QHeaderView::section:horizontal {{
            text-align: left;
        }}
        QHeaderView::section:first {{
            border-left: none;
        }}
        {line_edit_rules}
        QTableWidget QComboBox {{
            background-color: {cell_editor_bg};
            color: {colors['input_text']};
            border: 1px solid {colors['focus_border']};
            border-radius: 2px;
            padding: 2px 4px;
            font-size: 10px;
            min-height: 20px;
        }}
        QTableWidget QComboBox:focus {{
            background-color: {cell_editor_hover};
            border: 1px solid {colors['focus_border']};
        }}
        QTableWidget QComboBox::drop-down {{
            border: none;
            background-color: {cell_editor_bg};
            width: 16px;
        }}
        QTableWidget QComboBox::down-arrow {{
            image: none;
            border-left: 2px solid transparent;
            border-right: 2px solid transparent;
            border-top: 2px solid {colors['muted_text']};
            margin-right: 2px;
        }}
    """ + scrollbar_stylesheet()


def purchase_billing_table_style() -> str:
    """Editable billing/voucher grid with flush in-cell editors and edit highlight."""
    return sales_billing_table_style(inline_cell_editors=True)


def sales_entry_table_style() -> str:
    """Sales Entry billing grid with full colored border on active edit cells."""
    colors = _theme_colors()
    alt = colors["app_bg"] if _is_light_theme() else "#111c2e"
    edit_cell_bg = billing_cell_edit_background()
    line_edit_rules = f"""
        QTableWidget QLineEdit {{
            background-color: {edit_cell_bg};
            color: {colors['table_text']};
            border: 2px solid {colors['focus_border']};
            border-radius: 1px;
            padding: 0px 2px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            min-height: 0px;
            selection-background-color: {colors['focus_border']};
            selection-color: #FFFFFF;
        }}
        QTableWidget QLineEdit:focus {{
            background-color: {edit_cell_bg};
            border: 2px solid {colors['focus_border']};
        }}
        QTableWidget QLineEdit:disabled {{
            background-color: {colors['table_bg']};
            color: {colors['muted_text']};
            border: none;
        }}
        """
    return f"""
        QTableWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            border: none;
            gridline-color: {colors['border']};
            font-size: 11px;
            font-weight: bold;
            selection-background-color: transparent;
            selection-color: {colors['table_text']};
            alternate-background-color: {alt};
        }}
        QTableWidget::item {{
            padding: 3px 5px;
            border-bottom: 1px solid {colors['border']};
            min-height: 24px;
        }}
        QTableWidget::item:selected {{
            background-color: transparent;
            color: {colors['table_text']};
            border: 2px solid {colors['focus_border']};
            border-radius: 2px;
        }}
        QTableWidget::item:focus {{
            background-color: {edit_cell_bg};
            border: 2px solid {colors['focus_border']};
            border-radius: 1px;
        }}
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['accent_label']};
            font-weight: bold;
            padding: 4px 6px;
            border: 1px solid {colors['border']};
            font-size: 10px;
        }}
        {line_edit_rules}
    """ + scrollbar_stylesheet()


def editable_table_style() -> str:
    """Shared editable data-grid style for entry, payment, and receipt screens."""
    return purchase_billing_table_style()


def voucher_grid_embedded_line_edit_style() -> str:
    """Flush payment/receipt grid line edit: flat until focused, then Sales Entry highlight."""
    colors = _theme_colors()
    edit_cell_bg = billing_cell_edit_background()
    return f"""
        QLineEdit {{
            background-color: transparent;
            color: {colors['table_text']};
            border: none;
            border-radius: 0px;
            padding: 0px 2px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            min-height: 0px;
            selection-background-color: {colors['focus_border']};
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus {{
            background-color: {edit_cell_bg};
            border: 2px solid {colors['focus_border']};
            border-radius: 1px;
        }}
    """


def voucher_grid_embedded_combo_style() -> str:
    """Flush payment/receipt account combo: flat until focused, then Sales Entry highlight."""
    colors = _theme_colors()
    edit_cell_bg = billing_cell_edit_background()
    return f"""
        QComboBox {{
            background-color: transparent;
            color: {colors['table_text']};
            border: none;
            border-radius: 0px;
            padding: 0px 2px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            min-height: 0px;
        }}
        QComboBox:focus {{
            background-color: {edit_cell_bg};
            border: 2px solid {colors['focus_border']};
            border-radius: 1px;
        }}
        QComboBox QLineEdit {{
            background-color: transparent;
            color: {colors['table_text']};
            border: none;
            border-radius: 0px;
            padding: 0px 2px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            selection-background-color: {colors['focus_border']};
            selection-color: #FFFFFF;
        }}
        QComboBox:focus QLineEdit,
        QComboBox QLineEdit:focus {{
            background-color: {edit_cell_bg};
            border: 2px solid {colors['focus_border']};
            border-radius: 1px;
        }}
        QComboBox::drop-down {{
            border: none;
            background: transparent;
            width: 16px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {colors['muted_text']};
            margin-right: 2px;
        }}
    """


def voucher_grid_table_style() -> str:
    """Payment/receipt voucher grid matching Sales Entry flat cells and focus highlight."""
    colors = _theme_colors()
    alt = colors["app_bg"] if _is_light_theme() else "#111c2e"
    edit_cell_bg = billing_cell_edit_background()
    return f"""
        QTableWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            border: none;
            gridline-color: {colors['border']};
            font-size: 11px;
            font-weight: bold;
            selection-background-color: transparent;
            selection-color: {colors['table_text']};
            alternate-background-color: {alt};
        }}
        QTableWidget::item {{
            padding: 3px 5px;
            border-bottom: 1px solid {colors['border']};
            min-height: 24px;
        }}
        QTableWidget::item:selected {{
            background-color: transparent;
            color: {colors['table_text']};
            border: 2px solid {colors['focus_border']};
            border-radius: 2px;
        }}
        QTableWidget::item:focus {{
            background-color: {edit_cell_bg};
            border: 2px solid {colors['focus_border']};
            border-radius: 1px;
        }}
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['heading_text']};
            padding: 4px 6px;
            border: none;
            border-bottom: 2px solid {colors['border']};
            border-right: 1px solid {colors['border']};
            font-weight: bold;
            font-size: 11px;
            min-height: 26px;
        }}
        QHeaderView::section:horizontal {{
            text-align: left;
        }}
        QHeaderView::section:first {{
            border-left: none;
        }}
    """ + scrollbar_stylesheet()


def prepare_voucher_grid_cell_line_edit(editor) -> None:
    """Configure a flush embedded line edit inside payment/receipt grid cells."""
    try:
        editor.setFrame(False)
    except AttributeError:
        pass
    editor.setStyleSheet(voucher_grid_embedded_line_edit_style())


def prepare_voucher_grid_cell_combo(combo) -> None:
    """Configure a flush embedded account combo inside payment/receipt grid cells."""
    try:
        combo.setFrame(False)
    except AttributeError:
        pass
    combo.setStyleSheet(voucher_grid_embedded_combo_style())
    line_edit = combo.lineEdit()
    if line_edit is not None:
        try:
            line_edit.setFrame(False)
        except AttributeError:
            pass
    apply_combo_dropdown_theme(combo)


def ledger_report_table_style() -> str:
    """Legacy alias for read-only report/book table styling."""
    return read_only_report_table_style()


def read_only_report_table_style() -> str:
    """Standard read-only report/book grid styling (Best Sellers style)."""
    colors = _theme_colors()
    alt = colors["app_bg"] if _is_light_theme() else "#172033"
    selection_text = colors["input_text"] if _is_light_theme() else "white"
    return f"""
        QTableWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            border: 1px solid {colors['border']};
            gridline-color: {colors['border']};
            selection-background-color: {colors['focus_border'] if _is_light_theme() else '#2563eb'};
            selection-color: {selection_text};
            alternate-background-color: {alt};
        }}
        QTableWidget::item {{
            padding: 2px 6px;
        }}
        QTableWidget::item:selected {{
            background-color: {colors['focus_border'] if _is_light_theme() else '#2563eb'};
            color: {selection_text};
        }}
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['accent_label']};
            font-weight: bold;
            padding: 6px 8px;
            border: 1px solid {colors['border']};
        }}
    """ + scrollbar_stylesheet()


def sales_compact_button_style() -> str:
    colors = _theme_colors()
    hover = colors["border"] if _is_light_theme() else "#475569"
    pressed = colors["app_bg"] if _is_light_theme() else "#1e293b"
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
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ background-color: {pressed}; }}
    """


def sales_modern_3d_icon_button_style() -> str:
    """Compact raised 3D icon button style for Sales Entry utility actions."""
    colors = _theme_colors()
    if _is_light_theme():
        return f"""
            QPushButton#salesIconButton {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.45 #E8FAFA, stop:1 #C0E8E8
                );
                color: {colors['heading_text']};
                border: 1px solid {colors['border']};
                border-top: 1px solid #FFFFFF;
                border-left: 1px solid #FFFFFF;
                border-right: 1px solid {colors['border']};
                border-bottom: 3px solid #b0bec5;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
                min-width: 28px;
                min-height: 28px;
                max-width: 28px;
                max-height: 28px;
            }}
            QPushButton#salesIconButton:hover {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:1 #D2F2F2
                );
                color: {colors['focus_border']};
            }}
            QPushButton#salesIconButton:pressed {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #C0E8E8, stop:1 #FFFFFF
                );
                border: 1px solid {colors['border']};
                border-bottom: 1px solid {colors['border']};
                margin-top: 2px;
                padding-top: 1px;
            }}
            QPushButton#salesIconButton:disabled {{
                background-color: {colors['panel_bg']};
                color: {colors['muted_text']};
                border: 1px solid {colors['border']};
                border-bottom: 2px solid {colors['border']};
            }}
        """
    return f"""
        QPushButton#salesIconButton {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #5b6b82, stop:0.45 #3d4d63, stop:1 #1e293b
            );
            color: #FFFFFF;
            border: 1px solid {colors['border']};
            border-top: 1px solid #94a3b8;
            border-left: 1px solid #94a3b8;
            border-right: 1px solid #0f172a;
            border-bottom: 3px solid #1e1e1e;
            border-radius: 4px;
            font-size: 16px;
            font-weight: bold;
            padding: 0px;
            margin: 0px;
            min-width: 28px;
            min-height: 28px;
            max-width: 28px;
            max-height: 28px;
        }}
        QPushButton#salesIconButton:hover {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #64748b, stop:1 #334155
            );
            color: {colors['accent_label']};
        }}
        QPushButton#salesIconButton:pressed {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #1e293b, stop:1 #475569
            );
            border: 1px solid {colors['border']};
            border-bottom: 1px solid {colors['border']};
            margin-top: 2px;
            padding-top: 1px;
        }}
        QPushButton#salesIconButton:disabled {{
            background-color: {colors['panel_bg']};
            color: {colors['muted_text']};
            border: 1px solid {colors['border']};
            border-bottom: 2px solid {colors['border']};
        }}
    """


def sidebar_icon_box_style() -> str:
    """Filled 3D box framing a sidebar icon (matches shortcut toolbar tiles)."""
    return shortcut_toolbar_3d_icon_button_style().replace(
        "QPushButton#shortcutIconButton",
        "QFrame#sidebarIconBox",
    )


def sidebar_section_header_style() -> str:
    """Row style for a sidebar accordion section header with hover/active states."""
    colors = _theme_colors()
    return f"""
        QWidget#sidebarSectionHeader {{
            background-color: {colors['nav_header_bg']};
            border: none;
            border-left: 3px solid {colors['nav_accent']};
            border-radius: 0px;
        }}
        QWidget#sidebarSectionHeader[hovered="true"][active="false"] {{
            background-color: {colors['nav_header_hover']};
        }}
        QWidget#sidebarSectionHeader[active="true"] {{
            background-color: {colors['nav_header_active']};
        }}
        QWidget#sidebarSectionHeader[active="true"] QLabel#sidebarSectionTitle {{
            color: #FFFFFF;
        }}
        QLabel#sidebarSectionTitle {{
            color: {colors['nav_header_text']};
            font-size: 15px;
            font-weight: bold;
            background: transparent;
            border: none;
        }}
    """


# Navy frame from the official BIZORA logo artwork (light theme default).
SIDEBAR_LOGO_BORDER_COLOR = "#1a2b44"


def sidebar_logo_box_style() -> str:
    """Theme-aware logo frame: light stage + accent border in dark mode."""
    colors = _theme_colors()
    stage_bg = colors.get("logo_stage_bg", "transparent")
    stage_border = colors.get("logo_stage_border", SIDEBAR_LOGO_BORDER_COLOR)
    return f"""
        QFrame#sidebarLogoBox {{
            background-color: {stage_bg};
            border: 3px solid {stage_border};
            border-radius: 0px;
        }}
    """


def sidebar_route_button_style() -> str:
    """Sidebar submenu route buttons with hover colours scoped above global QPushButton rules."""
    colors = _theme_colors()
    return f"""
        QWidget#sidebarMenuHost QPushButton {{
            background-color: {colors['nav_item_bg']};
            color: {colors['nav_item_text']};
            border: none;
            border-left: 3px solid transparent;
            padding: 7px 18px;
            text-align: left;
            border-radius: 0px;
            font-size: 13px;
            font-weight: bold;
        }}
        QWidget#sidebarMenuHost QPushButton:hover {{
            background-color: {colors['nav_item_hover_bg']};
            color: {colors['nav_item_hover_text']};
            border-left: 3px solid {colors['nav_accent']};
        }}
        QWidget#sidebarMenuHost QPushButton:pressed {{
            background-color: {colors['nav_item_active_bg']};
            color: {colors['nav_item_hover_text']};
            border-left: 3px solid {colors['nav_accent']};
        }}
        QWidget#sidebarMenuHost QPushButton:disabled {{
            background-color: {colors['nav_item_bg']};
            color: {colors['muted_text']};
            border-left: 3px solid transparent;
        }}
    """


def sidebar_navigation_qss(colors: dict[str, str] | None = None) -> str:
    """Application-level sidebar navigation QSS that survives global QWidget transparency."""
    palette = colors or _theme_colors()
    return f"""
        QWidget#sidebarSectionHeader {{
            background-color: {palette['nav_header_bg']};
            border: none;
            border-left: 3px solid {palette['nav_accent']};
            border-radius: 0px;
        }}
        QWidget#sidebarSectionHeader[hovered="true"][active="false"] {{
            background-color: {palette['nav_header_hover']};
        }}
        QWidget#sidebarSectionHeader[active="true"] {{
            background-color: {palette['nav_header_active']};
        }}
        QWidget#sidebarSectionHeader[active="true"] QLabel#sidebarSectionTitle {{
            color: #FFFFFF;
        }}
        QLabel#sidebarSectionTitle {{
            color: {palette['nav_header_text']};
            font-size: 15px;
            font-weight: bold;
            background: transparent;
            border: none;
        }}
        QWidget#sidebarMenuHost QPushButton {{
            background-color: {palette['nav_item_bg']};
            color: {palette['nav_item_text']};
            border: none;
            border-left: 3px solid transparent;
            padding: 7px 18px;
            text-align: left;
            border-radius: 0px;
            font-size: 13px;
            font-weight: bold;
        }}
        QWidget#sidebarMenuHost QPushButton:hover {{
            background-color: {palette['nav_item_hover_bg']};
            color: {palette['nav_item_hover_text']};
            border-left: 3px solid {palette['nav_accent']};
        }}
        QWidget#sidebarMenuHost QPushButton:pressed {{
            background-color: {palette['nav_item_active_bg']};
            color: {palette['nav_item_hover_text']};
            border-left: 3px solid {palette['nav_accent']};
        }}
        QWidget#sidebarMenuHost QPushButton:disabled {{
            background-color: {palette['nav_item_bg']};
            color: {palette['muted_text']};
            border-left: 3px solid transparent;
        }}
    """


def shortcut_toolbar_3d_icon_button_style() -> str:
    """Raised 3D gradient style for icon-only shortcut toolbar buttons."""
    colors = _theme_colors()
    if _is_light_theme():
        return f"""
            QPushButton#shortcutIconButton {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.45 #E8FAFA, stop:1 #C0E8E8
                );
                border: 1px solid {colors['border']};
                border-top: 1px solid #FFFFFF;
                border-left: 1px solid #FFFFFF;
                border-bottom: 3px solid #b0bec5;
                border-radius: 6px;
                padding: 2px;
                margin-top: 0px;
            }}
            QPushButton#shortcutIconButton:hover {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:1 #D2F2F2
                );
            }}
            QPushButton#shortcutIconButton:pressed {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #C0E8E8, stop:1 #FFFFFF
                );
                border: 1px solid {colors['border']};
                border-bottom: 1px solid {colors['border']};
                margin-top: 2px;
                padding-top: 4px;
            }}
        """
    return f"""
        QPushButton#shortcutIconButton {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #5b6b82, stop:0.45 #3d4d63, stop:1 #1e293b
            );
            border: 1px solid {colors['border']};
            border-top: 1px solid #94a3b8;
            border-left: 1px solid #94a3b8;
            border-bottom: 3px solid #1e1e1e;
            border-radius: 6px;
            padding: 2px;
            margin-top: 0px;
        }}
        QPushButton#shortcutIconButton:hover {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #64748b, stop:1 #334155
            );
        }}
        QPushButton#shortcutIconButton:pressed {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #1e293b, stop:1 #475569
            );
            border: 1px solid {colors['border']};
            border-bottom: 1px solid {colors['border']};
            margin-top: 2px;
            padding-top: 4px;
        }}
    """


def master_settings_3d_button_style() -> str:
    """Raised 3D settings button with gear icon and Settings label."""
    colors = _theme_colors()
    if _is_light_theme():
        return f"""
            QPushButton {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.5 #ECEFF1, stop:1 #CFD8DC
                );
                color: {colors['heading_text']};
                border-top: 1px solid #FFFFFF;
                border-left: 1px solid #FFFFFF;
                border-right: 1px solid #90A4AE;
                border-bottom: 1px solid #78909C;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 4px 12px 4px 8px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:1 #E0E7EC
                );
                color: {colors['focus_border']};
            }}
            QPushButton:pressed {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #B0BEC5, stop:1 #ECEFF1
                );
                border-top: 1px solid #78909C;
                border-left: 1px solid #78909C;
                border-right: 1px solid #FFFFFF;
                border-bottom: 1px solid #FFFFFF;
                padding-top: 5px;
                padding-bottom: 3px;
            }}
        """
    return f"""
        QPushButton {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #64748b, stop:0.5 #475569, stop:1 #334155
            );
            color: #E2E8F0;
            border-top: 1px solid #94A3B8;
            border-left: 1px solid #94A3B8;
            border-right: 1px solid #0F172A;
            border-bottom: 1px solid #0F172A;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            padding: 4px 12px 4px 8px;
            text-align: left;
        }}
        QPushButton:hover {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #94A3B8, stop:1 #475569
            );
            color: {colors['accent_label']};
        }}
        QPushButton:pressed {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #1E293B, stop:1 #64748B
            );
            border-top: 1px solid #0F172A;
            border-left: 1px solid #0F172A;
            border-right: 1px solid #94A3B8;
            border-bottom: 1px solid #94A3B8;
            padding-top: 5px;
            padding-bottom: 3px;
        }}
    """


def sales_primary_button_style() -> str:
    colors = _theme_colors()
    hover = "#1565C0" if _is_light_theme() else "#2563eb"
    pressed = "#0D47A1" if _is_light_theme() else "#1d4ed8"
    return f"""
        QPushButton {{
            background-color: {colors['button_primary']};
            color: white;
            border: none;
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
            padding: 3px 6px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ background-color: {pressed}; }}
    """


def sales_danger_button_style() -> str:
    colors = _theme_colors()
    hover = "#C62828" if _is_light_theme() else "#dc2626"
    pressed = "#B71C1C" if _is_light_theme() else "#b91c1c"
    return f"""
        QPushButton {{
            background-color: {colors['button_danger']};
            color: white;
            border: none;
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
            padding: 3px 6px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ background-color: {pressed}; }}
    """


# =============================================================================
# Entry page zones (Sales / Purchase and similar voucher screens)
# =============================================================================

def entry_page_background_style() -> str:
    colors = _theme_colors()
    return f"background-color: {colors['app_bg']}; color: {colors['input_text']};"


def entry_header_strip_style() -> str:
    colors = _theme_colors()
    return f"""
        QFrame {{
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 4px;
        }}
    """


def entry_command_strip_style() -> str:
    colors = _theme_colors()
    zone_bg = colors.get("surface_alt", colors["app_bg"])
    return f"""
        QFrame {{
            background-color: {zone_bg};
            border: 1px solid {colors['border']};
            border-radius: 4px;
        }}
    """


def entry_section_frame_style() -> str:
    return entry_header_strip_style()


def entry_inset_frame_style() -> str:
    return entry_command_strip_style()


def entry_page_title_style() -> str:
    colors = _theme_colors()
    return (
        f"font-size:13px; font-weight:bold; color:{colors['heading_text']}; "
        "background:transparent; border:none;"
    )


def entry_page_title_label_style() -> str:
    colors = _theme_colors()
    return f"""
        QLabel {{
            color: {colors['heading_text']};
            font-size: 14px;
            font-weight: bold;
            padding: 4px 8px;
            background: transparent;
            border: none;
        }}
    """


def entry_footer_label_style() -> str:
    return sales_micro_label_style()


def entry_footer_input_style() -> str:
    colors = _theme_colors()
    accent = colors["accent_highlight"]
    if _is_light_theme():
        bg = "#E8F5E9"
        text = "#1B5E20"
        border = accent
        focus_bg = "#C8E6C9"
    else:
        bg = "#1c2a1e"
        text = "#bbf7d0"
        border = "#4ade80"
        focus_bg = "#14532d"
    return f"""
        QLineEdit {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 2px;
            color: {text};
            font-size: 10px;
            font-weight: bold;
            padding: 1px 3px;
        }}
        QLineEdit:focus {{
            background-color: {focus_bg};
            border: 1px solid {accent};
            color: {text};
        }}
    """


def entry_footer_input_readonly_style() -> str:
    colors = _theme_colors()
    return f"""
        QLineEdit {{
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 2px;
            color: {colors['muted_text']};
            font-size: 10px;
            font-weight: bold;
            padding: 1px 3px;
        }}
    """


def entry_table_header_style() -> str:
    colors = _theme_colors()
    return f"""
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['heading_text']};
            font-size: 10px;
            font-weight: bold;
            padding: 3px;
            border: 1px solid {colors['border']};
            border-bottom: 2px solid {colors['border']};
        }}
    """


def entry_nav_box_style() -> str:
    colors = _theme_colors()
    return f"""
        QFrame {{
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 2px;
        }}
    """


def entry_value_style(color_name: str = "accent_highlight") -> str:
    colors = _theme_colors()
    color = colors.get(color_name, colors["accent_highlight"])
    return (
        f"color: {color}; font-weight: bold; font-size: 11px; "
        "background: transparent; border: none;"
    )


def entry_footer_value_label_style(color_name: str = "input_text") -> str:
    """Theme-aware value labels in voucher footer totals blocks."""
    colors = _theme_colors()
    color = colors.get(color_name, colors["input_text"])
    return f"""
        QLabel {{
            color: {color};
            font-weight: bold;
            font-size: 11px;
            background: transparent;
            border: none;
        }}
    """


def entry_info_value_style() -> str:
    colors = _theme_colors()
    color = colors["focus_border"] if _is_light_theme() else colors["accent"]
    return (
        f"color: {color}; font-weight: bold; font-size: 11px; "
        "background: transparent; border: none;"
    )


def entry_micro_hint_style() -> str:
    """Tiny secondary hint label (e.g. discount % caption)."""
    colors = _theme_colors()
    color = colors["focus_border"] if _is_light_theme() else "#8ab4f8"
    return (
        f"QLabel {{ color: {color}; font-size: 7px; padding: 0px; margin: 0px; "
        "background: transparent; border: none; }}"
    )


def entry_calendar_style() -> str:
    colors = _theme_colors()
    if _is_light_theme():
        alt_bg = colors.get("surface_alt", colors["app_bg"])
        nav_bg = colors["panel_bg"]
        day_bg = colors["input_bg"]
        day_text = colors["input_text"]
        muted = colors["muted_text"]
        today_bg = colors["focus_border"]
        menu_bg = colors["input_bg"]
        btn_text = colors["input_text"]
    else:
        alt_bg = "#1e293b"
        nav_bg = "#0f172a"
        day_bg = "#1e2430"
        day_text = "#FFFFFF"
        muted = "#64748b"
        today_bg = "#0056b3"
        menu_bg = "#1e2430"
        btn_text = "#FFFFFF"
    return f"""
        QCalendarWidget QWidget {{ alternate-background-color: {alt_bg}; }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background-color: {nav_bg};
            min-height: 34px;
        }}
        QCalendarWidget QToolButton {{
            color: {btn_text};
            background-color: transparent;
            font-weight: bold;
            font-size: 12px;
            padding-top: 1px;
            padding-bottom: 1px;
            margin: 2px;
        }}
        QCalendarWidget QComboBox {{
            border: 1px solid {colors['border']};
            border-radius: 3px;
            padding: 1px 18px 1px 3px;
            min-width: 6em;
            color: {day_text};
            background-color: {menu_bg};
        }}
        QCalendarWidget QSpinBox {{
            border: 1px solid {colors['border']};
            border-radius: 3px;
            padding: 1px;
            color: {day_text};
            background-color: {menu_bg};
        }}
        QCalendarWidget QMenu {{
            background-color: {menu_bg};
            color: {day_text};
        }}
        QCalendarWidget QMenu::item:selected {{
            background-color: {today_bg};
            color: #FFFFFF;
        }}
        QCalendarWidget QAbstractItemView:enabled {{
            color: {day_text};
            background-color: {day_bg};
            selection-background-color: {today_bg};
            selection-color: #FFFFFF;
        }}
        QCalendarWidget QAbstractItemView::item {{
            padding: 0px;
            margin: 0px;
        }}
        QCalendarWidget QAbstractItemView:disabled {{
            color: {muted};
        }}
    """


def apply_calendar_day_formats(calendar_widget) -> None:
    """Apply consistent weekend and current-day formats on a calendar widget."""
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtGui import QColor, QFont, QTextCharFormat

    colors = _theme_colors()
    is_light = _is_light_theme()
    base_day_text = colors["input_text"] if is_light else "#FFFFFF"
    muted_text = colors["muted_text"] if is_light else "#64748b"
    weekend_text = "#FF0000"
    today_bg = colors["focus_border"] if is_light else "#0056b3"

    default_format = QTextCharFormat()
    default_format.setForeground(QColor(base_day_text))
    calendar_widget.setWeekdayTextFormat(Qt.Monday, default_format)
    calendar_widget.setWeekdayTextFormat(Qt.Tuesday, default_format)
    calendar_widget.setWeekdayTextFormat(Qt.Wednesday, default_format)
    calendar_widget.setWeekdayTextFormat(Qt.Thursday, default_format)
    calendar_widget.setWeekdayTextFormat(Qt.Friday, default_format)

    weekend_format = QTextCharFormat()
    weekend_format.setForeground(QColor(weekend_text))
    calendar_widget.setWeekdayTextFormat(Qt.Saturday, weekend_format)
    calendar_widget.setWeekdayTextFormat(Qt.Sunday, weekend_format)

    header_format = QTextCharFormat()
    header_format.setForeground(QColor(base_day_text))
    header_format.setFontWeight(QFont.Bold)
    calendar_widget.setHeaderTextFormat(header_format)

    disabled_format = QTextCharFormat()
    disabled_format.setForeground(QColor(muted_text))
    calendar_widget.setDateTextFormat(QDate(), disabled_format)

    today_format = QTextCharFormat()
    today_format.setBackground(QColor(today_bg))
    today_format.setForeground(QColor("#FFFFFF"))
    today_format.setFontWeight(QFont.Bold)
    calendar_widget.setDateTextFormat(QDate.currentDate(), today_format)


def apply_date_edit_calendar_theme(date_edit) -> None:
    """Apply shared calendar popup styling to a QDateEdit field."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QToolButton

    calendar = date_edit.calendarWidget()
    if calendar is None:
        return

    calendar.setStyleSheet(entry_calendar_style())

    prev_btn = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
    if prev_btn is not None:
        prev_btn.setArrowType(_Qt.NoArrow)
        prev_btn.setToolButtonStyle(_Qt.ToolButtonTextOnly)
        prev_btn.setText("<")
        prev_btn.setFixedSize(24, 24)
    next_btn = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
    if next_btn is not None:
        next_btn.setArrowType(_Qt.NoArrow)
        next_btn.setToolButtonStyle(_Qt.ToolButtonTextOnly)
        next_btn.setText(">")
        next_btn.setFixedSize(24, 24)

    apply_calendar_day_formats(calendar)


def _popup_list_hover_background() -> str:
    """Return theme token used for dropdown row hover highlights."""
    colors = _theme_colors()
    return colors.get(
        "nav_item_hover_bg",
        colors.get("surface_alt", colors["app_bg"]),
    )


def _enable_popup_list_hover(view) -> None:
    """Enable QListView/QCompleter hover pseudo-states in Qt stylesheets."""
    if view is None:
        return
    try:
        from PySide6.QtCore import Qt

        view.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        view.setMouseTracking(True)
        viewport = view.viewport()
        if viewport is not None:
            viewport.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            viewport.setMouseTracking(True)
    except Exception:
        pass


_COMBO_DROPDOWN_ITEM_DELEGATE = None


def apply_completer_popup_theme(completer) -> None:
    """Apply readable list colors to a QCompleter popup."""
    if completer is None:
        return
    popup = completer.popup()
    if popup is not None:
        popup.setStyleSheet(completer_popup_list_style())
        _enable_popup_list_hover(popup)
        delegate_cls = _get_combo_dropdown_item_delegate_class()
        popup.setItemDelegate(delegate_cls(popup))


def wire_line_edit_completer(editor, completer) -> None:
    """Attach a QCompleter to a line edit and apply the shared popup theme."""
    editor.setCompleter(completer)
    apply_completer_popup_theme(completer)


def wire_editable_combo_completer(combo, completer) -> None:
    """Theme both the combo dropdown list and its embedded completer popup."""
    combo.setCompleter(completer)
    apply_combo_dropdown_theme(combo)
    apply_completer_popup_theme(completer)


def style_filter_combo(combo) -> None:
    """Apply compact combo styling plus readable dropdown list colors."""
    combo.setStyleSheet(sales_compact_input_style())
    apply_combo_dropdown_theme(combo)


def _get_combo_dropdown_item_delegate_class():
    """Return a cached delegate class that paints combo popup hover rows."""
    global _COMBO_DROPDOWN_ITEM_DELEGATE
    if _COMBO_DROPDOWN_ITEM_DELEGATE is not None:
        return _COMBO_DROPDOWN_ITEM_DELEGATE

    from PySide6.QtCore import Qt, QSize
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QStyle, QStyledItemDelegate

    class ComboDropdownItemDelegate(QStyledItemDelegate):
        """Paint combo popup rows with readable hover and selection colors."""

        def paint(self, painter, option, index):
            """Render one dropdown row with theme hover feedback."""
            colors = _theme_colors()
            is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
            is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
            is_enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
            rect = option.rect
            selection_text = "#FFFFFF" if _is_light_theme() else colors["input_text"]

            if is_selected:
                background = QColor(colors["focus_border"])
                foreground = QColor(selection_text)
            elif is_hover and is_enabled:
                background = QColor(_popup_list_hover_background())
                foreground = QColor(colors["table_text"])
            else:
                background = QColor(colors["table_bg"])
                foreground = QColor(
                    colors["table_text"] if is_enabled else colors.get("muted_text", colors["table_text"])
                )

            painter.fillRect(rect, background)
            painter.setPen(foreground)
            painter.drawText(
                rect.adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
            )

        def sizeHint(self, option, index):
            """Keep dropdown rows tall enough for hover highlighting."""
            size = super().sizeHint(option, index)
            return QSize(size.width(), max(size.height(), 24))

    _COMBO_DROPDOWN_ITEM_DELEGATE = ComboDropdownItemDelegate
    return _COMBO_DROPDOWN_ITEM_DELEGATE


def apply_combo_dropdown_theme(combo) -> None:
    """Apply readable list colors to a QComboBox dropdown view."""
    if combo is None:
        return
    view = combo.view()
    if view is not None:
        view.setStyleSheet(completer_popup_list_style())
        _enable_popup_list_hover(view)
        delegate_cls = _get_combo_dropdown_item_delegate_class()
        view.setItemDelegate(delegate_cls(view))


def entry_picker_dialog_style() -> str:
    """Theme-aware modal search/picker dialog (party, stock, etc.)."""
    colors = _theme_colors()
    sel_bg = colors["focus_border"] if _is_light_theme() else "#3b82f6"
    sel_text = colors["input_text"] if _is_light_theme() else "white"
    hover_bg = colors.get("surface_alt", colors["app_bg"])
    return f"""
        QDialog {{
            background-color: {colors['app_bg']};
            color: {colors['input_text']};
        }}
        QLabel {{
            color: {colors['accent_label']};
            font-size: 11px;
            font-weight: bold;
            background: transparent;
            border: none;
        }}
        QLineEdit {{
            background-color: {colors['input_bg']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
            color: {colors['input_text']};
            font-size: 11px;
            padding: 5px 8px;
        }}
        QLineEdit:focus {{
            border: 1px solid {colors['focus_border']};
        }}
        QComboBox {{
            background-color: {colors['input_bg']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
            color: {colors['input_text']};
            font-size: 11px;
            padding: 5px 8px;
        }}
        QComboBox:focus {{
            border: 1px solid {colors['focus_border']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox::down-arrow {{
            image: none;
            width: 0px;
            height: 0px;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 4px solid {colors['muted_text']};
            margin-right: 4px;
        }}
        QListWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            border: 1px solid {colors['border']};
            font-size: 11px;
            selection-background-color: {sel_bg};
            selection-color: {sel_text};
        }}
        QListWidget::item {{
            padding: 6px;
        }}
        QListWidget::item:selected {{
            background-color: {sel_bg};
            color: {sel_text};
        }}
        QTableWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            gridline-color: {colors['border']};
            border: 1px solid {colors['border']};
            font-size: 11px;
            selection-background-color: {sel_bg};
            selection-color: {sel_text};
        }}
        QTableWidget::item:selected {{
            background-color: {sel_bg};
            color: {sel_text};
        }}
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['accent_label']};
            font-weight: bold;
            border: none;
            border-right: 1px solid {colors['border']};
            padding: 5px;
        }}
        QPushButton {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            padding: 5px 14px;
        }}
        QPushButton:hover {{
            background-color: {hover_bg};
        }}
        QRadioButton {{
            color: {colors['input_text']};
            font-size: 11px;
            font-weight: bold;
            spacing: 5px;
            background: transparent;
            border: none;
        }}
        QRadioButton::indicator {{
            width: 13px;
            height: 13px;
        }}
        QRadioButton:checked {{
            color: {colors['accent_label']};
        }}
    """


def entry_summary_dialog_style() -> str:
    """Theme-aware tax/summary dialog styling."""
    colors = _theme_colors()
    hover_bg = colors.get("surface_alt", colors["app_bg"])
    return f"""
        QDialog {{
            background-color: {colors['app_bg']};
            color: {colors['input_text']};
        }}
        QTableWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            gridline-color: {colors['border']};
            border: 1px solid {colors['border']};
            font-size: 11px;
        }}
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['accent_label']};
            font-weight: bold;
            border: none;
            border-right: 1px solid {colors['border']};
            padding: 5px;
        }}
        QPushButton {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            padding: 5px 14px;
        }}
        QPushButton:hover {{
            background-color: {hover_bg};
        }}
    """


def cash_tender_dialog_style() -> str:
    """Theme-aware Cash Tender payment dialog shown after Sales Entry save."""
    colors = _theme_colors()
    sel_bg = colors["focus_border"] if _is_light_theme() else "#3b82f6"
    sel_text = colors["input_text"] if _is_light_theme() else "white"
    return f"""
        QDialog {{
            background-color: {colors['app_bg']};
            color: {colors['input_text']};
        }}
        QLabel {{
            color: {colors['accent_label']};
            font-size: 14px;
            font-weight: bold;
            border: none;
            background: transparent;
        }}
        QLabel#headingLabel {{
            color: {colors['heading_text']};
            font-size: 18px;
            font-weight: bold;
        }}
        QLabel#instructionLabel {{
            color: {colors['muted_text']};
            font-size: 12px;
            font-weight: normal;
        }}
        QLabel#amountValueLabel {{
            color: {colors['heading_text']};
            font-size: 24px;
            font-weight: bold;
        }}
        QLabel#balanceReturnedLabel {{
            color: {colors['button_success']};
            font-size: 20px;
            font-weight: bold;
            border: 1px solid {colors['button_success']};
            border-radius: 4px;
            background-color: {colors['input_bg']};
        }}
        QLineEdit {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 4px;
            padding: 6px;
            font-size: 20px;
            font-weight: bold;
        }}
        QLineEdit:focus {{
            border: 1px solid {colors['focus_border']};
        }}
        QComboBox {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 4px;
            padding: 6px;
            font-size: 18px;
            font-weight: bold;
        }}
        QComboBox:focus {{
            border: 1px solid {colors['focus_border']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox::down-arrow {{
            image: none;
            width: 0px;
            height: 0px;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 4px solid {colors['muted_text']};
            margin-right: 4px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            selection-background-color: {sel_bg};
            selection-color: {sel_text};
        }}
    """


def entry_select_button_style() -> str:
    """Primary action button for picker dialogs."""
    colors = _theme_colors()
    hover = "#1565C0" if _is_light_theme() else "#2563eb"
    return f"""
        QPushButton {{
            background-color: {colors['button_primary']};
            color: white;
            border: none;
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            padding: 5px 14px;
        }}
        QPushButton:hover {{
            background-color: {hover};
        }}
    """


def entry_stock_ok_style() -> str:
    """Positive stock availability indicator."""
    colors = _theme_colors()
    color = "#2E7D32" if _is_light_theme() else colors["accent_highlight"]
    return (
        f"color: {color}; font-weight: bold; font-size: 11px; "
        "background: transparent; border: none;"
    )


def entry_stock_alert_style() -> str:
    """Out-of-stock / negative stock indicator."""
    if _is_light_theme():
        return (
            "color: #B71C1C; font-weight: bold; font-size: 11px; "
            "background-color: #FFCDD2; border: none;"
        )
    return (
        "color: #ffffff; font-weight: bold; font-size: 11px; "
        "background-color: #dc2626; border: none;"
    )


def entry_secondary_action_button_style() -> str:
    """Secondary compact action button (SMS, etc.)."""
    colors = _theme_colors()
    hover = colors["border"] if _is_light_theme() else "#475569"
    pressed = colors["app_bg"] if _is_light_theme() else "#1e293b"
    return f"""
        QPushButton {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
            padding: 4px 6px;
        }}
        QPushButton:hover {{
            background-color: {hover};
        }}
        QPushButton:pressed {{
            background-color: {pressed};
        }}
    """


def entry_grand_total_style() -> str:
    colors = _theme_colors()
    return f"""
        QLabel {{
            color: {colors['accent_highlight']};
            font-size: 42px;
            font-weight: bold;
            background: transparent;
            border: none;
            padding: 6px;
        }}
    """


def entry_save_button_style() -> str:
    colors = _theme_colors()
    hover = "#2E7D32" if _is_light_theme() else "#16a34a"
    pressed = "#1B5E20" if _is_light_theme() else "#15803d"
    return f"""
        QPushButton {{
            background-color: {colors['button_success']};
            color: white;
            border: none;
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            padding: 4px 8px;
        }}
        QPushButton:hover {{
            background-color: {hover};
        }}
        QPushButton:pressed {{
            background-color: {pressed};
        }}
    """


def dialog_page_style() -> str:
    colors = _theme_colors()
    return f"""
        QDialog {{
            background-color: {colors['app_bg']};
            color: {colors['input_text']};
        }}
    """


def message_warning_box_style() -> str:
    """Theme-aware QMessageBox styling for warning prompts."""
    colors = _theme_colors()
    hover = "#C62828" if _is_light_theme() else "#b91c1c"
    return f"""
        QMessageBox {{
            background-color: {colors['card_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
        }}
        QMessageBox QLabel {{
            color: {colors['input_text']};
            font-weight: bold;
            background: transparent;
            border: none;
        }}
        QMessageBox QPushButton {{
            background-color: {colors.get('button_warning', colors['button_primary'])};
            color: #FFFFFF;
            border: none;
            padding: 6px 14px;
            border-radius: 4px;
            min-width: 72px;
            font-weight: bold;
        }}
        QMessageBox QPushButton:hover {{
            background-color: {hover if _is_light_theme() else colors['button_primary']};
        }}
    """


def ui_memory_reset_button_style() -> str:
    """High-contrast Reset button for UI layout memory settings panels."""
    colors = _theme_colors()
    warning = colors.get("button_warning", colors["button_primary"])
    hover = colors["focus_border"]
    return f"""
        QPushButton {{
            background-color: {warning};
            color: #FFFFFF;
            border: 2px solid {warning};
            padding: 4px 20px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: bold;
            min-width: 100px;
            max-height: 34px;
        }}
        QPushButton:hover {{
            background-color: {hover};
            border-color: {hover};
            color: #FFFFFF;
        }}
        QPushButton:pressed {{
            background-color: {hover};
            color: #FFFFFF;
        }}
    """


def apply_reset_layouts_button(button) -> None:
    """Apply a visible Reset label and high-contrast styling to a QPushButton."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette

    colors = _theme_colors()
    warning = colors.get("button_warning", colors["button_primary"])
    button.setText("Reset")
    button.setFlat(False)
    button.setAutoDefault(False)
    button.setDefault(False)
    button.setMinimumWidth(100)
    button.setFixedHeight(34)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setAutoFillBackground(True)

    palette = button.palette()
    palette.setColor(QPalette.ColorRole.Button, QColor(warning))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#FFFFFF"))
    button.setPalette(palette)
    button.setStyleSheet(ui_memory_reset_button_style())
    button.update()


def loading_curtain_style() -> str:
    """Full-screen startup curtain background using the active theme."""
    colors = _theme_colors()
    return f"background-color: {colors['app_bg']};"


def loading_curtain_label_style(*, font_size: int = 36) -> str:
    """Startup loading headline text."""
    colors = _theme_colors()
    return (
        f"color: {colors['heading_text']}; "
        f"font-size: {font_size}px; "
        "font-weight: bold; "
        "background: transparent; "
        "border: none;"
    )


def loading_gateway_label_style(*, font_size: int = 28) -> str:
    """In-card loading label on the company gateway."""
    colors = _theme_colors()
    return (
        f"color: {colors['heading_text']}; "
        f"font-size: {font_size}px; "
        "font-weight: bold; "
        "background: transparent; "
        "border: none;"
    )


def message_critical_box_style() -> str:
    """Theme-aware QMessageBox styling for critical/error prompts."""
    colors = _theme_colors()
    hover = "#C62828" if _is_light_theme() else "#b91c1c"
    return f"""
        QMessageBox {{
            background-color: {colors['card_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['button_danger']};
        }}
        QMessageBox QLabel {{
            color: {colors['input_text']};
            font-weight: bold;
            background: transparent;
            border: none;
        }}
        QMessageBox QPushButton {{
            background-color: {colors['button_danger']};
            color: #FFFFFF;
            border: none;
            padding: 6px 14px;
            border-radius: 4px;
            min-width: 72px;
            font-weight: bold;
        }}
        QMessageBox QPushButton:hover {{
            background-color: {hover};
        }}
    """


def message_box_style_for_icon(icon) -> str:
    """Return the QMessageBox stylesheet for a standard icon role."""
    from PySide6.QtWidgets import QMessageBox

    if icon in (QMessageBox.Icon.Warning, QMessageBox.Warning):
        return message_warning_box_style()
    if icon in (QMessageBox.Icon.Critical, QMessageBox.Critical):
        return message_critical_box_style()
    return message_box_style()


def gateway_modal_dialog_style() -> str:
    """Shell styling for company-gateway child dialogs (open company, setup)."""
    colors = _theme_colors()
    return f"""
        QDialog {{
            background-color: {colors['app_bg']};
            color: {colors['input_text']};
        }}
        QLabel {{
            color: {colors['label_text']};
            background: transparent;
            border: none;
        }}
        QPushButton {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
            padding: 8px 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {colors.get('surface_alt', colors['panel_bg'])};
        }}
        QLineEdit, QComboBox, QDateEdit {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
            padding: 6px 8px;
        }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
            border: 1px solid {colors['focus_border']};
        }}
    """


def login_page_shell_style() -> str:
    """Theme-aware shell for the standalone login dialog."""
    colors = _theme_colors()
    return f"""
        QDialog {{
            background-color: {colors['app_bg']};
            color: {colors['input_text']};
        }}
        QDialog QLabel {{
            color: {colors['accent_label']};
            font-size: 14px;
            font-weight: bold;
            border: none;
            background: transparent;
        }}
        QLabel#titleLabel {{
            color: {colors['input_text']};
            font-size: 24px;
            font-weight: bold;
        }}
        QLabel#subtitleLabel, QLabel#hintLabel {{
            color: {colors['muted_text']};
            font-size: 14px;
            font-weight: normal;
        }}
        QLineEdit, QComboBox {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 4px;
            padding: 8px;
            font-size: 16px;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border: 1px solid {colors['focus_border']};
            background-color: {colors.get('surface_alt', colors['input_bg'])};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            selection-background-color: {colors['focus_border']};
            selection-color: {colors['input_text']};
        }}
        QPushButton#loginButton {{
            background-color: {colors['button_success']};
            color: #FFFFFF;
            border: none;
            border-radius: 4px;
            font-size: 16px;
            font-weight: bold;
        }}
        QPushButton#loginButton:hover {{
            background-color: {colors['focus_border']};
        }}
    """


def message_box_style() -> str:
    """Theme-aware QMessageBox shell and action buttons."""
    colors = _theme_colors()
    return f"""
        QMessageBox {{
            background-color: {colors['card_bg']};
            color: {colors['input_text']};
        }}
        QMessageBox QLabel {{
            color: {colors['input_text']};
            background: transparent;
            border: none;
        }}
        QMessageBox QPushButton {{
            background-color: {colors['button_primary']};
            color: #FFFFFF;
            border: none;
            padding: 6px 14px;
            border-radius: 4px;
            min-width: 72px;
            font-weight: bold;
        }}
        QMessageBox QPushButton:hover {{
            background-color: {colors['focus_border']};
        }}
    """


def section_panel_frame_style(selector: str = "QFrame") -> str:
    """Themed panel frame for summary sections, footers, and grouped controls."""
    colors = _theme_colors()
    return (
        f"{selector} {{ background-color: {colors['panel_bg']}; "
        f"border: 1px solid {colors['border']}; border-radius: 6px; }}"
    )


def complex_tool_dialog_style() -> str:
    """Full dialog styling for transfer, year-end, and similar multi-section dialogs."""
    from ui.scrollbar_style import scrollbar_stylesheet

    colors = _theme_colors()
    selection_text = colors["input_text"] if _is_light_theme() else "#FFFFFF"
    return f"""
        QDialog {{
            background-color: {colors['app_bg']};
            color: {colors['input_text']};
        }}
        QLabel {{
            color: {colors['label_text']};
            font-size: 13px;
            background: transparent;
            border: none;
        }}
        QLabel#titleLabel {{
            color: {colors['heading_text']};
            font-size: 20px;
            font-weight: bold;
        }}
        QLabel#fieldLabel {{
            color: {colors['label_text']};
            font-size: 13px;
            font-weight: bold;
        }}
        QLabel#warningLabel {{
            color: {colors['button_warning']};
            font-size: 13px;
            font-weight: bold;
        }}
        QLabel#recordsHintLabel, QLabel#selectionSummaryLabel {{
            color: {colors['muted_text']};
            font-size: 12px;
        }}
        QLabel#selectionSummaryLabel {{
            color: {colors['accent_label']};
            font-size: 13px;
            font-weight: bold;
        }}
        QComboBox, QDateEdit, QLineEdit {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 5px;
            padding: 8px 10px;
            font-size: 13px;
        }}
        QLineEdit:read-only {{
            color: {colors['muted_text']};
            background-color: {colors.get('surface_alt', colors['app_bg'])};
        }}
        QPushButton {{
            background-color: {colors.get('surface_alt', colors['panel_bg'])};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
            padding: 9px 16px;
            font-size: 13px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            border-color: {colors['focus_border']};
            background-color: {colors['panel_bg']};
        }}
        QPushButton#primaryButton, QPushButton#saveButton {{
            background-color: {colors['button_primary']};
            color: #FFFFFF;
            border: none;
        }}
        QPushButton#primaryButton:hover, QPushButton#saveButton:hover {{
            background-color: {colors['focus_border']};
        }}
        QPushButton#dangerButton {{
            background-color: {colors['button_danger']};
            color: #FFFFFF;
            border: none;
        }}
        QGroupBox {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            margin-top: 14px;
            padding-top: 18px;
        }}
        QTableWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            gridline-color: {colors['border']};
            selection-background-color: {colors['focus_border']};
            selection-color: {selection_text};
        }}
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['table_text']};
            border: none;
            padding: 7px;
            font-weight: bold;
        }}
        {scrollbar_stylesheet()}
    """


def line_edit_cell_editor_style() -> str:
    """Theme-aware QLineEdit style for table cell delegates."""
    return billing_cell_editor_inline_style()


def table_emphasis_text_hex() -> str:
    """Hex color for emphasized table row text."""
    return _theme_colors()["input_text"]


def accent_field_label_style() -> str:
    """Accent label chip used on voucher and note entry screens."""
    colors = _theme_colors()
    return f"""
        QLabel {{
            color: {colors['accent_label']};
            font-size: 12px;
            font-weight: bold;
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 4px;
            padding-left: 8px;
        }}
    """


def table_row_bg_color() -> str:
    """Background color for highlighted table rows."""
    colors = _theme_colors()
    return colors["panel_bg"] if _is_light_theme() else "#0f172a"


def semantic_positive_hex() -> str:
    """Theme-aware positive/success foreground color."""
    return _theme_colors()["button_success"]


def semantic_negative_hex() -> str:
    """Theme-aware negative/error foreground color."""
    return _theme_colors()["button_danger"]


def semantic_neutral_hex() -> str:
    """Theme-aware neutral/muted foreground color."""
    return _theme_colors()["muted_text"]


def semantic_warning_hex() -> str:
    """Theme-aware warning/accent foreground color."""
    return _theme_colors()["accent_label"]


def voucher_topbar_label_style() -> str:
    """Compact label style for voucher top-bar field captions."""
    colors = _theme_colors()
    return f"color: {colors['muted_text']}; font-size: 11px;"


def voucher_topbar_separator_style() -> str:
    """Vertical separator style for voucher top bars."""
    colors = _theme_colors()
    return f"background-color: {colors['border']};"


def report_action_button_style(*, danger: bool = False) -> str:
    """Theme-aware action button for report/management pages."""
    colors = _theme_colors()
    if danger:
        bg = colors["button_danger"]
        hover = colors["focus_border"] if _is_light_theme() else "#991b1b"
        border = colors["button_danger"]
    else:
        bg = colors["panel_bg"]
        hover = colors.get("surface_alt", colors["app_bg"])
        border = colors["border"]
    text = "#FFFFFF" if danger or not _is_light_theme() else colors["input_text"]
    return f"""
        QPushButton {{
            background-color: {bg};
            color: {text};
            border: 1px solid {border};
            border-radius: 4px;
            padding: 6px 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {hover};
            color: {text};
        }}
    """


def summary_profit_label_style(*, positive: bool = True) -> str:
    """Inline profit/loss summary label on financial statement pages."""
    color = semantic_positive_hex() if positive else semantic_negative_hex()
    return f"color: {color}; font-size: 13px; font-weight: bold;"


def net_sales_highlight_button_style(*, compact: bool = False) -> str:
    """Accent shortcut button for Net Sales Book entry points."""
    colors = _theme_colors()
    border_width = 1 if compact else 2
    font_size = 10 if compact else 11
    padding = "3px 10px" if compact else "8px 16px"
    radius = 3 if compact else 4
    return f"""
        QPushButton {{
            background-color: {colors['button_primary']};
            color: {colors['accent_label']};
            border: {border_width}px solid {colors['accent_label']};
            border-radius: {radius}px;
            font-size: {font_size}px;
            font-weight: bold;
            padding: {padding};
        }}
        QPushButton:hover {{
            background-color: {colors['focus_border']};
            color: #FFFFFF;
        }}
        QPushButton:pressed {{
            background-color: {colors['button_primary']};
            color: #FFFFFF;
        }}
    """


def net_sales_result_chip_style(*, positive: bool = True) -> str:
    """Highlighted net-result summary chip on Net Sales Book."""
    colors = _theme_colors()
    value_color = semantic_positive_hex() if positive else semantic_negative_hex()
    return f"""
        QLabel {{
            color: {value_color};
            background-color: transparent;
            border: none;
            font-size: 20px;
            font-weight: bold;
            padding: 4px 8px;
        }}
    """


def metric_card_style(*, accent_hex: str | None = None) -> str:
    """Small metric card frame used on summary dashboards."""
    colors = _theme_colors()
    accent = accent_hex or colors["button_primary"]
    return f"""
        QFrame {{
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-left: 4px solid {accent};
            border-radius: 6px;
        }}
        QLabel {{
            background: transparent;
            border: none;
            color: {colors['input_text']};
        }}
    """


# =============================================================================
# Master / company / accounts pages (shared across File menu & Masters)
# =============================================================================

def master_page_background_style() -> str:
    colors = _theme_colors()
    return f"background-color: {colors['app_bg']}; color: {colors['input_text']};"


def master_scroll_page_style(widget_id: str | None = None) -> str:
    colors = _theme_colors()
    app_bg = colors["app_bg"]
    text = colors["input_text"]
    if widget_id:
        return (
            f"QWidget#{widget_id} {{ background-color: {app_bg}; color: {text}; }}\n"
            f"QScrollArea {{ border: none; background-color: {app_bg}; }}"
        )
    return f"QScrollArea {{ border: none; background-color: {app_bg}; }}"


def master_page_title_style(font_size: int = 28) -> str:
    colors = _theme_colors()
    return (
        f"color: {colors['heading_text']}; font-size: {font_size}px; font-weight: bold; "
        "background: transparent; border: none;"
    )


def master_page_subtitle_style(font_size: int = 14) -> str:
    colors = _theme_colors()
    muted = colors["label_text"] if _is_light_theme() else colors["muted_text"]
    return (
        f"color: {muted}; font-size: {font_size}px; "
        "background: transparent; border: none;"
    )


def master_empty_state_style() -> str:
    colors = _theme_colors()
    return f"""
        QLabel {{
            color: {colors['accent_label']};
            font-size: 15px;
            font-weight: bold;
            padding: 36px 20px;
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
        }}
    """


def master_nav_primary_button_style() -> str:
    colors = _theme_colors()
    hover = colors["focus_border"] if _is_light_theme() else "#3b82f6"
    return f"""
        QPushButton {{
            background-color: {colors['button_primary']};
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
    """


def master_nav_secondary_button_style() -> str:
    colors = _theme_colors()
    hover = colors.get("surface_alt", colors["app_bg"])
    return f"""
        QPushButton {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            padding: 10px 20px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
    """


def master_tab_widget_style() -> str:
    colors = _theme_colors()
    hover = colors.get("surface_alt", colors["app_bg"])
    tab_text = colors["label_text"] if _is_light_theme() else colors["muted_text"]
    return f"""
        QTabWidget::pane {{
            background-color: {colors['app_bg']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
        }}
        QTabBar::tab {{
            background-color: {colors['panel_bg']};
            color: {tab_text};
            padding: 10px 20px;
            border: 1px solid {colors['border']};
            border-bottom: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background-color: {colors['app_bg']};
            color: {colors['heading_text']};
            border-bottom: 2px solid {colors['focus_border']};
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {hover};
        }}
    """


def master_table_style(*, inline_cell_editors: bool = True) -> str:
    colors = _theme_colors()
    sel_text = colors["input_text"] if _is_light_theme() else "white"
    edit_cell_bg = billing_cell_edit_background()
    embedded_editors = ""
    if inline_cell_editors:
        embedded_editors = f"""
        QTableWidget::item:focus {{
            background-color: {edit_cell_bg};
            border: 1px solid {colors['focus_border']};
        }}
        QTableWidget QLineEdit {{
            background-color: {edit_cell_bg};
            color: {colors['table_text']};
            border: none;
            border-bottom: 2px solid {colors['focus_border']};
            border-radius: 0px;
            padding: 0px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            selection-background-color: {colors['focus_border']};
            selection-color: #FFFFFF;
        }}
        QTableWidget QLineEdit:focus {{
            background-color: {edit_cell_bg};
            border: none;
            border-bottom: 2px solid {colors['focus_border']};
        }}
        QTableWidget QComboBox {{
            background-color: {edit_cell_bg};
            color: {colors['table_text']};
            border: none;
            border-bottom: 2px solid {colors['focus_border']};
            border-radius: 0px;
            padding: 0px 4px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            min-height: 0px;
        }}
        QTableWidget QComboBox:focus {{
            background-color: {edit_cell_bg};
            border: none;
            border-bottom: 2px solid {colors['focus_border']};
        }}
        """
    return f"""
        QTableWidget {{
            background-color: {colors['table_bg']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            gridline-color: {colors['border']};
            selection-background-color: {colors['focus_border']};
            color: {colors['table_text']};
        }}
        QTableWidget::item {{
            padding: 8px;
            color: {colors['table_text']};
        }}
        QTableWidget::item:selected {{
            background-color: {colors['focus_border']};
            color: {sel_text};
        }}
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['heading_text']};
            padding: 10px;
            border: none;
            font-weight: bold;
        }}
        {embedded_editors}
    """


def master_primary_action_button_style(padding: str = "10px 16px", font_size: int = 13) -> str:
    colors = _theme_colors()
    hover = colors["focus_border"] if _is_light_theme() else "#2563eb"
    return f"""
        QPushButton {{
            background-color: {colors['button_primary']};
            color: white;
            border: none;
            border-radius: 8px;
            font-size: {font_size}px;
            font-weight: bold;
            padding: {padding};
        }}
        QPushButton:hover {{ background-color: {hover}; }}
    """


def master_save_button_style() -> str:
    return entry_save_button_style()


def master_clear_button_style() -> str:
    colors = _theme_colors()
    hover = colors["border"] if _is_light_theme() else "#4b5563"
    pressed = colors["app_bg"] if _is_light_theme() else "#374151"
    return f"""
        QPushButton {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            padding: 6px 16px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ background-color: {pressed}; }}
    """


def master_profile_stylesheet() -> str:
    lc = legacy_colors()
    colors = _theme_colors()
    field_color = colors["label_text"] if _is_light_theme() else lc["text_secondary"]
    return f"""
        QWidget {{
            background-color: {lc['background']};
            color: {lc['text_primary']};
        }}
        QLabel {{
            color: {lc['text_primary']};
            font-size: 13px;
            background: transparent;
            border: none;
        }}
        QLabel.section {{
            color: {colors['heading_text']};
            font-size: 16px;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        QLabel.field {{
            color: {field_color};
            font-weight: bold;
            margin-top: 5px;
        }}
        QLabel.value {{
            color: {lc['text_primary']};
            background-color: {lc['card']};
            padding: 8px;
            border-radius: 4px;
            border: 1px solid {lc['border']};
        }}
        QPushButton {{
            background-color: {lc['primary']};
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {colors['focus_border']};
        }}
    """


def master_combo_style() -> str:
    colors = _theme_colors()
    sel_text = colors["input_text"] if _is_light_theme() else "white"
    return (
        sales_compact_input_style()
        + f"""
        QComboBox QAbstractItemView {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            selection-background-color: {colors['focus_border']};
            selection-color: {sel_text};
        }}
    """
    )


def master_textarea_style() -> str:
    colors = _theme_colors()
    return f"""
        QTextEdit {{
            background-color: {colors['input_bg']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
            color: {colors['input_text']};
            font-size: 12px;
            padding: 4px 8px;
        }}
        QTextEdit:focus {{
            border: 1px solid {colors['focus_border']};
        }}
    """


def master_panel_frame_style(object_name: str | None = None) -> str:
    colors = _theme_colors()
    selector = f"QFrame#{object_name}" if object_name else "QFrame"
    return f"""
        {selector} {{
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            padding: 8px;
        }}
    """


def master_preview_placeholder_style() -> str:
    colors = _theme_colors()
    muted = colors["label_text"] if _is_light_theme() else colors["muted_text"]
    return f"""
        QLabel {{
            background-color: {colors['panel_bg']};
            color: {muted};
            border: 1px solid {colors['border']};
            border-radius: 10px;
            font-size: 13px;
            padding: 10px;
        }}
    """


def master_section_heading_style(font_size: int = 14) -> str:
    colors = _theme_colors()
    return (
        f"color: {colors['accent_label']}; font-size: {font_size}px; font-weight: bold; "
        "background: transparent; border: none; padding: 0px; margin: 0px;"
    )


def master_form_field_label_style(font_size: int = 12) -> str:
    colors = _theme_colors()
    muted = colors["label_text"] if _is_light_theme() else colors["muted_text"]
    return (
        f"color: {muted}; font-size: {font_size}px; font-weight: bold; "
        "background: transparent; border: none; padding: 0px; margin: 0px;"
    )


def master_form_hint_style() -> str:
    colors = _theme_colors()
    hint = colors["heading_text"] if _is_light_theme() else colors["button_primary"]
    return (
        f"color: {hint}; font-size: 11px; font-weight: bold; "
        "margin: 2px 0; background: transparent; border: none;"
    )


def master_form_input_style() -> str:
    colors = _theme_colors()
    arrow = colors["label_text"] if _is_light_theme() else colors["muted_text"]
    sel_text = colors["input_text"] if _is_light_theme() else "white"
    return f"""
        QLineEdit, QTextEdit, QComboBox {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 12px;
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
            border: 2px solid {colors['focus_border']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 30px;
            background-color: {colors['input_bg']};
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid {arrow};
            margin-right: 5px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            selection-background-color: {colors['focus_border']};
            selection-color: {sel_text};
        }}
    """


def master_form_footer_style() -> str:
    colors = _theme_colors()
    return f"""
        QWidget {{
            background-color: {colors['app_bg']};
            border-top: 1px solid {colors['border']};
        }}
    """


def master_danger_action_button_style() -> str:
    colors = _theme_colors()
    hover = "#C62828" if _is_light_theme() else "#dc2626"
    return f"""
        QPushButton {{
            background-color: {colors['button_danger']};
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
    """


def master_dialog_heading_style(font_size: int = 16) -> str:
    colors = _theme_colors()
    return f"font-weight: bold; font-size: {font_size}px; color: {colors['accent_label']};"


def master_form_section_divider_style() -> str:
    colors = _theme_colors()
    return f"""
        QLabel {{
            color: {colors['heading_text']};
            font-size: 13px;
            font-weight: bold;
            background: transparent;
            border: none;
            border-bottom: 1px solid {colors['border']};
            padding: 5px 0px 3px 0px;
            margin: 0px;
        }}
    """


def billing_cell_edit_background() -> str:
    """Highlight background for billing grid cells that are open for editing."""
    colors = _theme_colors()
    if _is_light_theme():
        return "#D2F2F2"
    return "#1e3a52"


def billing_cell_editor_style() -> str:
    """Theme-aware QLineEdit for billing table cell delegates."""
    return billing_cell_editor_inline_style()


def billing_cell_editor_inline_style() -> str:
    """Flush QLineEdit that fills the full table cell with edit-mode border highlight."""
    colors = _theme_colors()
    edit_cell_bg = billing_cell_edit_background()
    return f"""
        QLineEdit {{
            background-color: {edit_cell_bg};
            color: {colors['table_text']};
            border: 2px solid {colors['focus_border']};
            border-radius: 0px;
            padding: 0px 2px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            selection-background-color: {colors['focus_border']};
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus {{
            background-color: {edit_cell_bg};
            border: 2px solid {colors['focus_border']};
        }}
    """


def sales_editing_cell_editor_style() -> str:
    """Sales Entry in-cell editor with full colored border highlight."""
    colors = _theme_colors()
    edit_cell_bg = billing_cell_edit_background()
    return f"""
        QLineEdit {{
            background-color: {edit_cell_bg};
            color: {colors['table_text']};
            border: 2px solid {colors['focus_border']};
            border-radius: 1px;
            padding: 0px 2px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            selection-background-color: {colors['focus_border']};
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus {{
            background-color: {edit_cell_bg};
            border: 2px solid {colors['focus_border']};
        }}
    """


def prepare_billing_cell_editor(editor) -> None:
    """Apply flush in-cell edit highlight styling to a table QLineEdit editor."""
    try:
        editor.setFrame(False)
    except AttributeError:
        pass
    editor.setStyleSheet(billing_cell_editor_inline_style())


def prepare_sales_cell_editor(editor) -> None:
    """Apply Sales Entry in-cell editor with full border highlight."""
    try:
        editor.setFrame(False)
    except AttributeError:
        pass
    editor.setStyleSheet(sales_editing_cell_editor_style())


def grid_selection_pen_color() -> str:
    """Hex color for outline-only table row selection pens."""
    return _theme_colors()["focus_border"]


def completer_popup_list_style() -> str:
    """Theme-aware QListView style for product/party completer popups."""
    colors = _theme_colors()
    selection_text = "#FFFFFF" if _is_light_theme() else colors["input_text"]
    hover_bg = _popup_list_hover_background()
    return f"""
        QListView {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            border: 1px solid {colors['focus_border']};
            font-size: 10px;
            selection-background-color: {colors['focus_border']};
            selection-color: {selection_text};
            outline: 0;
        }}
        QListView::item {{
            padding: 4px 6px;
            min-height: 24px;
            color: {colors['table_text']};
            background-color: {colors['table_bg']};
        }}
        QListView::item:hover {{
            background-color: {hover_bg};
            color: {colors['table_text']};
        }}
        QListView::item:selected {{
            background-color: {colors['focus_border']};
            color: {selection_text};
        }}
        QListView::item:selected:hover {{
            background-color: {colors['focus_border']};
            color: {selection_text};
        }}
    """


def popup_list_delegate_colors() -> dict:
    """Background/text colors for custom completer popup delegates."""
    colors = _theme_colors()
    return {
        "selected_bg": colors["focus_border"],
        "normal_bg": colors["table_bg"],
        "text": colors["table_text"],
    }


def footer_transparent_input_style() -> str:
    """Transparent inline footer field (e.g. round-off inside a chip)."""
    colors = _theme_colors()
    return f"""
        QLineEdit {{
            background-color: transparent;
            border: none;
            color: {colors['input_text']};
            font-size: 10px;
            padding: 0px;
        }}
    """


def discount_percent_micro_label_style() -> str:
    """Tiny percent hint label beside discount fields."""
    colors = _theme_colors()
    accent = colors.get("accent_soft", colors["focus_border"])
    return f"QLabel {{ color: {accent}; font-size: 7px; padding: 0px; margin: 0px; }}"


def report_detail_caption_style() -> str:
    """Caption style for drill-down report dialog headers."""
    colors = _theme_colors()
    return f"color: {colors['accent_label']}; font-size: 12px; font-weight: bold;"


def report_detail_value_style() -> str:
    """Value style for drill-down report dialog headers."""
    colors = _theme_colors()
    return f"color: {colors['input_text']}; font-size: 12px; font-weight: bold;"


def collection_tally_frame_style() -> str:
    """Highlighted tally summary frame on collection report."""
    colors = _theme_colors()
    return f"""
        QFrame {{
            background-color: {colors['panel_bg']};
            border: 2px solid {colors['button_warning']};
            border-radius: 6px;
            padding: 4px;
        }}
    """


def collection_tally_label_style() -> str:
    """Label style inside collection tally frame."""
    colors = _theme_colors()
    return (
        f"color: {colors['accent_label']}; font-size: 14px; "
        f"font-weight: bold; padding: 4px;"
    )


def chart_palette() -> dict:
    """Semantic chart series and axis colors for analysis reports."""
    colors = _theme_colors()
    return {
        "positive": colors["button_success"],
        "negative": colors["button_danger"],
        "primary": colors["focus_border"],
        "warning": colors.get("button_warning", colors["accent_label"]),
        "axis_label": colors["muted_text"],
        "grid_line": colors["border"],
        "legend_text": colors["input_text"],
        "legend_border": colors["border"],
        "table_text": colors["input_text"],
        "highlight_opening": colors["panel_bg"],
        "highlight_closing": colors.get("surface_alt", colors["panel_bg"]),
    }


def barcode_tool_button_style(variant: str = "primary") -> str:
    """Theme-aware action button for barcode manager toolbars."""
    colors = _theme_colors()
    light = _is_light_theme()
    variants = {
        "primary": (colors["button_primary"], "#1565C0" if light else "#1d4ed8"),
        "success": (colors["button_success"], "#15803d"),
        "danger": (colors["button_danger"], "#C62828" if light else "#b91c1c"),
        "warning": (colors.get("button_warning", "#ea580c"), "#c2410c"),
    }
    base, hover = variants.get(variant, variants["primary"])
    return f"""
        QPushButton {{
            background-color: {base};
            color: #ffffff;
            border: none;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
            padding: 6px 16px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ background-color: {base}; }}
    """


def barcode_manager_shell_style() -> str:
    """Root dialog background for barcode manager."""
    colors = _theme_colors()
    return f"QDialog {{ background-color: {colors['app_bg']}; color: {colors['input_text']}; }}"


def barcode_manager_strip_style() -> str:
    """Panel strip frame inside barcode manager."""
    colors = _theme_colors()
    return f"""
        QFrame {{
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 4px;
        }}
    """


def barcode_manager_input_style() -> str:
    """Line edit and combo style for barcode manager."""
    colors = _theme_colors()
    return f"""
        QLineEdit, QComboBox {{
            background-color: {colors['input_bg']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
            color: {colors['input_text']};
            font-size: 12px;
            font-weight: bold;
            padding: 4px 6px;
            min-height: 22px;
        }}
        QLineEdit:focus, QComboBox:focus {{ border: 1px solid {colors['focus_border']}; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
    """


def barcode_manager_compact_input_style() -> str:
    """Compact single-line field for barcode manager matrices."""
    colors = _theme_colors()
    return f"""
        QLineEdit {{
            background-color: {colors['input_bg']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
            color: {colors['input_text']};
            font-size: 11px;
            font-weight: bold;
            padding: 1px 6px;
            min-height: 0px;
            max-height: 26px;
        }}
        QLineEdit:focus {{ border: 1px solid {colors['focus_border']}; }}
    """


def barcode_manager_table_style() -> str:
    """Data table style for barcode manager queue."""
    colors = _theme_colors()
    return f"""
        QTableWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            gridline-color: {colors['border']};
            font-size: 11px;
            border: 1px solid {colors['border']};
            border-radius: 3px;
        }}
        QTableWidget::item:selected {{
            background-color: {colors['focus_border']};
            color: #ffffff;
        }}
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['accent_label']};
            font-weight: bold;
            border: none;
            border-right: 1px solid {colors['border']};
            padding: 5px;
        }}
    """


def barcode_manager_queue_cell_editor_style() -> str:
    """Flush in-cell editor for barcode print queue editable columns."""
    colors = _theme_colors()
    edit_cell_bg = billing_cell_edit_background()
    text_color = colors["input_text"]
    return f"""
        QLineEdit {{
            background-color: {edit_cell_bg};
            color: {text_color};
            border: 1px solid {colors['focus_border']};
            border-radius: 0px;
            padding: 0px 1px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            min-height: 0px;
            selection-background-color: {colors['focus_border']};
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus {{
            background-color: {edit_cell_bg};
            color: {text_color};
            border: 1px solid {colors['focus_border']};
        }}
    """


def prepare_barcode_queue_cell_editor(editor) -> None:
    """Apply compact flush styling to barcode print queue cell editors."""
    from PySide6.QtGui import QPalette, QColor

    try:
        editor.setFrame(False)
    except AttributeError:
        pass
    colors = _theme_colors()
    edit_cell_bg = billing_cell_edit_background()
    text_color = QColor(colors["input_text"])
    palette = editor.palette()
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Base, QColor(edit_cell_bg))
    palette.setColor(QPalette.ColorRole.WindowText, text_color)
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["focus_border"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    editor.setPalette(palette)
    editor.setAutoFillBackground(True)
    editor.setStyleSheet(barcode_manager_queue_cell_editor_style())


def barcode_manager_queue_table_style() -> str:
    """Input-style queue grid for barcode print label rows."""
    colors = _theme_colors()
    edit_cell_bg = billing_cell_edit_background()
    return f"""
        QTableWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            gridline-color: {colors['border']};
            font-size: 11px;
            font-weight: bold;
            border: 1px solid {colors['border']};
            border-radius: 3px;
            selection-background-color: transparent;
            selection-color: {colors['table_text']};
        }}
        QTableWidget::item {{
            padding: 1px 3px;
            border: none;
        }}
        QTableWidget::item:selected {{
            background-color: {colors['focus_border']};
            color: #ffffff;
        }}
        QTableWidget::item:focus {{
            background-color: {edit_cell_bg};
            color: {colors['input_text']};
            border: 1px solid {colors['focus_border']};
        }}
        QTableWidget QLineEdit {{
            background-color: {edit_cell_bg};
            color: {colors['input_text']};
            border: 1px solid {colors['focus_border']};
            border-radius: 0px;
            padding: 0px 1px;
            margin: 0px;
            font-size: 11px;
            font-weight: bold;
            min-height: 0px;
            selection-background-color: {colors['focus_border']};
            selection-color: #FFFFFF;
        }}
        QTableWidget QLineEdit:focus {{
            background-color: {edit_cell_bg};
            color: {colors['input_text']};
        }}
        QHeaderView::section {{
            background-color: {colors['table_header_bg']};
            color: {colors['accent_label']};
            font-weight: bold;
            border: none;
            border-right: 1px solid {colors['border']};
            padding: 5px;
        }}
    """


def barcode_manager_matrix_style() -> str:
    """Price-key matrix table inside barcode manager."""
    colors = _theme_colors()
    alt = colors.get("surface_alt", colors["panel_bg"])
    return f"""
        QTableWidget {{
            background-color: {colors['table_bg']};
            color: {colors['table_text']};
            gridline-color: {colors['border']};
            font-size: 13px;
            font-weight: bold;
            border: 1px solid {colors['border']};
            border-radius: 3px;
        }}
        QTableWidget::item {{
            padding: 0px;
        }}
        QTableWidget::item:selected {{
            background-color: {colors['focus_border']};
            color: #ffffff;
        }}
        QTableWidget QLineEdit {{
            background-color: {alt};
            color: {colors['input_text']};
            font-weight: bold;
            border: 1px solid {colors['focus_border']};
        }}
    """


def barcode_manager_group_box_style() -> str:
    """Grouped section style for barcode manager."""
    colors = _theme_colors()
    return f"""
        QGroupBox {{
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 4px;
            color: {colors['accent_label']};
            font-weight: bold;
            font-size: 10px;
            margin-top: 8px;
            padding-top: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }}
    """


def barcode_manager_tab_style() -> str:
    """Tab widget style for barcode manager."""
    colors = _theme_colors()
    return f"""
        QTabWidget::pane {{
            border: 1px solid {colors['border']};
            border-radius: 4px;
            background-color: {colors['app_bg']};
        }}
        QTabBar::tab {{
            background-color: {colors['panel_bg']};
            color: {colors['muted_text']};
            font-weight: bold;
            font-size: 12px;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}
        QTabBar::tab:selected {{
            background-color: {colors['surface_alt']};
            color: {colors['accent_label']};
        }}
    """


def barcode_manager_spin_style() -> str:
    """Spin box style for barcode manager."""
    colors = _theme_colors()
    return f"""
        QSpinBox {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            font-weight: bold;
            border: 1px solid {colors['border']};
            border-radius: 3px;
            padding: 2px 4px;
            min-height: 28px;
            max-height: 28px;
        }}
    """


def barcode_manager_checkbox_style() -> str:
    """Checkbox style for barcode manager."""
    from ui.checkbox_style import checkbox_indicator_style

    colors = _theme_colors()
    return f"""
        QCheckBox {{
            color: {colors['input_text']};
            spacing: 4px;
            background: transparent;
        }}
        {checkbox_indicator_style(16, 16)}
    """


def barcode_manager_compact_button_style() -> str:
    """Small neutral button inside barcode manager."""
    colors = _theme_colors()
    hover = colors.get("surface_alt", colors["panel_bg"])
    return f"""
        QPushButton {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            padding: 3px 8px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
    """


def barcode_manager_active_button_style() -> str:
    """Highlighted quick-select button in barcode manager."""
    colors = _theme_colors()
    base = colors["focus_border"]
    hover = colors["button_primary"] if _is_light_theme() else "#039BE5"
    return f"""
        QPushButton {{
            background-color: {base};
            color: #ffffff;
            border: 1px solid {colors['focus_border']};
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            padding: 3px 8px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
    """


def barcode_manager_stepper_button_style() -> str:
    """D-pad and font-size stepper buttons."""
    colors = _theme_colors()
    alt = colors.get("surface_alt", colors["panel_bg"])
    return f"""
        QPushButton {{
            background-color: {alt};
            color: {colors['input_text']};
            border: 1px solid {colors['focus_border']};
            border-radius: 4px;
            font-size: 18px;
            font-weight: bold;
            padding: 0px;
        }}
        QPushButton:hover:enabled {{ background-color: {colors['focus_border']}; }}
        QPushButton:disabled {{
            color: {colors['muted_text']};
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
        }}
    """


def barcode_manager_label_style() -> str:
    """Accent label style inside barcode manager panels."""
    colors = _theme_colors()
    return f"color: {colors['accent_label']}; font-weight: bold; font-size: 11px;"


def barcode_manager_muted_hint_style() -> str:
    """Muted hint label below barcode search popups."""
    colors = _theme_colors()
    return f"color: {colors['muted_text']}; font-size: 10px;"


def credit_debit_footer_button_style(kind: str) -> str:
    """Footer action buttons on credit/debit note entry."""
    mapping = {
        "save": sales_primary_button_style,
        "primary": sales_primary_button_style,
        "update": sales_primary_button_style,
        "neutral": sales_compact_button_style,
        "exit": sales_compact_button_style,
        "danger": sales_danger_button_style,
    }
    factory = mapping.get(kind, sales_compact_button_style)
    base = factory()
    return (
        base.replace("font-size: 10px;", "font-size: 12px;")
        .replace("padding: 3px 6px;", "padding: 8px 12px;")
        .replace("border-radius: 3px;", "border-radius: 5px;")
    )


def calculator_dialog_style() -> str:
    """Root calculator dialog shell."""
    colors = _theme_colors()
    return f"""
        QDialog {{
            background-color: {colors['app_bg']};
            color: {colors['input_text']};
        }}
    """


def calculator_display_frame_style() -> str:
    """Calculator two-line display container."""
    colors = _theme_colors()
    return f"""
        QFrame {{
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            padding: 5px;
        }}
    """


def calculator_expression_style() -> str:
    """Calculator expression line."""
    colors = _theme_colors()
    return f"""
        QLabel {{
            background-color: transparent;
            color: {colors['muted_text']};
            font-size: 14px;
            padding: 2px;
        }}
    """


def calculator_main_display_style() -> str:
    """Calculator main numeric display."""
    colors = _theme_colors()
    return f"""
        QLineEdit {{
            background-color: transparent;
            color: {colors['input_text']};
            border: none;
            font-size: 28px;
            font-weight: 400;
            padding: 5px;
        }}
    """


def entry_picker_field_style() -> str:
    """Left segment of a line-edit + picker button compound field."""
    colors = _theme_colors()
    return f"""
        QLineEdit {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-right: none;
            border-top-left-radius: 4px;
            border-bottom-left-radius: 4px;
            border-top-right-radius: 0px;
            border-bottom-right-radius: 0px;
            padding: 4px 8px;
            font-size: 12px;
        }}
        QLineEdit:focus {{ border-color: {colors['focus_border']}; }}
    """


def entry_picker_button_style() -> str:
    """Right picker button segment paired with entry_picker_field_style."""
    colors = _theme_colors()
    hover = colors.get("surface_alt", colors["panel_bg"])
    return f"""
        QPushButton {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-top-left-radius: 0px;
            border-bottom-left-radius: 0px;
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
            padding: 0px;
            font-size:  12px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
    """


def calculator_button_style(style_class: str) -> str:
    """Per-button calculator keypad styles."""
    colors = _theme_colors()
    alt = colors.get("surface_alt", colors["panel_bg"])
    if style_class == "memory":
        bg, hover = colors["panel_bg"], alt
    elif style_class == "clear":
        bg, hover = colors["button_danger"], "#C62828" if _is_light_theme() else "#b91c1c"
    elif style_class == "operation":
        bg, hover = colors["focus_border"], colors["button_primary"]
    elif style_class == "equals":
        bg, hover = colors["button_success"], "#15803d"
    else:
        bg, hover = alt, colors["panel_bg"]
    text_color = colors["input_text"] if style_class == "number" else "#ffffff"
    return f"""
        QPushButton {{
            background-color: {bg};
            color: {text_color};
            border: 1px solid {colors['border']};
            border-radius: 4px;
            font-size: 16px;
            font-weight: bold;
            min-height: 48px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ background-color: {bg}; }}
    """