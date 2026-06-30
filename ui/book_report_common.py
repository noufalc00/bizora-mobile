"""
Shared UI for Sales Book, Sales Return Book, Purchase Book, and Purchase Return Book.
"""
from html import escape
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QDate, QObject, QThread, QTimer, Signal, QStringListModel
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QCompleter, QComboBox, QDateEdit, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QMenu
from bizora_core.book_report_common import resolve_active_company_id, safe_float
from .report_preview_utils import table_widget_to_html
from .table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from .universal_preview_dialog import UniversalPreviewDialog
from .ui_memory import UiMemoryMixin, memory_table_attr_slug
from ui.date_formats import (
    configure_qdate_edit,
    format_display_date,
    is_date_field_key,
    prepare_report_date_edit,
    qdate_to_db,
    qdate_to_display,
    REPORT_DATE_FIELD_WIDTH,
)
from ui import theme
BOOK_REPORT_ACTION_BUTTON_HEIGHT = 28
BOOK_REPORT_DATE_FIELD_WIDTH = REPORT_DATE_FIELD_WIDTH

def _report_theme_colors() -> dict[str, str]:
    from ui import theme
    return theme._theme_colors()

def _report_is_light() -> bool:
    from ui import theme
    return theme._is_light_theme()

def compact_label_style() -> str:
    """Compact label style matching Sales Entry."""
    colors = _report_theme_colors()
    return f"\n        QLabel {{\n            color: {colors['accent_label']};\n            font-weight: bold;\n            font-size: 11px;\n            padding: 0px 2px;\n            background: transparent;\n            border: none;\n        }}\n    "

def compact_input_style() -> str:
    """Compact input style matching Sales Entry."""
    from ui import theme
    return theme.sales_compact_input_style()

def compact_date_style() -> str:
    """Compact date field style with specific width."""
    from ui import theme
    return theme.sales_compact_input_style()

def compact_combo_style() -> str:
    """Compact combo box style with specific width."""
    from ui import theme
    return theme.sales_compact_input_style()

def compact_search_style() -> str:
    """Compact search field style."""
    from ui import theme
    return theme.sales_compact_input_style()

def compact_primary_button_style() -> str:
    """Compact primary button style matching Sales Entry."""
    from ui import theme
    return theme.sales_primary_button_style()

def compact_secondary_button_style() -> str:
    """Compact secondary button style."""
    from ui import theme
    return theme.sales_compact_button_style()

def compact_topbar_frame_style() -> str:
    """Compact topbar frame style."""
    from ui import theme
    return theme.sales_action_frame_style()

def page_background_style() -> str:
    """Standard page background/text colors for report and book modules."""
    colors = _report_theme_colors()
    return f"background-color: {colors['app_bg']}; color: {colors['input_text']};"

def report_page_shell_style(widget_id: str | None=None) -> str:
    """Full-page shell for standalone report widgets in light and dark themes."""
    from ui import theme
    colors = _report_theme_colors()
    c = colors
    hover = c['focus_border']
    selector = f'QWidget#{widget_id}' if widget_id else 'QWidget'
    return f"""\n        {selector} {{\n            background-color: {c['app_bg']};\n            color: {c['input_text']};\n            font-family: "Segoe UI", Arial, sans-serif;\n        }}\n        QLabel {{\n            background: transparent;\n            border: none;\n            color: {c['input_text']};\n        }}\n        QComboBox, QDateEdit {{\n            background-color: {c['input_bg']};\n            color: {c['input_text']};\n            border: 1px solid {c['border']};\n            border-radius: 4px;\n            padding: 4px 8px;\n            font-size: 12px;\n        }}\n        QComboBox:focus, QDateEdit:focus {{\n            border: 1px solid {c['focus_border']};\n        }}\n        QComboBox::drop-down {{\n            border: none;\n            width: 22px;\n            background-color: {c['input_bg']};\n        }}\n        QComboBox QAbstractItemView {{\n            background-color: {c['input_bg']};\n            color: {c['input_text']};\n            border: 1px solid {c['border']};\n            selection-background-color: {c['focus_border']};\n            selection-color: #FFFFFF;\n        }}\n        QPushButton {{\n            background-color: {c['button_primary']};\n            color: #FFFFFF;\n            border: none;\n            border-radius: 4px;\n            font-size: 11px;\n            font-weight: bold;\n            padding: 6px 14px;\n        }}\n        QPushButton:hover {{\n            background-color: {hover};\n        }}\n    """ + theme.scrollbar_stylesheet()

def report_filter_frame_style() -> str:
    """Theme-aware filter bar frame for report pages."""
    colors = _report_theme_colors()
    return f"\n        QFrame {{\n            background-color: {colors['panel_bg']};\n            border: 1px solid {colors['border']};\n            border-radius: 6px;\n        }}\n        QLabel {{\n            background: transparent;\n            border: none;\n            color: {colors['input_text']};\n        }}\n    "

def standalone_module_window_style() -> str:
    """Theme-aware shell for StandaloneModuleWindow hosts."""
    colors = _report_theme_colors()
    return f"\n        QMainWindow {{\n            background-color: {colors['app_bg']};\n            color: {colors['input_text']};\n        }}\n        QWidget {{\n            background-color: {colors['app_bg']};\n            color: {colors['input_text']};\n        }}\n    "

def page_heading_style(font_size: int=22) -> str:
    """Standard page heading label style."""
    colors = _report_theme_colors()
    return f"color: {colors['heading_text']}; font-size: {font_size}px; font-weight: bold; background: transparent; border: none;"


def section_heading_style(font_size: int = 13) -> str:
    """Theme-aware subsection heading for compound entry/report pages."""
    colors = _report_theme_colors()
    return (
        f"color: {colors['heading_text']}; font-size: {font_size}px; "
        f"font-weight: bold; background: transparent; border: none;"
    )


def book_report_special_row_colors() -> dict[str, str]:
    """Background/foreground colors for Day Book and Cash Book highlight rows."""
    colors = _report_theme_colors()
    if _report_is_light():
        return {
            "opening": colors.get("surface_alt", colors["panel_bg"]),
            "total": colors.get("table_header_bg", colors["panel_bg"]),
            "closing_balance": "#B8E6D8",
            "separator_bg": colors["border"],
            "separator_fg": colors["muted_text"],
            "highlight_fg": colors["input_text"],
        }
    return {
        "opening": "#1e3a5f",
        "total": "#3f3f46",
        "closing_balance": "#064e3b",
        "separator_bg": "#111827",
        "separator_fg": "#9ca3af",
        "highlight_fg": "#ffffff",
    }


def apply_financial_statement_row_style(
    table: QTableWidget,
    row_idx: int,
    *,
    row_kind: str = "total",
) -> None:
    """Apply readable bold styling to P&L / Balance Sheet subtotal rows."""
    row_colors = book_report_special_row_colors()
    background = QBrush(QColor(row_colors.get(row_kind, row_colors["total"])))
    foreground = QBrush(QColor(row_colors["highlight_fg"]))
    font = QFont()
    font.setBold(True)
    for col in range(table.columnCount()):
        item = table.item(row_idx, col)
        if item is None:
            continue
        item.setFont(font)
        item.setBackground(background)
        item.setForeground(foreground)
        item.setData(Qt.ItemDataRole.BackgroundRole, background)
        item.setData(Qt.ItemDataRole.ForegroundRole, foreground)


