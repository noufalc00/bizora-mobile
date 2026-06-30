"""
Form widgets component for the Accounting Desktop Application.
Provides reusable labeled input widgets for forms.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QTextEdit, 
    QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QFrame
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont

from ui.theme import legacy_colors


def _C() -> dict[str, str]:
    return legacy_colors()


class LabeledInputWidget(QWidget):
    """Reusable labeled input widget with various input types."""
    
    def __init__(self, label_text: str, input_type: str = "text", parent=None):
        super().__init__(parent)
        self.label_text = label_text
        self.input_type = input_type
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the labeled input widget."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Label
        self.label = QLabel(self.label_text)
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {_C()['text_primary']};
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        layout.addWidget(self.label)
        
        # Input widget based on type
        self.input_widget = self.create_input_widget()
        layout.addWidget(self.input_widget)
    
    def create_input_widget(self) -> QWidget:
        """Create the appropriate input widget based on type."""
        if self.input_type == "text":
            widget = QLineEdit()
            widget.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {_C()['card']};
                    color: {_C()['text_primary']};
                    border: 1px solid {_C()['border']};
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-size: 13px;
                }}
                QLineEdit:focus {{
                    border-color: {_C()['primary']};
                }}
            """)
        elif self.input_type == "multiline":
            widget = QTextEdit()
            widget.setFixedHeight(80)
            widget.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {_C()['card']};
                    color: {_C()['text_primary']};
                    border: 1px solid {_C()['border']};
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-size: 13px;
                }}
                QTextEdit:focus {{
                    border-color: {_C()['primary']};
                }}
            """)
        elif self.input_type == "combo":
            widget = QComboBox()
            widget.setStyleSheet(f"""
                QComboBox {{
                    background-color: {_C()['card']};
                    color: {_C()['text_primary']};
                    border: 1px solid {_C()['border']};
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-size: 13px;
                }}
                QComboBox:hover {{
                    border-color: {_C()['border_focus']};
                }}
                QComboBox:focus {{
                    border-color: {_C()['primary']};
                }}
                QComboBox::drop-down {{
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 30px;
                    border-left-width: 1px;
                    border-left-color: {_C()['border']};
                    border-left-style: solid;
                    background-color: {_C()['button_hover']};
                }}
                QComboBox::down-arrow {{
                    image: none;
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 5px solid {_C()['text_secondary']};
                }}
                QComboBox QAbstractItemView {{
                    background-color: {_C()['card']};
                    color: {_C()['text_primary']};
                    border: 1px solid {_C()['border']};
                    selection-background-color: {_C()['primary']};
                    selection-color: white;
                }}
            """)
        elif self.input_type == "date":
            widget = QDateEdit()
            widget.setDate(QDate.currentDate())
            widget.setCalendarPopup(True)
            widget.setStyleSheet(f"""
                QDateEdit {{
                    background-color: {_C()['card']};
                    color: {_C()['text_primary']};
                    border: 1px solid {_C()['border']};
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-size: 13px;
                }}
                QDateEdit:focus {{
                    border-color: {_C()['primary']};
                }}
            """)
        elif self.input_type == "number":
            widget = QSpinBox()
            widget.setStyleSheet(f"""
                QSpinBox {{
                    background-color: {_C()['card']};
                    color: {_C()['text_primary']};
                    border: 1px solid {_C()['border']};
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-size: 13px;
                }}
                QSpinBox:focus {{
                    border-color: {_C()['primary']};
                }}
                QSpinBox::up-button, QSpinBox::down-button {{
                    background-color: {_C()['button_hover']};
                    border: 1px solid {_C()['border']};
                }}
            """)
        elif self.input_type == "decimal":
            widget = QDoubleSpinBox()
            widget.setDecimals(2)
            widget.setStyleSheet(f"""
                QDoubleSpinBox {{
                    background-color: {_C()['card']};
                    color: {_C()['text_primary']};
                    border: 1px solid {_C()['border']};
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-size: 13px;
                }}
                QDoubleSpinBox:focus {{
                    border-color: {_C()['primary']};
                }}
                QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                    background-color: {_C()['button_hover']};
                    border: 1px solid {_C()['border']};
                }}
            """)
        else:
            # Default to text input
            widget = QLineEdit()
            widget.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {_C()['card']};
                    color: {_C()['text_primary']};
                    border: 1px solid {_C()['border']};
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-size: 13px;
                }}
                QLineEdit:focus {{
                    border-color: {_C()['primary']};
                }}
            """)
        
        return widget
    
    def get_value(self):
        """Get the current value from the input widget."""
        if self.input_type == "text":
            return self.input_widget.text()
        elif self.input_type == "multiline":
            return self.input_widget.toPlainText()
        elif self.input_type == "combo":
            return self.input_widget.currentText()
        elif self.input_type == "date":
            return self.input_widget.date()
        elif self.input_type == "number":
            return self.input_widget.value()
        elif self.input_type == "decimal":
            return self.input_widget.value()
        else:
            return ""
    
    def set_value(self, value):
        """Set the value of the input widget."""
        if self.input_type == "text":
            self.input_widget.setText(str(value))
        elif self.input_type == "multiline":
            self.input_widget.setPlainText(str(value))
        elif self.input_type == "combo":
            index = self.input_widget.findText(str(value))
            if index >= 0:
                self.input_widget.setCurrentIndex(index)
        elif self.input_type == "date":
            if isinstance(value, QDate):
                self.input_widget.setDate(value)
            else:
                self.input_widget.setDate(QDate.fromString(str(value), "yyyy-MM-dd"))
        elif self.input_type == "number":
            self.input_widget.setValue(int(value))
        elif self.input_type == "decimal":
            self.input_widget.setValue(float(value))
    
    def clear(self):
        """Clear the input widget."""
        if self.input_type == "text":
            self.input_widget.clear()
        elif self.input_type == "multiline":
            self.input_widget.clear()
        elif self.input_type == "combo":
            self.input_widget.setCurrentIndex(0)
        elif self.input_type == "date":
            self.input_widget.setDate(QDate.currentDate())
        elif self.input_type == "number":
            self.input_widget.setValue(0)
        elif self.input_type == "decimal":
            self.input_widget.setValue(0.0)
    
    def set_placeholder(self, placeholder_text: str):
        """Set placeholder text for the input widget."""
        if hasattr(self.input_widget, 'setPlaceholderText'):
            self.input_widget.setPlaceholderText(placeholder_text)
    
    def set_enabled(self, enabled: bool):
        """Enable or disable the input widget."""
        self.input_widget.setEnabled(enabled)
        self.label.setEnabled(enabled)


