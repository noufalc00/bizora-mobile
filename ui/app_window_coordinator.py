"""
Application-wide window minimize and restore for Faizan Pro Accounting.

Module pages are separate top-level windows. Minimizing the hub sends the whole
program to the taskbar under one icon. Dock-minimized modules are evicted from
the coordinator tracking list so whole-application restore leaves them alone.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QAbstractNativeEventFilter, QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QWidget

from ui.hub_dockable_window import is_hub_managed_module_shell
from ui.ui_memory import (
    schedule_bind_module_window_to_hub,
    unbind_module_window_from_hub,
)

if TYPE_CHECKING:
    from ui.main_window import MainWindow

_SW_MINIMIZE = 6
_SW_HIDE = 0
_WM_SYSCOMMAND = 0x0112
_WM_SHOWWINDOW = 0x0018
_SC_MINIMIZE = 0xF020


def ensure_app_window_coordinator(hub: MainWindow) -> AppWindowCoordinator:
    """Create or return the coordinator attached to the main hub window."""
    coordinator = getattr(hub, "_app_window_coordinator", None)
    if coordinator is None:
        coordinator = AppWindowCoordinator(hub)
        hub._app_window_coordinator = coordinator
    return coordinator


def request_application_minimize(source: QWidget | None) -> bool:
    """Route a whole-application minimize only when the main hub requests it."""
    if source is None or type(source).__name__ != "MainWindow":
        return False
    coordinator = getattr(source, "_app_window_coordinator", None)
    if coordinator is None:
        return False
    coordinator.minimize_application(source_widget=source)
    return True


def _is_windows_generic_msg(event_type) -> bool:
    """Return True for Qt native Windows message events across PySide6 builds."""
    try:
        if event_type == b"windows_generic_MSG" or event_type == "windows_generic_MSG":
            return True
        if hasattr(event_type, "data"):
            return bytes(event_type.data()) == b"windows_generic_MSG"
        return bytes(event_type) == b"windows_generic_MSG"
    except Exception:
        return False


def _native_message_address(message) -> int | None:
    """Return a readable address for a Qt native Windows MSG pointer."""
    if message is None:
        return None
    try:
        return int(message)
    except (TypeError, ValueError):
        return None


class WindowsMinimizeNativeFilter(QAbstractNativeEventFilter):
    """Intercept hub minimize commands and minimize the whole application."""

    def __init__(self, coordinator: AppWindowCoordinator) -> None:
        super().__init__()
        self._coordinator = coordinator

    def nativeEventFilter(self, event_type, message):
        if sys.platform != "win32":
            return False, 0
        if not _is_windows_generic_msg(event_type):
            return False, 0
        address = _native_message_address(message)
        if address is None:
            return False, 0
        try:
            import ctypes
            from ctypes import wintypes

            class _Point(ctypes.Structure):
                _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

            class _Msg(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM),
                    ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD),
                    ("pt", _Point),
                ]

            msg = _Msg.from_address(address)
            hwnd = int(msg.hwnd or 0)
            if not hwnd:
                return False, 0
            if msg.message == _WM_SHOWWINDOW and bool(msg.wParam):
                hub = self._coordinator._hub
                docked_hwnds = getattr(hub, "_dock_minimized_hwnds", set()) or set()
                if hwnd in docked_hwnds:
                    ctypes.windll.user32.ShowWindow(hwnd, _SW_HIDE)
                    return True, 0
                widget = self._coordinator.find_widget_for_hwnd(hwnd)
                if widget is not None and self._coordinator.is_window_in_dock(widget):
                    ctypes.windll.user32.ShowWindow(hwnd, _SW_HIDE)
                    return True, 0
            if msg.message != _WM_SYSCOMMAND:
                return False, 0
            if (int(msg.wParam or 0) & 0xFFF0) != _SC_MINIMIZE:
                return False, 0

            widget = self._coordinator.find_widget_for_hwnd(hwnd)
            hub = self._coordinator._hub
            if widget is not None and widget is not hub:
                if is_hub_managed_module_shell(widget, hub):
                    if hasattr(hub, "dock_minimize_module_window"):
                        hub.dock_minimize_module_window(widget)
                    return True, 0
                return False, 0
            if widget is hub:
                self._coordinator.minimize_application(source_widget=widget)
                return True, 0
            return False, 0
        except Exception as error:
            print(f"[WINDOW] Native minimize hook failed: {error}")
            return False, 0


class AppWindowCoordinator(QObject):
    """Minimize and restore the hub plus every open module page as one application."""

    def __init__(self, hub: MainWindow) -> None:
        super().__init__(hub)
        self._hub = hub
        self._busy = False
        self._hub_was_minimized = False
        self._app_is_minimized = False
        self._windows_to_restore: list[QWidget] = []
        self._tracked_windows: list[QWidget] = []
        self._evicted_window_ids: set[int] = set()
        self._evicted_window_hwnds: set[int] = set()
        self._hub_restore_state = Qt.WindowState.WindowNoState
        self._restore_timer: QTimer | None = None
        self._native_filter: WindowsMinimizeNativeFilter | None = None

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            if sys.platform == "win32":
                self._native_filter = WindowsMinimizeNativeFilter(self)
                app.installNativeEventFilter(self._native_filter)
        print("[WINDOW] Application window coordinator active.")

    def register_module_window(self, module_window: QWidget) -> None:
        """Track a module page and bind it to the hub taskbar group."""
        if module_window is None:
            return
        module_window._hub_window = self._hub
        if self.is_window_in_dock(module_window):
            self.evict_tracked_window(module_window)
            return
        schedule_bind_module_window_to_hub(module_window, self._hub)
        self.return_tracked_window(module_window)

    def is_window_in_dock(self, window: QWidget | None) -> bool:
        """Return True when a module belongs on the hub internal taskbar strip."""
        if window is None or not isinstance(window, QWidget):
            return False
        top_level = self._top_level_window(window) or window
        hub = self._hub
        try:
            hwnd = int(top_level.winId())
            if hwnd and hwnd in getattr(hub, "_dock_minimized_hwnds", set()):
                return True
        except RuntimeError:
            pass
        if id(top_level) in self._evicted_window_ids or id(window) in self._evicted_window_ids:
            return True
        try:
            hwnd = int(top_level.winId())
            if hwnd and hwnd in self._evicted_window_hwnds:
                return True
        except RuntimeError:
            pass
        if hasattr(hub, "is_module_dock_minimized"):
            return bool(hub.is_module_dock_minimized(top_level))
        return False

    def _native_hwnd_is_docked(self, hwnd: int) -> bool:
        """Return True when a native handle belongs to the internal taskbar strip."""
        if not hwnd:
            return False
        if hwnd in getattr(self._hub, "_dock_minimized_hwnds", set()):
            return True
        if hwnd in self._evicted_window_hwnds:
            return True
        widget = self.find_widget_for_hwnd(hwnd)
        return widget is not None and self.is_window_in_dock(widget)

    def _mark_window_evicted(self, module_window: QWidget | None) -> None:
        """Remember a dock-minimized shell so discovery cannot re-track it."""
        if module_window is None:
            return
        top_level = self._top_level_window(module_window)
        for candidate in (module_window, top_level):
            if candidate is None:
                continue
            self._evicted_window_ids.add(id(candidate))
            try:
                hwnd = int(candidate.winId())
                if hwnd:
                    self._evicted_window_hwnds.add(hwnd)
            except RuntimeError:
                continue

    def _clear_window_eviction(self, module_window: QWidget | None) -> None:
        """Clear eviction markers when a module returns from the internal taskbar."""
        if module_window is None:
            return
        top_level = self._top_level_window(module_window)
        for candidate in (module_window, top_level):
            if candidate is None:
                continue
            self._evicted_window_ids.discard(id(candidate))
            try:
                hwnd = int(candidate.winId())
                if hwnd:
                    self._evicted_window_hwnds.discard(hwnd)
            except RuntimeError:
                continue

    def _purge_docked_from_tracked(self) -> None:
        """Drop docked or evicted modules from the active tracking list."""
        for window in list(self._tracked_windows):
            if self.is_window_in_dock(window):
                while window in self._tracked_windows:
                    self._tracked_windows.remove(window)

    @staticmethod
    def _top_level_window(widget: QWidget | None) -> QWidget | None:
        """Return the absolute top-level shell for one module window."""
        if widget is None or not isinstance(widget, QWidget):
            return None
        try:
            top_level = widget.window()
            return top_level if top_level is not None else widget
        except RuntimeError:
            return widget

    def _should_guard_show_event(self, watched: QObject) -> bool:
        """Return True when a Show event may belong to a dock-minimized module shell."""
        if not isinstance(watched, QWidget):
            return False
        top_level = self._top_level_window(watched)
        if top_level is None:
            return False
        if self.is_window_in_dock(top_level):
            return True
        if id(top_level) in self._evicted_window_ids:
            return True
        try:
            hwnd = int(top_level.winId())
            if hwnd and hwnd in self._evicted_window_hwnds:
                return True
            if hwnd and hwnd in getattr(self._hub, "_dock_minimized_hwnds", set()):
                return True
        except RuntimeError:
            pass
        return False

    def _same_native_window(self, left: QWidget | None, right: QWidget | None) -> bool:
        """Return True when two widgets refer to the same native top-level window."""
        if left is None or right is None:
            return False
        left_top = self._top_level_window(left)
        right_top = self._top_level_window(right)
        if left_top is right_top or left is right or left_top is right or left is right_top:
            return True
        try:
            return int(left_top.winId()) == int(right_top.winId())
        except RuntimeError:
            return False

    def _purge_window_from_restore_list(self, module_window: QWidget | None) -> None:
        """Remove one module from the pending whole-application restore list."""
        if module_window is None:
            return
        self._windows_to_restore = [
            window
            for window in self._windows_to_restore
            if not self._same_native_window(window, module_window)
        ]

    def evict_tracked_window(self, module_window: QWidget | None) -> None:
        """Remove a dock-minimized module from whole-application minimize tracking."""
        if module_window is None:
            return
        self._mark_window_evicted(module_window)
        top_level = self._top_level_window(module_window)
        for candidate in (module_window, top_level):
            if candidate is None:
                continue
            while candidate in self._tracked_windows:
                self._tracked_windows.remove(candidate)
        self._purge_window_from_restore_list(module_window)
        self._purge_docked_from_tracked()
        print(
            f"[DEBUG] EVICTED: Window removed from tracking list. "
            f"Tracked count: {len(self._tracked_windows)}"
        )

    def return_tracked_window(self, module_window: QWidget | None) -> None:
        """Add a restored module back to whole-application minimize tracking."""
        if module_window is None:
            return
        self._clear_window_eviction(module_window)
        hub = self._hub
        if hasattr(hub, "is_module_dock_minimized") and hub.is_module_dock_minimized(
            module_window
        ):
            return
        top_level = self._top_level_window(module_window) or module_window
        if top_level in self._tracked_windows or module_window in self._tracked_windows:
            return
        self._tracked_windows.append(top_level)
        print(
            f"[DEBUG] RETURNED: Window added back to tracking list. "
            f"Tracked count: {len(self._tracked_windows)}"
        )

    def is_managed_window(self, widget: QWidget | None) -> bool:
        """Return True when a top-level window belongs to this application session."""
        if widget is None:
            return False
        try:
            if widget is self._hub:
                return bool(getattr(self._hub, "dashboard_loaded", False))
            if type(widget).__name__ == "StandaloneModuleWindow":
                return True
            if isinstance(widget, (QMainWindow, QDialog)):
                owner = getattr(widget, "_hub_window", None) or widget.parent()
                return owner is self._hub
        except RuntimeError:
            return False
        return False

    def find_widget_for_hwnd(self, hwnd: int) -> QWidget | None:
        """Resolve a Qt widget from a native window handle."""
        if not hwnd:
            return None
        docked_modules = getattr(self._hub, "_dock_minimized_modules", {}) or {}
        for widget in docked_modules.values():
            try:
                if int(widget.winId()) == hwnd:
                    return widget
            except RuntimeError:
                continue
        app = QApplication.instance()
        if app is None:
            return None
        for widget in app.topLevelWidgets():
            try:
                if int(widget.winId()) == hwnd:
                    return widget
            except RuntimeError:
                continue
        return None

    def _discover_managed_windows(self) -> list[QWidget]:
        """Rebuild the tracking list from live windows, excluding internal-taskbar docks."""
        app = QApplication.instance()
        if app is None:
            self._tracked_windows = []
            return []

        candidates: list[QWidget] = []
        seen: set[int] = set()
        open_modules = getattr(self._hub, "_open_module_windows", {}) or {}
        scan_widgets = list(app.topLevelWidgets())
        for tracked_window in open_modules.values():
            if tracked_window not in scan_widgets:
                scan_widgets.append(tracked_window)

        for widget in scan_widgets:
            try:
                if not widget.isWindow():
                    continue
                if not is_hub_managed_module_shell(widget, self._hub):
                    continue
                key = id(widget)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(widget)
            except RuntimeError:
                continue

        final_list = [window for window in candidates if not self.is_window_in_dock(window)]
        self._tracked_windows = final_list
        return final_list

    @staticmethod
    def _strip_app_minimize(state: Qt.WindowState) -> Qt.WindowState:
        """Return the visible state to apply after the hub is restored from the taskbar."""
        visible_state = state & ~Qt.WindowState.WindowMinimized
        if visible_state == Qt.WindowState.WindowNoState:
            return Qt.WindowState.WindowActive
        return visible_state

    def _apply_window_state(self, widget: QWidget, state: Qt.WindowState) -> None:
        """Restore one window to its saved visible state, including maximized mode."""
        try:
            widget.setUpdatesEnabled(False)
            if state & Qt.WindowState.WindowFullScreen:
                widget.showFullScreen()
            elif state & Qt.WindowState.WindowMaximized:
                widget.showMaximized()
            else:
                widget.showNormal()
                if state not in (
                    Qt.WindowState.WindowNoState,
                    Qt.WindowState.WindowActive,
                ):
                    widget.setWindowState(state)
            widget.show()
            widget.repaint()
        except RuntimeError:
            pass
        finally:
            try:
                widget.setUpdatesEnabled(True)
            except RuntimeError:
                pass

    def _native_hide_window(self, module_window: QWidget | None, *, docked: bool = False) -> None:
        """Hide a module at both the Qt and Win32 layers."""
        if module_window is None:
            return
        try:
            if docked:
                module_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            module_window.hide()
            if sys.platform == "win32":
                import ctypes

                hwnd = int(module_window.winId())
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, _SW_HIDE)
        except RuntimeError:
            pass

    def _hide_module_for_app_minimize(self, module_window: QWidget | None) -> None:
        """Hide one floating module page while keeping it open for app restore."""
        if module_window is None or self.is_window_in_dock(module_window):
            return
        try:
            saved_state = module_window.windowState() & ~Qt.WindowState.WindowMinimized
            if saved_state == Qt.WindowState.WindowNoState:
                saved_state = Qt.WindowState.WindowActive
            module_window._last_visible_window_state = saved_state
            module_window._hidden_by_app_minimize = True
            unbind_module_window_from_hub(module_window)
            module_window._coordinator_minimize_in_progress = True
            self._native_hide_window(module_window, docked=False)
        except RuntimeError:
            return
        finally:
            try:
                module_window._coordinator_minimize_in_progress = False
            except RuntimeError:
                pass
        if module_window not in self._windows_to_restore:
            self._windows_to_restore.append(module_window)

    def _restore_module_after_app_minimize(self, module_window: QWidget | None) -> None:
        """Re-show one floating module page after the hub returns from the taskbar."""
        if module_window is None or self.is_window_in_dock(module_window):
            return
        try:
            module_window._hidden_by_app_minimize = False
            module_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
            module_window._coordinator_minimize_in_progress = True
            saved_state = getattr(
                module_window,
                "_last_visible_window_state",
                Qt.WindowState.WindowNoState,
            )
            self._apply_window_state(module_window, saved_state)
            schedule_bind_module_window_to_hub(module_window, self._hub)
            self.return_tracked_window(module_window)
            module_window.raise_()
        except RuntimeError:
            return
        finally:
            try:
                module_window._coordinator_minimize_in_progress = False
            except RuntimeError:
                pass

    def _rehide_whole_app_children(self) -> None:
        """Keep internal-taskbar modules hidden after the hub taskbar restore."""
        self._suppress_docked_module_windows()

    def _suppress_docked_module_windows(self) -> None:
        """Keep internal-taskbar modules hidden after the hub is restored from the OS."""
        docked_modules = getattr(self._hub, "_dock_minimized_modules", {}) or {}
        for module_window in list(docked_modules.values()):
            try:
                if not self.is_window_in_dock(module_window):
                    continue
                unbind_module_window_from_hub(module_window)
                module_window._coordinator_minimize_in_progress = True
                self._native_hide_window(module_window, docked=True)
            except RuntimeError:
                continue
            finally:
                try:
                    module_window._coordinator_minimize_in_progress = False
                except RuntimeError:
                    pass

    def _set_coordinator_minimize_flag(self, active: bool) -> None:
        """Mark managed windows so setWindowState overrides do not recurse."""
        flagged: set[int] = set()
        for widget in list(self._tracked_windows):
            try:
                widget_id = id(widget)
                if widget_id in flagged:
                    continue
                flagged.add(widget_id)
                widget._coordinator_minimize_in_progress = active
            except RuntimeError:
                continue
        open_modules = getattr(self._hub, "_open_module_windows", {}) or {}
        for widget in open_modules.values():
            try:
                widget_id = id(widget)
                if widget_id in flagged:
                    continue
                flagged.add(widget_id)
                widget._coordinator_minimize_in_progress = active
            except RuntimeError:
                continue
        try:
            self._hub._coordinator_minimize_in_progress = active
        except RuntimeError:
            pass

    def minimize_application(self, source_widget: QWidget | None = None) -> None:
        """Hide visible module pages and send only the hub to the Windows taskbar."""
        if self._busy:
            return
        if source_widget is not None and source_widget is not self._hub:
            return
        if getattr(self._hub, "_modal_dialog_active", False):
            return
        if self._app_is_minimized and self._hub.isMinimized():
            return

        if self._restore_timer is not None:
            self._restore_timer.stop()

        self._busy = True
        self._set_coordinator_minimize_flag(True)
        try:
            self._windows_to_restore = []

            try:
                self._hub_restore_state = self._hub.windowState()
            except RuntimeError:
                self._hub_restore_state = Qt.WindowState.WindowActive

            docked_modules = getattr(self._hub, "_dock_minimized_modules", {}) or {}
            for docked_window in list(docked_modules.values()):
                try:
                    self._mark_window_evicted(docked_window)
                    unbind_module_window_from_hub(docked_window)
                    self._native_hide_window(docked_window, docked=True)
                except RuntimeError:
                    continue

            self._purge_docked_from_tracked()
            visible_modules = self._discover_managed_windows()

            hub = self._hub
            for window in visible_modules:
                if window is self._hub:
                    continue
                if self.is_window_in_dock(window):
                    continue
                try:
                    self._hide_module_for_app_minimize(window)
                except RuntimeError:
                    continue

            self._hub._children_hidden_by_app_minimize = list(self._windows_to_restore)
            docked_count = len(getattr(hub, "_dock_minimized_modules", {}) or {})

            self._app_is_minimized = True
            self._hub_was_minimized = True

            if not self._hub.isMinimized():
                if sys.platform == "win32":
                    import ctypes

                    self._hub.createWinId()
                    hwnd = int(self._hub.winId())
                    if hwnd:
                        ctypes.windll.user32.ShowWindow(hwnd, _SW_MINIMIZE)
                else:
                    self._hub.setWindowState(
                        self._hub.windowState() | Qt.WindowState.WindowMinimized
                    )

            print(
                f"[WINDOW] Whole application minimized "
                f"({docked_count} on internal taskbar, "
                f"{len(self._windows_to_restore)} floating pages hidden)."
            )
        finally:
            self._set_coordinator_minimize_flag(False)
            self._busy = False

    def restore_application(self) -> None:
        """Restore the hub and reopen floating module pages hidden during app minimize."""
        if self._busy:
            return
        if getattr(self._hub, "_modal_dialog_active", False):
            return
        if not self._app_is_minimized and not self._hub.isMinimized():
            return

        self._busy = True
        self._set_coordinator_minimize_flag(True)
        try:
            self._app_is_minimized = False
            self._hub_was_minimized = False

            app = QApplication.instance()
            hidden_children = [
                window
                for window in list(self._windows_to_restore)
                if not self.is_window_in_dock(window)
            ]
            self._windows_to_restore.clear()
            self._hub._children_hidden_by_app_minimize = []
            docked_count = len(getattr(self._hub, "_dock_minimized_modules", {}) or {})

            self._hub.setUpdatesEnabled(False)
            try:
                self._apply_window_state(
                    self._hub,
                    self._strip_app_minimize(self._hub_restore_state),
                )

                for module_window in hidden_children:
                    self._restore_module_after_app_minimize(module_window)

                self._suppress_docked_module_windows()
                if app is not None:
                    app.processEvents()
                self._rehide_whole_app_children()
                QTimer.singleShot(0, self._rehide_whole_app_children)
                QTimer.singleShot(120, self._rehide_whole_app_children)
                if hasattr(self._hub, "_refresh_module_minimize_strip"):
                    self._hub._refresh_module_minimize_strip()
                self._hub.raise_()
                self._hub.activateWindow()
                self._hub.repaint()
            finally:
                self._hub.setUpdatesEnabled(True)

            print(
                f"[WINDOW] Whole application restored "
                f"({len(hidden_children)} floating pages reopened; "
                f"{docked_count} on internal taskbar)."
            )
        finally:
            self._set_coordinator_minimize_flag(False)
            self._busy = False

    def _schedule_restore_from_taskbar(self) -> None:
        """Restore once after Windows finishes the hub taskbar un-minimize transition."""
        if self._restore_timer is None:
            self._restore_timer = QTimer(self)
            self._restore_timer.setSingleShot(True)
            self._restore_timer.timeout.connect(self.restore_application)
        self._restore_timer.start(80)

    def handle_hub_change_event(self, event) -> None:
        """React to hub taskbar restore after a whole-application minimize."""
        if event.type() != QEvent.Type.WindowStateChange:
            return
        if self._busy:
            return

        if self._hub.isMinimized():
            self._hub_was_minimized = True
            return

        if self._app_is_minimized and self._hub_was_minimized:
            self._schedule_restore_from_taskbar()

    def handle_application_state_changed(self, state: Qt.ApplicationState) -> None:
        """Snapshot managed windows when Windows hides the whole process."""
        if state == Qt.ApplicationState.ApplicationHidden:
            if (
                not self._busy
                and not self._app_is_minimized
                and self._hub.isMinimized()
            ):
                self.minimize_application()
            return
        if getattr(self._hub, "_modal_dialog_active", False):
            return
        if (
            state == Qt.ApplicationState.ApplicationActive
            and self._app_is_minimized
            and not self._hub.isMinimized()
        ):
            self._schedule_restore_from_taskbar()

    def eventFilter(self, watched, event):
        """React to hub window-state changes when native hooks are unavailable."""
        if not isinstance(watched, QWidget):
            return False
        try:
            from shiboken6 import Shiboken

            if not Shiboken.isValid(watched):
                return False
        except Exception:
            pass
        if event.type() == QEvent.Type.Show and self._should_guard_show_event(watched):
            try:
                top_level = self._top_level_window(watched)
                if top_level is not None and self.is_window_in_dock(top_level):
                    self._native_hide_window(top_level, docked=True)
                    return True
            except RuntimeError:
                pass
            return False
        if (
            event.type() == QEvent.Type.WindowStateChange
            and watched is self._hub
            and not self._busy
            and not getattr(watched, "_coordinator_minimize_in_progress", False)
        ):
            QTimer.singleShot(0, lambda: self._handle_hub_state_change())
        return False

    def _handle_hub_state_change(self) -> None:
        """Apply whole-application minimize or restore after the hub state settles."""
        if self._busy:
            return
        try:
            if self._hub.isMinimized() and not self._app_is_minimized:
                self.minimize_application(source_widget=self._hub)
                return
            if self._app_is_minimized and not self._hub.isMinimized():
                self._schedule_restore_from_taskbar()
        except RuntimeError:
            return
