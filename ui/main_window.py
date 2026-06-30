"""
Main window implementation for the Accounting Desktop Application.
Uses QMainWindow with sidebar, topbar, and QStackedWidget for modular UI management.

PERFORMANCE NOTE: Heavy module imports are deferred using lazy imports inside
the respective show methods to improve startup time.
"""

import os
import sqlite3
import time
import traceback
from contextlib import closing
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QFrame,
    QMessageBox, QPushButton, QLabel, QAbstractButton, QApplication,
)
from PySide6.QtCore import Qt, QSettings, Signal, QTimer, QEvent

from config import APP_NAME, WINDOW_SIZE, active_company_manager
from db import Database, get_default_database_path, BASE_DIR
from utils.backup_manager import execute_backup
from utils.db_maintenance import DatabaseMaintenance
from components.shortcut_toolbar import ShortcutToolbar
from components.sidebar import Sidebar
from components.topbar import TopbarWidget
from ui.backup_dialog import BackupRestoreDialog
from ui.year_end_dialog import YearEndDialog
from ui.transfer_dialog import TransferDataDialog
from ui.keyboard_shortcuts import GLOBAL_ACTION_SHORTCUTS, MODULE_ROUTE_SHORTCUTS
from .dashboard import DashboardWidget
from .company_page import CompanyPageWidget
from .new_company_page import NewCompanyPageWidget
from .open_company_page import OpenCompanyPageWidget
from .open_company_page import OpenCompanyPageWidget
from .standalone_window import StandaloneModuleWindow, get_standalone_page_widget
from ui.module_minimize_strip import ModuleMinimizeStrip
from ui.company_gateway import CompanyGateway
from ui.salesman_book import SalesmanBook
from ui.theme_manager import get_theme_manager, sync_theme
from utils.theme_manager import ThemeManager as GlobalThemeManager, global_theme_manager
from ui.qt_pump import pump_ui_events

# Heavy imports (Products, Sales Entry, etc.) are loaded lazily inside show methods
# to improve startup performance. See: show_products(), show_sales(), etc.


