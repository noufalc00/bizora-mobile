"""
Financial year-end processing dialog.
"""
from __future__ import annotations
import os
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton, QVBoxLayout
from ui import theme
from db import BASE_DIR, get_default_database_path
from utils.year_end_processor import process_financial_year
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin, configure_non_modal_window
BACKUP_DIR_KEY = 'backup_dir'

class YearEndDialog(UiMemoryMixin, QDialog):
    """Dialog for closing the current financial year and creating a new database."""

    def __init__(self, db_path: str, company_name: str, master_db_path: str | None=None, parent=None):
        super().__init__(parent)
        self.db_path = os.path.abspath(db_path) if db_path else ''
        self.company_name = (company_name or 'company').strip() or 'company'
        self.master_db_path = self._resolve_master_db_path(master_db_path)
        self.setWindowTitle('Financial Year-End Processing')
        self._ui_memory_geometry_key = 'year_end_processing'
        self.resize(680, 420)
        self.setStyleSheet(self._dialog_stylesheet())
        self._build_ui()
        self._load_backup_directory()
        configure_non_modal_window(self, parent)
        self._init_ui_memory()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

    def _dialog_stylesheet(self) -> str:
        colors = theme._theme_colors()
        return f"\n            {theme.complex_tool_dialog_style()}\n            QPushButton#processButton {{\n                background-color: {colors['button_warning']};\n                color: #FFFFFF;\n                border: none;\n                border-radius: 6px;\n                padding: 12px 18px;\n                font-size: 14px;\n                font-weight: bold;\n            }}\n            QPushButton#processButton:hover {{\n                background-color: {colors['focus_border']};\n            }}\n            QPushButton#processButton:disabled {{\n                background-color: {colors['border']};\n                color: {colors['muted_text']};\n            }}\n        "

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        title_label = QLabel('Financial Year-End Processing')
        title_label.setObjectName('titleLabel')
        layout.addWidget(title_label)
        warning_label = QLabel('This will close the current financial year, carry forward closing balances as opening balances, and create a brand new company database.')
        warning_label.setObjectName('warningLabel')
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)
        current_label = QLabel('Current Company:')
        current_label.setObjectName('fieldLabel')
        self.current_company_input = QLineEdit(self.company_name)
        self.current_company_input.setReadOnly(True)
        layout.addWidget(current_label)
        layout.addWidget(self.current_company_input)
        new_name_label = QLabel('New Company Name:')
        new_name_label.setObjectName('fieldLabel')
        self.new_company_input = QLineEdit(self._default_new_company_name())
        layout.addWidget(new_name_label)
        layout.addWidget(self.new_company_input)
        backup_label = QLabel('Backup Directory:')
        backup_label.setObjectName('fieldLabel')
        layout.addWidget(backup_label)
        backup_row = QHBoxLayout()
        backup_row.setSpacing(10)
        self.backup_dir_input = QLineEdit()
        self.backup_dir_input.setReadOnly(True)
        self.backup_dir_input.setPlaceholderText('Select a backup folder')
        browse_button = QPushButton('Browse...')
        browse_button.clicked.connect(self._browse_backup_directory)
        backup_row.addWidget(self.backup_dir_input, 1)
        backup_row.addWidget(browse_button)
        layout.addLayout(backup_row)
        layout.addStretch()
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_button = QPushButton('Cancel')
        cancel_button.clicked.connect(self.reject)
        self.process_button = QPushButton('Start Year-End Process')
        self.process_button.setObjectName('processButton')
        self.process_button.clicked.connect(self._start_year_end_process)
        footer.addWidget(cancel_button)
        footer.addWidget(self.process_button)
        layout.addLayout(footer)

    def _default_new_company_name(self) -> str:
        current_year = datetime.now().year
        start_year = current_year % 100
        end_year = (current_year + 1) % 100
        return f'{self.company_name} - FY {start_year:02d}-{end_year:02d}'

    def _resolve_master_db_path(self, master_db_path: str | None) -> str:
        configured_path = master_db_path or get_default_database_path()
        configured_path = str(configured_path)
        if os.path.isabs(configured_path):
            return configured_path
        return os.path.abspath(os.path.join(BASE_DIR, configured_path))

    def _load_backup_directory(self) -> None:
        if not self.db_path:
            return
        backup_dir = ''
        try:
            with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
                connection.execute('PRAGMA busy_timeout = 5000;')
                cursor = connection.cursor()
                cursor.execute("\n                    SELECT name\n                    FROM sqlite_master\n                    WHERE type = 'table' AND name = 'app_settings'\n                    LIMIT 1\n                    ")
                if cursor.fetchone():
                    cursor.execute('\n                        SELECT setting_value\n                        FROM app_settings\n                        WHERE setting_key = ?\n                        ', (BACKUP_DIR_KEY,))
                    row = cursor.fetchone()
                    backup_dir = row[0] if row else ''
        except sqlite3.Error:
            backup_dir = ''
        if not backup_dir:
            backup_dir = os.path.abspath(os.path.join(BASE_DIR, 'backups'))
        self.backup_dir_input.setText(backup_dir)

    def _browse_backup_directory(self) -> None:
        selected_dir = QFileDialog.getExistingDirectory(self, 'Select Backup Directory', self.backup_dir_input.text() or os.path.expanduser('~'))
        if selected_dir:
            self.backup_dir_input.setText(selected_dir)

    def _build_new_database_path(self, new_company_name: str) -> str:
        base_dir = os.path.dirname(self.db_path) or BASE_DIR
        safe_name = re.sub('[^\\w\\-]+', '_', new_company_name.strip()).strip('_')
        if not safe_name:
            safe_name = 'new_financial_year'
        candidate = os.path.join(base_dir, f'{safe_name}.db')
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(base_dir, f'{safe_name}_{counter}.db')
            counter += 1
        return os.path.abspath(candidate)

    def _set_form_enabled(self, enabled: bool) -> None:
        self.new_company_input.setEnabled(enabled)
        self.process_button.setEnabled(enabled)

    def _validate_inputs(self) -> tuple[bool, str]:
        if not self.db_path or not os.path.isfile(self.db_path):
            return (False, 'The active company database could not be found.')
        new_company_name = self.new_company_input.text().strip()
        if not new_company_name:
            return (False, 'Please enter a name for the new financial year company.')
        backup_dir = self.backup_dir_input.text().strip()
        if not backup_dir:
            return (False, 'Please select a backup directory.')
        if not os.path.isdir(backup_dir):
            return (False, f'Backup directory does not exist:\n{backup_dir}')
        if not os.path.isfile(self.master_db_path):
            return (False, f'Master registry database not found:\n{self.master_db_path}')
        return (True, '')

    def _start_year_end_process(self) -> None:
        is_valid, error_message = self._validate_inputs()
        if not is_valid:
            QMessageBox.warning(self, 'Validation Error', error_message)
            return
        confirm = QMessageBox.question(self, 'Confirm Year-End Processing', 'This action will lock the current financial year database and create a new company database with carried-forward balances.\n\nDo you want to continue?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        new_company_name = self.new_company_input.text().strip()
        backup_dir = self.backup_dir_input.text().strip()
        new_db_path = self._build_new_database_path(new_company_name)
        self._set_form_enabled(False)
        progress = QProgressDialog('Processing year-end closing. Please wait...', None, 0, 0, self)
        progress.setWindowTitle('Year-End Processing')
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        try:
            success, message = process_financial_year(self.db_path, new_db_path, new_company_name, backup_dir, self.master_db_path)
        finally:
            progress.close()
            self._set_form_enabled(True)
        if not success:
            QMessageBox.critical(self, 'Year-End Processing Failed', message)
            return
        QMessageBox.information(self, 'Year-End Processing Complete', 'Year End Processing Complete! The application will now close. Please log in to the new financial year.')
        QApplication.quit()
        sys.exit(0)