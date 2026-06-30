"""
PySide6 view for running database diagnostics.

This module provides a small standalone widget that can be embedded in Admin,
Settings, or any page that has access to the application database instance.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import active_company_manager, resolve_active_company_id
from db import Database
from bizora_core.diagnostic_engine import DiagnosticEngine
from ui import theme
from ui.book_report_common import page_background_style, page_heading_style
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin


class DiagnosticWorker(QObject):
    """Run diagnostics on a worker-owned database connection."""

    results_ready = Signal(list)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type: Optional[str], db_path: Optional[str], company_id: int):
        """
        Initialize the worker.

        Args:
            db_type: Database backend type from the parent Database instance.
            db_path: SQLite database path from the parent Database instance.
            company_id: Tenant company identifier to scan.
        """
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id

    def run(self) -> None:
        """Execute diagnostics and emit structured result rows."""
        worker_db = None
        try:
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            results = DiagnosticEngine(worker_db).run_full_diagnostics(self.company_id)
            self.results_ready.emit(results)
        except Exception as exc:
            self.error.emit(f"Diagnostic UI Error: diagnostics failed: {exc}")
        finally:
            if worker_db is not None:
                worker_db.force_disconnect()
            self.finished.emit()


class DiagnosticView(UiMemoryMixin, QWidget):
    """Simple UI for launching and reading the system health report."""

    def __init__(
        self,
        db: Optional[Database] = None,
        company_id: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        """
        Initialize the diagnostic view.

        Args:
            db: Application Database instance. A default instance is created if omitted.
            company_id: Optional explicit company id. If omitted, active company state is used.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.db = db or Database()
        self.company_id = int(company_id) if company_id else resolve_active_company_id(self.db)
        self._diagnostic_thread: Optional[QThread] = None
        self._diagnostic_worker: Optional[DiagnosticWorker] = None
        self._is_scanning = False
        self._last_results: Optional[List[Dict[str, Any]]] = None

        self.setObjectName("DiagnosticView")
        self._build_ui()
        self.refresh_theme()
        self._init_ui_memory(restore_geometry=False, save_geometry=False)

    def _build_ui(self) -> None:
        """Build the diagnostics page layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self.title_label = QLabel("Database Health Diagnostics")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(
            "Scan historical ledger fractures, trial balance drift, and orphaned postings."
        )
        layout.addWidget(self.subtitle_label)

        self.run_button = QPushButton("Run System Diagnostics")
        self.run_button.setMinimumHeight(54)
        self.run_button.setCursor(Qt.PointingHandCursor)
        self.run_button.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.run_button.clicked.connect(self.run_diagnostics)
        layout.addWidget(self.run_button)

        self.report_area = QTextEdit()
        self.report_area.setReadOnly(True)
        self.report_area.setAcceptRichText(True)
        layout.addWidget(self.report_area, 1)

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(page_background_style())
        self.title_label.setStyleSheet(page_heading_style(24))
        colors = theme._theme_colors()
        self.subtitle_label.setStyleSheet(
            f"font-size: 13px; color: {colors['label_text']}; background: transparent; border: none;"
        )
        self.run_button.setStyleSheet(self._button_style())
        self.report_area.setStyleSheet(self._report_style())
        if self._is_scanning:
            self.report_area.setHtml(self._scanning_html())
        elif self._last_results is not None:
            self._display_results(self._last_results)
        else:
            self.report_area.setHtml(self._intro_html())

    def run_diagnostics(self) -> None:
        """Start diagnostics in a background QThread."""
        if self._is_scanning:
            return

        self.report_area.clear()
        current_company_id = active_company_manager.get_active_company_id()
        if not current_company_id:
            self.report_area.setHtml(
                self._message_html(
                    "ERROR",
                    "No active company is selected. Open a company before running diagnostics.",
                )
            )
            return

        self.company_id = int(current_company_id)
        thread = QThread(self)
        worker = DiagnosticWorker(
            getattr(self.db, "db_type", None),
            getattr(self.db, "db_path", None),
            self.company_id,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.results_ready.connect(self._display_results)
        worker.error.connect(self._display_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._worker_finished)

        self._diagnostic_thread = thread
        self._diagnostic_worker = worker
        self._set_scanning_state(True)
        thread.start()

    def _set_scanning_state(self, is_scanning: bool) -> None:
        """Toggle the UI while diagnostics are running."""
        self._is_scanning = is_scanning
        self.run_button.setEnabled(not is_scanning)
        self.run_button.setText("Scanning database..." if is_scanning else "Run System Diagnostics")
        if is_scanning:
            self.report_area.setHtml(self._scanning_html())

    def _worker_finished(self) -> None:
        """Release worker references after the background scan finishes."""
        self._diagnostic_thread = None
        self._diagnostic_worker = None
        self._set_scanning_state(False)

    def _display_error(self, message: str) -> None:
        """Display an unexpected worker error."""
        self._last_results = None
        self.report_area.setHtml(self._message_html("ERROR", message))

    def _display_results(self, results: List[Dict[str, Any]]) -> None:
        """Render diagnostic results as a colored HTML health report."""
        self._last_results = list(results or [])
        if self._is_healthy(results):
            colors = theme._theme_colors()
            self.report_area.setHtml(
                f"""
                <div style="font-size:30px; font-weight:800; color:{colors['button_success']}; margin-bottom:12px;">
                    SYSTEM HEALTHY: 100%
                </div>
                <p style="font-size:15px; color:{colors['label_text']};">
                    No trial balance, negative cash, or orphaned ledger fractures were found.
                </p>
                """
            )
            return

        colors = theme._theme_colors()
        blocks = [
            f"""
            <div style="font-size:24px; font-weight:800; color:{colors['button_danger']}; margin-bottom:10px;">
                SYSTEM HEALTH REPORT
            </div>
            """
        ]
        for result in results or []:
            severity = str(result.get("severity") or "ERROR").upper()
            color = colors["button_danger"] if severity == "ERROR" else colors["button_warning"]
            check = html.escape(str(result.get("check") or "Diagnostic Check"))
            message = html.escape(str(result.get("message") or "No message supplied."))
            context_html = self._context_html(result.get("context") or {})
            blocks.append(
                f"""
                <div style="border:1px solid {color}; border-radius:8px; padding:12px; margin:10px 0;">
                    <div style="color:{color}; font-size:16px; font-weight:800;">{severity}: {check}</div>
                    <div style="color:{colors['input_text']}; margin-top:6px;">{message}</div>
                    {context_html}
                </div>
                """
            )
        self.report_area.setHtml("".join(blocks))

    def _context_html(self, context: Dict[str, Any]) -> str:
        """Render diagnostic context key/value pairs."""
        if not context:
            return ""
        colors = theme._theme_colors()
        rows = []
        for key, value in context.items():
            label = html.escape(str(key).replace("_", " ").title())
            text = html.escape(str(value))
            rows.append(f"<li><b>{label}:</b> {text}</li>")
        return (
            f"<ul style='color:{colors['muted_text']}; margin-top:8px;'>{''.join(rows)}</ul>"
        )

    @staticmethod
    def _is_healthy(results: List[Dict[str, Any]]) -> bool:
        """Return True when the engine returned only the healthy result."""
        return (
            len(results or []) == 1
            and str(results[0].get("severity") or "").upper() == "HEALTHY"
            and str(results[0].get("message") or "") == DiagnosticEngine.HEALTHY_MESSAGE
        )

    def _intro_html(self) -> str:
        """Return the initial empty report text."""
        colors = theme._theme_colors()
        return f"""
        <div style="color:{colors['heading_text']}; font-size:18px; font-weight:700;">Health Report</div>
        <p style="color:{colors['muted_text']};">Click Run System Diagnostics to scan this company database.</p>
        """

    def _scanning_html(self) -> str:
        """Return the in-progress scan message."""
        colors = theme._theme_colors()
        return f"""
        <div style="color:{colors['button_primary']}; font-size:20px; font-weight:700;">
            Scanning database...
        </div>
        <p style="color:{colors['label_text']};">Please wait while tenant ledger diagnostics run.</p>
        """

    def _message_html(self, severity: str, message: str) -> str:
        """Return a one-message HTML report."""
        colors = theme._theme_colors()
        color = colors["button_danger"] if severity.upper() == "ERROR" else colors["button_warning"]
        return (
            f"<div style='color:{color}; font-size:18px; font-weight:800;'>"
            f"{html.escape(severity.upper())}</div>"
            f"<p style='color:{colors['input_text']};'>{html.escape(message)}</p>"
        )

    def _button_style(self) -> str:
        """Return stylesheet for the prominent diagnostics button."""
        colors = theme._theme_colors()
        return f"""
        QPushButton {{
            background-color: {colors['button_primary']};
            color: #FFFFFF;
            border: none;
            border-radius: 8px;
            padding: 12px 18px;
        }}
        QPushButton:hover {{
            background-color: {colors['focus_border']};
        }}
        QPushButton:pressed {{
            background-color: {colors['focus_border']};
        }}
        QPushButton:disabled {{
            background-color: {colors['border']};
            color: {colors['muted_text']};
        }}
        """

    def _report_style(self) -> str:
        """Return stylesheet for the scrollable health report area."""
        colors = theme._theme_colors()
        return f"""
        QTextEdit {{
            background-color: {colors['panel_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            padding: 12px;
            font-size: 13px;
        }}
        """