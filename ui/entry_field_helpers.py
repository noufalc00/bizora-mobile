"""
Shared entry-field helpers for voucher and payment screens.
"""
from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QLineEdit, QWidget


class ClickSelectAllFilter(QObject):
    """Select all editable text when the user clicks a field once."""

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if isinstance(obj, QLineEdit) and not obj.isReadOnly():
                QTimer.singleShot(0, obj.selectAll)
        return False


_CLICK_SELECT_FILTER: Optional[ClickSelectAllFilter] = None


def install_click_select_all(widget: QWidget) -> None:
    """Install one-click select-all behavior on a line edit or combo editor."""
    global _CLICK_SELECT_FILTER
    if _CLICK_SELECT_FILTER is None:
        _CLICK_SELECT_FILTER = ClickSelectAllFilter()

    if isinstance(widget, QComboBox):
        line_edit = widget.lineEdit()
        if line_edit is not None:
            install_click_select_all(line_edit)
        return

    if isinstance(widget, QLineEdit):
        widget.installEventFilter(_CLICK_SELECT_FILTER)


def install_click_select_all_many(widgets: Iterable[Optional[QWidget]]) -> None:
    """Install click-to-select-all on several widgets."""
    for widget in widgets:
        if widget is not None:
            install_click_select_all(widget)