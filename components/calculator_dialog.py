"""
Calculator dialog component for the Accounting Desktop Application.
Provides Windows Calculator style functionality with dark professional theme.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, 
    QLabel, QPushButton, QLineEdit, QFrame
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QFont, QKeyEvent

from config import COLORS
from ui import theme


class CalculatorDialog(QDialog):
    """Windows Calculator style dialog with dark professional theme."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calculator")
        self.setFixedSize(360, 500)
        self.setModal(False)  # Non-modal so it doesn't block the app
        
        # Calculator state
        self.current_input = "0"
        self.expression = ""
        self.operation = ""
        self.previous_input = ""
        self.new_number = True
        self.memory = 0
        
        self.setup_ui()
        self.setup_connections()
        self.setup_keyboard_support()
        
    def setup_ui(self):
        """Setup Windows Calculator style UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)
        
        self.setStyleSheet(theme.calculator_dialog_style())
        
        # Two-line display area (Windows Calculator style)
        display_container = QFrame()
        display_container.setStyleSheet(theme.calculator_display_frame_style())
        display_layout = QVBoxLayout(display_container)
        display_layout.setContentsMargins(10, 8, 10, 8)
        display_layout.setSpacing(2)
        
        # Expression line (top - shows operation history)
        self.expression_display = QLabel()
        self.expression_display.setAlignment(Qt.AlignRight)
        self.expression_display.setStyleSheet(theme.calculator_expression_style())
        self.expression_display.setText("")
        display_layout.addWidget(self.expression_display)
        
        # Main display line (bottom - shows current input/result)
        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setAlignment(Qt.AlignRight)
        self.display.setStyleSheet(theme.calculator_main_display_style())
        self.display.setText("0")
        display_layout.addWidget(self.display)
        
        layout.addWidget(display_container)
        
        # Button grid (Windows Calculator layout)
        button_layout = QGridLayout()
        button_layout.setSpacing(4)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        # Button definitions: (text, row, col, row_span, col_span, style_class)
        buttons = [
            # Row 0 - Memory and Clear
            ("MC", 0, 0, 1, 1, "memory"),
            ("MR", 0, 1, 1, 1, "memory"),
            ("M+", 0, 2, 1, 1, "memory"),
            ("M-", 0, 3, 1, 1, "memory"),
            ("C", 0, 4, 1, 1, "clear"),
            
            # Row 1 - Numbers and operations
            ("7", 1, 0, 1, 1, "number"),
            ("8", 1, 1, 1, 1, "number"),
            ("9", 1, 2, 1, 1, "number"),
            ("÷", 1, 3, 1, 1, "operation"),
            ("×", 1, 4, 1, 1, "operation"),
            
            # Row 2
            ("4", 2, 0, 1, 1, "number"),
            ("5", 2, 1, 1, 1, "number"),
            ("6", 2, 2, 1, 1, "number"),
            ("+", 2, 3, 1, 1, "operation"),
            ("-", 2, 4, 1, 1, "operation"),
            
            # Row 3
            ("1", 3, 0, 1, 1, "number"),
            ("2", 3, 1, 1, 1, "number"),
            ("3", 3, 2, 1, 1, "number"),
            ("±", 3, 3, 1, 1, "operation"),
            ("%", 3, 4, 1, 1, "operation"),
            
            # Row 4
            ("0", 4, 0, 1, 2, "number"),
            (".", 4, 2, 1, 1, "number"),
            ("=", 4, 3, 1, 2, "equals"),
        ]
        
        self.buttons = {}
        for text, row, col, row_span, col_span, style_class in buttons:
            btn = QPushButton(text)
            btn.setProperty("class", style_class)
            self.setup_button_style(btn, style_class)
            button_layout.addWidget(btn, row, col, row_span, col_span)
            self.buttons[text] = btn
        
        layout.addLayout(button_layout)
        
    def setup_keyboard_support(self):
        """Setup keyboard event handling with proper focus."""
        # Enable keyboard focus for the dialog
        self.setFocusPolicy(Qt.StrongFocus)
        # Make dialog accept focus when shown
        self.setAttribute(Qt.WA_ShowModal, False)
        
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard press events with improved mapping."""
        key = event.key()
        text = event.text()
        
        # Number keys (main keyboard only)
        if Qt.Key_0 <= key <= Qt.Key_9:
            num = key - Qt.Key_0
            self.number_clicked(num)
        # Decimal point (multiple keys)
        elif key == Qt.Key_Period or key == Qt.Key_Comma:
            self.decimal_clicked()
        # Operations with better handling
        elif key == Qt.Key_Plus:
            self.operation_clicked("+")
        elif key == Qt.Key_Minus:
            self.operation_clicked("-")
        elif key == Qt.Key_Asterisk or key == Qt.Key_multiply:
            self.operation_clicked("*")
        elif key == Qt.Key_Slash or key == Qt.Key_division:
            self.operation_clicked("/")
        # Handle equals key properly
        elif key == Qt.Key_Equal and not (event.modifiers() & Qt.ShiftModifier):
            self.equals_clicked()
        elif key == Qt.Key_Enter or key == Qt.Key_Return:
            self.equals_clicked()
        # Backspace for delete last digit
        elif key == Qt.Key_Backspace:
            self.backspace_clicked()
        # Escape for clear
        elif key == Qt.Key_Escape:
            self.clear_clicked()
        # Percentage
        elif key == Qt.Key_Percent:
            self.percentage_clicked()
        # Plus/minus toggle
        elif key == Qt.Key_F9:
            self.plus_minus_clicked()
        # Handle direct text input for numbers
        elif text and text.isdigit():
            self.number_clicked(int(text))
        else:
            # Pass to parent for other keys
            super().keyPressEvent(event)
    
    def backspace_clicked(self):
        """Handle backspace - remove last digit."""
        if not self.new_number and len(self.current_input) > 0:
            if len(self.current_input) == 1:
                self.current_input = "0"
                self.new_number = True
            else:
                self.current_input = self.current_input[:-1]
            self.update_display()
    
    def showEvent(self, event):
        """Handle dialog show event to ensure focus."""
        super().showEvent(event)
        self.setFocus()  # Ensure dialog has focus when shown
        
    def setup_button_style(self, button, style_class):
        """Apply theme-aware calculator keypad styling."""
        button.setProperty("calc_style_class", style_class)
        button.setStyleSheet(theme.calculator_button_style(style_class))

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(theme.calculator_dialog_style())
        for child in self.findChildren(QFrame):
            if child.layout() and self.display and child is self.display.parentWidget():
                child.setStyleSheet(theme.calculator_display_frame_style())
        self.expression_display.setStyleSheet(theme.calculator_expression_style())
        self.display.setStyleSheet(theme.calculator_main_display_style())
        for button in getattr(self, "buttons", {}).values():
            style_class = button.property("calc_style_class") or button.property("class")
            if style_class:
                button.setStyleSheet(theme.calculator_button_style(style_class))
    
    def setup_connections(self):
        """Setup button connections."""
        # Number buttons
        for i in range(10):
            self.buttons[str(i)].clicked.connect(lambda checked, num=i: self.number_clicked(num))
        
        # Decimal point
        self.buttons["."].clicked.connect(self.decimal_clicked)
        
        # Operation buttons
        self.buttons["+"].clicked.connect(lambda: self.operation_clicked("+"))
        self.buttons["-"].clicked.connect(lambda: self.operation_clicked("-"))
        self.buttons["×"].clicked.connect(lambda: self.operation_clicked("*"))
        self.buttons["÷"].clicked.connect(lambda: self.operation_clicked("/"))
        self.buttons["%"].clicked.connect(self.percentage_clicked)
        self.buttons["±"].clicked.connect(self.plus_minus_clicked)
        
        # Clear and equals
        self.buttons["C"].clicked.connect(self.clear_clicked)
        self.buttons["="].clicked.connect(self.equals_clicked)
        
        # Memory buttons
        self.buttons["MC"].clicked.connect(self.memory_clear)
        self.buttons["MR"].clicked.connect(self.memory_recall)
        self.buttons["M+"].clicked.connect(self.memory_add)
        self.buttons["M-"].clicked.connect(self.memory_subtract)
    
    def number_clicked(self, num):
        """Handle number button clicks - Windows Calculator style."""
        if self.new_number:
            self.current_input = str(num)
            self.new_number = False
        else:
            if self.current_input == "0":
                self.current_input = str(num)
            else:
                self.current_input += str(num)
        
        self.update_display()
    
    def decimal_clicked(self):
        """Handle decimal point click - Windows Calculator style."""
        if self.new_number:
            self.current_input = "0."
            self.new_number = False
        elif "." not in self.current_input:
            self.current_input += "."
        
        self.update_display()
    
    def operation_clicked(self, op):
        """Handle operation button clicks - Windows Calculator style."""
        if self.operation and not self.new_number:
            self.calculate_result()
        
        # Update expression display to show the operation
        if self.operation:
            # Show previous expression
            self.expression = f"{self.previous_input} {self.get_display_operator(self.operation)}"
        else:
            # Start new expression
            self.expression = f"{self.current_input} {self.get_display_operator(op)}"
        
        self.previous_input = self.current_input
        self.operation = op
        self.new_number = True
        self.update_display()
    
    def get_display_operator(self, op):
        """Convert internal operator to display operator."""
        operator_map = {
            "*": "×",
            "/": "÷",
            "+": "+",
            "-": "-"
        }
        return operator_map.get(op, op)
    
    def percentage_clicked(self):
        """Handle percentage calculation - Windows Calculator style."""
        try:
            current_value = float(self.current_input)
            if self.operation and self.previous_input:
                # Percentage of previous number
                result = float(self.previous_input) * (current_value / 100)
            else:
                # Simple percentage
                result = current_value / 100
            
            self.current_input = str(result)
            self.update_display()
        except ValueError:
            self.clear_clicked()
    
    def plus_minus_clicked(self):
        """Handle plus/minus toggle - Windows Calculator style."""
        try:
            current_value = float(self.current_input)
            self.current_input = str(-current_value)
            self.update_display()
        except ValueError:
            pass
    
    def clear_clicked(self):
        """Handle clear button - Windows Calculator style."""
        self.current_input = "0"
        self.previous_input = ""
        self.operation = ""
        self.expression = ""
        self.new_number = True
        self.update_display()
    
    def equals_clicked(self):
        """Handle equals button - Windows Calculator style."""
        if self.operation and self.previous_input:
            self.calculate_result()
    
    def calculate_result(self):
        """Calculate the result - Windows Calculator style."""
        try:
            prev_value = float(self.previous_input)
            current_value = float(self.current_input)
            
            if self.operation == "+":
                result = prev_value + current_value
            elif self.operation == "-":
                result = prev_value - current_value
            elif self.operation == "*":
                result = prev_value * current_value
            elif self.operation == "/":
                if current_value == 0:
                    self.current_input = "Error"
                    self.update_display()
                    self.new_number = True
                    return
                result = prev_value / current_value
            else:
                return
            
            # Format result
            if result.is_integer():
                self.current_input = str(int(result))
            else:
                self.current_input = f"{result:.10g}"
            
            # Update expression to show full calculation
            self.expression = f"{self.previous_input} {self.get_display_operator(self.operation)} {current_value} ="
            
            self.operation = ""
            self.previous_input = ""
            self.new_number = True
            self.update_display()
            
        except ValueError:
            self.current_input = "Error"
            self.update_display()
            self.new_number = True
    
    def update_display(self):
        """Update both displays - Windows Calculator style."""
        # Update main display
        self.display.setText(self.current_input)
        
        # Update expression display
        self.expression_display.setText(self.expression)
    
    # Memory functions
    def memory_clear(self):
        """Clear memory."""
        self.memory = 0
    
    def memory_recall(self):
        """Recall from memory."""
        self.current_input = str(self.memory)
        self.new_number = False
        self.update_display()
    
    def memory_add(self):
        """Add to memory."""
        try:
            self.memory += float(self.current_input)
        except ValueError:
            pass
    
    def memory_subtract(self):
        """Subtract from memory."""
        try:
            self.memory -= float(self.current_input)
        except ValueError:
            pass
