"""
Global application settings dialog.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.checkbox_style import create_checkbox, create_radio_button
from ui.settings_page_common import (
    apply_settings_page_styles,
    build_settings_content_stack,
    build_settings_footer_bar,
    build_settings_header,
    build_settings_page_shell,
    build_settings_section_nav,
    theme_colors,
)
from ui.theme_manager import get_theme_manager, sync_theme
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.time_formats import (
    TIME_FORMAT_12H,
    TIME_FORMAT_24H,
    get_time_format_preference,
    save_time_format_preference,
)
from ui.ui_memory import UiMemoryMixin, configure_non_modal_window
from utils.theme_manager import ThemeManager, global_theme_manager


class GlobalSettingsDialog(UiMemoryMixin, QDialog):
    """Dialog for global preferences such as application theme."""

    SECTIONS = (
        ("color_mode", "Color Mode"),
        ("font_settings", "Font Settings"),
        ("time_format", "Time Format"),
        ("layout_memory", "Window & Layout"),
    )

    def __init__(
        self,
        master_db_path: str | None = None,
        parent=None,
        initial_section: str | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("GeneralSettingsDialog")
        self.master_db_path = self._resolve_master_db_path(master_db_path)
        self._initial_section = initial_section or "color_mode"
        self._block_live_preview = False
        self.section_buttons: dict[str, QPushButton] = {}
        self.section_button_group: QButtonGroup | None = None
        self.section_stack: QStackedWidget | None = None
        self._build_ui()
        self._load_current_preferences()
        self._apply_theme_styles()
        self._show_section(self._initial_section)
        self.color_mode_combo.currentIndexChanged.connect(self._on_live_appearance_changed)
        self.bold_fonts_checkbox.toggled.connect(self._on_live_appearance_changed)
        global_theme_manager.theme_changed.connect(self.refresh_theme)
        self._theme_listener_connected = True
        configure_non_modal_window(self, parent)
        self._init_ui_memory()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

    def _disconnect_theme_listener(self) -> None:
        """Disconnect the live theme listener once when the dialog closes."""
        if not getattr(self, "_theme_listener_connected", False):
            return
        try:
            global_theme_manager.theme_changed.disconnect(self.refresh_theme)
        except (TypeError, RuntimeError):
            pass
        self._theme_listener_connected = False

    def closeEvent(self, event) -> None:
        """Stop live theme preview listeners before the dialog closes."""
        self._disconnect_theme_listener()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        """Close immediately and defer heavy theme rollback until afterward."""
        revert_needed = (
            result != QDialog.DialogCode.Accepted
            and global_theme_manager.is_preview_active()
        )
        master_db_path = self.master_db_path
        host_window = self.parent()
        self._disconnect_theme_listener()
        super().done(result)
        if revert_needed:
            QTimer.singleShot(
                0,
                lambda: self._deferred_cancel_cleanup(master_db_path, host_window),
            )

    def _deferred_cancel_cleanup(self, master_db_path: str, host_window) -> None:
        """Revert unsaved theme preview after the dialog has already closed."""
        app_instance = QApplication.instance()
        if app_instance is not None:
            global_theme_manager.revert_preview(app_instance, master_db_path)
        while host_window is not None:
            if hasattr(host_window, "apply_theme"):
                host_window.apply_theme()
                return
            host_window = host_window.parent()

    def _resolve_master_db_path(self, master_db_path: str | None) -> str:
        return ThemeManager.resolve_master_db_path(master_db_path)

    def _build_ui(self) -> None:
        self.setWindowTitle("General Settings")
        self.setMinimumSize(760, 560)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(14)

        self.title_label, self.subtitle_label = build_settings_header(
            layout,
            "General Settings",
            "Choose a section on the left to manage application appearance, fonts, "
            "and saved window layouts. Color mode and font changes preview live.",
        )

        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)
        nav_frame, self.section_buttons, self.section_button_group = (
            build_settings_section_nav(self, self.SECTIONS, self._show_section)
        )
        content_frame, self.section_stack = build_settings_content_stack()
        self.section_stack.addWidget(self._build_theme_page())
        self.section_stack.addWidget(self._build_font_page())
        self.section_stack.addWidget(self._build_time_format_page())
        self.section_stack.addWidget(self._build_layout_memory_page())
        body_layout.addWidget(nav_frame)
        body_layout.addWidget(content_frame, 1)
        layout.addLayout(body_layout, 1)

        self.footer_frame, self.save_button, self.cancel_button = build_settings_footer_bar(
            "Save Settings",
            self._on_save,
            self.reject,
        )
        layout.addWidget(self.footer_frame)

    def _build_theme_page(self) -> QWidget:
        """Create the color mode selection page."""
        page, layout = build_settings_page_shell(
            "Color Mode",
            "Choose Light or Dark for the application appearance. Changes apply "
            "immediately across open windows. Click Save Settings to keep your selection.",
        )
        row = QHBoxLayout()
        row.setSpacing(12)
        color_mode_label = QLabel("Color Mode")
        color_mode_label.setObjectName("settingsEntryLabel")
        self.color_mode_combo = QComboBox()
        self.color_mode_combo.setObjectName("colorModeCombo")
        self.color_mode_combo.setMinimumWidth(200)
        self.color_mode_combo.setMinimumHeight(34)
        self.color_mode_combo.addItem("Dark", "dark")
        self.color_mode_combo.addItem("Light", "light")
        row.addWidget(color_mode_label)
        row.addWidget(self.color_mode_combo)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        return page

    def _build_font_page(self) -> QWidget:
        """Create the font settings page."""
        page, layout = build_settings_page_shell(
            "Font Settings",
            "Tick or untick to preview bold text across the app immediately. "
            "Click Save Settings to keep the font setting.",
        )
        colors = theme_colors(self.master_db_path)
        self.bold_fonts_checkbox = create_checkbox(
            "Use bold fonts for all text and input fields",
            label_color=colors["input_text"],
            font_size=13,
            spacing=8,
        )
        layout.addWidget(self.bold_fonts_checkbox)
        layout.addStretch()
        return page

    def _build_time_format_page(self) -> QWidget:
        """Create the global 12/24-hour time format page."""
        page, layout = build_settings_page_shell(
            "Time Format",
            "Choose how time is shown across the application, including the top bar "
            "clock and printed bill time when Print Time is enabled.",
        )
        colors = theme_colors(self.master_db_path)
        label_color = colors["input_text"]
        self.time_12h_radio = create_radio_button(
            "12 Hour (AM/PM)",
            label_color=label_color,
            font_size=13,
            highlight_checked_label=False,
        )
        self.time_24h_radio = create_radio_button(
            "24 Hour",
            label_color=label_color,
            font_size=13,
            highlight_checked_label=False,
        )
        self.time_format_button_group = QButtonGroup(self)
        self.time_format_button_group.addButton(self.time_12h_radio)
        self.time_format_button_group.addButton(self.time_24h_radio)
        layout.addWidget(self.time_12h_radio)
        layout.addWidget(self.time_24h_radio)
        layout.addStretch()
        return page

    def _build_layout_memory_page(self) -> QWidget:
        """Create the layout memory reset page."""
        page, layout = build_settings_page_shell(
            "Window & Layout Memory",
            "This app remembers module window sizes and table column widths you adjust. "
            "Use the button below to restore all windows and column layouts to defaults.",
        )
        self.restore_layouts_button = QPushButton("Reset Layouts")
        self.restore_layouts_button.clicked.connect(self._on_restore_default_layouts)
        layout.addWidget(self.restore_layouts_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    def _show_section(self, section_id: str) -> None:
        """Display one settings section in the content stack."""
        index_map = {
            "color_mode": 0,
            "theme_selection": 0,
            "font_settings": 1,
            "time_format": 2,
            "layout_memory": 3,
        }
        if self.section_stack is not None:
            self.section_stack.setCurrentIndex(index_map.get(section_id, 0))
        button = self.section_buttons.get(section_id)
        if button is not None:
            button.setChecked(True)

    def _apply_theme_styles(self) -> None:
        """Apply current light/dark theme tokens to the settings dialog."""
        effective_theme = global_theme_manager.get_effective_theme(self.master_db_path)
        sync_theme(effective_theme, self.master_db_path)
        apply_settings_page_styles(
            self,
            "GeneralSettingsDialog",
            self.section_buttons,
            self.title_label,
            self.subtitle_label,
            self.footer_frame,
            self.save_button,
            self.cancel_button,
            self.restore_layouts_button,
            self.master_db_path,
        )
        colors = theme_colors(self.master_db_path)
        label_color = colors["input_text"]
        if hasattr(self.bold_fonts_checkbox, "set_label_color"):
            self.bold_fonts_checkbox.set_label_color(label_color)
        if hasattr(self.time_12h_radio, "set_label_color"):
            self.time_12h_radio.set_label_color(label_color)
        if hasattr(self.time_24h_radio, "set_label_color"):
            self.time_24h_radio.set_label_color(label_color)
        self._repaint_settings_shell()

    def _repaint_settings_shell(self) -> None:
        """Force an immediate repaint after live color-mode preview changes."""
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        app_instance = QApplication.instance()
        if app_instance is not None:
            app_instance.processEvents()

    def refresh_theme(self, theme_name: str | None = None) -> None:
        """Refresh dialog styling when the global theme changes."""
        if theme_name is not None:
            sync_theme(theme_name, self.master_db_path)
        self._apply_theme_styles()

    def _load_current_preferences(self) -> None:
        """Load saved theme and font preferences into the dialog controls."""
        self._block_live_preview = True
        try:
            current_theme = ThemeManager.get_theme_preference(self.master_db_path)
            theme_index = self.color_mode_combo.findData(current_theme)
            if theme_index >= 0:
                self.color_mode_combo.setCurrentIndex(theme_index)
            else:
                self.color_mode_combo.setCurrentIndex(0)
            self.bold_fonts_checkbox.setChecked(
                ThemeManager.get_bold_fonts_preference(self.master_db_path)
            )
            if get_time_format_preference(self.master_db_path) == TIME_FORMAT_24H:
                self.time_24h_radio.setChecked(True)
            else:
                self.time_12h_radio.setChecked(True)
        finally:
            self._block_live_preview = False

    def _selected_theme(self) -> str:
        selected = self.color_mode_combo.currentData()
        return str(selected or "dark")

    def _selected_time_format(self) -> str:
        """Return the selected global time display format."""
        return TIME_FORMAT_24H if self.time_24h_radio.isChecked() else TIME_FORMAT_12H

    def _on_live_appearance_changed(self, _value=0) -> None:
        """Preview color mode and bold-font changes before Save is clicked."""
        if self._block_live_preview:
            return
        app_instance = QApplication.instance()
        if app_instance is None:
            return
        global_theme_manager.apply_appearance(
            app_instance,
            self.master_db_path,
            self._selected_theme(),
            self.bold_fonts_checkbox.isChecked(),
            persist=False,
        )
        self._refresh_host_application_theme()

    def _on_restore_default_layouts(self) -> None:
        """Clear persisted window geometry and table column layout memory."""
        from ui.ui_memory import prompt_restore_default_ui_layouts

        prompt_restore_default_ui_layouts(self)

    def _refresh_host_application_theme(self) -> None:
        """Re-apply theme on the open main window after global settings are saved."""
        host = self.parent()
        while host is not None:
            if hasattr(host, "apply_theme"):
                host.apply_theme()
                return
            host = host.parent()

    def _on_save(self) -> None:
        app_instance = QApplication.instance()
        if app_instance is None:
            QMessageBox.warning(self, "Settings", "Application instance is not available.")
            return
        if not global_theme_manager.apply_appearance(
            app_instance,
            self.master_db_path,
            self._selected_theme(),
            self.bold_fonts_checkbox.isChecked(),
            persist=True,
        ):
            QMessageBox.critical(
                self,
                "Settings Update Failed",
                "Could not save theme and font preferences. Please try again.",
            )
            return
        if not save_time_format_preference(
            self.master_db_path,
            self._selected_time_format(),
        ):
            QMessageBox.critical(
                self,
                "Settings Update Failed",
                "Could not save the time format preference. Please try again.",
            )
            return
        self.refresh_theme(self._selected_theme())
        self.accept()