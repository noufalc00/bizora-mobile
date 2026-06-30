"""
QSettings-backed UI state persistence for Faizan Pro Accounting.

Persists window geometry, main-window toolbars/docks state, and QTableWidget
column layouts under the FaizanPro / AccountingApp settings scope.
"""

from __future__ import annotations

import re
import sys
from typing import Iterable

from PySide6.QtCore import QSettings, Qt, QTimer, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QHeaderView, QMainWindow, QTableWidget, QWidget

SETTINGS_ORG = "FaizanPro"
SETTINGS_APP = "AccountingApp"
WINDOWS_APP_USER_MODEL_ID = "BIZORA.Accounting.Desktop"


def configure_windows_process_app_user_model_id() -> None:
    """Assign one Windows AppUserModelID so all process windows share one taskbar icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            WINDOWS_APP_USER_MODEL_ID
        )
    except Exception as error:
        print(f"[WINDOW] AppUserModelID setup failed: {error}")


def is_live_qwidget(widget: QWidget | None) -> bool:
    """Return True when a QWidget wrapper still points to a live C++ object."""
    if widget is None:
        return False
    try:
        from shiboken6 import Shiboken

        return bool(Shiboken.isValid(widget))
    except Exception:
        return True

MAIN_WINDOW_UI_KEYS = (
    "mainwindow/geometry",
    "mainwindow/windowState",
    "mainwindow/splitterState",
)


def create_ui_settings() -> QSettings:
    """Return the shared application QSettings instance."""
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def derive_window_memory_key(title: str) -> str:
    """Build a stable settings slug from a module window title."""
    cleaned = (title or "").strip()
    cleaned = re.sub(r"\s*\(Edit\s*#\d+\)\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\(\d+\)\s*$", "", cleaned)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", cleaned).strip("_").lower()
    return slug or "standalone_module"


def window_geometry_settings_key(host: QWidget) -> str:
    """Return the QSettings key used for a host window's geometry blob."""
    custom_key = getattr(host, "_ui_memory_geometry_key", None)
    if custom_key:
        return f"window/{custom_key}/geometry"
    return f"{host.__class__.__name__}/geometry"


def table_header_settings_key(class_name: str, table_attr: str = "table") -> str:
    """Build the settings key used for a table header state blob."""
    if table_attr == "table":
        return f"{class_name}/tableHeaderState"
    return f"{class_name}/{table_attr}HeaderState"


def is_ui_memory_settings_key(key: str) -> bool:
    """Return True when a QSettings key belongs to persisted UI layout memory."""
    if key in MAIN_WINDOW_UI_KEYS:
        return True
    if key.startswith("window/") and key.endswith("/geometry"):
        return True
    if key.endswith("/geometry"):
        return True
    if key.endswith("HeaderState"):
        return True
    return False


def discover_table_widget_attrs(host: QWidget) -> tuple[str, ...]:
    """Return attribute names on host that currently hold a QTableWidget."""
    names: list[str] = []
    for name, value in vars(host).items():
        if isinstance(value, QTableWidget):
            names.append(name)
    return tuple(names)


def ensure_table_columns_interactive(table: QTableWidget) -> None:
    """Force every column to Interactive resize mode (Sales Book style)."""
    if table is None or table.columnCount() <= 0:
        return

    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(48)
    header.setHighlightSections(True)
    header.setSectionsClickable(True)
    for column_index in range(table.columnCount()):
        header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.Interactive)


def table_header_column_count_key(header_state_key: str) -> str:
    """Settings key storing the column count paired with a header state blob."""
    return f"{header_state_key}ColumnCount"


