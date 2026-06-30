"""
Cards component for the Accounting Desktop Application.
Provides reusable card widgets with dark professional accounting style.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ui.theme import legacy_colors


def _C() -> dict[str, str]:
    return legacy_colors()


class BaseCard(QFrame):
    """Base card widget with common styling and functionality."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_base_style()
        self.setup_ui()
    
    def setup_base_style(self):
        """Setup base card styling."""
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {_C()['surface']};
                border: 1px solid {_C()['border']};
                border-radius: 8px;
                padding: 0px;
            }}
            QFrame:hover {{
                border-color: {_C()['border_focus']};
            }}
        """)
    
    def setup_ui(self):
        """Setup the base card UI structure."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)
    
    def set_padding(self, left: int, top: int, right: int, bottom: int):
        """Set custom padding for the card."""
        self.main_layout.setContentsMargins(left, top, right, bottom)
    
    def set_spacing(self, spacing: int):
        """Set spacing between card elements."""
        self.main_layout.setSpacing(spacing)
    
    def add_widget(self, widget: QWidget):
        """Add a widget to the card."""
        self.main_layout.addWidget(widget)
    
    def add_layout(self, layout):
        """Add a layout to the card."""
        self.main_layout.addLayout(layout)
    
    def add_stretch(self, stretch: int = 1):
        """Add stretch space to the card."""
        self.main_layout.addStretch(stretch)


class TitledCard(BaseCard):
    """Card with title and content area."""
    
    def __init__(self, title: str = "", parent=None):
        self.title = title
        super().__init__(parent)
        self.setup_titled_ui()
    
    def setup_titled_ui(self):
        """Setup titled card UI."""
        # Title label
        if self.title:
            self.title_label = QLabel(self.title)
            self.title_label.setStyleSheet(f"""
                QLabel {{
                    color: {_C()['text_primary']};
                    font-size: 16px;
                    font-weight: bold;
                    margin-bottom: 8px;
                }}
            """)
            self.main_layout.addWidget(self.title_label)
        
        # Content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        
        self.main_layout.addWidget(self.content_widget)
    
    def add_content_widget(self, widget: QWidget):
        """Add a widget to the content area."""
        self.content_layout.addWidget(widget)
    
    def add_content_layout(self, layout):
        """Add a layout to the content area."""
        self.content_layout.addLayout(layout)
    
    def get_content_widget(self) -> QWidget:
        """Get the content widget for direct manipulation."""
        return self.content_widget
    
    def set_title(self, title: str):
        """Update the card title."""
        self.title = title
        if hasattr(self, 'title_label'):
            self.title_label.setText(title)


class MetricCard(TitledCard):
    """Card for displaying metrics and key performance indicators."""
    
    def __init__(self, title: str, value: str, subtitle: str = "", color: str = _C()['primary'], parent=None):
        self.value = value
        self.subtitle = subtitle
        self.color = color
        super().__init__(title, parent)
        self.setup_metric_ui()
    
    def setup_metric_ui(self):
        """Setup metric card UI."""
        # Value label
        self.value_label = QLabel(self.value)
        self.value_label.setStyleSheet(f"""
            QLabel {{
                color: {self.color};
                font-size: 24px;
                font-weight: bold;
                margin: 8px 0;
            }}
        """)
        self.add_content_widget(self.value_label)
        
        # Subtitle label
        if self.subtitle:
            self.subtitle_label = QLabel(self.subtitle)
            self.subtitle_label.setStyleSheet(f"""
                QLabel {{
                    color: {_C()['text_secondary']};
                    font-size: 13px;
                    font-style: italic;
                }}
            """)
            self.add_content_widget(self.subtitle_label)
    
    def update_value(self, value: str):
        """Update the metric value."""
        self.value = value
        self.value_label.setText(value)
    
    def update_subtitle(self, subtitle: str):
        """Update the subtitle."""
        self.subtitle = subtitle
        if hasattr(self, 'subtitle_label'):
            self.subtitle_label.setText(subtitle)
        else:
            # Create subtitle label if it doesn't exist
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setStyleSheet(f"""
                QLabel {{
                    color: {_C()['text_secondary']};
                    font-size: 13px;
                    font-style: italic;
                }}
            """)
            self.add_content_widget(self.subtitle_label)


class ActionCard(TitledCard):
    """Card with action buttons."""
    
    action_clicked = Signal(str)
    
    def __init__(self, title: str, actions: list = None, parent=None):
        self.actions = actions or []
        super().__init__(title, parent)
        self.setup_action_ui()
    
    def setup_action_ui(self):
        """Setup action card UI."""
        # Description (optional)
        self.description_label = QLabel("")
        self.description_label.setStyleSheet(f"""
            QLabel {{
                color: {_C()['text_secondary']};
                font-size: 13px;
                margin-bottom: 12px;
            }}
        """)
        self.description_label.setWordWrap(True)
        self.add_content_widget(self.description_label)
        
        # Action buttons
        self.button_layout = QHBoxLayout()
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        self.button_layout.setSpacing(8)
        
        self.action_buttons = {}
        for action_text in self.actions:
            btn = QPushButton(action_text)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {_C()['primary']};
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {_C()['primary_dark']};
                }}
            """)
            btn.clicked.connect(lambda checked, text=action_text: self.action_clicked.emit(text))
            self.action_buttons[action_text] = btn
            self.button_layout.addWidget(btn)
        
        self.button_layout.addStretch()
        self.add_content_layout(self.button_layout)
    
    def set_description(self, description: str):
        """Set the card description."""
        self.description_label.setText(description)
        self.description_label.setVisible(bool(description))
    
    def add_action(self, action_text: str):
        """Add a new action button."""
        btn = QPushButton(action_text)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_C()['primary']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {_C()['primary_dark']};
            }}
        """)
        btn.clicked.connect(lambda checked, text=action_text: self.action_clicked.emit(text))
        self.action_buttons[action_text] = btn
        self.button_layout.insertWidget(self.button_layout.count() - 1, btn)  # Insert before stretch
        self.actions.append(action_text)
    
    def get_action_button(self, action_text: str) -> QPushButton:
        """Get an action button by text."""
        return self.action_buttons.get(action_text)


