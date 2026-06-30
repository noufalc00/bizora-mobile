"""
Pure-Python date display helpers (no Qt dependency).

Used by mobile/cloud services that must not import PySide6.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from config import PYTHON_DB_DATE_FORMAT, PYTHON_DISPLAY_DATE_FORMAT


def format_display_date(value: Any) -> str:
    """Format database, Python, or ISO date values as dd-MM-yyyy."""
    if value is None:
        return ""
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