def restore_table_header_state(
    host: QWidget,
    table: QTableWidget,
    *,
    settings: QSettings | None = None,
    table_attr: str = "table",
) -> None:
    """Restore a table header layout from QSettings."""
    if table is None or table.columnCount() <= 0:
        return

    ensure_table_columns_interactive(table)
    store = settings or getattr(host, "settings", None) or create_ui_settings()
    key = table_header_settings_key(host.__class__.__name__, table_attr)
    count_key = table_header_column_count_key(key)
    try:
        state = store.value(key)
        if not state:
            return
        saved_count = store.value(count_key)
        if saved_count is None:
            # Legacy saves lack column-count metadata; skip restore to avoid Qt crashes.
            store.remove(key)
            return
        if int(saved_count) != table.columnCount():
            store.remove(key)
            store.remove(count_key)
            return
        header = table.horizontalHeader()
        if not header.restoreState(state):
            store.remove(key)
            store.remove(count_key)
    except Exception:
        try:
            store.remove(key)
            store.remove(count_key)
        except Exception:
            pass
    finally:
        ensure_table_columns_interactive(table)


def save_table_header_state(
    host: QWidget,
    table: QTableWidget,
    *,
    settings: QSettings | None = None,
    table_attr: str = "table",
) -> None:
    """Persist a table header layout to QSettings."""
    if table is None or table.columnCount() <= 0:
        return

    store = settings or getattr(host, "settings", None) or create_ui_settings()
    key = table_header_settings_key(host.__class__.__name__, table_attr)
    count_key = table_header_column_count_key(key)
    try:
        store.setValue(key, table.horizontalHeader().saveState())
        store.setValue(count_key, table.columnCount())
    except Exception:
        pass


def has_saved_window_geometry(
    host: QWidget,
    *,
    settings: QSettings | None = None,
) -> bool:
    """Return True when persisted geometry exists for a floating window host."""
    if not is_floating_window(host):
        return False

    store = settings or getattr(host, "settings", None) or create_ui_settings()
    key = window_geometry_settings_key(host)
    try:
        if store.value(key):
            return True
        legacy_key = f"{host.__class__.__name__}/geometry"
        return bool(store.value(legacy_key))
    except Exception:
        return False


def _screen_for_window(host: QWidget):
    """Return the QScreen that should bound a floating window."""
    screen = host.screen()
    if screen is not None:
        return screen
    try:
        screen = QGuiApplication.screenAt(host.frameGeometry().center())
    except Exception:
        screen = None
    return screen or QGuiApplication.primaryScreen()


def _frame_decoration_offsets(host: QWidget) -> tuple[int, int, int, int]:
    """Return left, top, right, bottom chrome sizes between client and frame rects."""
    geo = host.geometry()
    frame = host.frameGeometry()
    return (
        geo.x() - frame.x(),
        geo.y() - frame.y(),
        frame.right() - geo.right(),
        frame.bottom() - geo.bottom(),
    )


