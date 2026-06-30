from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QFileDialog, QMessageBox,
    QFrame, QScrollArea, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QObject, QEvent
from PySide6.QtGui import QPixmap
import os
import sqlite3
from contextlib import closing

from db import Database
from bizora_core.company_logic import CompanyLogic
from ui import theme
from ui.checkbox_style import create_checkbox
from ui.theme import GST_STATE_CODES
from ui.scrollbar_style import scrollbar_stylesheet
from utils.financial_year import get_current_financial_year_label, get_financial_year_options
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin


class ClickablePreviewLabel(QLabel):
    def __init__(self, text="No file selected"):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(64)
        self.setMaximumHeight(64)
        self.setWordWrap(True)
        self.setStyleSheet(theme.master_preview_placeholder_style())


class FormNavigationFilter(QObject):
    def __init__(self, parent_page, field_order):
        super().__init__(parent_page)
        self.parent_page = parent_page
        self.field_order = field_order

    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return False

        key = event.key()

        # Enter = move forward
        if key in (Qt.Key_Return, Qt.Key_Enter):
            combo_from_view = self._combo_for_view(obj)
            if combo_from_view:
                index = obj.currentIndex()
                if index.isValid():
                    combo_from_view.setCurrentIndex(index.row())
                combo_from_view.hidePopup()
                self._focus_next(combo_from_view)
                return True

            if isinstance(obj, QComboBox):
                if obj.view().isVisible():
                    index = obj.view().currentIndex()
                    if index.isValid():
                        obj.setCurrentIndex(index.row())
                    obj.hidePopup()
                    self._focus_next(obj)
                else:
                    obj.showPopup()
                return True

            if obj is self.parent_page.address:
                line_count = max(1, len(obj.toPlainText().splitlines()))
                if line_count >= 4:
                    self._focus_next(obj)
                    return True
                return False
            
            # Upload buttons should not open dialogs on Enter
            if obj in (self.parent_page.logo_button, self.parent_page.signature_button):
                self._focus_next(obj)
                return True

            if obj is self.parent_page.create_btn:
                obj.click()
                return True

            self._focus_next(obj)
            return True

        # Esc = move backward
        if key == Qt.Key_Escape:
            current_index = self._index_of(obj)
            if current_index > 0:
                prev_field = self.field_order[current_index - 1]
                if prev_field:
                    prev_field.setFocus()
                    return True
            return True

        return False

    def _focus_next(self, obj):
        current_index = self._index_of(obj)
        if current_index != -1 and current_index < len(self.field_order) - 1:
            next_field = self.field_order[current_index + 1]
            if next_field:
                next_field.setFocus()
                return True
        return False

    def _index_of(self, widget):
        for i, field in enumerate(self.field_order):
            if field is widget:
                return i
        return -1

    def _combo_for_view(self, obj):
        for combo in (
            self.parent_page.financial_year,
            self.parent_page.gst_type,
            self.parent_page.business_type,
            self.parent_page.business_category,
        ):
            if obj is combo.view():
                return combo
        return None


