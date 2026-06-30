"""
Net Sales Book — Net Cash Realization report for a selected date range.

Formula:
    net_sales = total_sales - credit_sales - sales_returns + debtor_receipts - discount_allowed
"""

from __future__ import annotations

import contextlib
import sqlite3
from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from bizora_core.dashboard_logic import _CREDIT_SALE_SQL
from config import active_company_manager
from db import DB_PATH
from ui import theme
from ui.book_report_common import (
    BOOK_REPORT_ACTION_BUTTON_HEIGHT,
    compact_date_style,
    compact_label_style,
    compact_primary_button_style,
    page_heading_style,
    report_filter_frame_style,
    report_footer_frame_style,
    report_page_shell_style,
)
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import (
    MemoryHostedDialog,
    UiMemoryMixin,
    focus_floating_window,
)


def _safe_float(value) -> float:
    """Convert database numeric values to float safely."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_currency(value: float) -> str:
    """Format a monetary value with rupee symbol and two decimal places."""
    return f"₹{value:,.2f}"


VIEW_NET_SALES_BUTTON_STYLE = None  # resolved at runtime via theme.net_sales_highlight_button_style()


def create_view_net_sales_button(*, action_height: int = 38) -> QPushButton:
    """Create a View Net Sales Book shortcut sized to match sibling action buttons."""
    button = QPushButton("View Net Sales Book")
    use_compact = action_height <= BOOK_REPORT_ACTION_BUTTON_HEIGHT + 2
    button.setStyleSheet(theme.net_sales_highlight_button_style(compact=use_compact))
    button.setMinimumWidth(158 if use_compact else 190)
    button.setFixedHeight(action_height)
    button.setToolTip("Open Net Sales & Cash Realization summary")
    return button


def _resolve_main_window_parent(caller: QWidget | None) -> QWidget | None:
    """Walk the widget hierarchy to find the application main window."""
    current = caller.window() if caller is not None else None
    while current is not None:
        if type(current).__name__ == "MainWindow":
            return current
        current = current.parentWidget()
    return caller.window() if caller is not None else None


def _net_sales_content_from_host(host: QWidget | None) -> "NetSalesBook | None":
    """Return the NetSalesBook page hosted inside a MemoryHostedDialog shell."""
    if host is None:
        return None
    if isinstance(host, NetSalesBook):
        return host
    layout = host.layout()
    if layout is not None and layout.count() > 0:
        content = layout.itemAt(0).widget()
        if isinstance(content, NetSalesBook):
            return content
    return None


def _track_net_sales_window(caller: QWidget | None, dialog: QWidget) -> None:
    """Clear the caller's cached popup reference when the dialog is destroyed."""
    if caller is None:
        return

    def _clear_reference() -> None:
        if getattr(caller, "_net_sales_window", None) is dialog:
            caller._net_sales_window = None

    dialog.destroyed.connect(_clear_reference)


def open_net_sales_book_window(parent, db_path=None, existing_window=None):
    """
    Open or raise the Net Sales Book popup with today's date range.

    Args:
        parent: Calling widget used to resolve the main window parent.
        db_path: SQLite database path for report queries.
        existing_window: Previously opened dialog shell, if any.

    Returns:
        The active MemoryHostedDialog window instance.
    """
    if existing_window is not None:
        try:
            focus_floating_window(existing_window)
            content = _net_sales_content_from_host(existing_window)
            if content is not None:
                content.refresh()
            return existing_window
        except RuntimeError:
            pass

    app_parent = _resolve_main_window_parent(parent)
    content = NetSalesBook(db_path or DB_PATH, parent=None)
    dialog = MemoryHostedDialog(
        content,
        title="Net Sales & Cash Realization",
        memory_key="net_sales_cash_realization",
        parent=app_parent,
        minimum_size=(920, 640),
    )
    dialog.resize(960, 680)
    content.refresh_theme()

    today = QDate.currentDate()
    content.start_date.setDate(today)
    content.end_date.setDate(today)
    content.calculate_net_sales()
    _track_net_sales_window(parent, dialog)
    dialog.show()
    return dialog