def clamp_window_to_available_screen(host: QWidget, *, margin: int = 8) -> bool:
    """
    Keep the full window frame inside the screen work area above the taskbar.

    Uses frame geometry so title-bar chrome is included and top/bottom are not
    corrected independently (which previously pushed the top off-screen).

    Returns True when the window geometry was adjusted.
    """
    if not is_live_qwidget(host) or not host.isWindow():
        return False
    if host.isMaximized() or host.isFullScreen():
        return False
    if getattr(host, "_ui_memory_clamping", False):
        return False

    screen = _screen_for_window(host)
    if screen is None:
        return False

    work = screen.availableGeometry()
    if work.width() <= 0 or work.height() <= 0:
        return False

    left_bound = work.x() + margin
    top_bound = work.y() + margin
    right_bound = work.x() + work.width() - margin - 1
    bottom_bound = work.y() + work.height() - margin - 1
    work_w = max(200, right_bound - left_bound + 1)
    work_h = max(150, bottom_bound - top_bound + 1)

    deco_l, deco_t, deco_r, deco_b = _frame_decoration_offsets(host)
    min_client_w = host.minimumWidth()
    min_client_h = host.minimumHeight()
    min_frame_w = min_client_w + deco_l + deco_r
    min_frame_h = min_client_h + deco_t + deco_b

    if min_frame_w > work_w:
        host.setMinimumWidth(max(200, work_w - deco_l - deco_r))
        min_client_w = host.minimumWidth()
        min_frame_w = min_client_w + deco_l + deco_r
    if min_frame_h > work_h:
        host.setMinimumHeight(max(150, work_h - deco_t - deco_b))
        min_client_h = host.minimumHeight()
        min_frame_h = min_client_h + deco_t + deco_b

    frame = host.frameGeometry()
    frame_w = min(max(frame.width(), min_frame_w), work_w)
    frame_h = min(max(frame.height(), min_frame_h), work_h)
    frame_x = frame.x()
    frame_y = frame.y()

    if frame_x < left_bound:
        frame_x = left_bound
    if frame_y < top_bound:
        frame_y = top_bound
    if frame_x + frame_w - 1 > right_bound:
        frame_x = right_bound - frame_w + 1
    if frame_y + frame_h - 1 > bottom_bound:
        frame_y = bottom_bound - frame_h + 1

    if frame_x < left_bound:
        frame_x = left_bound
        frame_w = min(frame_w, work_w)
    if frame_y < top_bound:
        frame_y = top_bound
        frame_h = min(frame_h, work_h)

    new_client_w = max(min_client_w, frame_w - deco_l - deco_r)
    new_client_h = max(min_client_h, frame_h - deco_t - deco_b)
    new_client_x = frame_x + deco_l
    new_client_y = frame_y + deco_t

    geo = host.geometry()
    if (
        geo.x() == new_client_x
        and geo.y() == new_client_y
        and geo.width() == new_client_w
        and geo.height() == new_client_h
    ):
        return False

    host._ui_memory_clamping = True
    try:
        host.setGeometry(new_client_x, new_client_y, new_client_w, new_client_h)
    finally:
        host._ui_memory_clamping = False
    return True


def _fire_scheduled_clamp(host: QWidget) -> None:
    """Run one deferred clamp pass for the latest scheduled request on a host."""
    if not is_live_qwidget(host):
        return
    margin = getattr(host, "_ui_memory_clamp_margin", 8)
    clamp_window_to_available_screen(host, margin=margin)


def schedule_clamp_window_to_available_screen(host: QWidget, *, margin: int = 8) -> None:
    """Clamp window geometry on the next event-loop tick after layout settles."""
    if not is_live_qwidget(host) or not host.isWindow():
        return
    host._ui_memory_clamp_margin = margin
    timer = getattr(host, "_ui_memory_clamp_timer", None)
    if timer is None:
        timer = QTimer(host)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda host=host: _fire_scheduled_clamp(host))
        host._ui_memory_clamp_timer = timer
    timer.start(0)


def restore_window_geometry(
    host: QWidget,
    *,
    settings: QSettings | None = None,
) -> bool:
    """Restore top-level window geometry from QSettings."""
    if not is_floating_window(host):
        return False

    store = settings or getattr(host, "settings", None) or create_ui_settings()
    key = window_geometry_settings_key(host)
    try:
        geometry = store.value(key)
        if not geometry:
            geometry = store.value(f"{host.__class__.__name__}/geometry")
        if geometry and host.restoreGeometry(geometry):
            clamp_window_to_available_screen(host)
            return True
    except Exception:
        try:
            store.remove(key)
        except Exception:
            pass
    return False


def save_window_geometry(host: QWidget, *, settings: QSettings | None = None) -> None:
    """Persist top-level window geometry to QSettings."""
    if not is_floating_window(host):
        return

    store = settings or getattr(host, "settings", None) or create_ui_settings()
    try:
        clamp_window_to_available_screen(host)
        store.setValue(window_geometry_settings_key(host), host.saveGeometry())
        legacy_key = f"{host.__class__.__name__}/geometry"
        if legacy_key != window_geometry_settings_key(host):
            store.remove(legacy_key)
    except Exception:
        pass


