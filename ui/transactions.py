"""
Transactions widget for the Accounting Desktop Application.
Manages income, expenses, and transfers between accounts.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QLineEdit, QDateEdit, QAbstractItemView
from PySide6.QtCore import Qt, QDate
from config import COLORS
from ui.table_header_utils import apply_adjustable_table_columns
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class TransactionsWidget(UiMemoryMixin, QWidget):
    """Transactions widget for managing financial transactions."""

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self._init_ui_memory()

    def setup_ui(self):
        """Setup transactions UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        header_layout = QHBoxLayout()
        title = QLabel('Transactions')
        title.setStyleSheet(f"\n            QLabel {{\n                color: {COLORS['text_primary']};\n                font-size: 24px;\n                font-weight: bold;\n            }}\n        ")
        header_layout.addWidget(title)
        header_layout.addStretch()
        add_btn = QPushButton('Add Transaction')
        add_btn.setStyleSheet(f"\n            QPushButton {{\n                background-color: {COLORS['primary']};\n                color: white;\n                border: none;\n                padding: 10px 20px;\n                border-radius: 6px;\n                font-size: 14px;\n                font-weight: bold;\n            }}\n            QPushButton:hover {{\n                background-color: {COLORS['primary_dark']};\n            }}\n        ")
        header_layout.addWidget(add_btn)
        layout.addLayout(header_layout)
        form_frame = QFrame()
        form_frame.setStyleSheet(f"\n            QFrame {{\n                background-color: {COLORS['surface']};\n                border-radius: 8px;\n                padding: 16px;\n            }}\n        ")
        form_layout = QHBoxLayout(form_frame)
        self.date_edit = QDateEdit()
        configure_qdate_edit(self.date_edit)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setStyleSheet(f"\n            QDateEdit {{\n                background-color: {COLORS['card']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                padding: 8px;\n                border-radius: 4px;\n            }}\n        ")
        form_layout.addWidget(QLabel('Date:'))
        form_layout.addWidget(self.date_edit)
        self.type_combo = QComboBox()
        self.type_combo.addItems(['Income', 'Expense', 'Transfer'])
        self.type_combo.setStyleSheet(f"\n            QComboBox {{\n                background-color: {COLORS['card']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                padding: 8px;\n                border-radius: 4px;\n            }}\n        ")
        form_layout.addWidget(QLabel('Type:'))
        form_layout.addWidget(self.type_combo)
        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText('0.00')
        self.amount_edit.setStyleSheet(f"\n            QLineEdit {{\n                background-color: {COLORS['card']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                padding: 8px;\n                border-radius: 4px;\n            }}\n        ")
        form_layout.addWidget(QLabel('Amount:'))
        form_layout.addWidget(self.amount_edit)
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText('Description')
        self.description_edit.setStyleSheet(f"\n            QLineEdit {{\n                background-color: {COLORS['card']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                padding: 8px;\n                border-radius: 4px;\n            }}\n        ")
        form_layout.addWidget(QLabel('Description:'))
        form_layout.addWidget(self.description_edit)
        save_btn = QPushButton('Save')
        save_btn.setStyleSheet(f"\n            QPushButton {{\n                background-color: {COLORS['success']};\n                color: white;\n                border: none;\n                padding: 8px 16px;\n                border-radius: 4px;\n                font-weight: bold;\n            }}\n        ")
        form_layout.addWidget(save_btn)
        form_layout.addStretch()
        layout.addWidget(form_frame)
        self.transactions_table = QTableWidget()
        self.transactions_table.setColumnCount(6)
        self.transactions_table.setHorizontalHeaderLabels(['Date', 'Type', 'Description', 'Account', 'Amount', 'Actions'])
        self.transactions_table.setStyleSheet(f"\n            QTableWidget {{\n                background-color: {COLORS['surface']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 8px;\n                gridline-color: {COLORS['border']};\n                selection-background-color: {COLORS['primary']};\n            }}\n            QTableWidget::item {{\n                padding: 8px;\n                color: {COLORS['text_primary']};\n            }}\n            QTableWidget::item:selected {{\n                background-color: {COLORS['primary']};\n            }}\n            QHeaderView::section {{\n                background-color: {COLORS['card']};\n                color: {COLORS['text_primary']};\n                padding: 10px;\n                border: none;\n                font-weight: bold;\n            }}\n        ")
        self.transactions_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.add_sample_transactions()
        apply_adjustable_table_columns(self.transactions_table)
        layout.addWidget(self.transactions_table)

    def add_sample_transactions(self):
        """Add sample transaction data."""
        transactions = [['2024-01-15', 'Income', 'Salary', 'Checking', '$3,250.00'], ['2024-01-14', 'Expense', 'Grocery Store', 'Checking', '-$125.50'], ['2024-01-13', 'Expense', 'Gas Station', 'Credit Card', '-$45.00'], ['2024-01-12', 'Income', 'Freelance Project', 'Checking', '$500.00'], ['2024-01-11', 'Expense', 'Restaurant', 'Credit Card', '-$67.80']]
        self.transactions_table.setRowCount(len(transactions))
        for row, transaction in enumerate(transactions):
            for col, value in enumerate(transaction):
                item = QTableWidgetItem(value)
                if col == 4:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.transactions_table.setItem(row, col, item)
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(5)
            edit_btn = QPushButton('Edit')
            edit_btn.setStyleSheet(f"\n                QPushButton {{\n                    background-color: {COLORS['info']};\n                    color: white;\n                    border: none;\n                    padding: 4px 8px;\n                    border-radius: 4px;\n                    font-size: 12px;\n                }}\n            ")
            actions_layout.addWidget(edit_btn)
            delete_btn = QPushButton('Delete')
            delete_btn.setStyleSheet(f"\n                QPushButton {{\n                    background-color: {COLORS['error']};\n                    color: white;\n                    border: none;\n                    padding: 4px 8px;\n                    border-radius: 4px;\n                    font-size: 12px;\n                }}\n            ")
            actions_layout.addWidget(delete_btn)
            self.transactions_table.setCellWidget(row, 5, actions_widget)