"""
Sidebar component with accordion-style navigation menu for the Accounting Desktop Application.
Provides main menu navigation with icons and modern styling.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QScrollArea, QLabel
)
from PySide6.QtCore import Qt, Signal

from config import COLORS


class SidebarWidget(QWidget):
    """Sidebar with accordion-style navigation menu."""
    
    page_changed = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.current_open_section = None
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the sidebar UI."""
        self.setFixedWidth(280)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['sidebar']};
                border-right: 1px solid {COLORS['border']};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # App title
        title_widget = self.create_app_title()
        layout.addWidget(title_widget)
        
        # Menu scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QScrollBar:vertical {{
                background-color: {COLORS['surface']};
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['border']};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {COLORS['border_focus']};
            }}
        """)
        
        menu_widget = QWidget()
        menu_layout = QVBoxLayout(menu_widget)
        menu_layout.setContentsMargins(10, 10, 10, 10)
        menu_layout.setSpacing(2)
        
        # Create menu sections
        self.menu_sections = {}
        menu_items = {
            "Dashboard": ["Overview", "Quick Stats", "Recent Activity"],
            "File": ["New", "Open", "Save", "Print", "Exit"],
            "Masters": ["Company", "Accounts", "Groups", "Items", "Categories"],
            "Entry": ["Vouchers", "Receipts", "Payments", "Journal"],
            "Books": ["Cash Book", "Bank Book", "Ledger", "Trial Balance"],
            "Reports": ["Balance Sheet", "Profit & Loss", "Cash Flow", "Tax Reports"],
            "Utilities": ["Backup", "Restore", "Import", "Export"],
            "Settings": ["General", "Database", "Security", "Appearance"],
            "Windows": ["Cascade", "Tile", "Minimize All"],
            "About Me": ["Company Info", "User Profile", "Preferences"]
        }
        
        # Icons for main menu items - using Unicode symbols
        menu_icons = {
            "Dashboard": "Dashboard",
            "File": "File", 
            "Masters": "Masters",
            "Entry": "Entry",
            "Books": "Books",
            "Reports": "Reports",
            "Utilities": "Utilities",
            "Settings": "Settings",
            "Windows": "Windows",
            "About Me": "About"
        }
        
        for section_name, subsections in menu_items.items():
            icon = menu_icons.get(section_name, "")
            section_widget = self.create_menu_section(section_name, subsections, icon)
            self.menu_sections[section_name] = section_widget
            menu_layout.addWidget(section_widget)
        
        menu_layout.addStretch()
        scroll_area.setWidget(menu_widget)
        layout.addWidget(scroll_area)
    
    def create_app_title(self) -> QWidget:
        """Create application title widget."""
        title_widget = QWidget()
        title_widget.setFixedHeight(60)
        title_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['primary']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(15, 0, 15, 0)
        
        title_label = QLabel("Accounting Pro")
        title_label.setStyleSheet(f"""
            QLabel {{
                color: white;
                font-size: 16px;
                font-weight: bold;
            }}
        """)
        title_layout.addWidget(title_label)
        
        return title_widget
    
    def create_menu_section(self, section_name: str, subsections: list, icon: str = "") -> QWidget:
        """Create a menu section with accordion behavior."""
        section_widget = QFrame()
        section_widget.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border-radius: 6px;
                margin: 3px 0;
            }}
        """)
        
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)
        
        # Section header button with icon
        icon_text = self.get_icon_text(icon)
        display_text = f"{icon_text} {section_name}" if icon_text else section_name
        header_btn = QPushButton(display_text)
        header_btn.setObjectName(f"header_{section_name}")
        header_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_primary']};
                border: none;
                padding: 18px 20px;
                text-align: left;
                border-radius: 6px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {COLORS['button_hover']};
                color: {COLORS['primary']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['button_pressed']};
            }}
        """)
        header_btn.clicked.connect(lambda: self.toggle_section(section_name))
        section_layout.addWidget(header_btn)
        
        # Subsections container
        subsections_widget = QWidget()
        subsections_widget.setObjectName(f"subsections_{section_name}")
        subsections_widget.setVisible(False)  # Initially collapsed
        
        subsections_layout = QVBoxLayout(subsections_widget)
        subsections_layout.setContentsMargins(25, 0, 0, 0)
        subsections_layout.setSpacing(1)
        
        # Create subsection buttons
        for subsection in subsections:
            sub_btn = QPushButton(subsection)
            sub_btn.setObjectName(f"sub_{subsection.replace(' ', '_')}")
            sub_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {COLORS['text_secondary']};
                    border: none;
                    padding: 14px 22px;
                    text-align: left;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['button_hover']};
                    color: {COLORS['text_primary']};
                }}
                QPushButton:pressed {{
                    background-color: {COLORS['primary']};
                    color: white;
                }}
            """)
            sub_btn.clicked.connect(lambda checked, name=subsection: self.page_changed.emit(name))
            subsections_layout.addWidget(sub_btn)
        
        section_layout.addWidget(subsections_widget)
        
        # Store references
        section_widget.header_btn = header_btn
        section_widget.subsections_widget = subsections_widget
        
        return section_widget
    
    def toggle_section(self, section_name: str):
        """Toggle accordion section open/closed."""
        if self.current_open_section == section_name:
            # Close current section
            self.menu_sections[section_name].subsections_widget.setVisible(False)
            self.current_open_section = None
        else:
            # Close previous section if open
            if self.current_open_section:
                self.menu_sections[self.current_open_section].subsections_widget.setVisible(False)
            
            # Open new section
            self.menu_sections[section_name].subsections_widget.setVisible(True)
            self.current_open_section = section_name
    
    def open_section(self, section_name: str):
        """Open specific section."""
        if section_name in self.menu_sections:
            self.toggle_section(section_name)
    
    def get_icon_text(self, icon_name: str) -> str:
        """Get modern icon text for menu items."""
        # Using Unicode symbols for modern professional icons
        unicode_icons = {
            "Dashboard": "Dashboard",
            "File": "File", 
            "Masters": "Masters",
            "Entry": "Entry",
            "Books": "Books",
            "Reports": "Reports",
            "Utilities": "Utilities",
            "Settings": "Settings",
            "Windows": "Windows",
            "About": "About"
        }
        return unicode_icons.get(icon_name, "")