def apply_default_window_geometry(
    host: QWidget,
    *,
    width_ratio: float = 0.9,
    height_ratio: float = 0.9,
    fallback_size: tuple[int, int] = (1200, 760),
) -> None:
    """Center a floating window using a screen-relative default size."""
    if not is_floating_window(host):
        return

    screen = host.screen()
    if screen is None:
        host.resize(*fallback_size)
        return

    available_geometry = screen.availableGeometry()
    width = max(host.minimumWidth(), int(available_geometry.width() * width_ratio))
    height = max(host.minimumHeight(), int(available_geometry.height() * height_ratio))
    host.resize(width, height)
    x = available_geometry.x() + (available_geometry.width() - width) // 2
    y = available_geometry.y() + (available_geometry.height() - height) // 2
    host.move(x, y)
    clamp_window_to_available_screen(host)


def present_floating_window(
    host: QWidget,
    *,
    width_ratio: float = 0.9,
    height_ratio: float = 0.9,
    fallback_size: tuple[int, int] = (1200, 760),
    settings: QSettings | None = None,
    restore_minimized: bool = True,
) -> None:
    """Show a floating window, preserving saved geometry when available."""
    if not has_saved_window_geometry(host, settings=settings):
        apply_default_window_geometry(
            host,
            width_ratio=width_ratio,
            height_ratio=height_ratio,
            fallback_size=fallback_size,
        )
    if restore_minimized and host.isMinimized():
        host.showNormal()
    else:
        host.show()
    host.raise_()
    host.activateWindow()
    schedule_clamp_window_to_available_screen(host)
    hub_window = getattr(host, "_hub_window", None)
    if hub_window is not None:
        force_bind_module_window_to_hub(host, hub_window)


def bind_module_window_to_hub(
    module_window: QWidget,
    hub_window: QWidget,
    *,
    force: bool = False,
) -> None:
    """Attach module windows to the hub for grouped taskbar behaviour on Windows."""
    if module_window is None or hub_window is None:
        return
    if force:
        module_window._hub_window_bound = False
    if getattr(module_window, "_hub_window_bound", False):
        return
    owner_hub = getattr(module_window, "_hub_window", None) or hub_window
    if hasattr(owner_hub, "is_module_dock_minimized") and owner_hub.is_module_dock_minimized(
        module_window
    ):
        return
    try:
        module_window.createWinId()
        hub_window.createWinId()
        module_handle = module_window.windowHandle()
        hub_handle = hub_window.windowHandle()
        if module_handle is not None and hub_handle is not None:
            module_handle.setTransientParent(hub_handle)
    except Exception as error:
        print(f"[WINDOW] Qt transient-parent bind failed: {error}")

    if sys.platform != "win32":
        module_window._hub_window_bound = True
        return
    try:
        module_hwnd = int(module_window.winId())
        hub_hwnd = int(hub_window.winId())
        if not module_hwnd or not hub_hwnd:
            return
        import ctypes

        GWLP_HWNDPARENT = -8
        ctypes.windll.user32.SetWindowLongPtrW(module_hwnd, GWLP_HWNDPARENT, hub_hwnd)
        _apply_windows_owned_window_taskbar_style(module_hwnd)
        module_window._hub_window_bound = True
    except Exception as error:
        print(f"[WINDOW] Win32 hub ownership bind failed: {error}")


def _apply_windows_owned_window_taskbar_style(module_hwnd: int) -> None:
    """Keep hub-owned module shells grouped under the main app without tool-window chrome."""
    if sys.platform != "win32" or not module_hwnd:
        return
    try:
        import ctypes

        gwl_exstyle = -20
        ws_ex_appwindow = 0x00040000
        ws_ex_toolwindow = 0x00000080
        swp_nomove = 0x0002
        swp_nosize = 0x0001
        swp_nozorder = 0x0004
        swp_noactivate = 0x0010
        swp_framechanged = 0x0020
        user32 = ctypes.windll.user32
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            long_ptr = ctypes.c_longlong
        else:
            long_ptr = ctypes.c_long
        user32.GetWindowLongPtrW.restype = long_ptr
        user32.SetWindowLongPtrW.restype = long_ptr
        ex_style = int(user32.GetWindowLongPtrW(module_hwnd, gwl_exstyle))
        # Owned child windows: drop APPWINDOW so they group with the hub. Never set
        # TOOLWINDOW — that removes minimize/maximize from the native title bar.
        new_style = (ex_style & ~ws_ex_appwindow) & ~ws_ex_toolwindow
        user32.SetWindowLongPtrW(module_hwnd, gwl_exstyle, new_style)
        user32.SetWindowPos(
            module_hwnd,
            0,
            0,
            0,
            0,
            0,
            swp_nomove | swp_nosize | swp_nozorder | swp_noactivate | swp_framechanged,
        )
    except Exception as error:
        print(f"[WINDOW] Win32 taskbar style update failed: {error}")


