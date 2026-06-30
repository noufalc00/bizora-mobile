"""
Hub-internal taskbar behavior for every floating module shell.

StandaloneModuleWindow implements these hooks directly. QDialog-based utility
windows (Print Settings, Tax Settings, etc.) receive the same behavior here so
title-bar minimize lands on the named internal strip instead of an OS ghost.
"""

from __future__ import annotations

import types

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QDialog, QMainWindow, QWidget


def detach_hub_module_from_qt_parent(module_window: QWidget | None, hub_window: QWidget | None) -> None:
    """Break Qt parent ownership so hub restore does not auto-restore child shells."""
    if module_window is None or hub_window is None:
        return
    try:
        parent = module_window.parent()
        if parent is hub_window:
            module_window.setParent(None)
    except RuntimeError:
        pass


def _resolve_hub(module_window: QWidget | None) -> QWidget | None:
    """Return the MainWindow hub attached to one module shell."""
    if module_window is None:
        return None
    try:
        from ui.standalone_window import _module_hub

        return _module_hub(module_window)
    except Exception:
        return getattr(module_window, "_hub_window", None)


def _hub_can_dock(hub: QWidget | None) -> bool:
    """Return True when the hub exposes internal taskbar dock helpers."""
    return hub is not None and hasattr(hub, "dock_minimize_module_window")


class _HubDockableEventFilter(QObject):
    """Route minimize and show events for QDialog-style module shells."""

    def __init__(self, module_window: QWidget) -> None:
        super().__init__(module_window)
        self._module_window = module_window

    def eventFilter(self, watched: QObject, event) -> bool:  # noqa: N802
        if watched is not self._module_window:
            return False
        try:
            from shiboken6 import Shiboken

            if not Shiboken.isValid(self._module_window):
                return False
        except Exception:
            pass

        hub = _resolve_hub(self._module_window)
        if not _hub_can_dock(hub):
            return False

        if event.type() == QEvent.Type.Show:
            return self._guard_show(hub)
        if event.type() == QEvent.Type.WindowStateChange:
            return self._guard_window_state(hub)
        return False

    def _guard_show(self, hub: QWidget) -> bool:
        """Block paint for dock-minimized shells."""
        try:
            if hub.is_module_dock_minimized(self._module_window):
                self._module_window.hide()
                return True
            hwnd = int(self._module_window.winId())
            if hwnd and hwnd in getattr(hub, "_dock_minimized_hwnds", set()):
                self._module_window.hide()
                return True
            coordinator = getattr(hub, "_app_window_coordinator", None)
            if coordinator is not None and coordinator.is_window_in_dock(self._module_window):
                self._module_window.hide()
                return True
        except RuntimeError:
            pass
        return False

    def _guard_window_state(self, hub: QWidget) -> bool:
        """Send title-bar minimize to the internal taskbar strip."""
        if getattr(self._module_window, "_coordinator_minimize_in_progress", False):
            return False
        if getattr(self._module_window, "_internal_dock_minimize_in_progress", False):
            return False
        try:
            if hub.is_module_dock_minimized(self._module_window):
                return False
            if self._module_window.isMinimized():
                hub.dock_minimize_module_window(self._module_window)
                return True
        except RuntimeError:
            pass
        return False


def _patch_method(module_window: QWidget, method_name: str, replacement) -> None:
    """Replace one QWidget method while preserving the original on the instance."""
    originals: dict = getattr(module_window, "_hub_dockable_originals", {})
    if method_name not in originals:
        originals[method_name] = getattr(module_window, method_name)
        module_window._hub_dockable_originals = originals
    setattr(module_window, method_name, types.MethodType(replacement, module_window))


