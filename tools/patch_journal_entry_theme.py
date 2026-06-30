from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / "ui" / "journal_entry_page.py"
t = p.read_text(encoding="utf-8")

if "from ui import theme" not in t:
    t = t.replace(
        "from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection",
        "from ui import theme\nfrom ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection",
    )

t = t.replace(
    "        layout.setSpacing(10)\n        self.setLayout(layout)",
    "        layout.setSpacing(10)\n        self.setStyleSheet(theme.entry_page_background_style())\n        self.setLayout(layout)",
)

replacements = [
    (
        '''        top_bar_frame.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #374151;
                border-radius: 4px;
            }
        """)''',
        "        top_bar_frame.setStyleSheet(theme.entry_header_strip_style())",
    ),
    (
        'voucher_label.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 11px;")',
        "voucher_label.setStyleSheet(theme.sales_micro_label_style())",
    ),
    (
        'date_label.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 11px;")',
        "date_label.setStyleSheet(theme.sales_micro_label_style())",
    ),
    (
        'remark_label.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 11px;")',
        "remark_label.setStyleSheet(theme.sales_micro_label_style())",
    ),
    (
        'lines_label.setStyleSheet("font-weight: bold; color: #fbbf24; font-size: 12px;")',
        "lines_label.setStyleSheet(theme.sales_micro_label_style())",
    ),
    (
        'separator.setStyleSheet("background-color: #374151;")',
        "separator.setStyleSheet(f\"background-color: {theme._theme_colors()['border']};\")",
    ),
    (
        'separator2.setStyleSheet("background-color: #374151;")',
        "separator2.setStyleSheet(f\"background-color: {theme._theme_colors()['border']};\")",
    ),
    (
        '''        self.lines_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e293b;
                color: #f1f5f9;
                gridline-color: #334155;
                border: 1px solid #334155;
            }
            QHeaderView::section {
                background-color: #334155;
                color: #fbbf24;
                padding: 6px;
                border: 1px solid #475569;
                font-weight: bold;
            }
        """)''',
        "        self.lines_table.setStyleSheet(theme.sales_billing_table_style())\n"
        "        self.lines_table.horizontalHeader().setStyleSheet(theme.entry_table_header_style())",
    ),
    (
        '''        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #f1f5f9;
                border: 1px solid #475569;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 3px 6px;
            }
            QPushButton:hover { background-color: #475569; }
        """)''',
        "        reset_btn.setStyleSheet(theme.sales_compact_button_style())",
    ),
    (
        '''        debit_edit.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #475569;
                border-radius: 2px;
                padding: 3px 6px;
                font-size: 11px;
            }
        """)''',
        "        debit_edit.setStyleSheet(theme.sales_compact_input_style())",
    ),
    (
        '''        credit_edit.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #475569;
                border-radius: 2px;
                padding: 3px 6px;
                font-size: 11px;
            }
        """)''',
        "        credit_edit.setStyleSheet(theme.sales_compact_input_style())",
    ),
    (
        '''        narration_edit.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #475569;
                border-radius: 2px;
                padding: 3px 6px;
                font-size: 11px;
            }
        """)''',
        "        narration_edit.setStyleSheet(theme.sales_compact_input_style())",
    ),
]

for old, new in replacements:
    t = t.replace(old, new)

# Replace nav_button_style method body
t = t.replace(
    '''    def nav_button_style(self):
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
    '''    def nav_button_style(self):
        return theme.sales_nav_button_style()''',
)

p.write_text(t, encoding="utf-8")
print("patched journal_entry_page.py")