class NewCompanyPageWidget(UiMemoryMixin, QWidget):
    company_created = Signal(dict)
    company_saved = Signal(dict)

    def __init__(self, db=None, company_visibility: str = "normal"):
        super().__init__()

        self.logo_path = ""
        self.signature_path = ""
        self.editing_company_id = None
        self.db = db or Database()
        self.company_visibility = (company_visibility or "normal").strip().lower()
        self.company_logic = CompanyLogic(self.db)

        # Use shared GST state codes from theme module
        self.gst_state_codes = GST_STATE_CODES

        self.setObjectName("NewCompanyPageWidget")
        self.setStyleSheet(theme.master_scroll_page_style("NewCompanyPageWidget"))

        self.build_ui()
        self._init_ui_memory(restore_geometry=False, save_geometry=False)

    # =========================================================
    # 1. MAIN UI
    # =========================================================
    def build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(
            theme.master_scroll_page_style() + scrollbar_stylesheet()
        )

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet(theme.master_page_background_style())

        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(18, 12, 18, 12)
        self.content_layout.setSpacing(6)

        self.build_header()
        self.print_checks = {}
        self.build_company_info_section()
        self.build_business_details_section()
        self.build_upload_section()

        self.scroll_area.setWidget(self.content_widget)
        root_layout.addWidget(self.scroll_area, 1)
        self.build_action_buttons(root_layout)

        # Connect text field change handlers
        self.gstin.textChanged.connect(self.on_gstin_changed)
        self.business_name.textChanged.connect(self.on_business_name_changed)
        self.state.textChanged.connect(self.on_state_changed)
        self.address.textChanged.connect(self.on_address_changed)

        # Set up Enter / Esc navigation
        self.setup_field_navigation()

    # =========================================================
    # 2. HEADER
    # =========================================================
    def build_header(self):
        self.title_label = QLabel("Create New Company")
        self.title_label.setStyleSheet(theme.master_page_title_style(22))
        self.content_layout.addWidget(self.title_label, alignment=Qt.AlignLeft)
        self.content_layout.addSpacing(2)

    # =========================================================
    # 3. SECTION HEADING
    # =========================================================
    def section_heading(self, text):
        label = QLabel(text)
        label.setStyleSheet(theme.master_section_heading_style())
        return label

    # =========================================================
    # 4. FIELD LABEL
    # =========================================================
    def field_label(self, text):
        label = QLabel(text)
        label.setStyleSheet(theme.master_form_field_label_style())
        return label

    # =========================================================
    # 5. INPUT HELPERS
    # =========================================================
    def create_line_edit(self, placeholder=""):
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        line_edit.setMinimumHeight(32)
        line_edit.setStyleSheet(theme.master_form_input_style())
        return line_edit

    def create_text_edit(self, placeholder=""):
        text_edit = QTextEdit()
        text_edit.setPlaceholderText(placeholder)
        text_edit.setMinimumHeight(64)
        text_edit.setMaximumHeight(82)
        text_edit.setMinimumWidth(260)
        text_edit.setMaximumWidth(360)
        text_edit.setStyleSheet(theme.master_form_input_style())
        return text_edit

    def create_combo_box(self, items):
        combo = QComboBox()
        combo.addItems(items)
        combo.setMinimumHeight(32)
        combo.setStyleSheet(theme.master_combo_style())
        return combo

    def create_button(self, text, primary=False):
        button = QPushButton(text)
        button.setMinimumHeight(32)
        button.setAutoDefault(False)
        button.setDefault(False)

        if primary:
            button.setStyleSheet(theme.master_primary_action_button_style())
        else:
            button.setStyleSheet(theme.master_clear_button_style())
        return button

    # =========================================================
    # 6. FIELD BLOCK
    # =========================================================
    def create_print_checkbox(self, key):
        colors = theme._theme_colors()
        label_color = colors["accent"] if theme._is_light_theme() else colors.get("nav_divider_text", "#93c5fd")
        checkbox = create_checkbox("Print on Bill", label_color=label_color, font_size=11)
        checkbox.setChecked(True)
        if not hasattr(self, "print_checks"):
            self.print_checks = {}
        self.print_checks[key] = checkbox
        return checkbox

    def field_block(self, label_text, widget, print_key=None):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        label_row = QHBoxLayout()
        label_row.setContentsMargins(0, 0, 0, 0)
        label_row.addWidget(self.field_label(label_text))
        if print_key:
            label_row.addStretch()
            label_row.addWidget(self.create_print_checkbox(print_key))
        layout.addLayout(label_row)
        layout.addWidget(widget)
        return layout

    # =========================================================
    # 7. COMPANY INFORMATION
    # =========================================================
    def build_company_info_section(self):
        self.content_layout.addWidget(self.section_heading("Company Information"))
        self.content_layout.addSpacing(2)

        self.business_name = self.create_line_edit("Enter your business name")
        self.phone = self.create_line_edit("Enter phone number")
        self.gstin = self.create_line_edit("Enter GSTIN")
        self.gst_type = self.create_combo_box(["Regular", "Composition"])
        self.email = self.create_line_edit("Enter email address")
        self.financial_year = self.create_combo_box([])
        self.refresh_financial_year_combo()

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        grid.addLayout(self.field_block("Business Name *", self.business_name), 0, 0, 1, 3)
        grid.addLayout(self.field_block("Financial Year *", self.financial_year), 1, 0)
        grid.addLayout(self.field_block("Phone Number", self.phone, "phone"), 1, 1)
        grid.addLayout(self.field_block("GSTIN", self.gstin, "gstin"), 1, 2)
        grid.addLayout(self.field_block("GST Registration Type", self.gst_type), 2, 0)
        grid.addLayout(self.field_block("Email", self.email, "email"), 2, 1, 1, 2)

        self.content_layout.addLayout(grid)
        self.content_layout.addSpacing(8)

    def refresh_financial_year_combo(self):
        """Refresh FY options from three years back through the current Indian FY."""
        if not hasattr(self, "financial_year"):
            return

        selected_value = self.financial_year.currentText().strip()
        options = get_financial_year_options(years_before_current=3)

        self.financial_year.blockSignals(True)
        self.financial_year.clear()
        self.financial_year.addItems(options)

        if selected_value in options:
            self.financial_year.setCurrentText(selected_value)
        else:
            self.financial_year.setCurrentText(get_current_financial_year_label())

        self.financial_year.blockSignals(False)

    def showEvent(self, event):
        """Keep the financial year list current when the page is shown."""
        super().showEvent(event)
        self.refresh_financial_year_combo()

    # =========================================================
    # 8. BUSINESS DETAILS
    # =========================================================
    def build_business_details_section(self):
        self.content_layout.addWidget(self.section_heading("Business Details"))
        self.content_layout.addSpacing(2)

        self.business_type = self.create_combo_box([
            "Select Business Type",
            "Retail",
            "Wholesale",
            "Service",
            "Manufacturing",
            "Trading",
            "Other"
        ])

        self.business_category = self.create_combo_box([
            "Select Business Category",
            "General",
            "Electronics",
            "Grocery",
            "Textile",
            "Medical",
            "Restaurant",
            "Other"
        ])

        self.address = self.create_text_edit("Enter address")
        self.state = self.create_line_edit("Enter state")
        self.pincode = self.create_line_edit("Enter pincode")

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        grid.addLayout(self.field_block("Business Type", self.business_type, "business_type"), 0, 0)
        grid.addLayout(self.field_block("Business Category", self.business_category, "business_category"), 0, 1)
        grid.addLayout(self.field_block("Address", self.address, "address"), 1, 0, 1, 2)
        grid.addLayout(self.field_block("State", self.state, "state"), 2, 0)
        grid.addLayout(self.field_block("Pincode", self.pincode, "pincode"), 2, 1)

        self.content_layout.addLayout(grid)
        self.content_layout.addSpacing(8)

    # =========================================================
    # 9. UPLOAD SECTION
    # =========================================================
    def build_upload_section(self):
        self.content_layout.addWidget(self.section_heading("Upload Details"))
        self.content_layout.addSpacing(2)

        self.logo_preview = ClickablePreviewLabel("Logo preview")
        self.signature_preview = ClickablePreviewLabel("Signature preview")

        self.logo_button = self.create_button("Upload Logo")
        self.signature_button = self.create_button("Upload Signature")

        self.logo_button.clicked.connect(self.upload_logo)
        self.signature_button.clicked.connect(self.upload_signature)

        upload_grid = QGridLayout()
        upload_grid.setContentsMargins(0, 0, 0, 0)
        upload_grid.setHorizontalSpacing(16)
        upload_grid.setVerticalSpacing(8)

        logo_layout = QVBoxLayout()
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(4)
        logo_label_row = QHBoxLayout()
        logo_label_row.setContentsMargins(0, 0, 0, 0)
        logo_label_row.addWidget(self.field_label("Logo"))
        logo_label_row.addStretch()
        logo_label_row.addWidget(self.create_print_checkbox("logo"))
        logo_layout.addLayout(logo_label_row)
        logo_layout.addWidget(self.logo_button)

        logo_conditions = QLabel("Formats: PNG, JPG, JPEG, PDF\nMax size: 2 MB")
        logo_conditions.setStyleSheet(theme.master_form_hint_style())
        logo_layout.addWidget(logo_conditions)
        logo_layout.addWidget(self.logo_preview)

        signature_layout = QVBoxLayout()
        signature_layout.setContentsMargins(0, 0, 0, 0)
        signature_layout.setSpacing(4)
        signature_label_row = QHBoxLayout()
        signature_label_row.setContentsMargins(0, 0, 0, 0)
        signature_label_row.addWidget(self.field_label("Signature"))
        signature_label_row.addStretch()
        signature_label_row.addWidget(self.create_print_checkbox("signature"))
        signature_layout.addLayout(signature_label_row)
        signature_layout.addWidget(self.signature_button)

        signature_conditions = QLabel("Formats: PNG, JPG, JPEG, PDF\nMax size: 2 MB")
        signature_conditions.setStyleSheet(theme.master_form_hint_style())
        signature_layout.addWidget(signature_conditions)
        signature_layout.addWidget(self.signature_preview)

        upload_grid.addLayout(logo_layout, 0, 0)
        upload_grid.addLayout(signature_layout, 0, 1)

        self.content_layout.addLayout(upload_grid)
        self.content_layout.addSpacing(12)

    # =========================================================
    # 10. ACTION BUTTONS
    # =========================================================
    def build_action_buttons(self, root_layout):
        footer = QWidget()
        footer.setStyleSheet(theme.master_form_footer_style())
        button_row = QHBoxLayout()
        button_row.setContentsMargins(18, 8, 18, 8)
        button_row.setSpacing(10)
        button_row.addStretch()
        footer.setLayout(button_row)

        self.clear_btn = self.create_button("Clear")
        self.create_btn = self.create_button("Create Company", primary=True)

        self.clear_btn.clicked.connect(self.clear_form)
        self.create_btn.clicked.connect(self.create_company)

        button_row.addWidget(self.clear_btn)
        button_row.addWidget(self.create_btn)

        root_layout.addWidget(footer, 0)

    # =========================================================
    # 11. UPLOAD FUNCTIONS
    # =========================================================
    def upload_logo(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Logo",
            "",
            "Supported Files (*.png *.jpg *.jpeg *.pdf)"
        )
        if file_path and self.validate_file(file_path, "Logo"):
            self.logo_path = file_path
            self.set_preview_image(self.logo_preview, file_path)

    def upload_signature(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Signature",
            "",
            "Supported Files (*.png *.jpg *.jpeg *.pdf)"
        )
        if file_path and self.validate_file(file_path, "Signature"):
            self.signature_path = file_path
            self.set_preview_image(self.signature_preview, file_path)

    def validate_file(self, file_path, file_type):
        allowed_extensions = [".png", ".jpg", ".jpeg", ".pdf"]
        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext not in allowed_extensions:
            QMessageBox.warning(
                self,
                "Invalid File Type",
                f"{file_type} must be one of: PNG, JPG, JPEG, or PDF.\n\nSelected file: {file_ext}"
            )
            return False

        max_size = 2 * 1024 * 1024
        try:
            file_size = os.path.getsize(file_path)
            if file_size > max_size:
                size_mb = file_size / (1024 * 1024)
                QMessageBox.warning(
                    self,
                    "File Too Large",
                    f"{file_type} file size must be less than 2MB.\n\nSelected file size: {size_mb:.2f}MB"
                )
                return False
        except Exception as e:
            QMessageBox.warning(
                self,
                "File Error",
                f"Could not check {file_type} file size: {str(e)}"
            )
            return False

        return True

    def set_preview_image(self, label, file_path):
        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext == ".pdf":
            label.setPixmap(QPixmap())
            label.setText("PDF selected")
            return

        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                max(50, label.width() - 20),
                max(50, label.height() - 20),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            label.setPixmap(scaled)
            label.setText("")
        else:
            label.setPixmap(QPixmap())
            label.setText("Preview not available")

    # =========================================================
    # 12. FORM ACTIONS
    # =========================================================
    def create_company(self):
        if not self.editing_company_id and self._company_limit_reached():
            from bizora_core.company_limits import company_limit_message

            QMessageBox.warning(
                self,
                "Limit Reached",
                company_limit_message(self.company_visibility),
            )
            return

        business_name = self.business_name.text().strip()

        if not business_name:
            QMessageBox.warning(self, "Validation Error", "Business Name is required.")
            self.business_name.setFocus()
            return

        financial_year = self.financial_year.currentText().strip()
        if not financial_year:
            QMessageBox.warning(self, "Validation Error", "Financial Year is required.")
            self.financial_year.setFocus()
            return

        company_data = {
            "business_name": business_name,
            "financial_year": financial_year,
            "phone_number": self.phone.text().strip(),
            "gstin": self.gstin.text().strip().upper(),
            "gst_type": self.gst_type.currentText() or "Regular",
            "email": self.email.text().strip(),
            "business_type": self.business_type.currentText(),
            "business_category": self.business_category.currentText(),
            "address": self.address.toPlainText().strip(),
            "state": self.state.text().strip(),
            "pincode": self.pincode.text().strip(),
            "logo_path": self.logo_path,
            "signature_path": self.signature_path,
            "print_phone": 1 if self.print_checks["phone"].isChecked() else 0,
            "print_gstin": 1 if self.print_checks["gstin"].isChecked() else 0,
            "print_email": 1 if self.print_checks["email"].isChecked() else 0,
            "print_business_type": 1 if self.print_checks["business_type"].isChecked() else 0,
            "print_business_category": 1 if self.print_checks["business_category"].isChecked() else 0,
            "print_address": 1 if self.print_checks["address"].isChecked() else 0,
            "print_state": 1 if self.print_checks["state"].isChecked() else 0,
            "print_pincode": 1 if self.print_checks["pincode"].isChecked() else 0,
            "print_logo": 1 if self.print_checks["logo"].isChecked() else 0,
            "print_signature": 1 if self.print_checks["signature"].isChecked() else 0,
            "visibility": self.company_visibility,
            "activate_on_create": self.company_visibility != "secret",
        }

        # Validate company data
        validation_result = self.company_logic.validate_company_data(
            company_data,
            current_company_id=self.editing_company_id,
        )
        
        if not validation_result['success']:
            QMessageBox.warning(self, "Validation Error", validation_result['message'])
            self.business_name.setFocus()
            return
        
        if self.editing_company_id:
            save_result = self.company_logic.update_company(self.editing_company_id, company_data)
        else:
            save_result = self.company_logic.create_company(company_data)
        
        if save_result['success']:
            if self.editing_company_id:
                company_data["id"] = self.editing_company_id
            try:
                from config import active_company_manager
                if self.company_visibility != "secret":
                    active_company = self.db.get_active_company(
                        visibility=self.company_visibility,
                    ) if self.db else None
                    if active_company and (
                        not self.editing_company_id
                        or active_company.get("id") == self.editing_company_id
                    ):
                        active_company_manager.set_active_company(active_company)
                        company_data = active_company
            except Exception:
                pass

            if not self.editing_company_id:
                self.company_created.emit(company_data)
            self.company_saved.emit(company_data)

            message = "Company details updated successfully." if self.editing_company_id else "Company details saved successfully."
            QMessageBox.information(self, "Success", message)

            if not self.editing_company_id:
                self.clear_form()
        else:
            QMessageBox.critical(self, "Error", save_result['message'])

    def _company_limit_reached(self):
        """Return True when the visibility pool has reached its configured cap."""
        from bizora_core.company_limits import company_limit_reached

        try:
            return company_limit_reached(self.db.db_path, self.company_visibility)
        except Exception as error:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Unable to check company limit:\n{error}",
            )
            return True

    def load_company_data(self, company_id):
        company = self.db.get_company_by_id(company_id) if self.db else None
        if not company:
            QMessageBox.warning(self, "Company Not Found", "Could not load the selected company.")
            return False

        self.editing_company_id = company_id
        self.title_label.setText("Edit Company Information")
        self.create_btn.setText("Update Information")

        self.business_name.setText(company.get("business_name") or "")
        self.refresh_financial_year_combo()
        saved_financial_year = (company.get("financial_year") or "").strip()
        if saved_financial_year:
            self.financial_year.setCurrentText(saved_financial_year)
        self.phone.setText(company.get("phone_number") or "")
        self.gstin.setText(company.get("gstin") or "")
        self.gst_type.setCurrentText(company.get("gst_type") or "Regular")
        self.email.setText(company.get("email") or "")
        self.business_type.setCurrentText(company.get("business_type") or "Select Business Type")
        self.business_category.setCurrentText(company.get("business_category") or "Select Business Category")
        self.address.setPlainText(company.get("address") or "")
        self.state.setText(company.get("state") or "")
        self.pincode.setText(company.get("pincode") or "")

        self.logo_path = company.get("logo_path") or ""
        self.signature_path = company.get("signature_path") or ""
        self.set_preview_image(self.logo_preview, self.logo_path) if self.logo_path else self.logo_preview.setText("Logo preview")
        self.set_preview_image(self.signature_preview, self.signature_path) if self.signature_path else self.signature_preview.setText("Signature preview")

        self._set_print_checked("phone", company.get("print_phone", 1))
        self._set_print_checked("gstin", company.get("print_gstin", 1))
        self._set_print_checked("email", company.get("print_email", 1))
        self._set_print_checked("business_type", company.get("print_business_type", 1))
        self._set_print_checked("business_category", company.get("print_business_category", 1))
        self._set_print_checked("address", company.get("print_address", 1))
        self._set_print_checked("state", company.get("print_state", 1))
        self._set_print_checked("pincode", company.get("print_pincode", 1))
        self._set_print_checked("logo", company.get("print_logo", 1))
        self._set_print_checked("signature", company.get("print_signature", 1))
        return True

    def _set_print_checked(self, key, value):
        checkbox = self.print_checks.get(key)
        if checkbox:
            checkbox.setChecked(str(value).strip().lower() not in {"0", "false", "no", "off", ""})

    def clear_form(self):
        self.business_name.clear()
        self.refresh_financial_year_combo()
        self.phone.clear()
        self.gstin.clear()
        self.email.clear()
        self.address.clear()
        self.state.clear()
        self.pincode.clear()
        for checkbox in self.print_checks.values():
            checkbox.setChecked(True)

        if self.business_type.count() > 0:
            self.business_type.setCurrentIndex(0)
        if self.gst_type.count() > 0:
            self.gst_type.setCurrentText("Regular")
        if self.business_category.count() > 0:
            self.business_category.setCurrentIndex(0)

        self.logo_path = ""
        self.signature_path = ""

        self.logo_preview.setPixmap(QPixmap())
        self.logo_preview.setText("Logo preview")

        self.signature_preview.setPixmap(QPixmap())
        self.signature_preview.setText("Signature preview")

    # =========================================================
    # 13. TEXT / VALIDATION HANDLERS
    # =========================================================
    def on_gstin_changed(self, text):
        max_gstin_length = 15
        cursor_pos = self.gstin.cursorPosition()

        filtered_text = "".join(char for char in text if char.isalnum())
        filtered_text = filtered_text[:max_gstin_length]
        upper_text = filtered_text.upper()

        if upper_text != text:
            self.gstin.blockSignals(True)
            self.gstin.setText(upper_text)
            self.gstin.setCursorPosition(min(cursor_pos, len(upper_text)))
            self.gstin.blockSignals(False)

        # Clear State field first, then autofill if valid GSTIN state code exists
        self.state.blockSignals(True)
        self.state.setText("")
        self.state.blockSignals(False)
        
        if len(upper_text) >= 2 and upper_text[:2].isdigit():
            state_code = upper_text[:2]
            if state_code in self.gst_state_codes:
                expected_state = self.gst_state_codes[state_code]
                self.state.blockSignals(True)
                self.state.setText(expected_state)
                self.state.blockSignals(False)

    def on_business_name_changed(self, text):
        if not text:
            return

        words = text.split(" ")
        capitalized_words = []

        for word in words:
            if word:
                capitalized_words.append(word[:1].upper() + word[1:])
            else:
                capitalized_words.append("")

        new_text = " ".join(capitalized_words)

        if new_text != text:
            cursor_pos = self.business_name.cursorPosition()
            self.business_name.blockSignals(True)
            self.business_name.setText(new_text)
            self.business_name.setCursorPosition(min(cursor_pos, len(new_text)))
            self.business_name.blockSignals(False)

    def on_state_changed(self, text):
        if not text:
            return

        words = text.split(" ")
        capitalized_words = []

        for word in words:
            if word:
                capitalized_words.append(word[:1].upper() + word[1:])
            else:
                capitalized_words.append("")

        new_text = " ".join(capitalized_words)

        if new_text != text:
            cursor_pos = self.state.cursorPosition()
            self.state.blockSignals(True)
            self.state.setText(new_text)
            self.state.setCursorPosition(min(cursor_pos, len(new_text)))
            self.state.blockSignals(False)

    def on_address_changed(self):
        text = self.address.toPlainText()
        if not text:
            return

        words = text.split(" ")
        capitalized_words = []

        for word in words:
            if word:
                capitalized_words.append(word[:1].upper() + word[1:])
            else:
                capitalized_words.append("")

        new_text = " ".join(capitalized_words)

        if new_text != text:
            cursor = self.address.textCursor()
            cursor_pos = cursor.position()
            self.address.blockSignals(True)
            self.address.setText(new_text)
            cursor.setPosition(min(cursor_pos, len(new_text)))
            self.address.setTextCursor(cursor)
            self.address.blockSignals(False)

    # =========================================================
    # 14. FIELD NAVIGATION
    # =========================================================
    def setup_field_navigation(self):
        # Field order: Business Name -> Phone -> GSTIN -> GST Type -> Email -> Business Type -> Business Category -> Address -> State -> Pincode -> Upload Logo -> Upload Signature -> Save Button
        self.field_order = [
            self.business_name,
            self.financial_year,
            self.phone,
            self.gstin,
            self.gst_type,
            self.email,
            self.business_type,
            self.business_category,
            self.address,
            self.state,
            self.pincode,
            self.logo_button,
            self.signature_button,
        ]

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
        self.gst_type.view().installEventFilter(self.enter_filter)
        self.financial_year.view().installEventFilter(self.enter_filter)
        self.business_type.view().installEventFilter(self.enter_filter)
        self.business_category.view().installEventFilter(self.enter_filter)
        
        # Also install event filter on Upload buttons to prevent Enter from triggering dialogs
        self.logo_button.installEventFilter(self.enter_filter)
        self.signature_button.installEventFilter(self.enter_filter)


NewCompanyPage = NewCompanyPageWidget