class FormRowWidget(QWidget):
    """A horizontal row containing multiple labeled inputs."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.inputs = {}
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the form row layout."""
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(15)
    
    def add_input(self, label_text: str, input_type: str = "text", stretch: int = 1):
        """Add a labeled input to the row."""
        input_widget = LabeledInputWidget(label_text, input_type)
        self.inputs[label_text] = input_widget
        self.layout.addWidget(input_widget, stretch)
        return input_widget
    
    def add_widget(self, widget: QWidget, stretch: int = 1):
        """Add a custom widget to the row."""
        self.layout.addWidget(widget, stretch)
    
    def add_stretch(self, stretch: int = 1):
        """Add stretch space to the row."""
        self.layout.addStretch(stretch)
    
    def get_input(self, label_text: str) -> LabeledInputWidget:
        """Get an input widget by label text."""
        return self.inputs.get(label_text)
    
    def get_values(self) -> dict:
        """Get all input values as a dictionary."""
        values = {}
        for label, input_widget in self.inputs.items():
            values[label] = input_widget.get_value()
        return values
    
    def clear_all(self):
        """Clear all input widgets."""
        for input_widget in self.inputs.values():
            input_widget.clear()


class FormSectionWidget(QFrame):
    """A form section with title and multiple input rows."""
    
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.title = title
        self.rows = []
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the form section."""
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {_C()['surface']};
                border: 1px solid {_C()['border']};
                border-radius: 8px;
                padding: 16px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Title
        if self.title:
            title_label = QLabel(self.title)
            title_label.setStyleSheet(f"""
                QLabel {{
                    color: {_C()['text_primary']};
                    font-size: 16px;
                    font-weight: bold;
                    margin-bottom: 8px;
                }}
            """)
            layout.addWidget(title_label)
        
        # Content area for rows
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        
        layout.addWidget(self.content_widget)
    
    def add_row(self, row_widget: QWidget):
        """Add a row widget to the form section."""
        self.rows.append(row_widget)
        self.content_layout.addWidget(row_widget)
        return row_widget
    
    def create_row(self) -> FormRowWidget:
        """Create and add a new form row."""
        row = FormRowWidget()
        self.add_row(row)
        return row
    
    def add_separator(self):
        """Add a separator line."""
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"""
            QFrame {{
                background-color: {_C()['border']};
                max-height: 1px;
            }}
        """)
        self.content_layout.addWidget(separator)
    
    def add_stretch(self, stretch: int = 1):
        """Add stretch space."""
        self.content_layout.addStretch(stretch)
    
    def get_all_values(self) -> dict:
        """Get all values from all rows."""
        all_values = {}
        for row in self.rows:
            if isinstance(row, FormRowWidget):
                all_values.update(row.get_values())
        return all_values
    
    def clear_all(self):
        """Clear all input widgets."""
        for row in self.rows:
            if isinstance(row, FormRowWidget):
                row.clear_all()