def ensure_hub_dockable_window(module_window: QWidget | None, hub_window: QWidget | None = None) -> None:
    """
    Install internal-taskbar minimize behavior on any hub module shell.

    StandaloneModuleWindow already overrides the relevant QWidget hooks.
    """
    if module_window is None:
        return
    if type(module_window).__name__ == "StandaloneModuleWindow":
        return
    if getattr(module_window, "_hub_dockable_installed", False):
        return
    if hub_window is not None:
        module_window._hub_window = hub_window

    detach_hub_module_from_qt_parent(module_window, hub_window or _resolve_hub(module_window))

    if not isinstance(module_window, (QMainWindow, QDialog)) or not module_window.isWindow():
        return

    module_window._hub_dockable_installed = True
    if not hasattr(module_window, "_last_visible_window_state"):
        module_window._last_visible_window_state = Qt.WindowState.WindowNoState

    event_filter = _HubDockableEventFilter(module_window)
    module_window.installEventFilter(event_filter)
    module_window._hub_dockable_event_filter = event_filter

    def show_minimized(self) -> None:
        hub = _resolve_hub(self)
        if _hub_can_dock(hub):
            hub.dock_minimize_module_window(self)
            return
        if getattr(self, "_coordinator_minimize_in_progress", False):
            self.hide()
            return
        originals = getattr(self, "_hub_dockable_originals", {})
        original = originals.get("showMinimized")
        if callable(original):
            original()

    def set_window_state(self, state: Qt.WindowState) -> None:
        new_state = Qt.WindowState(state)
        if getattr(self, "_coordinator_minimize_in_progress", False):
            if bool(new_state & Qt.WindowState.WindowMinimized):
                self.hide()
                return
            originals = getattr(self, "_hub_dockable_originals", {})
            original = originals.get("setWindowState")
            if callable(original):
                original(new_state)
            return

        going_minimized = bool(new_state & Qt.WindowState.WindowMinimized) and not bool(
            self.windowState() & Qt.WindowState.WindowMinimized
        )
        if going_minimized:
            hub = _resolve_hub(self)
            if _hub_can_dock(hub):
                hub.dock_minimize_module_window(self)
                return

        originals = getattr(self, "_hub_dockable_originals", {})
        original = originals.get("setWindowState")
        if callable(original):
            original(new_state)

    def change_event(self, event) -> None:
        hub = _resolve_hub(self)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and _hub_can_dock(hub)
            and not getattr(self, "_coordinator_minimize_in_progress", False)
            and not getattr(self, "_internal_dock_minimize_in_progress", False)
        ):
            try:
                if self.isMinimized() and not hub.is_module_dock_minimized(self):
                    hub.dock_minimize_module_window(self)
                    return
                if hub.is_module_dock_minimized(self):
                    return
            except RuntimeError:
                pass

        originals = getattr(self, "_hub_dockable_originals", {})
        original = originals.get("changeEvent")
        if callable(original):
            original(event)

        if hub is not None:
            try:
                if hub.is_module_dock_minimized(self):
                    return
            except RuntimeError:
                return
        if event.type() == QEvent.Type.WindowStateChange and not self.isMinimized():
            self._last_visible_window_state = self.windowState()

    def show_event(self, event: QShowEvent) -> None:
        hub = _resolve_hub(self)
        if hub is not None:
            try:
                if hub.is_module_dock_minimized(self):
                    event.ignore()
                    self.hide()
                    return
                hwnd = int(self.winId())
                if hwnd and hwnd in getattr(hub, "_dock_minimized_hwnds", set()):
                    event.ignore()
                    self.hide()
                    return
                coordinator = getattr(hub, "_app_window_coordinator", None)
                if coordinator is not None and coordinator.is_window_in_dock(self):
                    event.ignore()
                    self.hide()
                    return
            except RuntimeError:
                pass

        originals = getattr(self, "_hub_dockable_originals", {})
        original = originals.get("showEvent")
        if callable(original):
            original(event)

    _patch_method(module_window, "showMinimized", show_minimized)
    _patch_method(module_window, "setWindowState", set_window_state)
    _patch_method(module_window, "changeEvent", change_event)
    _patch_method(module_window, "showEvent", show_event)


def is_hub_managed_module_shell(widget: QWidget | None, hub: QWidget | None) -> bool:
    """Return True when a top-level window belongs to the hub module taskbar."""
    if widget is None or hub is None:
        return False
    if widget is hub:
        return False
    try:
        if not widget.isWindow():
            return False
    except RuntimeError:
        return False
    if type(widget).__name__ == "StandaloneModuleWindow":
        return True
    if getattr(widget, "_hub_window", None) is hub:
        return isinstance(widget, (QMainWindow, QDialog))
    open_modules = getattr(hub, "_open_module_windows", {}) or {}
    return widget in open_modules.values()