def force_bind_module_window_to_hub(module_window: QWidget, hub_window: QWidget) -> None:
    """Re-apply hub ownership and Windows taskbar grouping after show or flag changes."""
    bind_module_window_to_hub(module_window, hub_window, force=True)


def unbind_module_window_from_hub(module_window: QWidget) -> None:
    """Detach a module shell so Windows does not restore it with the hub taskbar icon."""
    if module_window is None:
        return
    module_window._hub_bind_generation = getattr(module_window, "_hub_bind_generation", 0) + 1
    module_window._hub_window_bound = False
    try:
        module_handle = module_window.windowHandle()
        if module_handle is not None:
            module_handle.setTransientParent(None)
    except Exception as error:
        print(f"[WINDOW] Qt transient-parent unbind failed: {error}")

    if sys.platform != "win32":
        return
    try:
        module_hwnd = int(module_window.winId())
        if not module_hwnd:
            return
        import ctypes

        GWLP_HWNDPARENT = -8
        ctypes.windll.user32.SetWindowLongPtrW(module_hwnd, GWLP_HWNDPARENT, 0)
        ctypes.windll.user32.ShowWindow(module_hwnd, 0)
    except Exception as error:
        print(f"[WINDOW] Win32 hub ownership unbind failed: {error}")


def schedule_bind_module_window_to_hub(
    module_window: QWidget,
    hub_window: QWidget,
) -> None:
    """Bind a module window to the hub once its native handle exists."""
    if module_window is None or hub_window is None:
        return
    if getattr(module_window, "_hub_window_bound", False):
        return
    owner_hub = getattr(module_window, "_hub_window", None) or hub_window
    if hasattr(owner_hub, "is_module_dock_minimized") and owner_hub.is_module_dock_minimized(
        module_window
    ):
        return

    bind_generation = getattr(module_window, "_hub_bind_generation", 0) + 1
    module_window._hub_bind_generation = bind_generation

    def _bind_when_ready(force: bool = False) -> None:
        if getattr(module_window, "_hub_bind_generation", 0) != bind_generation:
            return
        if getattr(module_window, "_hub_window_bound", False) and not force:
            return
        if hasattr(owner_hub, "is_module_dock_minimized") and owner_hub.is_module_dock_minimized(
            module_window
        ):
            return
        bind_module_window_to_hub(module_window, hub_window, force=force)

    QTimer.singleShot(0, lambda: _bind_when_ready(False))
    QTimer.singleShot(100, lambda: _bind_when_ready(True))
    QTimer.singleShot(300, lambda: _bind_when_ready(True))


def clear_all_ui_memory(*, settings: QSettings | None = None) -> int:
    """Remove all persisted UI layout keys and return the number removed."""
    store = settings or create_ui_settings()
    removed = 0
    try:
        for key in list(store.allKeys()):
            if is_ui_memory_settings_key(key):
                store.remove(key)
                removed += 1
        store.sync()
    except Exception as error:
        print(f"[UI MEMORY] Clear failed: {error}")
    return removed


def prompt_restore_default_ui_layouts(parent: QWidget | None = None) -> int | None:
    """
    Confirm with the user, clear all UI memory, and report the result.

    Returns the number of removed keys, or None when the user cancels.
    """
    from PySide6.QtWidgets import QMessageBox

    from ui.message_boxes import information as themed_information
    from ui.message_boxes import question as themed_question

    reply = themed_question(
        parent,
        "Reset Layouts",
        "This will reset all saved window sizes, positions, and table column widths "
        "back to their factory defaults.\n\nContinue?",
    )
    if reply != QMessageBox.Yes:
        return None

    try:
        removed_count = clear_all_ui_memory()
        themed_information(
            parent,
            "Layouts Restored",
            f"Reset complete. Removed {removed_count} saved layout item(s).\n\n"
            "Reopen module windows to apply the default sizes and column widths.",
        )
        return removed_count
    except Exception as error:
        print(f"[UI MEMORY] Restore prompt failed: {error}")
        QMessageBox.warning(
            parent,
            "Restore Failed",
            "Could not restore default layouts. Please try again.",
        )
        return None


