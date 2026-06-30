"""
Shared helpers for voucher entry pages: unsaved-close guard and next-number flow.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from config import active_company_manager
from bizora_core.invoice_numbering import get_next_voucher_from_current
from ui.message_boxes import show_message


class EntryVoucherMixin:
    """Mixin for sales/purchase/return/quotation entry widgets."""

    voucher_type: str = ""
    voucher_number_attr: str = ""

    def _init_entry_voucher_state(self) -> None:
        """Initialize dirty-state tracking for unsaved-close prompts."""
        self._entry_form_dirty = False
        self._entry_dirty_suppressed = False
        self._entry_snapshot = ""

    def _begin_entry_reset(self) -> None:
        """Suppress dirty tracking while a form is being cleared or reloaded."""
        self._entry_dirty_suppressed = True

    def _end_entry_reset(self) -> None:
        """Re-enable dirty tracking after a programmatic form reset."""
        self._entry_dirty_suppressed = False
        self._clear_entry_dirty()
        self._finalize_entry_baseline()

    def _capture_entry_snapshot(self) -> str:
        """Return a serialized form state for unsaved-close detection."""
        return ""

    def _finalize_entry_baseline(self) -> None:
        """Store the current form state as the saved baseline for close prompts."""
        try:
            self._entry_snapshot = self._capture_entry_snapshot()
        except Exception:
            self._entry_snapshot = ""

    def _is_entry_edit_mode(self) -> bool:
        """Return True when an existing saved voucher is loaded for editing."""
        for attr_name in (
            "current_sale_id",
            "current_purchase_id",
            "current_return_id",
            "current_quotation_id",
            "current_po_id",
        ):
            if getattr(self, attr_name, None):
                return True
        return False

    def _unsaved_close_dialog_copy(self) -> tuple[str, str]:
        """Return the title and body for the unsaved-close prompt."""
        if self._is_entry_edit_mode():
            return (
                "Unsaved Changes",
                "You have unsaved changes to this bill. Do you want to update before closing?",
            )
        return (
            "Unsaved Changes",
            "You have unsaved changes. Do you want to save before closing?",
        )

    def _schedule_entry_baseline_finalize(self, delay_ms: int = 0) -> None:
        """Capture the edit baseline after pending table and total updates settle."""
        def _apply_baseline() -> None:
            if getattr(self, "_deferred_totals_pending", False):
                QTimer.singleShot(0, _apply_baseline)
                return
            for method_name in ("calculate_totals", "calculate_grand_totals"):
                finalize_totals = getattr(self, method_name, None)
                if callable(finalize_totals):
                    try:
                        finalize_totals()
                    except Exception:
                        pass
                    break
            self._finalize_entry_baseline()

        QTimer.singleShot(delay_ms, _apply_baseline)

    def _entry_has_unsaved_changes(self) -> bool:
        """Return True when the form differs from its last saved baseline."""
        if getattr(self, "_entry_form_dirty", False):
            return True
        baseline = getattr(self, "_entry_snapshot", None)
        if baseline is None:
            return False
        try:
            return self._capture_entry_snapshot() != baseline
        except Exception:
            return getattr(self, "_entry_form_dirty", False)

    def _mark_entry_dirty(self, *_args) -> None:
        """Mark the current entry form as changed."""
        if getattr(self, "_entry_dirty_suppressed", False):
            return
        if getattr(self, "_is_loading", False) or getattr(self, "_is_initializing", False):
            return
        self._entry_form_dirty = True

    def _clear_entry_dirty(self) -> None:
        """Clear dirty state after save, load, or reset."""
        self._entry_form_dirty = False

    def _install_unsaved_guard(self, widgets: list[object], table=None) -> None:
        """Wire common widgets so edits trigger the unsaved-close prompt."""
        for widget in widgets:
            if widget is None:
                continue
            if hasattr(widget, "textChanged"):
                widget.textChanged.connect(self._mark_entry_dirty)
            elif hasattr(widget, "currentTextChanged"):
                widget.currentTextChanged.connect(self._mark_entry_dirty)
            elif hasattr(widget, "dateChanged"):
                widget.dateChanged.connect(self._mark_entry_dirty)
            elif hasattr(widget, "currentIndexChanged"):
                widget.currentIndexChanged.connect(self._mark_entry_dirty)
            elif hasattr(widget, "toggled"):
                widget.toggled.connect(self._mark_entry_dirty)
        if table is not None and hasattr(table, "itemChanged"):
            table.itemChanged.connect(self._mark_entry_dirty)

    def _confirm_close_with_unsaved_guard(
        self,
        event=None,
        *,
        parent_widget: QWidget | None = None,
    ) -> bool:
        """
        Prompt before closing when the form has unsaved edits.

        Returns True when the window may close, False when close is cancelled.
        """
        if not self._entry_has_unsaved_changes():
            return True

        dialog_parent = parent_widget or self.window() or self
        title, message = self._unsaved_close_dialog_copy()
        reply = show_message(
            dialog_parent,
            QMessageBox.Icon.Question,
            title,
            message,
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            if event is not None:
                event.ignore()
            return False
        if reply == QMessageBox.StandardButton.Yes:
            save_method = None
            for method_name in ("save", "save_return"):
                candidate = getattr(self, method_name, None)
                if callable(candidate):
                    save_method = candidate
                    break
            if save_method is None:
                if event is not None:
                    event.ignore()
                return False
            try:
                result = save_method()
            except Exception:
                if event is not None:
                    event.ignore()
                return False
            if result is None:
                if event is not None:
                    event.ignore()
                return False
            if isinstance(result, dict) and not result.get("success", True):
                if event is not None:
                    event.ignore()
                return False
            self._finalize_entry_baseline()
        self._clear_entry_dirty()
        return True

    def open_next_numbered_entry(self) -> None:
        """Open a fresh entry form with the next sequential voucher number."""
        if not self.voucher_type or not self.voucher_number_attr:
            return

        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, "No Active Company", "Please open a company first.")
            return

        number_widget = getattr(self, self.voucher_number_attr, None)
        if number_widget is None:
            return

        current_value = ""
        if hasattr(number_widget, "text"):
            current_value = number_widget.text().strip()

        next_number = get_next_voucher_from_current(
            self.db,
            active_company["id"],
            self.voucher_type,
            current_value,
        )

        self._begin_entry_reset()
        try:
            clear_method = getattr(self, "clear_form", None)
            if callable(clear_method):
                clear_method()
            if hasattr(number_widget, "setText"):
                number_widget.setText(next_number)
        finally:
            self._end_entry_reset()


    def _install_voucher_number_lookup(self) -> None:
        """Load a saved voucher when the user presses Enter in the number field."""
        number_widget = getattr(self, self.voucher_number_attr, None)
        if number_widget is None:
            return
        if hasattr(number_widget, "returnPressed"):
            number_widget.returnPressed.connect(self._on_voucher_number_lookup)

    def _on_voucher_number_lookup(self) -> None:
        """Attempt to load a saved voucher after the number field is committed."""
        if getattr(self, "_is_loading", False) or getattr(self, "_entry_dirty_suppressed", False):
            return
        number_widget = getattr(self, self.voucher_number_attr, None)
        if number_widget is None or not hasattr(number_widget, "text"):
            return
        voucher_number = number_widget.text().strip()
        if not voucher_number:
            return
        loader = getattr(self, "load_voucher_by_number", None)
        if callable(loader):
            loaded = loader(voucher_number)
            if not loaded:
                QMessageBox.information(
                    self,
                    "Not Found",
                    f"No saved record found for number '{voucher_number}'.",
                )

    def load_voucher_by_number(self, voucher_number: str) -> bool:
        """Default voucher lookup used by entry pages with a voucher_type."""
        if not self.voucher_type:
            return False
        active_company = active_company_manager.get_active_company()
        if not active_company:
            return False

        from bizora_core.voucher_lookup import find_voucher_id

        voucher_id = find_voucher_id(
            self.db,
            active_company["id"],
            self.voucher_type,
            voucher_number,
        )
        if not voucher_id:
            return False

        current_id = getattr(self, "current_po_id", None)
        if current_id is None:
            for attr_name in (
                "current_sale_id",
                "current_purchase_id",
                "current_return_id",
                "current_quotation_id",
            ):
                current_id = getattr(self, attr_name, None)
                if current_id:
                    break
        if current_id and int(current_id) == int(voucher_id):
            return True

        method_name = {
            "sales": "load_sale_by_id",
            "purchase": "load_purchase",
            "sales_return": "load_return_by_id",
            "purchase_return": "load_return_by_id",
            "quotation": "load_quotation_by_id",
            "purchase_order": "load_po_by_id",
        }.get(self.voucher_type)
        loader = getattr(self, method_name, None) if method_name else None
        if not callable(loader):
            return False
        try:
            loader(int(voucher_id))
            return True
        except Exception:
            return False


def prepare_standalone_window_for_prompt(window) -> None:
    """Restore a minimized module window so close prompts are visible and modal."""
    if window is None:
        return
    try:
        if window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()
        QApplication.processEvents()
    except RuntimeError:
        pass


def confirm_standalone_entry_close(window, event) -> bool:
    """Ask the hosted entry page about unsaved edits before closing a module window."""
    from ui.standalone_window import get_standalone_page_widget

    prepare_standalone_window_for_prompt(window)
    page_widget = get_standalone_page_widget(window)
    if page_widget is not None and hasattr(page_widget, "_confirm_close_with_unsaved_guard"):
        return page_widget._confirm_close_with_unsaved_guard(
            event,
            parent_widget=window,
        )
    return True