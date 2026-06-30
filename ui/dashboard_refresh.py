"""
Deferred dashboard refresh bus.

Voucher saves schedule a refresh after the current transaction commits so
dashboard metrics read the latest SQLite WAL state.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal


class DashboardRefreshBus(QObject):
    """Application-wide signal used to refresh live dashboard metrics."""

    refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._emit_refresh)

    def _emit_refresh(self) -> None:
        """Emit the refresh signal for all connected dashboard widgets."""
        try:
            self.refresh_requested.emit()
        except Exception as exc:
            print(f"[DASHBOARD] Refresh signal failed: {exc}")

    def request_refresh(self) -> None:
        """Coalesce rapid save events into one refresh after commit settles."""
        self._timer.start()


dashboard_refresh_bus = DashboardRefreshBus()


def request_dashboard_refresh() -> None:
    """Schedule a dashboard metrics refresh after the current save completes."""
    dashboard_refresh_bus.request_refresh()