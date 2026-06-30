"""
Product / Service page settings dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import active_company_manager
from bizora_core.product_settings_logic import (
    PRODUCT_ENTER_FIELD_DEFINITIONS,
    get_product_page_settings,
    save_product_page_settings,
)
from ui import theme
from ui.book_report_common import (
    page_heading_style,
    report_dialog_body_style,
    report_group_box_style,
)
from ui.checkbox_style import create_checkbox
from ui.theme_manager import get_theme_manager, sync_theme
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin, configure_non_modal_window
from utils.theme_manager import global_theme_manager


class ProductSettingsDialog(UiMemoryMixin, QDialog):
    """Configure Product / Service entry behaviour for the active company."""

    def __init__(self, parent=None, db=None, memory_key: str = "product_settings"):
        super().__init__(parent)
        self.db = db
        self._ui_memory_geometry_key = memory_key
        self._field_checkboxes: dict[str, object] = {}
        self._build_ui()
        self._load_settings()
        self._apply_theme_styles()
        global_theme_manager.theme_changed.connect(self.refresh_theme)
        self._init_ui_memory()
        configure_non_modal_window(self, parent)

    def _build_ui(self) -> None:
        """Build the settings dialog layout."""
        self.setWindowTitle("Product / Service Settings")
        self.setMinimumSize(520, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self.title_label = QLabel("Product / Service Settings")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.title_label)

        self.help_label = QLabel(
            "Customize Enter-key navigation, duplicate product rules, and "
            "name suggestions while entering products."
        )
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)

        self.allow_duplicate_checkbox = create_checkbox(
            "Allow duplicate product",
            font_size=13,
        )
        self.allow_duplicate_checkbox.setToolTip(
            "When enabled, multiple products may share the same name. "
            "Each product still receives its own barcode."
        )
        layout.addWidget(self.allow_duplicate_checkbox)

        self.show_name_list_checkbox = create_checkbox(
            "Show product list",
            font_size=13,
        )
        self.show_name_list_checkbox.setToolTip(
            "Show matching product names under the Product Name field as you type. "
            "Names are suggestions only — selecting one starts a new product entry."
        )
        layout.addWidget(self.show_name_list_checkbox)

        self.enter_group = QGroupBox("Press Enter key jump to")
        enter_group_layout = QVBoxLayout(self.enter_group)
        enter_group_layout.setContentsMargins(12, 20, 12, 12)
        enter_group_layout.setSpacing(8)

        self.enter_help_label = QLabel(
            "Tick only the fields you want to visit when pressing Enter. "
            "Unticked fields are skipped for faster data entry."
        )
        self.enter_help_label.setWordWrap(True)
        enter_group_layout.addWidget(self.enter_help_label)

        quick_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all_fields)
        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.clicked.connect(self._clear_all_fields)
        quick_row.addWidget(self.select_all_btn)
        quick_row.addWidget(self.clear_all_btn)
        quick_row.addStretch()
        enter_group_layout.addLayout(quick_row)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_widget = QWidget()
        fields_layout = QVBoxLayout(scroll_widget)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setSpacing(6)

        for field_key, label_text in PRODUCT_ENTER_FIELD_DEFINITIONS:
            checkbox = create_checkbox(label_text, font_size=12)
            self._field_checkboxes[field_key] = checkbox
            fields_layout.addWidget(checkbox)

        fields_layout.addStretch()
        self.scroll_area.setWidget(scroll_widget)
        enter_group_layout.addWidget(self.scroll_area)
        layout.addWidget(self.enter_group, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save_settings)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(self.save_btn)
        button_row.addWidget(self.cancel_btn)
        layout.addLayout(button_row)

    def _body_label_style(self) -> str:
        """Muted body copy style for help labels."""
        colors = get_theme_manager().get_colors()
        return (
            f"color: {colors['label_text']}; "
            "font-size: 13px; "
            "background: transparent; "
            "border: none;"
        )

    def _apply_theme_styles(self) -> None:
        """Apply current light/dark theme tokens to the settings dialog."""
        sync_theme()
        colors = get_theme_manager().get_colors()
        label_color = colors["input_text"]

        self.setStyleSheet(report_dialog_body_style() + theme.scrollbar_stylesheet())
        self.title_label.setStyleSheet(page_heading_style(18))
        self.help_label.setStyleSheet(self._body_label_style())
        self.enter_group.setStyleSheet(report_group_box_style())
        self.enter_help_label.setStyleSheet(self._body_label_style())
        self.select_all_btn.setStyleSheet(theme.master_nav_secondary_button_style())
        self.clear_all_btn.setStyleSheet(theme.master_clear_button_style())
        self.save_btn.setStyleSheet(theme.master_save_button_style())
        self.cancel_btn.setStyleSheet(theme.master_clear_button_style())

        for checkbox in (
            self.allow_duplicate_checkbox,
            self.show_name_list_checkbox,
            *self._field_checkboxes.values(),
        ):
            if hasattr(checkbox, "set_label_color"):
                checkbox.set_label_color(label_color)

    def refresh_theme(self, theme_name: str | None = None) -> None:
        """Refresh dialog styling when the global theme changes."""
        if theme_name is not None:
            sync_theme(theme_name)
        self._apply_theme_styles()

    def closeEvent(self, event) -> None:
        """Disconnect theme listener when the dialog closes."""
        try:
            global_theme_manager.theme_changed.disconnect(self.refresh_theme)
        except (TypeError, RuntimeError):
            pass
        super().closeEvent(event)

    def _select_all_fields(self) -> None:
        """Enable every Enter-jump field."""
        for checkbox in self._field_checkboxes.values():
            checkbox.setChecked(True)

    def _clear_all_fields(self) -> None:
        """Disable every Enter-jump field."""
        for checkbox in self._field_checkboxes.values():
            checkbox.setChecked(False)

    def _load_settings(self) -> None:
        """Load persisted settings for the active company."""
        active_company = active_company_manager.get_active_company()
        if not active_company or not self.db:
            self.allow_duplicate_checkbox.setChecked(False)
            self.show_name_list_checkbox.setChecked(False)
            self._select_all_fields()
            return

        try:
            settings = get_product_page_settings(self.db, active_company["id"])
            self.allow_duplicate_checkbox.setChecked(bool(settings.get("allow_duplicate")))
            self.show_name_list_checkbox.setChecked(bool(settings.get("show_name_list")))
            enabled_fields = set(settings.get("enter_jump_fields") or [])
            for field_key, checkbox in self._field_checkboxes.items():
                checkbox.setChecked(field_key in enabled_fields)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Settings",
                f"Could not load product settings:\n{exc}",
            )
            self._select_all_fields()

    def _save_settings(self) -> None:
        """Validate and persist settings for the active company."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, "No Active Company", "Please open a company first.")
            return
        if not self.db:
            QMessageBox.warning(self, "Settings", "Database is not available.")
            return

        enabled_fields = [
            field_key
            for field_key, checkbox in self._field_checkboxes.items()
            if checkbox.isChecked()
        ]
        if not enabled_fields:
            QMessageBox.warning(
                self,
                "Validation",
                "Select at least one field for Enter-key navigation.",
            )
            return

        values = {
            "allow_duplicate": self.allow_duplicate_checkbox.isChecked(),
            "show_name_list": self.show_name_list_checkbox.isChecked(),
            "enter_jump_fields": enabled_fields,
        }
        try:
            saved = save_product_page_settings(self.db, active_company["id"], values)
            if not saved:
                QMessageBox.warning(self, "Settings", "Failed to save product settings.")
                return
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Settings", f"Failed to save product settings:\n{exc}")