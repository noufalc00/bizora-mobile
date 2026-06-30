"""
Edit Company dialog for the Accounting Desktop Application.
Provides a professional interface to edit existing company details.
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QScrollArea, QGridLayout, QTextEdit, QLineEdit, QWidget, QMessageBox, QFileDialog, QCheckBox
from PySide6.QtCore import Qt, Signal, QObject, QEvent
from PySide6.QtGui import QPixmap
import os
from ui import theme
from ui.checkbox_style import create_checkbox
from db import Database
from bizora_core.company_logic import CompanyLogic
from ui.theme import GST_STATE_CODES
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class FormNavigationFilter(QObject):

    def __init__(self, parent_dialog, field_order):
        super().__init__(parent_dialog)
        self.parent_dialog = parent_dialog
        self.field_order = field_order

    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return False
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if obj is self.parent_dialog.address:
                return False
            if obj in (self.parent_dialog.logo_button, self.parent_dialog.signature_button):
                current_index = self._index_of(obj)
                if current_index != -1 and current_index < len(self.field_order) - 1:
                    next_field = self.field_order[current_index + 1]
                    if next_field:
                        next_field.setFocus()
                        return True
                return True
            current_index = self._index_of(obj)
            if current_index != -1 and current_index < len(self.field_order) - 1:
                next_field = self.field_order[current_index + 1]
                if next_field:
                    next_field.setFocus()
                    return True
            return True
        if key == Qt.Key_Escape:
            current_index = self._index_of(obj)
            if current_index > 0:
                prev_field = self.field_order[current_index - 1]
                if prev_field:
                    prev_field.setFocus()
                    return True
            return True
        return False

    def _index_of(self, widget):
        for i, field in enumerate(self.field_order):
            if field is widget:
                return i
        return -1

class ClickablePreviewLabel(QLabel):

    def __init__(self, text='No file selected'):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(110)
        self.setMaximumHeight(110)
        self.setWordWrap(True)
        self.setStyleSheet(theme.master_preview_placeholder_style())

class EditCompanyDialog(UiMemoryMixin, QDialog):
    """Dialog to edit existing company details with professional layout."""
    company_updated = Signal(dict)

    def __init__(self, company_data, db=None, parent=None):
        super().__init__(parent)
        self.company_data = company_data
        self.company_id = company_data['id']
        self.setWindowTitle(f"Edit Company - {company_data['business_name']}")
        self.setMinimumSize(800, 700)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.db = db or Database()
        self.company_logic = CompanyLogic(self.db)
        self.logo_path = company_data.get('logo_path', '')
        self.signature_path = company_data.get('signature_path', '')
        self.gst_state_codes = GST_STATE_CODES
        self.setup_ui()
        self.load_company_data()
        self.connect_signals()
        self._init_ui_memory()

    def setup_ui(self):
        """Setup the dialog UI."""
        self.setStyleSheet(theme.master_profile_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet(f'\n            QScrollArea {{\n                border: none;\n                background-color: transparent;\n            }}\n        ')
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(20)
        self.create_company_info_section(content_layout)
        self.create_business_details_section(content_layout)
        self.create_upload_section(content_layout)
        self.create_action_buttons(content_layout)
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)

    def create_company_info_section(self, layout):
        """Create company information section."""
        section_label = QLabel('Company Information')
        section_label.setProperty('class', 'section')
        layout.addWidget(section_label)
        info_frame = QFrame()
        info_frame.setStyleSheet(f"\n            QFrame {{\n                background-color: {theme.legacy_colors()['surface']};\n                border-radius: 8px;\n                border: 1px solid {theme.legacy_colors()['border']};\n                padding: 15px;\n            }}\n        ")
        info_layout = QGridLayout(info_frame)
        info_layout.setSpacing(15)
        business_name_label = QLabel('Business Name *:')
        business_name_label.setProperty('class', 'field')
        info_layout.addWidget(business_name_label, 0, 0)
        self.business_name = QLineEdit()
        self.business_name.setStyleSheet(f"\n            QLineEdit {{\n                background-color: {theme.legacy_colors()['background']};\n                color: {theme.legacy_colors()['text_primary']};\n                border: 1px solid {theme.legacy_colors()['border']};\n                border-radius: 4px;\n                padding: 8px;\n                font-size: 13px;\n            }}\n            QLineEdit:focus {{\n                border: 2px solid {theme.legacy_colors()['primary']};\n            }}\n        ")
        info_layout.addWidget(self.business_name, 0, 1)
        phone_label = QLabel('Phone:')
        phone_label.setProperty('class', 'field')
        info_layout.addWidget(phone_label, 1, 0)
        self.phone = QLineEdit()
        self.phone.setStyleSheet(f"\n            QLineEdit {{\n                background-color: {theme.legacy_colors()['background']};\n                color: {theme.legacy_colors()['text_primary']};\n                border: 1px solid {theme.legacy_colors()['border']};\n                border-radius: 4px;\n                padding: 8px;\n                font-size: 13px;\n            }}\n        ")
        info_layout.addWidget(self.phone, 1, 1)
        gstin_label = QLabel('GSTIN:')
        gstin_label.setProperty('class', 'field')
        info_layout.addWidget(gstin_label, 2, 0)
        self.gstin = QLineEdit()
        self.gstin.setStyleSheet(f"\n            QLineEdit {{\n                background-color: {theme.legacy_colors()['background']};\n                color: {theme.legacy_colors()['text_primary']};\n                border: 1px solid {theme.legacy_colors()['border']};\n                border-radius: 4px;\n                padding: 8px;\n                font-size: 13px;\n            }}\n        ")
        info_layout.addWidget(self.gstin, 2, 1)
        gst_type_label = QLabel('GST Registration Type:')
        gst_type_label.setProperty('class', 'field')
        info_layout.addWidget(gst_type_label, 3, 0)
        self.gst_type = self.create_combo_box(['Regular', 'Composition'])
        info_layout.addWidget(self.gst_type, 3, 1)
        email_label = QLabel('Email:')
        email_label.setProperty('class', 'field')
        info_layout.addWidget(email_label, 4, 0)
        self.email = QLineEdit()
        self.email.setStyleSheet(f"\n            QLineEdit {{\n                background-color: {theme.legacy_colors()['background']};\n                color: {theme.legacy_colors()['text_primary']};\n                border: 1px solid {theme.legacy_colors()['border']};\n                border-radius: 4px;\n                padding: 8px;\n                font-size: 13px;\n            }}\n        ")
        info_layout.addWidget(self.email, 4, 1)
        print_label = QLabel('Print Options:')
        print_label.setProperty('class', 'field')
        info_layout.addWidget(print_label, 5, 0)
        print_options_layout = QHBoxLayout()
        self.print_phone_cb = create_checkbox('Print Phone')
        self.print_phone_cb.setChecked(True)
        self.print_email_cb = create_checkbox('Print Email')
        self.print_email_cb.setChecked(True)
        print_options_layout.addWidget(self.print_phone_cb)
        print_options_layout.addWidget(self.print_email_cb)
        print_options_layout.addStretch()
        info_layout.addLayout(print_options_layout, 5, 1)
        layout.addWidget(info_frame)

    def create_business_details_section(self, layout):
        """Create business details section."""
        section_label = QLabel('Business Details')
        section_label.setProperty('class', 'section')
        layout.addWidget(section_label)
        details_frame = QFrame()
        details_frame.setStyleSheet(f"\n            QFrame {{\n                background-color: {theme.legacy_colors()['surface']};\n                border-radius: 8px;\n                border: 1px solid {theme.legacy_colors()['border']};\n                padding: 15px;\n            }}\n        ")
        details_layout = QGridLayout(details_frame)
        details_layout.setSpacing(15)
        type_label = QLabel('Business Type:')
        type_label.setProperty('class', 'field')
        details_layout.addWidget(type_label, 0, 0)
        self.business_type = self.create_combo_box(['Select Business Type', 'Retail', 'Wholesale', 'Service', 'Manufacturing', 'Trading', 'Other'])
        details_layout.addWidget(self.business_type, 0, 1)
        category_label = QLabel('Business Category:')
        category_label.setProperty('class', 'field')
        details_layout.addWidget(category_label, 1, 0)
        self.business_category = self.create_combo_box(['Select Business Category', 'General', 'Electronics', 'Grocery', 'Textile', 'Medical', 'Restaurant', 'Other'])
        details_layout.addWidget(self.business_category, 1, 1)
        address_label = QLabel('Address:')
        address_label.setProperty('class', 'field')
        details_layout.addWidget(address_label, 2, 0, Qt.AlignTop)
        self.address = QTextEdit()
        self.address.setMinimumHeight(80)
        self.address.setMaximumHeight(120)
        self.address.setStyleSheet(f"\n            QTextEdit {{\n                background-color: {theme.legacy_colors()['background']};\n                color: {theme.legacy_colors()['text_primary']};\n                border: 1px solid {theme.legacy_colors()['border']};\n                border-radius: 4px;\n                padding: 8px;\n                font-size: 13px;\n            }}\n        ")
        details_layout.addWidget(self.address, 2, 1)
        state_label = QLabel('State:')
        state_label.setProperty('class', 'field')
        details_layout.addWidget(state_label, 3, 0)
        self.state = QLineEdit()
        self.state.setStyleSheet(f"\n            QLineEdit {{\n                background-color: {theme.legacy_colors()['background']};\n                color: {theme.legacy_colors()['text_primary']};\n                border: 1px solid {theme.legacy_colors()['border']};\n                border-radius: 4px;\n                padding: 8px;\n                font-size: 13px;\n            }}\n        ")
        details_layout.addWidget(self.state, 3, 1)
        pincode_label = QLabel('Pincode:')
        pincode_label.setProperty('class', 'field')
        details_layout.addWidget(pincode_label, 4, 0)
        self.pincode = QLineEdit()
        self.pincode.setStyleSheet(f"\n            QLineEdit {{\n                background-color: {theme.legacy_colors()['background']};\n                color: {theme.legacy_colors()['text_primary']};\n                border: 1px solid {theme.legacy_colors()['border']};\n                border-radius: 4px;\n                padding: 8px;\n                font-size: 13px;\n            }}\n        ")
        details_layout.addWidget(self.pincode, 4, 1)
        balance_label = QLabel('Opening Balance:')
        balance_label.setProperty('class', 'field')
        details_layout.addWidget(balance_label, 5, 0)
        self.opening_balance = QLineEdit()
        self.opening_balance.setStyleSheet(f"\n            QLineEdit {{\n                background-color: {theme.legacy_colors()['background']};\n                color: {theme.legacy_colors()['text_primary']};\n                border: 1px solid {theme.legacy_colors()['border']};\n                border-radius: 4px;\n                padding: 8px;\n                font-size: 13px;\n            }}\n        ")
        details_layout.addWidget(self.opening_balance, 5, 1)
        layout.addWidget(details_frame)

    def create_upload_section(self, layout):
        """Create upload section for logo and signature."""
        section_label = QLabel('Upload Details')
        section_label.setProperty('class', 'section')
        layout.addWidget(section_label)
        upload_frame = QFrame()
        upload_frame.setStyleSheet(f"\n            QFrame {{\n                background-color: {theme.legacy_colors()['surface']};\n                border-radius: 8px;\n                border: 1px solid {theme.legacy_colors()['border']};\n                padding: 15px;\n            }}\n        ")
        upload_layout = QHBoxLayout(upload_frame)
        upload_layout.setSpacing(30)
        logo_section = self.create_upload_section_item('Logo')
        upload_layout.addWidget(logo_section)
        signature_section = self.create_upload_section_item('Signature')
        upload_layout.addWidget(signature_section)
        layout.addWidget(upload_frame)

    def create_upload_section_item(self, upload_type):
        """Create individual upload section item."""
        section = QFrame()
        section.setStyleSheet(f"\n            QFrame {{\n                background-color: {theme.legacy_colors()['background']};\n                border: 1px solid {theme.legacy_colors()['border']};\n                border-radius: 6px;\n                padding: 15px;\n            }}\n        ")
        layout = QVBoxLayout(section)
        layout.setSpacing(10)
        label = QLabel(f'{upload_type}:')
        label.setStyleSheet(f"\n            QLabel {{\n                color: {theme.legacy_colors()['text_secondary']};\n                font-weight: bold;\n                font-size: 12px;\n                margin-bottom: 5px;\n            }}\n        ")
        layout.addWidget(label)
        upload_button = QPushButton(f'Upload {upload_type}')
        upload_button.setMinimumHeight(35)
        layout.addWidget(upload_button)
        conditions = QLabel('Formats: PNG, JPG, JPEG, PDF\nMax size: 2 MB')
        conditions.setStyleSheet(f"""
            QLabel {{
                color: {theme._theme_colors()['focus_border']};
                font-size: 11px;
                font-weight: bold;
                margin: 2px 0;
            }}
        """)
        layout.addWidget(conditions)
        preview = ClickablePreviewLabel(f'{upload_type} preview')
        layout.addWidget(preview)
        if upload_type == 'Logo':
            upload_button.clicked.connect(self.upload_logo)
            self.logo_button = upload_button
            self.logo_preview = preview
        else:
            upload_button.clicked.connect(self.upload_signature)
            self.signature_button = upload_button
            self.signature_preview = preview
        return section

    def create_combo_box(self, items):
        """Create a styled combo box."""
        from PySide6.QtWidgets import QComboBox
        combo = QComboBox()
        combo.addItems(items)
        combo.setStyleSheet(f"\n            QComboBox {{\n                background-color: {theme.legacy_colors()['background']};\n                color: {theme.legacy_colors()['text_primary']};\n                border: 1px solid {theme.legacy_colors()['border']};\n                border-radius: 4px;\n                padding: 8px;\n                font-size: 13px;\n            }}\n            QComboBox::drop-down {{\n                border: none;\n                width: 20px;\n            }}\n            QComboBox::down-arrow {{\n                image: none;\n                border-left: 4px solid transparent;\n                border-right: 4px solid transparent;\n                border-top: 4px solid {theme.legacy_colors()['text_secondary']};\n            }}\n        ")
        return combo

    def create_action_buttons(self, layout):
        """Create action buttons."""
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        cancel_button = QPushButton('Cancel')
        cancel_button.setProperty('class', 'secondary')
        cancel_button.clicked.connect(self.reject)
        save_button = QPushButton('Save Changes')
        save_button.clicked.connect(self.save_company)
        self.save_button = save_button
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(save_button)
        layout.addLayout(button_layout)

    def connect_signals(self):
        """Connect signals for form validation."""
        self.gstin.textChanged.connect(self.on_gstin_changed)
        self.business_name.textChanged.connect(self.on_business_name_changed)
        self.state.textChanged.connect(self.on_state_changed)
        self.setup_field_navigation()

    def setup_field_navigation(self):
        """Set up keyboard navigation for Edit Company form."""
        self.field_order = [self.business_name, self.phone, self.gstin, self.gst_type, self.email, self.business_type, self.business_category, self.address, self.state, self.pincode, self.opening_balance, self.logo_button, self.signature_button, self.save_button]
        for field in self.field_order:
            if field is not None:
                field.setFocusPolicy(Qt.StrongFocus)
        self.logo_button.setAutoDefault(False)
        self.logo_button.setDefault(False)
        self.signature_button.setAutoDefault(False)
        self.signature_button.setDefault(False)
        self.enter_filter = FormNavigationFilter(self, self.field_order)
        for field in self.field_order:
            if field is not None:
                field.installEventFilter(self.enter_filter)
        self.logo_button.installEventFilter(self.enter_filter)
        self.signature_button.installEventFilter(self.enter_filter)

    def load_company_data(self):
        """Load existing company data into form fields."""
        self.business_name.setText(self.company_data.get('business_name', ''))
        self.phone.setText(self.company_data.get('phone_number', ''))
        self.gstin.setText(self.company_data.get('gstin', ''))
        self.gst_type.setCurrentText(self.company_data.get('gst_type') or 'Regular')
        self.email.setText(self.company_data.get('email', ''))
        self.print_phone_cb.setChecked(self.company_data.get('print_phone', True))
        self.print_email_cb.setChecked(self.company_data.get('print_email', True))
        self.business_type.setCurrentText(self.company_data.get('business_type', 'Select Business Type'))
        self.business_category.setCurrentText(self.company_data.get('business_category', 'Select Business Category'))
        self.address.setPlainText(self.company_data.get('address', ''))
        self.state.setText(self.company_data.get('state', ''))
        self.pincode.setText(self.company_data.get('pincode', ''))
        self.opening_balance.setText(self.company_data.get('opening_balance', ''))
        if self.logo_path and os.path.exists(self.logo_path):
            if self.logo_path.lower().endswith('.pdf'):
                self.logo_preview.setText('PDF Uploaded\n(Logo)')
            else:
                try:
                    pixmap = QPixmap(self.logo_path)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(150, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.logo_preview.setPixmap(scaled)
                        self.logo_preview.setText('')
                except Exception:
                    self.logo_preview.setText('Preview not available')
        if self.signature_path and os.path.exists(self.signature_path):
            if self.signature_path.lower().endswith('.pdf'):
                self.signature_preview.setText('PDF Uploaded\n(Signature)')
            else:
                try:
                    pixmap = QPixmap(self.signature_path)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(150, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.signature_preview.setPixmap(scaled)
                        self.signature_preview.setText('')
                except Exception:
                    self.signature_preview.setText('Preview not available')

    def upload_logo(self):
        """Handle logo upload."""
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select Logo', '', 'Supported Files (*.png *.jpg *.jpeg *.pdf)')
        if file_path:
            if self.validate_file(file_path, 'Logo'):
                self.logo_path = file_path
                self.set_preview_image(self.logo_preview, file_path)

    def upload_signature(self):
        """Handle signature upload."""
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select Signature', '', 'Supported Files (*.png *.jpg *.jpeg *.pdf)')
        if file_path:
            if self.validate_file(file_path, 'Signature'):
                self.signature_path = file_path
                self.set_preview_image(self.signature_preview, file_path)

    def validate_file(self, file_path, file_type):
        """Validate file type and size."""
        allowed_extensions = ['.png', '.jpg', '.jpeg', '.pdf']
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in allowed_extensions:
            QMessageBox.warning(self, 'Invalid File Type', f'{file_type} must be one of: PNG, JPG, JPEG, or PDF.')
            return False
        max_size = 2 * 1024 * 1024
        try:
            file_size = os.path.getsize(file_path)
            if file_size > max_size:
                size_mb = file_size / (1024 * 1024)
                QMessageBox.warning(self, 'File Too Large', f'{file_type} file size must be less than 2MB.\nSelected file size: {size_mb:.2f}MB')
                return False
        except Exception:
            QMessageBox.warning(self, 'File Error', f'Could not check {file_type} file size.')
            return False
        return True

    def set_preview_image(self, label, file_path):
        """Set preview image for uploaded file."""
        if file_path.lower().endswith('.pdf'):
            return
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(150, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(scaled)
            label.setText('')
        else:
            label.setText('Preview not available')

    def on_gstin_changed(self, text):
        """Handle GSTIN text changes - format validation and state detection."""
        MAX_GSTIN_LENGTH = 15
        cursor_pos = self.gstin.cursorPosition()
        filtered_text = ''.join((char for char in text if char.isalnum()))
        if len(filtered_text) > MAX_GSTIN_LENGTH:
            filtered_text = filtered_text[:MAX_GSTIN_LENGTH]
        upper_text = filtered_text.upper()
        if upper_text != text:
            self.gstin.blockSignals(True)
            self.gstin.setText(upper_text)
            self.gstin.setCursorPosition(min(cursor_pos, MAX_GSTIN_LENGTH))
            self.gstin.blockSignals(False)
        self.state.blockSignals(True)
        self.state.setText('')
        self.state.blockSignals(False)
        if len(upper_text) >= 2 and upper_text[:2].isdigit():
            state_code = upper_text[:2]
            if state_code in self.gst_state_codes:
                expected_state = self.gst_state_codes[state_code]
                self.state.blockSignals(True)
                self.state.setText(expected_state)
                self.state.blockSignals(False)

    def on_business_name_changed(self, text):
        """Handle business name changes - auto-capitalize first letter."""
        if not text:
            return
        words = text.split(' ')
        capitalized_words = []
        for word in words:
            if word:
                capitalized_words.append(word[:1].upper() + word[1:])
            else:
                capitalized_words.append('')
        new_text = ' '.join(capitalized_words)
        if new_text != text:
            cursor_pos = self.business_name.cursorPosition()
            self.business_name.blockSignals(True)
            self.business_name.setText(new_text)
            self.business_name.setCursorPosition(min(cursor_pos, len(new_text)))
            self.business_name.blockSignals(False)

    def on_state_changed(self, text):
        """Handle state changes - auto-capitalize."""
        if not text:
            return
        cursor_pos = self.state.cursorPosition()
        capitalized_text = ' '.join((word.capitalize() for word in text.split()))
        self.state.blockSignals(True)
        self.state.setText(capitalized_text)
        self.state.setCursorPosition(cursor_pos)
        self.state.blockSignals(False)

    def save_company(self):
        """Save updated company data."""
        business_name = self.business_name.text().strip()
        if not business_name:
            QMessageBox.warning(self, 'Validation Error', 'Business Name is required.')
            self.business_name.setFocus()
            return
        company_data = {'business_name': business_name, 'phone_number': self.phone.text().strip(), 'gstin': self.gstin.text().strip().upper(), 'gst_type': self.gst_type.currentText() or 'Regular', 'email': self.email.text().strip(), 'business_type': self.business_type.currentText(), 'business_category': self.business_category.currentText(), 'address': self.address.toPlainText().strip(), 'state': self.state.text().strip(), 'pincode': self.pincode.text().strip(), 'logo_path': self.logo_path, 'signature_path': self.signature_path, 'print_phone': 1 if self.print_phone_cb.isChecked() else 0, 'print_email': 1 if self.print_email_cb.isChecked() else 0}
        validation_result = self.company_logic.validate_company_data(company_data, self.company_id)
        if not validation_result['success']:
            QMessageBox.warning(self, 'Validation Error', validation_result['message'])
            self.business_name.setFocus()
            return
        update_result = self.company_logic.update_company(self.company_id, company_data)
        if update_result['success']:
            company_data['opening_balance'] = self.opening_balance.text().strip()
            company_data['id'] = self.company_id
            QMessageBox.information(self, 'Success', 'Company details updated successfully.')
            self.company_updated.emit(company_data)
            self.accept()
        else:
            QMessageBox.critical(self, 'Error', update_result['message'])