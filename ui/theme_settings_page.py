"""
Theme Settings Page for the Accounting Desktop application.

This page allows users to switch between Dark and Light themes.
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QButtonGroup, QFrame,
                               QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ui import theme
from ui.checkbox_style import create_radio_button
from ui.theme_manager import get_theme_manager, get_colors, set_theme
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin


class ThemeSettingsPage(UiMemoryMixin, QWidget):
    """Theme settings page for switching between Dark and Light themes."""

    def __init__(self, parent=None):
        """Initialize theme settings page."""
        super().__init__(parent)
        self.theme_manager = get_theme_manager()
        self._init_ui()
        self._load_current_theme()
        self._init_ui_memory(restore_geometry=False, save_geometry=False)

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        self.setLayout(layout)

        # Title
        title = QLabel("Theme Settings")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        colors = get_colors(self.theme_manager.get_current_theme())

        # Description
        description = QLabel("Choose your preferred theme for the application")
        description.setAlignment(Qt.AlignCenter)
        description.setStyleSheet(f"color: {colors['muted_text']}; font-size: 13px;")
        layout.addWidget(description)

        # Current theme display
        self.current_theme_label = QLabel("Current Theme: Loading...")
        self.current_theme_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.current_theme_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.current_theme_label)

        # Theme options frame
        theme_frame = QFrame()
        theme_frame.setStyleSheet("border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;")
        theme_layout = QVBoxLayout(theme_frame)
        theme_layout.setSpacing(12)

        # Dark theme radio button
        self.dark_radio = create_radio_button(
            "Dark Theme",
            label_color=colors["label_text"],
            font_size=13,
            highlight_checked_label=False,
        )
        theme_layout.addWidget(self.dark_radio)

        # Light theme radio button
        self.light_radio = create_radio_button(
            "Light Theme",
            label_color=colors["label_text"],
            font_size=13,
            highlight_checked_label=False,
        )
        theme_layout.addWidget(self.light_radio)

        # Add to button group
        self.theme_group = QButtonGroup(self)
        self.theme_group.addButton(self.dark_radio)
        self.theme_group.addButton(self.light_radio)

        layout.addWidget(theme_frame)

        # Preview card
        preview_frame = QFrame()
        preview_frame.setStyleSheet("border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;")
        preview_layout = QVBoxLayout(preview_frame)
        
        preview_label = QLabel("Preview")
        preview_label.setFont(QFont("Arial", 12, QFont.Bold))
        preview_label.setStyleSheet("color: #64748b;")
        preview_layout.addWidget(preview_label)

        self.preview_card = QFrame()
        self.preview_card.setFixedHeight(80)
        preview_layout.addWidget(self.preview_card)

        layout.addWidget(preview_frame)

        # Button bar
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setFont(QFont("Arial", 11, QFont.Bold))
        self.btn_apply.setStyleSheet(theme.sales_primary_button_style())
        self.btn_apply.clicked.connect(self._on_apply)
        button_layout.addWidget(self.btn_apply)

        self.btn_close = QPushButton("Close")
        self.btn_close.setFont(QFont("Arial", 11))
        self.btn_close.setStyleSheet(theme.sales_compact_button_style())
        self.btn_close.clicked.connect(self.close)
        button_layout.addWidget(self.btn_close)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        layout.addStretch()

    def _load_current_theme(self):
        """Load and display current theme."""
        current_theme = self.theme_manager.get_current_theme()
        self.current_theme_label.setText(f"Current Theme: {current_theme.title()}")

        if current_theme == "dark":
            self.dark_radio.setChecked(True)
        else:
            self.light_radio.setChecked(True)

        self._update_preview()

    def _update_preview(self):
        """Update preview card based on selected theme."""
        selected_theme = "dark" if self.dark_radio.isChecked() else "light"
        colors = get_colors(selected_theme)

        self.preview_card.setStyleSheet(f"""
            QFrame {{
                background-color: {colors['card_bg']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
            }}
        """)

    def _on_apply(self):
        """Handle Apply button click."""
        selected_theme = "dark" if self.dark_radio.isChecked() else "light"

        # Save theme
        success = set_theme(selected_theme)

        if success:
            # Apply theme to current page
            self._apply_theme_to_page()

            # Notify user
            QMessageBox.information(
                self,
                "Theme Changed",
                "Theme changed successfully. Some open windows may need to be reopened."
            )

            # Update current theme display
            self.current_theme_label.setText(f"Current Theme: {selected_theme.title()}")
        else:
            QMessageBox.critical(
                self,
                "Error",
                "Failed to change theme. Please try again."
            )

    def _apply_theme_to_page(self):
        """Apply theme to current page."""
        colors = get_colors()
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {colors['app_bg']};
                color: {colors['input_text']};
            }}
        """)

        # Update preview
        self._update_preview()

        # Update labels
        self.current_theme_label.setStyleSheet(f"""
            QLabel {{
                color: {colors['heading_text']};
                font-size: 14px;
                font-weight: bold;
            }}
        """)
        if hasattr(self, "btn_apply"):
            self.btn_apply.setStyleSheet(theme.sales_primary_button_style())
        if hasattr(self, "btn_close"):
            self.btn_close.setStyleSheet(theme.sales_compact_button_style())

    def refresh_theme(self):
        """Refresh theme when theme changes externally."""
        self._load_current_theme()
        self._apply_theme_to_page()