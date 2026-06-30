"""
Login dialog for authenticating users before opening the accounting app.
"""
import hashlib
import os
import sqlite3
from contextlib import closing
from typing import Callable, Optional
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout
from ui.brand_logo import create_brand_logo_box, refresh_brand_logo_box
from ui.ui_memory import UiMemoryMixin
from ui import theme
from ui.message_boxes import show_message
try:
    import db as database_module
except ImportError:
    database_module = None
try:
    from config import DATABASE_NAME
except ImportError:
    DATABASE_NAME = 'accounting.db'

class UsernameComboBox(QComboBox):
    """Username selector with QLineEdit-like helpers for legacy callers."""

    def text(self) -> str:
        """Return the currently selected username text."""
        return self.currentText()

    def setText(self, username: str) -> None:
        """
        Select a username, adding it only when a legacy caller supplies a new value.

        Args:
            username: Username text to select.
        """
        index = self.findText(username)
        if index < 0:
            self.addItem(username)
            index = self.count() - 1
        self.setCurrentIndex(index)

class LoginWindow(UiMemoryMixin, QDialog):
    """Modal dark-themed login window backed by the configured users table."""

    def __init__(self, db_path: str='faizan_pro.db', parent=None):
        """
        Initialize the login dialog and resolve the active SQLite database path.

        Args:
            db_path: SQLite database path used for authentication.
            parent: Optional parent widget for modal ownership.
        """
        super().__init__(parent)
        self.username = None
        self.role = None
        self.permissions = None
        self.current_user = None
        self.db_path = db_path or self._resolve_database_path()
        self._hash_password = self._resolve_hash_helper()
        self.setWindowTitle('Login')
        self.setWindowModality(Qt.ApplicationModal)
        self.setModal(True)
        self.setFixedSize(450, 380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMinimizeButtonHint & ~Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(theme.login_page_shell_style())
        self._setup_ui()
        self._connect_signals()
        self._init_ui_memory()

    def _setup_ui(self) -> None:
        """Build the username, password, and login action controls."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 16, 24, 14)
        root_layout.setSpacing(8)
        self.logo_box, self.brand_logo_label = create_brand_logo_box(
            380,
            155,
            label_object_name='loginBrandLogo',
            sidebar_variant=True,
        )
        root_layout.addWidget(self.logo_box, alignment=Qt.AlignCenter)
        self.subtitle_label = QLabel('Sign in to continue')
        self.subtitle_label.setObjectName('subtitleLabel')
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet('')
        root_layout.addWidget(self.subtitle_label)
        form_layout = QFormLayout()
        form_layout.setContentsMargins(0, 4, 0, 0)
        form_layout.setSpacing(8)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root_layout.addLayout(form_layout)
        self.username_combo = UsernameComboBox()
        self.username_combo.setObjectName('usernameCombo')
        self.username_combo.setPlaceholderText('Select username')
        self.username_combo.setMinimumHeight(38)
        self.username_combo.installEventFilter(self)
        self.username_input = self.username_combo
        form_layout.addRow(self._create_form_label('Username'), self.username_combo)
        self._load_usernames()
        self.password_input = QLineEdit()
        self.password_input.setObjectName('passwordInput')
        self.password_input.setPlaceholderText('Password')
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(38)
        form_layout.addRow(self._create_form_label('Password'), self.password_input)
        self.login_button = QPushButton('Login')
        self.login_button.setObjectName('loginButton')
        self.login_button.setMinimumHeight(34)
        self.login_button.setDefault(True)
        root_layout.addWidget(self.login_button)
        hint_label = QLabel('Press Enter to login. Press Escape to close.')
        hint_label.setObjectName('hintLabel')
        hint_label.setAlignment(Qt.AlignCenter)
        root_layout.addWidget(hint_label)
        self.username_combo.setFocus(Qt.FocusReason.OtherFocusReason)

    def _connect_signals(self) -> None:
        """Connect Enter key and login button actions."""
        self.login_button.clicked.connect(self.authenticate)
        self.password_input.returnPressed.connect(self.authenticate)

    def eventFilter(self, watched, event) -> bool:
        """
        Move from the username combo to password when Enter is pressed.

        Args:
            watched: Widget receiving the event.
            event: Qt event sent to the watched widget.
        """
        if watched is self.username_combo and event.type() == QEvent.Type.KeyPress and (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self.password_input.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        return super().eventFilter(watched, event)

    def _create_form_label(self, title: str) -> QLabel:
        """
        Create a consistently styled form label.

        Args:
            title: Text displayed beside an input field.
        """
        label = QLabel(title)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return label

    def authenticate(self) -> None:
        """Validate entered credentials against the configured SQLite users table."""
        entered_username = self.username_combo.currentText().strip()
        entered_password = self.password_input.text()
        if not entered_username or not entered_password:
            self._show_invalid_credentials()
            return
        try:
            user_record = self._fetch_user_record(entered_username)
        except sqlite3.Error:
            self._show_login_dialog_message(QMessageBox.Icon.Critical, 'Database Error', 'Unable to validate credentials. Please contact administrator.')
            return
        if user_record is None:
            self._show_invalid_credentials()
            return
        stored_password_hash = user_record[0]
        role = user_record[1]
        permissions = user_record[2] or ''
        entered_password_hash = self._hash_password(entered_password)
        if entered_password_hash != stored_password_hash:
            self._show_invalid_credentials()
            return
        self.username = entered_username
        self.role = role
        self.permissions = permissions
        self.current_user = {'username': entered_username, 'role': role, 'permissions': permissions}
        self.accept()

    def _load_usernames(self) -> None:
        """Populate the username combo from the configured users table."""
        try:
            with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
                connection.execute('PRAGMA busy_timeout = 5000;')
                connection.execute('PRAGMA journal_mode = DELETE;')
                connection.execute('PRAGMA synchronous = NORMAL;')
                with closing(connection.cursor()) as cursor:
                    cursor.execute('\n                        SELECT username\n                        FROM users\n                        ORDER BY username\n                        ')
                    fetched_rows = cursor.fetchall()
        except sqlite3.Error as exc:
            self._show_login_dialog_message(QMessageBox.Icon.Critical, 'Database Error', f'Unable to load users: {exc}')
            fetched_rows = []
        self.username_combo.clear()
        self.username_combo.addItems([row[0] for row in fetched_rows])

    def _fetch_user_record(self, username: str) -> Optional[tuple]:
        """
        Return the stored authentication record for a username.

        Args:
            username: Login username entered by the operator.
        """
        with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
            connection.execute('PRAGMA busy_timeout = 5000;')
            connection.execute('PRAGMA journal_mode = DELETE;')
            connection.execute('PRAGMA synchronous = NORMAL;')
            with closing(connection.cursor()) as cursor:
                cursor.execute('\n                    SELECT password_hash, role, permissions\n                    FROM users\n                    WHERE username = ?\n                    ', (username,))
                return cursor.fetchone()

    def _resolve_database_path(self) -> str:
        """Resolve the same SQLite database location used by the app database layer."""
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
        """Return the project password hasher, falling back to SHA-256 locally."""
        if database_module is not None:
            hash_helper = getattr(database_module, 'hash_password', None)
            if callable(hash_helper):
                return hash_helper
        return self._fallback_hash_password

    def _fallback_hash_password(self, password: str) -> str:
        """
        Return the SHA-256 password digest used by the seeded users table.

        Args:
            password: Plain text password entered by the operator.
        """
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def _show_invalid_credentials(self) -> None:
        """Warn the operator about failed authentication."""
        self._show_login_dialog_message(QMessageBox.Icon.Warning, 'Login Failed', 'Invalid credentials')

    def _show_login_dialog_message(self, icon, title: str, text: str) -> None:
        """Show a login-owned message box using the active application theme."""
        show_message(self, icon, title, text)

    def refresh_theme(self) -> None:
        """Re-apply theme-aware shell styles after a global theme change."""
        self.setStyleSheet(theme.login_page_shell_style())
        if hasattr(self, 'logo_box'):
            refresh_brand_logo_box(
                self.logo_box,
                self.brand_logo_label,
                380,
                155,
                sidebar_variant=True,
            )
        elif hasattr(self, 'brand_logo_label'):
            self.brand_logo_label.setStyleSheet('background: transparent; border: none;')