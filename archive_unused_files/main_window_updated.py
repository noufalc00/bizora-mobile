"""
Main window implementation for the Accounting Desktop Application.
Uses QMainWindow with sidebar, topbar, and QStackedWidget for modular UI management.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, Signal

from config import APP_NAME, COLORS, WINDOW_SIZE, active_company_manager
from components.sidebar import Sidebar
from components.topbar import TopbarWidget
from .dashboard import DashboardWidget
from .company_page import CompanyPageWidget
from .new_company_page import NewCompanyPageWidget
from .open_company_page import OpenCompanyPageWidget
from .products import ProductsWidget
from .debitor_creditor import DebitorCreditorWidget


class MainWindow(QMainWindow):
    """Main application window with sidebar, topbar, and stacked widgets."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1200, 800)
        
        # Initialize UI components
        self.stack_widget = QStackedWidget()
        
        # Setup UI
        self.setup_ui()
        
        # Connect signals
        self.connect_signals()
        
        # Apply global message box styling
        self.setup_global_dialog_styling()
        
        # Show dashboard by default
        self.show_dashboard()
    
    def setup_ui(self):
        """Setup main UI layout with horizontal structure."""
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main horizontal layout: left sidebar, right main area
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Left: Sidebar
        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)
        
        # Right: Main area with vertical layout
        main_area_widget = QWidget()
        main_area_layout = QVBoxLayout(main_area_widget)
        main_area_layout.setContentsMargins(0, 0, 0, 0)
        main_area_layout.setSpacing(0)
        
        # Topbar at top of main area
        self.topbar = TopbarWidget()
        main_area_layout.addWidget(self.topbar)
        
        # QStackedWidget workspace below topbar
        self.stack_widget = QStackedWidget()
        self.stack_widget.setStyleSheet(f"""
            QStackedWidget {{
                background-color: {COLORS['background']};
            }}
        """)
        main_area_layout.addWidget(self.stack_widget)
        
        # Add main area to main layout
        main_layout.addWidget(main_area_widget, 1)
        
        # Setup workspace pages
        self.setup_workspace_pages()
    
    def setup_workspace_pages(self):
        """Setup pages for the QStackedWidget workspace."""
        # Create dashboard page (initial page)
        self.dashboard_widget = DashboardWidget()
        self.stack_widget.addWidget(self.dashboard_widget)
        
        # Create company page
        self.company_widget = CompanyPageWidget()
        self.stack_widget.addWidget(self.company_widget)
        
        # Create new company page
        self.new_company_widget = NewCompanyPageWidget()
        self.stack_widget.addWidget(self.new_company_widget)
        
        # Create open company page
        self.open_company_widget = OpenCompanyPageWidget()
        self.stack_widget.addWidget(self.open_company_widget)
        
        # Create products page
        self.products_widget = ProductsWidget()
        self.stack_widget.addWidget(self.products_widget)
        
        # Create debitor/creditor page
        self.debitor_creditor_widget = DebitorCreditorWidget()
        self.stack_widget.addWidget(self.debitor_creditor_widget)
        
        # Add pages dictionary
        self.pages = {
            'Dashboard': self.dashboard_widget,
            'Company': self.company_widget,
            'New Company': self.new_company_widget,
            'Open Company': self.open_company_widget,
            'Product/Service': self.products_widget,
            'Debitor/Creditor': self.debitor_creditor_widget
        }
    
    def connect_signals(self):
        """Connect signals between components."""
        # Sidebar page changes
        self.sidebar.page_changed.connect(self.on_page_changed)
        self.sidebar.company_closed.connect(self.on_company_closed)
        
        # Topbar search
        self.topbar.search_requested.connect(self.on_search_requested)
        
        # Company page signals
        self.company_widget.company_saved.connect(self.on_company_saved)
        
        # New company page signals
        self.new_company_widget.company_saved.connect(self.on_company_saved)
        
        # Open company page signals
        self.open_company_widget.company_selected.connect(self.on_company_selected)
    
    def on_page_changed(self, page_name: str):
        """Handle page change from sidebar."""
        if page_name == "Company":
            self.show_company()
        elif page_name == "New Company":
            self.show_new_company()
        elif page_name == "Open Company":
            self.show_open_company()
        elif page_name == "Product/Service":
            self.show_products()
        elif page_name == "Debitor/Creditor":
            self.show_debitor_creditor()
        else:
            # For other pages, show dashboard for now
            self.show_dashboard()
    
    def on_search_requested(self, search_text: str):
        """Handle search request from topbar."""
        # Placeholder for search functionality
        print(f"Search requested: {search_text}")
    
    def on_company_saved(self):
        """Handle company saved event."""
        # Update topbar to show new active company
        self.topbar.update_active_company()
    
    def on_company_selected(self, company_data):
        """Handle company selection event."""
        if company_data:
            # Company was successfully opened, update topbar and show dashboard
            self.topbar.update_active_company()
            self.show_dashboard()
        else:
            # User cancelled, show dashboard
            self.show_dashboard()
    
    def on_company_closed(self):
        """Handle company close event."""
        # Update topbar to reflect no active company
        self.topbar.update_active_company()
        self.show_dashboard()
    
    def show_dashboard(self):
        """Show dashboard page."""
        self.stack_widget.setCurrentWidget(self.dashboard_widget)
    
    def show_company(self):
        """Show company page."""
        self.stack_widget.setCurrentWidget(self.company_widget)
    
    def show_new_company(self):
        """Show new company page."""
        self.stack_widget.setCurrentWidget(self.new_company_widget)
    
    def show_open_company(self):
        """Show open company page."""
        # Reload companies list each time to show latest data
        self.open_company_widget.load_companies()
        self.stack_widget.setCurrentWidget(self.open_company_widget)
    
    def show_products(self):
        """Show products/services page."""
        # Reload products list each time to show latest data
        self.products_widget.load_products()
        self.stack_widget.setCurrentWidget(self.products_widget)
    
    def show_debitor_creditor(self):
        """Show debitor/creditor page."""
        # Reload parties list each time to show latest data
        self.debitor_creditor_widget.load_parties()
        self.stack_widget.setCurrentWidget(self.debitor_creditor_widget)
    
    def setup_global_dialog_styling(self):
        """Apply global styling to all QMessageBox dialogs."""
        self.setStyleSheet("""
            QMessageBox {
                background-color: #2d3748;
                color: #ffffff;
                border: 1px solid #4b5563;
                border-radius: 6px;
                padding: 20px;
                font-size: 14px;
            }
            QMessageBox QLabel {
                color: #ffffff;
                font-size: 14px;
            }
            QMessageBox QPushButton {
                background-color: #4b5563;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
            QPushButton:focus {
                border: 2px solid #60a5fa;
            }
        """)
    
    def get_current_page(self) -> str:
        """Get the name of the current page."""
        current_widget = self.stack_widget.currentWidget()
        for name, widget in self.pages.items():
            if widget == current_widget:
                return name
        return "Unknown"
    
    def add_page(self, name: str, widget: QWidget):
        """Add a new page to the workspace."""
        self.pages[name] = widget
        self.stack_widget.addWidget(widget)
