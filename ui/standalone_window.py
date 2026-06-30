"""
Standalone window shell for module pages.
Provides a QMainWindow wrapper with native title bar and window controls.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout

from ui.book_report_common import standalone_module_window_style
from ui.ui_memory import (
    UiMemoryMixin,
    apply_module_window_chrome,
    configure_non_modal_window,
    derive_window_memory_key,
    schedule_clamp_window_to_available_screen,
)


def _resolve_hub_window(widget: QWidget | None) -> QWidget | None:
    """Return the MainWindow hub that can present standalone module windows."""
    candidate = widget
    seen: set[int] = set()
    while candidate is not None:
        object_id = id(candidate)
        if object_id in seen:
            break
        seen.add(object_id)
        if hasattr(candidate, "_center_and_show_window") and hasattr(
            candidate, "dock_minimize_module_window"
        ):
            return candidate
        hub_ref = getattr(candidate, "_hub_window", None)
        if hub_ref is not None and hub_ref is not candidate and id(hub_ref) not in seen:
            if hasattr(hub_ref, "_center_and_show_window") and hasattr(
                hub_ref, "dock_minimize_module_window"
            ):
                return hub_ref
            candidate = hub_ref
            continue
        parent = candidate.parent() if hasattr(candidate, "parent") else None
        candidate = parent() if callable(parent) else parent
    return None


def _module_hub(module_window: QWidget | None) -> QWidget | None:
    """Return the hub that exposes internal taskbar dock helpers."""
    if module_window is None:
        return None
    stored = getattr(module_window, "_hub_window", None)
    resolved = _resolve_hub_window(stored) or _resolve_hub_window(module_window)
    if resolved is not None and hasattr(resolved, "dock_minimize_module_window"):
        return resolved
    if stored is not None and hasattr(stored, "dock_minimize_module_window"):
        return stored
    return None


def get_standalone_page_widget(window: QWidget | None) -> QWidget | None:
    """Return the inner page widget hosted inside a StandaloneModuleWindow."""
    if window is None:
        return None

    if not hasattr(window, "centralWidget"):
        return window if isinstance(window, QWidget) else None

    host = window.centralWidget()
    if host is None:
        return None

    layout = host.layout() if hasattr(host, "layout") else None
    if layout is not None and layout.count() > 0:
        page_widget = layout.itemAt(0).widget()
        if page_widget is not None:
            return page_widget

    return host


class StandaloneModuleWindow(UiMemoryMixin, QMainWindow):
    """QMainWindow shell for module pages with native title bar and window controls."""

    def __init__(
        self,
        widget: QWidget,
        title: str,
        parent: QWidget | None = None,
        memory_key: str | None = None,
    ) -> None:
        """
        Initialize standalone window.

        Args:
            widget: The page widget to display as central widget
            title: Window title
            parent: Main hub window reference (not used as Qt parent)
            memory_key: Optional QSettings geometry key slug
        """
        hub_window = _resolve_hub_window(parent) or parent
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle(title)
        self._hub_window = hub_window
        self._ui_memory_geometry_key = memory_key or derive_window_memory_key(title)

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(widget)

        self.setCentralWidget(central_widget)
        self.setMinimumSize(1000, 650)
        self.resize(1200, 700)

        configure_non_modal_window(self, hub_window)
        self._last_visible_window_state = Qt.WindowState.WindowNoState
        self.refresh_theme()
        self._init_ui_memory(restore_geometry=True, save_geometry=True)
        apply_module_window_chrome(self, hub_window)
        schedule_clamp_window_to_available_screen(self)

    def refresh_theme(self) -> None:
        """Re-apply shell styles and refresh the hosted page widget."""
        if getattr(self, "_refreshing_theme", False):
            return

        self._refreshing_theme = True
        try:
            self.setStyleSheet(standalone_module_window_style())
            central_widget = self.centralWidget()
            if central_widget is not None:
                central_widget.setStyleSheet("background: transparent;")

            page_widget = get_standalone_page_widget(self)
            if (
                page_widget is not None
                and page_widget is not self
                and hasattr(page_widget, "refresh_theme")
            ):
                page_widget.refresh_theme()
        finally:
            self._refreshing_theme = False

    def showEvent(self, event: QShowEvent) -> None:
        """Present the module window unless it is dock-minimized on the hub strip."""
        hub = _module_hub(self)
        if hub is not None:
            if hub.is_module_dock_minimized(self):
                event.ignore()
                self.hide()
                return
            try:
                hwnd = int(self.winId())
                if hwnd and hwnd in getattr(hub, "_dock_minimized_hwnds", set()):
                    event.ignore()
                    self.hide()
                    return
            except RuntimeError:
                pass
            coordinator = getattr(hub, "window_coordinator", None)
            if coordinator is not None and coordinator.is_window_in_dock(self):
                event.ignore()
                self.hide()
                return
        super().showEvent(event)
        hub = _module_hub(self)
        if hub is not None:
            from ui.ui_memory import force_bind_module_window_to_hub

            force_bind_module_window_to_hub(self, hub)

    def changeEvent(self, event) -> None:
        """Route OS minimize to the hub internal taskbar instead of a title-only ghost."""
        hub = _module_hub(self)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and hub is not None
            and not getattr(self, "_coordinator_minimize_in_progress", False)
            and not getattr(self, "_internal_dock_minimize_in_progress", False)
        ):
            if self.isMinimized() and not hub.is_module_dock_minimized(self):
                hub.dock_minimize_module_window(self)
                return
            if hub.is_module_dock_minimized(self):
                return
        super().changeEvent(event)
        if hub is not None and hub.is_module_dock_minimized(self):
            return
        if event.type() == QEvent.Type.WindowStateChange and not self.isMinimized():
            self._last_visible_window_state = self.windowState()

    def showMinimized(self) -> None:
        """Dock-minimize this module to the hub strip instead of the OS taskbar."""
        hub = _module_hub(self)
        if hub is not None:
            hub.dock_minimize_module_window(self)
            return
        if getattr(self, "_coordinator_minimize_in_progress", False):
            self.hide()
            return
        super().showMinimized()

    def setWindowState(self, state: Qt.WindowState) -> None:
        """Route title-bar minimize to the hub dock strip."""
        new_state = Qt.WindowState(state)
        if getattr(self, "_coordinator_minimize_in_progress", False):
            if bool(new_state & Qt.WindowState.WindowMinimized):
                self.hide()
                return
            super().setWindowState(new_state)
            return
        going_minimized = bool(new_state & Qt.WindowState.WindowMinimized) and not bool(
            self.windowState() & Qt.WindowState.WindowMinimized
        )
        if going_minimized:
            hub = _module_hub(self)
            if hub is not None:
                hub.dock_minimize_module_window(self)
                return
        super().setWindowState(new_state)
