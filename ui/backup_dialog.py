"""
Backup and restore settings dialog for company database files.
"""
from __future__ import annotations
import os
import re
import sqlite3
import sys
from contextlib import closing
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget
from ui import theme
from ui.book_report_common import report_dialog_body_style, report_group_box_style
from utils.backup_manager import execute_backup, schedule_restore_on_restart
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin, configure_non_modal_window
BACKUP_DIR_KEY = 'backup_dir'
AUTO_BACKUP_KEY = 'auto_backup_enabled'

class BackupRestoreDialog(UiMemoryMixin, QDialog):
    """Dialog for configuring backups and restoring company database files."""

    def __init__(self, db_path: str, company_name: str, parent=None):
        """Initialize the backup and restore dialog for a company database."""
        super().__init__(parent)
        self.db_path = db_path
        self.company_name = company_name or 'company'
        self.setWindowTitle('Backup and Restore Data')
        self._ui_memory_geometry_key = 'backup_restore'
        self.resize(600, 450)
        self.setStyleSheet(self._dialog_stylesheet())
        self._build_ui()
        self._ensure_settings_table()
        self._load_settings()
        configure_non_modal_window(self, parent)
        self._init_ui_memory()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

    def _dialog_stylesheet(self) -> str:
        """Return the theme-aware dialog stylesheet with backup-specific accents."""
        from ui.checkbox_style import checkbox_indicator_style

        colors = theme._theme_colors()
        return f"""
            {report_dialog_body_style()}
            {report_group_box_style()}
            {theme.scrollbar_stylesheet()}
            QGroupBox#restoreGroup {{
                border: 1px solid {colors['button_danger']};
                color: {colors['button_warning']};
            }}
            QLabel#warningLabel {{
                color: {colors['button_warning']};
                font-size: 13px;
                font-weight: bold;
            }}
            QLineEdit {{
                background-color: {colors['input_bg']};
                color: {colors['input_text']};
                border: 1px solid {colors['border']};
                border-radius: 5px;
                padding: 9px 10px;
                font-size: 13px;
            }}
            QCheckBox {{
                color: {colors['input_text']};
                font-size: 13px;
                spacing: 8px;
            }}
            {checkbox_indicator_style()}
            QPushButton {{
                background-color: {colors['panel_bg']};
                color: {colors['input_text']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 9px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {colors.get('surface_alt', colors['panel_bg'])};
                border-color: {colors['focus_border']};
            }}
            QPushButton#manualBackupButton {{
                background-color: {colors['button_success']};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 13px 16px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton#manualBackupButton:hover {{
                background-color: {colors['button_success']};
            }}
            QPushButton#restoreButton {{
                background-color: {colors['button_danger']};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 13px 16px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton#restoreButton:hover {{
                background-color: {colors['button_danger']};
            }}
        """

    def _build_ui(self) -> None:
        """Create the backup and restore controls."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 18, 22, 18)
        main_layout.setSpacing(16)
        backup_group = QGroupBox('Data Backup')
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.setContentsMargins(16, 22, 16, 14)
        backup_layout.setSpacing(14)
        path_layout = QHBoxLayout()
        path_layout.setSpacing(10)
        path_label = QLabel('Backup Folder Path:')
        self.backup_path_input = QLineEdit()
        self.backup_path_input.setReadOnly(True)
        self.backup_path_input.setPlaceholderText('No backup folder selected')
        self.browse_button = QPushButton('Browse...')
        self.browse_button.clicked.connect(self.browse_backup_folder)
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.backup_path_input, 1)
        path_layout.addWidget(self.browse_button)
        backup_layout.addLayout(path_layout)
        from ui.checkbox_style import create_checkbox
        self.auto_backup_checkbox = create_checkbox('Auto-Backup on Application Close', variant='default')
        backup_layout.addWidget(self.auto_backup_checkbox)
        self.manual_backup_button = QPushButton('Run Manual Backup Now')
        self.manual_backup_button.setObjectName('manualBackupButton')
        self.manual_backup_button.clicked.connect(self.run_manual_backup)
        backup_layout.addWidget(self.manual_backup_button)
        main_layout.addWidget(backup_group)
        restore_group = QGroupBox('Data Restoration (DANGER)')
        restore_group.setObjectName('restoreGroup')
        restore_layout = QVBoxLayout(restore_group)
        restore_layout.setContentsMargins(16, 24, 16, 16)
        restore_layout.setSpacing(16)
        warning_label = QLabel('WARNING: Restoring data will overwrite all current database records. This action cannot be undone.')
        warning_label.setObjectName('warningLabel')
        warning_label.setWordWrap(True)
        restore_layout.addWidget(warning_label)
        self.restore_button = QPushButton('Restore from Backup File...')
        self.restore_button.setObjectName('restoreButton')
        self.restore_button.clicked.connect(self.restore_from_backup)
        restore_layout.addWidget(self.restore_button)
        main_layout.addWidget(restore_group)
        main_layout.addStretch()
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.save_button = QPushButton('Save')
        self.cancel_button = QPushButton('Cancel')
        self.save_button.clicked.connect(self.save_settings)
        self.cancel_button.clicked.connect(self.reject)
        footer_layout.addWidget(self.save_button)
        footer_layout.addWidget(self.cancel_button)
        main_layout.addLayout(footer_layout)

    def _ensure_settings_table(self) -> None:
        """Ensure the company database contains the settings table."""
        try:
            with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
                connection.execute('PRAGMA busy_timeout = 5000;')
                connection.execute('PRAGMA journal_mode = DELETE;')
                connection.execute('PRAGMA synchronous = NORMAL;')
                connection.execute('\n                    CREATE TABLE IF NOT EXISTS app_settings (\n                        setting_key TEXT PRIMARY KEY,\n                        setting_value TEXT\n                    )\n                    ')
                connection.commit()
        except sqlite3.Error as error:
            QMessageBox.critical(self, 'Settings Error', f'Unable to prepare backup settings:\n{error}')

    def _load_settings(self) -> None:
        """Load the saved backup directory and auto-backup preference."""
        settings = {BACKUP_DIR_KEY: '', AUTO_BACKUP_KEY: 'false'}
        try:
            with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
                connection.execute('PRAGMA busy_timeout = 5000;')
                with closing(connection.cursor()) as cursor:
                    cursor.execute('\n                        SELECT setting_key, setting_value\n                        FROM app_settings\n                        WHERE setting_key IN (?, ?)\n                        ', (BACKUP_DIR_KEY, AUTO_BACKUP_KEY))
                    for key, value in cursor.fetchall():
                        settings[key] = value or ''
        except sqlite3.Error as error:
            QMessageBox.warning(self, 'Settings Warning', f'Unable to load backup settings:\n{error}')
        self.backup_path_input.setText(settings[BACKUP_DIR_KEY])
        self.auto_backup_checkbox.setChecked(settings[AUTO_BACKUP_KEY].strip().lower() == 'true')

    def browse_backup_folder(self) -> None:
        """Choose the target directory for generated backup files."""
        selected_dir = QFileDialog.getExistingDirectory(self, 'Select Backup Folder', self.backup_path_input.text() or os.path.expanduser('~'))
        if selected_dir:
            self.backup_path_input.setText(selected_dir)

    def run_manual_backup(self) -> None:
        """Run an immediate backup into the selected backup directory."""
        target_dir = self.backup_path_input.text().strip()
        success, result = execute_backup(self.db_path, target_dir, self.company_name)
        if success:
            QMessageBox.information(self, 'Backup Complete', f'Backup created successfully:\n{result}')
            return
        QMessageBox.critical(self, 'Backup Failed', f'Could not create backup:\n{result}')

    def restore_from_backup(self) -> None:
        """Select and restore a backup database file after confirmation."""
        backup_file_path, _selected_filter = QFileDialog.getOpenFileName(self, 'Select Backup File', self.backup_path_input.text() or os.path.expanduser('~'), 'SQLite Database (*.db);;All Files (*)')
        if not backup_file_path:
            return
        confirmation = QMessageBox.warning(self, 'Confirm Restore', 'Restoring data will overwrite all current database records. This action cannot be undone.\n\nContinue?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        self._prepare_application_for_restore()
        restore_scheduled, restore_message = schedule_restore_on_restart(backup_file_path, self.db_path, self._current_company_id())
        if restore_scheduled:
            QMessageBox.information(self, 'Restore Complete', 'Backup restore is ready. The app will now close/restart.')
            QApplication.closeAllWindows()
            os.execl(sys.executable, sys.executable, *sys.argv)
            return
        QMessageBox.critical(self, 'Restore Failed', f'Could not prepare the selected backup file for restore:\n{restore_message}')
        self._restore_auto_backup_guard()

    def _prepare_application_for_restore(self) -> None:
        """Release app-owned database handles before overwriting the DB file."""
        parent_window = self.parent()
        if parent_window is not None:
            if hasattr(parent_window, 'skip_backup_on_close'):
                parent_window.skip_backup_on_close = True
            if hasattr(parent_window, '_close_tracked_module_windows'):
                parent_window._close_tracked_module_windows()
            database = getattr(parent_window, 'db', None)
            if database is not None:
                try:
                    if hasattr(database, 'force_disconnect'):
                        database.force_disconnect()
                    elif hasattr(database, 'disconnect'):
                        database.disconnect()
                except Exception as error:
                    print(f'[RESTORE] Could not close active database: {error}')
        QApplication.processEvents()

    def _restore_auto_backup_guard(self) -> None:
        """Allow normal close backup again if restore did not complete."""
        parent_window = self.parent()
        if parent_window is not None and hasattr(parent_window, 'skip_backup_on_close'):
            parent_window.skip_backup_on_close = False

    def _current_company_id(self):
        """Return the company ID currently being replaced by restore."""
        parent_window = self.parent()
        active_company = None
        if parent_window is not None:
            database = getattr(parent_window, 'db', None)
            if database is not None:
                try:
                    active_company = database.get_active_company()
                except Exception:
                    active_company = None
        if not active_company:
            try:
                from config import active_company_manager
                active_company = active_company_manager.get_active_company()
            except Exception:
                active_company = None
        try:
            return int(active_company.get('id')) if active_company else None
        except (TypeError, ValueError):
            return None

    def _register_restored_company(self, restored_company_name: str='') -> None:
        """Mark the restored company as active for the next gateway startup."""
        try:
            with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
                connection.execute('PRAGMA busy_timeout = 5000;')
                connection.execute('PRAGMA journal_mode = DELETE;')
                connection.execute('PRAGMA synchronous = NORMAL;')
                self._ensure_settings_table_for_connection(connection)
                company_record = self._select_restored_company(connection, restored_company_name)
                if company_record:
                    company_id, company_name = company_record
                    connection.execute('\n                        UPDATE companies\n                        SET is_active = 0\n                        ')
                    connection.execute('\n                        UPDATE companies\n                        SET is_active = 1\n                        WHERE id = ?\n                        ', (company_id,))
                    self._upsert_setting(connection, 'last_active_company_id', str(company_id))
                    self._upsert_setting(connection, 'last_active_company_name', company_name or restored_company_name or self.company_name)
                    self._upsert_setting(connection, 'last_active_company_path', os.path.abspath(self.db_path))
                connection.commit()
        except sqlite3.Error as error:
            QMessageBox.warning(self, 'Restore Warning', f'Backup restored, but the restored company could not be marked active:\n{error}')

    def _company_name_from_backup_file(self, backup_file_path: str) -> str:
        """Extract the company name prefix from a sequenced backup filename."""
        file_stem = os.path.splitext(os.path.basename(backup_file_path))[0]
        match = re.match('^(?P<company>.+)-\\d{2}-\\d{2}-\\d{4}-\\d{3}$', file_stem)
        if match:
            return match.group('company').strip()
        return ''

    def _ensure_settings_table_for_connection(self, connection: sqlite3.Connection) -> None:
        """Ensure app_settings exists on an already-open connection."""
        connection.execute('\n            CREATE TABLE IF NOT EXISTS app_settings (\n                setting_key TEXT PRIMARY KEY,\n                setting_value TEXT\n            )\n            ')

    def _select_restored_company(self, connection: sqlite3.Connection, restored_company_name: str=''):
        """Return the company row that should be active after restore."""
        cursor = connection.cursor()
        preferred_name = (restored_company_name or '').strip()
        if preferred_name:
            cursor.execute('\n                SELECT id, business_name\n                FROM companies\n                WHERE LOWER(TRIM(business_name)) = LOWER(TRIM(?))\n                ORDER BY id\n                LIMIT 1\n                ', (preferred_name,))
            company_record = cursor.fetchone()
            if company_record:
                return company_record
        cursor.execute('\n            SELECT id, business_name\n            FROM companies\n            ORDER BY is_active DESC, id\n            LIMIT 1\n            ')
        return cursor.fetchone()

    def save_settings(self) -> None:
        """Persist backup settings into the company database and close."""
        backup_dir = self.backup_path_input.text().strip()
        auto_backup_enabled = 'true' if self.auto_backup_checkbox.isChecked() else 'false'
        try:
            with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
                connection.execute('PRAGMA busy_timeout = 5000;')
                connection.execute('PRAGMA journal_mode = DELETE;')
                connection.execute('PRAGMA synchronous = NORMAL;')
                self._upsert_setting(connection, BACKUP_DIR_KEY, backup_dir)
                self._upsert_setting(connection, AUTO_BACKUP_KEY, auto_backup_enabled)
                connection.commit()
        except sqlite3.Error as error:
            QMessageBox.critical(self, 'Save Failed', f'Could not save backup settings:\n{error}')
            return
        self.accept()

    def _upsert_setting(self, connection: sqlite3.Connection, setting_key: str, setting_value: str) -> None:
        """Update or insert one app setting using ANSI-compatible SQL."""
        cursor = connection.cursor()
        cursor.execute('\n            UPDATE app_settings\n            SET setting_value = ?\n            WHERE setting_key = ?\n            ', (setting_value, setting_key))
        if cursor.rowcount == 0:
            cursor.execute('\n                INSERT INTO app_settings (setting_key, setting_value)\n                VALUES (?, ?)\n                ', (setting_key, setting_value))