"""
Cash Tender History page.

Displays the read-only Cash Tender audit log captured after Sales Entry saves.
"""
from typing import Any, Dict, List
from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from config import COLORS
from db import Database
from ui.book_report_common import compact_primary_button_style, compact_topbar_frame_style
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class CashTenderHistoryPageWidget(UiMemoryMixin, QWidget):
    """Read-only page for Cash Tender history records."""
    HEADERS = ('Bill No', 'Bill Amount', 'Cash Received', 'Balance Returned', 'Payment Mode', 'Created At')

    def __init__(self, db=None, parent=None):
        """Initialize the history page and schedule the first refresh."""
        super().__init__(parent)
        self.db = db or Database()
        self.setup_ui()
        QTimer.singleShot(100, self.refresh)
        self._init_ui_memory(table_attrs=("table",))

    def setup_ui(self):
        """Build the Cash Tender History page layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        title = QLabel('Cash Tender History')
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {COLORS['text_primary']};")
        layout.addWidget(title)
        toolbar = QFrame()
        toolbar.setStyleSheet(compact_topbar_frame_style())
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(12)
        info_label = QLabel('Read-only log of cash received and balance returned after Sales saves.')
        info_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; font-weight: bold;")
        toolbar_layout.addWidget(info_label)
        toolbar_layout.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setStyleSheet(compact_primary_button_style())
        self.refresh_btn.setFixedWidth(90)
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar_layout.addWidget(self.refresh_btn)
        layout.addWidget(toolbar)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        apply_read_only_report_table_selection(self.table)
        self.table.verticalHeader().setDefaultSectionSize(28)
        layout.addWidget(self.table, 1)
        self.status_label = QLabel('No records loaded.')
        self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(self.status_label)

    def refresh(self):
        """Reload Cash Tender history rows from the database."""
        try:
            rows = self._load_history_rows()
            self.populate_table(rows)
            self.status_label.setText(f'{len(rows)} Cash Tender record(s) loaded.')
        except Exception as exc:
            QMessageBox.warning(self, 'Cash Tender History', f'Could not load Cash Tender history: {exc}')

    def _load_history_rows(self) -> List[Dict[str, Any]]:
        """Fetch rows through the database layer with explicit column selection."""
        if hasattr(self.db, 'get_cash_tender_history'):
            return self.db.get_cash_tender_history()
        ph = self.db._get_placeholder()
        query = f'\n            SELECT bill_no, bill_amount, cash_received,\n                   balance_returned, payment_mode, created_at\n            FROM cash_tender_history\n            WHERE id >= {ph}\n            ORDER BY id DESC\n        '
        return self.db.execute_query(query, (0,)) or []

    def populate_table(self, rows: List[Dict[str, Any]]):
        """Populate the read-only table with history rows."""
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = (str(row.get('bill_no') or ''), self._format_amount(row.get('bill_amount')), self._format_amount(row.get('cash_received')), self._format_amount(row.get('balance_returned')), str(row.get('payment_mode') or 'Cash'), str(row.get('created_at') or ''))
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, col_idx, item)
            if row_idx % 50 == 0:
                QCoreApplication.processEvents()
        self.table.blockSignals(False)
        apply_adjustable_table_columns(self.table)
        self._restore_memory_table(self.table, "table")

    def _format_amount(self, value: Any) -> str:
        """Format a stored numeric value for display."""
        try:
            return f'{float(value or 0):.2f}'
        except (TypeError, ValueError):
            return '0.00'