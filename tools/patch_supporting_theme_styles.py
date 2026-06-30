"""Patch stock adjustment UI and voucher grid to use theme helpers."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_stock_adjustment_ui() -> None:
    path = ROOT / "ui" / "stock_adjustment_ui.py"
    text = path.read_text(encoding="utf-8")
    if "entry_page_background_style" not in text:
        text = text.replace(
            "        main_layout = QVBoxLayout(self)\n        main_layout.setContentsMargins(8, 8, 8, 8)",
            "        self.setStyleSheet(theme.entry_page_background_style())\n"
            "        main_layout = QVBoxLayout(self)\n        main_layout.setContentsMargins(8, 8, 8, 8)",
            1,
        )
    replacements = [
        (
            '''        frame.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
            }
        """)''',
            "        frame.setStyleSheet(theme.entry_header_strip_style())",
        ),
        (
            'voucher_label.setStyleSheet("color: #facc15; font-size: 10px; font-weight: bold;")',
            "voucher_label.setStyleSheet(theme.sales_micro_label_style())",
        ),
        (
            '''        self.voucher_no_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a;
                border: 1px solid #475569;
                border-radius: 2px;
                color: #f1f5f9;
                font-size: 11px;
                padding: 3px 6px;
            }
        """)''',
            "        self.voucher_no_input.setStyleSheet(theme.sales_compact_input_style())",
        ),
        (
            'date_label.setStyleSheet("color: #facc15; font-size: 10px; font-weight: bold;")',
            "date_label.setStyleSheet(theme.sales_micro_label_style())",
        ),
        (
            '''        self.date_input.setStyleSheet("""
            QDateEdit {
                background-color: #0f172a;
                border: 1px solid #475569;
                border-radius: 2px;
                color: #f1f5f9;
                font-size: 11px;
                padding: 3px 6px;
            }
        """)''',
            "        self.date_input.setStyleSheet(theme.sales_compact_input_style())",
        ),
        (
            'narration_label.setStyleSheet("color: #facc15; font-size: 10px; font-weight: bold;")',
            "narration_label.setStyleSheet(theme.sales_micro_label_style())",
        ),
        (
            '''        self.narration_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a;
                border: 1px solid #475569;
                border-radius: 2px;
                color: #f1f5f9;
                font-size: 11px;
                padding: 3px 6px;
            }
        """)''',
            "        self.narration_input.setStyleSheet(theme.sales_compact_input_style())",
        ),
        (
            '''        frame.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
            }
        """)''',
            "        frame.setStyleSheet(theme.entry_inset_frame_style())",
        ),
        (
            'barcode_label.setStyleSheet("color: #facc15; font-size: 10px; font-weight: bold;")',
            "barcode_label.setStyleSheet(theme.sales_micro_label_style())",
        ),
        (
            'product_label.setStyleSheet("color: #facc15; font-size: 10px; font-weight: bold;")',
            "product_label.setStyleSheet(theme.sales_micro_label_style())",
        ),
        (
            '''        self.product_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a;
                border: 1px solid #475569;
                border-radius: 2px;
                color: #f1f5f9;
                font-size: 11px;
                padding: 3px 6px;
            }
        """)''',
            "        self.product_input.setStyleSheet(theme.sales_compact_input_style())",
        ),
        (
            'stock_label.setStyleSheet("color: #facc15; font-size: 10px; font-weight: bold;")',
            "stock_label.setStyleSheet(theme.sales_micro_label_style())",
        ),
        (
            '''        self.stock_display.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 2px;
                color: #94a3b8;
                font-size: 11px;
                padding: 3px 6px;
            }
        """)''',
            "        self.stock_display.setStyleSheet(theme.entry_footer_input_readonly_style())",
        ),
        (
            'rate_label.setStyleSheet("color: #facc15; font-size: 10px; font-weight: bold;")',
            "rate_label.setStyleSheet(theme.sales_micro_label_style())",
        ),
        (
            '''        self.rate_display.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 2px;
                color: #94a3b8;
                font-size: 11px;
                padding: 3px 6px;
            }
        """)''',
            "        self.rate_display.setStyleSheet(theme.entry_footer_input_readonly_style())",
        ),
        (
            'increase_label.setStyleSheet("color: #4ade80; font-size: 10px; font-weight: bold;")',
            'increase_label.setStyleSheet(theme.entry_value_style("accent_highlight"))',
        ),
        (
            'self.total_increase_label.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")',
            'self.total_increase_label.setStyleSheet(theme.entry_value_style("accent_highlight"))',
        ),
        (
            'decrease_label.setStyleSheet("color: #f87171; font-size: 10px; font-weight: bold;")',
            'decrease_label.setStyleSheet(theme.entry_value_style("button_danger"))',
        ),
        (
            'self.total_decrease_label.setStyleSheet("color: #f87171; font-size: 11px; font-weight: bold;")',
            'self.total_decrease_label.setStyleSheet(theme.entry_value_style("button_danger"))',
        ),
        (
            'net_label.setStyleSheet("color: #facc15; font-size: 10px; font-weight: bold;")',
            "net_label.setStyleSheet(theme.sales_micro_label_style())",
        ),
        (
            'self.net_adjustment_label.setStyleSheet("color: #facc15; font-size: 11px; font-weight: bold;")',
            "self.net_adjustment_label.setStyleSheet(theme.entry_value_style(\"accent_label\"))",
        ),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    text = text.replace(
        '''        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #1d4ed8;
                color: #ffffff;
                border: 1px solid #1d4ed8;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)''',
        "        self.save_btn.setStyleSheet(theme.entry_save_button_style())",
    )
    text = text.replace(
        '''        self.remove_item_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: #ffffff;
                border: 1px solid #dc2626;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #ef4444;
            }
        """)''',
        "        self.remove_item_btn.setStyleSheet(theme.sales_danger_button_style())",
    )
    text = text.replace(
        '''        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #f1f5f9;
                border: 1px solid #475569;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)''',
        "        self.clear_btn.setStyleSheet(theme.sales_compact_button_style())",
    )
    path.write_text(text, encoding="utf-8")
    print("patched stock_adjustment_ui.py")


