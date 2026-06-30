"""
Central date display and storage helpers for Faizan Pro Accounting.

UI fields use dd-MM-yyyy. Database values stay yyyy-MM-dd.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit, QSizePolicy

from config import (
    DB_DATE_FORMAT,
    PYTHON_DB_DATE_FORMAT,
    PYTHON_DISPLAY_DATE_FORMAT,
    UI_DISPLAY_DATE_FORMAT,
)

DATE_FIELD_KEYS = frozenset(
    {
        "voucher_date",
        "invoice_date",
        "purchase_date",
        "return_date",
        "cheque_date",
        "received_issued_date",
        "related_bill_date",
        "note_date",
        "bill_date",
        "load_date",
        "movement_date",
        "adjustment_date",
        "due_date",
        "activity_date",
        "action_date",
        "date",
        "created_at",
    }
)


# Minimum width for report/book filter bars showing dd-MM-yyyy plus calendar button.
REPORT_DATE_FIELD_WIDTH = 118


def configure_qdate_edit(date_edit: QDateEdit, *, calendar_popup: bool = True) -> None:
    """Apply the standard display format and optional financial-year guard."""
    if calendar_popup:
        date_edit.setCalendarPopup(True)
    date_edit.setDisplayFormat(UI_DISPLAY_DATE_FORMAT)
    try:
        from ui.financial_year_guard import apply_financial_year_guard_to_date_edit

        apply_financial_year_guard_to_date_edit(date_edit)
    except Exception:
        pass


def prepare_report_date_edit(
    date_edit: QDateEdit,
    *,
    style_sheet: str | None = None,
    calendar_popup: bool = True,
    width: int | None = None,
) -> None:
    """Apply standard report top-bar date sizing so dd-MM-yyyy is never clipped."""
    configure_qdate_edit(date_edit, calendar_popup=calendar_popup)
    field_width = int(width if width is not None else REPORT_DATE_FIELD_WIDTH)
    date_edit.setFixedWidth(field_width)
    date_edit.setMinimumWidth(field_width)
    date_edit.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    if style_sheet:
        date_edit.setStyleSheet(style_sheet)
    try:
        from ui import theme

        theme.apply_date_edit_calendar_theme(date_edit)
    except Exception:
        pass


def qdate_to_db(qdate: QDate) -> str:
    """Convert a QDate to the database storage format."""
    return qdate.toString(DB_DATE_FORMAT)


def qdate_to_display(qdate: QDate) -> str:
    """Convert a QDate to the user-facing display format."""
    if not qdate.isValid():
        return ""
    return qdate.toString(UI_DISPLAY_DATE_FORMAT)


def db_to_qdate(value: Any) -> QDate:
    """Parse a stored database/ISO date string into QDate."""
    if value is None:
        return QDate()
    text = str(value).strip()
    if not text:
        return QDate()
    parsed = QDate.fromString(text[:10], DB_DATE_FORMAT)
    if parsed.isValid():
        return parsed
    return QDate.fromString(text[:10], "yyyy-MM-dd")


def is_date_field_key(key: str) -> bool:
    """Return True when a report/data key should be rendered as a date."""
    if not key:
        return False
    if key in DATE_FIELD_KEYS:
        return True
    return key.endswith("_date") or key.endswith("_at")


def format_display_date(value: Any) -> str:
    """Format database, Python, or Qt date values for on-screen display."""
    if value is None:
        return ""
    if isinstance(value, QDate):
        return qdate_to_display(value)
    if isinstance(value, datetime):
        return value.strftime(PYTHON_DISPLAY_DATE_FORMAT)
    if isinstance(value, date):
        return value.strftime(PYTHON_DISPLAY_DATE_FORMAT)

    text = str(value).strip()
    if not text:
        return ""

    for fmt in (
        PYTHON_DISPLAY_DATE_FORMAT,
        "%d-%m-%Y",
        "%d/%m/%Y",
        PYTHON_DB_DATE_FORMAT,
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            parsed = datetime.strptime(text[:19], fmt)
            return parsed.strftime(PYTHON_DISPLAY_DATE_FORMAT)
        except ValueError:
            continue

    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        try:
            parsed = datetime.strptime(text[:10], PYTHON_DB_DATE_FORMAT)
            return parsed.strftime(PYTHON_DISPLAY_DATE_FORMAT)
        except ValueError:
            pass

    return text[:10] if len(text) >= 10 else text


def parse_display_date(date_string: str) -> Optional[datetime]:
    """Parse a user-facing date string into datetime."""
    text = str(date_string or "").strip()
    if not text:
        return None
    for fmt in (PYTHON_DISPLAY_DATE_FORMAT, "%d-%m-%Y", "%d/%m/%Y", PYTHON_DB_DATE_FORMAT):
        try:
            return datetime.strptime(text[:10], fmt)
        except ValueError:
            continue
    return None
