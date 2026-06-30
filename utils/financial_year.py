"""
Indian financial year helpers (April to March).
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional, Tuple

from PySide6.QtCore import QDate


def get_current_financial_year_label(reference: Optional[date] = None) -> str:
    """Return the Indian FY label (e.g. 2025-26) for the given calendar date."""
    if reference is None:
        reference = date.today()

    start_year = reference.year if reference.month >= 4 else reference.year - 1
    end_year = start_year + 1
    return f"{start_year}-{str(end_year)[-2:]}"


def get_financial_year_options(years_before_current: int = 3) -> List[str]:
    """Return FY labels from N years before the current FY through the current FY."""
    current_label = get_current_financial_year_label()
    current_start_year = int(current_label.split("-")[0])
    options: List[str] = []

    for offset in range(years_before_current, -1, -1):
        start_year = current_start_year - offset
        end_year = start_year + 1
        options.append(f"{start_year}-{str(end_year)[-2:]}")

    return options


def get_financial_year_date_range(financial_year_label: str) -> Tuple[date, date]:
    """Return inclusive (start, end) calendar dates for an Indian FY label."""
    start_year = int(financial_year_label.split("-")[0])
    end_year = start_year + 1
    return date(start_year, 4, 1), date(end_year, 3, 31)


def get_financial_year_qdate_range(financial_year_label: str) -> Tuple[QDate, QDate]:
    """Return inclusive QDate range for an Indian FY label."""
    start_date, end_date = get_financial_year_date_range(financial_year_label)
    return (
        QDate(start_date.year, start_date.month, start_date.day),
        QDate(end_date.year, end_date.month, end_date.day),
    )


def get_working_financial_year_label() -> Optional[str]:
    """Return the active company's working financial year, if available."""
    try:
        from config import active_company_manager

        company = active_company_manager.get_active_company()
        if company:
            financial_year = (company.get("financial_year") or "").strip()
            if financial_year:
                return financial_year
            if active_company_manager.has_active_company():
                return get_current_financial_year_label()
    except Exception:
        pass
    return None


def is_qdate_in_financial_year(qdate: QDate, financial_year_label: str) -> bool:
    """Return True when the QDate falls inside the given FY."""
    start_date, end_date = get_financial_year_qdate_range(financial_year_label)
    return start_date <= qdate <= end_date
