"""
Initial company gateway dialog for Faizan Pro Accounting.

This standalone boot screen shows the last active company login and exposes
company switching and creation through a File menu.
"""
import sqlite3
import os
from contextlib import closing
from PySide6.QtCore import QDate, Qt, QTimer, Signal, QEvent, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDateEdit, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QToolButton, QVBoxLayout
from ui.loading_indicator import LoadingRunnerWidget
from ui.qt_pump import pump_ui_events
from ui.brand_logo import create_brand_logo_box, refresh_brand_logo_box
from config import APP_NAME, COMPANY_VISIBILITY_NORMAL, COMPANY_VISIBILITY_SECRET, active_company_manager
from db import Database, ensure_company_users_table, hash_password
from ui import theme
from ui.message_boxes import show_message
from ui.company_setup_view import CompanySetupView
from ui.login_window import UsernameComboBox
from ui.open_company_page import OpenCompanyPageWidget
from ui.secret_company_menu_dialog import SecretCompanyMenuDialog
from components.menu_icons import pixmap_for_menu_icon
from bizora_core.company_limits import company_limit_message, company_limit_reached, is_secret_company
from utils.theme_manager import ThemeManager
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin, clamp_window_to_available_screen

class CompanyGateway(UiMemoryMixin, QDialog):
    """Standalone company login dialog; also hosted inside MainWindow after logout."""
    authenticated = Signal(str, str, str, str)

    def __init__(self, parent=None):
        """Initialize the gateway window with last active company login."""
        super().__init__(parent)
        self.selected_company_path = ''
        self.selected_db_path = ''
        self.username = ''
        self.user_role = ''
        self.user_permissions = ''
        self.selected_login_date = QDate.currentDate()
        self.selected_company_data = None
        self.company_selection_dialog = None
        self.on_authenticated = None
        self._authentication_in_progress = False
        self._logo_box_armed = False
        self._secret_chord_step = 0
        self._session_secret_company = False
        self._regular_login_company_data = None
        self.db = self._create_gateway_database()
        self.selected_db_path = self.db.db_path
        self.setObjectName('companyGateway')
        if parent is not None:
            self.setWindowFlags(Qt.WindowType.Widget)
        self._build_ui()
        self._install_secret_unlock_handlers()
        self._apply_gateway_theme()
        self._connect_company_dropdown_if_present()
        self._load_last_active_company()
        self.update_user_dropdown()
        if parent is None:
            self.setWindowTitle(APP_NAME)
            self._init_ui_memory(restore_geometry=True, save_geometry=True)
        else:
            self._init_ui_memory(restore_geometry=False, save_geometry=False)

    def showEvent(self, event):
        """Refresh gateway colors whenever the login screen is shown again."""
        super().showEvent(event)
        self._apply_gateway_theme()
        if self.window() is not self:
            return
        try:
            clamp_window_to_available_screen(self)
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def _gateway_theme_name(self) -> str:
        return ThemeManager.get_theme_preference(ThemeManager.resolve_master_db_path())

    def _gateway_colors(self) -> dict[str, str]:
        return ThemeManager.get_colors(self._gateway_theme_name())

    def _apply_gateway_theme(self) -> None:
        """Apply saved theme styling to the gateway login screen."""
        colors = self._gateway_colors()
        gateway_bg = colors["app_bg"]
        card_bg = colors["card_bg"]
        card_border = colors["border"]
        menu_bg = colors["panel_bg"]
        title_color = colors["input_text"]
        company_color = colors["accent_label"]
        hint_color = colors["muted_text"]
        input_bg = colors["input_bg"]
        input_text = colors["input_text"]
        input_border = colors["border"]
        input_focus = colors["focus_border"]
        menu_bg_popup = colors["card_bg"]
        std_btn_bg = colors["panel_bg"]
        std_btn_text = colors["input_text"]
        std_btn_border = colors["border"]
        std_btn_hover = colors.get("surface_alt", colors["app_bg"])
        success_hover = "#2E7D32" if self._gateway_theme_name() == "light" else "#15803d"
        danger_hover = "#C62828" if self._gateway_theme_name() == "light" else "#b91c1c"
        self.setStyleSheet(
            f"QDialog#companyGateway {{ background-color: {gateway_bg}; color: {input_text}; }}\n"
            f"QDialog#companyGateway QLabel {{ color: {title_color}; font-size: 16px; font-weight: bold; background: transparent; border: none; }}\n"
            f"QDialog#companyGateway QPushButton {{ background-color: {std_btn_bg}; color: {std_btn_text}; border: 1px solid {std_btn_border}; border-radius: 6px; padding: 10px; font-weight: bold; }}\n"
            f"QDialog#companyGateway QPushButton:hover {{ background-color: {std_btn_hover}; }}\n"
            f"QDialog#companyGateway QLineEdit#passwordInput, QDialog#companyGateway QComboBox#usernameCombo {{ background-color: {input_bg}; color: {input_text}; border: 1px solid {input_border}; border-radius: 8px; padding: 9px; font-size: 14px; font-weight: bold; }}\n"
            f"QDialog#companyGateway QLineEdit#passwordInput:focus, QDialog#companyGateway QComboBox#usernameCombo:focus {{ border: 1px solid {input_focus}; }}\n"
            f"QDialog#companyGateway QComboBox#usernameCombo QAbstractItemView {{ background-color: {menu_bg_popup}; color: {input_text}; selection-background-color: {colors['focus_border']}; }}\n"
            f"QDialog#companyGateway QToolButton#fileMenuButton {{ background-color: {colors['button_primary']}; color: #ffffff; border: none; border-radius: 8px; padding: 9px 18px; text-align: left; font-size: 15px; font-weight: bold; }}\n"
            f"QDialog#companyGateway QToolButton#fileMenuButton:hover {{ background-color: {colors['focus_border']}; }}\n"
            f"QDialog#companyGateway QToolButton#fileMenuButton::menu-indicator {{ image: none; width: 0px; }}\n"
            f"QDialog#companyGateway QPushButton#loginButton {{ background-color: {colors['button_success']}; color: #ffffff; border: none; border-radius: 8px; padding: 10px; font-weight: bold; }}\n"
            f"QDialog#companyGateway QPushButton#loginButton:hover {{ background-color: {success_hover}; }}\n"
            f"QDialog#companyGateway QPushButton#exitButton {{ background-color: {colors['button_danger']}; color: #ffffff; border: none; border-radius: 22px; padding: 10px; font-size: 16px; font-weight: bold; }}\n"
            f"QDialog#companyGateway QPushButton#exitButton:hover {{ background-color: {danger_hover}; }}\n"
            f"QMenu {{ background-color: {menu_bg_popup}; color: {input_text}; border: 1px solid {card_border}; }}\n"
            f"QMenu::item {{ padding: 8px 28px; }}\n"
            f"QMenu::item:selected {{ background-color: {colors['focus_border']}; color: #ffffff; }}"
        )
        if hasattr(self, 'menu_row'):
            self.menu_row.setStyleSheet(f'QFrame {{ background-color: {menu_bg}; border-bottom: 1px solid {card_border}; border-radius: 0px; }}')
        if hasattr(self, 'login_card'):
            self.login_card.setStyleSheet(f'QFrame#loginCard {{ background-color: {card_bg}; border: 1px solid {card_border}; border-radius: 14px; }}')
        if hasattr(self, 'logo_box'):
            refresh_brand_logo_box(
                self.logo_box,
                self.brand_logo_label,
                420,
                190,
                sidebar_variant=True,
            )
        if hasattr(self, 'secret_file_button'):
            self.secret_file_button.setStyleSheet(theme.shortcut_toolbar_3d_icon_button_style())
        if hasattr(self, 'brand_logo_label'):
            self.brand_logo_label.setStyleSheet('background: transparent; border: none;')
        if hasattr(self, 'company_label'):
            self.company_label.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {company_color}; background: transparent; border: none;')
        if hasattr(self, 'company_hint_label'):
            self.company_hint_label.setStyleSheet(f'font-size: 13px; font-weight: normal; color: {hint_color}; background: transparent; border: none;')
        if hasattr(self, 'login_date_input'):
            self.login_date_input.setStyleSheet(theme.sales_compact_input_style())
            self._style_date_calendar(self.login_date_input)

    def _build_ui(self):
        """Build the gateway menu and last-active-company login form."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        menu_row = QFrame()
        self.menu_row = menu_row
        menu_layout = QHBoxLayout(menu_row)
        menu_layout.setContentsMargins(10, 10, 10, 10)
        menu_layout.setSpacing(0)
        file_menu = QMenu(self)
        open_recent_action = file_menu.addAction('📂 Open Companies')
        open_recent_action.triggered.connect(self.open_existing_company_list)
        create_company_action = file_menu.addAction('➕ Create New Company')
        create_company_action.triggered.connect(self.open_create_company)
        self.file_menu_button = QToolButton(self)
        self.file_menu_button.setObjectName('fileMenuButton')
        self.file_menu_button.setText('File')
        self.file_menu_button.setMenu(file_menu)
        self.file_menu_button.setPopupMode(QToolButton.InstantPopup)
        self.file_menu_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.file_menu_button.setIcon(QIcon(os.path.join('assets', 'icons', 'file.svg')))
        self.file_menu_button.setMinimumHeight(38)
        menu_layout.addWidget(self.file_menu_button, alignment=Qt.AlignLeft)
        menu_layout.addStretch()
        main_layout.addWidget(menu_row)
        main_layout.addStretch(1)
        login_card = QFrame()
        self.login_card = login_card
        login_card.setObjectName('loginCard')
        login_card.setFixedWidth(430)
        card_layout = QVBoxLayout(login_card)
        card_layout.setContentsMargins(32, 28, 32, 28)
        card_layout.setSpacing(14)
        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(0, 0, 0, 0)
        logo_row.setSpacing(8)
        logo_row.addStretch()
        self.logo_box, self.brand_logo_label = create_brand_logo_box(
            420,
            190,
            label_object_name='gatewayBrandLogo',
            sidebar_variant=True,
        )
        logo_row.addWidget(self.logo_box, alignment=Qt.AlignCenter)
        self.secret_file_button = QToolButton(self)
        self.secret_file_button.setObjectName('shortcutIconButton')
        self.secret_file_button.setToolTip('')
        self.secret_file_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.secret_file_button.setFixedSize(42, 38)
        self.secret_file_button.setIconSize(QSize(28, 28))
        self.secret_file_button.setStyleSheet(theme.shortcut_toolbar_3d_icon_button_style())
        self.secret_file_button.hide()
        self.secret_file_button.clicked.connect(self.open_secret_company_menu)
        logo_row.addWidget(self.secret_file_button, alignment=Qt.AlignBottom)
        logo_row.addStretch()
        card_layout.addLayout(logo_row)
        self.company_label = QLabel('No active company selected')
        self.company_label.setAlignment(Qt.AlignCenter)
        self.company_label.setWordWrap(True)
        card_layout.addWidget(self.company_label)
        self.company_hint_label = QLabel('Use File > Open Companies to select one.')
        self.company_hint_label.setAlignment(Qt.AlignCenter)
        self.company_hint_label.setWordWrap(True)
        card_layout.addWidget(self.company_hint_label)
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_layout.setSpacing(12)
        self.username_label = QLabel('Username')
        self.username_combo = UsernameComboBox()
        self.username_combo.setObjectName('usernameCombo')
        self.username_combo.setMinimumHeight(38)
        self.username_combo.setPlaceholderText('Select username')
        form_layout.addRow(self.username_label, self.username_combo)
        self.password_label = QLabel('Password')
        self.password_input = QLineEdit()
        self.password_input.setObjectName('passwordInput')
        self.password_input.setMinimumHeight(38)
        self.password_input.setPlaceholderText('Password')
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self.authenticate_current_company)
        form_layout.addRow(self.password_label, self.password_input)
        card_layout.addLayout(form_layout)
        self.date_label = QLabel('Date')
        self.login_date_input = QDateEdit()
        configure_qdate_edit(self.login_date_input)
        self.login_date_input.setObjectName('loginDateButton')
        self.login_date_input.setCalendarPopup(True)
        self.login_date_input.setDate(QDate.currentDate())
        self.login_date_input.setStyleSheet(theme.sales_compact_input_style())
        self.login_date_input.setFixedWidth(260)
        self.login_date_input.setMinimumHeight(38)
        self._style_date_calendar(self.login_date_input)
        form_layout.addRow(self.date_label, self.login_date_input)
        self.login_button = QPushButton('Login')
        self.login_button.setObjectName('loginButton')
        self.login_button.setMinimumHeight(42)
        self.login_button.setDefault(False)
        self.login_button.setAutoDefault(False)
        self.login_button.clicked.connect(self.authenticate_current_company)
        card_layout.addWidget(self.login_button)
        self.exit_button = QPushButton('⏻ Exit')
        self.exit_button.setObjectName('exitButton')
        self.exit_button.setMinimumHeight(44)
        self.exit_button.setDefault(False)
        self.exit_button.setAutoDefault(False)
        self.exit_button.clicked.connect(self._handle_exit_clicked)
        card_layout.addWidget(self.exit_button)
        self.loading_label = QLabel('Loading Application...')
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet(theme.loading_gateway_label_style())
        self.loading_label.hide()
        card_layout.addWidget(self.loading_label)
        self.loading_runner = LoadingRunnerWidget(width=132, height=132)
        self.loading_runner.hide()
        card_layout.addWidget(self.loading_runner, alignment=Qt.AlignCenter)
        self._handoff_pump_timer = QTimer(self)
        self._handoff_pump_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._handoff_pump_timer.setInterval(16)
        self._handoff_pump_timer.timeout.connect(pump_ui_events)
        main_layout.addWidget(login_card, alignment=Qt.AlignCenter)
        main_layout.addStretch(2)

    def _install_secret_unlock_handlers(self) -> None:
        """Arm the hidden company launcher when the logo box is clicked."""
        if hasattr(self, 'logo_box'):
            self.logo_box.installEventFilter(self)
        if hasattr(self, 'brand_logo_label'):
            self.brand_logo_label.installEventFilter(self)
        if not getattr(self, '_app_secret_filter_installed', False):
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
                self._app_secret_filter_installed = True

    def _gateway_login_screen_active(self) -> bool:
        """Return True when this gateway is the visible login screen."""
        try:
            if not self.isVisible():
                return False
        except RuntimeError:
            return False
        host = self.window()
        if host is self:
            return True
        stacked = getattr(host, 'stacked_widget', None)
        if stacked is not None:
            try:
                return stacked.currentWidget() is self
            except RuntimeError:
                return False
        return False

    def eventFilter(self, watched, event):
        """Track logo clicks and capture the secret chord after logout."""
        logo_box = getattr(self, 'logo_box', None)
        brand_logo = getattr(self, 'brand_logo_label', None)
        if watched in (logo_box, brand_logo):
            if event.type() == QEvent.Type.MouseButtonDblClick:
                if self._is_secret_file_icon_visible():
                    self._close_secret_file_launcher()
                    return True
            if event.type() == QEvent.Type.MouseButtonPress:
                self._arm_secret_unlock()

        if self._gateway_login_screen_active() and getattr(self, '_logo_box_armed', False):
            if event.type() == QEvent.Type.ShortcutOverride:
                if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and event.key() in (
                    Qt.Key.Key_B,
                    Qt.Key.Key_Z,
                ):
                    event.accept()
                    return True
            if event.type() == QEvent.Type.KeyPress and self._handle_secret_unlock_key(event):
                return True

        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        """Handle the hidden Ctrl+B, Z unlock chord after a logo-box click."""
        if self._gateway_login_screen_active() and self._handle_secret_unlock_key(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def _arm_secret_unlock(self) -> None:
        """Begin listening for the secret unlock key chord."""
        self._logo_box_armed = True
        self._secret_chord_step = 0
        arm_timer = getattr(self, '_secret_arm_timer', None)
        if arm_timer is None:
            arm_timer = QTimer(self)
            arm_timer.setSingleShot(True)
            arm_timer.timeout.connect(self._disarm_secret_unlock)
            self._secret_arm_timer = arm_timer
        arm_timer.stop()
        arm_timer.start(8000)

    def _disarm_secret_unlock(self) -> None:
        """Expire the secret unlock chord window."""
        self._logo_box_armed = False
        self._secret_chord_step = 0

    def _handle_secret_unlock_key(self, event) -> bool:
        """Return True when the Ctrl+B, Z chord reveals the secret file icon."""
        if not self._logo_box_armed:
            return False
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            return False
        if event.key() == Qt.Key.Key_B:
            self._secret_chord_step = 1
            return True
        if event.key() == Qt.Key.Key_Z and self._secret_chord_step == 1:
            self._reveal_secret_file_icon()
            self._disarm_secret_unlock()
            return True
        return False

    def _reveal_secret_file_icon(self) -> None:
        """Show the hidden file icon beside the login logo."""
        button = getattr(self, 'secret_file_button', None)
        if button is None:
            return
        pixmap = pixmap_for_menu_icon(
            'assets/icons/file.svg',
            QSize(28, 28),
            device_pixel_ratio=button.devicePixelRatioF(),
        )
        if pixmap is not None:
            button.setIcon(QIcon(pixmap))
        button.show()

    def _hide_secret_file_icon(self) -> None:
        """Hide the secret launcher icon from the login page."""
        button = getattr(self, 'secret_file_button', None)
        if button is not None:
            button.hide()

    def _is_secret_file_icon_visible(self) -> bool:
        """Return True when the secret file launcher icon is shown."""
        button = getattr(self, 'secret_file_button', None)
        if button is None:
            return False
        try:
            return button.isVisible()
        except RuntimeError:
            return False

    def _close_secret_file_launcher(self) -> None:
        """Hide the secret file icon and clear any pending unlock chord."""
        self._hide_secret_file_icon()
        self._disarm_secret_unlock()
        arm_timer = getattr(self, '_secret_arm_timer', None)
        if arm_timer is not None:
            arm_timer.stop()

    def open_secret_company_menu(self) -> None:
        """Open the compact secret create/open company popup."""
        menu_dialog = SecretCompanyMenuDialog(self)
        menu_dialog.create_button.clicked.connect(
            lambda: self._launch_secret_company_action(menu_dialog, 'create')
        )
        menu_dialog.open_button.clicked.connect(
            lambda: self._launch_secret_company_action(menu_dialog, 'open')
        )
        menu_dialog.exec()

    def _launch_secret_company_action(self, menu_dialog: QDialog, action: str) -> None:
        """Close the secret menu and run one secret company workflow."""
        menu_dialog.accept()
        if action == 'create':
            self.open_secret_create_company()
        elif action == 'open':
            self.open_secret_company_list()

    def open_secret_create_company(self) -> None:
        """Create a secret company without affecting the normal login panel."""
        try:
            if company_limit_reached(self.db.db_path, COMPANY_VISIBILITY_SECRET):
                self._show_login_dialog_message(
                    QMessageBox.Icon.Warning,
                    'Limit Reached',
                    company_limit_message(COMPANY_VISIBILITY_SECRET),
                )
                return
            setup_dialog = QDialog(self)
            setup_dialog.setWindowTitle('Create Secret Company')
            setup_dialog.resize(900, 700)
            setup_dialog.setStyleSheet(theme.gateway_modal_dialog_style())
            setup_layout = QVBoxLayout(setup_dialog)
            setup_layout.setContentsMargins(0, 0, 0, 0)
            setup_layout.setSpacing(0)
            setup_view = CompanySetupView(self.db, company_visibility=COMPANY_VISIBILITY_SECRET)
            setup_view.company_saved.connect(lambda _company_data: setup_dialog.accept())
            setup_layout.addWidget(setup_view)
            setup_dialog.exec()
        except Exception as error:
            self._show_login_dialog_message(
                QMessageBox.Icon.Critical,
                'Company Setup Error',
                f'Unable to open secret company setup:\n{error}',
            )

    def open_secret_company_list(self) -> None:
        """Open only companies created from the secret company page."""
        try:
            selection_dialog = QDialog(self)
            selection_dialog.setWindowTitle('Open Secret Companies')
            selection_dialog.resize(900, 700)
            selection_dialog.setStyleSheet(theme.gateway_modal_dialog_style())
            selection_layout = QVBoxLayout(selection_dialog)
            selection_layout.setContentsMargins(0, 0, 0, 0)
            selection_layout.setSpacing(0)
            open_company_widget = OpenCompanyPageWidget(
                self.db,
                auto_close_on_selection=False,
                show_success_message=False,
                activate_on_selection=False,
                show_row_actions=True,
                row_actions=('view',),
                company_visibility=COMPANY_VISIBILITY_SECRET,
                title_text='Secret Companies',
                subtitle_text='Select a secret company to use for login',
            )
            open_company_widget.company_selected.connect(
                lambda company_data: self._handle_company_selected(
                    company_data,
                    via_secret_file=True,
                )
            )
            selection_layout.addWidget(open_company_widget)
            self.company_selection_dialog = selection_dialog
            selection_dialog.exec()
            self.company_selection_dialog = None
        except Exception as error:
            self._show_login_dialog_message(
                QMessageBox.Icon.Critical,
                'Open Company Error',
                f'Unable to open secret company list:\n{error}',
            )

    def _style_date_calendar(self, date_edit):
        """Apply the sales/purchase dark calendar popup style."""
        calendar = date_edit.calendarWidget()
        if calendar is None:
            return
        calendar.setStyleSheet(theme.entry_calendar_style())
        prev_btn = calendar.findChild(QToolButton, 'qt_calendar_prevmonth')
        if prev_btn:
            prev_btn.setArrowType(Qt.NoArrow)
            prev_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            prev_btn.setText('<')
            prev_btn.setFixedSize(24, 24)
        next_btn = calendar.findChild(QToolButton, 'qt_calendar_nextmonth')
        if next_btn:
            next_btn.setArrowType(Qt.NoArrow)
            next_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            next_btn.setText('>')
            next_btn.setFixedSize(24, 24)
        theme.apply_calendar_day_formats(calendar)

    def _load_last_active_company(self):
        """Load and display the last active normal company for the login panel."""
        try:
            self._regular_login_company_data = self.db.get_active_company(
                visibility=COMPANY_VISIBILITY_NORMAL,
            )
            self.selected_company_data = self._regular_login_company_data
            self._session_secret_company = False
        except Exception as error:
            self._show_login_dialog_message(QMessageBox.Icon.Critical, 'Company Load Error', f'Unable to load last active company:\n{error}')
            self._regular_login_company_data = None
            self.selected_company_data = None
            self._session_secret_company = False
        self._refresh_company_display()

    def _refresh_company_display(self):
        """Refresh the login panel company labels."""
        if not self.selected_company_data:
            self.company_label.setText('No active company selected')
            self.company_hint_label.setText('Use File > Open Companies to select a company.')
            self.login_button.setEnabled(False)
            return
        business_name = self.selected_company_data.get('business_name', '')
        gstin = self.selected_company_data.get('gstin') or 'No GSTIN'
        state = self.selected_company_data.get('state') or 'State not set'
        self.company_label.setText(business_name)
        self.company_hint_label.setText(f'{gstin} | {state}')
        self.login_button.setEnabled(True)

    def _load_usernames(self):
        """Populate usernames from the selected application database."""
        self.update_user_dropdown()

    def update_user_dropdown(self):
        """Populate usernames strictly from the currently selected company DB."""
        company_db_path = self._selected_company_db_path()
        company_id = self._selected_company_id()
        fetched_rows = []
        try:
            ensure_company_users_table(company_db_path, company_id)
            with closing(sqlite3.connect(company_db_path, timeout=30.0)) as connection:
                connection.execute('PRAGMA busy_timeout = 5000;')
                connection.execute('PRAGMA journal_mode = DELETE;')
                connection.execute('PRAGMA synchronous = NORMAL;')
                with closing(connection.cursor()) as cursor:
                    cursor.execute('\n                        SELECT username\n                        FROM users\n                        WHERE company_id = ?\n                        ORDER BY username\n                        ', (company_id,))
                    fetched_rows = cursor.fetchall()
        except (sqlite3.Error, OSError, ValueError) as error:
            print(f'[COMPANY GATEWAY] Could not load company users: {error}')
            fetched_rows = [('admin',)]
        self.username_combo.clear()
        usernames = [row[0] for row in fetched_rows] or ['admin']
        self.username_combo.addItems(usernames)

    def _connect_company_dropdown_if_present(self):
        """Connect a company combobox to username refresh when one exists."""
        for attribute_name in ('company_combo', 'company_dropdown', 'company_selector'):
            company_combo = getattr(self, attribute_name, None)
            if company_combo is None or not hasattr(company_combo, 'currentIndexChanged'):
                continue
            company_combo.currentIndexChanged.connect(self.update_user_dropdown)
            return

    def authenticate_current_company(self):
        """Authenticate the entered user for the selected company."""
        if self._authentication_in_progress:
            return
        self._authentication_in_progress = True
        authenticated = False
        try:
            if not self.selected_company_data:
                self._show_login_dialog_message(QMessageBox.Icon.Warning, 'No Company Selected', 'Please select a company from File > Open Companies.')
                return
            entered_username = self.username_combo.currentText().strip()
            entered_password = self.password_input.text()
            if not entered_username or not entered_password:
                self._show_login_failed_warning()
                return
            try:
                user_record = self._fetch_user_record(entered_username)
            except sqlite3.Error as error:
                self._show_login_dialog_message(QMessageBox.Icon.Critical, 'Database Error', f'Unable to validate credentials:\n{error}')
                return
            stored_hash = user_record[0] if user_record else ''
            stored_plain_password = user_record[1] if user_record else ''
            password_matches = bool(stored_hash) and hash_password(entered_password) == stored_hash or (bool(stored_plain_password) and entered_password == stored_plain_password)
            if not user_record or not password_matches:
                self._show_login_failed_warning()
                return
            self.username = entered_username
            self.user_role = self._normalize_role(user_record[2])
            self.user_permissions = user_record[3] or ''
            self.selected_login_date = self.login_date_input.date()
            self.selected_db_path = self._selected_company_db_path()
            self.selected_company_path = self.selected_db_path
            self.selected_company_data = self._activate_selected_company(self.selected_company_data)
            authenticated = True
            file_path = self.selected_db_path
            company_name = ''
            if self.selected_company_data:
                company_name = self.selected_company_data.get('business_name', '')
            self.authenticated.emit(file_path, company_name, self.username, self.user_role)
        finally:
            if not authenticated:
                self._authentication_in_progress = False

    def _handle_exit_clicked(self) -> None:
        """Close the app from standalone gateway or the host window when embedded."""
        if self._is_embedded_page():
            host = self.window()
            if host is not None:
                host.close()
            return
        self.window().close()

    def _is_embedded_page(self) -> bool:
        """Return True when this gateway is hosted inside MainWindow, not standalone."""
        return self.window() is not self

    def _hide_gateway_login_form(self) -> None:
        """Hide login controls before the startup curtain is shown."""
        if hasattr(self, 'menu_row'):
            self.menu_row.hide()
        if hasattr(self, 'login_card'):
            self.login_card.hide()
        self.company_label.hide()
        self.company_hint_label.hide()
        self.username_label.hide()
        self.username_combo.hide()
        self.password_label.hide()
        self.password_input.hide()
        self.date_label.hide()
        self.login_date_input.hide()
        self.login_button.hide()
        self.exit_button.hide()
        self.file_menu_button.setEnabled(False)
        self.file_menu_button.hide()
        if hasattr(self, 'logo_box'):
            self.logo_box.hide()
        self.brand_logo_label.hide()

    def _show_gateway_handoff_loading(self) -> None:
        """Swap the login form for the in-window loading animation."""
        self._hide_gateway_login_form()
        self.brand_logo_label.show()
        if hasattr(self, 'logo_box'):
            self.logo_box.show()
        self.loading_label.show()
        self.loading_runner.show()
        self.loading_runner.start()
        self._handoff_pump_timer.start()

    def freeze_for_startup_handoff(self) -> None:
        """Block login edits while the fullscreen curtain is already visible."""
        self._authentication_in_progress = True
        if self._is_embedded_page():
            self._show_gateway_handoff_loading()
            return
        self.login_button.setEnabled(False)
        self.exit_button.setEnabled(False)
        self.username_combo.setEnabled(False)
        self.password_input.setEnabled(False)
        self.file_menu_button.setEnabled(False)

    def thaw_after_startup_handoff(self) -> None:
        """Clear the handoff freeze state."""
        self._authentication_in_progress = False

    def prepare_handoff_overlay(self):
        """Show a clean loading state while the main window initializes."""
        self.freeze_for_startup_handoff()
        if self._is_embedded_page():
            host = self.window()
            if host is not None:
                host.update()
        self.update()
        pump_ui_events()

    def _show_login_failed_warning(self):
        """Show a high-contrast login failure warning dialog."""
        self._show_login_dialog_message(QMessageBox.Icon.Warning, 'Login Failed', 'Invalid credentials')

    def _show_login_dialog_message(self, icon, title, text):
        """Show a gateway-owned message box using the active application theme."""
        show_message(self, icon, title, text)

    def reset_login_state(self) -> None:
        """Prepare the gateway for a fresh login after logout."""
        self.username = ''
        self.user_role = ''
        self.user_permissions = ''
        self.password_input.clear()
        self._session_secret_company = False
        self._disarm_secret_unlock()
        self._hide_secret_file_icon()
        self._install_secret_unlock_handlers()
        self.restore_after_failed_handoff()
        self._load_last_active_company()
        self.update_user_dropdown()

    def restore_after_failed_handoff(self):
        """Restore the login controls when the main workspace cannot open."""
        self.thaw_after_startup_handoff()
        if not self._is_embedded_page():
            self.show()
        self.brand_logo_label.show()
        if hasattr(self, 'logo_box'):
            self.logo_box.show()
        if hasattr(self, 'menu_row'):
            self.menu_row.show()
        if hasattr(self, 'login_card'):
            self.login_card.show()
        self.company_label.show()
        self.company_hint_label.show()
        self.username_label.show()
        self.username_combo.show()
        self.password_label.show()
        self.password_input.show()
        self.date_label.show()
        self.login_date_input.show()
        self.login_button.show()
        self.exit_button.show()
        self.file_menu_button.show()
        self.loading_label.hide()
        self._handoff_pump_timer.stop()
        self.loading_runner.stop()
        self.loading_runner.hide()
        self.file_menu_button.setEnabled(True)
        self.username_combo.setEnabled(True)
        self.password_input.setEnabled(True)
        self.exit_button.setEnabled(True)
        self.login_button.setText('Login')
        self.login_button.setEnabled(True)
        self._refresh_company_display()
        self.password_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def close_handoff_overlay(self):
        """Compatibility hook for the old handoff cover flow."""
        return

    def _fetch_user_record(self, username):
        """Return password hash, role, and permissions for the given user."""
        company_db_path = self._selected_company_db_path()
        company_id = self._selected_company_id()
        ensure_company_users_table(company_db_path, company_id)
        with closing(sqlite3.connect(company_db_path, timeout=30.0)) as connection:
            connection.execute('PRAGMA busy_timeout = 5000;')
            connection.execute('PRAGMA journal_mode = DELETE;')
            connection.execute('PRAGMA synchronous = NORMAL;')
            with closing(connection.cursor()) as cursor:
                cursor.execute('\n                    SELECT password_hash, password, role, permissions\n                    FROM users\n                    WHERE company_id = ?\n                      AND username = ?\n                    ', (company_id, username))
                return cursor.fetchone()

    def _selected_company_id(self):
        """Return the selected company registry ID for user isolation."""
        company_data = self.selected_company_data or {}
        try:
            return int(company_data.get('id'))
        except (TypeError, ValueError):
            return None

    def _selected_company_db_path(self):
        """Return the SQLite path that owns users for the selected company."""
        company_data = self.selected_company_data or {}
        for key in ('db_path', 'database_path', 'company_db_path', 'file_path', 'path'):
            value = company_data.get(key)
            if value:
                return value
        return self.selected_db_path or self.db.db_path

    def _normalize_role(self, role):
        """Return the canonical role string expected by MainWindow."""
        role_text = str(role or '').strip()
        if role_text.lower() == 'admin':
            return 'Admin'
        if role_text.lower() == 'user':
            return 'User'
        return role_text or 'User'

    def open_existing_company_list(self):
        """Open the same created-companies list used by the main app menu."""
        try:
            selection_dialog = QDialog(self)
            selection_dialog.setWindowTitle('Open Companies')
            selection_dialog.resize(900, 700)
            selection_dialog.setStyleSheet(theme.gateway_modal_dialog_style())
            selection_layout = QVBoxLayout(selection_dialog)
            selection_layout.setContentsMargins(0, 0, 0, 0)
            selection_layout.setSpacing(0)
            open_company_widget = OpenCompanyPageWidget(self.db, auto_close_on_selection=False, show_success_message=False, activate_on_selection=False, show_row_actions=False, company_visibility=COMPANY_VISIBILITY_NORMAL, title_text='Open Companies', subtitle_text='Select a company to use for login')
            open_company_widget.company_selected.connect(
                lambda company_data: self._handle_company_selected(
                    company_data,
                    via_secret_file=False,
                )
            )
            selection_layout.addWidget(open_company_widget)
            self.company_selection_dialog = selection_dialog
            selection_dialog.exec()
            self.company_selection_dialog = None
        except Exception as error:
            self._show_login_dialog_message(QMessageBox.Icon.Critical, 'Open Company Error', f'Unable to open company list:\n{error}')

    def browse_and_open_company(self):
        """Compatibility wrapper that opens the created-companies list."""
        self.open_existing_company_list()

    def _handle_company_selected(
        self,
        company_data,
        *,
        via_secret_file: bool = False,
    ):
        """Apply the selected company to the login panel."""
        if not company_data:
            if self.company_selection_dialog:
                self.company_selection_dialog.reject()
            return
        self.selected_company_data = company_data
        self._session_secret_company = bool(
            via_secret_file or is_secret_company(company_data)
        )
        self._refresh_company_display()
        self.update_user_dropdown()
        self.password_input.clear()
        self.password_input.setFocus(Qt.FocusReason.OtherFocusReason)
        if self.company_selection_dialog:
            self.company_selection_dialog.accept()

    def _activate_selected_company(self, company_data):
        """Mark the selected company active after successful authentication."""
        if not company_data:
            return None
        active_company = company_data
        try:
            if self._session_secret_company:
                # Secret-file logins are transient and must not change recent history.
                active_company_manager.set_active_company(active_company)
                return active_company
            if self.db and company_data.get('id'):
                self.db.set_active_company(company_data['id'])
                refreshed = self.db.get_active_company()
                if refreshed:
                    active_company = refreshed
            active_company_manager.set_active_company(active_company)
            self._regular_login_company_data = active_company
        except Exception as error:
            self._show_login_dialog_message(QMessageBox.Icon.Warning, 'Warning', f'Company login succeeded, but the active company flag could not be updated:\n{error}')
        return active_company

    def _create_gateway_database(self):
        """Create the database used to show the existing company list."""
        database = Database()
        if not database.initialize_database():
            raise RuntimeError(f'Schema initialization failed for database: {database.db_path}')
        return database

    def open_create_company(self):
        """Open the comprehensive company setup UI as a modal dialog."""
        try:
            if company_limit_reached(self.db.db_path, COMPANY_VISIBILITY_NORMAL):
                self._show_login_dialog_message(
                    QMessageBox.Icon.Warning,
                    'Limit Reached',
                    company_limit_message(COMPANY_VISIBILITY_NORMAL),
                )
                return
            setup_dialog = QDialog(self)
            setup_dialog.setWindowTitle('Create New Company')
            setup_dialog.resize(900, 700)
            setup_dialog.setStyleSheet(theme.gateway_modal_dialog_style())
            setup_layout = QVBoxLayout(setup_dialog)
            setup_layout.setContentsMargins(0, 0, 0, 0)
            setup_layout.setSpacing(0)
            setup_view = CompanySetupView(self.db, company_visibility=COMPANY_VISIBILITY_NORMAL)
            setup_view.company_saved.connect(lambda _company_data: setup_dialog.accept())
            setup_layout.addWidget(setup_view)
            setup_dialog.exec()
            self._load_last_active_company()
            self._load_usernames()
        except Exception as error:
            self._show_login_dialog_message(QMessageBox.Icon.Critical, 'Company Setup Error', f'Unable to open company setup:\n{error}')
