"""Post-login startup handoff inside the single MainWindow shell (no extra windows)."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QTimer, QThread, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

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
    """Build the dashboard inside the existing MainWindow while login loading stays visible."""

    def __init__(
        self,
        app,
        main_window,
        db_path: str,
        company_name: str,
        username: str,
        role: str,
    ):
        super().__init__()
        self.app = app
        self.main_window = main_window
        self.gateway = getattr(main_window, "gateway", None)
        self.db_path = db_path
        self.company_name = company_name
        self.username = username
        self.role = role

        self._db_worker: DatabasePrepWorker | None = None

    def start(self) -> None:
        """Keep the embedded gateway visible while the dashboard builds off-screen."""
        pump_ui_events()
        QTimer.singleShot(
            _GATEWAY_OVERLAY_PAINT_DELAY_MS,
            self._initialize_dashboard,
        )

    def _stop_gateway_overlay(self) -> None:
        """Stop gateway handoff timers and loader animation."""
        if self.gateway is None:
            return
        handoff_timer = getattr(self.gateway, "_handoff_pump_timer", None)
        if handoff_timer is not None:
            handoff_timer.stop()
        loading_runner = getattr(self.gateway, "loading_runner", None)
        if loading_runner is not None:
            loading_runner.stop()
            loading_runner.hide()
        loading_label = getattr(self.gateway, "loading_label", None)
        if loading_label is not None:
            loading_label.hide()

    def _initialize_dashboard(self) -> None:
        """Prepare the database off-thread, then build the dashboard in-place."""
        self._db_worker = DatabasePrepWorker(self.db_path)
        self._db_worker.finished_ok.connect(self._on_database_ready)
        self._db_worker.failed.connect(self._on_database_failed)
        self._db_worker.start()

    def _on_database_ready(self) -> None:
        QTimer.singleShot(0, self._begin_dashboard_handoff)

    def _begin_dashboard_handoff(self) -> None:
        try:
            self.main_window.begin_dashboard_handoff(
                self.db_path,
                self.company_name,
                self.username,
                self.role,
                on_ready=self._on_dashboard_ready,
                on_failed=self._on_startup_failed,
                defer_page_switch=True,
            )
        except BaseException as error:
            self._on_startup_failed(error)

    def _on_dashboard_ready(self) -> None:
        self.app.main_window = self.main_window
        QTimer.singleShot(0, self._finish)

    def _finish(self) -> None:
        """Switch the same MainWindow to the dashboard without opening/closing windows."""
        self._stop_gateway_overlay()

        main_window = self.main_window
        if main_window is None:
            return

        main_window.complete_dashboard_handoff()
        pump_ui_events()

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


def start_handoff(app, main_window, db_path, company_name, username, role) -> None:
    """Entry point used after successful company login."""
    controller = StartupHandoffController(
        app,
        main_window,
        db_path,
        company_name,
        username,
        role,
    )
    app._startup_handoff = controller
    controller.start()


def schedule_handoff(app, main_window, db_path, company_name, username, role) -> None:
    """Begin in-window handoff immediately after the gateway login overlay is shown."""
    start_handoff(
        app,
        main_window,
        db_path,
        company_name,
        username,
        role,
    )