def financial_statement_table_style() -> str:
    """QTableWidget style for P&L / Balance Sheet — item text comes from cell roles."""
    from ui import theme
    colors = _report_theme_colors()
    sel_bg = colors["focus_border"]
    sel_text = colors["input_text"] if _report_is_light() else "white"
    return (
        f"\n        QTableWidget {{\n"
        f"            background-color: {colors['table_bg']};\n"
        f"            alternate-background-color: {colors['card_bg']};\n"
        f"            color: {colors['table_text']};\n"
        f"            gridline-color: {colors['border']};\n"
        f"            border: 1px solid {colors['border']};\n"
        f"            selection-background-color: {sel_bg};\n"
        f"            selection-color: {sel_text};\n"
        f"        }}\n"
        f"        QTableWidget::item {{\n"
        f"            padding: 6px;\n"
        f"        }}\n"
        f"        QHeaderView::section {{\n"
        f"            background-color: {colors['table_header_bg']};\n"
        f"            color: {colors['heading_text']};\n"
        f"            padding: 7px;\n"
        f"            border: none;\n"
        f"            border-right: 1px solid {colors['border']};\n"
        f"            border-bottom: 1px solid {colors['border']};\n"
        f"            font-weight: bold;\n"
        f"        }}\n"
        f"    "
        + theme.scrollbar_stylesheet()
    )

def report_summary_label_style() -> str:
    colors = _report_theme_colors()
    return f"color: {colors['accent_label']}; font-size: 13px; font-weight: bold; background: transparent; border: none;"

def report_data_table_style() -> str:
    """Theme-aware QTableWidget style for standalone report pages."""
    from ui import theme
    colors = _report_theme_colors()
    sel_bg = colors['focus_border']
    sel_text = colors['input_text'] if _report_is_light() else 'white'
    return f"\n        QTableWidget {{\n            background-color: {colors['table_bg']};\n            alternate-background-color: {colors['card_bg']};\n            color: {colors['table_text']};\n            gridline-color: {colors['border']};\n            border: 1px solid {colors['border']};\n            selection-background-color: {sel_bg};\n            selection-color: {sel_text};\n        }}\n        QTableWidget::item {{\n            padding: 6px;\n            color: {colors['table_text']};\n        }}\n        QHeaderView::section {{\n            background-color: {colors['table_header_bg']};\n            color: {colors['heading_text']};\n            padding: 7px;\n            border: none;\n            border-right: 1px solid {colors['border']};\n            border-bottom: 1px solid {colors['border']};\n            font-weight: bold;\n        }}\n    " + theme.scrollbar_stylesheet()

def report_group_box_style() -> str:
    """Theme-aware QGroupBox style for settings/report dialogs."""
    colors = _report_theme_colors()
    return f"\n        QGroupBox {{\n            background-color: {colors['panel_bg']};\n            color: {colors['input_text']};\n            border: 1px solid {colors['border']};\n            border-radius: 8px;\n            margin-top: 16px;\n            padding-top: 12px;\n            padding-left: 0px;\n            padding-right: 0px;\n            padding-bottom: 0px;\n            font-weight: bold;\n        }}\n        QGroupBox::title {{\n            subcontrol-origin: margin;\n            subcontrol-position: top left;\n            left: 14px;\n            padding: 0 6px;\n            color: {colors['accent_label']};\n            background-color: transparent;\n            border: none;\n        }}\n    "

def report_dialog_body_style() -> str:
    """Theme-aware dialog shell for global settings and report popups."""
    colors = _report_theme_colors()
    return f"\n        QDialog {{\n            background-color: {colors['app_bg']};\n            color: {colors['input_text']};\n        }}\n        QLabel {{\n            background: transparent;\n            border: none;\n            color: {colors['input_text']};\n        }}\n        QPushButton {{\n            background-color: {colors['panel_bg']};\n            color: {colors['input_text']};\n            border: 1px solid {colors['border']};\n            padding: 8px 16px;\n            border-radius: 6px;\n            font-weight: 600;\n        }}\n        QPushButton:hover {{\n            background-color: {colors.get('surface_alt', colors['panel_bg'])};\n            border-color: {colors['focus_border']};\n        }}\n        QPushButton#primaryButton {{\n            background-color: {colors['button_primary']};\n            color: #FFFFFF;\n            border: none;\n        }}\n        QPushButton#primaryButton:hover {{\n            background-color: {colors['focus_border']};\n        }}\n    "

def report_footer_frame_style() -> str:
    colors = _report_theme_colors()
    return f"\n        QFrame {{\n            background-color: {colors['panel_bg']};\n            border: 1px solid {colors['border']};\n            border-radius: 4px;\n        }}\n        QLabel {{\n            background: transparent;\n            border: none;\n            color: {colors['input_text']};\n        }}\n    "

def report_detail_dialog_style() -> str:
    """Theme-aware read-only voucher/detail dialog styling."""
    from ui import theme
    colors = _report_theme_colors()
    sel_bg = colors['focus_border']
    sel_text = colors['input_text'] if _report_is_light() else 'white'
    return f"\n        QDialog {{\n            background-color: {colors['app_bg']};\n            color: {colors['input_text']};\n        }}\n        QLabel {{\n            color: {colors['input_text']};\n            font-size: 13px;\n            background: transparent;\n            border: none;\n        }}\n        QTableWidget {{\n            background-color: {colors['table_bg']};\n            color: {colors['table_text']};\n            gridline-color: {colors['border']};\n            selection-background-color: {sel_bg};\n            selection-color: {sel_text};\n            border: 1px solid {colors['border']};\n        }}\n        QHeaderView::section {{\n            background-color: {colors['table_header_bg']};\n            color: {colors['accent_label']};\n            padding: 7px;\n            border: 0px;\n            font-weight: bold;\n        }}\n        QPushButton {{\n            background-color: {colors['button_primary']};\n            color: white;\n            border: none;\n            padding: 8px 18px;\n            border-radius: 6px;\n            font-weight: bold;\n        }}\n        QPushButton:hover {{\n            background-color: {colors['focus_border']};\n        }}\n    " + theme.scrollbar_stylesheet()

def report_dialog_heading_style(font_size: int=16) -> str:
    colors = _report_theme_colors()
    return f"color: {colors['heading_text']}; font-size: {font_size}px; font-weight: bold; background: transparent; border: none;"

def report_filter_frame_style(selector: str='QFrame') -> str:
    colors = _report_theme_colors()
    return f"{selector} {{ background-color: {colors['panel_bg']}; border: 1px solid {colors['border']}; border-radius: 6px; }}"

