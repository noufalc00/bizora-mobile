"""
Buttons component for the Accounting Desktop Application.
Provides reusable button classes with dark theme support.
"""

from PySide6.QtWidgets import QPushButton, QHBoxLayout, QWidget
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from ui.theme import legacy_colors


def _C() -> dict[str, str]:
    return legacy_colors()


class BaseButton(QPushButton):
    """Base button class with common styling and functionality."""
    
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setup_base_style()
    
    def setup_base_style(self):
        """Setup base button styling."""
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(36)
    
    def set_size(self, width: int = None, height: int = None):
        """Set button size."""
        if width:
            self.setFixedWidth(width)
        if height:
            self.setFixedHeight(height)
    
    def set_enabled(self, enabled: bool):
        """Set button enabled state with visual feedback."""
        super().setEnabled(enabled)
        if not enabled:
            self.setStyleSheet(self.style_sheet + """
                QPushButton {
                    opacity: 0.6;
                }
            """)


class PrimaryButton(BaseButton):
    """Primary action button with blue theme."""
    
    def __init__(self, text: str = "Primary", parent=None):
        super().__init__(text, parent)
        self.setup_style()
    
    def setup_style(self):
        """Setup primary button styling."""
        self.style_sheet = f"""
            QPushButton {{
                background-color: {_C()['primary']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {_C()['primary_dark']};
            }}
            QPushButton:pressed {{
                background-color: {_C()['primary']};
            }}
            QPushButton:disabled {{
                background-color: {_C()['button_default']};
                color: {_C()['text_disabled']};
            }}
        """
        self.setStyleSheet(self.style_sheet)


class SecondaryButton(BaseButton):
    """Secondary button with gray theme."""
    
    def __init__(self, text: str = "Secondary", parent=None):
        super().__init__(text, parent)
        self.setup_style()
    
    def setup_style(self):
        """Setup secondary button styling."""
        self.style_sheet = f"""
            QPushButton {{
                background-color: {_C()['button_default']};
                color: {_C()['text_primary']};
                border: 1px solid {_C()['border']};
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {_C()['button_hover']};
                border-color: {_C()['border_focus']};
            }}
            QPushButton:pressed {{
                background-color: {_C()['button_pressed']};
            }}
            QPushButton:disabled {{
                background-color: {_C()['surface']};
                color: {_C()['text_disabled']};
                border-color: {_C()['border']};
            }}
        """
        self.setStyleSheet(self.style_sheet)


class SuccessButton(BaseButton):
    """Success button with green theme."""
    
    def __init__(self, text: str = "Success", parent=None):
        super().__init__(text, parent)
        self.setup_style()
    
    def setup_style(self):
        """Setup success button styling."""
        self.style_sheet = f"""
            QPushButton {{
                background-color: {_C()['success']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #45a049;
            }}
            QPushButton:pressed {{
                background-color: #3d8b40;
                            }}
            QPushButton:disabled {{
                background-color: {_C()['button_default']};
                color: {_C()['text_disabled']};
            }}
        """
        self.setStyleSheet(self.style_sheet)


class DangerButton(BaseButton):
    """Danger button with red theme."""
    
    def __init__(self, text: str = "Delete", parent=None):
        super().__init__(text, parent)
        self.setup_style()
    
    def setup_style(self):
        """Setup danger button styling."""
        self.style_sheet = f"""
            QPushButton {{
                background-color: {_C()['error']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #da190b;
            }}
            QPushButton:pressed {{
                background-color: #c41811;
                            }}
            QPushButton:disabled {{
                background-color: {_C()['button_default']};
                color: {_C()['text_disabled']};
            }}
        """
        self.setStyleSheet(self.style_sheet)


class WarningButton(BaseButton):
    """Warning button with orange theme."""
    
    def __init__(self, text: str = "Warning", parent=None):
        super().__init__(text, parent)
        self.setup_style()
    
    def setup_style(self):
        """Setup warning button styling."""
        self.style_sheet = f"""
            QPushButton {{
                background-color: {_C()['warning']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #e68900;
            }}
            QPushButton:pressed {{
                background-color: #cc7a00;
                            }}
            QPushButton:disabled {{
                background-color: {_C()['button_default']};
                color: {_C()['text_disabled']};
            }}
        """
        self.setStyleSheet(self.style_sheet)


class IconButton(BaseButton):
    """Icon-only button with minimal styling."""
    
    def __init__(self, icon_text: str = ">", parent=None):
        super().__init__(icon_text, parent)
        self.setup_style()
    
    def setup_style(self):
        """Setup icon button styling."""
        self.style_sheet = f"""
            QPushButton {{
                background-color: transparent;
                color: {_C()['text_secondary']};
                border: 1px solid {_C()['border']};
                padding: 8px;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
                min-width: 36px;
                min-height: 36px;
            }}
            QPushButton:hover {{
                background-color: {_C()['button_hover']};
                color: {_C()['text_primary']};
                border-color: {_C()['border_focus']};
            }}
            QPushButton:pressed {{
                background-color: {_C()['button_pressed']};
            }}
            QPushButton:disabled {{
                color: {_C()['text_disabled']};
                border-color: {_C()['border']};
            }}
        """
        self.setStyleSheet(self.style_sheet)


class LinkButton(BaseButton):
    """Link-style button that looks like a hyperlink."""
    
    def __init__(self, text: str = "Link", parent=None):
        super().__init__(text, parent)
        self.setup_style()
    
    def setup_style(self):
        """Setup link button styling."""
        self.style_sheet = f"""
            QPushButton {{
                background-color: transparent;
                color: {_C()['primary']};
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 13px;
                text-decoration: underline;
            }}
            QPushButton:hover {{
                background-color: {_C()['primary']};
                color: white;
                text-decoration: none;
            }}
            QPushButton:pressed {{
                background-color: {_C()['primary_dark']};
            }}
            QPushButton:disabled {{
                color: {_C()['text_disabled']};
            }}
        """
        self.setStyleSheet(self.style_sheet)


