"""
Barcode label configuration UI with live sticker preview.

Restores the full pre-Phase-130 settings workspace (hardware, price key,
click-to-edit canvas, D-Pad offsets) while persisting to barcode_settings
SQLite row id=1. Opened from Settings -> Barcode Settings or the print queue
gear button.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox
from PySide6.QtCore import QTimer, Qt

from bizora_core.barcode_db import (
    fetch_barcode_preferences,
    preferences_to_barcode_settings,
    save_barcode_preferences as persist_barcode_preferences,
    _gap_index_from_stored,
    _size_index_from_stored,
)
from ui.barcode_manager import (
    BarcodeManagerWindow,
    BarcodeSettings,
    LabelRenderEngine,
    DEFAULT_PRICE_DIGITS,
    default_element_offsets,
    default_typography_settings,
    load_calibration_config,
)


class BarcodeSettingsUI(BarcodeManagerWindow):
    """
    Full barcode configuration dialog reusing BarcodeManagerWindow settings UI.

    Includes live label preview, quick-select elements, and offset typography
    controls exactly as before the Phase 130 print-queue split.
    """

    def __init__(self, parent=None, db=None):
        QDialog.__init__(self, parent)
        self.db = db
        self._close_on_settings_save = True
        self._use_live_layout_edits = True

        if db:
            prefs = fetch_barcode_preferences(db)
            self.settings = preferences_to_barcode_settings(prefs)
        else:
            self.settings = BarcodeSettings().load()
        self.barcode_settings = self.settings

        self.calibration = load_calibration_config()
        self.engine = LabelRenderEngine(self.settings)
        self._active_element_key = None
        self.current_active_element = None
        self._quick_select_buttons = {}
        self._live_offsets = dict(
            self.settings.element_offsets or default_element_offsets()
        )
        self._live_typography = dict(
            self.settings.typography_settings or default_typography_settings()
        )

        self.setWindowTitle("Barcode Label Settings")
        self.setMinimumSize(1100, 680)
        self.setStyleSheet(self._window_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.addWidget(self._build_settings_tab(), 1)

        self._install_arrow_key_filter()
        self._load_barcode_preferences_from_db()
        self._wire_settings_preview_signals()
        self._rewire_save_configuration_button()
        self._disable_button_auto_defaults()
        if hasattr(self, "update_preview_canvas_size"):
            QTimer.singleShot(0, lambda: self.update_preview_canvas_size())
        QTimer.singleShot(0, self._sync_price_key_table_geometry)
        self._ui_memory_geometry_key = "barcode_settings"
        from ui.ui_memory import apply_standard_window_chrome

        apply_standard_window_chrome(self)
        self._init_ui_memory(restore_geometry=True, save_geometry=True, table_attrs=())
        from ui.ui_memory import configure_non_modal_window

        configure_non_modal_window(self, parent)

    def closeEvent(self, event):
        """Always remove the global event filter before the settings dialog closes."""
        self._teardown_app_event_filter()
        super().closeEvent(event)

    def _rewire_save_configuration_button(self):
        """Connect Save Configuration to database persistence handler."""
        if not hasattr(self, "save_config_btn"):
            return
        try:
            self.save_config_btn.clicked.disconnect(self.save_label_settings)
        except (TypeError, RuntimeError):
            pass
        self.save_config_btn.clicked.connect(self.save_barcode_preferences)

    def _load_barcode_preferences_from_db(self):
        """Load company-specific barcode preferences into settings widgets."""
        if self.db is None:
            self._apply_saved_label_settings()
            return
        try:
            prefs = fetch_barcode_preferences(self.db)
            company_name = prefs.get("company_name", "") or ""
            cipher_string = prefs.get("cipher_string", "") or ""
            default_size = prefs.get("default_size", "")
            default_gap = prefs.get("default_gap", "")
            default_printer = prefs.get("default_printer", "") or ""
            barcode_padding = prefs.get("barcode_padding", "") or "No Padding"

            if hasattr(self, "company_input"):
                self.company_input.setText(company_name)

            self._inject_cipher_string_into_matrix(cipher_string)

            if hasattr(self, "size_combo"):
                size_idx = _size_index_from_stored(default_size)
                if 0 <= size_idx < self.size_combo.count():
                    self.size_combo.setCurrentIndex(size_idx)

            if hasattr(self, "gap_combo"):
                gap_idx = _gap_index_from_stored(default_gap)
                if 0 <= gap_idx < self.gap_combo.count():
                    self.gap_combo.setCurrentIndex(gap_idx)

            if default_printer and hasattr(self, "printer_combo"):
                printer_idx = self.printer_combo.findText(default_printer)
                if printer_idx >= 0:
                    self.printer_combo.setCurrentIndex(printer_idx)

            if hasattr(self, "padding_combo"):
                padding_idx = self.padding_combo.findText(barcode_padding)
                if padding_idx < 0:
                    padding_idx = 0
                self.padding_combo.setCurrentIndex(padding_idx)

            self.settings = preferences_to_barcode_settings(prefs)
            self.barcode_settings = self.settings
            self.engine.settings = self.settings
            self._live_offsets = dict(
                self.settings.element_offsets or default_element_offsets()
            )
            self._live_typography = dict(
                self.settings.typography_settings or default_typography_settings()
            )
            if hasattr(self, "preview_canvas"):
                self.preview_canvas.update()
        except Exception:
            self._apply_saved_label_settings()

    def _inject_cipher_string_into_matrix(self, cipher_string: str):
        """Populate row 2 of the price key matrix from a 10-character cipher."""
        if not hasattr(self, "price_key_matrix"):
            return
        letters = (cipher_string or "").strip().upper()
        if len(letters) < 10:
            letters = (letters + "RCNXZYBQWM")[:10]
        self.price_key_matrix.blockSignals(True)
        try:
            for col in range(min(10, self.price_key_matrix.columnCount())):
                let_item = self.price_key_matrix.item(1, col)
                if let_item is not None:
                    let_item.setText(letters[col])
                    let_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if len(letters) >= 10:
                self.settings.price_key_map = {
                    digit: letters[idx]
                    for idx, digit in enumerate(DEFAULT_PRICE_DIGITS)
                }
        except Exception:
            pass
        finally:
            self.price_key_matrix.blockSignals(False)

    def _cipher_string_from_matrix(self) -> str:
        """Read row 2 cipher cells into one 10-letter string."""
        if not hasattr(self, "price_key_matrix"):
            return ""
        letters = []
        for col in range(min(10, self.price_key_matrix.columnCount())):
            let_item = self.price_key_matrix.item(1, col)
            letter = ""
            if let_item is not None:
                letter = (let_item.text() or "").strip().upper()[:1]
            letters.append(letter)
        return "".join(letters)

    def save_barcode_preferences(self):
        """Persist company, cipher, size, gap, printer, and layout to SQLite."""
        try:
            cipher_string = self._cipher_string_from_matrix()
            company_name = ""
            if hasattr(self, "company_input"):
                company_name = self.company_input.text().strip()
            size_text = (
                self.size_combo.currentText() if hasattr(self, "size_combo") else ""
            )
            gap_text = (
                self.gap_combo.currentText() if hasattr(self, "gap_combo") else ""
            )
            printer_name = (
                self.printer_combo.currentText().strip()
                if hasattr(self, "printer_combo")
                else ""
            )

            self.settings.company_name = company_name
            self.settings.price_key_map = self._current_price_map()
            self.settings.sticker_size_index = (
                self.size_combo.currentIndex() if hasattr(self, "size_combo") else 0
            )
            self.settings.media_gap_index = (
                self.gap_combo.currentIndex() if hasattr(self, "gap_combo") else 0
            )
            self.settings.element_offsets = self.get_element_offsets()
            self.settings.typography_settings = self.get_typography_settings()
            self.settings.printer_name = printer_name
            self.settings.barcode_padding = (
                self.padding_combo.currentText()
                if hasattr(self, "padding_combo")
                else "No Padding"
            )
            self.engine.settings = self.settings

            if self.db is not None:
                payload = {
                    "company_name": company_name,
                    "cipher_string": cipher_string,
                    "default_size": size_text,
                    "default_gap": gap_text,
                    "default_printer": printer_name,
                    "barcode_padding": self.settings.barcode_padding,
                    "font_thickness": self.settings.font_thickness,
                    "price_key_map": self.settings.price_key_map,
                    "element_offsets": self.settings.element_offsets,
                    "typography_settings": self.settings.typography_settings,
                }
                if not persist_barcode_preferences(self.db, payload):
                    QMessageBox.warning(
                        self,
                        "Save Failed",
                        "Could not update company barcode settings.",
                    )
                    return

            self.settings.save()

            QMessageBox.information(
                self,
                "Barcode Settings",
                "Barcode configuration saved successfully.",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))


def open_barcode_settings_dialog(parent=None, db=None):
    """Open barcode settings as a non-modal window tied to the application hub."""
    dialog = BarcodeSettingsUI(parent=parent, db=db)
    from ui.ui_memory import configure_non_modal_window

    configure_non_modal_window(dialog, parent)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog