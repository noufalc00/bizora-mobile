"""
Secondary 3D-style shortcut toolbar mounted directly under the application
header.

Icons are loaded from SVG assets using the same ``load_menu_icon`` helper as
the sidebar main-menu headers, then attached with ``QPushButton.setIcon`` after
the layout is built (deferred via ``QTimer.singleShot``).
"""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton

from components.global_search_bar import GlobalSearchBar
from components.menu_icons import pixmap_for_menu_icon


SHORTCUT_BUTTONS: tuple[tuple[str, str], ...] = (
    ("Sales", "assets/icons/shortcuts/sales.svg"),
    ("Sales Return", "assets/icons/shortcuts/sales_return.svg"),
    ("Purchase", "assets/icons/shortcuts/purchase.svg"),
    ("Cash Receipt", "assets/icons/shortcuts/cash_receipt.svg"),
    ("Bank Receipt", "assets/icons/shortcuts/bank_receipt.svg"),
    ("Cash Payment", "assets/icons/shortcuts/cash_payment.svg"),
    ("Bank Payment", "assets/icons/shortcuts/bank_payment.svg"),
    ("Day Book", "assets/icons/shortcuts/day_book.svg"),
    ("Cash Book", "assets/icons/shortcuts/cash_book.svg"),
    ("Ledger", "assets/icons/shortcuts/ledger.svg"),
)

_BUTTON_WIDTH = 48
_BUTTON_HEIGHT = 42
_ICON_SIZE = QSize(36, 36)


class ShortcutToolbar(QFrame):
    """Compact, theme-aware shortcut bar that sits below the main topbar."""

    shortcut_activated = Signal(str)
    search_requested = Signal(str)

    def __init__(self, parent=None):
        """Build the toolbar layout, buttons, and apply the initial theme."""
        super().__init__(parent)

        self.setObjectName("shortcutToolbar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(56)

        self._buttons: dict[str, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        for route_name, icon_path in SHORTCUT_BUTTONS:
            button = self._build_button(route_name, icon_path)
            self._buttons[route_name] = button
            layout.addWidget(button)

        layout.addSpacing(10)

        self.global_search_bar = GlobalSearchBar(self)
        self.global_search_bar.search_requested.connect(self._emit_search_requested)
        layout.addWidget(self.global_search_bar, 1)

        self.refresh_theme()
        QTimer.singleShot(0, self._apply_shortcut_icons)

    def _build_button(self, route_name: str, icon_path: str) -> QPushButton:
        """Create a single icon-only shortcut button bound to ``route_name``."""
        button = QPushButton("", self)
        button.setObjectName("shortcutIconButton")
        button.icon_path = icon_path
        button.route_name = route_name
        button.setToolTip(route_name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(_BUTTON_WIDTH, _BUTTON_HEIGHT)
        button.setIconSize(_ICON_SIZE)
        button.setFlat(False)
        button.clicked.connect(
            lambda _checked=False, name=route_name: self._emit_route(name)
        )
        return button

    def _apply_shortcut_icons(self) -> None:
        """Attach cached SVG icons scaled to fill each shortcut button."""
        for button in self._buttons.values():
            icon_path = getattr(button, "icon_path", "")
            pixmap = pixmap_for_menu_icon(
                icon_path,
                _ICON_SIZE,
                device_pixel_ratio=button.devicePixelRatioF(),
                bust_cache=True,
            )
            if pixmap is None:
                continue
            button.setIcon(QIcon(pixmap))

    def _button_stylesheet(self) -> str:
        """Return the per-button 3D stylesheet."""
        try:
            from ui.theme import shortcut_toolbar_3d_icon_button_style

            return shortcut_toolbar_3d_icon_button_style()
        except Exception as exc:
            print(f"[WARN] ShortcutToolbar 3D style lookup failed: {exc}")
            return ""

    def _apply_button_styles(self) -> None:
        """Apply 3D QSS directly on each button, matching the sidebar pattern."""
        button_style = self._button_stylesheet()
        for button in self._buttons.values():
            button.setStyleSheet(button_style)
        self.setStyleSheet(self._build_frame_stylesheet())

    def showEvent(self, event):
        """Ensure SVG icons are attached the first time the bar is shown."""
        super().showEvent(event)
        if any(button.icon().isNull() for button in self._buttons.values()):
            QTimer.singleShot(0, self._apply_shortcut_icons)

    def _emit_search_requested(self, search_text: str) -> None:
        """Forward topbar-style search requests to the main window."""
        try:
            self.search_requested.emit(search_text)
        except Exception as exc:
            print(f"[WARN] ShortcutToolbar search emit failed: {exc}")

    def focus_search_field(self) -> None:
        """Focus the global search field on the shortcut row."""
        search_bar = getattr(self, "global_search_bar", None)
        if search_bar is not None and hasattr(search_bar, "focus_search_field"):
            search_bar.focus_search_field()

    def _emit_route(self, route_name: str) -> None:
        """Emit ``shortcut_activated`` for the supplied route name."""
        try:
            self.shortcut_activated.emit(route_name)
        except Exception as exc:
            print(
                f"[WARN] ShortcutToolbar emit failed for "
                f"'{route_name}': {exc}"
            )

    def _current_theme_name(self) -> str:
        """Return the active theme name, defaulting to ``dark`` on failure."""
        try:
            from ui.theme_manager import get_theme_manager

            return get_theme_manager().get_current_theme() or "dark"
        except Exception as exc:
            print(f"[WARN] ShortcutToolbar could not read theme: {exc}")
            return "dark"

    def _theme_palette(self) -> dict[str, str]:
        """Return frame-level colors for the shortcut toolbar host."""
        theme_name = self._current_theme_name()
        try:
            from utils.theme_manager import global_theme_manager

            base_colors = global_theme_manager.get_colors(theme_name)
        except Exception as exc:
            print(f"[WARN] ShortcutToolbar palette lookup failed: {exc}")
            base_colors = {
                "panel_bg": "#1E1E1E",
                "border": "#404040",
            }

        return {
            "frame_bg": base_colors.get("panel_bg", "#1E1E1E"),
            "border": base_colors.get("border", "#404040"),
        }

    def _build_frame_stylesheet(self) -> str:
        """Return QSS for the toolbar host frame only."""
        palette = self._theme_palette()
        return f"""
            QFrame#shortcutToolbar {{
                background-color: {palette['frame_bg']};
                border: none;
                border-bottom: 1px solid {palette['border']};
            }}
        """

    def refresh_theme(self) -> None:
        """Re-apply stylesheet and re-attach SVG icons for the active theme."""
        try:
            self._apply_button_styles()
        except Exception as exc:
            print(f"[WARN] ShortcutToolbar stylesheet refresh failed: {exc}")

        self._apply_shortcut_icons()

        search_bar = getattr(self, "global_search_bar", None)
        if search_bar is not None and hasattr(search_bar, "refresh_theme"):
            search_bar.refresh_theme()

    def apply_permissions(self, allowed_routes: Iterable[str]) -> None:
        """Hide any button whose route is not present in ``allowed_routes``."""
        if allowed_routes is None:
            for button in self._buttons.values():
                button.setVisible(True)
            return

        try:
            allowed_set = {str(route) for route in allowed_routes}
        except Exception as exc:
            print(f"[WARN] ShortcutToolbar permission set invalid: {exc}")
            return

        for route_name, button in self._buttons.items():
            button.setVisible(route_name in allowed_set)
