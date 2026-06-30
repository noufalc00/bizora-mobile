"""
Global Theme Manager for the Accounting Desktop application.

Provides dark and colorful light theme QSS, icon color helpers, and
persistence via the master database ``global_settings`` table.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFont

from utils.color_tokens import COLOR_TOKENS, DEFAULT_THEME, VALID_THEMES, get_theme_colors

THEME_SETTING_KEY = "app_theme"
BOLD_FONTS_SETTING_KEY = "app_bold_fonts"


class ThemeManager(QObject):
    """Central theme definitions and master-database preference storage."""

    theme_changed = Signal(str)

    VALID_THEMES = VALID_THEMES
    DEFAULT_THEME = DEFAULT_THEME
    THEME_SETTING_KEY = THEME_SETTING_KEY
    BOLD_FONTS_SETTING_KEY = BOLD_FONTS_SETTING_KEY

    COLOR_TOKENS = COLOR_TOKENS

    def __init__(self, parent: QObject | None = None):
        """Initialize the global theme manager signal source."""
        super().__init__(parent)
        self._preview_theme: str | None = None
        self._preview_bold_fonts: bool | None = None

    def is_preview_active(self) -> bool:
        """Return True while Global Settings is previewing unsaved appearance."""
        return self._preview_theme is not None or self._preview_bold_fonts is not None

    def clear_preview(self) -> None:
        """Discard unsaved appearance preview state."""
        self._preview_theme = None
        self._preview_bold_fonts = None

    def get_effective_theme(self, master_db_path: str) -> str:
        """Return the live theme, including any unsaved preview selection."""
        if self._preview_theme is not None:
            return self._preview_theme
        return self.get_theme_preference(master_db_path)

    def get_effective_bold_fonts(self, master_db_path: str) -> bool:
        """Return the live bold-font mode, including any unsaved preview state."""
        if self._preview_bold_fonts is not None:
            return self._preview_bold_fonts
        return self.get_bold_fonts_preference(master_db_path)

    @staticmethod
    def apply_font_weight_to_app(app, bold_fonts: bool) -> None:
        """Apply bold/normal weight at the QApplication level for live updates."""
        if app is None:
            return
        try:
            current = app.font()
            updated = QFont(current)
            updated.setBold(bool(bold_fonts))
            updated.setWeight(
                QFont.Weight.Bold if bold_fonts else QFont.Weight.Normal
            )
            app.setFont(updated)
        except Exception as exc:
            print(f"Error applying application font weight: {exc}")

    @classmethod
    def get_theme_preference(cls, master_db_path: str) -> str:
        """Read the saved theme from ``global_settings``; default is ``dark``."""
        if not master_db_path or not os.path.isfile(master_db_path):
            return DEFAULT_THEME

        try:
            with closing(cls._connect(master_db_path)) as connection:
                cls._ensure_global_settings_table(connection)
                row = connection.execute(
                    """
                    SELECT setting_value
                    FROM global_settings
                    WHERE setting_key = ?
                    """,
                    (THEME_SETTING_KEY,),
                ).fetchone()
                if row:
                    theme_name = str(row[0] or "").strip().lower()
                    if theme_name in VALID_THEMES:
                        return theme_name
        except Exception as exc:
            print(f"Error loading theme preference: {exc}")

        return DEFAULT_THEME

    @classmethod
    def get_bold_fonts_preference(cls, master_db_path: str) -> bool:
        """Read whether global bold fonts are enabled from ``global_settings``."""
        if not master_db_path or not os.path.isfile(master_db_path):
            return False

        try:
            with closing(cls._connect(master_db_path)) as connection:
                cls._ensure_global_settings_table(connection)
                row = connection.execute(
                    """
                    SELECT setting_value
                    FROM global_settings
                    WHERE setting_key = ?
                    """,
                    (BOLD_FONTS_SETTING_KEY,),
                ).fetchone()
                if row:
                    return str(row[0] or "").strip().lower() in {"1", "true", "yes", "on"}
        except Exception as exc:
            print(f"Error loading bold-font preference: {exc}")

        return False

    @classmethod
    def save_bold_fonts_preference(cls, master_db_path: str, enabled: bool) -> bool:
        """Persist the global bold-font preference in ``global_settings``."""
        if not master_db_path:
            print("Master database path is required to save bold-font preference.")
            return False

        db_dir = os.path.dirname(os.path.abspath(master_db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        try:
            with closing(cls._connect(master_db_path)) as connection:
                cls._ensure_global_settings_table(connection)
                connection.execute(
                    """
                    INSERT INTO global_settings (setting_key, setting_value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(setting_key) DO UPDATE SET
                        setting_value = excluded.setting_value,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (BOLD_FONTS_SETTING_KEY, "1" if enabled else "0"),
                )
                connection.commit()
            return True
        except Exception as exc:
            print(f"Error saving bold-font preference: {exc}")
            return False

    @classmethod
    def save_theme_preference(cls, master_db_path: str, theme_name: str) -> bool:
        """Persist the theme choice in ``global_settings``."""
        normalized = str(theme_name or "").strip().lower()
        if normalized not in VALID_THEMES:
            print(f"Invalid theme name: {theme_name}")
            return False
        if not master_db_path:
            print("Master database path is required to save theme preference.")
            return False

        db_dir = os.path.dirname(os.path.abspath(master_db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        try:
            with closing(cls._connect(master_db_path)) as connection:
                cls._ensure_global_settings_table(connection)
                connection.execute(
                    """
                    INSERT INTO global_settings (setting_key, setting_value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(setting_key) DO UPDATE SET
                        setting_value = excluded.setting_value,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (THEME_SETTING_KEY, normalized),
                )
                connection.commit()
            return True
        except Exception as exc:
            print(f"Error saving theme preference: {exc}")
            return False

    @staticmethod
    def get_dark_theme_qss() -> str:
        """Return the comprehensive dark-theme QSS string."""
        qss_path = Path(__file__).resolve().parent.parent / "assets" / "styles" / "dark_theme.qss"
        try:
            base_qss = qss_path.read_text(encoding="utf-8")
        except OSError:
            base_qss = """
                QMainWindow, QDialog {
                    background-color: #121212;
                    color: #ffffff;
                }
                QWidget {
                    background-color: #121212;
                    color: #ffffff;
                }
            """

        from ui.checkbox_style import app_checkbox_style

        return f"""
            {base_qss}

            QMainWindow {{
                background-color: #121212;
                color: #ffffff;
            }}
            QDialog {{
                background-color: #1f1f1f;
                color: #ffffff;
            }}
            QGroupBox {{
                background-color: #1E1E1E;
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 8px;
                margin-top: 16px;
                padding: 18px 14px 14px 14px;
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0 6px;
            }}

            QLabel {{
                background-color: transparent;
                border: none;
            }}

            QMessageBox {{
                background-color: #1E1E1E;
                color: #ffffff;
            }}
            QMessageBox QLabel {{
                color: #ffffff;
                background: transparent;
                border: none;
            }}
            QMessageBox QPushButton {{
                background-color: #2196F3;
                color: #ffffff;
                border: none;
                padding: 6px 14px;
                border-radius: 4px;
                min-width: 72px;
                font-weight: bold;
            }}
            QMessageBox QPushButton:hover {{
                background-color: #1976D2;
            }}

            QFrame {{
                background-color: transparent;
                border: none;
            }}

            {ThemeManager._sidebar_navigation_qss(ThemeManager.COLOR_TOKENS["dark"])}

            {app_checkbox_style()}
        """

    @staticmethod
    def get_light_theme_qss() -> str:
        """Return a comprehensive, modern colorful light-theme QSS string."""
        from ui.checkbox_style import app_checkbox_style

        c = ThemeManager.COLOR_TOKENS["light"]
        return f"""
            QMainWindow, QDialog {{
                background-color: {c['app_bg']};
                color: {c['input_text']};
            }}

            QWidget {{
                background-color: transparent;
                color: {c['input_text']};
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 10pt;
            }}

            QLabel {{
                color: {c['label_text']};
                background-color: transparent;
                border: none;
            }}

            QFrame {{
                background-color: transparent;
                border: none;
            }}

            QGroupBox {{
                background-color: {c['panel_bg']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                margin-top: 16px;
                padding: 18px 14px 14px 14px;
                font-weight: bold;
                color: {c['input_text']};
            }}

            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0 6px;
                color: {c['accent_label']};
                background-color: transparent;
                border: none;
            }}

            QLabel:disabled {{
                color: {c['muted_text']};
            }}

            QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {{
                background-color: {c['input_bg']};
                color: {c['input_text']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                padding: 8px;
            }}

            QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {c['focus_border']};
            }}

            QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled {{
                background-color: {c['surface_alt']};
                color: {c['muted_text']};
            }}

            QTextEdit, QPlainTextEdit {{
                background-color: {c['input_bg']};
                color: {c['input_text']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                padding: 8px;
            }}

            QTextEdit:focus, QPlainTextEdit:focus {{
                border-color: {c['focus_border']};
            }}

            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border-left: 1px solid {c['border']};
                background-color: {c['input_bg']};
            }}

            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {c['label_text']};
                margin-right: 6px;
            }}

            QComboBox QAbstractItemView {{
                background-color: {c['input_bg']};
                color: {c['input_text']};
                border: 1px solid {c['border']};
                selection-background-color: {c['focus_border']};
                selection-color: #FFFFFF;
            }}

            QPushButton {{
                background-color: {c['panel_bg']};
                color: {c['input_text']};
                border: 1px solid {c['border']};
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 600;
            }}

            QPushButton:hover {{
                background-color: {c['surface_alt']};
                border-color: {c['focus_border']};
            }}

            QPushButton:pressed {{
                background-color: {c['card_bg']};
            }}

            QPushButton:disabled {{
                background-color: {c['surface_alt']};
                color: {c['muted_text']};
                border-color: {c['border']};
            }}

            QPushButton#primaryButton, QPushButton#actionButton {{
                background-color: {c['button_primary']};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
            }}

            QPushButton#primaryButton:hover, QPushButton#actionButton:hover {{
                background-color: {c['focus_border']};
            }}

            QPushButton#primaryButton:pressed, QPushButton#actionButton:pressed {{
                background-color: #0B5F6B;
            }}

            QTableWidget, QTableView {{
                background-color: {c['table_bg']};
                alternate-background-color: {c['card_bg']};
                color: {c['table_text']};
                gridline-color: {c['border']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                selection-background-color: {c['surface_alt']};
                selection-color: {c['input_text']};
            }}

            QTableWidget::item, QTableView::item {{
                padding: 8px;
            }}

            QHeaderView::section {{
                background-color: {c['table_header_bg']};
                color: {c['heading_text']};
                padding: 8px;
                border: none;
                border-right: 1px solid {c['border']};
                border-bottom: 1px solid {c['border']};
                font-weight: bold;
            }}

            QTabWidget::pane {{
                border: 1px solid {c['border']};
                background-color: {c['card_bg']};
                border-radius: 8px;
            }}

            QTabBar::tab {{
                background-color: {c['panel_bg']};
                color: {c['label_text']};
                padding: 8px 16px;
                border: 1px solid {c['border']};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }}

            QTabBar::tab:selected {{
                background-color: {c['button_primary']};
                color: #FFFFFF;
            }}

            QTabBar::tab:hover:!selected {{
                background-color: {c['surface_alt']};
            }}

            QMenuBar {{
                background-color: {c['panel_bg']};
                color: {c['input_text']};
                border-bottom: 1px solid {c['border']};
            }}

            QMenuBar::item:selected {{
                background-color: {c['surface_alt']};
                color: {c['heading_text']};
            }}

            QMenu {{
                background-color: {c['card_bg']};
                color: {c['input_text']};
                border: 1px solid {c['border']};
            }}

            QMenu::item:selected {{
                background-color: {c['button_primary']};
                color: #FFFFFF;
            }}

            QCheckBox {{
                background: transparent;
                color: {c['label_text']};
                border: none;
            }}

            QCalendarWidget QAbstractItemView::item {{
                padding: 0px;
                margin: 0px;
            }}

            QScrollBar:vertical, QScrollBar:horizontal {{
                background: {c['scrollbar_track']};
                border: none;
                margin: 0px;
            }}

            QScrollBar:vertical {{
                width: 10px;
            }}

            QScrollBar:horizontal {{
                height: 10px;
            }}

            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: {c['scrollbar_handle']};
                border-radius: 5px;
                min-height: 28px;
                min-width: 28px;
                margin: 2px;
            }}

            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
                background: {c['scrollbar_handle_hover']};
            }}

            QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {{
                background: {c['scrollbar_handle_pressed']};
            }}

            QScrollBar::add-line, QScrollBar::sub-line {{
                width: 0px;
                height: 0px;
                border: none;
                background: none;
            }}

            QScrollBar::add-page, QScrollBar::sub-page {{
                background: none;
            }}

            QMessageBox {{
                background-color: {c['card_bg']};
                color: {c['input_text']};
            }}
            QMessageBox QLabel {{
                color: {c['input_text']};
                background: transparent;
                border: none;
            }}
            QMessageBox QPushButton {{
                background-color: {c['button_primary']};
                color: #FFFFFF;
                border: none;
                padding: 6px 14px;
                border-radius: 4px;
                min-width: 72px;
                font-weight: bold;
            }}
            QMessageBox QPushButton:hover {{
                background-color: {c['focus_border']};
            }}

            {ThemeManager._sidebar_navigation_qss(c)}

            {app_checkbox_style()}
        """

    @staticmethod
    def _sidebar_navigation_qss(colors: dict[str, str]) -> str:
        """Sidebar section headers and route buttons (property-driven hover)."""
        from ui.theme import sidebar_navigation_qss

        return sidebar_navigation_qss(colors)

    @staticmethod
    def get_icon_color(theme_name: str) -> str:
        """Return icon tint color for the active theme."""
        if str(theme_name or "").strip().lower() == "light":
            return "#263238"
        return "white"

    @classmethod
    def get_bold_fonts_qss(cls) -> str:
        """Return application-wide QSS that forces bold text on common controls."""
        selectors = cls._font_weight_selectors()
        return f"""
            {selectors} {{
                font-weight: bold;
            }}
        """

    @classmethod
    def get_normal_fonts_qss(cls) -> str:
        """Return application-wide QSS that resets text to normal weight."""
        selectors = cls._font_weight_selectors()
        return f"""
            {selectors} {{
                font-weight: normal;
            }}
        """

    @classmethod
    def _font_weight_selectors(cls) -> str:
        """Shared selector list for global font-weight overrides."""
        return ", ".join(
            (
                "QWidget",
                "QLabel",
                "QLineEdit",
                "QTextEdit",
                "QPlainTextEdit",
                "QComboBox",
                "QSpinBox",
                "QDoubleSpinBox",
                "QDateEdit",
                "QTimeEdit",
                "QDateTimeEdit",
                "QPushButton",
                "QCheckBox",
                "QRadioButton",
                "QTabBar::tab",
                "QMenu",
                "QMenuBar",
                "QTableWidget",
                "QTableView",
                "QHeaderView::section",
                "QListWidget",
                "QListView",
                "QTreeWidget",
                "QTreeView",
                "QGroupBox",
                "QToolTip",
            )
        )

    @classmethod
    def build_application_stylesheet(
        cls,
        theme_name: str,
        *,
        bold_fonts: bool = False,
    ) -> str:
        """Compose the full application QSS for a theme and font-weight mode."""
        stylesheet = cls.get_stylesheet(theme_name)
        if bold_fonts:
            stylesheet = f"{stylesheet}\n{cls.get_bold_fonts_qss()}"
        else:
            stylesheet = f"{stylesheet}\n{cls.get_normal_fonts_qss()}"
        return stylesheet

    @classmethod
    def get_stylesheet(cls, theme_name: str) -> str:
        """Return the full application QSS for the requested theme."""
        normalized = str(theme_name or DEFAULT_THEME).strip().lower()
        if normalized == "light":
            return cls.get_light_theme_qss()
        return cls.get_dark_theme_qss()

    @classmethod
    def get_colors(cls, theme_name: str | None = None) -> dict[str, str]:
        """Return semantic color tokens for UI helpers."""
        return get_theme_colors(theme_name)

    @classmethod
    def resolve_master_db_path(cls, master_db_path: str | None = None) -> str:
        """Return the absolute master registry database path."""
        from db import BASE_DIR, get_default_database_path

        configured_path = master_db_path or get_default_database_path()
        if not os.path.isabs(configured_path):
            configured_path = os.path.join(BASE_DIR, configured_path)
        return os.path.abspath(configured_path)

    @classmethod
    def apply_application_theme(cls, app, master_db_path: str | None = None) -> str:
        """Apply the saved or previewed theme to the entire ``QApplication`` instance."""
        resolved_path = cls.resolve_master_db_path(master_db_path)
        manager = global_theme_manager
        theme_name = manager.get_effective_theme(resolved_path)
        bold_fonts = manager.get_effective_bold_fonts(resolved_path)
        app.setStyleSheet(cls.build_application_stylesheet(theme_name, bold_fonts=bold_fonts))
        cls.apply_font_weight_to_app(app, bold_fonts)
        try:
            from ui.message_boxes import install_static_method_patch
            install_static_method_patch()
        except Exception:
            pass
        try:
            from ui.theme_manager import sync_theme

            sync_theme(theme_name, resolved_path)
        except Exception:
            pass
        return theme_name

    def apply_appearance(
        self,
        app_instance,
        master_db_path: str,
        theme_name: str,
        bold_fonts: bool,
        *,
        persist: bool = False,
        emit_signal: bool = True,
    ) -> bool:
        """Apply theme and bold fonts, optionally persisting to global_settings."""
        if not app_instance:
            return False

        resolved_master_db_path = self.resolve_master_db_path(master_db_path)
        normalized_theme = str(theme_name or DEFAULT_THEME).strip().lower()
        if normalized_theme not in VALID_THEMES:
            return False

        if persist:
            if not self.save_theme_preference(resolved_master_db_path, normalized_theme):
                return False
            if not self.save_bold_fonts_preference(resolved_master_db_path, bold_fonts):
                return False
            self.clear_preview()
        else:
            self._preview_theme = normalized_theme
            self._preview_bold_fonts = bool(bold_fonts)

        app_instance.setStyleSheet(
            self.build_application_stylesheet(normalized_theme, bold_fonts=bold_fonts)
        )
        self.apply_font_weight_to_app(app_instance, bold_fonts)
        try:
            from ui.message_boxes import install_static_method_patch
            install_static_method_patch()
        except Exception:
            pass
        try:
            from ui.theme_manager import sync_theme

            sync_theme(normalized_theme, resolved_master_db_path)
        except Exception:
            pass

        if emit_signal:
            self.theme_changed.emit(normalized_theme)
        return True

    def revert_preview(self, app_instance, master_db_path: str) -> None:
        """Restore persisted theme and font settings after a cancelled preview."""
        if not self.is_preview_active():
            return

        resolved_master_db_path = self.resolve_master_db_path(master_db_path)
        saved_theme = self.get_theme_preference(resolved_master_db_path)
        saved_bold = self.get_bold_fonts_preference(resolved_master_db_path)
        self.clear_preview()

        if app_instance:
            app_instance.setStyleSheet(
                self.build_application_stylesheet(saved_theme, bold_fonts=saved_bold)
            )
            self.apply_font_weight_to_app(app_instance, saved_bold)
        try:
            from ui.message_boxes import install_static_method_patch
            install_static_method_patch()
        except Exception:
            pass
        try:
            from ui.theme_manager import sync_theme

            sync_theme(saved_theme, resolved_master_db_path)
        except Exception:
            pass
        self.theme_changed.emit(saved_theme)

    def apply_theme(self, app_instance, master_db_path: str, theme_name: str) -> bool:
        """Persist and apply theme instantly, then emit a global change signal."""
        resolved_master_db_path = self.resolve_master_db_path(master_db_path)
        bold_fonts = self.get_bold_fonts_preference(resolved_master_db_path)
        return self.apply_appearance(
            app_instance,
            resolved_master_db_path,
            theme_name,
            bold_fonts,
            persist=True,
        )

    @staticmethod
    def _connect(master_db_path: str) -> sqlite3.Connection:
        connection = sqlite3.connect(master_db_path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @classmethod
    def _ensure_global_settings_table(cls, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS global_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


global_theme_manager = ThemeManager()
