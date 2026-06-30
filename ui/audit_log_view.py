"""
Audit log viewer for administrative review of voucher activity.

This module displays the tenant-scoped audit_logs table with date and text
filters while keeping database access explicit and parameterized.
"""
from __future__ import annotations
import logging
from typing import Any, List, Optional, Sequence, Tuple
from PySide6.QtCore import QCoreApplication, QDate, Qt, QTimer
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QDateEdit
from config import COLORS, resolve_active_company_id
from db import Database
from ui.book_report_common import compact_date_style, compact_label_style, compact_primary_button_style, compact_search_style, compact_secondary_button_style, compact_topbar_frame_style, report_status_label_style
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
LOGGER = logging.getLogger(__name__)

class AuditLogView(UiMemoryMixin, QWidget):
    """Administrative screen for browsing tenant audit log rows."""
    COLUMNS: Tuple[str, ...] = ('Date', 'Module', 'Action', 'Reference No', 'Description')

    def __init__(self, db: Optional[Database]=None, company_id: Optional[int]=None, parent: Optional[QWidget]=None):
        """
        Initialize the audit log view.

        Args:
            db: Application database instance.
            company_id: Optional tenant identifier; active company is used if omitted.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.db = db or Database()
        self.company_id = int(company_id) if company_id else resolve_active_company_id(self.db)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(350)
        self._search_timer.timeout.connect(self.load_audit_logs)
        self.setObjectName('AuditLogView')
        self._build_ui()
        self.reset_filters(load=False)
        QTimer.singleShot(100, self.load_audit_logs)
        self._init_ui_memory(table_attrs=("table",))

    def _build_ui(self) -> None:
        """Build the audit log screen layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        title = QLabel('Audit Logs')
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {COLORS['text_primary']};")
        layout.addWidget(title)
        subtitle = QLabel('Review user actions for the currently opened company.')
        subtitle.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        layout.addWidget(subtitle)
        self._build_filters(layout)
        self._build_table(layout)
        self.status_label = QLabel('')
        self.status_label.setStyleSheet(report_status_label_style())
        layout.addWidget(self.status_label)

    def _build_filters(self, parent_layout: QVBoxLayout) -> None:
        """Build date and search filters."""
        frame = QFrame()
        frame.setStyleSheet(compact_topbar_frame_style())
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        from_label = QLabel('From Date:')
        from_label.setStyleSheet(compact_label_style())
        layout.addWidget(from_label)
        self.from_date_edit = QDateEdit()
        prepare_report_date_edit(self.from_date_edit, style_sheet=compact_date_style())
        self.from_date_edit.dateChanged.connect(self._queue_refresh)
        layout.addWidget(self.from_date_edit)
        to_label = QLabel('To Date:')
        to_label.setStyleSheet(compact_label_style())
        layout.addWidget(to_label)
        self.to_date_edit = QDateEdit()
        prepare_report_date_edit(self.to_date_edit, style_sheet=compact_date_style())
        self.to_date_edit.dateChanged.connect(self._queue_refresh)
        layout.addWidget(self.to_date_edit)
        search_label = QLabel('Search:')
        search_label.setStyleSheet(compact_label_style())
        layout.addWidget(search_label)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('Reference No or Description')
        self.search_edit.setMinimumWidth(260)
        self.search_edit.setStyleSheet(compact_search_style())
        self.search_edit.textChanged.connect(self._queue_refresh)
        self.search_edit.returnPressed.connect(self.load_audit_logs)
        layout.addWidget(self.search_edit, 1)
        self.refresh_button = QPushButton('Refresh')
        self.refresh_button.setStyleSheet(compact_primary_button_style())
        self.refresh_button.clicked.connect(self.load_audit_logs)
        layout.addWidget(self.refresh_button)
        self.reset_button = QPushButton('Reset')
        self.reset_button.setStyleSheet(compact_secondary_button_style())
        self.reset_button.clicked.connect(self.reset_filters)
        layout.addWidget(self.reset_button)
        parent_layout.addWidget(frame)

    def _build_table(self, parent_layout: QVBoxLayout) -> None:
        """Build the read-only audit log table."""
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        apply_read_only_report_table_selection(self.table)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 180)
        parent_layout.addWidget(self.table, 1)

    def reset_filters(self, load: bool=True) -> None:
        """Reset filters to the current month and optionally reload data."""
        today = QDate.currentDate()
        self.from_date_edit.setDate(today.addDays(-today.day() + 1))
        self.to_date_edit.setDate(today)
        self.search_edit.clear()
        if load:
            self.load_audit_logs()

    def refresh_company(self, company_id: Optional[int]=None) -> None:
        """Refresh the active company and reload tenant-scoped audit rows."""
        self.company_id = int(company_id) if company_id else resolve_active_company_id(self.db)
        self.load_audit_logs()

    def _queue_refresh(self) -> None:
        """Debounce filter changes before loading audit rows."""
        self._search_timer.start()

    def load_audit_logs(self) -> None:
        """Fetch filtered audit logs and render them in the table."""
        self._search_timer.stop()
        self.company_id = self.company_id or resolve_active_company_id(self.db)
        if not self.company_id:
            self.table.setRowCount(0)
            self.status_label.setText('No active company is selected.')
            return
        from_date = qdate_to_db(self.from_date_edit.date())
        to_date = qdate_to_db(self.to_date_edit.date())
        if from_date > to_date:
            self.status_label.setText('From Date cannot be later than To Date.')
            return
        search_text = self.search_edit.text().strip()
        try:
            rows = self._fetch_audit_rows(int(self.company_id), f'{from_date} 00:00:00', f'{to_date} 23:59:59', search_text)
        except Exception as exc:
            LOGGER.exception('AuditLogView fetch failed: company_id=%s from_date=%s to_date=%s search=%r', self.company_id, from_date, to_date, search_text)
            self.table.setRowCount(0)
            self.status_label.setText(f'Unable to load audit logs: {exc}')
            return
        self._populate_table(rows)
        self.status_label.setText(f'{len(rows)} audit log row(s) loaded.')

    def _fetch_audit_rows(self, company_id: int, from_datetime: str, to_datetime: str, search_text: str) -> List[Sequence[Any]]:
        """
        Return audit rows using explicit columns and parameterized filters.

        Args:
            company_id: Tenant identifier to enforce.
            from_datetime: Inclusive lower action_date bound.
            to_datetime: Inclusive upper action_date bound.
            search_text: Optional reference/description search text.
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        placeholder = self.db._get_placeholder()
        sql = f'\n            SELECT\n                action_date,\n                module,\n                action_type,\n                reference_id,\n                description\n            FROM audit_logs\n            WHERE company_id = {placeholder}\n              AND action_date >= {placeholder}\n              AND action_date <= {placeholder}\n        '
        params: List[Any] = [company_id, from_datetime, to_datetime]
        if search_text:
            sql += f'\n              AND (\n                  reference_id LIKE {placeholder}\n                  OR description LIKE {placeholder}\n              )\n            '
            like_value = f'%{search_text}%'
            params.extend([like_value, like_value])
        sql += ' ORDER BY action_date DESC'
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()

    def _populate_table(self, rows: Sequence[Sequence[Any]]) -> None:
        """Populate the audit table with fetched rows."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row_index, row in enumerate(rows):
            self.table.insertRow(row_index)
            for column_index in range(len(self.COLUMNS)):
                raw_value = row[column_index]
                if column_index == 0:
                    value = format_display_date(raw_value)
                else:
                    value = '' if raw_value is None else str(raw_value)
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_index, column_index, item)
            if row_index % 100 == 0:
                QCoreApplication.processEvents()
        self.table.setSortingEnabled(True)
        apply_adjustable_table_columns(self.table)
        self._restore_memory_table(self.table, "table")