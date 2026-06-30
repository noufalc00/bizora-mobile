#!/usr/bin/env python3
"""
Main entry point for the Accounting Desktop Application.
Uses PySide6 with Qt Widgets and SQLite database.

Startup opens the company login window first. After login, a full-screen
loading curtain is shown while the main workspace is prepared off-screen.
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from utils.backup_manager import apply_pending_restore_if_any
from utils.theme_manager import ThemeManager
from ui.ui_memory import configure_windows_process_app_user_model_id


def _apply_global_theme(app: QApplication) -> str:
    """Load and apply the saved theme before any window is shown."""
    return ThemeManager.apply_application_theme(app)


if __name__ == "__main__":
    configure_windows_process_app_user_model_id()
    restore_status, restore_message = apply_pending_restore_if_any()
    if restore_status is False:
        print(f"[RESTORE] Pending restore failed: {restore_message}")

    from ui.brand_logo import load_app_logo_icon
    from ui.company_gateway import CompanyGateway
    from ui.startup_handoff import schedule_handoff
    from ui.ui_memory import present_floating_window

    app = QApplication(sys.argv)
    app_icon = load_app_logo_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    _apply_global_theme(app)

    gateway = CompanyGateway()
    app.gateway = gateway
    if not app_icon.isNull():
        gateway.setWindowIcon(app_icon)

    gateway.authenticated.connect(
        lambda db_path, company_name, username, role: schedule_handoff(
            app,
            gateway,
            db_path,
            company_name,
            username,
            role,
        )
    )

    present_floating_window(
        gateway,
        width_ratio=0.9,
        height_ratio=0.9,
        fallback_size=(900, 700),
    )
    gateway.setWindowState(gateway.windowState() & ~Qt.WindowState.WindowMinimized)
    sys.exit(app.exec())