def patch_voucher_grid_common() -> None:
    path = ROOT / "ui" / "voucher_grid_common.py"
    text = path.read_text(encoding="utf-8")
    old_input = '''    @staticmethod
    def input_style() -> str:
        return """
        QLineEdit, QDateEdit {
            background-color: #1e293b;
            border: 1px solid #475569;
            border-radius: 3px;
            color: #f1f5f9;
            font-size: 11px;
            padding: 2px 4px;
        }
        QLineEdit:focus, QDateEdit:focus {
            border: 1px solid #60a5fa;
        }
        QDateEdit::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            border: none;
            width: 20px;
        }
        QDateEdit::down-arrow {
            image: none;
            width: 0px;
            height: 0px;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 4px solid #94a3b8;
            margin-right: 4px;
        }
        """'''
    new_input = '''    @staticmethod
    def input_style() -> str:
        from ui import theme
        return theme.sales_compact_input_style()'''
    text = text.replace(old_input, new_input)

    old_combo = '''    @staticmethod
    def combo_input_style() -> str:
        return """
        QComboBox {
            background-color: #1e293b;
            border: 1px solid #475569;
            border-radius: 3px;
            color: #f1f5f9;
            font-size: 11px;
            padding: 2px 4px;
        }
        QComboBox:focus {
            border: 1px solid #60a5fa;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            border: none;
            width: 20px;
        }
        QComboBox::down-arrow {
            image: none;
            width: 0px;
            height: 0px;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 4px solid #94a3b8;
            margin-right: 4px;
        }
        QComboBox QAbstractItemView {
            background-color: #1e293b;
            color: #f1f5f9;
            border: 1px solid #475569;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }
        """'''
    new_combo = '''    @staticmethod
    def combo_input_style() -> str:
        from ui import theme
        return theme.sales_compact_input_style()'''
    text = text.replace(old_combo, new_combo)

    text = text.replace(
        '''    @staticmethod
    def micro_label_style() -> str:
        return """
        QLabel {
            color: #facc15;
            font-weight: bold;
            font-size: 11px;
            padding: 0px 2px;
            background: transparent;
            border: none;
        }
        """''',
        '''    @staticmethod
    def micro_label_style() -> str:
        from ui import theme
        return theme.sales_micro_label_style()''',
    )
    text = text.replace(
        '''    @staticmethod
    def balance_label_style() -> str:
        return """
        QLabel {
            background-color: #1e293b;
            border: 1px solid #475569;
            border-radius: 3px;
            color: #93c5fd;
            font-size: 11px;
            font-weight: bold;
            padding: 2px 4px;
        }
        """''',
        '''    @staticmethod
    def balance_label_style() -> str:
        from ui import theme
        return theme.entry_footer_input_readonly_style() + " QLabel { color: " + theme._theme_colors()["focus_border"] + "; }"''',
    )
    text = text.replace(
        '''    @staticmethod
    def nav_button_style() -> str:
        return """
        QPushButton {
            background-color: transparent;
            color: #94a3b8;
            border: none;
            font-size: 7px;
            font-weight: bold;
            padding: 0px;
        }
        QPushButton:hover {
            color: #facc15;
            background-color: transparent;
        }
        QPushButton:pressed {
            color: #f1f5f9;
            background-color: transparent;
        }
        """''',
        '''    @staticmethod
    def nav_button_style() -> str:
        from ui import theme
        return theme.sales_nav_button_style()''',
    )
    text = text.replace(
        '''    @staticmethod
    def top_bar_style() -> str:
        return """
        QFrame {
            background-color: #0f172a;
            border: 1px solid #334155;
            border-radius: 4px;
        }
        """''',
        '''    @staticmethod
    def top_bar_style() -> str:
        from ui import theme
        return theme.entry_command_strip_style()''',
    )
    text = text.replace(
        '''    @staticmethod
    def table_style() -> str:
        return """
        QTableWidget {
            background-color: #1e293b;
            color: #f1f5f9;
            gridline-color: #334155;
            border: 1px solid #334155;
            alternate-background-color: #1f2937;
        }
        QTableWidget::item {
            padding: 3px;
        }
        QTableWidget::item:selected {
            background-color: #2563eb;
            color: #ffffff;
        }
        QHeaderView::section {
            background-color: #1e3a5f;
            color: #fbbf24;
            padding: 6px;
            border: 1px solid #334155;
            font-weight: bold;
            font-size: 11px;
        }
        QTableWidget::item:alternate {
            background-color: #1f2937;
        }
        QTableWidget QLineEdit {
            background-color: #1e293b;
            color: #f1f5f9;
            border: 1px solid #475569;
            border-radius: 2px;
            padding: 3px 6px;
            font-size: 11px;
        }
        QTableWidget QLineEdit:focus {
            border: 1px solid #60a5fa;
        }
        """''',
        '''    @staticmethod
    def table_style() -> str:
        from ui import theme
        return theme.sales_billing_table_style()''',
    )
    path.write_text(text, encoding="utf-8")
    print("patched voucher_grid_common.py")


def main() -> None:
    patch_stock_adjustment_ui()
    patch_voucher_grid_common()


if __name__ == "__main__":
    main()