def is_floating_window(widget: QWidget) -> bool:
    """Return True only for widgets that are real top-level windows."""
    if widget is None:
        return False
    if getattr(widget, "_ui_memory_geometry_key", None) and isinstance(
        widget, (QMainWindow, QDialog)
    ):
        return True
    if not widget.isWindow():
        return False
    if isinstance(widget, QMainWindow):
        return True
    return bool(widget.windowFlags() & Qt.WindowType.Window)


def is_fixed_size_dialog(widget: QWidget) -> bool:
    """Return True when a dialog is locked to a single non-resizable size."""
    if not isinstance(widget, QDialog):
        return False
    min_size = widget.minimumSize()
    max_size = widget.maximumSize()
    if max_size.width() >= 10000 or max_size.height() >= 10000:
        return False
    return (
        min_size.width() == max_size.width()
        and min_size.height() == max_size.height()
        and min_size.width() > 0
        and min_size.height() > 0
    )


def should_apply_standard_window_chrome(widget: QWidget) -> bool:
    """Return True when a top-level window should expose min/max/close buttons."""
    if widget is None:
        return False
    if isinstance(widget, QMainWindow):
        return True
    if not isinstance(widget, QDialog):
        return False
    if type(widget).__name__ in {"LoginWindow"}:
        return False
    if is_fixed_size_dialog(widget):
        return False
    return True


def configure_non_modal_window(window: QWidget, hub_window: QWidget | None = None) -> None:
    """Keep secondary pages non-modal; each window minimizes independently."""
    if window is None:
        return
    if hasattr(window, "setModal"):
        window.setModal(False)
    window.setWindowModality(Qt.WindowModality.NonModal)
    if hub_window is not None:
        window._hub_window = hub_window
        from ui.hub_dockable_window import detach_hub_module_from_qt_parent

        detach_hub_module_from_qt_parent(window, hub_window)


def apply_module_window_chrome(
    module_window: QWidget,
    hub_window: QWidget | None = None,
) -> None:
    """Apply full window chrome once; repeated calls only refresh hub binding."""
    if module_window is None:
        return
    if getattr(module_window, "_module_window_chrome_applied", False):
        return

    flags = (
        Qt.WindowType.Window
        | Qt.WindowType.WindowSystemMenuHint
        | Qt.WindowType.WindowMinimizeButtonHint
        | Qt.WindowType.WindowMaximizeButtonHint
        | Qt.WindowType.WindowCloseButtonHint
    )
    was_visible = module_window.isVisible()
    modality = module_window.windowModality()
    module_window.setWindowFlags(flags)
    module_window.setWindowModality(modality)
    module_window._module_window_chrome_applied = True
    if was_visible:
        module_window.show()
        module_window.raise_()
    resolved_hub = hub_window or getattr(module_window, "_hub_window", None)
    if resolved_hub is not None:
        schedule_bind_module_window_to_hub(module_window, resolved_hub)


def apply_standard_window_chrome(
    widget: QWidget,
    *,
    allow_minimize: bool = True,
    allow_maximize: bool = True,
) -> None:
    """Apply native minimize, maximize, and close buttons to a top-level window."""
    if not should_apply_standard_window_chrome(widget):
        return
    if type(widget).__name__ == "StandaloneModuleWindow":
        apply_module_window_chrome(widget, widget.parent())
        return

    flags = (
        Qt.WindowType.Window
        | Qt.WindowType.WindowSystemMenuHint
        | Qt.WindowType.WindowCloseButtonHint
    )
    if allow_minimize:
        flags |= Qt.WindowType.WindowMinimizeButtonHint
    if allow_maximize:
        flags |= Qt.WindowType.WindowMaximizeButtonHint

    was_visible = widget.isVisible()
    modality = widget.windowModality()
    widget.setWindowFlags(flags)
    widget.setWindowModality(modality)
    if allow_minimize and allow_maximize:
        widget._module_window_chrome_applied = True
    if was_visible:
        widget.show()
        widget.raise_()


