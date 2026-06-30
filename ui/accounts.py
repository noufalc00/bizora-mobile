"""
Accounts widget for the Accounting Desktop Application.
Manages bank accounts, credit cards, and other financial accounts.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt
from ui import theme
from ui.table_header_utils import apply_adjustable_table_columns
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class AccountsWidget(UiMemoryMixin, QWidget):
    """Accounts widget for managing financial accounts."""

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self._init_ui_memory()

    def setup_ui(self):
        """Setup accounts UI."""
        self.setStyleSheet(theme.master_page_background_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        header_layout = QHBoxLayout()
        title = QLabel('Accounts')
        title.setStyleSheet(theme.master_page_title_style(24))
        header_layout.addWidget(title)
        header_layout.addStretch()
        add_btn = QPushButton('Add Account')
        add_btn.setStyleSheet(theme.master_primary_action_button_style('10px 20px', 14))
        header_layout.addWidget(add_btn)
        layout.addLayout(header_layout)
        self.accounts_table = QTableWidget()
        self.accounts_table.setColumnCount(5)
        self.accounts_table.setHorizontalHeaderLabels(['Account Name', 'Type', 'Balance', 'Currency', 'Actions'])
        self.accounts_table.setStyleSheet(theme.master_table_style())
        self.accounts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.add_sample_accounts()
        apply_adjustable_table_columns(self.accounts_table)
        layout.addWidget(self.accounts_table)
        summary_frame = QFrame()
        colors = theme.legacy_colors()
        summary_frame.setStyleSheet(f"\n            QFrame {{\n                background-color: {colors['surface']};\n                border-radius: 8px;\n                padding: 16px;\n                border: 1px solid {colors['border']};\n            }}\n        ")
        summary_layout = QHBoxLayout(summary_frame)
        total_balance = QLabel('Total Balance: $12,450.00')
        total_balance.setStyleSheet(f"\n            QLabel {{\n                color: {colors['text_primary']};\n                font-size: 16px;\n                font-weight: bold;\n                background: transparent;\n                border: none;\n            }}\n        ")
        summary_layout.addWidget(total_balance)
        summary_layout.addStretch()
        account_count = QLabel('Accounts: 4')
        account_count.setStyleSheet(f"\n            QLabel {{\n                color: {colors['text_secondary']};\n                font-size: 14px;\n                background: transparent;\n                border: none;\n            }}\n        ")
        summary_layout.addWidget(account_count)
        layout.addWidget(summary_frame)

    def add_sample_accounts(self):
        """Add sample account data."""
        accounts = [['Checking Account', 'Checking', '$5,230.50', 'USD'], ['Savings Account', 'Savings', '$7,219.50', 'USD'], ['Credit Card', 'Credit', '-$1,250.00', 'USD'], ['Cash Wallet', 'Cash', '$250.00', 'USD']]
        self.accounts_table.setRowCount(len(accounts))
        for row, account in enumerate(accounts):
            for col, value in enumerate(account):
                item = QTableWidgetItem(value)
                if col == 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.accounts_table.setItem(row, col, item)