class NetSalesBook(UiMemoryMixin, QWidget):
    """Net Sales & Cash Realization summary for a custom date range."""

    def __init__(self, db_path=None, parent=None):
        """Initialize the report page with database path and optional parent window."""
        super().__init__(parent)
        self.setObjectName("NetSalesBook")
        self.db_path = db_path or DB_PATH
        self.company_id: Optional[int] = None
        self._filter_labels: list[QLabel] = []
        self._build_ui()
        self._apply_theme_styles()
        self.refresh()

    def _build_ui(self) -> None:
        """Build header, date filters, summary cards, and net result label."""
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        self.header_label = QLabel("Net Sales & Cash Realization")
        root.addWidget(self.header_label)

        self.filter_frame = QFrame()
        self.filter_frame.setObjectName("filterFrame")
        filter_row = QHBoxLayout(self.filter_frame)
        filter_row.setContentsMargins(10, 8, 10, 8)
        filter_row.setSpacing(10)

        today = QDate.currentDate()

        self.start_date = QDateEdit()
        self.start_date.setDate(today)
        prepare_report_date_edit(self.start_date, style_sheet=compact_date_style())
        self.end_date = QDateEdit()
        self.end_date.setDate(today)
        prepare_report_date_edit(self.end_date, style_sheet=compact_date_style())

        self.calculate_btn = QPushButton("Calculate")
        self.calculate_btn.setMinimumWidth(130)
        calc_font = QFont(self.calculate_btn.font())
        calc_font.setBold(True)
        self.calculate_btn.setFont(calc_font)
        self.calculate_btn.clicked.connect(self.calculate_net_sales)

        for label_text, widget in (
            ("Start Date", self.start_date),
            ("End Date", self.end_date),
        ):
            lbl = QLabel(label_text)
            self._filter_labels.append(lbl)
            filter_row.addWidget(lbl)
            filter_row.addWidget(widget)

        filter_row.addStretch(1)
        filter_row.addWidget(self.calculate_btn)
        root.addWidget(self.filter_frame)

        self.cards_frame = QFrame()
        self.cards_frame.setObjectName("summaryCardsFrame")
        cards_row = QHBoxLayout(self.cards_frame)
        cards_row.setContentsMargins(10, 10, 10, 10)
        cards_row.setSpacing(12)

        self.total_sales_card, self.total_sales_value = self._create_summary_card(
            "Total Sales", theme.semantic_positive_hex()
        )
        self.credit_sales_card, self.credit_sales_value = self._create_summary_card(
            "Credit Sales (Minus)", theme.semantic_negative_hex()
        )
        self.sales_returns_card, self.sales_returns_value = self._create_summary_card(
            "Sales Returns (Minus)", theme.semantic_warning_hex()
        )
        self.debtor_receipts_card, self.debtor_receipts_value = self._create_summary_card(
            "Debtor Receipts (Plus)", theme._theme_colors()["button_primary"]
        )
        self.discount_allowed_card, self.discount_allowed_value = self._create_summary_card(
            "Discount Allowed (Minus)", theme._theme_colors()["focus_border"]
        )

        summary_cards = (
            self.total_sales_card,
            self.credit_sales_card,
            self.sales_returns_card,
            self.debtor_receipts_card,
            self.discount_allowed_card,
        )
        for card in summary_cards:
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setMinimumHeight(92)
            cards_row.addWidget(card, 1)
        root.addWidget(self.cards_frame)

        self.footer_frame = QFrame()
        self.footer_frame.setObjectName("footerFrame")
        footer_layout = QVBoxLayout(self.footer_frame)
        footer_layout.setContentsMargins(12, 10, 12, 10)

        self.net_result_label = QLabel("NET REALIZED SALES: ₹0.00")
        net_font = QFont()
        net_font.setPointSize(20)
        net_font.setBold(True)
        self.net_result_label.setFont(net_font)
        self.net_result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_layout.addWidget(self.net_result_label)
        root.addWidget(self.footer_frame)

    def _style_date_calendar(self, date_edit: QDateEdit) -> None:
        """Apply shared calendar popup styling for light and dark themes."""
        calendar = date_edit.calendarWidget()
        if calendar is None:
            return
        calendar.setStyleSheet(theme.entry_calendar_style())
        theme.apply_calendar_day_formats(calendar)
        prev_btn = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        if prev_btn:
            prev_btn.setArrowType(Qt.ArrowType.NoArrow)
            prev_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            prev_btn.setText("<")
            prev_btn.setFixedSize(24, 24)
        next_btn = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        if next_btn:
            next_btn.setArrowType(Qt.ArrowType.NoArrow)
            next_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            next_btn.setText(">")
            next_btn.setFixedSize(24, 24)

    def _apply_theme_styles(self) -> None:
        """Apply current light/dark theme tokens to all report widgets."""
        self.setStyleSheet(report_page_shell_style(self.objectName()))
        self.header_label.setStyleSheet(page_heading_style(22))
        self.filter_frame.setStyleSheet(report_filter_frame_style())
        self.cards_frame.setStyleSheet(report_filter_frame_style())
        self.footer_frame.setStyleSheet(report_footer_frame_style())
        prepare_report_date_edit(self.start_date, style_sheet=compact_date_style())
        prepare_report_date_edit(self.end_date, style_sheet=compact_date_style())
        self.calculate_btn.setStyleSheet(compact_primary_button_style())
        for label in self._filter_labels:
            label.setStyleSheet(compact_label_style())
        self._style_date_calendar(self.start_date)
        self._style_date_calendar(self.end_date)
        card_accents = (
            (self.total_sales_card, theme.semantic_positive_hex()),
            (self.credit_sales_card, theme.semantic_negative_hex()),
            (self.sales_returns_card, theme.semantic_warning_hex()),
            (self.debtor_receipts_card, theme._theme_colors()["button_primary"]),
            (self.discount_allowed_card, theme._theme_colors()["focus_border"]),
        )
        for card, accent in card_accents:
            card.setStyleSheet(theme.metric_card_style(accent_hex=accent))
        self.net_result_label.setStyleSheet(theme.net_sales_result_chip_style(positive=True))

    def _create_summary_card(self, title: str, accent_color: str) -> tuple[QFrame, QLabel]:
        """Create a theme-aware summary card with title and value labels."""
        frame = QFrame()
        frame.setMinimumWidth(130)
        frame.setStyleSheet(theme.metric_card_style(accent_hex=accent_color))
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        colors = theme._theme_colors()
        label_style = (
            f"color: {colors['input_text']}; font-weight: bold; background: transparent; border: none;"
        )

        title_label = QLabel(title)
        title_label.setStyleSheet(f"{label_style} font-size: 13px;")

        value_label = QLabel("₹0.00")
        value_font = QFont()
        value_font.setPointSize(18)
        value_font.setBold(True)
        value_label.setFont(value_font)
        value_label.setStyleSheet(f"{label_style} font-size: 18px;")

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return frame, value_label

    def refresh(self) -> None:
        """Resolve active company and recalculate totals for the current filters."""
        company = active_company_manager.get_active_company()
        self.company_id = company.get("id") if company else None
        if not self.company_id:
            self._reset_totals()
            return
        self.calculate_net_sales()

    def _reset_totals(self) -> None:
        """Clear all summary labels to zero."""
        self.total_sales_value.setText("₹0.00")
        self.credit_sales_value.setText("₹0.00")
        self.sales_returns_value.setText("₹0.00")
        self.debtor_receipts_value.setText("₹0.00")
        self.discount_allowed_value.setText("₹0.00")
        self.net_result_label.setText("NET REALIZED SALES: ₹0.00")

    def _fetch_scalar(self, cursor: sqlite3.Cursor, query: str, params: tuple) -> float:
        """Execute a scalar SUM query and return the numeric result."""
        cursor.execute(query, params)
        row = cursor.fetchone()
        return _safe_float(row[0] if row else 0)

    def calculate_net_sales(self) -> None:
        """
        Compute net cash realization for the selected date range.

        Discount Allowed is sourced from cash/bank receipt voucher headers
        (`total_discount`) and line items (`discount`) recorded during
        debtor collection.
        """
        if not self.company_id:
            company = active_company_manager.get_active_company()
            self.company_id = company.get("id") if company else None
        if not self.company_id:
            QMessageBox.warning(
                self,
                "Net Sales Book",
                "Please open a company first.",
            )
            self._reset_totals()
            return

        start_date = qdate_to_db(self.start_date.date())
        end_date = qdate_to_db(self.end_date.date())
        if self.start_date.date() > self.end_date.date():
            QMessageBox.warning(
                self,
                "Net Sales Book",
                "Start Date cannot be after End Date.",
            )
            return

        company_id = self.company_id

        total_sales_sql = """
            SELECT COALESCE(SUM(grand_total), 0)
            FROM sales
            WHERE company_id = ?
              AND invoice_date BETWEEN ? AND ?
              AND COALESCE(status, 'Active') <> 'Voided'
        """
        credit_sales_sql = f"""
            SELECT COALESCE(SUM(grand_total), 0)
            FROM sales
            WHERE company_id = ?
              AND {_CREDIT_SALE_SQL}
              AND invoice_date BETWEEN ? AND ?
              AND COALESCE(status, 'Active') <> 'Voided'
        """
        sales_returns_sql = """
            SELECT COALESCE(SUM(grand_total), 0)
            FROM sales_returns
            WHERE company_id = ?
              AND return_date BETWEEN ? AND ?
              AND COALESCE(status, 'Active') <> 'Voided'
        """
        debtor_receipts_sql = """
            SELECT COALESCE(SUM(receipt_total), 0)
            FROM (
                SELECT CASE
                    WHEN COALESCE(cr.total_amount, 0) > 0 THEN cr.total_amount
                    ELSE cr.amount
                END AS receipt_total
                FROM cash_receipts cr
                INNER JOIN ledger_accounts la
                    ON cr.received_from_account_id = la.id
                WHERE cr.company_id = ?
                  AND la.group_name = 'Sundry Debtors'
                  AND cr.voucher_date BETWEEN ? AND ?
                UNION ALL
                SELECT CASE
                    WHEN COALESCE(br.total_amount, 0) > 0 THEN br.total_amount
                    ELSE br.amount
                END AS receipt_total
                FROM bank_receipts br
                INNER JOIN ledger_accounts la
                    ON br.received_from_account_id = la.id
                WHERE br.company_id = ?
                  AND la.group_name = 'Sundry Debtors'
                  AND br.voucher_date BETWEEN ? AND ?
            ) debtor_receipt_rows
        """
        discount_allowed_sql = """
            SELECT COALESCE(SUM(discount_amount), 0)
            FROM (
                SELECT COALESCE(cri.discount, 0) AS discount_amount
                FROM cash_receipt_items cri
                INNER JOIN cash_receipts cr ON cri.receipt_id = cr.id
                WHERE cr.company_id = ?
                  AND cr.voucher_date BETWEEN ? AND ?
                UNION ALL
                SELECT COALESCE(bri.discount, 0) AS discount_amount
                FROM bank_receipt_items bri
                INNER JOIN bank_receipts br ON bri.receipt_id = br.id
                WHERE br.company_id = ?
                  AND br.voucher_date BETWEEN ? AND ?
            ) discount_rows
        """

        try:
            with contextlib.closing(sqlite3.connect(self.db_path, timeout=30.0)) as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                cursor = conn.cursor()

                total_sales = self._fetch_scalar(
                    cursor,
                    total_sales_sql,
                    (company_id, start_date, end_date),
                )
                credit_sales = self._fetch_scalar(
                    cursor,
                    credit_sales_sql,
                    (company_id, start_date, end_date),
                )
                sales_returns = self._fetch_scalar(
                    cursor,
                    sales_returns_sql,
                    (company_id, start_date, end_date),
                )
                debtor_receipts = self._fetch_scalar(
                    cursor,
                    debtor_receipts_sql,
                    (
                        company_id,
                        start_date,
                        end_date,
                        company_id,
                        start_date,
                        end_date,
                    ),
                )
                discount_allowed = self._fetch_scalar(
                    cursor,
                    discount_allowed_sql,
                    (
                        company_id,
                        start_date,
                        end_date,
                        company_id,
                        start_date,
                        end_date,
                    ),
                )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Net Sales Book",
                f"Could not calculate net sales: {exc}",
            )
            return

        net_sales = (
            total_sales - credit_sales - sales_returns + debtor_receipts - discount_allowed
        )

        self.total_sales_value.setText(_format_currency(total_sales))
        self.credit_sales_value.setText(_format_currency(credit_sales))
        self.sales_returns_value.setText(_format_currency(sales_returns))
        self.debtor_receipts_value.setText(_format_currency(debtor_receipts))
        self.discount_allowed_value.setText(_format_currency(discount_allowed))

        result_positive = net_sales >= 0
        self.net_result_label.setText(
            f"NET REALIZED SALES: {_format_currency(net_sales)}"
        )
        self.net_result_label.setStyleSheet(
            theme.net_sales_result_chip_style(positive=result_positive)
        )

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self._apply_theme_styles()
        if self.company_id:
            self.calculate_net_sales()