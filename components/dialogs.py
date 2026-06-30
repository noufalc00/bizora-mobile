"""
Dialogs component for the Accounting Desktop Application.
Provides reusable dialog helpers with dark theme support.
"""

from PySide6.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QTextEdit, QFrame, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon

from config import COLORS
from ui import theme
from ui.message_boxes import apply_message_box_theme, question as themed_question


class DialogHelper:
    """Helper class for creating common message dialogs."""
    
    @staticmethod
    def show_info(parent, title: str, message: str) -> int:
        """Show an information dialog."""
        from ui.message_boxes import information
        return information(parent, title, message)
    
    @staticmethod
    def show_success(parent, title: str, message: str) -> int:
        """Show a success dialog."""
        from ui.message_boxes import information
        return information(parent, title, message)
    
    @staticmethod
    def show_warning(parent, title: str, message: str) -> int:
        """Show a warning dialog."""
        from ui.message_boxes import warning
        return warning(parent, title, message)
    
    @staticmethod
    def show_error(parent, title: str, message: str) -> int:
        """Show an error dialog."""
        from ui.message_boxes import critical
        return critical(parent, title, message)
    
    @staticmethod
    def show_confirm(parent, title: str, message: str) -> bool:
        """Show a confirmation dialog and return True if confirmed."""
        from PySide6.QtWidgets import QMessageBox
        return themed_question(parent, title, message) == QMessageBox.Yes
    
    @staticmethod
    def show_question(parent, title: str, message: str, buttons: list = None) -> int:
        """Show a question dialog with custom buttons."""
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        
        if buttons:
            msg_box.setStandardButtons(QMessageBox.NoButton)
            for button_text, button_role in buttons:
                msg_box.addButton(button_text, button_role)
        else:
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        
        apply_message_box_theme(msg_box, QMessageBox.Question)
        
        return msg_box.exec()


class InputDialog(QDialog):
    """Custom input dialog for getting user input."""
    
    def __init__(self, title: str, label: str, default_value: str = "", parent=None):
        super().__init__(parent)
        self.title = title
        self.label_text = label
        self.default_value = default_value
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the input dialog."""
        self.setWindowTitle(self.title)
        self.setModal(True)
        self.setFixedSize(400, 200)
        
        # Apply dark theme styling
        self.setStyleSheet(theme.dialog_page_style())
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Label
        label = QLabel(self.label_text)
        label.setStyleSheet(theme.master_form_field_label_style())
        layout.addWidget(label)
        
        # Input field
        self.input_field = QLineEdit()
        self.input_field.setText(self.default_value)
        self.input_field.setStyleSheet(theme.sales_compact_input_style())
        layout.addWidget(self.input_field)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(theme.sales_primary_button_style())
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(theme.sales_compact_button_style())
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def get_value(self) -> str:
        """Get the input value."""
        return self.input_field.text().strip()


class MultiInputDialog(QDialog):
    """Custom dialog for getting multiple inputs."""
    
    def __init__(self, title: str, fields: list, parent=None):
        super().__init__(parent)
        self.title = title
        self.fields = fields  # List of tuples: (label, default_value, input_type)
        self.input_widgets = {}
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the multi-input dialog."""
        self.setWindowTitle(self.title)
        self.setModal(True)
        self.setFixedSize(450, 300)
        
        # Apply dark theme styling
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS['surface']};
                color: {COLORS['text_primary']};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Input fields
        for label, default_value, input_type in self.fields:
            field_label = QLabel(label)
            field_label.setStyleSheet(f"""
                QLabel {{
                    color: {COLORS['text_primary']};
                    font-size: 13px;
                    font-weight: 500;
                    margin-bottom: 5px;
                }}
            """)
            layout.addWidget(field_label)
            
            if input_type == "text":
                input_widget = QLineEdit()
                input_widget.setText(default_value)
                input_widget.setStyleSheet(f"""
                    QLineEdit {{
                        background-color: {COLORS['card']};
                        color: {COLORS['text_primary']};
                        border: 1px solid {COLORS['border']};
                        padding: 8px 12px;
                        border-radius: 6px;
                        font-size: 13px;
                    }}
                    QLineEdit:focus {{
                        border-color: {COLORS['primary']};
                    }}
                """)
            elif input_type == "multiline":
                input_widget = QTextEdit()
                input_widget.setPlainText(default_value)
                input_widget.setFixedHeight(80)
                input_widget.setStyleSheet(f"""
                    QTextEdit {{
                        background-color: {COLORS['card']};
                        color: {COLORS['text_primary']};
                        border: 1px solid {COLORS['border']};
                        padding: 8px 12px;
                        border-radius: 6px;
                        font-size: 13px;
                    }}
                    QTextEdit:focus {{
                        border-color: {COLORS['primary']};
                    }}
                """)
            else:
                # Default to text input
                input_widget = QLineEdit()
                input_widget.setText(default_value)
                input_widget.setStyleSheet(f"""
                    QLineEdit {{
                        background-color: {COLORS['card']};
                        color: {COLORS['text_primary']};
                        border: 1px solid {COLORS['border']};
                        padding: 8px 12px;
                        border-radius: 6px;
                        font-size: 13px;
                    }}
                    QLineEdit:focus {{
                        border-color: {COLORS['primary']};
                    }}
                """)
            
            self.input_widgets[label] = input_widget
            layout.addWidget(input_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 500;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary_dark']};
            }}
        """)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['button_default']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 500;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['button_hover']};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def get_values(self) -> dict:
        """Get all input values as a dictionary."""
        values = {}
        for label, input_widget in self.input_widgets.items():
            if isinstance(input_widget, QTextEdit):
                values[label] = input_widget.toPlainText().strip()
            else:
                values[label] = input_widget.text().strip()
        return values


class ProgressDialog(QDialog):
    """Simple progress dialog for long operations."""
    
    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.message = message
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the progress dialog."""
        self.setWindowTitle(self.title)
        self.setModal(True)
        self.setFixedSize(400, 120)
        
        # Apply dark theme styling
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS['surface']};
                color: {COLORS['text_primary']};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Message
        message_label = QLabel(self.message)
        message_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_primary']};
                font-size: 14px;
            }}
        """)
        layout.addWidget(message_label)
        
        # Progress indicator (simple label for now)
        progress_label = QLabel("Processing...")
        progress_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                font-size: 12px;
                font-style: italic;
            }}
        """)
        layout.addWidget(progress_label)
        
        layout.addStretch()
    
    def update_message(self, message: str):
        """Update the progress message."""
        # Find and update the message label
        for child in self.children():
            if isinstance(child, QLabel) and child.text().startswith("Processing"):
                child.setText(message)
                break