def focus_floating_window(window: QWidget) -> None:
    """Raise a floating window for explicit user navigation without altering minimized state."""
    if window is None:
        return
    try:
        if window.isMinimized():
            window.showMinimized()
        else:
            window.show()
        window.raise_()
        window.activateWindow()
    except RuntimeError:
        pass


class UiMemoryMixin:
    """
    Mixin that restores and saves window geometry and table column layouts.

    Call ``_init_ui_memory()`` at the end of ``__init__`` after the UI is built.
    """

    _ui_memory_table_attrs: tuple[str, ...] | None = None
    _ui_memory_restore_geometry: bool | None = None
    _ui_memory_save_geometry: bool | None = None

    def _init_ui_memory(
        self,
        *,
        restore_geometry: bool | None = None,
        save_geometry: bool | None = None,
        table_attrs: tuple[str, ...] | None = None,
    ) -> None:
        """Initialize QSettings and restore persisted UI state."""
        try:
            if type(self).__name__ != "StandaloneModuleWindow":
                apply_standard_window_chrome(self)
            self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

            if table_attrs is not None:
                self._ui_memory_table_attrs = table_attrs

            if restore_geometry is None:
                restore_geometry = (
                    self._ui_memory_restore_geometry
                    if self._ui_memory_restore_geometry is not None
                    else is_floating_window(self)
                )
            if save_geometry is None:
                save_geometry = (
                    self._ui_memory_save_geometry
                    if self._ui_memory_save_geometry is not None
                    else is_floating_window(self)
                )

            self._ui_memory_save_geometry_flag = bool(save_geometry)

            if restore_geometry:
                restore_window_geometry(self, settings=self.settings)
                schedule_clamp_window_to_available_screen(self)
            self._restore_table_headers()
            self._connect_table_header_persistence()
            self._connect_geometry_persistence()
        except Exception as error:
            print(f"[UI MEMORY] Restore skipped for {self.__class__.__name__}: {error}")

    def _connect_geometry_persistence(self) -> None:
        """Debounce-save floating window geometry while the user resizes it."""
        if not getattr(self, "_ui_memory_save_geometry_flag", False):
            return
        if not is_floating_window(self):
            return
        if getattr(self, "_ui_memory_geometry_timer", None) is not None:
            return

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(350)
        timer.timeout.connect(self._persist_window_geometry_only)
        self._ui_memory_geometry_timer = timer

    def _connect_table_header_persistence(self) -> None:
        """Debounce-save table column widths when the user drags header dividers."""
        if getattr(self, "_ui_memory_header_timer", None) is not None:
            return

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(350)
        timer.timeout.connect(self._save_table_headers)
        self._ui_memory_header_timer = timer

        for _attr, table in self._iter_memory_tables():
            header = table.horizontalHeader()
            header.sectionResized.connect(lambda *_args, t=timer: t.start())

    def _iter_memory_tables(self) -> Iterable[tuple[str, QTableWidget]]:
        """Yield (attribute_name, table) pairs configured for persistence."""
        attrs = self._ui_memory_table_attrs
        if attrs is None:
            attrs = discover_table_widget_attrs(self)
        for attr in attrs:
            table = getattr(self, attr, None)
            if isinstance(table, QTableWidget):
                yield attr, table

    def _restore_table_headers(self) -> None:
        """Restore all configured table header states."""
        for attr, table in self._iter_memory_tables():
            restore_table_header_state(
                self,
                table,
                settings=self.settings,
                table_attr=attr,
            )

    def _restore_memory_table(self, table: QTableWidget, table_attr: str) -> None:
        """Restore one table layout after columns and headers are available."""
        if table is None or table.columnCount() <= 0:
            return
        if not hasattr(self, "settings"):
            self.settings = create_ui_settings()
        restore_table_header_state(
            self,
            table,
            settings=self.settings,
            table_attr=table_attr,
        )
        self._ui_memory_active_table_attr = table_attr
        self._ui_memory_active_table = table

    def _save_table_headers(self) -> None:
        """Save all configured table header states."""
        active_attr = getattr(self, "_ui_memory_active_table_attr", None)
        active_table = getattr(self, "_ui_memory_active_table", None)
        if (
            active_attr
            and isinstance(active_table, QTableWidget)
            and active_table.columnCount() > 0
        ):
            save_table_header_state(
                self,
                active_table,
                settings=self.settings,
                table_attr=active_attr,
            )
            return
        for attr, table in self._iter_memory_tables():
            save_table_header_state(
                self,
                table,
                settings=self.settings,
                table_attr=attr,
            )

    def _persist_window_geometry_only(self) -> None:
        """Persist only window geometry (used by debounced resize handling)."""
        try:
            if getattr(self, "_ui_memory_save_geometry_flag", False) and is_floating_window(self):
                save_window_geometry(self, settings=getattr(self, "settings", None))
        except Exception as error:
            print(f"[UI MEMORY] Geometry save skipped for {self.__class__.__name__}: {error}")

    def _persist_ui_memory(self) -> None:
        """Save geometry and table layouts before the widget is hidden or closed."""
        try:
            self._persist_window_geometry_only()
            if hasattr(self, "settings"):
                self._save_table_headers()
        except Exception as error:
            print(f"[UI MEMORY] Save skipped for {self.__class__.__name__}: {error}")

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Persist geometry while the user resizes a floating window."""
        timer = getattr(self, "_ui_memory_geometry_timer", None)
        if timer is not None and getattr(self, "_ui_memory_save_geometry_flag", False):
            timer.start()
        super().resizeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Keep restored windows inside the visible desktop work area."""
        super().showEvent(event)
        if is_floating_window(self) and not self.isMaximized() and not self.isFullScreen():
            schedule_clamp_window_to_available_screen(self)

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Re-clamp when a window is restored from maximized/full-screen."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if is_floating_window(self) and not self.isMaximized() and not self.isFullScreen():
                schedule_clamp_window_to_available_screen(self)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Persist UI state when the widget is hidden."""
        self._persist_ui_memory()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Persist UI state when the widget is closed."""
        self._persist_ui_memory()
        super().closeEvent(event)


