"""
Settings widget for the Accounting Desktop Application.
Manages company invoice numbering, cash tender, and operational options.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from db import Database
from ui.checkbox_style import create_checkbox
from ui.settings_page_common import (
    apply_settings_page_styles,
    build_settings_content_stack,
    build_settings_footer_bar,
    build_settings_header,
    build_settings_page_shell,
    build_settings_section_nav,
    theme_colors,
)
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin
from bizora_core.invoice_numbering import (
    INVOICE_PREFIX_KEY,
    VOUCHER_PREFIX_LABELS,
    VOUCHER_PREFIX_SETTINGS,
)
from bizora_core.entry_type_defaults import (
    DEFAULT_ENTRY_TYPE_KEY,
    ENTRY_TYPE_SETTINGS,
    ENTRY_TYPE_VOUCHERS,
    normalize_entry_type,
)
from bizora_core.settings_logic import get_settings, save_settings


class SettingsWidget(UiMemoryMixin, QWidget):
    """Company settings for voucher numbering and operational preferences."""

    SECTIONS = (
        ("cash_tender", "Cash Tender"),
        ("invoice_numbering", "Invoice Numbering"),
        ("other_options", "Other Options"),
        ("layout_memory", "Window & Layout"),
    )

    def __init__(self, db=None, parent=None, initial_section: str | None = None):
        """Initialize the settings widget with the active application database."""
        super().__init__(parent)
        self.setObjectName("InvoiceSettingsPage")
        self.db = db or Database()
        self._initial_section = initial_section or "cash_tender"
        self.prefix_inputs = {}
        self.entry_type_inputs = {}
        self.section_buttons = {}
        self.setup_ui()
        self._apply_page_styles()
        self._show_section(self._initial_section)
        self._init_ui_memory()
        self.load_general_settings()

    def setup_ui(self):
        """Build the settings page with left navigation and section pages."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 14)
        root_layout.setSpacing(14)

        self.title_label, self.subtitle_label = build_settings_header(
            root_layout,
            "Invoice Settings",
            "Choose a section on the left to configure invoice and operational settings.",
        )

        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)
        nav_frame, self.section_buttons, self.section_button_group = (
            build_settings_section_nav(self, self.SECTIONS, self._show_section)
        )
        content_frame, self.section_stack = build_settings_content_stack()
        self.section_stack.addWidget(self._build_cash_tender_page())
        self.section_stack.addWidget(self._build_invoice_numbering_page())
        self.section_stack.addWidget(self._build_other_options_page())
        self.section_stack.addWidget(self._build_layout_memory_page())
        body_layout.addWidget(nav_frame)
        body_layout.addWidget(content_frame, 1)
        root_layout.addLayout(body_layout, 1)

        self.footer_frame, self.save_btn, self.cancel_btn = build_settings_footer_bar(
            "Save Settings",
            self.save_settings,
            self.close_settings_dialog,
        )
        root_layout.addWidget(self.footer_frame)

    def _build_cash_tender_page(self) -> QWidget:
        """Create the cash tender settings page."""
        page, layout = build_settings_page_shell(
            "Cash Tender",
            "When enabled, Sales Entry opens the cash received and balance return "
            "dialog after a bill is saved.",
        )
        colors = theme_colors()
        self.cash_tender_checkbox = create_checkbox(
            "Enable Cash Tender Window on Sales Save",
            label_color=colors["input_text"],
            font_size=13,
            spacing=8,
        )
        layout.addWidget(self.cash_tender_checkbox)
        layout.addStretch()
        return page

    def _build_invoice_numbering_page(self) -> QWidget:
        """Create the invoice prefix and entry-type settings page."""
        page, layout = build_settings_page_shell(
            "Invoice Numbering",
            "Set a prefix and default entry type for each voucher screen. "
            "Blank prefixes use the default values below. "
            "Entry type applies only to Cash/Credit screens. "
            "All numbers use a 3-digit sequence such as 001, 002, 003.",
        )

        form_frame = QFrame()
        form_frame.setObjectName("settingsFormFrame")
        form_layout = QGridLayout(form_frame)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setHorizontalSpacing(14)
        form_layout.setVerticalSpacing(10)
        form_layout.setColumnStretch(0, 0)
        form_layout.setColumnStretch(1, 1)
        form_layout.setColumnStretch(2, 0)

        entry_header = QLabel("Entry")
        prefix_header = QLabel("Prefix")
        type_header = QLabel("Entry Type")
        for header in (entry_header, prefix_header, type_header):
            header.setObjectName("settingsGridHeader")
        form_layout.addWidget(entry_header, 0, 0)
        form_layout.addWidget(prefix_header, 0, 1)
        form_layout.addWidget(type_header, 0, 2)

        row = 1
        for voucher_type, label_text in VOUCHER_PREFIX_LABELS.items():
            self._add_numbering_form_row(form_layout, row, voucher_type, label_text)
            row += 1

        default_label = QLabel("Default")
        default_label.setObjectName("settingsDefaultLabel")
        self.invoice_prefix_input = QLineEdit()
        self.invoice_prefix_input.setPlaceholderText("Used when an entry prefix is blank")
        self.invoice_prefix_input.setMaxLength(20)
        self.invoice_prefix_input.setMinimumWidth(220)
        self.default_entry_type_combo = QComboBox()
        self.default_entry_type_combo.addItems(["Cash", "Credit"])
        self.default_entry_type_combo.setFixedWidth(130)
        form_layout.addWidget(default_label, row, 0)
        form_layout.addWidget(self.invoice_prefix_input, row, 1)
        form_layout.addWidget(self.default_entry_type_combo, row, 2)

        layout.addWidget(form_frame)
        layout.addStretch()
        return page

    def _add_numbering_form_row(
        self,
        grid: QGridLayout,
        row: int,
        voucher_type: str,
        label_text: str,
    ) -> None:
        """Add one clean numbering row to the invoice settings form."""
        label = QLabel(label_text)
        label.setObjectName("settingsEntryLabel")

        prefix_edit = QLineEdit()
        prefix_edit.setPlaceholderText("e.g. SL-")
        prefix_edit.setMaxLength(20)
        prefix_edit.setMinimumWidth(220)
        prefix_edit.setMinimumHeight(34)
        self.prefix_inputs[voucher_type] = prefix_edit

        grid.addWidget(label, row, 0)
        grid.addWidget(prefix_edit, row, 1)

        if voucher_type in ENTRY_TYPE_VOUCHERS:
            type_combo = QComboBox()
            type_combo.addItems(["Cash", "Credit"])
            type_combo.setFixedWidth(130)
            type_combo.setMinimumHeight(34)
            self.entry_type_inputs[voucher_type] = type_combo
            grid.addWidget(type_combo, row, 2)
            return

        not_applicable = QLabel("Not applicable")
        not_applicable.setObjectName("settingsMutedLabel")
        not_applicable.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(not_applicable, row, 2)

    def _build_other_options_page(self) -> QWidget:
        """Create the other options settings page."""
        page, layout = build_settings_page_shell(
            "Other Options",
            "Control debug output and delete confirmation behaviour for this company.",
        )
        colors = theme_colors()
        self.debug_checkbox = create_checkbox(
            "Enable debug mode",
            label_color=colors["input_text"],
            font_size=13,
            spacing=8,
        )
        self.confirm_delete_checkbox = create_checkbox(
            "Confirm before deleting transactions",
            label_color=colors["input_text"],
            font_size=13,
            spacing=8,
        )
        self.confirm_delete_checkbox.setChecked(True)
        layout.addWidget(self.debug_checkbox)
        layout.addWidget(self.confirm_delete_checkbox)
        layout.addStretch()
        return page

    def _build_layout_memory_page(self) -> QWidget:
        """Create the layout memory reset page."""
        page, layout = build_settings_page_shell(
            "Window & Layout Memory",
            "This app remembers module window sizes and table column widths you adjust. "
            "Use the button below to restore all windows and column layouts to defaults.",
        )
        self.restore_layouts_button = QPushButton("Reset Layouts")
        self.restore_layouts_button.clicked.connect(self._restore_default_ui_layouts)
        layout.addWidget(self.restore_layouts_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    def _show_section(self, section_id: str) -> None:
        """Display one settings section in the content stack."""
        index_map = {
            "cash_tender": 0,
            "invoice_numbering": 1,
            "other_options": 2,
            "layout_memory": 3,
        }
        index = index_map.get(section_id, 0)
        self.section_stack.setCurrentIndex(index)
        button = self.section_buttons.get(section_id)
        if button is not None:
            button.setChecked(True)

    def _apply_page_styles(self) -> None:
        """Apply theme-aware styles to the settings page."""
        apply_settings_page_styles(
            self,
            "InvoiceSettingsPage",
            self.section_buttons,
            self.title_label,
            self.subtitle_label,
            self.footer_frame,
            self.save_btn,
            self.cancel_btn,
            self.restore_layouts_button,
        )
        from ui.theme_manager import get_theme_manager

        label_color = get_theme_manager().get_colors()["input_text"]
        if hasattr(self.cash_tender_checkbox, "set_label_color"):
            self.cash_tender_checkbox.set_label_color(label_color)
        if hasattr(self.debug_checkbox, "set_label_color"):
            self.debug_checkbox.set_label_color(label_color)
        if hasattr(self.confirm_delete_checkbox, "set_label_color"):
            self.confirm_delete_checkbox.set_label_color(label_color)

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self._apply_page_styles()

    def close_settings_dialog(self):
        """Close the containing Settings dialog when Cancel is clicked."""
        parent = self.parent()
        while parent is not None and (not hasattr(parent, "reject")):
            parent = parent.parent()
        if parent is not None:
            parent.reject()
        else:
            self.close()

    def _restore_default_ui_layouts(self):
        """Clear persisted UI layout memory after user confirmation."""
        from ui.ui_memory import prompt_restore_default_ui_layouts

        prompt_restore_default_ui_layouts(self)

    def load_general_settings(self):
        """Load company settings into the UI controls."""
        try:
            self.cash_tender_checkbox.setChecked(self.db.is_cash_tender_enabled())
        except Exception as exc:
            print(f"Cash tender load error: {exc}")
            self.cash_tender_checkbox.setChecked(True)

        try:
            from config import active_company_manager

            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            settings = get_settings(self.db, active_company["id"])
            self.invoice_prefix_input.setText(str(settings.get(INVOICE_PREFIX_KEY, "") or ""))
            for voucher_type, input_widget in self.prefix_inputs.items():
                setting_key = VOUCHER_PREFIX_SETTINGS.get(voucher_type, "")
                input_widget.setText(str(settings.get(setting_key, "") or ""))
            default_type = normalize_entry_type(settings.get(DEFAULT_ENTRY_TYPE_KEY, "Cash"))
            default_index = self.default_entry_type_combo.findText(
                default_type, Qt.MatchFlag.MatchFixedString
            )
            if default_index >= 0:
                self.default_entry_type_combo.setCurrentIndex(default_index)
            for voucher_type, combo_widget in self.entry_type_inputs.items():
                setting_key = ENTRY_TYPE_SETTINGS.get(voucher_type, "")
                entry_type = normalize_entry_type(settings.get(setting_key, default_type))
                type_index = combo_widget.findText(entry_type, Qt.MatchFlag.MatchFixedString)
                if type_index >= 0:
                    combo_widget.setCurrentIndex(type_index)
            self.debug_checkbox.setChecked(
                str(settings.get("enable_debug_mode", "0")).strip().lower()
                in {"1", "true", "yes", "on"}
            )
            self.confirm_delete_checkbox.setChecked(
                str(settings.get("confirm_before_delete", "1")).strip().lower()
                in {"1", "true", "yes", "on"}
            )
        except Exception as exc:
            print(f"Settings load error: {exc}")

    def save_settings(self):
        """Persist editable settings from this settings widget."""
        try:
            from config import active_company_manager

            active_company = active_company_manager.get_active_company()
            if not active_company:
                QMessageBox.warning(self, "Settings", "Please open a company first.")
                return

            saved = self.db.set_cash_tender_enabled(self.cash_tender_checkbox.isChecked())
            if not saved:
                QMessageBox.warning(self, "Settings", "Could not save cash tender setting.")
                return

            values = {
                INVOICE_PREFIX_KEY: self.invoice_prefix_input.text().strip(),
                DEFAULT_ENTRY_TYPE_KEY: normalize_entry_type(
                    self.default_entry_type_combo.currentText()
                ),
                "enable_debug_mode": "1" if self.debug_checkbox.isChecked() else "0",
                "confirm_before_delete": "1" if self.confirm_delete_checkbox.isChecked() else "0",
            }
            for voucher_type, input_widget in self.prefix_inputs.items():
                setting_key = VOUCHER_PREFIX_SETTINGS.get(voucher_type)
                if setting_key:
                    values[setting_key] = input_widget.text().strip()
            for voucher_type, combo_widget in self.entry_type_inputs.items():
                setting_key = ENTRY_TYPE_SETTINGS.get(voucher_type)
                if setting_key:
                    values[setting_key] = normalize_entry_type(combo_widget.currentText())

            if not save_settings(self.db, active_company["id"], values):
                QMessageBox.warning(self, "Settings", "Could not save invoice settings.")
                return

            QMessageBox.information(self, "Settings", "Settings saved successfully.")
        except Exception as exc:
            print(f"Settings save error: {exc}")
            QMessageBox.warning(self, "Settings", "An error occurred while saving settings.")