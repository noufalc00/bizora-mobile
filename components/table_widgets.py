"""
Table widgets component for the Accounting Desktop Application.
Provides reusable table widget helpers for data display.
"""

from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QLineEdit, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ui.theme import legacy_colors


def _C() -> dict[str, str]:
    return legacy_colors()


class DataTableWidget(QTableWidget):
    """Reusable data table widget with consistent styling and functionality."""
    
    row_selected = Signal(int)
    row_double_clicked = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_table()
        self.setup_connections()
    
    def setup_table(self):
        """Setup table with default styling and behavior."""
        # Basic table properties
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSortingEnabled(True)
        
        # Styling
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {_C()['surface']};
                color: {_C()['text_primary']};
                border: 1px solid {_C()['border']};
                gridline-color: {_C()['border']};
                selection-background-color: {_C()['primary']};
                selection-color: white;
                font-size: 13px;
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {_C()['border']};
            }}
            QTableWidget::item:selected {{
                background-color: {_C()['primary']};
                color: white;
            }}
            QTableWidget::item:hover {{
                background-color: {_C()['button_hover']};
            }}
            QHeaderView::section {{
                background-color: {_C()['card']};
                color: {_C()['text_primary']};
                padding: 10px 8px;
                border: 1px solid {_C()['border']};
                font-weight: bold;
                font-size: 13px;
            }}
            QHeaderView::section:horizontal {{
                border-left: none;
                border-right: none;
                border-top: none;
                border-bottom: 2px solid {_C()['primary']};
            }}
            QHeaderView::section:vertical {{
                border-left: none;
                border-right: none;
                border-top: none;
                border-bottom: none;
            }}
        """)
        
        # Header setup
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(40)
    
    def setup_connections(self):
        """Setup signal connections."""
        self.itemSelectionChanged.connect(self.on_selection_changed)
        self.itemDoubleClicked.connect(self.on_item_double_clicked)
    
    def on_selection_changed(self):
        """Handle selection changes."""
        selected_items = self.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            self.row_selected.emit(row)
    
    def on_item_double_clicked(self, item):
        """Handle double click events."""
        self.row_double_clicked.emit(item.row())
    
    def set_headers(self, headers: list):
        """Set table headers."""
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
    
    def add_row(self, data: list, alignment: list = None):
        """Add a new row with data."""
        row_position = self.rowCount()
        self.insertRow(row_position)
        
        for col, value in enumerate(data):
            item = QTableWidgetItem(str(value))
            
            # Set alignment if specified
            if alignment and col < len(alignment):
                item.setTextAlignment(alignment[col])
            
            # Set numeric alignment for numeric data
            if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit()):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            self.setItem(row_position, col, item)
        
        return row_position
    
    def update_row(self, row: int, data: list):
        """Update existing row data."""
        for col, value in enumerate(data):
            if col < self.columnCount():
                item = self.item(row, col)
                if item is None:
                    item = QTableWidgetItem(str(value))
                    self.setItem(row, col, item)
                else:
                    item.setText(str(value))
    
    def clear_data(self):
        """Clear all data but keep headers."""
        self.setRowCount(0)
    
    def get_selected_row_data(self) -> list:
        """Get data from the selected row."""
        selected_items = self.selectedItems()
        if not selected_items:
            return []
        
        row = selected_items[0].row()
        row_data = []
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item:
                row_data.append(item.text())
            else:
                row_data.append("")
        
        return row_data
    
    def get_all_data(self) -> list:
        """Get all data from the table."""
        all_data = []
        for row in range(self.rowCount()):
            row_data = []
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    row_data.append(item.text())
                else:
                    row_data.append("")
            all_data.append(row_data)
        
        return all_data
    
    def auto_resize_columns(self):
        """Automatically resize columns to fit content."""
        self.resizeColumnsToContents()
    
    def set_column_widths(self, widths: list):
        """Set specific column widths."""
        for col, width in enumerate(widths):
            if col < self.columnCount():
                self.setColumnWidth(col, width)


class TableWithControlsWidget(QWidget):
    """Table widget with search, filter, and action controls."""
    
    def __init__(self, headers: list, parent=None):
        super().__init__(parent)
        self.headers = headers
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the table with controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # Controls section
        controls_widget = self.create_controls_widget()
        layout.addWidget(controls_widget)
        
        # Table
        self.table = DataTableWidget()
        self.table.set_headers(self.headers)
        layout.addWidget(self.table)
        
        # Status section
        status_widget = self.create_status_widget()
        layout.addWidget(status_widget)
    
    def create_controls_widget(self) -> QWidget:
        """Create the controls section."""
        controls_widget = QFrame()
        controls_widget.setStyleSheet(f"""
            QFrame {{
                background-color: {_C()['surface']};
                border: 1px solid {_C()['border']};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 5, 10, 5)
        controls_layout.setSpacing(10)
        
        # Search
        search_label = QLabel("Search:")
        search_label.setStyleSheet(f"""
            QLabel {{
                color: {_C()['text_primary']};
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        controls_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to search...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {_C()['card']};
                color: {_C()['text_primary']};
                border: 1px solid {_C()['border']};
                padding: 6px 10px;
                border-radius: 4px;
                font-size: 12px;
                min-width: 200px;
            }}
            QLineEdit:focus {{
                border-color: {_C()['primary']};
            }}
        """)
        self.search_input.textChanged.connect(self.on_search_changed)
        controls_layout.addWidget(self.search_input)
        
        controls_layout.addStretch()
        
        # Filter
        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet(f"""
            QLabel {{
                color: {_C()['text_primary']};
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        controls_layout.addWidget(filter_label)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Active", "Inactive"])
        self.filter_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {_C()['card']};
                color: {_C()['text_primary']};
                border: 1px solid {_C()['border']};
                padding: 6px 10px;
                border-radius: 4px;
                font-size: 12px;
                min-width: 100px;
            }}
        """)
        self.filter_combo.currentTextChanged.connect(self.on_filter_changed)
        controls_layout.addWidget(self.filter_combo)
        
        controls_layout.addStretch()
        
        # Action buttons
        self.add_btn = QPushButton("Add")
        self.add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_C()['success']};
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: #45a049;
            }}
        """)
        controls_layout.addWidget(self.add_btn)
        
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_C()['primary']};
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {_C()['primary_dark']};
            }}
        """)
        controls_layout.addWidget(self.edit_btn)
        
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_C()['error']};
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: #da190b;
            }}
        """)
        controls_layout.addWidget(self.delete_btn)
        
        return controls_widget
    
    def create_status_widget(self) -> QWidget:
        """Create the status section."""
        status_widget = QFrame()
        status_widget.setStyleSheet(f"""
            QFrame {{
                background-color: {_C()['surface']};
                border: 1px solid {_C()['border']};
                border-radius: 6px;
                padding: 8px 10px;
            }}
        """)
        
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(10, 5, 10, 5)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {_C()['text_secondary']};
                font-size: 12px;
            }}
        """)
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        self.record_count_label = QLabel("0 records")
        self.record_count_label.setStyleSheet(f"""
            QLabel {{
                color: {_C()['text_secondary']};
                font-size: 12px;
            }}
        """)
        status_layout.addWidget(self.record_count_label)
        
        return status_widget
    
    def on_search_changed(self, text: str):
        """Handle search text changes."""
        # This can be overridden in subclasses to implement search functionality
        self.update_status(f"Searching: {text}")
    
    def on_filter_changed(self, filter_text: str):
        """Handle filter changes."""
        # This can be overridden in subclasses to implement filter functionality
        self.update_status(f"Filter: {filter_text}")
    
    def update_status(self, message: str):
        """Update status message."""
        self.status_label.setText(message)
    
    def update_record_count(self, count: int):
        """Update record count display."""
        self.record_count_label.setText(f"{count} records")
    
    def add_data(self, data: list):
        """Add data to the table."""
        for row_data in data:
            self.table.add_row(row_data)
        self.update_record_count(self.table.rowCount())
    
    def clear_data(self):
        """Clear all table data."""
        self.table.clear_data()
        self.update_record_count(0)
        self.update_status("Ready")
    
    def get_selected_data(self) -> list:
        """Get selected row data."""
        return self.table.get_selected_row_data()
    
    def get_table(self) -> DataTableWidget:
        """Get the underlying table widget."""
        return self.table


class SimpleTableWidget(QWidget):
    """Simple table widget for basic data display."""
    
    def __init__(self, headers: list, parent=None):
        super().__init__(parent)
        self.headers = headers
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the simple table."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.table = DataTableWidget()
        self.table.set_headers(self.headers)
        layout.addWidget(self.table)
    
    def add_row(self, data: list):
        """Add a row to the table."""
        self.table.add_row(data)
    
    def clear_data(self):
        """Clear all data."""
        self.table.clear_data()
    
    def get_table(self) -> DataTableWidget:
        """Get the table widget."""
        return self.table
