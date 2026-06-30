"""
MDI-style minimized module strip shown along the bottom of the main hub window.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from ui.theme_manager import get_theme_manager


class ModuleMinimizeStrip(QFrame):
    """Horizontal strip of restore buttons for dock-minimized module windows."""

    restore_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("moduleMinimizeStrip")
        self._buttons: dict[int, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        self._layout = layout

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setFixedHeight(34)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """Apply theme colors to the minimized-module strip."""
        theme_manager = get_theme_manager()
        colors = theme_manager.get_colors()
        is_dark = theme_manager.get_current_theme() == "dark"
        if is_dark:
            strip_bg = colors.get("nav_item_hover_bg", "#1f2937")
            button_bg = colors.get("input_bg", "#2D2D2D")
            button_border = colors.get("border", "#505050")
        else:
            strip_bg = colors.get("panel_bg", colors["card_bg"])
            button_bg = colors.get("surface_alt", colors.get("input_bg", strip_bg))
            button_border = colors.get("border", "#cccccc")
        hover_bg = colors.get("focus_border", colors.get("button_primary", "#2196F3"))
        text_color = colors.get("input_text", "#ffffff")
        self.setStyleSheet(
            f"""
            QFrame#moduleMinimizeStrip {{
                background-color: {strip_bg};
                border-top: 1px solid {button_border};
            }}
            QPushButton#moduleMinimizeButton {{
                background-color: {button_bg};
                color: {text_color};
                border: 1px solid {button_border};
                border-radius: 3px;
                padding: 2px 10px;
                font-size: 11px;
                min-height: 22px;
                max-height: 22px;
            }}
            QPushButton#moduleMinimizeButton:hover {{
                background-color: {hover_bg};
                color: #ffffff;
                border: 1px solid {hover_bg};
            }}
            """
        )

    def sync_entries(self, entries: list[tuple[QWidget, str]]) -> None:
        """Rebuild strip buttons to match the current dock-minimized module list."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._buttons.clear()

        for window, title in entries:
            window_id = id(window)
            label = (title or "Module").strip() or "Module"
            button = QPushButton(label, self)
            button.setObjectName("moduleMinimizeButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(
                QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Fixed,
            )
            button.clicked.connect(
                lambda _checked=False, module=window: self.restore_requested.emit(module)
            )
            self._buttons[window_id] = button
            self._layout.addWidget(button)

        self._layout.addStretch(1)
