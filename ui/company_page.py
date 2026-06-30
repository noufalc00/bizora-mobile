"""
Company Page for the Accounting Desktop Application.
Handles company creation and management with form validation.
"""

from bizora_core.company_limits import company_limit_message, company_limit_reached
from config import COMPANY_VISIBILITY_NORMAL

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QMessageBox
from PySide6.QtCore import Qt, Signal

from ui import theme
from components import (
    FormSectionWidget, FormRowWidget, LabeledInputWidget,
    PrimaryButton, SecondaryButton, DangerButton, FormButtonGroup,
    DialogHelper
)
from db import Database
from bizora_core.company_logic import CompanyLogic
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin


class CompanyPageWidget(UiMemoryMixin, QWidget):
    """Company page widget for creating and managing companies."""
    
    company_saved = Signal()
    
    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db or Database()
        self.company_logic = CompanyLogic(self.db)
        self.setup_ui()
        self.setup_connections()
        self.load_existing_companies()
        self._init_ui_memory(restore_geometry=False, save_geometry=False)
    
    def setup_ui(self):
        """Setup the company page UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Header
        header_widget = self.create_header()
        layout.addWidget(header_widget)
        
        # Main form
        self.form_widget = self.create_company_form()
        layout.addWidget(self.form_widget)
        
        # Existing companies section
        self.companies_widget = self.create_existing_companies_section()
        layout.addWidget(self.companies_widget)
        
        layout.addStretch()
    
    def create_header(self) -> QWidget:
        """Create the header section."""
        header_widget = QWidget()
        header_widget.setFixedHeight(80)
        
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title_label = QLabel("Company Management")
        colors = theme.legacy_colors()
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {colors['text_primary']};
                font-size: 24px;
                font-weight: bold;
                background: transparent;
                border: none;
            }}
        """)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Description
        desc_label = QLabel("Create and manage your business company information")
        desc_label.setStyleSheet(f"""
            QLabel {{
                color: {colors['text_secondary']};
                font-size: 14px;
                background: transparent;
                border: none;
            }}
        """)
        header_layout.addWidget(desc_label)
        
        return header_widget
    
    def create_company_form(self) -> FormSectionWidget:
        """Create the company information form."""
        form = FormSectionWidget("Company Information")
        
        # Basic Information Row
        basic_row = form.create_row()
        self.business_name_input = basic_row.add_input("Business Name *", "text", 2)
        self.phone_input = basic_row.add_input("Phone Number", "text", 1)
        
        # GSTIN and Email Row
        contact_row = form.create_row()
        self.gstin_input = contact_row.add_input("GSTIN", "text", 1)
        self.gst_type_input = contact_row.add_input("GST Registration Type", "combo", 1)
        self.email_input = contact_row.add_input("Email", "text", 1)
        
        # Business Type and Category Row
        type_row = form.create_row()
        self.business_type_input = type_row.add_input("Business Type", "combo", 1)
        self.business_category_input = type_row.add_input("Business Category", "combo", 1)
        
        # Setup combo boxes
        self.business_type_input.input_widget.addItems([
            "Select...", "Proprietorship", "Partnership", "Private Limited", "Public Limited", "LLP", "Others"
        ])
        self.business_category_input.input_widget.addItems([
            "Select...", "Manufacturing", "Trading", "Services", "Retail", "Wholesale", "Others"
        ])
        self.gst_type_input.input_widget.addItems(["Regular", "Composition"])
        
        # Address Row
        address_row = form.create_row()
        self.address_input = address_row.add_input("Address", "multiline", 2)
        
        # State and Pincode Row
        location_row = form.create_row()
        self.state_input = location_row.add_input("State", "text", 1)
        self.pincode_input = location_row.add_input("Pincode", "text", 1)
        
        # Set placeholders
        self.business_name_input.set_placeholder("Enter your business name")
        self.phone_input.set_placeholder("Enter phone number")
        self.gstin_input.set_placeholder("Enter GSTIN number")
        self.email_input.set_placeholder("Enter email address")
        self.address_input.set_placeholder("Enter complete business address")
        self.state_input.set_placeholder("Enter state")
        self.pincode_input.set_placeholder("Enter pincode")
        
        # Form buttons
        button_group = FormButtonGroup()
        self.save_btn = button_group.get_save_button()
        self.clear_btn = button_group.get_clear_button()
        
        form.add_row(button_group)
        
        return form
    
    def create_existing_companies_section(self) -> FormSectionWidget:
        """Create the existing companies section."""
        section = FormSectionWidget("Existing Companies")
        
        # Companies list will be populated dynamically
        self.companies_list_widget = QWidget()
        self.companies_layout = QVBoxLayout(self.companies_list_widget)
        self.companies_layout.setContentsMargins(0, 0, 0, 0)
        self.companies_layout.setSpacing(8)
        
        section.add_row(self.companies_list_widget)
        
        return section
    
    def setup_connections(self):
        """Setup signal connections."""
        self.save_btn.clicked.connect(self.save_company)
        self.clear_btn.clicked.connect(self.clear_form)
    
    def validate_form(self) -> tuple:
        """Validate the form and return (is_valid, error_message)."""
        business_name = self.business_name_input.get_value().strip()
        
        # Check required fields
        if not business_name:
            return False, "Business Name is required"
        
        # Check for duplicate company name
        if self.company_logic.validate_company_data({'business_name': business_name})['success'] is False:
            error_msg = self.company_logic.validate_company_data({'business_name': business_name})['message']
            if 'already exists' in error_msg:
                return False, error_msg
        
        # Validate email format if provided
        email = self.email_input.get_value().strip()
        if email and not self.validate_email(email):
            return False, "Please enter a valid email address"
        
        # Validate phone number if provided
        phone = self.phone_input.get_value().strip()
        if phone and not self.validate_phone(phone):
            return False, "Please enter a valid phone number"
        
        # Validate pincode if provided
        pincode = self.pincode_input.get_value().strip()
        if pincode and not pincode.isdigit():
            return False, "Pincode must contain only numbers"
        
        return True, ""
    
    def validate_email(self, email: str) -> bool:
        """Validate email format."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def validate_phone(self, phone: str) -> bool:
        """Validate phone number format."""
        # Remove common formatting characters
        cleaned = phone.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        return cleaned.isdigit() and 10 <= len(cleaned) <= 15
    
    def save_company(self):
        """Save the company information."""
        if self._company_limit_reached():
            QMessageBox.warning(
                self,
                "Limit Reached",
                company_limit_message(COMPANY_VISIBILITY_NORMAL),
            )
            return

        # Validate form
        is_valid, error_message = self.validate_form()
        if not is_valid:
            DialogHelper.show_error(self, "Validation Error", error_message)
            return
        
        # Collect form data
        company_data = {
            'business_name': self.business_name_input.get_value().strip(),
            'phone_number': self.phone_input.get_value().strip(),
            'gstin': self.gstin_input.get_value().strip(),
            'gst_type': self.gst_type_input.get_value() or 'Regular',
            'email': self.email_input.get_value().strip(),
            'business_type': self.business_type_input.get_value(),
            'business_category': self.business_category_input.get_value(),
            'address': self.address_input.get_value().strip(),
            'state': self.state_input.get_value().strip(),
            'pincode': self.pincode_input.get_value().strip()
        }
        
        # Remove "Select..." values
        if company_data['business_type'] == "Select...":
            company_data['business_type'] = ""
        if company_data['business_category'] == "Select...":
            company_data['business_category'] = ""
        
        # Validate company data
        validation_result = self.company_logic.validate_company_data(company_data)
        
        if not validation_result['success']:
            DialogHelper.show_error(self, "Validation Error", validation_result['message'])
            return
        
        # Create company
        create_result = self.company_logic.create_company(company_data)
        
        if create_result['success']:
            DialogHelper.show_success(self, "Success", f"Company '{company_data['business_name']}' has been created successfully!")
            self.company_saved.emit()
            self.clear_form()
            self.load_existing_companies()
        else:
            DialogHelper.show_error(self, "Database Error", create_result['message'])

    def _company_limit_reached(self):
        """Return True when the normal company pool has reached its cap."""
        try:
            return company_limit_reached(self.db.db_path, COMPANY_VISIBILITY_NORMAL)
        except Exception as error:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Unable to check company limit:\n{error}",
            )
            return True
    
    def clear_form(self):
        """Clear all form fields."""
        self.form_widget.clear_all()
        # Reset combo boxes to "Select..."
        self.business_type_input.input_widget.setCurrentIndex(0)
        self.business_category_input.input_widget.setCurrentIndex(0)
        self.gst_type_input.input_widget.setCurrentText("Regular")
    
    def load_existing_companies(self):
        """Load and display existing companies."""
        # Clear existing companies display
        for i in reversed(range(self.companies_layout.count())):
            child = self.companies_layout.itemAt(i).widget()
            if child:
                child.setParent(None)
        
        # Load companies from database
        result = self.company_logic.get_all_companies(
            visibility=COMPANY_VISIBILITY_NORMAL,
        )
        
        if not result['success']:
            companies = []
        else:
            companies = result['data']
        
        if not companies:
            colors = theme.legacy_colors()
            # Show no companies message
            no_companies_label = QLabel("No companies created yet")
            no_companies_label.setStyleSheet(f"""
                QLabel {{
                    color: {colors['text_secondary']};
                    font-style: italic;
                    padding: 20px;
                    text-align: center;
                }}
            """)
            no_companies_label.setAlignment(Qt.AlignCenter)
            self.companies_layout.addWidget(no_companies_label)
        else:
            # Display each company
            for company in companies:
                company_widget = self.create_company_item(company)
                self.companies_layout.addWidget(company_widget)
    
    def create_company_item(self, company: dict) -> QWidget:
        """Create a widget to display a company item."""
        colors = theme.legacy_colors()
        item_widget = QFrame()
        item_widget.setStyleSheet(f"""
            QFrame {{
                background-color: {colors['card']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 12px;
            }}
            QFrame:hover {{
                border-color: {colors['border_focus']};
            }}
        """)
        
        item_layout = QVBoxLayout(item_widget)
        item_layout.setContentsMargins(12, 12, 12, 12)
        item_layout.setSpacing(8)
        
        # Company name and status
        header_layout = QHBoxLayout()
        
        name_label = QLabel(company['business_name'])
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {colors['text_primary']};
                font-size: 14px;
                font-weight: bold;
            }}
        """)
        header_layout.addWidget(name_label)
        
        header_layout.addStretch()
        
        # Active status indicator
        if company.get('is_active', 0):
            status_label = QLabel("Active")
            status_label.setStyleSheet(f"""
                QLabel {{
                    color: {colors['success']};
                    font-size: 12px;
                    font-weight: 600;
                    padding: 4px 8px;
                    background-color: rgba(76, 175, 80, 0.1);
                    border-radius: 4px;
                }}
            """)
            header_layout.addWidget(status_label)
        
        item_layout.addLayout(header_layout)
        
        # Company details
        details = []
        if company.get('phone_number'):
            details.append(f"Phone: {company['phone_number']}")
        if company.get('email'):
            details.append(f"Email: {company['email']}")
        if company.get('gstin'):
            details.append(f"GSTIN: {company['gstin']}")
        details.append(f"GST Type: {company.get('gst_type') or 'Regular'}")
        if company.get('business_type'):
            details.append(f"Type: {company['business_type']}")
        
        if details:
            details_text = " | ".join(details)
            details_label = QLabel(details_text)
            details_label.setStyleSheet(f"""
                QLabel {{
                    color: {colors['text_secondary']};
                    font-size: 12px;
                }}
            """)
            item_layout.addWidget(details_label)
        
        # Address
        if company.get('address'):
            address_label = QLabel(f"Address: {company['address']}")
            address_label.setStyleSheet(f"""
                QLabel {{
                    color: {colors['text_secondary']};
                    font-size: 12px;
                }}
            """)
            item_layout.addWidget(address_label)
        
        return item_widget