def report_compound_entry_page_style() -> str:
    """Full-page stylesheet for legacy compound entry/report pages."""
    from ui import theme
    colors = _report_theme_colors()
    c = colors
    hover = c['focus_border']
    tab_muted = c['muted_text']
    sel_bg = c['focus_border']
    sel_text = '#FFFFFF' if _report_is_light() else 'white'
    return f"\n        QWidget {{ background-color: {c['app_bg']}; color: {c['input_text']}; }}\n        QLabel {{ color: {c['accent_label']}; font-size: 12px; font-weight: bold; }}\n        QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {{\n            background-color: {c['input_bg']}; color: {c['input_text']};\n            border: 1px solid {c['border']}; padding: 4px 8px; border-radius: 3px; font-size: 12px;\n        }}\n        QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{\n            border: 1px solid {c['focus_border']};\n        }}\n        QPushButton {{\n            background-color: {c['button_primary']}; color: white; border: none;\n            padding: 6px 12px; border-radius: 3px; font-size: 12px; font-weight: bold;\n        }}\n        QPushButton:hover {{ background-color: {hover}; }}\n        QTableWidget, QTableView {{\n            background-color: {c['table_bg']}; color: {c['table_text']};\n            gridline-color: {c['border']}; border: 1px solid {c['border']};\n            selection-background-color: {sel_bg}; selection-color: {sel_text};\n        }}\n        QHeaderView::section {{\n            background-color: {c['table_header_bg']}; color: {c['accent_label']};\n            padding: 6px; border: 0px; border-right: 1px solid {c['border']};\n            font-weight: bold; font-size: 12px;\n        }}\n        QFrame {{ background-color: {c['panel_bg']}; border-radius: 4px; }}\n        QTabWidget::pane {{ border: 1px solid {c['border']}; background-color: {c['panel_bg']}; }}\n        QTabBar::tab {{\n            background-color: {c.get('surface_alt', c['panel_bg'])}; color: {tab_muted};\n            padding: 8px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px;\n        }}\n        QTabBar::tab:selected {{ background-color: {c['button_primary']}; color: white; }}\n    " + theme.scrollbar_stylesheet()

def report_accent_label_chip_style(padding: str='4px 6px') -> str:
    """Bordered accent label chip (legacy yellow label boxes)."""
    colors = _report_theme_colors()
    return f"color: {colors['accent_label']}; font-size: 12px; font-weight: bold; background-color: {colors['app_bg']}; border: 1px solid {colors['border']}; border-radius: 4px; padding: {padding};"

def report_picker_dialog_style() -> str:
    from ui import theme
    return theme.entry_picker_dialog_style()

def add_labeled_filter_rows(
    grid: QGridLayout,
    field_row_groups: List[List[tuple[str, QWidget]]],
    *,
    columns: int = 4,
) -> None:
    """
    Lay out labeled filters on a fixed-column grid with aligned columns.

    Single-field rows span all columns (for example a full-width Search box).
    """
    for block_idx, row_fields in enumerate(field_row_groups):
        label_row = block_idx * 2
        field_row = label_row + 1
        if len(row_fields) == 1:
            label_text, widget = row_fields[0]
            label = QLabel(label_text)
            label.setStyleSheet(compact_label_style())
            grid.addWidget(label, label_row, 0, 1, columns)
            grid.addWidget(widget, field_row, 0, 1, columns)
            continue
        for col, (label_text, widget) in enumerate(row_fields):
            if col >= columns:
                break
            label = QLabel(label_text)
            label.setStyleSheet(compact_label_style())
            grid.addWidget(label, label_row, col)
            grid.addWidget(widget, field_row, col)
    for col in range(columns):
        grid.setColumnStretch(col, 1)

def create_filter_action_layout(buttons: List[QPushButton]) -> QHBoxLayout:
    """Create a standard action-button row for book/report filter bars."""
    layout = QHBoxLayout()
    layout.setSpacing(6)
    layout.setContentsMargins(0, 4, 0, 0)
    for btn in buttons:
        btn.setStyleSheet(compact_primary_button_style())
        btn.setFixedHeight(BOOK_REPORT_ACTION_BUTTON_HEIGHT)
        btn.setMinimumWidth(max(btn.minimumWidth(), 68))
        layout.addWidget(btn)
    layout.addStretch()
    return layout

def attach_filter_action_row(grid: QGridLayout, action_layout: QHBoxLayout, *, row: int, span_cols: int=4) -> None:
    """Attach an action-button row beneath filter fields inside a filter grid."""
    grid.addLayout(action_layout, row, 0, 1, span_cols)
REPORT_COLUMNS = {'Bill Wise': [('Date', 'voucher_date'), ('No', 'voucher_no'), ('Party', 'party_name'), ('Type', 'voucher_subtype'), ('Nature', 'nature'), ('Taxable', 'taxable_amount'), ('CGST', 'cgst_amount'), ('SGST', 'sgst_amount'), ('IGST', 'igst_amount'), ('CESS', 'cess_amount'), ('Tax', 'tax_total'), ('Discount', 'discount_total'), ('Round Off', 'round_off'), ('Grand Total', 'grand_total'), ('Settled', 'settled_amount'), ('Balance', 'balance_amount')], 'Item Wise': [('Date', 'voucher_date'), ('No', 'voucher_no'), ('Party', 'party_name'), ('Product', 'product_name'), ('Barcode', 'barcode'), ('HSN', 'hsn'), ('Qty', 'quantity'), ('Rate', 'rate'), ('Gross', 'gross_value'), ('Discount', 'discount'), ('Taxable', 'taxable_amount'), ('Tax %', 'tax_percent'), ('CGST', 'cgst_amount'), ('SGST', 'sgst_amount'), ('IGST', 'igst_amount'), ('CESS', 'cess_amount'), ('Tax', 'tax_amount'), ('Total', 'grand_total')], 'Tax Wise': [('Date', 'voucher_date'), ('No', 'voucher_no'), ('Party', 'party_name'), ('HSN', 'hsn'), ('Product', 'product_name'), ('Tax %', 'tax_percent'), ('CGST %', 'cgst'), ('SGST %', 'sgst'), ('IGST %', 'igst'), ('CESS %', 'cess'), ('Taxable', 'taxable_amount'), ('CGST', 'cgst_amount'), ('SGST', 'sgst_amount'), ('IGST', 'igst_amount'), ('CESS', 'cess_amount'), ('Tax', 'tax_amount'), ('Total', 'grand_total')], 'Tax Summary': [('Tax %', 'tax_percent'), ('CGST %', 'cgst'), ('SGST %', 'sgst'), ('IGST %', 'igst'), ('CESS %', 'cess'), ('Nature', 'nature'), ('Bill Count', 'bill_count'), ('Taxable', 'taxable_amount'), ('CGST', 'cgst_amount'), ('SGST', 'sgst_amount'), ('IGST', 'igst_amount'), ('CESS', 'cess_amount'), ('Tax', 'tax_amount'), ('Total', 'grand_total')], 'Credit': [('Date', 'voucher_date'), ('No', 'voucher_no'), ('Party', 'party_name'), ('Grand Total', 'grand_total'), ('Settled', 'settled_amount'), ('Balance', 'balance_amount'), ('Due Date', 'due_date'), ('Status', 'status')], 'Party Wise': [('Party', 'party_name'), ('Type', 'party_type'), ('Bill Count', 'bill_count'), ('Taxable', 'taxable_amount'), ('Tax', 'tax_total'), ('Discount', 'discount_total'), ('Grand Total', 'grand_total'), ('Settled', 'settled_amount'), ('Balance', 'balance_amount')], 'Category Wise': [('Category', 'category'), ('Bill Count', 'bill_count'), ('Qty', 'quantity_total'), ('Taxable', 'taxable_amount'), ('Tax', 'tax_total'), ('Discount', 'discount_total'), ('Grand Total', 'grand_total')], 'Bill Wise Profit': [('Date', 'invoice_date'), ('Invoice No', 'invoice_number'), ('Party', 'party_name'), ('Sales Value', 'sales_value'), ('Cost Value', 'cost_value'), ('Gross Profit', 'profit'), ('Margin %', 'margin_percent')], 'Party Wise Profit': [('Date', 'invoice_date'), ('Invoice No', 'invoice_number'), ('Party', 'party_name'), ('Sales Value', 'sales_value'), ('Cost Value', 'cost_value'), ('Gross Profit', 'profit'), ('Margin %', 'margin_percent')], 'Item Wise Profit': [('Product', 'product_name'), ('Qty Sold', 'qty_sold'), ('Sales Value', 'sales_value'), ('Cost Value', 'cost_value'), ('Gross Profit', 'profit'), ('Margin %', 'margin_percent')]}
AMOUNT_KEYS = {'taxable_amount', 'cgst_amount', 'sgst_amount', 'igst_amount', 'cess_amount', 'tax_total', 'discount_total', 'round_off', 'grand_total', 'settled_amount', 'balance_amount', 'gross_value', 'discount', 'tax_amount', 'rate', 'quantity', 'quantity_total', 'sales_value', 'cost_value', 'profit'}
PERCENT_KEYS = {'tax_percent', 'cgst', 'sgst', 'igst', 'cess', 'margin_percent'}

