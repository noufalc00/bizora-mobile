"""
Hidden secret-company launcher used only from the gateway login logo unlock.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout

from components.menu_icons import pixmap_for_menu_icon
from ui import theme


class SecretCompanyMenuDialog(QDialog):
    """Small popup with secret create/open company actions."""

    def __init__(self, parent=None):
        """Build the compact secret company launcher dialog."""
        super().__init__(parent)
        self.setWindowTitle("Company Tools")
        self.setModal(True)
        self.setFixedSize(320, 170)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.MSWindowsFixedSizeDialogHint
        )
        self.setStyleSheet(theme.gateway_modal_dialog_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_label_button = QPushButton(self)
        icon_label_button.setObjectName("shortcutIconButton")
        icon_label_button.setEnabled(False)
        icon_label_button.setFixedSize(48, 42)
        icon_label_button.setIconSize(QSize(30, 30))
        icon_label_button.setStyleSheet(theme.shortcut_toolbar_3d_icon_button_style())
        pixmap = pixmap_for_menu_icon(
            "assets/icons/file.svg",
            QSize(30, 30),
            device_pixel_ratio=self.devicePixelRatioF(),
        )
        if pixmap is not None:
            icon_label_button.setIcon(QIcon(pixmap))
        icon_row.addWidget(icon_label_button)
        icon_row.addStretch()
        layout.addLayout(icon_row)

        self.create_button = QPushButton("Create New Company")
        self.create_button.setMinimumHeight(36)
        self.create_button.setStyleSheet(theme.master_nav_primary_button_style())
        layout.addWidget(self.create_button)

        self.open_button = QPushButton("Open Companies")
        self.open_button.setMinimumHeight(36)
        self.open_button.setStyleSheet(theme.master_nav_secondary_button_style())
        layout.addWidget(self.open_button)