def memory_table_attr_slug(value: str) -> str:
    """Build a stable table-memory suffix from a report or layout label."""
    cleaned = (value or "").strip()
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", cleaned).strip("_").lower()
    return cleaned or "default"


class MemoryHostedDialog(UiMemoryMixin, QDialog):
    """Top-level dialog shell that persists window geometry for hosted pages."""

    def __init__(
        self,
        content: QWidget,
        *,
        title: str,
        memory_key: str,
        parent: QWidget | None = None,
        minimum_size: tuple[int, int] = (860, 720),
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._ui_memory_geometry_key = memory_key
        self.setWindowTitle(title)
        self.setMinimumSize(*minimum_size)
        from PySide6.QtWidgets import QVBoxLayout
        from ui.book_report_common import report_dialog_body_style

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content)
        self.setStyleSheet(report_dialog_body_style())
        apply_standard_window_chrome(self)
        configure_non_modal_window(self, parent)
        self._init_ui_memory(restore_geometry=True, save_geometry=True, table_attrs=())

    def refresh_theme(self) -> None:
        """Re-apply dialog shell styles and refresh the hosted page widget."""
        from ui.book_report_common import report_dialog_body_style

        self.setStyleSheet(report_dialog_body_style())
        layout = self.layout()
        if layout is None or layout.count() <= 0:
            return
        content = layout.itemAt(0).widget()
        if content is not None and hasattr(content, "refresh_theme"):
            content.refresh_theme()