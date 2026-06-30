"""Post-login startup handoff using the gateway loading overlay (no extra window)."""

from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from ui.qt_pump import pump_ui_events

# Brief yield so the gateway loading overlay paints before heavy startup work.
_GATEWAY_OVERLAY_PAINT_DELAY_MS = 120


class DatabasePrepWorker(QThread):
    """Prepare the company database off the UI thread."""

    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path

    def run(self) -> None:
        try:
            from db import Database

            database = Database(db_type="sqlite", db_path=self.db_path)
            if not database.initialize_database():
                raise RuntimeError(
                    f"Schema initialization failed for database: {database.db_path}"
                )
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class StartupHandoffController(QObject):
    """Keep the gateway loading overlay visible while the dashboard builds off-screen."""

    def __init__(
        self,
        app,
        gateway,
        db_path: str,
        company_name: str,
        username: str,
        role: str,
    ):
        super().__init__()
        self.app = app
        self.gateway = gateway
        self.db_path = db_path
        self.company_name = company_name
        self.username = username
        self.role = role

        self._main_window = None
        self._db_worker: DatabasePrepWorker | None = None

        self._pump_timer = QTimer(self)
        self._pump_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._pump_timer.setInterval(16)
        self._pump_timer.timeout.connect(self._pump_gateway_overlay)

    def start(self) -> None:
        """Begin dashboard startup without closing the gateway or opening another window."""
        if self.gateway is not None:
            self.gateway.raise_()
            self.gateway.activateWindow()
        pump_ui_events()

        self._pump_timer.start()

        QTimer.singleShot(
            _GATEWAY_OVERLAY_PAINT_DELAY_MS,
            self._initialize_main_window,
        )

    def _pump_gateway_overlay(self) -> None:
        """Keep the gateway loading animation responsive during startup."""
        pump_ui_events()
        if self.gateway is not None and self.gateway.isVisible():
            self.gateway.raise_()

    def _stop_gateway_overlay(self) -> None:
        """Stop gateway handoff timers and loader animation."""
        self._pump_timer.stop()
        if self.gateway is None:
            return
        handoff_timer = getattr(self.gateway, "_handoff_pump_timer", None)
        if handoff_timer is not None:
            handoff_timer.stop()
        loading_runner = getattr(self.gateway, "loading_runner", None)
        if loading_runner is not None:
            loading_runner.stop()

    def _initialize_main_window(self) -> None:
        """Prepare the database off-thread, then build the main window."""
        self._db_worker = DatabasePrepWorker(self.db_path)
        self._db_worker.finished_ok.connect(self._on_database_ready)
        self._db_worker.failed.connect(self._on_database_failed)
        self._db_worker.start()

    def _on_database_ready(self) -> None:
        QTimer.singleShot(0, self._create_main_window)

    def _create_main_window(self) -> None:
        try:
            from ui.main_window import MainWindow

            self._main_window = MainWindow(skip_gateway=True)
            self._main_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            self._main_window.begin_dashboard_handoff(
                self.db_path,
                self.company_name,
                self.username,
                self.role,
                on_ready=self._on_dashboard_ready,
                on_failed=self._on_startup_failed,
            )
        except BaseException as error:
            self._on_startup_failed(error)

    def _on_dashboard_ready(self) -> None:
        if self._main_window is None:
            return
        self.app.main_window = self._main_window
        QTimer.singleShot(0, self._finish)

    def _finish(self) -> None:
        """Reveal the main window, then retire the gateway in the same UI tick."""
        if self._main_window is not None:
            self._main_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
            self._main_window.showMaximized()
            self._main_window.raise_()
            self._main_window.activateWindow()
            pump_ui_events()

        self._stop_gateway_overlay()

        if self.gateway is not None:
            self.gateway.hide()
            self.gateway.close()

        if hasattr(self.app, "curtain"):
            self.app.curtain = None

    def _on_database_failed(self, message: str) -> None:
        self._on_startup_failed(RuntimeError(message))

    def _on_startup_failed(self, error: BaseException) -> None:
        self._stop_gateway_overlay()
        traceback.print_exc()
        if self.gateway is not None:
            self.gateway.restore_after_failed_handoff()
            QMessageBox.critical(
                self.gateway,
                "Startup Error",
                f"Unable to open the main dashboard:\n{error}",
            )


def start_handoff(app, gateway, db_path, company_name, username, role) -> None:
    """Entry point used after successful company login."""
    controller = StartupHandoffController(
        app,
        gateway,
        db_path,
        company_name,
        username,
        role,
    )
    app._startup_handoff = controller
    controller.start()


def schedule_handoff(app, gateway, db_path, company_name, username, role) -> None:
    """Begin handoff while the gateway loading overlay remains on screen."""
    start_handoff(
        app,
        gateway,
        db_path,
        company_name,
        username,
        role,
    )
