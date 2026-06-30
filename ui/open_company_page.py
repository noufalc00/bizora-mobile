"""
Open Company page for the Accounting Desktop Application.
Provides a dialog to select and open an existing company from the database.
"""
import os
import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFrame, QScrollArea, QAbstractItemView
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from db import Database
from config import active_company_manager
from bizora_core.company_logic import CompanyLogic
from ui import theme
from .view_company_dialog import ViewCompanyDialog
from .table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from .new_company_page import NewCompanyPageWidget
from .standalone_window import StandaloneModuleWindow, _resolve_hub_window
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class OpenCompanyPageWidget(UiMemoryMixin, QWidget):
    """Open Company page with company selection functionality."""
    company_selected = Signal(dict)
    company_profile_updated = Signal(dict)

    def __init__(self, db=None, auto_close_on_selection=True, show_success_message=True, activate_on_selection=True, show_row_actions=True, row_actions=('view', 'edit', 'delete'), active_only=False, title_text='Open Company', subtitle_text='Select a company to work with', show_open_button=True, open_button_text='Open Selected Company', company_visibility='normal'):
        """Initialize the company list with configurable selection behavior."""
        super().__init__()
        self.db = db or Database()
        self.auto_close_on_selection = auto_close_on_selection
        self.show_success_message = show_success_message
        self.activate_on_selection = activate_on_selection
        self.show_row_actions = show_row_actions
        self.row_actions = set(row_actions or ())
        self.active_only = active_only
        self.title_text = title_text
        self.subtitle_text = subtitle_text
        self.show_open_button = show_open_button
        self.open_button_text = open_button_text
        self.company_visibility = (company_visibility or 'normal').strip().lower()
        self.company_logic = CompanyLogic(self.db)
        self.setup_ui()
        self.load_companies()
        self._init_ui_memory()

    def setup_ui(self):
        """Setup the Open Company UI."""
        self.setObjectName('OpenCompanyPageWidget')
        self.setStyleSheet(theme.master_scroll_page_style('OpenCompanyPageWidget'))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet(theme.master_scroll_page_style())
        content_widget = QWidget()
        content_widget.setStyleSheet(theme.master_page_background_style())
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(28, 22, 28, 22)
        content_layout.setSpacing(20)
        self.create_header(content_layout)
        self.create_companies_table(content_layout)
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        self.create_footer_bar(layout)

    def create_header(self, layout):
        """Create page header."""
        title = QLabel(self.title_text)
        title.setStyleSheet(theme.master_page_title_style(28))
        layout.addWidget(title, alignment=Qt.AlignLeft)
        layout.addSpacing(10)
        subtitle = QLabel(self.subtitle_text)
        subtitle.setStyleSheet(theme.master_page_subtitle_style())
        layout.addWidget(subtitle, alignment=Qt.AlignLeft)
        layout.addSpacing(20)

    def create_companies_table(self, layout):
        """Create companies selection table."""
        self.companies_table = QTableWidget()
        column_count = 6 if self.show_row_actions else 5
        self.companies_table.setColumnCount(column_count)
        headers = ['Company Name', 'GSTIN', 'Phone', 'Email', 'Status']
        if self.show_row_actions:
            headers.append('Actions')
        self.companies_table.setHorizontalHeaderLabels(headers)
        apply_read_only_report_table_selection(self.companies_table)
        self.companies_table.verticalHeader().setDefaultSectionSize(40)
        if self.show_open_button:
            self.companies_table.itemDoubleClicked.connect(self.open_selected_company)
        layout.addWidget(self.companies_table)

    def create_footer_bar(self, layout):
        """Create the fixed footer bar with page actions."""
        footer = QWidget()
        footer.setStyleSheet(theme.master_form_footer_style())
        button_layout = QHBoxLayout(footer)
        button_layout.setContentsMargins(18, 8, 18, 8)
        button_layout.setSpacing(10)
        self.open_button = QPushButton(self.open_button_text)
        self.open_button.setMinimumHeight(42)
        self.open_button.setStyleSheet(theme.master_primary_action_button_style())
        self.open_button.clicked.connect(self.open_selected_company)
        self.open_button.setEnabled(False)
        if self.show_open_button:
            button_layout.addWidget(self.open_button)
        button_layout.addStretch()
        self.close_button = QPushButton('Close')
        self.close_button.setMinimumHeight(42)
        self.close_button.setStyleSheet(theme.master_nav_secondary_button_style())
        self.close_button.clicked.connect(self.close_page)
        button_layout.addWidget(self.close_button)
        layout.addWidget(footer, 0)

    def load_companies(self):
        """Load companies from database into table."""
        result = self.company_logic.get_all_companies(
            visibility=self.company_visibility,
        )
        if not result['success']:
            companies = []
        else:
            companies = result['data']
        if self.active_only:
            session_company_id = active_company_manager.get_active_company_id()
            session_company = active_company_manager.get_active_company()
            if session_company_id:
                if (
                    session_company
                    and int(session_company.get('id') or 0) == int(session_company_id)
                ):
                    companies = [session_company]
                else:
                    company_row = self.db.get_company_by_id(session_company_id)
                    companies = [company_row] if company_row else []
            else:
                companies = [company for company in companies if company.get('is_active')]
        if not companies:
            self.companies_table.setRowCount(1)
            if self.active_only:
                empty_message = 'No active company is open. Please open a company first.'
            elif self.company_visibility == 'secret':
                empty_message = 'No secret companies found. Create a secret company first.'
            else:
                empty_message = 'No companies found. Create a new company first.'
            no_company_item = QTableWidgetItem(empty_message)
            no_company_item.setTextAlignment(Qt.AlignCenter)
            self.companies_table.setItem(0, 0, no_company_item)
            self.companies_table.setSpan(0, 0, 1, self.companies_table.columnCount())
            self.open_button.setEnabled(False)
            return
        self.companies_table.setRowCount(len(companies))
        for row, company in enumerate(companies):
            name_item = QTableWidgetItem(company['business_name'])
            name_item.setData(Qt.UserRole, company)
            self.companies_table.setItem(row, 0, name_item)
            gstin_item = QTableWidgetItem(company['gstin'] or '')
            self.companies_table.setItem(row, 1, gstin_item)
            phone_item = QTableWidgetItem(company['phone_number'] or '')
            self.companies_table.setItem(row, 2, phone_item)
            email_item = QTableWidgetItem(company['email'] or '')
            self.companies_table.setItem(row, 3, email_item)
            status = 'Active' if company['is_active'] else 'Inactive'
            status_item = QTableWidgetItem(status)
            if company['is_active']:
                status_item.setData(Qt.ForegroundRole, '#10b981')
                status_item.setData(Qt.FontRole, QFont('Segoe UI', -1, QFont.Bold))
            else:
                status_item.setData(Qt.ForegroundRole, '#9ca3af')
            self.companies_table.setItem(row, 4, status_item)
            if self.show_row_actions:
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(2, 2, 2, 2)
                actions_layout.setSpacing(2)
                actions_layout.setAlignment(Qt.AlignCenter)
                if 'view' in self.row_actions:
                    view_btn = self._create_action_button('View', '#3b82f6', '#2563eb', '#1d4ed8')
                    view_btn.clicked.connect(lambda checked, comp=company: self.view_company(comp))
                    actions_layout.addWidget(view_btn)
                if 'edit' in self.row_actions:
                    edit_btn = self._create_action_button('Edit', '#f59e0b', '#d97706', '#b45309')
                    edit_btn.clicked.connect(lambda checked, comp=company: self.edit_company(comp))
                    actions_layout.addWidget(edit_btn)
                if 'delete' in self.row_actions:
                    delete_btn = self._create_action_button('Delete', '#ef4444', '#dc2626', '#b91c1c')
                    delete_btn.clicked.connect(lambda checked, comp=company: self.delete_company(comp))
                    actions_layout.addWidget(delete_btn)
                self.companies_table.setCellWidget(row, 5, actions_widget)
        self.companies_table.itemSelectionChanged.connect(self.on_selection_changed)
        apply_adjustable_table_columns(self.companies_table)

    def _create_action_button(self, text, color, hover_color, pressed_color):
        """Create a compact row action button."""
        button = QPushButton(text)
        button.setFixedSize(48, 24)
        button.setStyleSheet(f'\n            QPushButton {{\n                background-color: {color};\n                color: white;\n                border: none;\n                border-radius: 2px;\n                font-size: 9px;\n                font-weight: bold;\n                padding: 1px 3px;\n            }}\n            QPushButton:hover {{\n                background-color: {hover_color};\n            }}\n            QPushButton:pressed {{\n                background-color: {pressed_color};\n            }}\n        ')
        return button

    def on_selection_changed(self):
        """Handle table selection change."""
        selected_items = self.companies_table.selectedItems()
        if selected_items:
            self.open_button.setEnabled(True)
        else:
            self.open_button.setEnabled(False)

    def open_selected_company(self):
        """Open the selected company."""
        selected_row = self.companies_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, 'No Selection', 'Please select a company to open.')
            return
        name_item = self.companies_table.item(selected_row, 0)
        if not name_item:
            return
        company_data = name_item.data(Qt.UserRole)
        if self.activate_on_selection:
            try:
                if self.db and company_data.get('id'):
                    self.db.set_active_company(company_data['id'])
                    refreshed = self.db.get_active_company()
                    if refreshed:
                        company_data = refreshed
            except Exception as e:
                QMessageBox.warning(self, 'Warning', f'Company opened in this session, but DB active flag could not be updated: {e}')
            active_company_manager.set_active_company(company_data)
        self.company_selected.emit(company_data)
        if self.show_success_message:
            QMessageBox.information(self, 'Success', f"Company '{company_data['business_name']}' has been opened successfully.")
        if self.auto_close_on_selection:
            top_level = self.window()
            if top_level and top_level is not self:
                top_level.close()
            else:
                self.close()

    def view_company(self, company_data):
        """View company details in professional dialog."""
        dialog = ViewCompanyDialog(company_data, self)
        dialog.exec()

    def edit_company(self, company_data):
        """Edit company details using the shared company profile form."""
        company_id = company_data.get('id')
        if not company_id:
            QMessageBox.warning(self, 'No Company', 'Could not identify the selected company.')
            return
        widget = NewCompanyPageWidget(self.db)
        if not widget.load_company_data(company_id):
            return
        hub = _resolve_hub_window(self) or _resolve_hub_window(self.window())
        window_key = f'edit_company_{company_id}'
        if hub is not None:
            existing = hub._open_module_windows.get(window_key)
            if existing is not None and hub._is_live_module_window(existing):
                hub._center_and_show_window(existing)
                existing.raise_()
                existing.activateWindow()
                self.edit_company_window = existing
                return
        window = StandaloneModuleWindow(widget, 'Edit Company Information', hub)
        window.setMinimumSize(900, 700)
        widget.company_saved.connect(lambda updated_data: self._on_edit_company_saved(window, updated_data))
        if hub is not None:
            hub._open_module_windows[window_key] = window
            window.destroyed.connect(lambda key=window_key: hub._on_module_window_closed(key))
            hub._center_and_show_window(window)
        else:
            window.show()
        window.raise_()
        window.activateWindow()
        self.edit_company_window = window

    def _on_edit_company_saved(self, window, updated_data):
        self.on_company_updated(updated_data)
        self.load_companies()
        if window:
            window.close()

    def on_company_updated(self, updated_data):
        """Handle company update event."""
        active_company = active_company_manager.get_active_company()
        if active_company and active_company.get('id') == updated_data.get('id'):
            refreshed_company = self.db.get_company_by_id(updated_data['id'])
            if refreshed_company:
                active_company_manager.set_active_company(refreshed_company)
        self.company_profile_updated.emit(dict(updated_data or {}))

    def delete_company(self, company_data):
        """Delete company with confirmation."""
        reply = QMessageBox.question(self, 'Delete Company', f"Are you sure you want to permanently delete '{company_data['business_name']}'?\n\nThis action cannot be undone.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            main_window = self._find_main_window()
            if main_window is not None:
                main_window.skip_backup_on_close = True
            company_db_path = self._company_database_path(company_data, main_window)
            result = self.company_logic.delete_company(company_data['id'])
            if result['success']:
                self._delete_company_database_file(company_db_path)
                QMessageBox.information(self, 'Success', f"Company '{company_data['business_name']}' has been deleted successfully. The application will now restart.")
                self._restart_application()
            else:
                if main_window is not None:
                    main_window.skip_backup_on_close = False
                QMessageBox.critical(self, 'Error', result['message'])

    def _find_main_window(self):
        """Return the owning main window if this page is hosted in one."""
        widget = self
        while widget is not None:
            if hasattr(widget, 'skip_backup_on_close'):
                return widget
            widget = widget.parent()
        active_window = QApplication.activeWindow()
        while active_window is not None:
            if hasattr(active_window, 'skip_backup_on_close'):
                return active_window
            active_window = active_window.parent()
        return None

    def _company_database_path(self, company_data, main_window):
        """Return a deletable company database path when the registry stores one."""
        for key in ('db_path', 'database_path', 'company_db_path', 'file_path', 'path'):
            value = company_data.get(key)
            if value:
                candidate_path = os.path.abspath(str(value))
                current_db_path = getattr(main_window, 'db_path', None)
                if current_db_path and candidate_path == os.path.abspath(current_db_path):
                    return ''
                return candidate_path
        return ''

    def _delete_company_database_file(self, company_db_path):
        """Delete the physical company database file when it is separate."""
        if not company_db_path or not os.path.isfile(company_db_path):
            return
        try:
            os.remove(company_db_path)
        except OSError as error:
            QMessageBox.warning(self, 'Database File Warning', f'Company was removed, but the database file could not be deleted:\n{error}')

    def _restart_application(self):
        """Restart the application so the gateway opens with no deleted company."""
        QApplication.closeAllWindows()
        os.execl(sys.executable, sys.executable, *sys.argv)

    def close_page(self):
        """Close the hosting standalone window or selection dialog."""
        top_level = self.window()
        if top_level and top_level is not self:
            top_level.close()
            return
        self.close()
OpenCompanyPage = OpenCompanyPageWidget