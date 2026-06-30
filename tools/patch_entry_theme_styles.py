"""Patch entry-screen UI mixins to use shared theme style delegates."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CALENDAR_METHOD = '''    def apply_calendar_style(self, date_edit):
        """Apply theme-aware calendar styling to a QDateEdit popup."""
        from PySide6.QtWidgets import QToolButton
        from PySide6.QtGui import QTextCharFormat, QColor, QFont
        from PySide6.QtCore import QDate, Qt as _Qt

        calendar = date_edit.calendarWidget()
        if calendar is None:
            return

        calendar.setStyleSheet(theme.entry_calendar_style())

        prev_btn = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        if prev_btn:
            prev_btn.setArrowType(_Qt.NoArrow)
            prev_btn.setToolButtonStyle(_Qt.ToolButtonTextOnly)
            prev_btn.setText("<")
            prev_btn.setFixedSize(24, 24)
        next_btn = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        if next_btn:
            next_btn.setArrowType(_Qt.NoArrow)
            next_btn.setToolButtonStyle(_Qt.ToolButtonTextOnly)
            next_btn.setText(">")
            next_btn.setFixedSize(24, 24)

        colors = theme._theme_colors()
        today_bg = colors["focus_border"] if theme._is_light_theme() else "#0056b3"
        today_format = QTextCharFormat()
        today_format.setBackground(QColor(today_bg))
        today_format.setForeground(QColor("#FFFFFF"))
        today_format.setFontWeight(QFont.Bold)
        calendar.setDateTextFormat(QDate.currentDate(), today_format)
'''

STYLE_CALENDAR_METHOD = '''    def _style_date_calendar(self, date_edit):
        """Apply theme-aware calendar styling to a QDateEdit popup."""
        from PySide6.QtWidgets import QToolButton
        from PySide6.QtGui import QTextCharFormat, QColor, QFont
        from PySide6.QtCore import QDate, Qt as _Qt

        calendar = date_edit.calendarWidget()
        if calendar is None:
            return

        calendar.setStyleSheet(theme.entry_calendar_style())

        prev_btn = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        if prev_btn:
            prev_btn.setArrowType(_Qt.NoArrow)
            prev_btn.setToolButtonStyle(_Qt.ToolButtonTextOnly)
            prev_btn.setText("<")
            prev_btn.setFixedSize(24, 24)
        next_btn = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        if next_btn:
            next_btn.setArrowType(_Qt.NoArrow)
            next_btn.setToolButtonStyle(_Qt.ToolButtonTextOnly)
            next_btn.setText(">")
            next_btn.setFixedSize(24, 24)

        colors = theme._theme_colors()
        today_bg = colors["focus_border"] if theme._is_light_theme() else "#0056b3"
        today_format = QTextCharFormat()
        today_format.setBackground(QColor(today_bg))
        today_format.setForeground(QColor("#FFFFFF"))
        today_format.setFontWeight(QFont.Bold)
        calendar.setDateTextFormat(QDate.currentDate(), today_format)
'''

ENTRY_STYLE_BLOCK = '''    # ==================== STYLE METHODS ====================

    def header_strip_style(self):
        return theme.entry_header_strip_style()

    def page_title_style(self):
        return theme.entry_page_title_label_style()

    def invoice_command_strip_style(self):
        return theme.entry_command_strip_style()

    def party_matrix_style(self):
        return theme.entry_section_frame_style()

    def product_strip_style(self):
        return theme.entry_inset_frame_style()

    def options_strip_style(self):
        return theme.entry_section_frame_style()

    def table_zone_style(self):
        return theme.entry_inset_frame_style()

    def footer_panel_style(self):
        return theme.entry_section_frame_style()

    def action_zone_style(self):
        return theme.entry_inset_frame_style()

    def adjustment_zone_style(self):
        return theme.entry_inset_frame_style()

    def tax_zone_style(self):
        return theme.entry_inset_frame_style()

    def compact_input_style(self):
        return theme.sales_compact_input_style()

    def barcode_input_style(self):
        return theme.sales_barcode_input_style()

    def micro_label_style(self):
        return theme.sales_micro_label_style()

    def nav_button_style(self):
        return theme.sales_nav_button_style()

    def compact_button_style(self):
        return theme.sales_compact_button_style()

    def primary_button_style(self):
        return theme.sales_primary_button_style()

    def danger_button_style(self):
        return theme.sales_danger_button_style()

    def save_button_style(self):
        return theme.entry_save_button_style()

    def table_style(self):
        return theme.sales_billing_table_style()

    def table_header_style(self):
        return theme.entry_table_header_style()

    def footer_label_style(self):
        return theme.entry_footer_label_style()

    def footer_input_style(self):
        return theme.sales_compact_input_style()

    def footer_input_readonly_style(self):
        return theme.entry_footer_input_readonly_style()

    def footer_discount_box_style(self):
        return theme.entry_footer_input_style()

    def footer_value_style(self):
        return theme.entry_value_style("input_text")

    def footer_final_style(self):
        return theme.entry_info_value_style()

    def grand_total_green_style(self):
        return theme.entry_value_style("accent_highlight")
'''

SALES_RETURN_EXTRA = '''
    def status_strip_style(self):
        return theme.entry_section_frame_style()

    def status_label_style(self):
        return theme.sales_status_label_style()

    def status_value_style(self):
        return theme.sales_status_value_style()

    def status_checkbox_style(self):
        return theme.sales_status_checkbox_style()

    def nav_box_style(self):
        return theme.sales_nav_box_style()

    def round_off_input_style(self):
        colors = theme._theme_colors()
        return (
            f"QLineEdit {{ background-color: transparent; border: none; "
            f"color: {colors['input_text']}; font-size: 10px; padding: 0px; }}"
        )

    def discount_percent_hint_style(self):
        return theme.entry_micro_hint_style()
'''


def replace_from_marker(text: str, marker: str, new_tail: str) -> str:
    idx = text.index(marker)
    return text[:idx] + new_tail


def patch_sales_return_ui() -> None:
    path = ROOT / "ui" / "sales_return_ui.py"
    text = path.read_text(encoding="utf-8")
    start = text.index("    def apply_calendar_style(self, date_edit):")
    end = text.index("    # ==================== ZONE A - PAGE HEADER STRIP ====================")
    text = text[:start] + CALENDAR_METHOD + "\n\n" + text[end:]
    text = text.replace(
        """        export_pdf_btn.setStyleSheet(\"\"\"
            QPushButton {
                background-color: #2563eb; color: #f1f5f9;
                border: 1px solid #3b82f6; border-radius: 3px;
                font-size: 10px; font-weight: bold; padding: 3px 6px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:pressed { background-color: #1e40af; }
        \"\"\")""",
        "        export_pdf_btn.setStyleSheet(theme.sales_primary_button_style())",
    )
    text = text.replace(
        'self.discount_percent_label.setStyleSheet("QLabel { color: #8ab4f8; font-size: 7px; padding: 0px; margin: 0px; }")',
        "self.discount_percent_label.setStyleSheet(self.discount_percent_hint_style())",
    )
    text = text.replace(
        """self.round_off_input.setStyleSheet(\"\"\"QLineEdit {
            background-color: transparent;
            border: none;
            color: #f1f5f9;
            font-size: 10px;
            padding: 0px;
        }\"\"\")""",
        "self.round_off_input.setStyleSheet(self.round_off_input_style())",
    )
    sales_styles = ENTRY_STYLE_BLOCK.replace(
        "    def footer_input_style(self):\n        return theme.sales_compact_input_style()",
        "    def footer_input_style(self):\n        return theme.entry_footer_input_style()",
    ) + SALES_RETURN_EXTRA
    text = replace_from_marker(text, "    # ==================== STYLE METHODS ====================", sales_styles)
    path.write_text(text, encoding="utf-8")
    print("patched sales_return_ui.py")


def patch_purchase_return_ui() -> None:
    path = ROOT / "ui" / "purchase_return_ui.py"
    text = path.read_text(encoding="utf-8")
    if "from ui import theme" not in text:
        text = text.replace(
            "from PySide6.QtGui import QDoubleValidator\n\nfrom .theme import GST_STATE_CODES",
            "from PySide6.QtGui import QDoubleValidator\n\nfrom ui import theme\nfrom .theme import GST_STATE_CODES",
        )
    text = replace_from_marker(
        text,
        "    # ==================== STYLES (identical to purchase_entry_ui.py) ====================",
        ENTRY_STYLE_BLOCK,
    )
    path.write_text(text, encoding="utf-8")
    print("patched purchase_return_ui.py")


def patch_purchase_order_ui() -> None:
    path = ROOT / "ui" / "purchase_order_ui.py"
    text = path.read_text(encoding="utf-8")
    start = text.index("    def _style_date_calendar(self, date_edit):")
    end = text.index("    # ==================== STYLE METHODS ====================")
    text = text[:start] + STYLE_CALENDAR_METHOD + "\n\n" + text[end:]
    po_styles = ENTRY_STYLE_BLOCK.replace(
        "    def table_zone_style(self):\n        return theme.entry_inset_frame_style()",
        "    def table_zone_style(self):\n        return theme.sales_table_zone_style()",
    ).replace(
        "    def grand_total_green_style(self):\n        return theme.entry_value_style(\"accent_highlight\")",
        "    def grand_total_green_style(self):\n        return theme.entry_grand_total_style()",
    )
    text = replace_from_marker(text, "    # ==================== STYLE METHODS ====================", po_styles)
    path.write_text(text, encoding="utf-8")
    print("patched purchase_order_ui.py")


def patch_page_backgrounds() -> None:
    for name in ("sales_return.py", "purchase_return.py", "purchase_order.py"):
        path = ROOT / "ui" / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        needle = "    def setup_ui(self):\n        layout = QVBoxLayout(self)"
        insert = (
            "    def setup_ui(self):\n"
            "        from ui import theme\n"
            "        self.setStyleSheet(theme.entry_page_background_style())\n"
            "        layout = QVBoxLayout(self)"
        )
        if needle in text and "entry_page_background_style" not in text:
            text = text.replace(needle, insert, 1)
            path.write_text(text, encoding="utf-8")
            print(f"patched {name} page background")


def main() -> None:
    patch_sales_return_ui()
    patch_purchase_return_ui()
    patch_purchase_order_ui()
    patch_page_backgrounds()


if __name__ == "__main__":
    main()