class MainWindow(QMainWindow):
    """Main application window with sidebar, topbar, and stacked widgets."""

    NAVIGATION_PERMISSION_MAP = {
        "Sales": {"sales"},
        "Sales Return": {"sales"},
        "Van Entry": {"sales"},
        "Van Return Entry": {"sales"},
        "Purchase": {"purchases"},
        "Purchase Return": {"purchases"},
        "Purchase Order": {"purchases"},
        "Quotation": {"quotations"},
        "Purchase Order Book": {"purchases", "reports"},
        "Cash Payment": {"payments"},
        "Bank Payment": {"payments"},
        "Cash Receipt": {"receipts"},
        "Bank Receipt": {"receipts"},
        "Post Dated Cheque": {"payments", "receipts"},
        "Credit/Debit Note": {"sales", "purchases"},
        "Journal Entry": {"payments", "receipts"},
        "Day Book": {"reports"},
        "Cash Book": {"reports"},
        "Ledger": {"reports"},
        "Ledger Statement": {"reports"},
        "Bill History": {"reports"},
        "Cash Tender History": {"reports"},
        "Sales Book": {"reports"},
        "Quotation Book": {"reports"},
        "Sales Return Book": {"reports"},
        "Purchase Book": {"reports"},
        "Purchase Return Book": {"reports"},
        "PDC Book": {"reports"},
        "Journal Book": {"reports"},
        "Daily Stock Register": {"reports"},
        "Price List": {"reports"},
        "Stock Report": {"reports"},
        "Sales Wise Profit": {"reports"},
        "Monthly Analysis": {"reports"},
        "GST Sales Report": {"reports"},
        "GST Purchase Report": {"reports"},
        "GSTR-1": {"reports"},
        "Daily Collection Report": {"reports"},
        "Best Sellers (Top Products)": {"reports"},
        "Salesman Record Book": {"reports"},
        "Trial Balance": {"reports"},
        "Profit and Loss Account": {"reports"},
        "Balance Sheet": {"reports"},
        "Stock Value": {"reports"},
        "Opening Balance": {"settings"},
        "Opening Stock Entry": {"settings"},
        "Stock Adjustment": {"settings"},
        "General Settings": {"settings"},
        "Tax Settings": {"settings"},
        "Invoice Settings": {"settings"},
        "User Settings": {"settings"},
        "Manage Users": {"settings"},
        "User Management": {"settings"},
        "Users": {"settings"},
        "Barcode Settings": {"settings"},
        "Print Settings": {"settings"},
        "Barcode": {"settings"},
        "Stock Checker": {"settings"},
        "System Diagnostics": {"settings"},
        "Audit Logs": {"settings"},
        "Backup and Restore Data": {"settings"},
        "Inter-Company Transfer": {"settings"},
        "Close Financial Year (Year-End)": {"settings"},
        "Compact and Repair Data": {"settings"},
    }

    READ_ONLY_TITLE_SUFFIX = " [READ ONLY - PREVIOUS FINANCIAL YEAR]"

    READ_ONLY_ALLOWED_ROUTES = frozenset({
        "View Company",
        "Close Company",
        "Day Book",
        "Cash Book",
        "Ledger",
        "Ledger Statement",
        "Bill History",
        "Cash Tender History",
        "Sales Book",
        "Sales Return Book",
        "Purchase Book",
        "Purchase Return Book",
        "Purchase Order Book",
        "Quotation Book",
        "Journal Book",
        "PDC Book",
        "Daily Stock Register",
        "Price List",
        "Stock Report",
        "Sales Wise Profit",
        "Monthly Analysis",
        "GST Sales Report",
        "GST Purchase Report",
        "GSTR-1",
        "Daily Collection Report",
        "Best Sellers (Top Products)",
        "Salesman Record Book",
        "Trial Balance",
        "Profit and Loss Account",
        "Balance Sheet",
        "Stock Value",
        "Stock Checker",
        "System Diagnostics",
        "Audit Logs",
        "Print Settings",
        "Barcode",
    })

    READ_ONLY_DISABLED_BUTTON_KEYWORDS = (
        "save",
        "create",
        "edit",
        "delete",
        "new transaction",
        "add ",
        "update",
        "remove",
    )
    
    def __init__(self, skip_gateway: bool = False, *, use_external_handoff: bool = False):
        """Initialize the morphing hub with the gateway as the first page."""
        super().__init__()
        global_theme_manager.theme_changed.connect(self._on_global_theme_changed)

        self.db_path = None
        self.db = None
        self.company_name = "company"
        self.current_user = None
        self.user_role = None
        self.user_permissions = ""
        self.current_user_record = None
        self.auto_backup_enabled = False
        self.skip_backup_on_close = False
        self._open_module_windows = {}
        self._module_window_state_snapshot = {}
        self._reapplying_module_window_states = False
        self._module_restore_timer_active = False
        self._unified_minimize_in_progress = False
        self._unified_minimize_scheduled = False
        self._unified_minimize_initiator = None
        self._unified_restore_in_progress = False
        self._hub_restore_window_state = Qt.WindowState.WindowNoState
        self._dock_minimized_modules: dict[int, QWidget] = {}
        self._dock_minimized_order: list[int] = []
        self._dock_minimized_hwnds: set[int] = set()
        self.dark_overlay = None
        self._page_load_times = {}
        self.dashboard_container = None
        self.dashboard_loaded = False
        self.is_read_only = False
        self._read_only_disabled_widgets = []
        self._base_window_title = APP_NAME
        self._handoff_on_ready = None
        self._handoff_data = None
        self._handoff_init_start = None
        self._handoff_defer_page_switch = False
        self._use_external_handoff = use_external_handoff

        self.settings = QSettings("FaizanPro", "AccountingApp")
        if not use_external_handoff:
            self._restore_main_window_ui_state()

        self.setWindowTitle(APP_NAME)
        self.resize(900, 700)
        self.setMinimumSize(900, 700)

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.gateway = None
        self._logout_gateway_authenticated_connected = False
        if not skip_gateway:
            self.gateway = CompanyGateway(self.stacked_widget)
            self.gateway.authenticated.connect(self.morph_to_dashboard)
            self._logout_gateway_authenticated_connected = True
            self.stacked_widget.addWidget(self.gateway)
            self.stacked_widget.setCurrentIndex(0)

        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_application_state_changed)

    def morph_to_dashboard(self, db_path, company_name, username, role):
        """Build the dashboard page and expand the hub after login."""
        if self.dashboard_loaded:
            self._resume_dashboard_session(db_path, company_name, username, role)
            return

        init_start = time.time()
        self.db_path = db_path
        self.db = self._create_database_from_path(db_path)
        self.company_name = company_name or "company"
        self.current_user = username
        self.user_role = self._normalize_role(role)
        self.user_permissions = self._normalize_user_permissions("", self.user_role)
        self.current_user_record = None

        self.setMinimumSize(1200, 800)
        self._ensure_settings_table()
        self.auto_backup_enabled = self._load_auto_backup_preference()
        self._setup_utility_actions()
        QTimer.singleShot(0, self._setup_report_actions)
        self._clear_application_menu_bar()
        self.theme_manager = get_theme_manager(self._master_registry_db_path())

        self.dashboard_container = QWidget()
        self.setup_ui(self.dashboard_container)
        self.stacked_widget.addWidget(self.dashboard_container)
        self.connect_signals()
        self.setup_global_dialog_styling()
        self.apply_theme()
        if self.user_role:
            self.apply_user_permissions(self.user_role, self.user_permissions)
        self._show_all_navigation_controls()
        self._load_active_company_from_db()
        self._refresh_backup_company_context()
        self.show_dashboard()
        self.stacked_widget.setCurrentIndex(1)
        self.dashboard_loaded = True
        self._sync_read_only_mode()
        self._restore_main_window_ui_state(prefer_saved_state=True)
        from ui.app_window_coordinator import ensure_app_window_coordinator

        ensure_app_window_coordinator(self)

        init_end = time.time()
        print(f"[PERF] MainWindow dashboard morph: {init_end - init_start:.3f} sec")

    def begin_dashboard_handoff(
        self,
        db_path,
        company_name,
        username,
        role,
        on_ready,
        on_failed=None,
        *,
        defer_page_switch: bool = False,
    ):
        """Build the dashboard in stages so the loading animation can keep running."""
        if self.dashboard_loaded:
            self._resume_dashboard_session(db_path, company_name, username, role)
            if on_ready:
                QTimer.singleShot(0, on_ready)
            return

        self._handoff_on_ready = on_ready
        self._handoff_on_failed = on_failed
        self._handoff_data = (db_path, company_name, username, role)
        self._handoff_init_start = time.time()
        self._handoff_defer_page_switch = defer_page_switch
        QTimer.singleShot(0, self._handoff_step_prepare)

    def prepare_dashboard_handoff_reveal(self) -> None:
        """Apply dashboard page and geometry without showing the hub window."""
        from PySide6.QtGui import QGuiApplication

        dashboard_container = getattr(self, "dashboard_container", None)
        if dashboard_container is not None:
            dashboard_index = self.stacked_widget.indexOf(dashboard_container)
            if dashboard_index >= 0:
                self.stacked_widget.setCurrentIndex(dashboard_index)
        self.setMinimumSize(1200, 800)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.availableGeometry())
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def complete_dashboard_handoff(self) -> None:
        """Reveal the dashboard page inside the same MainWindow after startup handoff."""
        self.prepare_dashboard_handoff_reveal()
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            from utils.a4_preview_prewarm import schedule_a4_preview_engine_prewarm

            schedule_a4_preview_engine_prewarm()
        except Exception:
            pass

    def _handoff_report_error(self, error: BaseException) -> None:
        """Forward staged handoff failures to the startup controller."""
        on_failed = getattr(self, "_handoff_on_failed", None)
        self._handoff_on_ready = None
        self._handoff_on_failed = None
        self._handoff_data = None
        self._handoff_init_start = None
        if on_failed:
            on_failed(error)
        else:
            raise error

    def _handoff_step_prepare(self):
        try:
            db_path, company_name, username, role = self._handoff_data
            self.db_path = db_path
            self.db = self._create_database_from_path(db_path)
            self.company_name = company_name or "company"
            self.current_user = username
            self.user_role = self._normalize_role(role)
            self.user_permissions = self._normalize_user_permissions("", self.user_role)
            self.current_user_record = None

            self._ensure_settings_table()
            self.auto_backup_enabled = self._load_auto_backup_preference()
            self._setup_utility_actions()
            self._clear_application_menu_bar()
            self.theme_manager = get_theme_manager(self._master_registry_db_path())
            pump_ui_events()
            QTimer.singleShot(0, self._handoff_step_build_ui)
        except BaseException as error:
            self._handoff_report_error(error)

    def _handoff_step_build_ui(self):
        try:
            self.dashboard_container = QWidget()
            self.setup_ui(self.dashboard_container)
            self.stacked_widget.addWidget(self.dashboard_container)
            pump_ui_events()
            QTimer.singleShot(0, self._handoff_step_finalize)
        except BaseException as error:
            self._handoff_report_error(error)

    def _handoff_step_finalize(self):
        try:
            self.connect_signals()
            self.setup_global_dialog_styling()
            self.apply_theme()
            if self.user_role:
                self.apply_user_permissions(self.user_role, self.user_permissions)
            self._show_all_navigation_controls()
            self._load_active_company_from_db()
            self._refresh_backup_company_context()
            self.show_dashboard()
            if not getattr(self, "_handoff_defer_page_switch", False):
                self.stacked_widget.setCurrentIndex(max(0, self.stacked_widget.count() - 1))
            self._handoff_defer_page_switch = False
            self.dashboard_loaded = True
            self._sync_read_only_mode()
            QTimer.singleShot(0, self._setup_report_actions)
            from ui.app_window_coordinator import ensure_app_window_coordinator

            ensure_app_window_coordinator(self)

            init_end = time.time()
            start = self._handoff_init_start or init_end
            print(f"[PERF] MainWindow dashboard handoff: {init_end - start:.3f} sec")

            on_ready = self._handoff_on_ready
            self._handoff_on_ready = None
            self._handoff_on_failed = None
            self._handoff_data = None
            self._handoff_init_start = None
            if on_ready:
                on_ready()
        except BaseException as error:
            self._handoff_report_error(error)

    def _create_database_from_path(self, db_path):
        """Create and initialize a SQLite database manager for a selected company."""
        if not db_path:
            return None

        database = Database(db_type="sqlite", db_path=db_path)
        if not database.initialize_database():
            raise RuntimeError(
                f"Schema initialization failed for database: {database.db_path}"
            )
        return database

    def _ensure_settings_table(self):
        """Ensure persistent application settings exist in the company database."""
        if not self.db_path:
            return

        with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
            connection.execute("PRAGMA busy_timeout = 5000;")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT
                )
                """
            )
            connection.commit()

    def _load_auto_backup_preference(self):
        """Load the persisted auto-backup setting."""
        if not self.db_path:
            return False

        with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
            connection.execute("PRAGMA busy_timeout = 5000;")
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT setting_value
                FROM app_settings
                WHERE setting_key = ?
                """,
                ("auto_backup_enabled",),
            )
            row = cursor.fetchone()

        value = row[0] if row else "false"
        return value == "true"

    def _clear_application_menu_bar(self) -> None:
        """Remove top-level application menus from the native menu bar."""
        menu_bar = self.menuBar()
        for action in list(menu_bar.actions()):
            menu_bar.removeAction(action)
        menu_bar.setVisible(False)

    def _setup_utility_actions(self):
        """Create utility actions without attaching them to the top menu bar."""
        if not getattr(self, "backup_restore_action", None):
            backup_restore_action = QAction("Backup and Restore Data", self)
            backup_restore_action.setShortcut(QKeySequence())
            backup_restore_action.triggered.connect(self.open_backup_dialog)
            self.backup_restore_action = backup_restore_action

        if not getattr(self, "year_end_action", None):
            year_end_action = QAction("Close Financial Year (Year-End)", self)
            year_end_action.setShortcut(QKeySequence())
            year_end_action.triggered.connect(self.open_year_end_dialog)
            self.year_end_action = year_end_action

        if not getattr(self, "inter_company_transfer_action", None):
            inter_company_transfer_action = QAction("Inter-Company Transfer", self)
            inter_company_transfer_action.setShortcut(QKeySequence())
            inter_company_transfer_action.triggered.connect(self.open_transfer_dialog)
            self.inter_company_transfer_action = inter_company_transfer_action

        if not getattr(self, "compact_repair_action", None):
            compact_repair_action = QAction("Compact and Repair Data", self)
            compact_repair_action.setShortcut(QKeySequence())
            compact_repair_action.triggered.connect(self.run_compact_and_repair)
            self.compact_repair_action = compact_repair_action
            self._set_compact_repair_menu_icon()

        if not getattr(self, "global_settings_action", None):
            global_settings_action = QAction("Global Settings", self)
            global_settings_action.setShortcut(QKeySequence())
            global_settings_action.triggered.connect(self.open_global_settings_dialog)
            self.global_settings_action = global_settings_action

    def _current_icon_color(self, theme_name: str | None = None) -> str:
        """Return the qtawesome tint color for the active theme."""
        if theme_name is None:
            theme_name = (
                self.theme_manager.get_current_theme()
                if getattr(self, "theme_manager", None)
                else "dark"
            )
        return global_theme_manager.get_icon_color(theme_name)

    def _set_compact_repair_menu_icon(self, theme_name: str | None = None) -> None:
        """Apply the Utilities menu icon for Compact & Repair Database."""
        compact_repair_action = getattr(self, "compact_repair_action", None)
        if compact_repair_action is None:
            return
        try:
            import qtawesome as qta

            icon_color = self._current_icon_color(theme_name)
            compact_repair_action.setIcon(
                qta.icon("fa5s.tools", color=icon_color)
            )
        except ImportError:
            pass
        except Exception as exc:
            print(f"[WARN] Could not set compact/repair menu icon: {exc}")

    def _refresh_qtawesome_menu_icons(self, theme_name: str | None = None) -> None:
        """Refresh qtawesome icons so they match the active theme."""
        try:
            import qtawesome as qta

            icon_color = self._current_icon_color(theme_name)
            if getattr(self, "best_sellers_report_action", None):
                self.best_sellers_report_action.setIcon(
                    qta.icon("fa5s.trophy", color=icon_color)
                )
            if getattr(self, "salesman_record_book_action", None):
                self.salesman_record_book_action.setIcon(
                    qta.icon("fa5s.user-tie", color=icon_color)
                )
            self._set_compact_repair_menu_icon(theme_name)
        except ImportError:
            pass
        except Exception as exc:
            print(f"[WARN] Could not refresh qtawesome menu icons: {exc}")

    def _on_global_theme_changed(self, theme_name: str) -> None:
        """Apply a saved theme across the live dashboard without restart."""
        if not getattr(self, "dashboard_loaded", False):
            return

        try:
            sync_theme(theme_name, self._master_registry_db_path())
            self.apply_theme()
        except Exception as exc:
            print(f"[WARN] Live theme update failed: {exc}")

    def refresh_icons(self, theme_name: str) -> None:
        """Refresh all long-lived qtawesome icons when the global theme changes."""
        icon_color = global_theme_manager.get_icon_color(theme_name)
        self._refresh_qtawesome_menu_icons(theme_name)
        self._last_icon_color = icon_color

    def _setup_report_actions(self):
        """Create report actions without attaching them to the top menu bar."""
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is None:
            return

        if not getattr(self, "best_sellers_report_action", None):
            best_sellers_action = QAction("Best Sellers (Top Products)", self)
            best_sellers_action.triggered.connect(self.open_best_sellers_report)
            self.best_sellers_report_action = best_sellers_action

        if not getattr(self, "salesman_record_book_action", None):
            salesman_action = QAction("Salesman Record Book", self)
            salesman_action.triggered.connect(self.open_salesman_book)
            self.salesman_record_book_action = salesman_action

        self._refresh_qtawesome_menu_icons()

    def _refresh_backup_company_context(self):
        """Refresh the company name used for backup file names."""
        active_company = active_company_manager.get_active_company()
        if not active_company and self.db is not None:
            try:
                active_company = self.db.get_active_company()
            except Exception:
                active_company = None

        if active_company:
            self.company_name = active_company.get("business_name") or "company"

    def _load_read_only_flag(self) -> bool:
        """Return True when the active company database is locked for year-end."""
        if not self.db_path:
            return False

        try:
            with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
                connection.execute("PRAGMA busy_timeout = 5000;")
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'app_settings'
                    LIMIT 1
                    """
                )
                if not cursor.fetchone():
                    return False

                cursor.execute(
                    """
                    SELECT setting_value
                    FROM app_settings
                    WHERE setting_key = ?
                    """,
                    ("is_read_only",),
                )
                row = cursor.fetchone()
        except Exception as error:
            print(f"[MAIN WINDOW] Could not load read-only flag: {error}")
            return False

        return bool(row and str(row[0]).strip().lower() == "true")

    def _create_read_only_banner(self) -> QLabel:
        """Create the persistent closed-year warning shown below the topbar."""
        from ui import theme

        colors = theme._theme_colors()
        banner = QLabel(
            "This financial year is closed. Data is locked for viewing only."
        )
        banner.setWordWrap(True)
        banner.setAlignment(Qt.AlignCenter)
        banner.setVisible(False)
        banner.setStyleSheet(
            f"""
            QLabel {{
                background-color: {colors['accent_label']};
                color: {colors['app_bg'] if theme._is_light_theme() else colors['input_text']};
                font-size: 14px;
                font-weight: bold;
                padding: 10px 16px;
                border-bottom: 1px solid {colors['border']};
            }}
            """
        )
        return banner

    def _sync_read_only_mode(self) -> None:
        """Apply or clear read-only restrictions based on app_settings."""
        self.is_read_only = self._load_read_only_flag()
        self._update_window_title_for_read_only()
        self._update_read_only_banner()

        if self.is_read_only:
            if self.dashboard_loaded:
                self._close_tracked_module_windows()
            self._apply_read_only_navigation_state()
            self._disable_data_entry_buttons()
            self._apply_read_only_menu_state()
            return

        self._restore_data_entry_buttons()
        self._restore_navigation_after_read_only()
        self._apply_read_only_menu_state()

    def _update_window_title_for_read_only(self) -> None:
        """Append the read-only suffix to the main window title when locked."""
        if self.is_read_only:
            self.setWindowTitle(f"{self._base_window_title}{self.READ_ONLY_TITLE_SUFFIX}")
            return
        self.setWindowTitle(self._base_window_title)

    def _update_read_only_banner(self) -> None:
        """Show or hide the closed-year warning banner."""
        banner = getattr(self, "read_only_banner", None)
        if banner is not None:
            banner.setVisible(bool(self.is_read_only))

    def _is_read_only_route_blocked(self, page_name: str) -> bool:
        """Return True when a sidebar route must be blocked in read-only mode."""
        if not self.is_read_only:
            return False
        if not page_name or page_name.startswith("--"):
            return False
        return page_name not in self.READ_ONLY_ALLOWED_ROUTES

    def _apply_read_only_navigation_state(self) -> None:
        """Disable sidebar routes that perform data entry while read-only."""
        if not self.is_read_only:
            return

        sidebar = getattr(self, "sidebar", None)
        if not sidebar:
            return

        for route_name in getattr(sidebar, "navigation_buttons", {}):
            if route_name in self.READ_ONLY_ALLOWED_ROUTES or route_name.startswith("--"):
                continue
            for widget in self._navigation_widgets_for_route(route_name):
                if widget is not None:
                    widget.setEnabled(False)

        if hasattr(self, "manage_users_button"):
            self.manage_users_button.setEnabled(False)

    def _restore_navigation_after_read_only(self) -> None:
        """Re-enable sidebar navigation after leaving read-only mode."""
        sidebar = getattr(self, "sidebar", None)
        if not sidebar:
            return

        if hasattr(sidebar, "show_all_routes"):
            sidebar.show_all_routes()
            return

        for route_name in getattr(sidebar, "navigation_buttons", {}):
            for widget in self._navigation_widgets_for_route(route_name):
                if widget is not None:
                    widget.setVisible(True)
                    widget.setEnabled(True)

        for section_widget in getattr(sidebar, "menu_sections", {}).values():
            section_widget.setVisible(True)
            if hasattr(section_widget, "header_btn"):
                section_widget.header_btn.setVisible(True)
                section_widget.header_btn.setEnabled(True)

        if self._is_admin_user():
            self._ensure_admin_controls()
            if hasattr(self, "manage_users_button"):
                self.manage_users_button.setEnabled(True)

    def _disable_data_entry_buttons(self) -> None:
        """Disable save/create/edit/delete style buttons across the workspace."""
        self._restore_data_entry_buttons()

        logout_button = getattr(self, "logout_btn", None)
        for button in self.findChildren(QPushButton):
            if button is logout_button:
                continue

            label = button.text().strip().lower()
            if not any(keyword in label for keyword in self.READ_ONLY_DISABLED_BUTTON_KEYWORDS):
                continue

            if button.isEnabled():
                self._read_only_disabled_widgets.append(button)
                button.setEnabled(False)

        for button in self.findChildren(QAbstractButton):
            if isinstance(button, QPushButton) or button is logout_button:
                continue

            label = button.text().strip().lower()
            if not any(keyword in label for keyword in self.READ_ONLY_DISABLED_BUTTON_KEYWORDS):
                continue

            if button.isEnabled():
                self._read_only_disabled_widgets.append(button)
                button.setEnabled(False)

    def _restore_data_entry_buttons(self) -> None:
        """Re-enable buttons that were disabled for read-only mode."""
        for widget in self._read_only_disabled_widgets:
            try:
                widget.setEnabled(True)
            except RuntimeError:
                pass
        self._read_only_disabled_widgets.clear()

    def _apply_read_only_menu_state(self) -> None:
        """Disable write-capable menu actions while the company is read-only."""
        backup_action = getattr(self, "backup_restore_action", None)
        if backup_action is not None:
            backup_action.setEnabled(not self.is_read_only)

        year_end_action = getattr(self, "year_end_action", None)
        if year_end_action is not None:
            year_end_action.setEnabled(not self.is_read_only)

        compact_repair_action = getattr(self, "compact_repair_action", None)
        if compact_repair_action is not None:
            compact_repair_action.setEnabled(not self.is_read_only)

    def _show_read_only_warning(self) -> None:
        """Warn the user that the closed financial year is view-only."""
        self._show_permission_denied_warning(
            "This financial year is closed and locked for viewing only.",
            title="Read Only Company",
        )

    def resizeEvent(self, event):
        """Keep overlays aligned with the current main window size."""
        super().resizeEvent(event)
        dark_overlay = getattr(self, "dark_overlay", None)
        if dark_overlay is not None and dark_overlay.isVisible():
            dark_overlay.setGeometry(0, 0, self.width(), self.height())

    def _restore_main_window_ui_state(self, prefer_saved_state: bool = False) -> None:
        """Restore main-window geometry, dock/toolbar state, and optional splitter."""
        try:
            geometry = self.settings.value("mainwindow/geometry")
            window_state = self.settings.value("mainwindow/windowState")
            if geometry:
                self.restoreGeometry(geometry)
            if window_state:
                self.restoreState(window_state)
            elif prefer_saved_state:
                self.showMaximized()

            if not self.isMaximized() and not self.isFullScreen():
                from ui.ui_memory import schedule_clamp_window_to_available_screen
                schedule_clamp_window_to_available_screen(self)

            splitter = getattr(self, "main_splitter", None)
            if splitter is not None:
                splitter_state = self.settings.value("mainwindow/splitterState")
                if splitter_state:
                    splitter.restoreState(splitter_state)
        except Exception as error:
            print(f"[UI MEMORY] Main window restore failed: {error}")

    def _save_main_window_ui_state(self) -> None:
        """Persist main-window geometry, dock/toolbar state, and optional splitter."""
        try:
            if not self.isMaximized() and not self.isFullScreen():
                from ui.ui_memory import clamp_window_to_available_screen
                clamp_window_to_available_screen(self)
            self.settings.setValue("mainwindow/geometry", self.saveGeometry())
            self.settings.setValue("mainwindow/windowState", self.saveState())
            splitter = getattr(self, "main_splitter", None)
            if splitter is not None:
                self.settings.setValue("mainwindow/splitterState", splitter.saveState())
        except Exception as error:
            print(f"[UI MEMORY] Main window save failed: {error}")

    @property
    def window_coordinator(self):
        """Return the application-wide minimize and dock registry coordinator."""
        return getattr(self, "_app_window_coordinator", None)

    def _coordinator_for_module(self, module_window=None):
        """Return the application window coordinator, creating it when needed."""
        from ui.app_window_coordinator import ensure_app_window_coordinator

        ensure_app_window_coordinator(self)
        return self.window_coordinator

    def _evict_module_from_coordinator(self, module_window) -> None:
        """Remove a dock-minimized module from coordinator minimize tracking."""
        coordinator = self._coordinator_for_module(module_window)
        if coordinator is not None:
            coordinator.evict_tracked_window(module_window)

    def _return_module_to_coordinator(self, module_window) -> None:
        """Add a restored module back to coordinator minimize tracking."""
        coordinator = self._coordinator_for_module(module_window)
        if coordinator is not None:
            coordinator.return_tracked_window(module_window)

    def _module_native_hwnd(self, module_window) -> int:
        """Return the Win32 handle for a module shell, or zero when unavailable."""
        if module_window is None:
            return 0
        try:
            return int(module_window.winId())
        except RuntimeError:
            return 0

    def _remember_docked_hwnd(self, module_window) -> None:
        """Remember a dock-minimized module by native handle for stable matching."""
        hwnd = self._module_native_hwnd(module_window)
        if hwnd:
            self._dock_minimized_hwnds.add(hwnd)

    def _forget_docked_hwnd(self, module_window) -> None:
        """Drop the native handle entry when a module leaves the internal strip."""
        hwnd = self._module_native_hwnd(module_window)
        if hwnd:
            self._dock_minimized_hwnds.discard(hwnd)

    def _canonical_module_window(self, module_window):
        """Return the absolute top-level window for coordinator tracking."""
        if not self._is_live_module_window(module_window):
            return None
        try:
            top_level = module_window.window()
            if top_level is not None and not self._is_live_module_window(top_level):
                return None
            return top_level if top_level is not None else module_window
        except RuntimeError:
            return None

    @staticmethod
    def _is_live_module_window(module_window) -> bool:
        """Return True when a module shell wrapper is still valid."""
        if module_window is None:
            return False
        try:
            from shiboken6 import Shiboken

            return bool(Shiboken.isValid(module_window))
        except Exception:
            return True

    def is_module_dock_minimized(self, module_window) -> bool:
        """Return True when a module page is dock-minimized on the hub strip."""
        if module_window is None:
            return False
        canonical = self._canonical_module_window(module_window)
        if canonical is None:
            return False
        canonical_id = id(canonical)
        if canonical_id in self._dock_minimized_modules:
            return True
        hwnd = self._module_native_hwnd(canonical)
        if hwnd and hwnd in self._dock_minimized_hwnds:
            return True
        target_hwnd = hwnd
        for docked_window in self._dock_minimized_modules.values():
            if docked_window is canonical or id(docked_window) == canonical_id:
                return True
            if target_hwnd:
                try:
                    if int(docked_window.winId()) == target_hwnd:
                        return True
                except RuntimeError:
                    continue
        return False

    def dock_minimize_module_window(
        self,
        module_window,
        *,
        from_restore: bool = False,
        from_app_minimize: bool = False,
    ) -> None:
        """Dock-minimize one module page to the bottom strip instead of the OS taskbar."""
        if module_window is None:
            return
        module_window = self._canonical_module_window(module_window)
        if module_window is None:
            return
        try:
            already_docked = self.is_module_dock_minimized(module_window)
            top_window = module_window.window() or module_window
            top_window._internal_dock_minimize_in_progress = True
            if (
                not from_restore
                and not from_app_minimize
                and not already_docked
            ):
                saved_state = module_window.windowState() & ~Qt.WindowState.WindowMinimized
                if saved_state == Qt.WindowState.WindowNoState:
                    saved_state = Qt.WindowState.WindowActive
                module_window._last_visible_window_state = saved_state

            window_id = id(top_window)
            self._dock_minimized_modules[window_id] = top_window
            if window_id not in self._dock_minimized_order:
                self._dock_minimized_order.append(window_id)
            self._remember_docked_hwnd(top_window)
            self._refresh_module_minimize_strip()

            top_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            top_window.setWindowState(
                top_window.windowState() & ~Qt.WindowState.WindowMinimized
            )
            self._evict_module_from_coordinator(module_window)
            from ui.ui_memory import unbind_module_window_from_hub

            unbind_module_window_from_hub(top_window)
            top_window.hide()

            coordinator = getattr(self, "_app_window_coordinator", None)
            if coordinator is not None:
                coordinator._native_hide_window(top_window, docked=True)

            self._evict_module_from_coordinator(module_window)
            self._refresh_module_minimize_strip()
            self.activateWindow()
            if from_app_minimize and not already_docked:
                title = (top_window.windowTitle() or "Module").strip()
                print(f"[WINDOW] '{title}' placed on internal taskbar during app minimize.")
            elif not from_app_minimize and not already_docked:
                title = (top_window.windowTitle() or "Module").strip()
                print(f"[WINDOW] '{title}' docked to internal taskbar.")
        except RuntimeError:
            self._undock_module_window(module_window)
        finally:
            try:
                top_window._internal_dock_minimize_in_progress = False
            except RuntimeError:
                pass

    def dock_restore_module_window(self, module_window) -> None:
        """Restore one dock-minimized module page from the bottom strip."""
        if module_window is None:
            return
        try:
            module_window = self._canonical_module_window(module_window)
            top_window = module_window.window() or module_window
            window_id = id(top_window)
            self._dock_minimized_modules.pop(window_id, None)
            if window_id in self._dock_minimized_order:
                self._dock_minimized_order.remove(window_id)
            self._forget_docked_hwnd(top_window)
            top_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)

            self._return_module_to_coordinator(module_window)

            saved_state = getattr(
                module_window,
                "_last_visible_window_state",
                Qt.WindowState.WindowNoState,
            )
            top_window.showNormal()
            top_window.show()
            if saved_state & Qt.WindowState.WindowFullScreen:
                top_window.showFullScreen()
            elif saved_state & Qt.WindowState.WindowMaximized:
                top_window.showMaximized()
            else:
                top_window.showNormal()
            top_window.raise_()
            top_window.activateWindow()
            from ui.ui_memory import schedule_bind_module_window_to_hub

            schedule_bind_module_window_to_hub(top_window, self)
            self._refresh_module_minimize_strip()
        except RuntimeError:
            self._undock_module_window(module_window)

    def _undock_module_window(self, module_window) -> None:
        """Remove one module page from the dock-minimize strip."""
        if not self._is_live_module_window(module_window):
            self._refresh_module_minimize_strip()
            return
        try:
            module_window = self._canonical_module_window(module_window)
            if module_window is None:
                self._refresh_module_minimize_strip()
                return
            top_window = module_window.window() or module_window
            window_id = id(top_window)
            self._dock_minimized_modules.pop(window_id, None)
            if window_id in self._dock_minimized_order:
                self._dock_minimized_order.remove(window_id)
            self._forget_docked_hwnd(top_window)
            try:
                top_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
            except RuntimeError:
                pass
            self._evict_module_from_coordinator(module_window)
        except RuntimeError:
            pass
        self._refresh_module_minimize_strip()

    def _refresh_module_minimize_strip(self) -> None:
        """Rebuild the bottom strip from the current dock-minimized module list."""
        strip = getattr(self, "module_minimize_strip", None)
        if strip is None:
            return
        entries: list[tuple[QWidget, str]] = []
        stale_ids: list[int] = []
        for window_id in self._dock_minimized_order:
            module_window = self._dock_minimized_modules.get(window_id)
            if module_window is None:
                stale_ids.append(window_id)
                continue
            try:
                entries.append((module_window, module_window.windowTitle()))
            except RuntimeError:
                stale_ids.append(window_id)
        for window_id in stale_ids:
            self._dock_minimized_modules.pop(window_id, None)
            if window_id in self._dock_minimized_order:
                self._dock_minimized_order.remove(window_id)
        strip.sync_entries(entries)
        strip.setVisible(bool(entries))

    def _register_module_window(self, module_window) -> None:
        """Keep a hub reference on tracked standalone module windows."""
        if module_window is not None:
            from ui.hub_dockable_window import (
                detach_hub_module_from_qt_parent,
                ensure_hub_dockable_window,
            )
            from ui.ui_memory import apply_module_window_chrome

            module_window._hub_window = self
            detach_hub_module_from_qt_parent(module_window, self)
            apply_module_window_chrome(module_window, self)
            ensure_hub_dockable_window(module_window, self)
            page_widget = get_standalone_page_widget(module_window)
            if page_widget is not None:
                page_widget._hub_window = self
            coordinator = getattr(self, "_app_window_coordinator", None)
            if coordinator is not None:
                coordinator.register_module_window(module_window)

    def _maybe_return_to_dashboard(self) -> None:
        """Refresh the dashboard when no module pages remain open."""
        if self._open_module_windows:
            return
        if hasattr(self, "stack_widget") and hasattr(self, "dashboard_widget"):
            self.stack_widget.setCurrentWidget(self.dashboard_widget)
            if hasattr(self.dashboard_widget, "refresh_data"):
                self.dashboard_widget.refresh_data()

    def _present_non_modal_window(
        self,
        window_key: str,
        build_window,
        *,
        on_existing=None,
        width_ratio: float = 0.9,
        height_ratio: float = 0.9,
        fallback_size: tuple[int, int] = (1200, 760),
    ):
        """Create or raise a standalone module window."""
        existing = self._open_module_windows.get(window_key)
        if existing is not None:
            try:
                if on_existing is not None:
                    on_existing(existing)
                self._center_and_show_window(
                    existing,
                    width_ratio=width_ratio,
                    height_ratio=height_ratio,
                    fallback_size=fallback_size,
                )
                return existing
            except RuntimeError:
                self._open_module_windows.pop(window_key, None)

        window = build_window()
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        from ui.hub_dockable_window import detach_hub_module_from_qt_parent

        detach_hub_module_from_qt_parent(window, self)
        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._open_module_windows[window_key] = window
        self._center_and_show_window(
            window,
            width_ratio=width_ratio,
            height_ratio=height_ratio,
            fallback_size=fallback_size,
        )
        return window

    def _on_application_state_changed(self, state) -> None:
        """Track application visibility changes for unified minimize and restore."""
        coordinator = getattr(self, "_app_window_coordinator", None)
        if coordinator is not None:
            coordinator.handle_application_state_changed(state)
        if state == Qt.ApplicationState.ApplicationHidden:
            self._application_was_minimized = True
            return
        if (
            state == Qt.ApplicationState.ApplicationActive
            and getattr(self, "_application_was_minimized", False)
        ):
            self._application_was_minimized = False

    def _is_active_module_window(self, window) -> bool:
        """Return True when a tracked module window is still open on screen."""
        if window is None:
            return False
        try:
            from shiboken6 import Shiboken

            if not Shiboken.isValid(window):
                return False
        except Exception:
            pass
        try:
            if getattr(window, "_hidden_by_app_minimize", False):
                return True
            hidden_children = getattr(self, "_children_hidden_by_app_minimize", None) or []
            if window in hidden_children:
                return True
            if getattr(window, "_saved_hub_window_state", None) is not None:
                return True
            if self.is_module_dock_minimized(window):
                return True
            if window.isMinimized():
                return True
            return window.isVisible()
        except RuntimeError:
            return False

    def _prune_stale_module_windows(self) -> None:
        """Drop closed module windows that were hidden without being destroyed."""
        stale_keys: list[str] = []
        for window_key, window in self._open_module_windows.items():
            if not self._is_active_module_window(window):
                stale_keys.append(window_key)
        for window_key in stale_keys:
            self._open_module_windows.pop(window_key, None)

    def _get_tracked_module_window(self, window_key: str):
        """Return a live tracked module window or None after pruning stale entries."""
        window = self._open_module_windows.get(window_key)
        if window is None:
            return None
        if not self._is_active_module_window(window):
            self._open_module_windows.pop(window_key, None)
            return None
        return window

    def showMinimized(self) -> None:
        """Minimize the whole application from the hub title bar or taskbar."""
        if getattr(self, "_coordinator_minimize_in_progress", False):
            super().showMinimized()
            return
        coordinator = getattr(self, "_app_window_coordinator", None)
        if coordinator is not None:
            coordinator.minimize_application(source_widget=self)
            return
        super().showMinimized()

    def setWindowState(self, state: Qt.WindowState) -> None:
        """Redirect hub minimize requests to the application coordinator."""
        new_state = Qt.WindowState(state)
        if getattr(self, "_coordinator_minimize_in_progress", False):
            super().setWindowState(new_state)
            return
        going_minimized = bool(new_state & Qt.WindowState.WindowMinimized) and not bool(
            self.windowState() & Qt.WindowState.WindowMinimized
        )
        coordinator = getattr(self, "_app_window_coordinator", None)
        if going_minimized and coordinator is not None:
            coordinator.minimize_application(source_widget=self)
            return
        super().setWindowState(new_state)

    def changeEvent(self, event) -> None:
        """Delegate hub minimize and restore to the application window coordinator."""
        super().changeEvent(event)
        coordinator = getattr(self, "_app_window_coordinator", None)
        if coordinator is not None:
            coordinator.handle_hub_change_event(event)
            if event.type() == QEvent.Type.WindowStateChange:
                self._main_window_was_minimized = self.isMinimized()

    def closeEvent(self, event):
        """Run silent settings-driven auto-backup before closing."""
        if not getattr(self, "_shutdown_module_windows_confirmed", False):
            if not self._confirm_shutdown_open_module_windows():
                event.ignore()
                return
            self._shutdown_module_windows_confirmed = True
            self._close_tracked_module_windows(skip_unsaved_prompt=True)

        try:
            if self.auto_backup_enabled and not self.skip_backup_on_close:
                self._run_silent_auto_backup()
        except Exception as error:
            print(f"[BACKUP] Auto-backup failed: {error}")

        self._save_main_window_ui_state()
        event.accept()

    def _confirm_shutdown_open_module_windows(self) -> bool:
        """Prompt for unsaved entry edits before the main application window closes."""
        from ui.entry_voucher_mixin import confirm_standalone_entry_close

        for window in list(self._open_module_windows.values()):
            if window is None:
                continue
            try:
                if not confirm_standalone_entry_close(window, event=None):
                    return False
            except RuntimeError:
                continue
        return True

    def open_backup_dialog(self):
        """Open the backup and restore settings dialog."""
        if self.is_read_only:
            self._show_read_only_warning()
            return

        def build_window():
            return BackupRestoreDialog(self.db_path, self.company_name, self)

        try:
            self._present_non_modal_window(
                "backup_restore",
                build_window,
                fallback_size=(640, 480),
                width_ratio=0.55,
                height_ratio=0.72,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Backup and Restore Data",
                f"Could not open backup and restore settings:\n{exc}",
            )

    def run_compact_and_repair(self) -> None:
        """Compact and repair the active company SQLite database."""
        if self.is_read_only:
            self._show_read_only_warning()
            return
        if not self.db_path:
            QMessageBox.warning(
                self,
                "No Company Database",
                "Please open a company before compacting and repairing the database.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Compact & Repair Database",
            "This process will optimize the database and may take a few moments. "
            "Do you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            success, message = DatabaseMaintenance.compact_and_repair(self.db_path)
        finally:
            QApplication.restoreOverrideCursor()

        if success:
            QMessageBox.information(self, "Compact & Repair Database", message)
        else:
            QMessageBox.critical(self, "Compact & Repair Database", message)

    def _master_registry_db_path(self) -> str:
        """Return the absolute path to the master company registry database."""
        master_db_path = get_default_database_path()
        if not os.path.isabs(master_db_path):
            master_db_path = os.path.join(BASE_DIR, master_db_path)
        return os.path.abspath(master_db_path)

    def open_year_end_dialog(self):
        """Open the financial year-end processing dialog."""
        if self.is_read_only:
            self._show_read_only_warning()
            return
        if not self.db_path:
            QMessageBox.warning(
                self,
                "No Company Database",
                "Please open a company before running year-end processing.",
            )
            return

        master_db_path = self._master_registry_db_path()

        def build_window():
            return YearEndDialog(
                self.db_path,
                self.company_name,
                master_db_path,
                self,
            )

        try:
            self._present_non_modal_window(
                "year_end_processing",
                build_window,
                fallback_size=(700, 440),
                width_ratio=0.58,
                height_ratio=0.72,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Financial Year-End Processing",
                f"Could not open year-end processing:\n{exc}",
            )

    def open_transfer_dialog(self):
        """Open the inter-company data transfer dialog."""
        if self.is_read_only:
            self._show_read_only_warning()
            return

        master_db_path = self._master_registry_db_path()

        active_company = active_company_manager.get_active_company()
        active_company_id = active_company.get("id") if active_company else None

        def build_window():
            return TransferDataDialog(
                master_db_path,
                active_company_id,
                self,
            )

        try:
            self._present_non_modal_window(
                "inter_company_transfer",
                build_window,
                fallback_size=(920, 580),
                width_ratio=0.82,
                height_ratio=0.85,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Inter-Company Data Transfer",
                f"Could not open inter-company transfer:\n{exc}",
            )

    def _resolve_auto_backup_settings(self) -> tuple[bool, str]:
        """Read persisted auto-backup enabled flag and target directory."""
        if not self.db_path:
            return False, ""

        settings = {
            "auto_backup_enabled": "false",
            "backup_dir": "",
        }
        try:
            with closing(sqlite3.connect(self.db_path, timeout=30.0)) as connection:
                connection.execute("PRAGMA busy_timeout = 5000;")
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT setting_key, setting_value
                    FROM app_settings
                    WHERE setting_key IN (?, ?)
                    """,
                    ("auto_backup_enabled", "backup_dir"),
                )
                for setting_key, setting_value in cursor.fetchall():
                    settings[setting_key] = setting_value or ""
        except sqlite3.Error as error:
            print(f"[BACKUP] Could not load auto-backup settings: {error}")
            return False, ""

        auto_backup_enabled = (
            settings["auto_backup_enabled"].strip().lower() == "true"
        )
        backup_dir = settings["backup_dir"].strip()
        return auto_backup_enabled, backup_dir

    def _auto_backup_will_run(self) -> bool:
        """Return True when auto-backup is configured and ready to execute."""
        if not self.db_path or self.skip_backup_on_close:
            return False

        self.auto_backup_enabled = self._load_auto_backup_preference()
        if not self.auto_backup_enabled:
            return False

        auto_backup_enabled, backup_dir = self._resolve_auto_backup_settings()
        return auto_backup_enabled and os.path.isdir(backup_dir)

    def _run_silent_auto_backup(self, *, notify_on_success: bool = True) -> bool:
        """Create an auto-backup when enabled in app settings.

        Returns:
            bool: True when a backup file was created successfully.
        """
        if not self._auto_backup_will_run():
            return False

        _, backup_dir = self._resolve_auto_backup_settings()
        self._refresh_backup_company_context()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            success, result = execute_backup(
                self.db_path,
                backup_dir,
                self.company_name,
            )
        finally:
            QApplication.restoreOverrideCursor()

        if success:
            if notify_on_success:
                QMessageBox.information(
                    self,
                    "Auto-Backup Complete",
                    f"Auto-backup created successfully:\n{result}",
                )
            return True

        QMessageBox.warning(
            self,
            "Auto-Backup Failed",
            f"Could not create an automatic backup:\n{result}",
        )
        return False

    def setup_ui(self, central_widget=None):
        """Setup main UI layout with horizontal structure."""
        setup_start = time.time()

        if central_widget is None:
            central_widget = QWidget()
            self.setCentralWidget(central_widget)

        # Main horizontal layout: left sidebar, right main area
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left: Sidebar (lightweight, loaded immediately)
        sidebar_start = time.time()
        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)
        sidebar_end = time.time()
        print(f"[PERF] Sidebar setup: {sidebar_end - sidebar_start:.3f} sec")
        pump_ui_events()

        # Right: Main area with vertical layout
        self.main_area_widget = QWidget()
        self.main_area_widget.setObjectName("mainAreaWidget")
        main_area_layout = QVBoxLayout(self.main_area_widget)
        main_area_layout.setContentsMargins(0, 0, 0, 0)
        main_area_layout.setSpacing(0)

        # Topbar at top of main area (lightweight, loaded immediately)
        topbar_start = time.time()
        self.topbar = TopbarWidget(self.db)
        self._setup_logout_button()
        main_area_layout.addWidget(self.topbar)
        topbar_end = time.time()
        print(f"[PERF] Topbar setup: {topbar_end - topbar_start:.3f} sec")
        pump_ui_events()

        self.shortcut_toolbar = ShortcutToolbar()
        main_area_layout.addWidget(self.shortcut_toolbar)

        self.read_only_banner = self._create_read_only_banner()
        main_area_layout.addWidget(self.read_only_banner)

        self.admin_controls = self._create_admin_controls()
        main_area_layout.addWidget(self.admin_controls)
        if not self._is_admin_user() and hasattr(self, "manage_users_button"):
            self.manage_users_button.setVisible(False)
            self.manage_users_button.setEnabled(False)

        # Dashboard workspace always stays visible under floating module pages.
        self.stack_widget = QStackedWidget()
        colors = get_theme_manager(self._master_registry_db_path()).get_colors()
        self.stack_widget.setStyleSheet(f"""
            QStackedWidget {{
                background-color: {colors['app_bg']};
            }}
        """)
        main_area_layout.addWidget(self.stack_widget, 1)

        self.module_minimize_strip = ModuleMinimizeStrip(self.main_area_widget)
        self.module_minimize_strip.hide()
        self.module_minimize_strip.restore_requested.connect(self.dock_restore_module_window)
        main_area_layout.addWidget(self.module_minimize_strip)

        # Add main area to main layout
        main_layout.addWidget(self.main_area_widget, 1)

        # Setup workspace pages (lightweight pages only)
        self.setup_workspace_pages()
        pump_ui_events()

        setup_end = time.time()
        print(f"[PERF] setup_ui total: {setup_end - setup_start:.3f} sec")

    def _setup_logout_button(self) -> None:
        """Apply themed styling to the topbar logout control."""
        self.logout_btn = getattr(self.topbar, "logout_btn", None)
        if self.logout_btn is None:
            return
        self.logout_btn.setStyleSheet(self._logout_button_style())

    def _logout_button_style(self) -> str:
        """Return the distinct topbar stylesheet for the logout action."""
        try:
            tm = getattr(self, "theme_manager", None) or get_theme_manager()
            colors = tm.get_colors()
            is_light = tm.get_current_theme() == "light"
        except Exception:
            colors = GlobalThemeManager.get_colors("dark")
            is_light = False
        hover = "#C62828" if is_light else "#dc2626"
        pressed = "#B71C1C" if is_light else "#7f1d1d"
        return f"""
            QPushButton#logoutButton {{
                background-color: {colors['button_danger']};
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton#logoutButton:hover {{
                background-color: {hover};
            }}
            QPushButton#logoutButton:pressed {{
                background-color: {pressed};
            }}
        """

    def _is_admin_user(self) -> bool:
        """Return True when the authenticated user has the Admin role."""
        return self._normalize_role(self.user_role) == "Admin"

    def _normalize_role(self, role):
        """Return the canonical role value used by permission checks."""
        role_text = str(role or "").strip()
        if role_text.lower() == "admin":
            return "Admin"
        if role_text.lower() == "user":
            return "User"
        return role_text

    def _ensure_admin_controls(self):
        """Create and show Admin controls after login role assignment."""
        if not hasattr(self, "admin_controls"):
            self.admin_controls = self._create_admin_controls()
            dashboard_root = getattr(self, "dashboard_container", None)
            central_widget = dashboard_root or self.centralWidget()
            central_layout = central_widget.layout()
            main_area = central_layout.itemAt(1).widget() if central_layout else None
            main_area_layout = main_area.layout() if main_area else None
            if main_area_layout:
                main_area_layout.insertWidget(2, self.admin_controls)

        self.admin_controls.setVisible(True)
        self.admin_controls.setEnabled(True)
        if hasattr(self, "manage_users_button"):
            self.manage_users_button.setVisible(True)
            self.manage_users_button.setEnabled(True)

    def _hide_admin_controls(self):
        """Hide Admin-only controls for standard users."""
        if hasattr(self, "manage_users_button"):
            self.manage_users_button.setVisible(False)
            self.manage_users_button.setEnabled(False)

    def _clear_login_overlay(self) -> None:
        """Remove the temporary login overlay from the main workspace."""
        if self.dark_overlay is not None:
            self.dark_overlay.hide()
            self.dark_overlay.deleteLater()
            self.dark_overlay = None

    def _dashboard_welcome_html(self, colors: dict[str, str] | None = None) -> str:
        """Build themed HTML for the dashboard welcome banner."""
        from config import BRAND_NAME

        palette = colors or get_theme_manager().get_colors()
        return (
            f'<span style="color:{palette["muted_text"]}; font-size:18px; font-weight:600;">'
            f"Welcome to </span>"
            f'<span style="color:{palette["heading_text"]}; font-size:18px; font-weight:700;">'
            f"{BRAND_NAME}</span>"
        )

    def _refresh_dashboard_welcome_label(self, colors: dict[str, str] | None = None) -> None:
        """Reapply welcome banner text and colors after a theme switch."""
        welcome_label = getattr(self, "dashboard_welcome_label", None)
        if welcome_label is None:
            return
        welcome_label.setTextFormat(Qt.TextFormat.RichText)
        welcome_label.setText(self._dashboard_welcome_html(colors))

    def _create_admin_controls(self) -> QFrame:
        """Create the dashboard welcome row with optional admin actions."""
        colors = get_theme_manager().get_colors()
        admin_frame = QFrame()
        admin_frame.setObjectName("adminControls")
        admin_frame.setStyleSheet(f"""
            QFrame#adminControls {{
                background-color: {colors['panel_bg']};
                border-bottom: 1px solid {colors['border']};
            }}
            QLabel#adminWelcomeLabel {{
                background: transparent;
                border: none;
            }}
            QPushButton#manageUsersButton {{
                background-color: {colors['button_primary']};
                color: #ffffff;
                border: none;
                padding: 7px 14px;
                border-radius: 5px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton#manageUsersButton:hover {{
                background-color: {colors['focus_border']};
            }}
        """)

        admin_layout = QHBoxLayout(admin_frame)
        admin_layout.setContentsMargins(20, 8, 20, 8)
        admin_layout.setSpacing(12)

        self.dashboard_welcome_label = QLabel()
        self.dashboard_welcome_label.setObjectName("adminWelcomeLabel")
        self._refresh_dashboard_welcome_label(colors)
        admin_layout.addWidget(self.dashboard_welcome_label)
        admin_layout.addStretch()

        self.manage_users_button = QPushButton("Manage Users")
        self.manage_users_button.setObjectName("manageUsersButton")
        self.manage_users_button.setToolTip("Manage application users and permissions")
        self.manage_users_button.clicked.connect(self.show_user_management)
        admin_layout.addWidget(self.manage_users_button)

        return admin_frame
    
    def setup_workspace_pages(self):
        """Setup pages for the QStackedWidget workspace."""
        # Create dashboard page (initial page)
        self.dashboard_widget = DashboardWidget(self.db)
        self.stack_widget.addWidget(self.dashboard_widget)

        # Create company page
        self.company_widget = CompanyPageWidget(self.db)
        self.stack_widget.addWidget(self.company_widget)

        # New Company, Open Company, Products, Debtors/Creditors, Bank Accounts, Sales Entry, Purchase Entry, Ledger will be standalone windows, not in stack

        # Add pages dictionary (excluding standalone windows)
        self.pages = {
            'Dashboard': self.dashboard_widget,
            'Company': self.company_widget,
        }
    
    def connect_signals(self):
        """Connect signals between components."""
        # Sidebar page changes
        self.sidebar.page_changed.connect(self.on_page_changed)
        self.sidebar.company_closed.connect(self.on_company_closed)

        self.topbar.logout_requested.connect(self.handle_logout)
        if hasattr(self, "shortcut_toolbar") and hasattr(self.shortcut_toolbar, "search_requested"):
            self.shortcut_toolbar.search_requested.connect(self.on_search_requested)

        # Secondary shortcut toolbar (below the topbar) routes through the
        # standard page-change handler.
        if hasattr(self, "shortcut_toolbar"):
            self.shortcut_toolbar.shortcut_activated.connect(
                self._handle_shortcut_route
            )

        # Company page signals
        self.company_widget.company_saved.connect(self.on_active_company_profile_updated)

        self._setup_global_shortcuts()

    def _handle_shortcut_route(self, route_name: str) -> None:
        """Dispatch a ``ShortcutToolbar`` click to the standard page router.

        Failures are intentionally swallowed (logged only) so a routing
        issue for one shortcut never tears the main window down.
        """
        try:
            self.on_page_changed(route_name)
        except Exception as exc:
            print(f"[WARN] Shortcut route '{route_name}' failed: {exc}")

    def _setup_global_shortcuts(self) -> None:
        """Register application-wide navigation and action shortcuts."""
        if getattr(self, "_global_shortcuts_initialized", False):
            return
        self._global_shortcuts_initialized = True

        for route_name, key_sequence in MODULE_ROUTE_SHORTCUTS.items():
            shortcut = QShortcut(QKeySequence(key_sequence), self)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(
                lambda route=route_name: self._open_route_from_shortcut(route)
            )

        action_bindings = (
            ("save", self._handle_global_save),
            ("print", self._handle_global_print),
            ("search", self._handle_global_search),
            ("new_record", self._handle_global_new_record),
        )
        for action_key, handler in action_bindings:
            key_sequence = GLOBAL_ACTION_SHORTCUTS.get(action_key)
            if not key_sequence:
                continue
            shortcut = QShortcut(QKeySequence(key_sequence), self)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(handler)

    def _open_route_from_shortcut(self, page_name: str) -> None:
        """Navigate to a module using a keyboard shortcut."""
        if self._is_login_gateway_active():
            return
        if not getattr(self, "dashboard_loaded", False):
            return
        self.on_page_changed(page_name)

    def _is_login_gateway_active(self) -> bool:
        """Return True when the stacked login gateway is the current page."""
        gateway = getattr(self, "gateway", None)
        stacked = getattr(self, "stacked_widget", None)
        if gateway is None or stacked is None:
            return False
        try:
            return stacked.currentWidget() is gateway and gateway.isVisible()
        except RuntimeError:
            return False

    def _active_entry_widget(self):
        """Return the focused entry widget from a module window, if any."""
        active_window = QApplication.activeWindow()
        if active_window is None:
            return None

        if active_window is self:
            current_widget = getattr(self, "stack_widget", None)
            if current_widget is None:
                return None
            widget = current_widget.currentWidget()
            dashboard_widget = getattr(self, "dashboard_widget", None)
            if widget is not None and widget is not dashboard_widget:
                return widget
            return None

        if hasattr(active_window, "centralWidget"):
            return active_window.centralWidget()
        return None

    def _click_first_matching_control(self, widget, attr_names) -> bool:
        """Click the first enabled push button matching the provided names."""
        if widget is None:
            return False

        for attr_name in attr_names:
            control = getattr(widget, attr_name, None)
            if isinstance(control, QPushButton) and control.isEnabled():
                control.click()
                return True
        return False

    def _call_first_matching_method(self, widget, method_names) -> bool:
        """Call the first callable method found on the active entry widget."""
        if widget is None:
            return False

        for method_name in method_names:
            method = getattr(widget, method_name, None)
            if callable(method):
                method()
                return True
        return False

    def _handle_global_save(self) -> None:
        """Trigger save on the currently focused entry screen."""
        widget = self._active_entry_widget()
        if self._click_first_matching_control(
            widget,
            ("save_btn", "btn_save", "save_button", "ok_btn"),
        ):
            return
        self._call_first_matching_method(
            widget,
            (
                "save_record",
                "save_invoice",
                "save_quotation",
                "save_or_update",
                "save_return",
                "save_company",
                "save_payment",
                "save_receipt",
            ),
        )

    def _handle_global_print(self) -> None:
        """Trigger print on the currently focused entry screen."""
        widget = self._active_entry_widget()
        if self._click_first_matching_control(
            widget,
            ("print_btn", "btn_print", "print_button"),
        ):
            return
        self._call_first_matching_method(
            widget,
            ("print_invoice", "print_voucher", "print_document", "print_report"),
        )

    def _handle_global_search(self) -> None:
        """Focus the global search field on the shortcut toolbar row."""
        toolbar = getattr(self, "shortcut_toolbar", None)
        if toolbar is not None and hasattr(toolbar, "focus_search_field"):
            toolbar.focus_search_field()
            return

        search_bar = getattr(toolbar, "global_search_bar", None) if toolbar else None
        search_input = getattr(search_bar, "search_input", None) if search_bar else None
        if search_input is None:
            return
        search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        search_input.selectAll()

    def _handle_global_new_record(self) -> None:
        """Trigger new-record actions on the currently focused entry screen."""
        widget = self._active_entry_widget()
        if self._click_first_matching_control(
            widget,
            ("new_btn", "btn_new", "add_btn", "btn_add", "new_button"),
        ):
            return
        self._call_first_matching_method(
            widget,
            ("new_record", "add_new_row", "clear_form", "reset_form", "prepare_new"),
        )

    def show_login_screen(self) -> bool:
        """Return to the company gateway login screen."""
        self._return_to_login_screen()
        return True

    def _confirm_logout(self) -> bool:
        """Ask the user to confirm logout before ending the current session."""
        from ui.message_boxes import question as themed_question

        message = (
            "Are you sure you want to log out?\n\n"
            "You will return to the login screen and must sign in again "
            "to continue working."
        )
        if self._auto_backup_will_run():
            message += (
                "\n\nAn automatic backup will be created before logging out."
            )

        reply = themed_question(
            self,
            "Log Out",
            message,
        )
        return reply == QMessageBox.StandardButton.Yes

    def handle_logout(self) -> None:
        """Log out the current user and return to the login screen."""
        if not self._confirm_logout():
            return

        try:
            if self._auto_backup_will_run():
                self._run_silent_auto_backup()
            self._return_to_login_screen()
        except Exception as exc:
            print(f"[MAIN WINDOW] Logout failed: {exc}")
            traceback.print_exc()
            QMessageBox.warning(
                self,
                "Log Out",
                f"Could not return to the login screen:\n{exc}",
            )

    def _ensure_logout_gateway(self):
        """Create or recover the login gateway page inside the main stacked widget."""
        from ui.company_gateway import CompanyGateway

        gateway = getattr(self, "gateway", None)
        if gateway is not None:
            try:
                if self.stacked_widget.indexOf(gateway) >= 0:
                    return gateway
            except RuntimeError:
                gateway = None
                self.gateway = None

        gateway = CompanyGateway(self.stacked_widget)
        self.gateway = gateway
        if not getattr(self, "_logout_gateway_authenticated_connected", False):
            gateway.authenticated.connect(self.morph_to_dashboard)
            self._logout_gateway_authenticated_connected = True

        if self.stacked_widget.indexOf(gateway) < 0:
            self.stacked_widget.insertWidget(0, gateway)

        app = QApplication.instance()
        if app is not None:
            app.gateway = gateway

        return gateway

    def _resume_dashboard_session(
        self,
        db_path: str,
        company_name: str,
        username: str,
        role: str,
    ) -> None:
        """Re-apply authenticated user context after logging in again."""
        self.db_path = db_path
        current_db_path = getattr(self.db, "db_path", None) if self.db is not None else None
        if db_path and current_db_path != db_path:
            self.db = self._create_database_from_path(db_path)

        self.company_name = company_name or "company"
        self._set_authenticated_session(username, role, "", None)
        self.user_role = self._normalize_role(role)
        self.user_permissions = self._normalize_user_permissions("", self.user_role)
        if self.user_role:
            self.apply_user_permissions(self.user_role, self.user_permissions)
        self._show_all_navigation_controls()
        if self._is_admin_user():
            self._ensure_admin_controls()
        else:
            self._hide_admin_controls()
        self._load_active_company_from_db()
        self._refresh_backup_company_context()
        self._sync_read_only_mode()
        self.show_dashboard()
        self.stacked_widget.setCurrentIndex(1)
        self.setMinimumSize(1200, 800)
        self.showMaximized()
        from ui.app_window_coordinator import ensure_app_window_coordinator

        ensure_app_window_coordinator(self)

    def _clear_authenticated_session(self) -> None:
        """Remove the current user context from the main workspace."""
        self.current_user = None
        self.user_role = None
        self.user_permissions = ""
        self.current_user_record = None
        self._hide_admin_controls()

    def _return_to_login_screen(self) -> None:
        """Close open modules, clear the session, and show the login gateway."""
        self._close_tracked_module_windows(skip_unsaved_prompt=True)
        self._clear_login_overlay()
        self._clear_authenticated_session()
        self._module_window_state_snapshot = {}
        self._application_was_minimized = False
        self._main_window_was_minimized = False

        try:
            active_company_manager.clear_active_company()
        except Exception as exc:
            print(f"[MAIN WINDOW] Could not clear active company on logout: {exc}")

        gateway = self._ensure_logout_gateway()
        if hasattr(gateway, "reset_login_state"):
            gateway.reset_login_state()
        elif hasattr(gateway, "restore_after_failed_handoff"):
            gateway.restore_after_failed_handoff()
            password_input = getattr(gateway, "password_input", None)
            if password_input is not None:
                password_input.clear()

        gateway_index = self.stacked_widget.indexOf(gateway)
        if gateway_index >= 0:
            self.stacked_widget.setCurrentIndex(gateway_index)
            gateway.show()

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 700)
        self.raise_()
        self.activateWindow()

        password_input = getattr(gateway, "password_input", None)
        if password_input is not None:
            password_input.setFocus(Qt.FocusReason.OtherFocusReason)

        pump_ui_events()

    def _set_authenticated_session(
        self,
        username: str,
        role: str,
        permissions: str,
        current_user_record=None,
    ) -> None:
        """
        Store authenticated user context and refresh the topbar user display.

        Args:
            username: Authenticated login name.
            role: Authenticated role, such as Admin or User.
            permissions: Comma-separated permission list or ALL.
            current_user_record: Optional dialog-provided user metadata.
        """
        normalized_permissions = self._normalize_user_permissions(permissions, role)
        self.current_user = username
        self.user_role = role
        self.user_permissions = normalized_permissions
        self.current_user_record = current_user_record

        if self.current_user_record is not None:
            self.current_user_record["permissions"] = normalized_permissions

        self._update_current_user_display()

    def _current_user_display_name(self) -> str:
        """Return the best available username for the topbar display."""
        if isinstance(self.current_user, dict):
            return (
                self.current_user.get("username")
                or self.current_user.get("name")
                or "Admin User"
            )

        if self.current_user:
            return str(self.current_user)

        if isinstance(self.current_user_record, dict):
            return (
                self.current_user_record.get("username")
                or self.current_user_record.get("name")
                or "Admin User"
            )

        return "Admin User"

    def _update_current_user_display(self) -> None:
        """Refresh the topbar username label using available helper attributes."""
        username = self._current_user_display_name()
        display_text = username
        if self.user_role:
            display_text = f"{display_text} ({self.user_role})"

        direct_label = getattr(self, "user_label", None)
        if direct_label is not None and hasattr(direct_label, "setText"):
            direct_label.setText(display_text)

        topbar = getattr(self, "topbar", None)
        if topbar is None:
            return

        if hasattr(topbar, "set_current_user_display"):
            topbar.set_current_user_display(username, self.user_role)
            return

        for label_attr in (
            "user_label",
            "current_user_label",
            "username_label",
            "user_name_label",
        ):
            label = getattr(topbar, label_attr, None)
            if label is not None and hasattr(label, "setText"):
                label.setText(display_text)
                return

    def _close_tracked_module_windows(self, *, skip_unsaved_prompt: bool = False) -> None:
        """Close tracked standalone module windows before switching users or exiting."""
        for window_key, window in list(self._open_module_windows.items()):
            try:
                if window is not None:
                    if skip_unsaved_prompt:
                        window._skip_unsaved_close_prompt = True
                    window.close()
            except Exception as exc:
                print(f"[MAIN WINDOW] Could not close {window_key} during logout: {exc}")

        self._open_module_windows.clear()

    def apply_user_permissions(self, role, permissions_string=None):
        """Apply login-loaded module permissions to sidebar navigation controls.

        Args:
            role: Authenticated user role. For backward compatibility, this may
                be the old permissions_string argument.
            permissions_string: Comma-separated module permissions or the literal
                ALL for unrestricted Admin access.
        """
        known_roles = {"Admin", "User"}
        if permissions_string is None and str(role or "").strip() not in known_roles:
            permissions_string = role
            role = self.user_role

        role = role or self.user_role
        permissions_string = self._normalize_user_permissions(permissions_string, role)
        self.user_role = role
        self.user_permissions = permissions_string
        self._update_current_user_display()
        try:
            if role == "Admin" or str(permissions_string or "").strip().upper() == "ALL":
                self._allowed_navigation_permissions = None
                self._show_all_navigation_controls()
                self._refresh_shortcut_toolbar_permissions()
                print("[MAIN WINDOW] Applied unrestricted Admin permissions.")
                return

            self._allowed_navigation_permissions = self._sanitize_permissions(
                permissions_string
            )
            self._show_all_navigation_controls()
            self._refresh_shortcut_toolbar_permissions()

            print(
                "[AUTH] applying permissions "
                f"role={role or '(none)'} "
                f"permissions={permissions_string if permissions_string else '(none)'} "
                f"allowed={sorted(self._allowed_navigation_permissions)}"
            )
        except Exception as exc:
            print(f"[MAIN WINDOW] Could not apply user permissions: {exc}")

    def _refresh_shortcut_toolbar_permissions(self) -> None:
        """Hide shortcut toolbar buttons the active user cannot access.

        Filters the toolbar's ten canonical routes through ``_is_page_allowed``
        and pushes the allowed subset into ``ShortcutToolbar.apply_permissions``
        so the bar mirrors the rest of the navigation gating logic.
        """
        toolbar = getattr(self, "shortcut_toolbar", None)
        if toolbar is None:
            return

        shortcut_routes = (
            "Sales",
            "Sales Return",
            "Purchase",
            "Cash Receipt",
            "Bank Receipt",
            "Cash Payment",
            "Bank Payment",
            "Day Book",
            "Cash Book",
            "Ledger",
        )

        try:
            allowed_routes = {
                route for route in shortcut_routes if self._is_page_allowed(route)
            }
            toolbar.apply_permissions(allowed_routes)
        except Exception as exc:
            print(f"[WARN] Could not refresh shortcut toolbar permissions: {exc}")

    def _normalize_user_permissions(self, permissions_string, role=None):
        """Return a non-None permission string with Admin fallback applied."""
        normalized_permissions = permissions_string or ""
        effective_role = role if role is not None else self.user_role
        if not str(normalized_permissions).strip() and effective_role == "Admin":
            return "ALL"
        return normalized_permissions

    def _sanitize_permissions(self, permissions_string):
        """Return lowercase module permissions from a comma-separated string."""
        if permissions_string:
            allowed = {
                p.strip().lower()
                for p in str(permissions_string).split(",")
                if p.strip()
            }
        else:
            allowed = set()
        return allowed

    def _show_all_navigation_controls(self):
        """Force all sidebar and Admin navigation controls visible and enabled."""
        sidebar = getattr(self, "sidebar", None)
        if sidebar and hasattr(sidebar, "show_all_routes"):
            sidebar.show_all_routes()
        elif sidebar:
            for route_name in getattr(sidebar, "navigation_buttons", {}):
                for widget in self._navigation_widgets_for_route(route_name):
                    if widget is None:
                        continue
                    widget.setVisible(True)
                    widget.setEnabled(True)
            for section_widget in getattr(sidebar, "menu_sections", {}).values():
                section_widget.setVisible(True)
                if hasattr(section_widget, "header_btn"):
                    section_widget.header_btn.setVisible(True)
                    section_widget.header_btn.setEnabled(True)

        if self._is_admin_user():
            self._ensure_admin_controls()
        else:
            self._hide_admin_controls()

    def _is_page_allowed(self, page_name: str) -> bool:
        """Return True when the authenticated user may open a route."""
        has_all_permissions = (
            str(self.user_permissions or "").strip().upper() == "ALL"
        )
        if self.user_role == "Admin" or has_all_permissions:
            return True

        allowed_permissions = getattr(self, "_allowed_navigation_permissions", None)
        if allowed_permissions is None:
            return True

        required_permissions = self.NAVIGATION_PERMISSION_MAP.get(page_name)
        if not required_permissions:
            return True

        return bool(required_permissions.intersection(allowed_permissions))

    def _required_permissions_for_route(self, route_name: str):
        """Return checkbox permission tokens required by a navigation route."""
        return self.NAVIGATION_PERMISSION_MAP.get(route_name)

    def _navigation_widgets_for_route(self, route_name: str):
        """Return sidebar widgets registered for a route, if present."""
        sidebar = getattr(self, "sidebar", None)
        if not sidebar:
            return []

        navigation_buttons = getattr(sidebar, "navigation_buttons", {})
        widgets = navigation_buttons.get(route_name, [])
        if isinstance(widgets, (list, tuple, set)):
            return list(widgets)
        return [widgets]

    def _apply_sidebar_permission_visibility(self):
        """Keep every sidebar route visible while route guards enforce access."""
        sidebar = getattr(self, "sidebar", None)
        if not sidebar:
            return

        if hasattr(sidebar, "show_all_routes"):
            sidebar.show_all_routes()
        else:
            for route_name in getattr(sidebar, "navigation_buttons", {}):
                for widget in self._navigation_widgets_for_route(route_name):
                    if widget is None:
                        continue
                    widget.setVisible(True)
                    widget.setEnabled(True)
            for section_widget in getattr(sidebar, "menu_sections", {}).values():
                section_widget.setVisible(True)
                if hasattr(section_widget, "header_btn"):
                    section_widget.header_btn.setVisible(True)
                    section_widget.header_btn.setEnabled(True)

        sidebar.updateGeometry()
        sidebar.update()

    def _show_permission_denied_warning(self, message=None, title="Permission Denied"):
        """Show a red permission warning without opening the blocked module."""
        warning_text = (
            message
            or "You do not have permission to open this module. Please contact Admin."
        )
        from ui.message_boxes import warning as themed_warning
        themed_warning(self, title, warning_text)

    def _refresh_sidebar_permission_layout(self):
        """Hide empty sidebar sections and orphaned divider labels."""
        sidebar = getattr(self, "sidebar", None)
        menu_sections = getattr(sidebar, "menu_sections", {}) if sidebar else {}

        for section_name, section_widget in menu_sections.items():
            navigation_items = getattr(section_widget, "navigation_items", [])
            pending_dividers = []
            section_has_visible_button = False

            for item in navigation_items:
                if isinstance(item, QLabel):
                    item.setVisible(False)
                    pending_dividers = [item]
                    continue

                if isinstance(item, QPushButton) and not item.isHidden():
                    section_has_visible_button = True
                    for divider in pending_dividers:
                        divider.setVisible(True)
                    pending_dividers = []

            section_widget.setVisible(section_has_visible_button or not navigation_items)
            if (
                getattr(sidebar, "current_open_section", None) == section_name
                and not section_widget.isVisible()
            ):
                sidebar.current_open_section = None

            section_layout = section_widget.layout()
            if section_layout is not None:
                section_layout.invalidate()
                section_layout.activate()

        sidebar.updateGeometry()
        sidebar.update()

    def _load_active_company_from_db(self):
        """Load the company opened during login without overwriting a gateway session."""
        try:
            session_company = active_company_manager.get_active_company()
            if session_company and session_company.get("id"):
                # Secret-file logins set the session company without touching is_active.
                active_company_manager.set_active_company(session_company)
                self.company_name = (
                    session_company.get("business_name") or self.company_name
                )
                if hasattr(self, "topbar") and self.topbar:
                    self.topbar.update_active_company()
                return

            active_company = self.db.get_active_company() if self.db else None
            if active_company:
                active_company_manager.set_active_company(active_company)
                self.company_name = (
                    active_company.get("business_name") or self.company_name
                )
                if hasattr(self, "topbar") and self.topbar:
                    self.topbar.update_active_company()
                return
        except Exception as error:
            print(f"[MAIN WINDOW] Could not load active company: {error}")

        active_company_manager.clear_active_company()
        print("[MAIN WINDOW] No active company is available.")

        # New company and Open company signals will be connected when windows are opened
    
    def _requires_open_company(self, page_name: str) -> bool:
        """Return True for modules that must not open without an active company."""
        free_pages = {
            "Dashboard",
            "View Company",
            "Close Company", "General Settings", "Tax Settings",
            "Invoice Settings", "User Settings", "Barcode Settings",
            "About Me",
        }
        return page_name not in free_pages

    def ensure_company_or_redirect(self) -> bool:
        """
        Reusable helper for company guard behavior.
        
        Returns:
            bool: True if company is active, False if redirected to Open Company page
        """
        if active_company_manager.has_active_company():
            return True
        
        # Show warning and automatically redirect to Open Company page
        QMessageBox.warning(self, "No Company Open", "Please open a company first")
        self.show_open_company()
        return False

    def _ensure_company_open_for_page(self, page_name: str) -> bool:
        if not self._requires_open_company(page_name):
            return True
        return self.ensure_company_or_redirect()

    def on_page_changed(self, page_name: str):
        """Handle page change from sidebar."""
        if self._is_read_only_route_blocked(page_name):
            self._show_read_only_warning()
            return

        if not self._is_page_allowed(page_name):
            self._show_permission_denied_warning()
            return

        if not self._ensure_company_open_for_page(page_name):
            return

        if page_name == "Company":
            self.show_company()
        elif page_name in ("Dashboard", "Dashboard Home"):
            self.show_dashboard()
        elif page_name == "New Company":
            self.show_new_company()
        elif page_name == "View Company":
            self.show_view_company()
        elif page_name == "Open Company":
            self.show_open_company()
        elif page_name == "Product/Service":
            self.show_products()
        elif page_name == "Account":
            self.show_account_creation()
        elif page_name in ("Debitor/Creditor", "Debtor/Creditor"):
            self.show_debitor_creditor()
        elif page_name == "Bank Account":
            self.show_bank_accounts()
        elif page_name == "Sales":
            self.show_sales()
        elif page_name == "Purchase":
            self.show_purchase()
        elif page_name == "Purchase Order":
            self.show_purchase_order()
        elif page_name == "Quotation":
            self.show_quotation_entry()
        elif page_name == "Post Dated Cheque":
            self.show_pdc()
        elif page_name == "Credit/Debit Note":
            self.show_credit_debit_note()
        elif page_name == "Van Entry":
            self.show_van_entry()
        elif page_name == "Van Return Entry":
            self.show_van_return()
        elif page_name == "Opening Balance":
            self.show_opening_balance()
        elif page_name == "Opening Stock Entry":
            self.show_opening_stock_entry()
        elif page_name == "Stock Adjustment":
            self.show_stock_adjustment()
        elif page_name == "Sales Return":
            self.show_sales_return()
        elif page_name == "Purchase Return":
            self.show_purchase_return()
        elif page_name == "Ledger":
            self.show_ledger()
        elif page_name == "Ledger Statement":
            self.show_ledger_statement()
        elif page_name == "Bill History":
            self.show_bill_history()
        elif page_name == "Cash Tender History":
            self.show_cash_tender_history()
        elif page_name == "Sales Book":
            self.show_sales_book()
        elif page_name == "Quotation Book":
            self.show_quotation_book()
        elif page_name == "Sales Return Book":
            self.show_sales_return_book()
        elif page_name == "Purchase Book":
            self.show_purchase_book()
        elif page_name == "Purchase Order Book":
            self.show_purchase_order_book()
        elif page_name == "Purchase Return Book":
            self.show_purchase_return_book()
        elif page_name == "Day Book":
            self.show_day_book()
        elif page_name == "Cash Book":
            self.show_cash_book()
        elif page_name == "PDC Book":
            self.show_pdc_book()
        elif page_name == "Journal Book":
            self.show_journal_book()
        elif page_name == "Daily Stock Register":
            self.show_daily_stock_register()
        elif page_name == "Price List":
            self.show_price_list()
        elif page_name == "Stock Checker":
            self.show_stock_checker()
        elif page_name == "System Diagnostics":
            self.show_system_diagnostics()
        elif page_name == "Print Settings":
            self.show_print_settings()
        elif page_name == "Audit Logs":
            self.show_audit_logs()
        elif page_name == "Manage Users":
            self.show_user_management()
        elif page_name == "Backup and Restore Data":
            self.open_backup_dialog()
        elif page_name == "Compact and Repair Data":
            self.run_compact_and_repair()
        elif page_name == "Inter-Company Transfer":
            self.open_transfer_dialog()
        elif page_name == "Close Financial Year (Year-End)":
            self.open_year_end_dialog()
        elif page_name == "Daily Collection Report":
            self.show_collection_report()
        elif page_name == "Best Sellers (Top Products)":
            self.open_best_sellers_report()
        elif page_name == "Salesman Record Book":
            self.open_salesman_book()
        elif page_name == "Trial Balance":
            self.show_trial_balance()
        elif page_name == "Profit and Loss Account":
            self.show_profit_loss()
        elif page_name == "Balance Sheet":
            self.show_balance_sheet()
        elif page_name == "Stock Value":
            self.show_stock_value()
        elif page_name == "Stock Report":
            self.show_stock_report()
        elif page_name == "Sales Wise Profit":
            self.show_sales_profit_book()
        elif page_name == "Monthly Analysis":
            self.show_monthly_analysis()
        elif page_name == "Cash Receipt":
            self.show_cash_receipt()
        elif page_name == "Cash Payment":
            self.show_cash_payment()
        elif page_name == "Bank Receipt":
            self.show_bank_receipt()
        elif page_name == "Bank Payment":
            self.show_bank_payment()
        elif page_name == "Journal Entry":
            self.show_journal_entry()
        elif page_name == "GST Sales Report":
            self.show_gst_sales_report()
        elif page_name == "GSTR-1":
            self.show_gstr1()
        elif page_name == "GST Purchase Report":
            self.show_gst_purchase_report()
        elif page_name == "Barcode":
            self.show_barcode_print_queue()
        elif page_name == "Barcode Settings":
            self.show_barcode_settings()
        elif page_name == "General Settings":
            self.open_global_settings_dialog()
        elif page_name == "Tax Settings":
            self.show_tax_settings()
        elif page_name == "Invoice Settings":
            self.show_invoice_settings()
        elif page_name == "User Settings":
            self.show_user_management()
        elif page_name == "Close Company":
            if hasattr(self, "sidebar") and hasattr(self.sidebar, "close_company"):
                self.sidebar.close_company()
        else:
            # For other pages, show dashboard for now
            self.show_dashboard()
    
    def on_search_requested(self, search_text: str):
        """Handle global menu search from the shortcut toolbar."""
        query = (search_text or "").strip()
        if not query:
            return

        try:
            from bizora_core.global_search import find_search_suggestions, resolve_global_search

            result = resolve_global_search(query)
            if result is not None and result.score < 850:
                suggestions = find_search_suggestions(query, limit=1)
                if suggestions:
                    refined = resolve_global_search(suggestions[0])
                    if refined is not None:
                        result = refined

            if result is None:
                QMessageBox.information(
                    self,
                    "Search",
                    f"No matching menu item found for \"{query}\".",
                )
                return

            self._execute_global_search_result(result)
            toolbar = getattr(self, "shortcut_toolbar", None)
            search_bar = getattr(toolbar, "global_search_bar", None) if toolbar else None
            if search_bar is not None and hasattr(search_bar, "search_input"):
                search_bar.search_input.clear()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Search",
                f"Could not complete search:\n{exc}",
            )

    def _exec_modal_dialog(self, dialog_runner) -> None:
        """Backward-compatible wrapper; secondary pages now open non-modally."""
        dialog_runner()

    def _execute_global_search_result(self, result) -> None:
        """Open the route or settings pane resolved by search."""
        from bizora_core.global_search import GlobalSearchResult

        if not isinstance(result, GlobalSearchResult):
            return

        if result.kind == "settings_section":
            self._open_settings_route_with_section(
                result.settings_parent_route or "",
                result.settings_section_id or "",
            )
            return

        if result.route_name:
            self.on_page_changed(result.route_name)

    def _open_settings_route_with_section(
        self,
        parent_route: str,
        section_id: str,
    ) -> None:
        """Open a settings dialog and focus one nested section."""
        if parent_route == "General Settings":
            self.open_global_settings_dialog(initial_section=section_id)
            return

        if parent_route == "Invoice Settings":
            self.show_invoice_settings(initial_section=section_id)
            return

        self.on_page_changed(parent_route)
    
    def on_active_company_profile_updated(self, updated_data=None):
        """Refresh session state and topbar after company profile changes."""
        try:
            active_id = active_company_manager.get_active_company_id()
            company_id = None
            if isinstance(updated_data, dict):
                company_id = updated_data.get("id")
            if company_id is None:
                company_id = active_id
            if self.db and company_id and active_id == company_id:
                refreshed = self.db.get_company_by_id(company_id)
                if refreshed:
                    active_company_manager.set_active_company(refreshed)
                    self.company_name = refreshed.get("business_name") or self.company_name
        except Exception as exc:
            print(f"[MAIN WINDOW] Could not refresh active company profile: {exc}")
        if hasattr(self, "topbar") and self.topbar:
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

    def _resolve_module_page_widget(self, window, widget_type):
        """Return a hosted page widget from a standalone module window."""
        page = get_standalone_page_widget(window)
        if page is None:
            return None
        if isinstance(page, widget_type):
            return page
        return page.findChild(widget_type)

    def _on_module_window_closed(self, window_key):
        """Clean up tracking when a standalone module window is closed."""
        window = self._open_module_windows.get(window_key)
        if self._is_live_module_window(window):
            self._undock_module_window(window)
        self._open_module_windows.pop(window_key, None)
        self._maybe_return_to_dashboard()
    
    def on_company_closed(self):
        """Handle company close event."""
        try:
            if self.db:
                self.db.execute_update("UPDATE companies SET is_active = 0", ())
        except Exception as e:
            print(f"[MAIN WINDOW] Could not clear DB active company flag: {e}")
        # Update topbar to reflect no active company
        self.topbar.update_active_company()
        self.show_dashboard()
    
    def show_dashboard(self):
        """Show dashboard page."""
        self.stack_widget.setCurrentWidget(self.dashboard_widget)
        if hasattr(self.dashboard_widget, "set_database"):
            self.dashboard_widget.set_database(self.db)
        if hasattr(self.dashboard_widget, "refresh_data"):
            self.dashboard_widget.refresh_data()
    
    def show_company(self):
        """Show company page."""
        self.stack_widget.setCurrentWidget(self.company_widget)
    
    def show_new_company(self):
        """Open new company as standalone window."""
        # Check if window already exists
        if 'new_company' in self._open_module_windows:
            window = self._open_module_windows['new_company']
            self._center_and_show_window(window)
            window.activateWindow()
            return

        # Create widget and window
        widget = NewCompanyPageWidget(self.db)
        window = StandaloneModuleWindow(widget, "Create New Company", self)
        window.setMinimumSize(900, 700)

        # Connect signals
        widget.company_saved.connect(self.on_active_company_profile_updated)

        # Clean up when window closes
        window.destroyed.connect(lambda: self._on_module_window_closed('new_company'))

        self._center_and_show_window(window)

        # Track window
        self._open_module_windows['new_company'] = window
    
    def show_view_company(self):
        """Open the active company management page with view, edit, and delete actions."""
        if 'view_company' in self._open_module_windows:
            window = self._open_module_windows['view_company']
            widget = get_standalone_page_widget(window)
            if isinstance(widget, OpenCompanyPageWidget) and hasattr(widget, 'load_companies'):
                widget.load_companies()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        widget = OpenCompanyPageWidget(
            self.db,
            auto_close_on_selection=False,
            show_success_message=True,
            activate_on_selection=False,
            show_row_actions=True,
            row_actions=("view", "edit", "delete"),
            active_only=True,
            company_visibility=(
                (active_company_manager.get_active_company() or {}).get("visibility")
                or "normal"
            ),
            title_text="View Company",
            subtitle_text="View, edit, or delete the currently active company",
            show_open_button=False,
        )
        widget.load_companies()
        window = StandaloneModuleWindow(widget, "View Company", self)
        window.setMinimumSize(900, 700)
        widget.company_profile_updated.connect(self.on_active_company_profile_updated)
        window.destroyed.connect(lambda: self._on_module_window_closed('view_company'))
        self._center_and_show_window(window)
        self._open_module_windows['view_company'] = window

    def show_open_company(self):
        """Open the company selection window."""
        if 'open_company' in self._open_module_windows:
            window = self._open_module_windows['open_company']
            widget = self._resolve_module_page_widget(window, OpenCompanyPageWidget)
            if widget is None:
                widget = self._resolve_module_page_widget(window, NewCompanyPageWidget)
            if widget and hasattr(widget, 'load_companies'):
                widget.load_companies()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        widget = OpenCompanyPageWidget(
            self.db,
            auto_close_on_selection=True,
            show_success_message=True,
            activate_on_selection=True,
            show_row_actions=True,
            row_actions=("view", "edit", "delete"),
            active_only=False,
            title_text="Open Company",
            subtitle_text="Select a company to work with",
            show_open_button=True,
        )
        widget.load_companies()
        window = StandaloneModuleWindow(widget, "Open Company", self)
        window.setMinimumSize(900, 700)
        widget.company_selected.connect(self.on_company_selected)
        widget.company_profile_updated.connect(self.on_active_company_profile_updated)
        window.destroyed.connect(lambda: self._on_module_window_closed('open_company'))
        self._center_and_show_window(window)
        self._open_module_windows['open_company'] = window
    
    def show_products(self):
        """Open products/services as standalone window (lazy loaded)."""
        # Check if window already exists
        if 'products' in self._open_module_windows:
            window = self._open_module_windows['products']
            # Reload products list when focusing existing window
            from .products import ProductsWidget
            widget = self._resolve_module_page_widget(window, ProductsWidget)
            if widget:
                widget.load_products()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        # Lazy import: load heavy module only when needed
        import_start = time.time()
        from .products import ProductsWidget
        import_end = time.time()

        # Create widget and window
        widget = ProductsWidget(self.db)
        widget.load_products()
        window = StandaloneModuleWindow(widget, "Products / Services", self)
        window.setMinimumSize(1000, 700)

        # Clean up when window closes
        window.destroyed.connect(lambda: self._on_module_window_closed('products'))

        # Show window
        self._center_and_show_window(window)

        # Track window
        self._open_module_windows['products'] = window

        # Performance logging
        load_time = import_end - import_start
        self._page_load_times['products'] = load_time
        print(f"[PERF] First Products open: {load_time:.3f} sec (import: {load_time:.3f} sec)")
    
    def show_debitor_creditor(self):
        """Open debitor/creditor as standalone window (lazy loaded)."""
        # Check if window already exists
        if 'debitor_creditor' in self._open_module_windows:
            window = self._open_module_windows['debitor_creditor']
            # Reload parties list when focusing existing window
            from .debitor_creditor import DebitorCreditorWidget
            widget = self._resolve_module_page_widget(window, DebitorCreditorWidget)
            if widget:
                widget.load_parties()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        # Lazy import: load heavy module only when needed
        import_start = time.time()
        from .debitor_creditor import DebitorCreditorWidget
        import_end = time.time()

        # Create widget and window
        widget = DebitorCreditorWidget(self.db)
        widget.load_parties()

        # Connect party_saved signal to refresh all open Sales Entry windows
        widget.party_saved.connect(self._on_party_saved)

        window = StandaloneModuleWindow(widget, "Debtors / Creditors", self)
        window.setMinimumSize(1000, 700)

        # Clean up when window closes
        window.destroyed.connect(lambda: self._on_module_window_closed('debitor_creditor'))

        # Show window
        self._center_and_show_window(window)

        # Track window
        self._open_module_windows['debitor_creditor'] = window

        # Performance logging
        load_time = import_end - import_start
        self._page_load_times['debitor_creditor'] = load_time
        print(f"[PERF] First Debtor/Creditor open: {load_time:.3f} sec")

    def _on_party_saved(self):
        """Handle party_saved signal - refresh all open Sales Entry and Purchase Return windows."""
        from .sales_entry import SalesEntryWidget
        sales_windows = [k for k in self._open_module_windows.keys() if k.startswith('sales_')]
        for window_key in sales_windows:
            window = self._open_module_windows[window_key]
            widget = self._resolve_module_page_widget(window, SalesEntryWidget)
            if widget and hasattr(widget, 'refresh_parties'):
                widget.refresh_parties()

        # Refresh Purchase Return windows
        from .purchase_return import PurchaseReturnPageWidget
        pr_windows = [k for k in self._open_module_windows.keys() if k.startswith('purchase_return')]
        for window_key in pr_windows:
            window = self._open_module_windows[window_key]
            widget = self._resolve_module_page_widget(window, PurchaseReturnPageWidget)
            if widget and hasattr(widget, 'refresh_creditors'):
                widget.refresh_creditors()

        # Refresh Purchase Entry windows
        from .purchase_entry import PurchaseEntryWidget
        pe_windows = [k for k in self._open_module_windows.keys() if k.startswith('purchase_')]
        for window_key in pe_windows:
            if window_key in pr_windows:
                continue
            window = self._open_module_windows[window_key]
            widget = self._resolve_module_page_widget(window, PurchaseEntryWidget)
            if widget and hasattr(widget, 'load_creditors'):
                widget.load_creditors()
    
    def show_bank_accounts(self):
        """Open bank accounts as standalone window (lazy loaded)."""
        # Check if window already exists
        if 'bank_accounts' in self._open_module_windows:
            window = self._open_module_windows['bank_accounts']
            # Reload bank accounts list when focusing existing window
            from .bank_accounts import BankAccountWidget
            widget = self._resolve_module_page_widget(window, BankAccountWidget)
            if widget:
                widget.load_bank_accounts()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        # Lazy import: load heavy module only when needed
        import_start = time.time()
        from .bank_accounts import BankAccountWidget
        import_end = time.time()

        # Create widget and window
        widget = BankAccountWidget(self.db)
        widget.load_bank_accounts()
        window = StandaloneModuleWindow(widget, "Bank Accounts", self)
        window.setMinimumSize(1000, 700)

        # Clean up when window closes
        window.destroyed.connect(lambda: self._on_module_window_closed('bank_accounts'))

        # Show window
        self._center_and_show_window(window)

        # Track window
        self._open_module_windows['bank_accounts'] = window

        # Performance logging
        load_time = import_end - import_start
        self._page_load_times['bank_accounts'] = load_time
        print(f"[PERF] First Bank Accounts open: {load_time:.3f} sec")

    def show_account_creation(self):
        """Open Account Creation page as standalone window (lazy loaded)."""
        if 'account_creation' in self._open_module_windows:
            window = self._open_module_windows['account_creation']
            from .account_creation_page import AccountCreationPageWidget
            widget = get_standalone_page_widget(window)
            if isinstance(widget, AccountCreationPageWidget):
                widget._load_data()
                widget._load_accounts_table()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from .account_creation_page import AccountCreationPageWidget
        import_end = time.time()

        widget = AccountCreationPageWidget(self.db)
        window = StandaloneModuleWindow(
            widget, "Chart of Accounts", self, memory_key="account_creation"
        )
        window.setMinimumSize(800, 600)

        window.destroyed.connect(lambda: self._on_module_window_closed('account_creation'))
        self._center_and_show_window(window, fallback_size=(800, 600))
        self._open_module_windows['account_creation'] = window

        load_time = import_end - import_start
        self._page_load_times['account_creation'] = load_time
        print(f"[PERF] First Account Creation open: {load_time:.3f} sec")

    def show_purchase_order(self):
        """Open purchase order entry as a standalone window (isolated from stock/ledger)."""
        import_start = time.time()
        from .purchase_order import PurchaseOrderUI
        import_end = time.time()

        po_windows = [
            k for k in self._open_module_windows.keys() if k.startswith("purchase_order_")
        ]
        next_num = len(po_windows) + 1
        window_key = f"purchase_order_{next_num}"

        widget = PurchaseOrderUI(parent=None, db=self.db)
        title = "Purchase Order" if next_num == 1 else f"Purchase Order ({next_num})"
        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window)

        self._open_module_windows[window_key] = window
        print(f"[PERF] Purchase Order module load: {import_end - import_start:.3f} sec")

    def show_quotation_entry(self):
        """Open quotation entry as standalone window (allows multiple instances, lazy loaded)."""
        # Lazy import: load heavy module only when needed
        import_start = time.time()
        from .quotation_entry import QuotationEntryWidget
        import_end = time.time()

        # Quotation Entry allows multiple concurrent windows
        # Track all open quotation windows with numbered keys
        quotation_windows = [k for k in self._open_module_windows.keys() if k.startswith('quotation_')]
        next_num = len(quotation_windows) + 1
        window_key = f'quotation_{next_num}'

        # Create widget and window
        widget = QuotationEntryWidget(self.db)

        # Determine window title
        if next_num == 1:
            title = "Quotation Entry"
        else:
            title = f"Quotation Entry ({next_num})"

        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window)

        # Register window
        self._open_module_windows[window_key] = window

        # Log performance
        load_time = import_end - import_start
        print(f"[PERF] Quotation Entry module load: {load_time:.3f} sec")

    def show_pdc(self):
        """Open PDC (Post Dated Cheque) page as standalone window."""
        # Check if window already exists
        if "pdc" in self._open_module_windows:
            window = self._open_module_windows["pdc"]
            widget = get_standalone_page_widget(window)
            if widget and hasattr(widget, "load_company"):
                widget.load_company()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        # Create new window
        from .pdc_page import PDCPage

        widget = PDCPage(self.db)

        title = "Post Dated Cheque"

        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window, fallback_size=(1200, 800))

        # Track window
        self._open_module_windows['pdc'] = window

    def show_credit_debit_note(self):
        """Open Credit/Debit Note page as standalone window."""
        from .credit_debit_note_page import CreditDebitNotePage

        widget = CreditDebitNotePage(self.db)

        title = "Credit / Debit Note"

        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window, fallback_size=(1200, 800))

        # Track window
        self._open_module_windows['credit_debit_note'] = window

    def show_sales(self):
        """Open sales entry as standalone window (allows multiple instances, lazy loaded)."""
        # Lazy import: load heavy module only when needed
        import_start = time.time()
        from .sales_entry import SalesEntryWidget
        import_end = time.time()

        # Sales Entry allows multiple concurrent windows
        # Track all open sales windows with numbered keys
        sales_windows = [k for k in self._open_module_windows.keys() if k.startswith('sales_')]
        next_num = len(sales_windows) + 1
        window_key = f'sales_{next_num}'

        # Create widget and window. Heavy Sales caches load after the window is visible.
        widget = SalesEntryWidget(self.db)

        # Determine window title
        if next_num == 1:
            title = "Sales Entry"
        else:
            title = f"Sales Entry ({next_num})"

        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window)

        # Connect widget close event to cleanup
        widget.window_closed.connect(lambda: self._on_sales_window_closed(window_key))

        # Show window
        self._center_and_show_window(window)

        # Track window
        self._open_module_windows[window_key] = window

        # Performance logging (only for first window)
        if next_num == 1:
            load_time = time.time() - import_start
            self._page_load_times['sales_entry'] = load_time
            print(f"[PERF] First Sales Entry open total: {load_time:.3f} sec")

    def _on_sales_window_closed(self, window_key):
        """Clean up tracking when a Sales Entry window is closed."""
        if window_key in self._open_module_windows:
            del self._open_module_windows[window_key]

    def show_purchase(self):
        """Open purchase entry as standalone window (allows multiple instances, lazy loaded)."""
        # Lazy import: load heavy module only when needed
        import_start = time.time()
        from .purchase_entry import PurchaseEntryWidget
        import_end = time.time()

        # Purchase Entry allows multiple concurrent windows
        # Track all open purchase windows with numbered keys
        purchase_windows = [k for k in self._open_module_windows.keys() if k.startswith('purchase_')]
        next_num = len(purchase_windows) + 1
        window_key = f'purchase_{next_num}'

        # Create widget and window
        widget = PurchaseEntryWidget(self, self.db)
        # Don't load creditors/products here - they will be loaded lazily on show

        # Determine window title - always use "Purchase Entry" without numbers
        title = "Purchase Entry"

        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window)

        # Connect widget close event to cleanup
        widget.window_closed.connect(lambda: self._on_purchase_window_closed(window_key))

        # Show window
        self._center_and_show_window(window)

        # Track window
        self._open_module_windows[window_key] = window

        # Performance logging (only for first window)
        if next_num == 1:
            load_time = time.time() - import_start
            self._page_load_times['purchase_entry'] = load_time
            print(f"[PERF] First Purchase Entry open total: {load_time:.3f} sec")

    def _on_purchase_window_closed(self, window_key):
        """Clean up tracking when a Purchase Entry window is closed."""
        if window_key in self._open_module_windows:
            del self._open_module_windows[window_key]

    def show_ledger(self):
        """Open ledger as standalone window (lazy loaded)."""
        # Check if window already exists
        if 'ledger' in self._open_module_windows:
            window = self._open_module_windows['ledger']
            # Refresh ledger when focusing existing window
            from .ledger_page import LedgerPageWidget
            widget = self._resolve_module_page_widget(window, LedgerPageWidget)
            if widget and hasattr(widget, 'refresh'):
                widget.refresh()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        # Lazy import: load heavy module only when needed
        import_start = time.time()
        from .ledger_page import LedgerPageWidget
        import_end = time.time()

        # Create widget and window
        widget = LedgerPageWidget(self.db)
        widget.refresh()
        window = StandaloneModuleWindow(widget, "Ledger", self)
        window.setMinimumSize(1200, 700)

        # Clean up when window closes
        window.destroyed.connect(lambda: self._on_module_window_closed('ledger'))

        # Show window
        self._center_and_show_window(window)

        # Track window
        self._open_module_windows['ledger'] = window

        # Performance logging
        load_time = import_end - import_start
        self._page_load_times['ledger'] = load_time
        print(f"[PERF] First Ledger open: {load_time:.3f} sec")

    def show_collection_report(self):
        """Open Daily Collection Report."""
        self._open_book_window(
            "collection_report",
            "Daily Collection Report",
            "ui.collection_report",
            "CollectionReportUI",
        )

    def open_best_sellers_report(self):
        """Open Best Sellers Report as a standalone popup window."""
        window_key = "best_sellers_report"
        existing_window = self._open_module_windows.get(window_key)
        if existing_window is not None:
            try:
                widget = get_standalone_page_widget(existing_window)
                if widget and hasattr(widget, "refresh_theme"):
                    widget.refresh_theme()
                if widget and hasattr(widget, "refresh"):
                    widget.refresh()
                self._center_and_show_window(existing_window)
                existing_window.activateWindow()
                return
            except RuntimeError:
                del self._open_module_windows[window_key]

        import_start = time.time()
        from ui.best_sellers_report import BestSellersReport

        import_end = time.time()

        db_path = self.db_path or get_default_database_path()
        widget = BestSellersReport(db_path=db_path)
        window = StandaloneModuleWindow(
            widget,
            "Best Sellers Report — Top Selling Products",
            self,
            memory_key=window_key,
        )
        self._center_and_show_window(window, fallback_size=(960, 640))

        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._center_and_show_window(window)
        self._open_module_windows[window_key] = window

        load_time = import_end - import_start
        self._page_load_times[window_key] = load_time
        print(f"[PERF] First Best Sellers Report open: {load_time:.3f} sec")

    def open_salesman_book(self):
        """Open Salesman Record Book as a standalone report window."""
        window_key = "salesman_record_book"
        if window_key in self._open_module_windows:
            window = self._open_module_windows[window_key]
            widget = get_standalone_page_widget(window)
            if widget and hasattr(widget, "refresh_theme"):
                widget.refresh_theme()
            if widget and hasattr(widget, "refresh"):
                widget.refresh()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        widget = SalesmanBook(self.db)
        import_end = time.time()

        window = StandaloneModuleWindow(widget, "Salesman Record Book", self)
        self._center_and_show_window(window)

        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._center_and_show_window(window)
        self._open_module_windows[window_key] = window

        load_time = import_end - import_start
        self._page_load_times[window_key] = load_time
        print(f"[PERF] First Salesman Record Book open: {load_time:.3f} sec")

    def show_trial_balance(self):
        """Open Trial Balance inside the MDI workspace (lazy loaded)."""
        if 'trial_balance' in self._open_module_windows:
            window = self._open_module_windows['trial_balance']
            from .trial_balance_page import TrialBalancePageWidget
            widget = get_standalone_page_widget(window)
            if isinstance(widget, TrialBalancePageWidget) and hasattr(widget, 'refresh'):
                widget.refresh()
            elif widget is not None:
                page = widget.findChild(TrialBalancePageWidget)
                if page and hasattr(page, 'refresh'):
                    page.refresh()
            self._center_and_show_window(window, fallback_size=(1300, 720))
            return

        import_start = time.time()
        from .trial_balance_page import TrialBalancePageWidget
        import_end = time.time()

        widget = TrialBalancePageWidget(self.db)
        widget.refresh()
        window = StandaloneModuleWindow(
            widget, "Trial Balance", self, memory_key="trial_balance"
        )
        window.setMinimumSize(1300, 720)

        window.destroyed.connect(lambda: self._on_module_window_closed('trial_balance'))
        self._center_and_show_window(window, fallback_size=(1300, 720))
        self._open_module_windows['trial_balance'] = window

        load_time = import_end - import_start
        self._page_load_times['trial_balance'] = load_time
        print(f"[PERF] First Trial Balance open: {load_time:.3f} sec")

    def show_profit_loss(self):
        """Open Profit & Loss Account as standalone window (lazy loaded)."""
        from config import active_company_manager
        
        company_id = active_company_manager.get_active_company_id()
        if not company_id:
            QMessageBox.warning(self, "No Company", "Please open a company first.")
            return

        if 'profit_loss' in self._open_module_windows:
            window = self._open_module_windows['profit_loss']
            from .profit_loss_page import ProfitLossPageWidget
            widget = self._resolve_module_page_widget(window, ProfitLossPageWidget)
            if widget and hasattr(widget, '_load_data'):
                widget._load_data()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from .profit_loss_page import ProfitLossPageWidget
        import_end = time.time()

        widget = ProfitLossPageWidget(self.db)
        window = StandaloneModuleWindow(widget, "Profit & Loss Account", self)
        window.setMinimumSize(1200, 700)
        window.resize(1200, 700)

        window.destroyed.connect(lambda: self._on_module_window_closed('profit_loss'))
        self._center_and_show_window(window)
        self._open_module_windows['profit_loss'] = window

        load_time = import_end - import_start
        self._page_load_times['profit_loss'] = load_time
        print(f"[PERF] First Profit & Loss open: {load_time:.3f} sec")

    def show_balance_sheet(self):
        """Open Balance Sheet page as standalone window."""
        if 'balance_sheet' in self._open_module_windows:
            window = self._open_module_windows['balance_sheet']
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from .balance_sheet_page import BalanceSheetPageWidget
        import_end = time.time()

        widget = BalanceSheetPageWidget(self.db)
        window = StandaloneModuleWindow(widget, "Balance Sheet", self)
        window.setMinimumSize(1200, 700)
        window.resize(1200, 700)

        window.destroyed.connect(lambda: self._on_module_window_closed('balance_sheet'))
        self._center_and_show_window(window)
        self._open_module_windows['balance_sheet'] = window

        load_time = import_end - import_start
        self._page_load_times['balance_sheet'] = load_time
        print(f"[PERF] First Balance Sheet open: {load_time:.3f} sec")

    def show_stock_report(self):
        """Open stock report as standalone window (lazy loaded)."""
        # Check if window already exists
        if 'stock_report' in self._open_module_windows:
            window = self._open_module_windows['stock_report']
            # Refresh stock report when focusing existing window
            from .stock_report_page import StockReportPageWidget
            widget = self._resolve_module_page_widget(window, StockReportPageWidget)
            if widget and hasattr(widget, 'refresh_report'):
                widget.refresh_report()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        # Lazy import: load heavy module only when needed
        import_start = time.time()
        from .stock_report_page import StockReportPageWidget
        import_end = time.time()

        widget = StockReportPageWidget(db=self.db)
        widget.refresh_report()
        window = StandaloneModuleWindow(widget, "Stock Report", self)
        window.setMinimumSize(1000, 600)

        window.destroyed.connect(lambda: self._on_module_window_closed('stock_report'))
        self._center_and_show_window(window)
        self._open_module_windows['stock_report'] = window

        load_time = import_end - import_start
        self._page_load_times['stock_report'] = load_time
        print(f"[PERF] First Stock Report open: {load_time:.3f} sec")

    def show_stock_value(self):
        """Open Stock Value as standalone window (lazy loaded)."""
        if 'stock_value' in self._open_module_windows:
            window = self._open_module_windows['stock_value']
            from .stock_value_page import StockValuePageWidget
            widget = self._resolve_module_page_widget(window, StockValuePageWidget)
            if widget and hasattr(widget, 'refresh'):
                widget.refresh()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from .stock_value_page import StockValuePageWidget
        import_end = time.time()

        widget = StockValuePageWidget(db=self.db)
        window = StandaloneModuleWindow(widget, "Stock Value", self)
        window.setMinimumSize(1000, 600)

        window.destroyed.connect(lambda: self._on_module_window_closed('stock_value'))
        self._center_and_show_window(window)
        self._open_module_windows['stock_value'] = window

        load_time = import_end - import_start
        self._page_load_times['stock_value'] = load_time
        print(f"[PERF] First Stock Value open: {load_time:.3f} sec")

    def show_day_book(self):
        """Open Day Book."""
        self._open_book_window(
            "day_book",
            "Day Book",
            "ui.day_book_page",
            "DayBookPageWidget",
        )

    def show_cash_book(self):
        """Open Cash Book."""
        self._open_book_window(
            "cash_book",
            "Cash Book",
            "ui.cash_book_page",
            "CashBookWidget",
        )

    def show_pdc_book(self):
        """Open PDC Book."""
        if "pdc_book" in self._open_module_windows:
            window = self._open_module_windows["pdc_book"]
            widget = get_standalone_page_widget(window)
            if widget and hasattr(widget, "refresh"):
                widget.refresh()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from ui.pdc_book_page import PDCBookPageWidget
        import_end = time.time()

        widget = PDCBookPageWidget(self.db)
        widget.pdc_entry_requested.connect(self.open_pdc_entry_from_book)
        window = StandaloneModuleWindow(widget, "PDC Book", self)
        self._center_and_show_window(window)

        window.destroyed.connect(lambda: self._on_module_window_closed("pdc_book"))
        self._center_and_show_window(window)
        self._open_module_windows["pdc_book"] = window

        load_time = import_end - import_start
        self._page_load_times["pdc_book"] = load_time
        print(f"[PERF] First PDC Book open: {load_time:.3f} sec")

    def show_journal_book(self):
        """Open Journal Book."""
        if "journal_book" in self._open_module_windows:
            window = self._open_module_windows["journal_book"]
            widget = get_standalone_page_widget(window)
            if widget and hasattr(widget, "refresh"):
                widget.refresh()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from ui.journal_book_page import JournalBookPageWidget
        import_end = time.time()

        widget = JournalBookPageWidget(self.db)
        widget.journal_entry_requested.connect(self.open_journal_entry_from_book)
        window = StandaloneModuleWindow(widget, "Journal Book", self)
        self._center_and_show_window(window)

        window.destroyed.connect(lambda: self._on_module_window_closed("journal_book"))
        self._center_and_show_window(window)
        self._open_module_windows["journal_book"] = window

        load_time = import_end - import_start
        self._page_load_times["journal_book"] = load_time
        print(f"[PERF] First Journal Book open: {load_time:.3f} sec")

    def show_daily_stock_register(self):
        """Open Daily Stock Register."""
        if "daily_stock_register" in self._open_module_windows:
            window = self._open_module_windows["daily_stock_register"]
            widget = get_standalone_page_widget(window)
            if widget and hasattr(widget, "refresh"):
                widget.refresh()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from ui.daily_stock_register_page import DailyStockRegisterPageWidget
        import_end = time.time()

        widget = DailyStockRegisterPageWidget(self.db)
        window = StandaloneModuleWindow(widget, "Daily Stock Register", self)
        self._center_and_show_window(window)

        self._open_module_windows["daily_stock_register"] = window

    def show_price_list(self):
        """Open Price List / Stock View."""
        if "price_list" in self._open_module_windows:
            window = self._open_module_windows["price_list"]
            widget = get_standalone_page_widget(window)
            if widget and hasattr(widget, "load_price_list"):
                widget.load_price_list()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from ui.price_list_page import PriceListPageWidget
        import_end = time.time()

        widget = PriceListPageWidget(self.db)
        window = StandaloneModuleWindow(widget, "Price List / Stock View", self)
        self._center_and_show_window(window)

        self._open_module_windows["price_list"] = window

        window.destroyed.connect(lambda: self._on_module_window_closed("price_list"))

        load_time = import_end - import_start
        self._page_load_times["price_list"] = load_time
        print(f"[PERF] First Price List open: {load_time:.3f} sec")

    def show_stock_checker(self):
        """Open Stock Checker / Physical Stock Reconciliation."""
        if "stock_checker" in self._open_module_windows:
            window = self._open_module_windows["stock_checker"]
            widget = get_standalone_page_widget(window)
            if widget and hasattr(widget, "load_stock_data"):
                widget.load_stock_data()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from ui.stock_checker_page import StockCheckerPageWidget
        import_end = time.time()

        widget = StockCheckerPageWidget(self.db)
        window = StandaloneModuleWindow(widget, "Stock Checker / Physical Stock Reconciliation", self)
        self._center_and_show_window(window)

        self._open_module_windows["stock_checker"] = window

        window.destroyed.connect(lambda: self._on_module_window_closed("stock_checker"))

        load_time = import_end - import_start
        self._page_load_times["stock_checker"] = load_time
        print(f"[PERF] First Stock Checker open: {load_time:.3f} sec")

    def show_system_diagnostics(self):
        """Open System Diagnostics as a standalone utility window."""
        from ui.diagnostic_view import DiagnosticView

        window_key = "system_diagnostics"
        if window_key in self._open_module_windows:
            window = self._open_module_windows[window_key]
            widget = self._resolve_module_page_widget(window, DiagnosticView)
            if widget:
                widget.company_id = active_company_manager.get_active_company_id()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        company_id = active_company_manager.get_active_company_id()
        widget = DiagnosticView(self.db, company_id=company_id, parent=self)
        window = StandaloneModuleWindow(widget, "System Diagnostics", self)
        window.setMinimumSize(1000, 650)
        window.resize(1100, 720)
        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._open_module_windows[window_key] = window
        self._center_and_show_window(
            window,
            width_ratio=0.72,
            height_ratio=0.82,
            fallback_size=(1100, 720),
        )

    def show_print_settings(self):
        """Open company-scoped print settings as a standalone hub child window."""
        from ui.print_settings_dialog import PrintSettingsWidget

        window_key = "print_settings"
        company_id = active_company_manager.get_active_company_id()

        existing = self._open_module_windows.get(window_key)
        if existing is not None:
            try:
                from shiboken6 import isValid

                if not isValid(existing):
                    raise RuntimeError("stale print settings window")
                if (
                    not existing.isVisible()
                    and not self.is_module_dock_minimized(existing)
                ):
                    raise RuntimeError("hidden print settings window")
            except Exception:
                self._open_module_windows.pop(window_key, None)
                try:
                    existing.close()
                except RuntimeError:
                    pass
                existing = None

        if existing is not None:
            window = existing
            widget = get_standalone_page_widget(window)
            self._center_and_show_window(
                window,
                width_ratio=0.75,
                height_ratio=0.82,
                fallback_size=(1280, 860),
            )
            if widget is not None and hasattr(widget, "complete_initial_load"):
                QTimer.singleShot(0, widget.complete_initial_load)
            window.activateWindow()
            return

        widget = PrintSettingsWidget(parent=self, db=self.db, company_id=company_id)
        window = StandaloneModuleWindow(
            widget,
            "Print Settings",
            self,
            memory_key="print_settings",
        )
        window.setMinimumSize(1100, 720)
        window.resize(1280, 860)
        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._open_module_windows[window_key] = window
        widget.resize(1280, 860)

        presented = {"done": False}

        def _present_print_settings_window() -> None:
            """Show the print designer after preview load or safety timeout."""
            if presented["done"]:
                return
            presented["done"] = True
            self._center_and_show_window(
                window,
                width_ratio=0.75,
                height_ratio=0.82,
                fallback_size=(1280, 860),
            )
            window.activateWindow()

        # Safety reveal if preview callbacks stall on a hidden shell.
        QTimer.singleShot(3500, _present_print_settings_window)

        try:
            widget.complete_initial_load(on_ready=_present_print_settings_window)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Print Settings",
                f"Could not load print settings:\n{exc}",
            )
            _present_print_settings_window()
        else:
            from PySide6.QtWidgets import QApplication

            for _ in range(3):
                QApplication.processEvents()

    def show_audit_logs(self):
        """Open Audit Logs as a standalone utility window."""
        from ui.audit_log_view import AuditLogView

        window_key = "audit_logs"
        company_id = active_company_manager.get_active_company_id()
        if window_key in self._open_module_windows:
            window = self._open_module_windows[window_key]
            widget = self._resolve_module_page_widget(window, AuditLogView)
            if widget:
                widget.refresh_company(company_id)
            self._center_and_show_window(window)
            window.activateWindow()
            return

        widget = AuditLogView(self.db, company_id=company_id, parent=self)
        window = StandaloneModuleWindow(widget, "Audit Logs", self)
        window.setMinimumSize(1000, 650)
        window.resize(1100, 720)
        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._open_module_windows[window_key] = window
        self._center_and_show_window(
            window,
            width_ratio=0.72,
            height_ratio=0.82,
            fallback_size=(1100, 720),
        )

    def open_pdc_entry_from_book(self, pdc_type: str, pdc_id: int):
        """Open PDC entry page from PDC Book double-click."""
        print(f"[DEBUG] Opening PDC entry from book: Type={pdc_type}, ID={pdc_id}")
        # Open PDC page with the correct tab and load the specific entry
        self.show_pdc()
        # Use QTimer to ensure window is fully loaded before loading data
        QTimer.singleShot(100, lambda: self._load_pdc_data(pdc_type, pdc_id))

    def _load_pdc_data(self, pdc_type: str, pdc_id: int):
        """Load PDC data after window is ready."""
        print(f"[DEBUG] Loading PDC data: Type={pdc_type}, ID={pdc_id}")
        # Find the PDC window and load the entry
        if "pdc" in self._open_module_windows:
            window = self._open_module_windows["pdc"]
            widget = get_standalone_page_widget(window)
            if widget and hasattr(widget, 'load_pdc_for_edit'):
                tab_index = 0 if pdc_type == "RECEIPT" else 1
                print(f"[DEBUG] Calling load_pdc_for_edit with ID={pdc_id}, Tab={tab_index}")
                widget.load_pdc_for_edit(pdc_id, tab_index)
            else:
                print("[DEBUG] PDC page widget not found or missing load_pdc_for_edit")
        else:
            print(f"[DEBUG] PDC window not found in _open_module_windows")

    def open_journal_entry_from_book(self, voucher_id: int):
        """Open Journal entry page from Journal Book double-click."""
        print(f"[DEBUG] Opening Journal entry from book: ID={voucher_id}")
        # Open Journal entry page and load the specific entry
        self.show_journal_entry()
        # Use QTimer to ensure window is fully loaded before loading data
        QTimer.singleShot(100, lambda: self._load_journal_data(voucher_id))

    def _load_journal_data(self, voucher_id: int):
        """Load Journal entry data after window is ready."""
        print(f"[DEBUG] Loading Journal entry data: ID={voucher_id}")
        # Find the Journal Entry window and load the entry
        if "journal_entry" in self._open_module_windows:
            window = self._open_module_windows["journal_entry"]
            widget = get_standalone_page_widget(window)
            if widget and hasattr(widget, 'load_journal_for_edit'):
                print(f"[DEBUG] Calling load_journal_for_edit with ID={voucher_id}")
                widget.load_journal_for_edit(voucher_id)
            else:
                print("[DEBUG] Journal page widget not found or missing load_journal_for_edit")
        else:
            print(f"[DEBUG] Journal Entry window not found in _open_module_windows")

    def _center_and_show_window(self, window, width_ratio=0.9, height_ratio=0.9, fallback_size=(1200, 760)):
        """Center a standalone module window and show it, keeping saved geometry."""
        hidden_children = getattr(self, "_children_hidden_by_app_minimize", None)
        if hidden_children and window in hidden_children:
            hidden_children.remove(window)
        try:
            window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
        except RuntimeError:
            pass
        self._register_module_window(window)
        if self.is_module_dock_minimized(window):
            self.dock_restore_module_window(window)
        else:
            from ui.ui_memory import present_floating_window

            present_floating_window(
                window,
                width_ratio=width_ratio,
                height_ratio=height_ratio,
                fallback_size=fallback_size,
            )

    def show_van_entry(self):
        """Open Van Entry as a standalone window."""
        window_key = "van_entry"
        if window_key in self._open_module_windows:
            window = self._open_module_windows[window_key]
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from .van_entry_page import VanEntryWidget
        import_end = time.time()

        widget = VanEntryWidget(self.db)
        window = StandaloneModuleWindow(widget, "Van Entry / Van Load Entry", self)
        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._open_module_windows[window_key] = window
        self._center_and_show_window(window, width_ratio=0.65, height_ratio=0.85, fallback_size=(800, 600))

        load_time = import_end - import_start
        self._page_load_times[window_key] = load_time
        print(f"[PERF] First Van Entry open: {load_time:.3f} sec")

    def show_van_return(self):
        """Open Van Return Entry as a standalone window."""
        window_key = "van_return"
        if window_key in self._open_module_windows:
            window = self._open_module_windows[window_key]
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        from .van_return_page import VanReturnWidget
        import_end = time.time()

        widget = VanReturnWidget(self.db)
        window = StandaloneModuleWindow(widget, "Van Return Entry / Van Settlement", self)
        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._open_module_windows[window_key] = window
        self._center_and_show_window(window, width_ratio=0.65, height_ratio=0.85, fallback_size=(800, 600))

        load_time = import_end - import_start
        self._page_load_times[window_key] = load_time
        print(f"[PERF] First Van Return Entry open: {load_time:.3f} sec")

    def show_opening_balance(self):
        """Open Opening Balance as standalone window (singleton).

        Handles re-open safely: if the window was closed (hidden) it gets
        re-shown; if the underlying C++ object was destroyed a fresh window
        is created.
        """
        window_key = 'opening_balance_singleton'

        if window_key in self._open_module_windows:
            window = self._open_module_windows[window_key]
            # Guard against C++ object deleted but Python ref still alive
            try:
                from shiboken6 import Shiboken
                alive = Shiboken.isValid(window)
            except Exception:
                alive = True  # Assume alive if shiboken not available
            if alive:
                self._center_and_show_window(window)
                window.activateWindow()
                return
            else:
                # Stale reference — remove and recreate
                del self._open_module_windows[window_key]

        import_start = time.time()
        from .opening_balance_page import OpeningBalanceWidget
        import_end = time.time()

        widget = OpeningBalanceWidget(self.db)

        window = StandaloneModuleWindow(widget, "Opening Balance", self)
        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._open_module_windows[window_key] = window
        self._center_and_show_window(window, width_ratio=0.75, height_ratio=0.85, fallback_size=(900, 700))

        load_time = import_end - import_start
        self._page_load_times[window_key] = load_time
        print(f"[PERF] First Opening Balance open: {load_time:.3f} sec")

    def show_opening_stock_entry(self):
        """Open Opening Balance focused on the stock grid (singleton)."""
        window_key = 'opening_balance_singleton'

        if window_key in self._open_module_windows:
            window = self._open_module_windows[window_key]
            try:
                from shiboken6 import Shiboken
                alive = Shiboken.isValid(window)
            except Exception:
                alive = True
            if alive:
                widget = get_standalone_page_widget(window)
                if widget is not None and hasattr(widget, 'focus_stock_section'):
                    widget.focus_stock_section()
                self._center_and_show_window(window)
                window.activateWindow()
                return
            del self._open_module_windows[window_key]

        import_start = time.time()
        from .opening_balance_page import OpeningBalanceWidget
        import_end = time.time()

        widget = OpeningBalanceWidget(self.db)
        widget.focus_stock_section()

        window = StandaloneModuleWindow(widget, "Opening Stock Entry", self)
        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._open_module_windows[window_key] = window
        self._center_and_show_window(window, width_ratio=0.75, height_ratio=0.85, fallback_size=(900, 700))

        load_time = import_end - import_start
        self._page_load_times[window_key] = load_time
        print(f"[PERF] First Opening Stock Entry open: {load_time:.3f} sec")

    def show_stock_adjustment(self):
        """Open Stock Adjustment as standalone window (singleton)."""
        window_key = 'stock_adjustment_singleton'

        if window_key in self._open_module_windows:
            window = self._open_module_windows[window_key]
            try:
                from shiboken6 import Shiboken
                alive = Shiboken.isValid(window)
            except Exception:
                alive = True
            if alive:
                self._center_and_show_window(window)
                window.activateWindow()
                return
            else:
                del self._open_module_windows[window_key]

        import_start = time.time()
        from .stock_adjustment_page import StockAdjustmentWidget
        import_end = time.time()

        widget = StockAdjustmentWidget(self.db)
        
        window = StandaloneModuleWindow(widget, "Stock Adjustment", self)
        window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
        self._open_module_windows[window_key] = window
        self._center_and_show_window(window, width_ratio=0.85, height_ratio=0.9, fallback_size=(1100, 750))

        load_time = import_end - import_start
        self._page_load_times[window_key] = load_time
        print(f"[PERF] First Stock Adjustment open: {load_time:.3f} sec")

    def show_sales_return(self):
        """Open sales return as standalone window (allows multiple instances, lazy loaded)."""
        # Lazy import: load heavy module only when needed
        import_start = time.time()
        from .sales_return import SalesReturnPageWidget
        import_end = time.time()

        # Sales Return allows multiple concurrent windows
        # Track all open sales return windows with numbered keys
        sales_return_windows = [k for k in self._open_module_windows.keys() if k.startswith('sales_return_')]
        next_num = len(sales_return_windows) + 1
        window_key = f'sales_return_{next_num}'

        # Create widget and window
        widget = SalesReturnPageWidget(self, self.db)

        # Determine window title
        if next_num == 1:
            title = "Sales Return"
        else:
            title = f"Sales Return ({next_num})"

        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window)

        # Clean up when window closes
        window.destroyed.connect(lambda: self._on_sales_return_window_closed(window_key))

        # Show window
        self._center_and_show_window(window)

        # Track window
        self._open_module_windows[window_key] = window

        # Performance logging (only for first window)
        if next_num == 1:
            load_time = time.time() - import_start
            self._page_load_times['sales_return'] = load_time
            print(f"[PERF] First Sales Return open total: {load_time:.3f} sec")

    def _on_sales_return_window_closed(self, window_key):
        """Clean up tracking when a Sales Return window is closed."""
        if window_key in self._open_module_windows:
            del self._open_module_windows[window_key]

    def show_purchase_return(self):
        """Open purchase return as standalone window (allows multiple instances, lazy loaded)."""
        # Lazy import: load heavy module only when needed
        import_start = time.time()
        from .purchase_return import PurchaseReturnPageWidget
        import_end = time.time()

        # Purchase Return allows multiple concurrent windows
        # Track all open purchase return windows with numbered keys
        purchase_return_windows = [k for k in self._open_module_windows.keys() if k.startswith('purchase_return_')]
        next_num = len(purchase_return_windows) + 1
        window_key = f'purchase_return_{next_num}'

        # Create widget and window
        widget = PurchaseReturnPageWidget(self, self.db)

        # Determine window title
        if next_num == 1:
            title = "Purchase Return"
        else:
            title = f"Purchase Return ({next_num})"

        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window)

        # Clean up when window closes
        window.destroyed.connect(lambda: self._on_purchase_return_window_closed(window_key))

        # Show window
        self._center_and_show_window(window)

        # Track window
        self._open_module_windows[window_key] = window

        # Performance logging (only for first window)
        if next_num == 1:
            load_time = time.time() - import_start
            self._page_load_times['purchase_return'] = load_time
            print(f"[PERF] First Purchase Return open total: {load_time:.3f} sec")

    def _on_purchase_return_window_closed(self, window_key):
        """Clean up tracking when a Purchase Return window is closed."""
        if window_key in self._open_module_windows:
            del self._open_module_windows[window_key]
    

    def _open_book_window(self, window_key, title, import_path, class_name):
        """Open a Books report page as a standalone window."""
        window = self._get_tracked_module_window(window_key)
        if window is not None:
            widget = get_standalone_page_widget(window)
            if widget and hasattr(widget, "refresh") and not getattr(widget, "_loading", False):
                widget.refresh()
            self._center_and_show_window(window)
            window.activateWindow()
            return

        import_start = time.time()
        module = __import__(import_path, fromlist=[class_name])
        widget_class = getattr(module, class_name)
        import_end = time.time()

        try:
            widget = widget_class(self.db)
            window = StandaloneModuleWindow(widget, title, self)
            self._center_and_show_window(window)
            window.destroyed.connect(lambda: self._on_module_window_closed(window_key))
            self._center_and_show_window(window)
            window.activateWindow()
            self._open_module_windows[window_key] = window
            load_time = import_end - import_start
            self._page_load_times[window_key] = load_time
            print(f"[PERF] First {title} open: {load_time:.3f} sec")
        except Exception as exc:
            print(f"[ERROR] Failed to open {title}: {exc}")
            traceback.print_exc()
            QMessageBox.critical(self, "Open Failed", f"Could not open {title}:\n{exc}")

    def show_sales_book(self):
        """Open Sales Book."""
        self._open_book_window(
            "sales_book",
            "Sales Book",
            "ui.sales_book_page",
            "SalesBookPageWidget",
        )

    def show_ledger_statement(self):
        """Open read-only Ledger Statement page."""
        self._open_book_window(
            "ledger_statement",
            "Statement of Account",
            "ui.ledger_statement_page",
            "LedgerStatementPageWidget",
        )

    def show_bill_history(self):
        """Open Bill History management grid."""
        self._open_book_window(
            "bill_history",
            "Bill History & Management",
            "ui.bill_history_page",
            "BillHistoryPageWidget",
        )

    def show_cash_tender_history(self):
        """Open the read-only Cash Tender History grid."""
        self._open_book_window(
            "cash_tender_history",
            "Cash Tender History",
            "ui.cash_tender_history_page",
            "CashTenderHistoryPageWidget",
        )

    def show_sales_profit_book(self):
        """Open Sales Wise Profit Book."""
        self._open_book_window(
            "sales_profit_book",
            "Sales Wise Profit Book",
            "ui.sales_profit_book_page",
            "SalesProfitBookPageWidget",
        )

    def show_monthly_analysis(self):
        """Open Monthly Analysis."""
        self._open_book_window(
            "monthly_analysis",
            "Monthly Analysis",
            "ui.monthly_analysis_page",
            "MonthlyAnalysisWidget",
        )

    def show_quotation_book(self):
        """Open Quotation Book."""
        self._open_book_window(
            "quotation_book",
            "Quotation Book",
            "ui.quotation_book_page",
            "QuotationBookPageWidget",
        )

    def show_sales_return_book(self):
        """Open Sales Return Book."""
        self._open_book_window(
            "sales_return_book",
            "Sales Return Book",
            "ui.sales_return_book_page",
            "SalesReturnBookPageWidget",
        )

    def show_purchase_book(self):
        """Open Purchase Book."""
        self._open_book_window(
            "purchase_book",
            "Purchase Book",
            "ui.purchase_book_page",
            "PurchaseBookPageWidget",
        )

    def show_purchase_order_book(self):
        """Open Purchase Order Book register."""
        self._open_book_window(
            "purchase_order_book",
            "Purchase Order Book",
            "ui.purchase_order_book",
            "PurchaseOrderBookUI",
        )

    def show_purchase_return_book(self):
        """Open Purchase Return Book."""
        self._open_book_window(
            "purchase_return_book",
            "Purchase Return Book",
            "ui.purchase_return_book_page",
            "PurchaseReturnBookPageWidget",
        )

    def show_cash_receipt(self):
        """Open Cash Receipt voucher."""
        self._open_book_window(
            "cash_receipt",
            "Cash Receipt",
            "ui.cash_receipt_page",
            "CashReceiptPageWidget",
        )

    def show_cash_payment(self):
        """Open Cash Payment voucher."""
        self._open_book_window(
            "cash_payment",
            "Cash Payment",
            "ui.cash_payment_page",
            "CashPaymentPageWidget",
        )

    def show_bank_receipt(self):
        """Open Bank Receipt voucher."""
        self._open_book_window(
            "bank_receipt",
            "Bank Receipt",
            "ui.bank_receipt_page",
            "BankReceiptPageWidget",
        )

    def show_bank_payment(self):
        """Open Bank Payment voucher."""
        self._open_book_window(
            "bank_payment",
            "Bank Payment",
            "ui.bank_payment_page",
            "BankPaymentPageWidget",
        )

    def show_journal_entry(self):
        """Open Journal Entry voucher."""
        self._open_book_window(
            "journal_entry",
            "Journal Entry",
            "ui.journal_entry_page",
            "JournalEntryPageWidget",
        )

    def show_gst_sales_report(self):
        """Open GST Sales Report."""
        from ui.gst_sales_report_page import GSTSalesReportPage

        widget = GSTSalesReportPage(self.db)

        # Determine window title
        title = "GST Sales Report"

        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window, fallback_size=(1200, 800))

        # Track window
        self._open_module_windows['gst_sales_report'] = window

    def show_gstr1(self):
        """Open GSTR-1 Report for GST portal upload."""
        from ui.gstr1_page import GSTR1Page

        widget = GSTR1Page(self.db)

        # Determine window title
        title = "GSTR-1 Report"

        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window, fallback_size=(1200, 800))

        # Track window
        self._open_module_windows['gstr1'] = window

    def show_gst_purchase_report(self):
        """Open GST Purchase Report."""
        from ui.gst_purchase_report_page import GSTPurchaseReportPage

        widget = GSTPurchaseReportPage(self.db)

        # Determine window title
        title = "GST Purchase Report"

        window = StandaloneModuleWindow(widget, title, self)

        self._center_and_show_window(window, fallback_size=(1200, 800))

        # Track window
        self._open_module_windows['gst_purchase_report'] = window

    def show_barcode_settings(self):
        """Open the dedicated barcode label configuration window."""
        def build_window():
            from ui.barcode_settings import BarcodeSettingsUI

            return BarcodeSettingsUI(parent=self, db=self.db)

        try:
            self._present_non_modal_window(
                "barcode_settings",
                build_window,
                fallback_size=(900, 700),
                width_ratio=0.75,
                height_ratio=0.82,
            )
        except Exception as exc:
            QMessageBox.warning(
                self, "Barcode Settings", f"Could not open barcode settings: {exc}"
            )

    def show_barcode_print_queue(self):
        """Open the barcode print queue from Utilities."""
        if "barcode_print_queue" in self._open_module_windows:
            window = self._open_module_windows["barcode_print_queue"]
            window.resize(1050, 680)
            self._center_and_show_window(
                window,
                width_ratio=0.82,
                height_ratio=0.85,
                fallback_size=(1050, 680),
            )
            return

        try:
            from ui.barcode_manager import BarcodeManagerWindow

            widget = BarcodeManagerWindow(parent=None, db=self.db)
            window = StandaloneModuleWindow(widget, "Barcode Print Queue", self)
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            window.setMinimumSize(1000, 650)
            window.resize(1050, 680)
            original_close_event = window.closeEvent

            def barcode_close_event(event):
                """Clear transient lookup UI before the utility shell closes."""
                try:
                    widget.reset_product_lookup_state()
                except Exception:
                    pass
                original_close_event(event)

            window.closeEvent = barcode_close_event
            window.destroyed.connect(
                lambda: self._on_module_window_closed("barcode_print_queue")
            )
            self._open_module_windows["barcode_print_queue"] = window
            self._center_and_show_window(
                window,
                width_ratio=0.82,
                height_ratio=0.85,
                fallback_size=(1050, 680),
            )
        except Exception as exc:
            QMessageBox.warning(
                self, "Barcode Print Queue", f"Could not open barcode print queue: {exc}"
            )

    def open_global_settings_dialog(self, initial_section: str | None = None):
        """Open the global settings window for color mode and appearance."""
        section = initial_section or "color_mode"

        def build_window():
            from ui.settings_dialog import GlobalSettingsDialog

            return GlobalSettingsDialog(
                master_db_path=self._master_registry_db_path(),
                parent=self,
                initial_section=section,
            )

        def focus_section(window) -> None:
            if hasattr(window, "_show_section"):
                window._show_section(section)

        self._present_non_modal_window(
            "general_settings",
            build_window,
            on_existing=focus_section,
            fallback_size=(860, 720),
            width_ratio=0.75,
            height_ratio=0.82,
        )

    def show_invoice_settings(self, initial_section: str | None = None):
        """Open invoice settings as a non-modal window with persisted geometry."""
        section = initial_section or "invoice_settings"

        def build_window():
            from ui import theme
            from ui.settings import SettingsWidget
            from ui.ui_memory import MemoryHostedDialog

            settings_widget = SettingsWidget(db=self.db, initial_section=section)
            dialog = MemoryHostedDialog(
                settings_widget,
                title="Invoice Settings",
                memory_key="invoice_settings",
                parent=self,
                minimum_size=(860, 720),
            )
            dialog.setStyleSheet(theme.dialog_page_style())
            return dialog

        def focus_section(window) -> None:
            layout = window.layout()
            if layout is None or layout.count() <= 0:
                return
            content = layout.itemAt(0).widget()
            if content is not None and hasattr(content, "_show_section"):
                content._show_section(section)

        self._present_non_modal_window(
            "invoice_settings",
            build_window,
            on_existing=focus_section,
            fallback_size=(860, 720),
            width_ratio=0.75,
            height_ratio=0.82,
        )

    def show_tax_settings(self):
        """Open product/tax field settings as a non-modal window."""
        def build_window():
            from ui.product_settings_dialog import ProductSettingsDialog

            dialog = ProductSettingsDialog(
                parent=self,
                db=self.db,
                memory_key="tax_settings",
            )
            dialog.setWindowTitle("Tax Settings")
            return dialog

        self._present_non_modal_window(
            "tax_settings",
            build_window,
            fallback_size=(560, 620),
            width_ratio=0.55,
            height_ratio=0.75,
        )

    def show_settings(self):
        """Backward-compatible alias for invoice settings."""
        self.show_invoice_settings()

    def show_user_management(self):
        """Open Admin-only user management as a non-modal window."""
        if not self._is_admin_user():
            self._show_permission_denied_warning(
                "Cannot open without admin permission.",
                "Access Denied",
            )
            return

        def build_window():
            from ui.user_management import UserManagementDialog

            return UserManagementDialog(parent=self, db_path=self.db_path)

        self._present_non_modal_window(
            "user_management",
            build_window,
            fallback_size=(980, 620),
            width_ratio=0.82,
            height_ratio=0.82,
        )

    def open_voucher_for_edit(self, voucher_type: str, voucher_id: int):
        """Open voucher entry page in edit mode by voucher type and ID."""
        voucher_type_lower = voucher_type.lower().replace(" ", "_")

        if voucher_type_lower in ("sales", "sale"):
            self._open_sales_entry_for_edit(voucher_id)
        elif voucher_type_lower in ("purchase", "purchases"):
            self._open_purchase_entry_for_edit(voucher_id)
        elif voucher_type_lower in ("sales_return", "sales_returns", "return"):
            self._open_sales_return_for_edit(voucher_id)
        elif voucher_type_lower in ("purchase_return", "purchase_returns"):
            self._open_purchase_return_for_edit(voucher_id)
        elif voucher_type_lower in ("quotation", "quotations"):
            self._open_quotation_entry_for_edit(voucher_id)
        elif voucher_type_lower in ("cash_receipt", "receipt", "receipts"):
            self._open_cash_receipt_for_edit(voucher_id)
        elif voucher_type_lower in ("cash_payment", "payment", "payments"):
            self._open_cash_payment_for_edit(voucher_id)
        elif voucher_type_lower == "bank_receipt":
            self._open_bank_receipt_for_edit(voucher_id)
        elif voucher_type_lower == "bank_payment":
            self._open_bank_payment_for_edit(voucher_id)
        elif voucher_type_lower in ("journal", "journal_voucher"):
            self._open_journal_entry_for_edit(voucher_id)
        else:
            QMessageBox.warning(self, "Unsupported Voucher Type", f"Voucher type '{voucher_type}' is not supported for editing.")

    def _bring_window_to_front(self, window):
        """Bring a module window to the front with focus."""
        if not window:
            return
        try:
            self._center_and_show_window(window)
            window.activateWindow()
            QTimer.singleShot(100, lambda: (window.raise_(), window.activateWindow()))
        except Exception:
            pass

    def _open_sales_entry_for_edit(self, sale_id: int):
        """Open sales entry in edit mode."""
        from .sales_entry import SalesEntryWidget
        widget = SalesEntryWidget(db=self.db)
        widget.load_voucher(sale_id)  # Use standardized load_voucher method
        window = StandaloneModuleWindow(widget, f"Sales Entry (Edit #{sale_id})", self)
        self._center_and_show_window(window)
        self._open_module_windows[f'sales_edit_{sale_id}'] = window
        self._bring_window_to_front(window)

    def _open_purchase_entry_for_edit(self, purchase_id: int):
        """Open purchase entry in edit mode."""
        from .purchase_entry import PurchaseEntryWidget
        widget = PurchaseEntryWidget(parent=self, db=self.db)
        widget.load_voucher(purchase_id)  # Use standardized load_voucher method
        window = StandaloneModuleWindow(widget, f"Purchase Entry (Edit #{purchase_id})", self)
        self._center_and_show_window(window)
        self._open_module_windows[f'purchase_edit_{purchase_id}'] = window
        self._bring_window_to_front(window)

    def _open_sales_return_for_edit(self, return_id: int):
        """Open sales return in edit mode."""
        from .sales_return import SalesReturnPageWidget
        widget = SalesReturnPageWidget(main_window=self, db=self.db)
        widget.load_return_by_id(return_id)
        window = StandaloneModuleWindow(widget, f"Sales Return (Edit #{return_id})", self)
        self._center_and_show_window(window)
        self._open_module_windows[f'sales_return_edit_{return_id}'] = window
        self._bring_window_to_front(window)

    def _open_purchase_return_for_edit(self, return_id: int):
        """Open purchase return in edit mode."""
        from .purchase_return import PurchaseReturnPageWidget
        widget = PurchaseReturnPageWidget(main_window=self, db=self.db)
        widget.load_return_by_id(return_id)
        window = StandaloneModuleWindow(widget, f"Purchase Return (Edit #{return_id})", self)
        self._center_and_show_window(window)
        self._open_module_windows[f'purchase_return_edit_{return_id}'] = window
        self._bring_window_to_front(window)

    def _open_quotation_entry_for_edit(self, quotation_id: int):
        """Open quotation entry in edit mode."""
        from .quotation_entry import QuotationEntryWidget
        widget = QuotationEntryWidget(db=self.db)
        widget.load_quotation_by_id(quotation_id)
        window = StandaloneModuleWindow(widget, f"Quotation Entry (Edit #{quotation_id})", self)
        self._center_and_show_window(window)
        self._open_module_windows[f'quotation_edit_{quotation_id}'] = window
        self._bring_window_to_front(window)

    def _open_voucher_grid_for_edit(self, module_name: str, class_name: str, voucher_id: int, title: str, key_prefix: str):
        """Open a cash/bank voucher-grid page and load an existing voucher."""
        import importlib
        module = importlib.import_module(module_name)
        widget_class = getattr(module, class_name)
        widget = widget_class(db=self.db)
        if hasattr(widget, "load_voucher_by_id"):
            widget.load_voucher_by_id(voucher_id)
        window = StandaloneModuleWindow(widget, f"{title} (Edit #{voucher_id})", self)
        self._center_and_show_window(window, height_ratio=0.88)
        self._open_module_windows[f"{key_prefix}_edit_{voucher_id}"] = window
        self._bring_window_to_front(window)

    def _open_cash_receipt_for_edit(self, receipt_id: int):
        self._open_voucher_grid_for_edit("ui.cash_receipt_page", "CashReceiptPageWidget", receipt_id, "Cash Receipt", "cash_receipt")

    def _open_cash_payment_for_edit(self, payment_id: int):
        self._open_voucher_grid_for_edit("ui.cash_payment_page", "CashPaymentPageWidget", payment_id, "Cash Payment", "cash_payment")

    def _open_bank_receipt_for_edit(self, receipt_id: int):
        self._open_voucher_grid_for_edit("ui.bank_receipt_page", "BankReceiptPageWidget", receipt_id, "Bank Receipt", "bank_receipt")

    def _open_bank_payment_for_edit(self, payment_id: int):
        self._open_voucher_grid_for_edit("ui.bank_payment_page", "BankPaymentPageWidget", payment_id, "Bank Payment", "bank_payment")

    def _open_journal_entry_for_edit(self, journal_id: int):
        """Open journal entry in edit mode."""
        QMessageBox.information(self, "Edit Journal", f"Journal entry editing is not yet implemented.\nJournal ID: {journal_id}")
    def apply_theme(self):
        """Apply the current theme globally across the application."""
        from PySide6.QtWidgets import QApplication

        master_db_path = self._master_registry_db_path()
        self.theme_manager = get_theme_manager(master_db_path)
        self.theme_manager.sync_theme()
        colors = self.theme_manager.get_colors()

        app = QApplication.instance()
        if app is not None:
            GlobalThemeManager.apply_application_theme(app, master_db_path)

        self.stack_widget.setStyleSheet(f"""
            QStackedWidget {{
                background-color: {colors['app_bg']};
            }}
        """)

        if hasattr(self, "main_area_widget"):
            self.main_area_widget.setStyleSheet(f"""
                QWidget#mainAreaWidget {{
                    background-color: {colors['app_bg']};
                    color: {colors['input_text']};
                }}
            """)

        if hasattr(self, "topbar") and hasattr(self.topbar, "set_logout_button_style"):
            self.topbar.set_logout_button_style(self._logout_button_style())
        elif hasattr(self, "logout_btn") and self.logout_btn is not None:
            self.logout_btn.setStyleSheet(self._logout_button_style())

        if hasattr(self, "admin_controls"):
            admin_colors = colors
            self.admin_controls.setStyleSheet(f"""
                QFrame#adminControls {{
                    background-color: {admin_colors['panel_bg']};
                    border-bottom: 1px solid {admin_colors['border']};
                }}
                QLabel#adminWelcomeLabel {{
                    background: transparent;
                    border: none;
                }}
                QPushButton#manageUsersButton {{
                    background-color: {admin_colors['button_primary']};
                    color: #ffffff;
                    border: none;
                    padding: 7px 14px;
                    border-radius: 5px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                QPushButton#manageUsersButton:hover {{
                    background-color: {admin_colors['focus_border']};
                }}
            """)
            self._refresh_dashboard_welcome_label(admin_colors)

        if hasattr(self, "dashboard_widget") and hasattr(self.dashboard_widget, "refresh_theme"):
            self.dashboard_widget.refresh_theme()

        if hasattr(self.sidebar, 'refresh_theme'):
            self.sidebar.refresh_theme()
        if hasattr(self.topbar, 'refresh_theme'):
            self.topbar.refresh_theme()
        if hasattr(self, 'shortcut_toolbar') and hasattr(self.shortcut_toolbar, 'refresh_theme'):
            self.shortcut_toolbar.refresh_theme()
        if hasattr(self, "module_minimize_strip"):
            self.module_minimize_strip.refresh_theme()
            self._refresh_module_minimize_strip()

        self._refresh_qtawesome_menu_icons()
        self.refresh_theme_for_open_windows()
        self._refresh_visible_page_theme()

    def _refresh_visible_page_theme(self) -> None:
        """Refresh the currently visible workspace page after a theme change."""
        stack_widget = getattr(self, "stack_widget", None)
        if stack_widget is None:
            return

        current_widget = stack_widget.currentWidget()
        if current_widget is not None and hasattr(current_widget, "refresh_theme"):
            try:
                current_widget.refresh_theme()
            except Exception as error:
                print(f"[WARN] Could not refresh visible page theme: {error}")

    def refresh_theme_for_open_windows(self):
        """Refresh theme for all open MDI module pages."""
        for window_key, window in self._open_module_windows.items():
            try:
                if hasattr(window, "refresh_theme"):
                    window.refresh_theme()
                    continue
                page = get_standalone_page_widget(window)
                if page is not None and hasattr(page, "refresh_theme"):
                    page.refresh_theme()
            except Exception as error:
                print(f"Error refreshing theme for window {window_key}: {error}")

    def setup_global_dialog_styling(self):
        """Legacy startup hook; global styling is applied on the QApplication instance."""
        pass
    
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
