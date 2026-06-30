"""Post-login startup handoff inside the single MainWindow shell (no extra windows)."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QVBoxLayout, QWidget

from ui.brand_logo import create_brand_logo_label
from ui.loading_indicator import LoadingRunnerWidget
from ui.qt_pump import pump_ui_events
from ui import theme

# Brief yield so the handoff overlay paints before heavy startup work.
_HANDOFF_OVERLAY_PAINT_DELAY_MS = 120


class StartupHandoffOverlay(QWidget):
    """Full-window in-process loading veil (child widget, not a separate window)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("startupHandoffOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.setStyleSheet(theme.loading_curtain_style())

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        self._brand_logo = create_brand_logo_label(520, 240, object_name="startupBrandLogo")
        layout.addWidget(self._brand_logo, alignment=Qt.AlignmentFlag.AlignCenter)

        loading_label = QLabel("Loading Application...")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_font = QFont()
        loading_font.setPointSize(24)
        loading_font.setBold(True)
        loading_label.setFont(loading_font)
        loading_label.setStyleSheet(theme.loading_curtain_label_style(font_size=24))
        layout.addWidget(loading_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self._runner = LoadingRunnerWidget(width=132, height=132)
        layout.addWidget(self._runner, alignment=Qt.AlignmentFlag.AlignCenter)

        self._pump_timer = QTimer(self)
        self._pump_timer.setInterval(16)
        self._pump_timer.timeout.connect(pump_ui_events)

    def start_animation(self) -> None:
        """Show the loader and keep the UI responsive during startup."""
        self._runner.start()
        self._pump_timer.start()

    def stop_animation(self) -> None:
        """Stop loader animation timers."""
        self._pump_timer.stop()
        self._runner.stop()


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
    """Build the dashboard inside the existing MainWindow while the overlay stays visible."""

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
        """Begin dashboard startup after the in-window overlay has painted."""
        pump_ui_events()
        QTimer.singleShot(_HANDOFF_OVERLAY_PAINT_DELAY_MS, self._initialize_dashboard)

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
        """Reveal the dashboard in the same MainWindow, then remove the overlay."""
        main_window = self.main_window
        if main_window is None:
            return
        main_window.complete_dashboard_handoff()
        pump_ui_events()

    def _on_database_failed(self, message: str) -> None:
        self._on_startup_failed(RuntimeError(message))

    def _on_startup_failed(self, error: BaseException) -> None:
        if self.main_window is not None:
            self.main_window.hide_startup_handoff_overlay()
        traceback.print_exc()
        if self.gateway is not None:
            self.gateway.restore_after_failed_handoff()
            QMessageBox.critical(
                self.main_window or self.gateway,
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
    """Begin in-window handoff immediately after the login overlay is shown."""
    start_handoff(
        app,
        main_window,
        db_path,
        company_name,
        username,
        role,
    )