def footer_title_style() -> str:
    """Theme-aware footer metric title style."""
    colors = _report_theme_colors()
    return f"color: {colors['accent_label']}; font-weight: bold;"

def footer_value_style() -> str:
    """Theme-aware footer metric value style."""
    colors = _report_theme_colors()
    return f"color: {colors['button_success']}; font-weight: bold; font-size: 14px;"

def report_status_label_style() -> str:
    """Muted status line below report filter bars."""
    colors = _report_theme_colors()
    return f"color: {colors['muted_text']}; font-size: 12px; background: transparent; border: none;"
FOOTER_TITLE_STYLE = footer_title_style()
FOOTER_VALUE_STYLE = footer_value_style()

def footer_metric_html(title: str, value: str) -> str:
    """Return rich footer HTML that keeps a metric title and value together."""
    clean_title = str(title or '').strip()
    if not clean_title.endswith(':'):
        clean_title = f'{clean_title}:'
    return f"<span style='{footer_title_style()}'>{escape(clean_title)} </span><span style='{footer_value_style()}'>{escape(str(value))}</span>"

def set_footer_metric(label: QLabel, title: str, value: str) -> None:
    """Update a combined footer metric label without splitting title and value."""
    label.setText(footer_metric_html(title, value))

def create_footer_metric_label(title: str, value: str='0.00') -> QLabel:
    """Create one rich-text footer metric label with title and value grouped."""
    label = QLabel()
    label.setTextFormat(Qt.RichText)
    label.setWordWrap(False)
    label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    label.setStyleSheet('background: transparent; border: none;')
    set_footer_metric(label, title, value)
    return label

def create_footer_title_label(text: str) -> QLabel:
    """Create a footer total heading label with the standard yellow style."""
    label = QLabel(text)
    label.setStyleSheet(footer_title_style())
    label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
    return label

def create_footer_value_label(text: str='0.00', minimum_width: int=95) -> QLabel:
    """Create a footer total value label with the standard green style."""
    label = QLabel(text)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    label.setStyleSheet(footer_value_style())
    label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
    return label

class BookReportWorker(QObject):
    """Run heavy book report queries on a worker-owned database connection."""
    data_ready = Signal(list)
    error = Signal(str)
    finished = Signal()

    def __init__(self, logic_class, db_type, db_path, method_name: str, args: tuple):
        super().__init__()
        self.logic_class = logic_class
        self.db_type = db_type
        self.db_path = db_path
        self.method_name = method_name
        self.args = args

    def run(self):
        """Execute report query and emit rows back to the GUI thread."""
        worker_db = None
        try:
            from db import Database
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            logic = self.logic_class(worker_db)
            method = getattr(logic, self.method_name)
            result = method(*self.args)
            if not result.get('success'):
                self.error.emit(result.get('message') or 'Unable to load report.')
                return
            self.data_ready.emit(result.get('data', []))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                try:
                    worker_db.force_disconnect()
                except Exception:
                    pass
            self.finished.emit()

