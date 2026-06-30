"""
Standalone window that lists all routes for one sidebar section.

Opened when the user searches a section name (for example, "Settings") from the
topbar and needs to pick a sub-menu item.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from bizora_core.navigation_catalog import routes_for_section
from ui.keyboard_shortcuts import format_route_button_text
from ui.qt_pump import pump_ui_events
from ui.scrollbar_style import scrollbar_stylesheet
from ui.theme import sidebar_route_button_style
from ui.theme_manager import get_theme_manager


class GlobalSearchSectionWidget(QWidget):
    """Scrollable list of routes belonging to one navigation section."""

    route_selected = Signal(str)

    def __init__(self, section_name: str, allowed_routes: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.section_name = section_name
        self.allowed_routes = allowed_routes
        self._build_ui()

    def _theme_colors(self) -> dict[str, str]:
        return get_theme_manager().get_colors()

    def _build_ui(self) -> None:
        colors = self._theme_colors()
        self.setObjectName("globalSearchSectionWidget")
        self.setStyleSheet(f"""
            QWidget#globalSearchSectionWidget {{
                background-color: {colors['page_bg']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel(self.section_name)
        title.setStyleSheet(f"""
            QLabel {{
                color: {colors['heading_text']};
                font-size: 22px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(title)

        subtitle = QLabel("Choose a menu item below to open it.")
        subtitle.setStyleSheet(f"""
            QLabel {{
                color: {colors['muted_text']};
                font-size: 13px;
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(subtitle)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            {scrollbar_stylesheet()}
        """)

        list_host = QFrame()
        list_host.setStyleSheet("QFrame { background: transparent; border: none; }")
        list_layout = QVBoxLayout(list_host)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(4)

        route_names = routes_for_section(self.section_name)
        if self.allowed_routes is not None:
            allowed = set(self.allowed_routes)
            route_names = [route for route in route_names if route in allowed]

        for route_name in route_names:
            button = QPushButton(format_route_button_text(route_name, route_name))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(sidebar_route_button_style())
            button.clicked.connect(
                lambda _checked=False, name=route_name: self.route_selected.emit(name)
            )
            list_layout.addWidget(button)
            pump_ui_events()

        list_layout.addStretch()
        scroll_area.setWidget(list_host)
        layout.addWidget(scroll_area, 1)