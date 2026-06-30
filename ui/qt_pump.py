"""Small helper to keep Qt animations alive during heavy synchronous work."""

from __future__ import annotations

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication


def pump_ui_events(max_milliseconds: int = 0) -> None:
    """Process pending UI events so timers and paints can run."""
    app = QApplication.instance()
    if app is not None:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, max_milliseconds)