class ButtonGroup(QWidget):
    """Container for organizing multiple buttons."""
    
    def __init__(self, orientation: str = "horizontal", spacing: int = 10, parent=None):
        super().__init__(parent)
        self.orientation = orientation
        self.spacing = spacing
        self.buttons = []
        self.setup_layout()
    
    def setup_layout(self):
        """Setup the button group layout."""
        if self.orientation == "horizontal":
            self.layout = QHBoxLayout(self)
        else:
            self.layout = QVBoxLayout(self)
        
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(self.spacing)
    
    def add_button(self, button: QPushButton, stretch: int = 0):
        """Add a button to the group."""
        self.buttons.append(button)
        if stretch > 0:
            self.layout.addWidget(button, stretch)
        else:
            self.layout.addWidget(button)
        return button
    
    def add_primary_button(self, text: str, stretch: int = 0) -> PrimaryButton:
        """Add a primary button."""
        button = PrimaryButton(text)
        self.add_button(button, stretch)
        return button
    
    def add_secondary_button(self, text: str, stretch: int = 0) -> SecondaryButton:
        """Add a secondary button."""
        button = SecondaryButton(text)
        self.add_button(button, stretch)
        return button
    
    def add_success_button(self, text: str, stretch: int = 0) -> SuccessButton:
        """Add a success button."""
        button = SuccessButton(text)
        self.add_button(button, stretch)
        return button
    
    def add_danger_button(self, text: str, stretch: int = 0) -> DangerButton:
        """Add a danger button."""
        button = DangerButton(text)
        self.add_button(button, stretch)
        return button
    
    def add_warning_button(self, text: str, stretch: int = 0) -> WarningButton:
        """Add a warning button."""
        button = WarningButton(text)
        self.add_button(button, stretch)
        return button
    
    def add_icon_button(self, icon_text: str, stretch: int = 0) -> IconButton:
        """Add an icon button."""
        button = IconButton(icon_text)
        self.add_button(button, stretch)
        return button
    
    def add_stretch(self, stretch: int = 1):
        """Add stretch space to the layout."""
        self.layout.addStretch(stretch)
    
    def set_all_enabled(self, enabled: bool):
        """Enable or disable all buttons."""
        for button in self.buttons:
            button.setEnabled(enabled)
    
    def get_buttons(self) -> list:
        """Get all buttons in the group."""
        return self.buttons


class ActionButtonGroup(ButtonGroup):
    """Pre-configured button group for common actions."""
    
    def __init__(self, parent=None):
        super().__init__("horizontal", 8, parent)
        self.setup_actions()
    
    def setup_actions(self):
        """Setup common action buttons."""
        self.add_btn = self.add_primary_button("Add")
        self.edit_btn = self.add_secondary_button("Edit")
        self.delete_btn = self.add_danger_button("Delete")
        self.add_stretch()
        self.refresh_btn = self.add_icon_button("Refresh")
    
    def get_add_button(self) -> PrimaryButton:
        """Get the add button."""
        return self.add_btn
    
    def get_edit_button(self) -> SecondaryButton:
        """Get the edit button."""
        return self.edit_btn
    
    def get_delete_button(self) -> DangerButton:
        """Get the delete button."""
        return self.delete_btn
    
    def get_refresh_button(self) -> IconButton:
        """Get the refresh button."""
        return self.refresh_btn


class NavigationButtonGroup(ButtonGroup):
    """Pre-configured button group for navigation."""
    
    def __init__(self, parent=None):
        super().__init__("horizontal", 5, parent)
        self.setup_navigation()
    
    def setup_navigation(self):
        """Setup navigation buttons."""
        self.back_btn = self.add_secondary_button("Back")
        self.add_stretch()
        self.next_btn = self.add_primary_button("Next")
        self.finish_btn = self.add_success_button("Finish")
        
        # Initially hide finish button
        self.finish_btn.hide()
    
    def get_back_button(self) -> SecondaryButton:
        """Get the back button."""
        return self.back_btn
    
    def get_next_button(self) -> PrimaryButton:
        """Get the next button."""
        return self.next_btn
    
    def get_finish_button(self) -> SuccessButton:
        """Get the finish button."""
        return self.finish_btn
    
    def show_finish(self):
        """Show finish button and hide next button."""
        self.next_btn.hide()
        self.finish_btn.show()
    
    def show_next(self):
        """Show next button and hide finish button."""
        self.finish_btn.hide()
        self.next_btn.show()


class FormButtonGroup(ButtonGroup):
    """Pre-configured button group for forms."""
    
    def __init__(self, parent=None):
        super().__init__("horizontal", 10, parent)
        self.setup_form_buttons()
    
    def setup_form_buttons(self):
        """Setup form buttons."""
        self.add_stretch()
        self.cancel_btn = self.add_secondary_button("Cancel")
        self.save_btn = self.add_primary_button("Save")
        self.clear_btn = self.add_warning_button("Clear")
    
    def get_save_button(self) -> PrimaryButton:
        """Get the save button."""
        return self.save_btn
    
    def get_cancel_button(self) -> SecondaryButton:
        """Get the cancel button."""
        return self.cancel_btn
    
    def get_clear_button(self) -> WarningButton:
        """Get the clear button."""
        return self.clear_btn
