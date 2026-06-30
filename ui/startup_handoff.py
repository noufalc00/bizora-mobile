"""Post-login startup handoff: fullscreen loading curtain, then dashboard reveal."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import QLabel, QMessageBox, QVBoxLayout, QWidget

from ui.brand_logo import create_brand_logo_box
from ui.loading_indicator import LoadingRunnerWidget
from ui.qt_pump import pump_ui_events
from ui import theme

# Delay before heavy startup work so the curtain paints on screen first.
_CURTAIN_PAINT_DELAY_MS = 200
_CURTAIN_PAINT_PUMPS = 16


class LoadingCurtainWidget(QWidget):
    """Full-screen loading window shown while the main dashboard initializes."""

    escape_pressed = Signal()

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setObjectName("loadingCurtain")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet(theme.loading_curtain_style())

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        logo_box, _brand_logo = create_brand_logo_box(
            520,
            240,
            label_object_name="startupBrandLogo",
            sidebar_variant=True,
        )
        layout.addWidget(logo_box, alignment=Qt.AlignmentFlag.AlignCenter)

        loading_label = QLabel("Loading Application...")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_font = QFont()
        loading_font.setPointSize(24)
        loading_font.setBold(True)
        loading_label.setFont(loading_font)
        loading_label.setStyleSheet(theme.loading_curtain_label_style(font_size=24))
        layout.addWidget(loading_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.runner = LoadingRunnerWidget(width=132, height=132)
        layout.addWidget(self.runner, alignment=Qt.AlignmentFlag.AlignCenter)

        escape_hint = QLabel("Press Esc to return to login if loading is stuck.")
        escape_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        escape_hint.setStyleSheet(theme.loading_curtain_label_style(font_size=13))
        layout.addWidget(escape_hint, alignment=Qt.AlignmentFlag.AlignCenter)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Allow Escape to cancel a stuck startup handoff."""
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


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
    """Show the loading curtain, build the dashboard underneath, then reveal it."""

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
        self._curtain: LoadingCurtainWidget | None = None
        self._runner: LoadingRunnerWidget | None = None
        self._db_worker: DatabasePrepWorker | None = None
        self._cancelled = False

        self._pump_timer = QTimer(self)
        self._pump_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._pump_timer.setInterval(16)
        self._pump_timer.timeout.connect(self._pump_and_keep_curtain_on_top)

    def start(self) -> None:
        """Paint the fullscreen curtain first, then build the dashboard underneath."""
        self._build_curtain()
        if self._curtain is None or self._runner is None:
            self._on_startup_failed(RuntimeError("Unable to open the loading screen."))
            return

        self._curtain.show()
        self._runner.show()
        self._raise_curtain()
        self._pump_timer.start()
        for _ in range(_CURTAIN_PAINT_PUMPS):
            pump_ui_events()

        if self.gateway is not None:
            freeze = getattr(self.gateway, "freeze_for_startup_handoff", None)
            if callable(freeze):
                freeze()

        QTimer.singleShot(
            _CURTAIN_PAINT_DELAY_MS,
            self._initialize_main_window,
        )

    def _build_curtain(self) -> None:
        """Create the fullscreen loading curtain on the primary display."""
        curtain = LoadingCurtainWidget()
        curtain.escape_pressed.connect(self.abort_handoff)
        curtain.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen
        )
        curtain.setWindowModality(Qt.WindowModality.ApplicationModal)
        curtain.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        curtain.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            curtain.setGeometry(screen.geometry())

        self._curtain = curtain
        self._runner = curtain.runner
        self.app.curtain = curtain

    def _raise_curtain(self) -> None:
        """Keep the loading curtain above every other window during handoff."""
        if self._curtain is None:
            return
        self._curtain.raise_()
        self._curtain.activateWindow()
        self._curtain.setFocus()

    def _pump_and_keep_curtain_on_top(self) -> None:
        """Pump UI events and re-assert curtain z-order on Windows."""
        pump_ui_events()
        if self._curtain is not None and self._curtain.isVisible():
            self._curtain.raise_()

    def _release_curtain(self) -> None:
        """Hide and destroy the loading curtain."""
        self._pump_timer.stop()
        if self._runner is not None:
            self._runner.stop()
            self._runner.hide()
            self._runner = None
        if self._curtain is not None:
            self._curtain.hide()
            self._curtain.close()
            self._curtain.deleteLater()
            self._curtain = None
        if hasattr(self.app, "curtain"):
            self.app.curtain = None

    def abort_handoff(self) -> None:
        """Cancel a stuck handoff and return the operator to the login screen."""
        if self._cancelled:
            return
        self._cancelled = True
        print("[STARTUP] Loading handoff cancelled by operator (Esc).")

        worker = self._db_worker
        self._db_worker = None
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.wait(2000)

        partial_main = self._main_window
        self._main_window = None
        if partial_main is not None:
            try:
                partial_main.hide()
                partial_main.setParent(None)
                partial_main.deleteLater()
            except RuntimeError:
                pass

        self._release_curtain()

        gateway = self.gateway
        if gateway is not None:
            thaw = getattr(gateway, "thaw_after_startup_handoff", None)
            if callable(thaw):
                thaw()
            gateway.show()
            gateway.restore_after_failed_handoff()

        if hasattr(self.app, "_startup_handoff"):
            self.app._startup_handoff = None
        if hasattr(self.app, "main_window"):
            self.app.main_window = None

    def _initialize_main_window(self) -> None:
        """Prepare the database off-thread, then build the main window."""
        if self._cancelled:
            return
        self._db_worker = DatabasePrepWorker(self.db_path)
        self._db_worker.finished_ok.connect(self._on_database_ready)
        self._db_worker.failed.connect(self._on_database_failed)
        self._db_worker.start()

    def _on_database_ready(self) -> None:
        if self._cancelled:
            return
        QTimer.singleShot(0, self._create_main_window)

    def _create_main_window(self) -> None:
        if self._cancelled:
            return
        try:
            from ui.main_window import MainWindow

            self._main_window = MainWindow(skip_gateway=True)
            self._main_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            self._main_window.hide()
            self._main_window.begin_dashboard_handoff(
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
        if self._cancelled:
            return
        if self._main_window is None:
            return
        self.app.main_window = self._main_window
        QTimer.singleShot(0, self._finish)

    def _finish(self) -> None:
        """Reveal the dashboard under the curtain, then retire the login shell."""
        if self._cancelled:
            return
        main = self._main_window
        gateway = self.gateway

        if main is not None:
            main.prepare_dashboard_handoff_reveal()
            try:
                main.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
            except RuntimeError:
                pass
            main.showMaximized()
            for _ in range(4):
                pump_ui_events()

        if gateway is not None:
            thaw = getattr(gateway, "thaw_after_startup_handoff", None)
            if callable(thaw):
                thaw()
            gateway.hide()
            pump_ui_events()

        self._release_curtain()
        pump_ui_events()

        if gateway is not None:
            self.gateway = None
            gateway.deleteLater()
            pump_ui_events()

        if main is not None:
            main.raise_()
            main.activateWindow()
            try:
                from utils.a4_preview_prewarm import schedule_a4_preview_engine_prewarm

                schedule_a4_preview_engine_prewarm()
            except Exception:
                pass

    def _on_database_failed(self, message: str) -> None:
        self._on_startup_failed(RuntimeError(message))

    def _on_startup_failed(self, error: BaseException) -> None:
        if self._cancelled:
            return
        self._release_curtain()
        traceback.print_exc()
        if self.gateway is not None:
            thaw = getattr(self.gateway, "thaw_after_startup_handoff", None)
            if callable(thaw):
                thaw()
            self.gateway.show()
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
    """Begin handoff immediately after successful login."""
    start_handoff(
        app,
        gateway,
        db_path,
        company_name,
        username,
        role,
    )
