"""
Application-wide theme coordinator.

Delegates QSS generation and master-database persistence to
``utils.theme_manager.ThemeManager``.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from db import BASE_DIR, get_default_database_path
from utils.theme_manager import ThemeManager as GlobalThemeManager


class ThemeManager:
    """Runtime theme state with widget helper styles."""

    VALID_THEMES = GlobalThemeManager.VALID_THEMES

    def __init__(self):
        self._current_theme = GlobalThemeManager.DEFAULT_THEME
        self._master_db_path = self._resolve_master_db_path(None)
        self._load_theme_setting()

    def set_master_db_path(self, master_db_path: str | None) -> None:
        """Point persistence at the master registry database."""
        resolved = self._resolve_master_db_path(master_db_path)
        if resolved != self._master_db_path:
            self._master_db_path = resolved
            self._load_theme_setting()

    def get_current_theme(self) -> str:
        return self._current_theme

    def sync_theme(self, theme_name: str | None = None) -> None:
        """Refresh in-memory theme state from the DB or an explicit value."""
        if theme_name is not None:
            normalized = str(theme_name).strip().lower()
            if normalized in self.VALID_THEMES:
                self._current_theme = normalized
                return

        self._load_theme_setting()

    def set_theme(self, theme_name: str) -> bool:
        normalized = str(theme_name or "").strip().lower()
        if normalized not in self.VALID_THEMES:
            print(f"Invalid theme name: {theme_name}")
            return False

        self._current_theme = normalized
        return self._save_theme_setting()

    def get_colors(self, theme_name: Optional[str] = None) -> Dict[str, str]:
        if theme_name is None:
            theme_name = self._current_theme
        return GlobalThemeManager.get_colors(theme_name)

    def get_icon_color(self, theme_name: Optional[str] = None) -> str:
        if theme_name is None:
            theme_name = self._current_theme
        return GlobalThemeManager.get_icon_color(theme_name)

    def app_stylesheet(self) -> str:
        from utils.theme_manager import global_theme_manager

        return GlobalThemeManager.build_application_stylesheet(
            self._current_theme,
            bold_fonts=global_theme_manager.get_effective_bold_fonts(self._master_db_path),
        )

    def widget_stylesheet(self) -> str:
        colors = self.get_colors()
        return f"""
            QWidget {{
                background-color: {colors['panel_bg']};
                color: {colors['input_text']};
            }}
        """

    def input_style(self) -> str:
        colors = self.get_colors()
        return f"""
            QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {{
                background-color: {colors['input_bg']};
                color: {colors['input_text']};
                border: 1px solid {colors['border']};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border: 1px solid {colors['focus_border']};
                outline: none;
            }}
            QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled {{
                background-color: {colors['app_bg']};
                color: {colors['label_text']};
            }}
        """

    def combo_style(self) -> str:
        colors = self.get_colors()
        return f"""
            QComboBox {{
                background-color: {colors['input_bg']};
                color: {colors['input_text']};
                border: 1px solid {colors['border']};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QComboBox:focus {{
                border: 1px solid {colors['focus_border']};
                outline: none;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['panel_bg']};
                color: {colors['input_text']};
                selection-background-color: {colors['focus_border']};
                selection-color: {self.get_icon_color()};
                border: 1px solid {colors['border']};
            }}
        """

    def button_style(self, kind: str = "primary") -> str:
        colors = self.get_colors()
        button_colors = {
            "primary": colors["button_primary"],
            "success": colors["button_success"],
            "danger": colors["button_danger"],
            "warning": colors["button_warning"],
            "secondary": colors["border"],
        }
        bg_color = button_colors.get(kind, colors["button_primary"])
        primary_text = "#FFFFFF" if self._current_theme == "light" else "white"

        if kind == "secondary":
            return f"""
                QPushButton {{
                    background-color: {colors['panel_bg']};
                    color: {colors['input_text']};
                    border: 1px solid {colors['border']};
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 4px 8px;
                }}
                QPushButton:hover {{
                    background-color: {colors['border']};
                }}
                QPushButton:pressed {{
                    background-color: {colors['app_bg']};
                }}
            """

        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: {primary_text};
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {self._darken_color(bg_color, 10)};
            }}
            QPushButton:pressed {{
                background-color: {self._darken_color(bg_color, 20)};
            }}
        """

    def table_style(self) -> str:
        colors = self.get_colors()
        selection_text = colors["input_text"] if self._current_theme == "light" else "white"
        return f"""
            QTableWidget {{
                background-color: {colors['table_bg']};
                color: {colors['table_text']};
                gridline-color: {colors['border']};
                border: 1px solid {colors['border']};
                border-radius: 4px;
                selection-background-color: {colors['focus_border'] if self._current_theme == 'dark' else '#BBDEFB'};
                selection-color: {selection_text};
            }}
            QTableWidget::item {{
                padding: 6px;
                border-bottom: 1px solid {colors['border']};
            }}
            QTableWidget::item:selected {{
                background-color: {colors['focus_border'] if self._current_theme == 'dark' else '#BBDEFB'};
                color: {selection_text};
            }}
            QHeaderView::section {{
                background-color: {colors['table_header_bg']};
                color: {colors['heading_text']};
                padding: 8px;
                border: none;
                border-right: 1px solid {colors['border']};
                border-bottom: 1px solid {colors['border']};
                font-weight: bold;
                font-size: 12px;
            }}
            QTableWidget::item:alternate {{
                background-color: {self._adjust_color(colors['table_bg'], 5 if self._current_theme == 'dark' else -2)};
            }}
        """

    def label_style(self) -> str:
        colors = self.get_colors()
        return f"""
            QLabel {{
                color: {colors['label_text']};
                font-size: 12px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 2px 0px;
            }}
        """

    def card_style(self) -> str:
        colors = self.get_colors()
        return f"""
            QFrame {{
                background-color: {colors['card_bg']};
                border: 1px solid {colors['border']};
                border-radius: 8px;
                padding: 8px;
            }}
        """

    def _resolve_master_db_path(self, master_db_path: str | None) -> str:
        configured_path = master_db_path or get_default_database_path()
        if not os.path.isabs(configured_path):
            configured_path = os.path.join(BASE_DIR, configured_path)
        return os.path.abspath(configured_path)

    def _load_theme_setting(self) -> None:
        self._current_theme = GlobalThemeManager.get_theme_preference(self._master_db_path)

    def _save_theme_setting(self) -> bool:
        return GlobalThemeManager.save_theme_preference(
            self._master_db_path,
            self._current_theme,
        )

    def _darken_color(self, hex_color: str, percent: int) -> str:
        hex_color = hex_color.lstrip("#")
        rgb = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
        factor = 1 - (percent / 100)
        rgb = tuple(int(c * factor) for c in rgb)
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _adjust_color(self, hex_color: str, percent: int) -> str:
        hex_color = hex_color.lstrip("#")
        rgb = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
        if percent >= 0:
            rgb = tuple(min(255, int(c * (1 + percent / 100))) for c in rgb)
        else:
            rgb = tuple(max(0, int(c * (1 + percent / 100))) for c in rgb)
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


_theme_manager_instance: ThemeManager | None = None


def get_theme_manager(master_db_path: str | None = None) -> ThemeManager:
    global _theme_manager_instance
    if _theme_manager_instance is None:
        _theme_manager_instance = ThemeManager()
    if master_db_path:
        _theme_manager_instance.set_master_db_path(master_db_path)
    return _theme_manager_instance


def get_current_theme() -> str:
    return get_theme_manager().get_current_theme()


def sync_theme(theme_name: str | None = None, master_db_path: str | None = None) -> None:
    """Synchronize the shared runtime theme manager with persisted preferences."""
    get_theme_manager(master_db_path).sync_theme(theme_name)


def set_theme(theme_name: str) -> bool:
    return get_theme_manager().set_theme(theme_name)


def get_colors(theme_name: Optional[str] = None) -> Dict[str, str]:
    return get_theme_manager().get_colors(theme_name)