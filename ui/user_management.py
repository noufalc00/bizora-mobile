"""
Admin user management dialog for application users and module permissions.
"""
import hashlib
import os
import sqlite3
from contextlib import closing
from typing import Callable, Dict, List, Optional
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout
from config import COLORS, DATABASE_NAME, active_company_manager
from ui.table_header_utils import apply_adjustable_table_columns
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin, configure_non_modal_window
try:
    import db as database_module
    from db import ensure_company_users_table
except ImportError:
    database_module = None
    ensure_company_users_table = None

class UserManagementDialog(UiMemoryMixin, QDialog):
    """Dialog for Admin users to add, edit, and permission application users."""
    FEATURE_NAMES = ['Sales', 'Purchases', 'Quotations', 'Payments', 'Receipts', 'Reports', 'Settings']

    def __init__(self, parent=None, db_path: Optional[str]=None):
        """
        Initialize the user management dialog.

        Args:
            parent: Optional parent widget for modal ownership.
            db_path: Optional SQLite database path, mainly for smoke tests.
        """
        super().__init__(parent)
        parent_db_path = getattr(parent, 'db_path', None) if parent is not None else None
        self.db_path = db_path or parent_db_path or self._resolve_database_path()
        self.company_id = self._resolve_company_id(parent)
        if ensure_company_users_table is not None:
            ensure_company_users_table(self.db_path, self.company_id)
        self._hash_password = self._resolve_hash_helper()
        self.selected_user_id = None
        self.feature_checkboxes: Dict[str, object] = {}
        self.setWindowTitle('Admin User Management')
        self.setMinimumSize(980, 620)
        self.setStyleSheet(self._dialog_style())
        self._setup_ui()
        self._connect_signals()
        self.load_users()
        self.clear_form()
        self._init_ui_memory()
        configure_non_modal_window(self, parent)

    def _setup_ui(self) -> None:
        """Build the two-panel user table and add/edit form layout."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)
        header_label = QLabel('Admin User Management')
        header_label.setObjectName('titleLabel')
        root_layout.addWidget(header_label)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)
        root_layout.addLayout(content_layout, 1)
        left_panel = self._create_left_panel()
        right_panel = self._create_right_panel()
        content_layout.addWidget(left_panel, 3)
        content_layout.addWidget(right_panel, 2)
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_button = QPushButton('Close')
        close_button.setObjectName('secondaryButton')
        close_button.clicked.connect(self.reject)
        close_layout.addWidget(close_button)
        root_layout.addLayout(close_layout)

    def _create_left_panel(self) -> QFrame:
        """Create the user list panel without exposing password hashes."""
        panel = QFrame()
        panel.setObjectName('panel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        title = QLabel('Users')
        title.setObjectName('sectionLabel')
        layout.addWidget(title)
        self.users_table = QTableWidget(0, 4)
        self.users_table.setHorizontalHeaderLabels(['ID', 'Username', 'Role', 'Permissions'])
        self.users_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.users_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.users_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.users_table.setFocusPolicy(Qt.StrongFocus)
        self.users_table.verticalHeader().setVisible(False)
        layout.addWidget(self.users_table, 1)
        return panel

    def _create_right_panel(self) -> QFrame:
        """Create the user add/edit form and feature permission checkboxes."""
        panel = QFrame()
        panel.setObjectName('panel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        title = QLabel('Add / Edit User')
        title.setObjectName('sectionLabel')
        layout.addWidget(title)
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_layout.setSpacing(12)
        layout.addLayout(form_layout)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText('Username')
        form_layout.addRow('Username', self.username_input)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText('Required for new users')
        form_layout.addRow('Password', self.password_input)
        self.role_combo = QComboBox()
        self.role_combo.addItems(['User', 'Admin'])
        form_layout.addRow('Role', self.role_combo)
        feature_group = QGroupBox('Feature Access')
        feature_layout = QGridLayout(feature_group)
        feature_layout.setContentsMargins(14, 18, 14, 14)
        feature_layout.setSpacing(10)
        for index, feature_name in enumerate(self.FEATURE_NAMES):
            checkbox = self._create_feature_checkbox(feature_name)
            self.feature_checkboxes[feature_name] = checkbox
            feature_layout.addWidget(checkbox, index // 2, index % 2)
        layout.addWidget(feature_group)
        hint_label = QLabel('Admin role always saves ALL permissions. Leave password blank when editing to keep the existing password.')
        hint_label.setObjectName('hintLabel')
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        button_layout = QHBoxLayout()
        self.clear_button = QPushButton('New / Clear')
        self.clear_button.setObjectName('secondaryButton')
        self.save_button = QPushButton('Add User')
        self.save_button.setObjectName('primaryButton')
        self.reset_pwd_btn = QPushButton('Force Reset Password')
        self.reset_pwd_btn.setObjectName('secondaryButton')
        self.delete_button = QPushButton('Delete User')
        self.delete_button.setObjectName('dangerButton')
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch()
        button_layout.addWidget(self.reset_pwd_btn)
        button_layout.addWidget(self.save_button)
        layout.addLayout(button_layout)
        layout.addStretch()
        return panel

    def _create_feature_checkbox(self, title: str):
        """
        Create a feature checkbox.

        Args:
            title: Feature name displayed to the administrator.
        """
        from ui.checkbox_style import create_checkbox
        checkbox = create_checkbox(title, variant='default')
        checkbox.setMinimumHeight(28)
        return checkbox

    def _connect_signals(self) -> None:
        """Connect table selection, role changes, and user action buttons."""
        self.users_table.cellClicked.connect(self.populate_form_from_row)
        self.clear_button.clicked.connect(self.clear_form)
        self.save_button.clicked.connect(self.save_user)
        self.reset_pwd_btn.clicked.connect(self.reset_password)
        self.delete_button.clicked.connect(self.delete_user)
        self.role_combo.currentTextChanged.connect(self._sync_role_permissions)
        self.username_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.save_user)

    def load_users(self) -> None:
        """Load users from the configured users table into the user list."""
        try:
            with self._open_connection() as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute('\n                        SELECT id, username, role, permissions\n                        FROM users\n                        WHERE company_id = ?\n                        ORDER BY username\n                        ', (self.company_id,))
                    records = cursor.fetchall()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, 'Database Error', f'Unable to load users: {exc}')
            return
        self.users_table.setRowCount(0)
        for row_index, record in enumerate(records):
            self.users_table.insertRow(row_index)
            self._set_user_table_row(row_index, record)
            QCoreApplication.processEvents()
        apply_adjustable_table_columns(self.users_table)

    def _set_user_table_row(self, row_index: int, record: tuple) -> None:
        """
        Populate one user table row.

        Args:
            row_index: Target table row.
            record: Tuple containing id, username, role, and permissions.
        """
        user_id, username, role, permissions = record
        id_item = QTableWidgetItem(str(user_id))
        id_item.setData(Qt.ItemDataRole.UserRole, user_id)
        id_item.setData(Qt.ItemDataRole.UserRole + 1, permissions or '')
        username_item = QTableWidgetItem(username or '')
        role_item = QTableWidgetItem(role or 'User')
        permissions_item = QTableWidgetItem(self._permissions_summary(permissions or ''))
        self.users_table.setItem(row_index, 0, id_item)
        self.users_table.setItem(row_index, 1, username_item)
        self.users_table.setItem(row_index, 2, role_item)
        self.users_table.setItem(row_index, 3, permissions_item)

    def populate_form_from_row(self, row_index: int, column_index: int=0) -> None:
        """
        Populate the form from a clicked user row.

        Args:
            row_index: Clicked table row.
            column_index: Clicked table column, unused but required by signal.
        """
        del column_index
        self.users_table.selectRow(row_index)
        id_item = self.users_table.item(row_index, 0)
        username_item = self.users_table.item(row_index, 1)
        role_item = self.users_table.item(row_index, 2)
        if id_item is None or username_item is None or role_item is None:
            return
        self.selected_user_id = id_item.data(Qt.ItemDataRole.UserRole)
        permissions = id_item.data(Qt.ItemDataRole.UserRole + 1) or ''
        self.username_input.setText(username_item.text())
        self.password_input.clear()
        self.password_input.setPlaceholderText('Leave blank to keep password')
        self.role_combo.setCurrentText(role_item.text() or 'User')
        self._apply_permissions_to_checkboxes(permissions)
        self.save_button.setText('Update User')
        self.delete_button.setEnabled(True)

    def clear_form(self) -> None:
        """Reset the form for adding a new user."""
        self.selected_user_id = None
        self.users_table.clearSelection()
        self.username_input.clear()
        self.password_input.clear()
        self.password_input.setPlaceholderText('Required for new users')
        self.role_combo.setCurrentText('User')
        self._apply_permissions_to_checkboxes('')
        self.save_button.setText('Add User')
        self.delete_button.setEnabled(False)
        self.username_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def save_user(self) -> None:
        """Create a new user or update the selected user after validation."""
        username = self.username_input.text().strip()
        password = self.password_input.text()
        role = self.role_combo.currentText()
        permissions = self._selected_permissions_for_save(role)
        if not username:
            QMessageBox.warning(self, 'Validation Error', 'Username is required.')
            self.username_input.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if self.selected_user_id is None:
            self._create_user(username, password, role, permissions)
            return
        if not self._can_update_selected_user(role):
            return
        self._update_user(username, password, role, permissions)

    def delete_user(self) -> None:
        """Delete the selected user after confirmation and safety checks."""
        if self.selected_user_id is None:
            QMessageBox.warning(self, 'No User Selected', 'Select a user before deleting.')
            return
        username = self.username_input.text().strip()
        role = self._selected_user_role()
        if role == 'Admin' and self._admin_count() <= 1:
            QMessageBox.warning(self, 'Cannot Delete Last Admin', 'At least one Admin user must remain in the system.')
            return
        if self._is_current_session_user(username):
            QMessageBox.warning(self, 'Cannot Delete Current User', 'Log in with another Admin account before deleting this user.')
            return
        response = QMessageBox.question(self, 'Confirm Delete', f"Delete user '{username}'? This action cannot be undone.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            with self._open_connection() as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute('\n                        DELETE FROM users\n                        WHERE id = ?\n                          AND company_id = ?\n                        ', (self.selected_user_id, self.company_id))
                    if cursor.rowcount == 0:
                        QMessageBox.warning(self, 'User Not Found', 'The selected user no longer exists.')
                        return
                connection.commit()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, 'Database Error', f'Unable to delete user: {exc}')
            return
        QMessageBox.information(self, 'User Deleted', 'User deleted successfully.')
        self.load_users()
        self.clear_form()

    def reset_password(self) -> None:
        """Force reset the selected user's password using the password field."""
        selected_row = self.users_table.currentRow()
        username_item = self.users_table.item(selected_row, 1) if selected_row >= 0 else None
        if selected_row < 0 or username_item is None:
            QMessageBox.warning(self, 'No User Selected', 'Select a user before resetting the password.')
            return
        target_username = username_item.text().strip()
        if not target_username:
            QMessageBox.warning(self, 'No User Selected', 'Select a valid user before resetting the password.')
            return
        new_password = self.password_input.text()
        if not new_password:
            QMessageBox.warning(self, 'Validation Error', 'Please type a new password to reset')
            self.password_input.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        try:
            with self._open_connection() as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute('\n                        UPDATE users\n                        SET password = ?,\n                            password_hash = ?\n                        WHERE company_id = ?\n                          AND username = ?\n                        ', (new_password, self._hash_password(new_password), self.company_id, target_username))
                    if cursor.rowcount == 0:
                        QMessageBox.warning(self, 'User Not Found', 'The selected user no longer exists.')
                        return
                connection.commit()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, 'Database Error', f'Unable to reset password: {exc}')
            return
        QMessageBox.information(self, 'Password Reset', f'Password successfully reset for {target_username}')
        self.password_input.clear()

    def _create_user(self, username: str, password: str, role: str, permissions: str) -> None:
        """
        Insert a new user with a hashed password.

        Args:
            username: New username.
            password: Plain text password to hash before storage.
            role: User role.
            permissions: Comma-separated feature access or ALL.
        """
        if not password:
            QMessageBox.warning(self, 'Validation Error', 'Password is required when adding a new user.')
            self.password_input.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        try:
            with self._open_connection() as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute('\n                        INSERT INTO users (\n                            company_id, username, password, password_hash, role, permissions\n                        ) VALUES (?, ?, ?, ?, ?, ?)\n                        ', (self.company_id, username, password, self._hash_password(password), role, permissions))
                connection.commit()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, 'Duplicate Username', 'A user with this username already exists.')
            return
        except sqlite3.Error as exc:
            QMessageBox.critical(self, 'Database Error', f'Unable to add user: {exc}')
            return
        QMessageBox.information(self, 'User Added', 'User saved successfully.')
        self.load_users()
        self.clear_form()

    def _update_user(self, username: str, password: str, role: str, permissions: str) -> None:
        """
        Update the selected user, changing password only when provided.

        Args:
            username: Updated username.
            password: Optional new plain text password.
            role: Updated role.
            permissions: Updated feature access.
        """
        try:
            with self._open_connection() as connection:
                with closing(connection.cursor()) as cursor:
                    if password:
                        cursor.execute('\n                            UPDATE users\n                            SET username = ?,\n                                password = ?,\n                                password_hash = ?,\n                                role = ?,\n                                permissions = ?\n                            WHERE id = ?\n                              AND company_id = ?\n                            ', (username, password, self._hash_password(password), role, permissions, self.selected_user_id, self.company_id))
                    else:
                        cursor.execute('\n                            UPDATE users\n                            SET username = ?,\n                                role = ?,\n                                permissions = ?\n                            WHERE id = ?\n                              AND company_id = ?\n                            ', (username, role, permissions, self.selected_user_id, self.company_id))
                    if cursor.rowcount == 0:
                        QMessageBox.warning(self, 'User Not Found', 'The selected user no longer exists.')
                        return
                connection.commit()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, 'Duplicate Username', 'A user with this username already exists.')
            return
        except sqlite3.Error as exc:
            QMessageBox.critical(self, 'Database Error', f'Unable to update user: {exc}')
            return
        QMessageBox.information(self, 'User Updated', 'User updated successfully.')
        self.load_users()
        self.clear_form()

    def _can_update_selected_user(self, new_role: str) -> bool:
        """
        Return whether the selected user can be updated to the requested role.

        Args:
            new_role: Role selected in the edit form.
        """
        existing_role = self._selected_user_role()
        if existing_role == 'Admin' and new_role != 'Admin' and (self._admin_count() <= 1):
            QMessageBox.warning(self, 'Cannot Demote Last Admin', 'At least one Admin user must remain in the system.')
            return False
        return True

    def _selected_user_role(self) -> str:
        """Return the database role for the selected user."""
        if self.selected_user_id is None:
            return ''
        try:
            with self._open_connection() as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute('\n                        SELECT role\n                        FROM users\n                        WHERE id = ?\n                          AND company_id = ?\n                        ', (self.selected_user_id, self.company_id))
                    record = cursor.fetchone()
        except sqlite3.Error:
            return self.role_combo.currentText()
        return record[0] if record else self.role_combo.currentText()

    def _admin_count(self) -> int:
        """Return the number of Admin users currently stored."""
        try:
            with self._open_connection() as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute('\n                        SELECT COUNT(id)\n                        FROM users\n                        WHERE company_id = ?\n                          AND role = ?\n                        ', (self.company_id, 'Admin'))
                    record = cursor.fetchone()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, 'Database Error', f'Unable to verify Admin users: {exc}')
            return 0
        return int(record[0] or 0) if record else 0

    def _is_current_session_user(self, username: str) -> bool:
        """
        Return True when the selected user is the authenticated session user.

        Args:
            username: Username selected for deletion.
        """
        parent = self.parent()
        if parent is None:
            return False
        current_user = getattr(parent, 'current_user', None)
        if isinstance(current_user, dict):
            current_user = current_user.get('username') or current_user.get('name')
        if not current_user:
            user_record = getattr(parent, 'current_user_record', None)
            if isinstance(user_record, dict):
                current_user = user_record.get('username') or user_record.get('name')
        return bool(username and current_user and (username == current_user))

    def _open_connection(self):
        """Return a localized SQLite connection with app-standard pragmas."""
        if not self.db_path:
            raise sqlite3.Error('No active company database is available.')
        if self.company_id is None:
            raise sqlite3.Error('No active company is selected for user management.')
        if ensure_company_users_table is not None:
            ensure_company_users_table(self.db_path, self.company_id)
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.execute('PRAGMA busy_timeout = 5000;')
        connection.execute('PRAGMA journal_mode = DELETE;')
        connection.execute('PRAGMA synchronous = NORMAL;')
        return closing(connection)

    def _resolve_company_id(self, parent) -> Optional[int]:
        """Return the active company ID for company-scoped user CRUD."""
        active_company = active_company_manager.get_active_company()
        if active_company and active_company.get('id') is not None:
            return int(active_company['id'])
        parent_db = getattr(parent, 'db', None) if parent is not None else None
        if parent_db is not None:
            try:
                active_company = parent_db.get_active_company()
                if active_company and active_company.get('id') is not None:
                    return int(active_company['id'])
            except Exception:
                return None
        return None

    def _selected_permissions_for_save(self, role: str) -> str:
        """
        Return the normalized permission string for saving.

        Args:
            role: Selected role from the form.
        """
        if role == 'Admin':
            return 'ALL'
        selected_features: List[str] = []
        for feature_name in self.FEATURE_NAMES:
            checkbox = self.feature_checkboxes[feature_name]
            if checkbox.isChecked():
                selected_features.append(feature_name)
        return ','.join(selected_features)

    def _apply_permissions_to_checkboxes(self, permissions: str) -> None:
        """
        Apply a saved permission string to the feature checkboxes.

        Args:
            permissions: Comma-separated features or ALL.
        """
        normalized_permissions = (permissions or '').strip()
        has_all_permissions = normalized_permissions.upper() == 'ALL'
        selected = {value.strip() for value in normalized_permissions.split(',') if value.strip()}
        for feature_name, checkbox in self.feature_checkboxes.items():
            checkbox.setChecked(has_all_permissions or feature_name in selected)
        self._sync_role_permissions(self.role_combo.currentText())

    def _sync_role_permissions(self, role: str) -> None:
        """
        Keep Admin permissions locked to all feature access.

        Args:
            role: Current role value.
        """
        is_admin = role == 'Admin'
        for checkbox in self.feature_checkboxes.values():
            checkbox.setEnabled(not is_admin)
            if is_admin:
                checkbox.setChecked(True)

    def _permissions_summary(self, permissions: str) -> str:
        """
        Return a readable permission summary for the user table.

        Args:
            permissions: Comma-separated features or ALL.
        """
        normalized_permissions = (permissions or '').strip()
        if normalized_permissions.upper() == 'ALL':
            return 'All Features'
        if not normalized_permissions:
            return 'No Feature Access'
        return normalized_permissions

    def _resolve_database_path(self) -> str:
        """Resolve the configured SQLite database path used by the app."""
        configured_path = None
        base_dir = None
        if database_module is not None:
            path_getter = getattr(database_module, 'get_default_database_path', None)
            if callable(path_getter):
                configured_path = path_getter()
            if not configured_path:
                configured_path = getattr(database_module, 'DB_PATH', None)
            if not configured_path:
                database_class = getattr(database_module, 'Database', None)
                if database_class is not None:
                    configured_path = database_class(db_type='sqlite').db_path
            base_dir = getattr(database_module, 'BASE_DIR', None)
        if not configured_path:
            configured_path = DATABASE_NAME
        configured_path = str(configured_path)
        if os.path.isabs(configured_path):
            return configured_path
        if base_dir:
            return os.path.abspath(os.path.join(str(base_dir), configured_path))
        return os.path.abspath(configured_path)

    def _resolve_hash_helper(self) -> Callable[[str], str]:
        """Return the project password hasher, falling back to SHA-256."""
        if database_module is not None:
            hash_helper = getattr(database_module, 'hash_password', None)
            if callable(hash_helper):
                return hash_helper
        return self._fallback_hash_password

    def _fallback_hash_password(self, password: str) -> str:
        """
        Return a SHA-256 password digest when db.hash_password is unavailable.

        Args:
            password: Plain text password.
        """
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def _dialog_style(self) -> str:
        """Return a dark professional stylesheet consistent with the app."""
        from ui.checkbox_style import checkbox_indicator_style
        return f"\n            QDialog {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n            }}\n            QLabel {{\n                color: {COLORS['text_primary']};\n                font-size: 13px;\n                background: transparent;\n            }}\n            QLabel#titleLabel {{\n                font-size: 22px;\n                font-weight: bold;\n                color: {COLORS['text_primary']};\n            }}\n            QLabel#sectionLabel {{\n                font-size: 16px;\n                font-weight: bold;\n                color: {COLORS['primary_light']};\n            }}\n            QLabel#hintLabel {{\n                color: {COLORS['text_secondary']};\n                font-size: 12px;\n            }}\n            QFrame#panel {{\n                background-color: {COLORS['surface']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 8px;\n            }}\n            QLineEdit, QComboBox {{\n                background-color: {COLORS['card']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 8px 10px;\n                min-height: 24px;\n            }}\n            QLineEdit:focus, QComboBox:focus {{\n                border-color: {COLORS['border_focus']};\n            }}\n            QGroupBox {{\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 8px;\n                margin-top: 10px;\n                font-weight: bold;\n                padding-top: 8px;\n            }}\n            QGroupBox::title {{\n                subcontrol-origin: margin;\n                left: 12px;\n                padding: 0 6px;\n                color: {COLORS['primary_light']};\n            }}\n            QCheckBox {{\n                color: {COLORS['text_primary']};\n                spacing: 8px;\n                font-size: 13px;\n                font-weight: bold;\n            }}\n            {checkbox_indicator_style()}\n            QCheckBox:disabled {{\n                color: {COLORS['text_secondary']};\n            }}\n            QTableWidget {{\n                background-color: {COLORS['card']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                gridline-color: {COLORS['border']};\n                selection-background-color: {COLORS['primary_dark']};\n                selection-color: #ffffff;\n            }}\n            QTableWidget::item {{\n                padding: 7px;\n            }}\n            QTableWidget::item:selected {{\n                background-color: {COLORS['primary']};\n                color: #ffffff;\n            }}\n            QTableWidget::item:selected:!active {{\n                background-color: {COLORS['primary']};\n                color: #ffffff;\n            }}\n            QHeaderView::section {{\n                background-color: #111827;\n                color: #ffffff;\n                border: none;\n                border-right: 1px solid {COLORS['border']};\n                padding: 8px;\n                font-weight: bold;\n            }}\n            QPushButton {{\n                border: none;\n                border-radius: 6px;\n                padding: 9px 16px;\n                font-weight: bold;\n            }}\n            QPushButton#primaryButton {{\n                background-color: {COLORS['primary']};\n                color: #ffffff;\n            }}\n            QPushButton#primaryButton:hover {{\n                background-color: {COLORS['primary_dark']};\n            }}\n            QPushButton#secondaryButton {{\n                background-color: {COLORS['button_default']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n            }}\n            QPushButton#secondaryButton:hover {{\n                background-color: {COLORS['button_hover']};\n            }}\n            QPushButton#dangerButton {{\n                background-color: #dc2626;\n                color: #ffffff;\n            }}\n            QPushButton#dangerButton:hover {{\n                background-color: #b91c1c;\n            }}\n            QPushButton#dangerButton:disabled {{\n                background-color: {COLORS['button_default']};\n                color: {COLORS['text_secondary']};\n            }}\n        "