class VoucherDetailDialog(UiMemoryMixin, QDialog):
    """Read-only voucher detail dialog with Open Original / Edit button."""

    def __init__(self, title: str, detail: Dict[str, Any], parent=None, voucher_id: int=None, voucher_type: str=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(900, 620)
        self.detail = detail
        self.voucher_id = voucher_id
        self.voucher_type = voucher_type
        self._build_ui()
        self._init_ui_memory()

    def _build_ui(self):
        self.setStyleSheet(report_detail_dialog_style())
        layout = QVBoxLayout(self)
        header = self.detail.get('header', {})
        header_label = QLabel(f"{header.get('voucher_type', '')}  |  No: {header.get('voucher_no', '')}  |  Date: {format_display_date(header.get('voucher_date', ''))}  |  Party: {header.get('party_name', '')}")
        header_label.setStyleSheet(report_dialog_heading_style(16))
        layout.addWidget(header_label)
        info = QLabel(f"GSTIN: {header.get('gstin', '')}    State: {header.get('state', '')}    Narration: {header.get('narration', '')}")
        layout.addWidget(info)
        colors = _report_theme_colors()
        table = self.table = QTableWidget()
        columns = [('SL No', 'sl_no'), ('Product', 'product_name'), ('Barcode', 'barcode'), ('HSN', 'hsn'), ('Qty', 'quantity'), ('Rate', 'rate'), ('Taxable', 'taxable_amount'), ('CGST', 'cgst_amount'), ('SGST', 'sgst_amount'), ('IGST', 'igst_amount'), ('CESS', 'cess_amount'), ('Tax', 'tax_amount'), ('Total', 'grand_total')]
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels([label for label, key in columns])
        items = self.detail.get('items', [])
        table.setRowCount(len(items))
        for row, item_data in enumerate(items):
            for col, (label, key) in enumerate(columns):
                value = item_data.get(key, '')
                if key == 'sl_no':
                    text = str(row + 1)
                    cell = QTableWidgetItem(text)
                    cell.setBackground(QColor(colors['accent_label']))
                    cell.setForeground(QColor(colors['input_text']))
                    cell.setTextAlignment(Qt.AlignCenter)
                elif key in PERCENT_KEYS:
                    rate = safe_float(value)
                    text = f'{rate:g}%'
                    cell = QTableWidgetItem(text)
                    if key in AMOUNT_KEYS or key in PERCENT_KEYS:
                        cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif key in AMOUNT_KEYS:
                    text = f'{safe_float(value):,.2f}'
                    cell = QTableWidgetItem(text)
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    text = str(value if value is not None else '')
                    cell = QTableWidgetItem(text)
                table.setItem(row, col, cell)
        apply_adjustable_table_columns(table, sl_no_column=0, sl_no_width=60)
        layout.addWidget(table)
        totals_layout = QHBoxLayout()
        totals_layout.setContentsMargins(5, 5, 5, 5)
        totals_layout.setSpacing(10)
        footer_fields = [('Taxable', header.get('taxable_amount')), ('Tax', header.get('tax_total')), ('Grand Total', header.get('grand_total')), ('Settled', header.get('settled_amount')), ('Balance', header.get('balance_amount'))]
        for title, amount in footer_fields:
            totals_layout.addWidget(create_footer_metric_label(title, f'{safe_float(amount):,.2f}'))
        totals_layout.addStretch()
        layout.addLayout(totals_layout)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        if self.voucher_id and self.voucher_type:
            open_button = QPushButton('Open Original / Edit Voucher')
            open_button.setStyleSheet(compact_primary_button_style())
            open_button.clicked.connect(self.open_voucher_for_edit)
            button_layout.addWidget(open_button)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

    def open_voucher_for_edit(self, *args):
        """Emit signal to open voucher for editing."""
        main_window = self.parent()
        while main_window and (main_window is self or not hasattr(main_window, 'open_voucher_for_edit')):
            main_window = main_window.parent()
        if main_window and hasattr(main_window, 'open_voucher_for_edit'):
            main_window.open_voucher_for_edit(self.voucher_type, self.voucher_id)
            self.accept()
        else:
            QMessageBox.information(self, 'Edit Voucher', f'Open {self.voucher_type} #{self.voucher_id} for editing.\n\nThis functionality requires the main window to be accessible.')

class SummaryDetailDialog(UiMemoryMixin, QDialog):
    """Read-only detail list for summary rows."""

    def __init__(self, title: str, rows: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(950, 600)
        self.rows = rows
        self._build_ui()
        self._init_ui_memory()

    def _build_ui(self):
        self.setStyleSheet(report_detail_dialog_style())
        layout = QVBoxLayout(self)
        title = QLabel(self.windowTitle())
        title.setStyleSheet(report_dialog_heading_style(16))
        layout.addWidget(title)
        columns = REPORT_COLUMNS['Bill Wise']
        table = self.table = QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels([label for label, key in columns])
        table.setRowCount(len(self.rows))
        for row, row_data in enumerate(self.rows):
            for col, (label, key) in enumerate(columns):
                value = row_data.get(key, '')
                if key in PERCENT_KEYS:
                    rate = safe_float(value)
                    text = f'{rate:g}%'
                elif key in AMOUNT_KEYS:
                    text = f'{safe_float(value):,.2f}'
                else:
                    text = str(value if value is not None else '')
                item = QTableWidgetItem(text)
                if key in AMOUNT_KEYS or key in PERCENT_KEYS:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(row, col, item)
        apply_adjustable_table_columns(table, sl_no_column=0, sl_no_width=60)
        layout.addWidget(table)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

class BookReportPageWidget(UiMemoryMixin, QWidget):
    """Base report page used by all voucher book modules."""

    def __init__(self, db, logic, title: str, report_types: List[str], parent=None):
        super().__init__(parent)
        self.db = db
        self.logic = logic
        self.title = title
        self.report_types = report_types
        self.current_rows: List[Dict[str, Any]] = []
        self.current_columns: List[tuple[str, str]] = []
        self.company_id: Optional[int] = None
        self._loading = False
        self._report_thread = None
        self._report_worker = None
        self.party_model = QStringListModel([])
        self.product_model = QStringListModel([])
        self.category_model = QStringListModel([])
        self.products_by_barcode = {}
        self._ui_memory_active_table_attr = "table"
        self._ui_memory_active_table = None
        self._build_ui()
        self._sync_table_headers_for_report_type()
        self._sync_category_filter_for_report_type()
        QTimer.singleShot(100, self.refresh)
        self._init_ui_memory(table_attrs=("table",))

    def _style_input(self) -> str:
        return compact_input_style()

    def _build_ui(self):
        self.setStyleSheet(page_background_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QLabel(self.title)
        header.setStyleSheet(page_heading_style(22))
        root.addWidget(header)
        filter_frame = QFrame()
        self.filter_frame = filter_frame
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QGridLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setHorizontalSpacing(8)
        filter_layout.setVerticalSpacing(6)
        self.from_date = QDateEdit()
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        self.to_date = QDateEdit()
        self.to_date.setDate(QDate.currentDate())
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        self.report_combo = QComboBox()
        self.report_combo.addItems(self.report_types)
        self.report_combo.setStyleSheet(compact_combo_style())
        self.report_combo.setMinimumWidth(168)
        self.report_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.report_combo.currentTextChanged.connect(self._on_report_type_changed)
        theme.apply_combo_dropdown_theme(self.report_combo)
        self.party_search = QLineEdit()
        self.party_search.setPlaceholderText('Party search')
        self.party_search.setStyleSheet(compact_search_style())
        self.party_search.setMinimumWidth(96)
        self.party_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.party_completer = QCompleter(self.party_model, self.party_search)
        self.party_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.party_completer.setFilterMode(Qt.MatchContains)
        theme.wire_line_edit_completer(self.party_search, self.party_completer)
        self.category_search = QLineEdit()
        self.category_search.setPlaceholderText('Category search')
        self.category_search.setStyleSheet(compact_search_style())
        self.category_search.setMinimumWidth(96)
        self.category_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.category_completer = QCompleter(self.category_model, self.category_search)
        self.category_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.category_completer.setFilterMode(Qt.MatchContains)
        theme.wire_line_edit_completer(self.category_search, self.category_completer)
        self.category_search.returnPressed.connect(self.load_data)
        self.barcode_search = QLineEdit()
        self.barcode_search.setPlaceholderText('Barcode')
        self.barcode_search.setStyleSheet(theme.sales_barcode_input_style())
        self.barcode_search.setFixedWidth(110)
        self.barcode_search.setReadOnly(False)
        self.barcode_search.setFocusPolicy(Qt.StrongFocus)
        self.barcode_search.returnPressed.connect(self.on_barcode_enter)
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText('Product search')
        self.product_search.setStyleSheet(compact_search_style())
        self.product_search.setMinimumWidth(96)
        self.product_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.product_search.setReadOnly(False)
        self.product_search.setFocusPolicy(Qt.StrongFocus)
        self._setup_product_completer()
        self.product_search.returnPressed.connect(self.on_product_enter)
        self.tax_filter = QComboBox()
        self._populate_gst_filter()
        self.tax_filter.setStyleSheet(compact_combo_style())
        self.tax_filter.setMinimumWidth(148)
        self.tax_filter.setMaximumWidth(260)
        self.tax_filter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tax_filter.setFocusPolicy(Qt.StrongFocus)
        self.tax_filter.currentIndexChanged.connect(self.load_data)
        theme.apply_combo_dropdown_theme(self.tax_filter)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search bill no, party, product, narration')
        self.search_input.setStyleSheet(compact_search_style())
        self.search_input.setMinimumWidth(140)
        self.search_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search_input.returnPressed.connect(self.load_data)
        self.load_btn = QPushButton('Load')
        self.refresh_btn = QPushButton('Refresh')
        self.export_btn = QPushButton('Export')
        action_height = BOOK_REPORT_ACTION_BUTTON_HEIGHT
        for btn in (self.load_btn, self.refresh_btn, self.export_btn):
            btn.setStyleSheet(compact_primary_button_style())
            btn.setFixedHeight(action_height)
            btn.setMinimumWidth(68)
        self.load_btn.clicked.connect(self.load_data)
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn.clicked.connect(self.show_export_menu)
        filter_rows = [
            [
                ('From', self.from_date),
                ('To', self.to_date),
                ('Report Type', self.report_combo),
                ('Category', self.category_search),
            ],
            [
                ('Party', self.party_search),
                ('Product', self.product_search),
                ('Barcode', self.barcode_search),
                ('GST', self.tax_filter),
            ],
            [('Search', self.search_input)],
        ]
        add_labeled_filter_rows(filter_layout, filter_rows)
        self.filter_action_layout = create_filter_action_layout([self.load_btn, self.refresh_btn, self.export_btn])
        attach_filter_action_row(filter_layout, self.filter_action_layout, row=6)
        root.addWidget(filter_frame)
        self.summary_label = QLabel('Ready')
        self.summary_label.setStyleSheet(report_summary_label_style())
        root.addWidget(self.summary_label)
        self.export_menu = QMenu(self)
        self.excel_action = self.export_menu.addAction('Export Excel')
        self.pdf_action = self.export_menu.addAction('Export PDF')
        self.table = QTableWidget()
        apply_read_only_report_table_selection(self.table)
        self.table.setStyleSheet(report_data_table_style())
        self.table.itemDoubleClicked.connect(self.open_detail_from_row)
        root.addWidget(self.table, 1)
        footer_frame = QFrame()
        self.footer_frame = footer_frame
        footer_frame.setStyleSheet(report_footer_frame_style())
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(5, 5, 5, 5)
        footer_layout.setSpacing(10)
        self.footer_total_labels = {}
        self.footer_total_titles = {}
        footer_fields = [('Rows', 'rows', '0'), ('Total Tax', 'total_tax', '0.00'), ('Total Amount', 'total_amount', '0.00')]
        for title, key, default_value in footer_fields:
            metric_label = create_footer_metric_label(title, default_value)
            footer_layout.addWidget(metric_label)
            self.footer_total_labels[key] = metric_label
            self.footer_total_titles[key] = title
        footer_layout.addStretch()
        root.addWidget(footer_frame)

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(page_background_style())
        if hasattr(self, 'filter_frame'):
            self.filter_frame.setStyleSheet(compact_topbar_frame_style())
        if hasattr(self, 'footer_frame'):
            self.footer_frame.setStyleSheet(report_footer_frame_style())
        self.summary_label.setStyleSheet(report_summary_label_style())
        prepare_report_date_edit(self.from_date, style_sheet=compact_date_style())
        prepare_report_date_edit(self.to_date, style_sheet=compact_date_style())
        self.report_combo.setStyleSheet(compact_combo_style())
        theme.apply_combo_dropdown_theme(self.report_combo)
        self.party_search.setStyleSheet(compact_search_style())
        theme.apply_completer_popup_theme(getattr(self, 'party_completer', None))
        if hasattr(self, 'category_search'):
            self.category_search.setStyleSheet(compact_search_style())
            theme.apply_completer_popup_theme(getattr(self, 'category_completer', None))
        self.barcode_search.setStyleSheet(theme.sales_barcode_input_style())
        self.product_search.setStyleSheet(compact_search_style())
        product_completer = self.product_search.completer()
        if product_completer is not None:
            theme.apply_completer_popup_theme(product_completer)
        self.tax_filter.setStyleSheet(compact_combo_style())
        theme.apply_combo_dropdown_theme(self.tax_filter)
        self.search_input.setStyleSheet(compact_search_style())
        for btn in (self.load_btn, self.refresh_btn, self.export_btn):
            btn.setStyleSheet(compact_primary_button_style())
        self.table.setStyleSheet(report_data_table_style())

    def _populate_gst_filter(self):
        """Populate GST filter labels while preserving numeric filter values."""
        gst_options = [('All GST', None), ('GST 0%', 0.0), ('GST 1% (IGST 1% / CGST 0.5% + SGST 0.5%)', 1.0), ('GST 3% (IGST 3% / CGST 1.5% + SGST 1.5%)', 3.0), ('GST 5% (IGST 5% / CGST 2.5% + SGST 2.5%)', 5.0), ('GST 12% (IGST 12% / CGST 6% + SGST 6%)', 12.0), ('GST 18% (IGST 18% / CGST 9% + SGST 9%)', 18.0), ('GST 28% (IGST 28% / CGST 14% + SGST 14%)', 28.0)]
        for label, rate in gst_options:
            self.tax_filter.addItem(label, rate)

    def refresh(self):
        self.company_id = resolve_active_company_id(self.db)
        if not self.company_id:
            self.show_no_data('Please open a company first.')
            return
        parties = self.logic.get_party_choices(self.company_id)
        products = self.logic.get_product_choices(self.company_id)
        self.party_model.setStringList(['All Parties'] + [p.get('name', '') for p in parties if p.get('name')])
        self.product_model.setStringList([p.get('name', '') for p in products if p.get('name')])
        categories = self.logic.get_category_choices(self.company_id)
        self.category_model.setStringList(['All Categories'] + categories)
        self.products_by_barcode = {}
        for p in products:
            bc = str(p.get('barcode', '')).strip()
            if bc:
                self.products_by_barcode[bc] = p
        self.load_data()

    def _setup_product_completer(self):
        """Setup product completer with starts-with matching (like Sales Entry)."""
        from .sales_entry_popup import setup_product_completer

        def on_product_selected_callback(index, model_idx, editor):
            """Handle product selection from completer popup."""
            product = model_idx.data(Qt.UserRole)
            if product:
                editor.setText(product.get('name', ''))
                self.load_data()
        setup_product_completer(self.product_search, self, None, on_product_selected_callback, min_chars=1)

    def on_barcode_enter(self):
        """Handle barcode Enter key - lookup product and auto-select product filter."""
        barcode = str(self.barcode_search.text()).strip()
        if not barcode:
            return
        product = self.products_by_barcode.get(barcode)
        if product:
            product_name = product.get('name', '')
            self.product_search.setText(product_name)
            self.load_data()
        else:
            self.load_data()

    def on_product_enter(self):
        """Handle product Enter key by applying typed product filters."""
        if self.product_search.text().strip():
            self.load_data()
            return
        self.show_product_dialog()

    def show_product_dialog(self):
        """Show product search popup dialog (same pattern as Stock Adjustment)."""
        from config import active_company_manager
        company_id = active_company_manager.get_active_company_id()
        if not company_id:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView
        from PySide6.QtCore import Qt, QTimer
        popup = QDialog(self)
        popup.setWindowTitle('Select Product')
        popup.resize(620, 440)
        popup.setStyleSheet(report_picker_dialog_style())
        layout = QVBoxLayout(popup)
        search_layout = QHBoxLayout()
        search_label = QLabel('Search Product:')
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type product name or barcode...')
        search_layout.addWidget(search_label)
        search_layout.addWidget(search_input)
        layout.addLayout(search_layout)
        table = self.table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['Name', 'Barcode', 'Stock', 'Rate', ''])
        apply_read_only_report_table_selection(table)
        layout.addWidget(table)
        button_layout = QHBoxLayout()
        select_btn = QPushButton('Select')
        cancel_btn = QPushButton('Cancel')
        button_layout.addWidget(select_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        products = self.logic.get_product_choices(company_id)
        table.setRowCount(len(products))
        for row, product in enumerate(products):
            table.setItem(row, 0, QTableWidgetItem(product.get('name', '')))
            table.setItem(row, 1, QTableWidgetItem(product.get('barcode', '')))
            table.setItem(row, 2, QTableWidgetItem(f"{float(product.get('quantity', 0)):.3f}"))
            rate = float(product.get('sale_price') or product.get('mrp') or product.get('purchase_rate') or 0)
            table.setItem(row, 3, QTableWidgetItem(f'{rate:.2f}'))
        apply_adjustable_table_columns(table)
        selected_product = [None]

        def on_search_changed():
            text = search_input.text().strip().lower()
            for row in range(table.rowCount()):
                name = table.item(row, 0).text().lower()
                barcode = table.item(row, 1).text().lower()
                if text in name or text in barcode:
                    table.setRowHidden(row, False)
                else:
                    table.setRowHidden(row, True)

        def on_select():
            current_row = table.currentRow()
            if current_row >= 0:
                name = table.item(current_row, 0).text()
                for product in products:
                    if product.get('name') == name:
                        selected_product[0] = product
                        break
            popup.accept()

        def on_cancel():
            popup.reject()
        search_input.textChanged.connect(on_search_changed)
        select_btn.clicked.connect(on_select)
        cancel_btn.clicked.connect(on_cancel)
        table.doubleClicked.connect(on_select)
        popup.exec()
        if selected_product[0]:
            product_name = selected_product[0].get('name', '')
            self.product_search.setText(product_name)
            self.load_data()

    def _on_report_type_changed(self):
        self._ensure_filter_widgets_openable()
        self._sync_category_filter_for_report_type()
        self._sync_table_headers_for_report_type()
        self.load_data()

    def _sync_category_filter_for_report_type(self) -> None:
        """Tune the category filter hint for category-wise and item reports."""
        if not hasattr(self, 'category_search'):
            return
        report_type = self.report_combo.currentText()
        if 'Category Wise' in report_type:
            self.category_search.setPlaceholderText('e.g. Stationary, Fancy')
            self.category_search.setEnabled(True)
            return
        self.category_search.setPlaceholderText('Category search')
        self.category_search.setEnabled(True)

    def _sync_table_headers_for_report_type(self) -> None:
        """Pre-fill book table headers for the active report type and restore widths."""
        if not hasattr(self, "table") or not hasattr(self, "report_combo"):
            return
        report_type = self.report_combo.currentText()
        key = self._report_key(report_type)
        columns = REPORT_COLUMNS.get(key, REPORT_COLUMNS["Bill Wise"])
        headers = ["SL No"] + [label for label, _data_key in columns]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        memory_attr = f"table_{memory_table_attr_slug(key)}"
        self._ui_memory_active_table_attr = memory_attr
        self._ui_memory_active_table = self.table
        if hasattr(self, "settings"):
            self._restore_memory_table(self.table, memory_attr)

    def _ensure_filter_widgets_openable(self):
        """Keep shared topbar filters editable across every book report type."""
        self.barcode_search.setEnabled(True)
        self.barcode_search.setReadOnly(False)
        self.barcode_search.setFocusPolicy(Qt.StrongFocus)
        self.product_search.setEnabled(True)
        self.product_search.setReadOnly(False)
        self.product_search.setFocusPolicy(Qt.StrongFocus)
        self.tax_filter.setEnabled(True)
        self.tax_filter.setFocusPolicy(Qt.StrongFocus)
        if hasattr(self, 'category_search'):
            self.category_search.setEnabled(True)
            self.category_search.setReadOnly(False)
            self.category_search.setFocusPolicy(Qt.StrongFocus)

    def _filters(self) -> Dict[str, Any]:
        category_text = self.category_search.text().strip()
        if category_text.lower() in ('all', 'all categories'):
            category_text = ''
        filters = {
            'party': self.party_search.text().strip(),
            'category': category_text,
            'barcode': self.barcode_search.text().strip(),
            'product': self.product_search.text().strip(),
            'tax_rate': self.tax_filter.currentData(),
            'search': self.search_input.text().strip(),
        }
        return filters

    def _report_key(self, report_type: str) -> str:
        if 'Bill Wise Profit' in report_type:
            return 'Bill Wise Profit'
        if 'Party Wise Profit' in report_type:
            return 'Party Wise Profit'
        if 'Item Wise Profit' in report_type:
            return 'Item Wise Profit'
        if 'Item Wise' in report_type:
            return 'Item Wise'
        if 'Tax Summary' in report_type:
            return 'Tax Summary'
        if 'Tax Wise' in report_type:
            return 'Tax Wise'
        if 'Credit' in report_type or 'Refund' in report_type or 'Pending' in report_type:
            return 'Credit'
        if 'Party Wise' in report_type:
            return 'Party Wise'
        if 'Category Wise' in report_type:
            return 'Category Wise'
        return 'Bill Wise'

    def _logic_method_name(self, report_type: str) -> str:
        """Resolve the report query method without touching widgets in workers."""
        if 'Item Wise' in report_type and 'Profit' not in report_type:
            return 'get_item_wise'
        if 'Tax Summary' in report_type:
            return 'get_tax_summary'
        if 'Tax Wise' in report_type:
            return 'get_tax_wise'
        if 'Credit' in report_type or 'Refund' in report_type or 'Pending' in report_type:
            return 'get_credit_or_pending'
        if 'Party Wise' in report_type and 'Profit' not in report_type:
            return 'get_party_wise'
        if 'Category Wise' in report_type:
            return 'get_category_wise'
        if 'Item Wise Profit' in report_type:
            return 'get_item_wise'
        if 'Party Wise Profit' in report_type:
            return 'get_party_wise'
        return 'get_bill_wise'

    def _set_loading_state(self, is_loading: bool):
        """Disable only explicit load controls while a worker runs."""
        self._loading = is_loading
        self.load_btn.setEnabled(not is_loading)
        self.refresh_btn.setEnabled(not is_loading)
        self.report_combo.setEnabled(not is_loading)
        self._ensure_filter_widgets_openable()
        if is_loading:
            self.summary_label.setText('Loading...')

    def _start_report_worker(self, method_name: str, args: tuple, report_key: str):
        """Start a QThread worker and keep table updates on the GUI thread."""
        if self._loading:
            return
        db_type = getattr(self.db, 'db_type', None)
        db_path = getattr(self.db, 'db_path', None)
        thread = QThread(self)
        worker = BookReportWorker(type(self.logic), db_type, db_path, method_name, args)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(lambda rows, key=report_key: self.populate_table(rows, key))
        worker.error.connect(lambda message: self.show_no_data(f'Error loading report: {message}'))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_report_worker_finished)
        self._report_thread = thread
        self._report_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _on_report_worker_finished(self):
        """Reset loading state after the worker thread exits."""
        self._report_thread = None
        self._report_worker = None
        self._set_loading_state(False)

    def load_data(self):
        """Snapshot current topbar filters and start threaded report loading."""
        if self._loading:
            return
        if not self.company_id:
            self.company_id = resolve_active_company_id(self.db)
        if not self.company_id:
            self.show_no_data('Please open a company first.')
            return
        report_type = self.report_combo.currentText()
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        filters = self._filters()
        method_name = self._logic_method_name(report_type)
        args = (self.company_id, from_date, to_date, filters)
        self._start_report_worker(method_name, args, self._report_key(report_type))

    def load_report(self):
        """Backward-compatible wrapper for older callers."""
        self.load_data()

    def apply_filters(self):
        """Compatibility entry point used by filter-style callers."""
        self.load_data()

    def populate_table(self, rows: List[Dict[str, Any]], key: str):
        self.current_rows = rows
        self.current_columns = REPORT_COLUMNS[key]
        headers = ['SL No'] + [label for label, data_key in self.current_columns]
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(0)
        if not rows:
            self.show_no_data('No data found for selected filters.', preserve_headers=True)
            return
        self.table.setRowCount(len(rows))
        total_amount = 0.0
        total_tax = 0.0
        for row_index, row_data in enumerate(rows):
            sl_item = QTableWidgetItem(str(row_index + 1))
            sl_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_index, 0, sl_item)
            total_amount += safe_float(row_data.get('grand_total'))
            total_tax += safe_float(row_data.get('tax_total') or row_data.get('tax_amount'))
            for col_index, (label, data_key) in enumerate(self.current_columns, start=1):
                value = row_data.get(data_key, '')
                if data_key in PERCENT_KEYS:
                    rate = safe_float(value)
                    text = f'{rate:g}%'
                elif data_key in AMOUNT_KEYS:
                    text = f'{safe_float(value):,.2f}'
                elif data_key == 'category' and not str(value or '').strip():
                    text = 'Uncategorized'
                elif is_date_field_key(data_key):
                    text = format_display_date(value)
                else:
                    text = str(value if value is not None else '')
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, row_data)
                if data_key in AMOUNT_KEYS or data_key in PERCENT_KEYS:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if data_key == 'profit':
                    profit_val = safe_float(value)
                    if profit_val < 0:
                        item.setForeground(QColor('#ef4444'))
                    elif profit_val > 0:
                        item.setForeground(QColor('#22c55e'))
                self.table.setItem(row_index, col_index, item)
        apply_adjustable_table_columns(self.table, sl_no_column=0, sl_no_width=60)
        memory_attr = f"table_{memory_table_attr_slug(key)}"
        self._ui_memory_active_table_attr = memory_attr
        self._ui_memory_active_table = self.table
        self._restore_memory_table(self.table, memory_attr)
        self.summary_label.setText(f'Rows: {len(rows)}    Total Tax: {total_tax:,.2f}    Total Amount: {total_amount:,.2f}')
        self._set_footer_total('rows', str(len(rows)))
        self._set_footer_total('total_tax', f'{total_tax:,.2f}')
        self._set_footer_total('total_amount', f'{total_amount:,.2f}')

    def show_no_data(self, message: str, preserve_headers: bool=False):
        if not preserve_headers:
            self.table.clear()
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(['Message'])
        self.table.setRowCount(1)
        item = QTableWidgetItem(message)
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(0, 0, item)
        if self.table.columnCount() > 1:
            self.table.setSpan(0, 0, 1, self.table.columnCount())
        self.summary_label.setText(message)
        if hasattr(self, 'footer_total_labels'):
            self._set_footer_total('rows', '0')
            self._set_footer_total('total_tax', '0.00')
            self._set_footer_total('total_amount', '0.00')

    def _set_footer_total(self, key: str, value: str) -> None:
        """Set one combined footer metric while preserving its title text."""
        label = self.footer_total_labels.get(key)
        title = self.footer_total_titles.get(key, key)
        if label is not None:
            set_footer_metric(label, title, value)

    def _row_data_from_item(self, item: QTableWidgetItem) -> Dict[str, Any]:
        if not item:
            return {}
        data = item.data(Qt.UserRole)
        return data if isinstance(data, dict) else {}

    def open_detail_from_row(self, item: QTableWidgetItem):
        row_data = self._row_data_from_item(item)
        if not row_data:
            return
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        report_type = self.report_combo.currentText()
        if 'Profit' in report_type:
            sale_id = row_data.get('sale_id')
            if sale_id:
                try:
                    from ui.sales_entry import SalesEntryWidget
                    from ui.ui_memory import apply_standard_window_chrome
                    from PySide6.QtWidgets import QApplication
                    sales_entry = SalesEntryWidget(self.db)
                    sales_entry.setParent(self)
                    apply_standard_window_chrome(sales_entry)
                    sales_entry.load_sale_by_id(sale_id)
                    sales_entry.show()
                    screen = QApplication.primaryScreen()
                    screen_geometry = screen.availableGeometry()
                    window_width = sales_entry.width()
                    window_height = sales_entry.height()
                    if window_width > screen_geometry.width():
                        window_width = screen_geometry.width() - 50
                    if window_height > screen_geometry.height():
                        window_height = screen_geometry.height() - 50
                    sales_entry.resize(window_width, window_height)
                    x = max(0, (screen_geometry.width() - window_width) // 2)
                    y = max(0, (screen_geometry.height() - window_height) // 2)
                    sales_entry.move(x, y)
                except Exception as e:
                    QMessageBox.information(self, 'Error', f'Could not open Sales Entry: {str(e)}')
            else:
                QMessageBox.information(self, 'Info', 'No sale ID available for this row.')
            return
        voucher_id = row_data.get('voucher_id')
        if voucher_id:
            detail = self.logic.get_bill_detail(self.company_id, int(voucher_id))
            if not detail.get('success'):
                QMessageBox.information(self, 'Details', detail.get('message', 'No voucher details found.'))
                return
            voucher_type = row_data.get('voucher_type') or self.title.split()[0]
            dialog = VoucherDetailDialog(f'{self.title} Details', detail, self, voucher_id=int(voucher_id), voucher_type=voucher_type)
            dialog.exec()
            return
        summary = self.logic.get_summary_detail_rows(self.company_id, from_date, to_date, report_type, row_data, self._filters())
        rows = summary.get('data', []) if summary.get('success') else []
        dialog = SummaryDetailDialog(f'{self.title} Supporting Details', rows, self)
        dialog.exec()

    def show_export_menu(self):
        """Show export menu at button position. Heavy imports happen only after user picks an option."""
        pos = self.export_btn.mapToGlobal(self.export_btn.rect().bottomLeft())
        action = self.export_menu.exec(pos)
        if action == self.excel_action:
            self.export_excel()
        elif action == self.pdf_action:
            self.export_pdf()

    def export_excel(self):
        try:
            from openpyxl import Workbook
        except Exception:
            QMessageBox.information(self, 'Export', 'openpyxl is not installed.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export Excel', f'{self.title}.xlsx', 'Excel Files (*.xlsx)')
        if not path:
            return
        wb = Workbook()
        ws = wb.active
        ws.title = self.title[:31]
        headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
        ws.append(headers)
        for row in range(self.table.rowCount()):
            ws.append([self.table.item(row, col).text() if self.table.item(row, col) else '' for col in range(self.table.columnCount())])
        wb.save(path)
        QMessageBox.information(self, 'Export', 'Excel export completed.')

    def export_pdf(self):
        """Open the current report in the universal print/PDF preview dialog."""
        if self.table.rowCount() == 0:
            QMessageBox.information(self, 'No Data', 'Load report data first.')
            return
        subtitle = f"{self.report_combo.currentText()} | {qdate_to_display(self.from_date.date())} to {qdate_to_display(self.to_date.date())}"
        filters = []
        for label, widget in (
            ('Party', self.party_search),
            ('Category', self.category_search),
            ('Barcode', self.barcode_search),
            ('Product', self.product_search),
            ('Search', self.search_input),
        ):
            value = widget.text().strip()
            if value:
                filters.append(f'{label}: {value}')
        if self.tax_filter.currentData() is not None:
            filters.append(f'GST: {self.tax_filter.currentText()}')
        filters.append(self.summary_label.text())
        html_string = table_widget_to_html(self.table, self.title, subtitle, filters)
        dialog = UniversalPreviewDialog(html_string, self)
        dialog.exec()