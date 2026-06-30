"""
Shared layout and styling helpers for settings pages and dialogs.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.book_report_common import page_heading_style, report_summary_label_style
from ui.theme import apply_reset_layouts_button
from ui.theme_manager import get_theme_manager
from utils.theme_manager import ThemeManager, global_theme_manager


def effective_theme_name(master_db_path: str | None = None) -> str:
    """Return the live theme, including unsaved General Settings preview."""
    resolved = ThemeManager.resolve_master_db_path(master_db_path)
    return global_theme_manager.get_effective_theme(resolved)


def theme_colors(master_db_path: str | None = None) -> dict[str, str]:
    """Return active theme colors for settings screens."""
    theme_name = effective_theme_name(master_db_path)
    return get_theme_manager(master_db_path).get_colors(theme_name)


def footer_frame_style(master_db_path: str | None = None) -> str:
    """Return footer separator style for settings action buttons."""
    colors = theme_colors(master_db_path)
    return (
        f"QFrame#settingsFooterFrame {{"
        f"background-color: transparent; border: none; "
        f"border-top: 1px solid {colors['border']};}}"
    )


def primary_button_style(master_db_path: str | None = None) -> str:
    """Return primary action button style."""
    colors = theme_colors(master_db_path)
    return (
        f"QPushButton {{"
        f"background-color: {colors['button_primary']}; color: #FFFFFF; "
        f"border: none; border-radius: 6px; padding: 10px 22px; "
        f"font-size: 13px; font-weight: bold;}}"
        f"QPushButton:hover {{background-color: {colors['focus_border']};}}"
    )


def secondary_button_style(master_db_path: str | None = None) -> str:
    """Return secondary action button style."""
    colors = theme_colors(master_db_path)
    hover = colors.get("surface_alt", colors["panel_bg"])
    return (
        f"QPushButton {{"
        f"background-color: {colors['panel_bg']}; color: {colors['input_text']}; "
        f"border: 1px solid {colors['border']}; border-radius: 6px; "
        f"padding: 10px 22px; font-size: 13px; font-weight: 600;}}"
        f"QPushButton:hover {{background-color: {hover}; "
        f"border-color: {colors['focus_border']};}}"
    )


def settings_page_stylesheet(
    root_object_name: str,
    master_db_path: str | None = None,
) -> str:
    """Return the shared stylesheet for invoice/general settings screens."""
    theme_name = effective_theme_name(master_db_path)
    colors = theme_colors(master_db_path)
    hover = colors.get("surface_alt", colors["panel_bg"])
    active_bg = colors.get("nav_item_active_bg", colors["focus_border"])
    active_text = (
        "#FFFFFF"
        if theme_name == "light"
        else colors.get("nav_item_hover_text", "#FFFFFF")
    )
    return f"""
        QWidget#{root_object_name} {{
            background-color: {colors['app_bg']};
            color: {colors['input_text']};
        }}
        QDialog#{root_object_name} {{
            background-color: {colors['app_bg']};
            color: {colors['input_text']};
        }}
        QFrame#settingsNavFrame {{
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
        }}
        QFrame#settingsContentFrame {{
            background-color: {colors['panel_bg']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
        }}
        QFrame#settingsFormFrame {{
            background-color: {colors.get('card_bg', colors['panel_bg'])};
            border: 1px solid {colors['border']};
            border-radius: 8px;
        }}
        QLabel {{
            background: transparent;
            border: none;
            color: {colors['input_text']};
        }}
        QLabel#settingsSectionTitle {{
            color: {colors['heading_text']};
            font-size: 18px;
            font-weight: bold;
        }}
        QLabel#settingsSectionHelp {{
            color: {colors['label_text']};
            font-size: 12px;
            font-weight: normal;
        }}
        QLabel#settingsGridHeader {{
            color: {colors['accent_label']};
            font-size: 12px;
            font-weight: bold;
            padding-bottom: 4px;
        }}
        QLabel#settingsEntryLabel {{
            color: {colors['input_text']};
            font-size: 13px;
            font-weight: 600;
            min-width: 130px;
        }}
        QLabel#settingsDefaultLabel {{
            color: {colors['heading_text']};
            font-size: 13px;
            font-weight: bold;
        }}
        QLabel#settingsMutedLabel {{
            color: {colors['muted_text']};
            font-size: 12px;
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QLineEdit, QComboBox {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 13px;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border: 1px solid {colors['focus_border']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
            background-color: {colors['input_bg']};
        }}
        QComboBox QAbstractItemView {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            border: 1px solid {colors['border']};
            selection-background-color: {colors['focus_border']};
            selection-color: #FFFFFF;
        }}
        QPushButton#settingsNavButton {{
            background-color: transparent;
            color: {colors['input_text']};
            border: none;
            border-left: 3px solid transparent;
            border-radius: 4px;
            padding: 10px 12px;
            text-align: left;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton#settingsNavButton:hover {{
            background-color: {hover};
            border-left: 3px solid {colors['accent_label']};
        }}
        QPushButton#settingsNavButton:checked {{
            background-color: {active_bg};
            color: {active_text};
            border-left: 3px solid {colors['accent_label']};
        }}
        QPushButton#settingsNavButton:checked:hover {{
            background-color: {active_bg};
            color: {active_text};
            border-left: 3px solid {colors['accent_label']};
        }}
    """


def apply_settings_page_styles(
    widget,
    root_object_name: str,
    section_buttons: dict[str, QPushButton],
    title_label: QLabel,
    subtitle_label: QLabel,
    footer_frame: QFrame,
    save_button: QPushButton,
    cancel_button: QPushButton,
    restore_button: QPushButton | None = None,
    master_db_path: str | None = None,
) -> None:
    """Apply the shared settings page look-and-feel."""
    widget.setStyleSheet(settings_page_stylesheet(root_object_name, master_db_path))
    title_label.setStyleSheet(page_heading_style(22))
    subtitle_label.setStyleSheet(report_summary_label_style())
    footer_frame.setStyleSheet(footer_frame_style(master_db_path))
    save_button.setStyleSheet(primary_button_style(master_db_path))
    cancel_button.setStyleSheet(secondary_button_style(master_db_path))
    if restore_button is not None:
        apply_reset_layouts_button(restore_button)
    for button in section_buttons.values():
        button.setObjectName("settingsNavButton")


def build_settings_header(
    root_layout: QVBoxLayout,
    title_text: str,
    subtitle_text: str,
) -> tuple[QLabel, QLabel]:
    """Add the standard settings title and subtitle."""
    title_label = QLabel(title_text)
    title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root_layout.addWidget(title_label)

    subtitle_label = QLabel(subtitle_text)
    subtitle_label.setWordWrap(True)
    subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root_layout.addWidget(subtitle_label)
    return title_label, subtitle_label


def build_settings_section_nav(
    parent,
    sections: tuple[tuple[str, str], ...],
    on_section_selected,
) -> tuple[QFrame, dict[str, QPushButton], QButtonGroup]:
    """Create the left settings navigation panel."""
    nav_frame = QFrame()
    nav_frame.setObjectName("settingsNavFrame")
    nav_frame.setFixedWidth(190)
    nav_layout = QVBoxLayout(nav_frame)
    nav_layout.setContentsMargins(8, 10, 8, 10)
    nav_layout.setSpacing(6)

    button_group = QButtonGroup(parent)
    button_group.setExclusive(True)
    section_buttons: dict[str, QPushButton] = {}

    for section_id, title in sections:
        button = QPushButton(title)
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(
            lambda _checked=False, sid=section_id: on_section_selected(sid)
        )
        button_group.addButton(button)
        section_buttons[section_id] = button
        nav_layout.addWidget(button)

    nav_layout.addStretch()
    return nav_frame, section_buttons, button_group


def build_settings_content_stack() -> tuple[QFrame, QStackedWidget]:
    """Create the right-hand stacked content area."""
    content_frame = QFrame()
    content_frame.setObjectName("settingsContentFrame")
    content_layout = QVBoxLayout(content_frame)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(0)

    section_stack = QStackedWidget()
    content_layout.addWidget(section_stack)
    return content_frame, section_stack


def build_settings_page_shell(title: str, help_text: str) -> tuple[QWidget, QVBoxLayout]:
    """Create a scrollable settings section page."""
    page = QWidget()
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(12)

    heading = QLabel(title)
    heading.setObjectName("settingsSectionTitle")
    layout.addWidget(heading)

    help_label = QLabel(help_text)
    help_label.setWordWrap(True)
    help_label.setObjectName("settingsSectionHelp")
    layout.addWidget(help_label)

    scroll.setWidget(inner)
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(0, 0, 0, 0)
    page_layout.addWidget(scroll)
    return page, layout


def build_settings_footer_bar(
    save_text: str,
    on_save,
    on_cancel,
) -> tuple[QFrame, QPushButton, QPushButton]:
    """Create the standard settings footer action bar."""
    footer_frame = QFrame()
    footer_frame.setObjectName("settingsFooterFrame")
    layout = QHBoxLayout(footer_frame)
    layout.setContentsMargins(0, 12, 0, 0)
    layout.setSpacing(10)
    layout.addStretch()

    save_button = QPushButton(save_text)
    save_button.clicked.connect(on_save)
    layout.addWidget(save_button)

    cancel_button = QPushButton("Cancel")
    cancel_button.clicked.connect(on_cancel)
    layout.addWidget(cancel_button)
    return footer_frame, save_button, cancel_button