class InfoCard(TitledCard):
    """Card for displaying informational content."""
    
    def __init__(self, title: str, info_text: str = "", icon_text: str = "i", parent=None):
        self.info_text = info_text
        self.icon_text = icon_text
        super().__init__(title, parent)
        self.setup_info_ui()
    
    def setup_info_ui(self):
        """Setup info card UI."""
        # Icon and text layout
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(12)
        
        # Icon
        self.icon_label = QLabel(self.icon_text)
        self.icon_label.setStyleSheet(f"""
            QLabel {{
                background-color: {_C()['info']};
                color: white;
                border-radius: 12px;
                padding: 8px;
                font-size: 14px;
                font-weight: bold;
                min-width: 24px;
                max-width: 24px;
                min-height: 24px;
                max-height: 24px;
            }}
        """)
        self.icon_label.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(self.icon_label)
        
        # Info text
        self.info_label = QLabel(self.info_text)
        self.info_label.setStyleSheet(f"""
            QLabel {{
                color: {_C()['text_secondary']};
                font-size: 13px;
                line-height: 1.4;
            }}
        """)
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)
        
        info_layout.addStretch()
        self.add_content_layout(info_layout)
    
    def set_info_text(self, text: str):
        """Update the info text."""
        self.info_text = text
        self.info_label.setText(text)
    
    def set_icon_text(self, text: str):
        """Update the icon text."""
        self.icon_text = text
        self.icon_label.setText(text)


class StatusCard(TitledCard):
    """Card for displaying status information."""
    
    def __init__(self, title: str, status: str = "Active", status_color: str = _C()['success'], parent=None):
        self.status = status
        self.status_color = status_color
        super().__init__(title, parent)
        self.setup_status_ui()
    
    def setup_status_ui(self):
        """Setup status card UI."""
        # Status layout
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)
        
        # Status indicator
        self.status_indicator = QFrame()
        self.status_indicator.setFixedSize(12, 12)
        self.status_indicator.setStyleSheet(f"""
            QFrame {{
                background-color: {self.status_color};
                border-radius: 6px;
            }}
        """)
        status_layout.addWidget(self.status_indicator)
        
        # Status text
        self.status_label = QLabel(self.status)
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {self.status_color};
                font-size: 14px;
                font-weight: 600;
            }}
        """)
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        self.add_content_layout(status_layout)
    
    def update_status(self, status: str, color: str = None):
        """Update the status."""
        self.status = status
        self.status_label.setText(status)
        
        if color:
            self.status_color = color
            self.status_label.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    font-size: 14px;
                    font-weight: 600;
                }}
            """)
            self.status_indicator.setStyleSheet(f"""
                QFrame {{
                    background-color: {color};
                    border-radius: 6px;
                }}
            """)


class CardGrid(QWidget):
    """Container for arranging cards in a grid layout."""
    
    def __init__(self, columns: int = 2, spacing: int = 15, parent=None):
        super().__init__(parent)
        self.columns = columns
        self.spacing = spacing
        self.cards = []
        self.setup_grid_ui()
    
    def setup_grid_ui(self):
        """Setup grid layout."""
        from PySide6.QtWidgets import QGridLayout
        
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(self.spacing)
    
    def add_card(self, card: BaseCard, row: int = None, col: int = None):
        """Add a card to the grid."""
        if row is None and col is None:
            # Auto-arrange in grid
            position = len(self.cards)
            row = position // self.columns
            col = position % self.columns
        
        self.cards.append(card)
        self.grid_layout.addWidget(card, row, col)
        return card
    
    def add_card_span(self, card: BaseCard, row: int, col: int, row_span: int = 1, col_span: int = 1):
        """Add a card with custom span."""
        self.cards.append(card)
        self.grid_layout.addWidget(card, row, col, row_span, col_span)
        return card
    
    def clear_cards(self):
        """Remove all cards."""
        for card in self.cards:
            self.grid_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
    
    def get_cards(self) -> list:
        """Get all cards in the grid."""
        return self.cards


class CardList(QWidget):
    """Container for arranging cards vertically."""
    
    def __init__(self, spacing: int = 12, parent=None):
        super().__init__(parent)
        self.spacing = spacing
        self.cards = []
        self.setup_list_ui()
    
    def setup_list_ui(self):
        """Setup list layout."""
        self.list_layout = QVBoxLayout(self)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(self.spacing)
    
    def add_card(self, card: BaseCard):
        """Add a card to the list."""
        self.cards.append(card)
        self.list_layout.addWidget(card)
        return card
    
    def insert_card(self, index: int, card: BaseCard):
        """Insert a card at a specific position."""
        self.cards.insert(index, card)
        self.list_layout.insertWidget(index, card)
        return card
    
    def remove_card(self, card: BaseCard):
        """Remove a card from the list."""
        if card in self.cards:
            self.cards.remove(card)
            self.list_layout.removeWidget(card)
            card.deleteLater()
    
    def clear_cards(self):
        """Remove all cards."""
        for card in self.cards:
            self.list_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
    
    def get_cards(self) -> list:
        """Get all cards in the list."""
        return self.cards
