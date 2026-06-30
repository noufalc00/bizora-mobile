"""
Company-scoped print settings screen for invoice defaults.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import COLORS, active_company_manager
from db import Database
from bizora_core.print_settings_logic import get_print_settings, save_print_settings
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin


class PrintSettingsView(UiMemoryMixin, QWidget):
    """Settings screen for global invoice print defaults scoped by company."""

    def __init__(
        self,
        db: Optional[Database] = None,
        company_id: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the screen with an explicit or active company id."""
        super().__init__(parent)
        self.db = db or Database()
        self.company_id = company_id or active_company_manager.get_active_company_id()
        self._build_ui()
        if self.company_id:
            self.load_settings()
        self._init_ui_memory(restore_geometry=False, save_geometry=False)

    def refresh_company(self, company_id: Optional[int]) -> None:
        """Switch the screen to another active company and reload settings."""
        self.company_id = company_id
        self.load_settings()

    def _build_ui(self) -> None:
        """Build the print settings form."""
        self.setObjectName("PrintSettingsView")
        self.setStyleSheet(f"""
            QWidget#PrintSettingsView {{
                background-color: {COLORS['background']};
                color: {COLORS['text_primary']};
            }}
            QLabel {{
                color: {COLORS['text_primary']};
                font-size: 13px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Print Settings")
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['primary']};
                font-size: 22px;
                font-weight: bold;
            }}
        """)
        root.addWidget(title)

        form_frame = QFrame()
        form_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 16px;
            }}
        """)
        grid = QGridLayout(form_frame)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        self.default_format = self._combo(["A4", "Thermal"])
        self.default_theme = self._combo(["Classic", "Modern Pink"])
        self.header_quote = self._text_edit("Header quotes, offers, or promotional text")
        self.footer_terms = self._text_edit("Footer terms and conditions")

        grid.addWidget(self._label("Default Print Format"), 0, 0)
        grid.addWidget(self.default_format, 0, 1)
        grid.addWidget(self._label("Default Theme"), 1, 0)
        grid.addWidget(self.default_theme, 1, 1)
        grid.addWidget(self._label("Header Quotes / Offers"), 2, 0, Qt.AlignTop)
        grid.addWidget(self.header_quote, 2, 1)
        grid.addWidget(self._label("Footer Terms & Conditions"), 3, 0, Qt.AlignTop)
        grid.addWidget(self.footer_terms, 3, 1)

        root.addWidget(form_frame)

        actions = QHBoxLayout()
        actions.addStretch()
        self.reload_button = QPushButton("Reload")
        self.save_button = QPushButton("Save Settings")
        self.reload_button.clicked.connect(self.load_settings)
        self.save_button.clicked.connect(self.save_settings)
        actions.addWidget(self.reload_button)
        actions.addWidget(self.save_button)
        root.addLayout(actions)
        root.addStretch()

    def _label(self, text: str) -> QLabel:
        """Return a styled field label."""
        label = QLabel(text)
        label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                font-weight: bold;
            }}
        """)
        return label

    def _combo(self, items: list) -> QComboBox:
        """Return a styled dropdown."""
        combo = QComboBox()
        combo.addItems(items)
        combo.setMinimumHeight(34)
        combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['background']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 7px;
            }}
        """)
        return combo

    def _text_edit(self, placeholder: str) -> QTextEdit:
        """Return a styled multiline text box."""
        text_edit = QTextEdit()
        text_edit.setPlaceholderText(placeholder)
        text_edit.setMinimumHeight(100)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['background']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        return text_edit

    def load_settings(self) -> None:
        """Load print defaults for the selected company."""
        if not self.company_id:
            QMessageBox.warning(self, "Print Settings", "Please open a company first.")
            return

        try:
            settings = get_print_settings(self.db, self.company_id)
        except sqlite3.Error as e:
            print(f"Database Error: {e}")
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to load print settings.\nError: {str(e)}",
            )
            return
        except Exception as e:
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to load print settings.\nError: {str(e)}",
            )
            return
        self.default_format.setCurrentText(settings.get("default_format", "A4") or "A4")
        theme = settings.get("default_theme", "Classic") or "Classic"
        if theme == "Modern":
            theme = "Modern Pink"
        self.default_theme.setCurrentText(theme)
        self.header_quote.setPlainText(settings.get("header_quote", "") or "")
        self.footer_terms.setPlainText(settings.get("footer_terms", "") or "")

    def save_settings(self) -> None:
        """Persist print defaults for the selected company."""
        if not self.company_id:
            QMessageBox.warning(self, "Print Settings", "Please open a company first.")
            return

        try:
            success = save_print_settings(
                self.db,
                self.company_id,
                default_format=self.default_format.currentText(),
                default_theme=self.default_theme.currentText(),
                header_quote=self.header_quote.toPlainText().strip(),
                footer_terms=self.footer_terms.toPlainText().strip(),
            )
        except sqlite3.Error as e:
            print(f"Database Error: {e}")
            QMessageBox.critical(self, "Save Error", f"Failed to save settings.\nError: {str(e)}")
            return
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save settings.\nError: {str(e)}")
            return

        if success:
            QMessageBox.information(self, "Print Settings", "Print settings saved successfully.")
        else:
            QMessageBox.critical(self, "Print Settings", "Could not save print settings.")