"""
Guard voucher date inputs against the active company's working financial year.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit, QMessageBox, QWidget
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display

from utils.financial_year import (
    get_financial_year_qdate_range,
    get_working_financial_year_label,
    is_qdate_in_financial_year,
)


def _resolve_parent_widget(date_edit: QDateEdit, parent: Optional[QWidget]) -> Optional[QWidget]:
    """Pick the best parent widget for warning dialogs."""
    if parent is not None:
        return parent
    return date_edit.window()


def _clamp_to_financial_year(
    qdate: QDate,
    financial_year_label: str,
) -> QDate:
    """Clamp a date to the nearest boundary inside the working FY."""
    start_date, end_date = get_financial_year_qdate_range(financial_year_label)
    if qdate < start_date:
        return start_date
    if qdate > end_date:
        return end_date
    return qdate


def apply_financial_year_guard_to_date_edit(
    date_edit: QDateEdit,
    parent: Optional[QWidget] = None,
) -> None:
    """Restrict a date field to the active company's working financial year."""
    if getattr(date_edit, "_financial_year_guard_applied", False):
        return

    date_edit._financial_year_guard_applied = True
    date_edit._financial_year_guard_resetting = False

    def refresh_bounds() -> None:
        """Apply min/max bounds from the active working financial year."""
        financial_year_label = get_working_financial_year_label()
        if not financial_year_label:
            date_edit.setMinimumDate(QDate(1900, 1, 1))
            date_edit.setMaximumDate(QDate(2999, 12, 31))
            return

        start_date, end_date = get_financial_year_qdate_range(financial_year_label)
        date_edit.setMinimumDate(start_date)
        date_edit.setMaximumDate(end_date)

        current_date = date_edit.date()
        if not is_qdate_in_financial_year(current_date, financial_year_label):
            date_edit.blockSignals(True)
            date_edit.setDate(_clamp_to_financial_year(current_date, financial_year_label))
            date_edit.blockSignals(False)

    def on_date_changed(new_date: QDate) -> None:
        """Warn and reset when a date falls outside the working financial year."""
        if date_edit._financial_year_guard_resetting:
            return

        financial_year_label = get_working_financial_year_label()
        if not financial_year_label:
            return

        if is_qdate_in_financial_year(new_date, financial_year_label):
            return

        start_date, end_date = get_financial_year_qdate_range(financial_year_label)
        corrected_date = _clamp_to_financial_year(new_date, financial_year_label)

        date_edit._financial_year_guard_resetting = True
        date_edit.blockSignals(True)
        date_edit.setDate(corrected_date)
        date_edit.blockSignals(False)
        date_edit._financial_year_guard_resetting = False

        dialog_parent = _resolve_parent_widget(date_edit, parent)
        QMessageBox.warning(
            dialog_parent,
            "Financial Year Restriction",
            (
                f"Date must fall within the working financial year {financial_year_label} "
                f"({qdate_to_display(start_date)} to {qdate_to_display(end_date)})."
            ),
        )

    refresh_bounds()
    date_edit.dateChanged.connect(on_date_changed)
    date_edit._refresh_financial_year_bounds = refresh_bounds


def apply_financial_year_guard_to_named_dates(widget: QWidget, *date_attr_names: str) -> None:
    """Apply the working-FY guard to named QDateEdit attributes on a voucher widget."""
    for attr_name in date_attr_names:
        date_edit = getattr(widget, attr_name, None)
        if isinstance(date_edit, QDateEdit):
            apply_financial_year_guard_to_date_edit(date_edit, widget)