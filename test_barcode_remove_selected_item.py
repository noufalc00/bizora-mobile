"""Offscreen regression checks for Barcode Utilities row removal confirmation."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui import barcode_manager  # noqa: E402
from ui.barcode_manager import BarcodeManagerWindow, COL_SL  # noqa: E402


def _app():
    """Return the shared QApplication used by the offscreen checks."""
    return QApplication.instance() or QApplication(sys.argv)


def _sample_rows():
    """Return stable queue rows for remove-selected regression checks."""
    return [
        {
            "barcode": "111",
            "product_name": "First Item",
            "supplier_code": "A1",
            "purchase_price": 10,
            "mrp": 15,
            "item_index": 1,
            "print_qty": 1,
        },
        {
            "barcode": "222",
            "product_name": "Second Item",
            "supplier_code": "B2",
            "purchase_price": 20,
            "mrp": 25,
            "item_index": 2,
            "print_qty": 1,
        },
    ]


def _install_messagebox_spies(question_response):
    """Monkeypatch QMessageBox calls and collect their invocation payloads."""
    calls = {"warning": [], "question": []}
    original_warning = barcode_manager.QMessageBox.warning
    original_question = barcode_manager.QMessageBox.question

    def warning(parent, title, message):
        """Record warning dialogs without showing a modal window."""
        calls["warning"].append((parent, title, message))
        return barcode_manager.QMessageBox.StandardButton.Ok

    def question(parent, title, message, buttons=None, default_button=None):
        """Record confirmation dialogs without showing a modal window."""
        calls["question"].append(
            (parent, title, message, buttons, default_button)
        )
        return question_response

    barcode_manager.QMessageBox.warning = warning
    barcode_manager.QMessageBox.question = question
    return calls, original_warning, original_question


def _restore_messagebox(original_warning, original_question):
    """Restore QMessageBox functions after a monkeypatched check."""
    barcode_manager.QMessageBox.warning = original_warning
    barcode_manager.QMessageBox.question = original_question


def test_no_selection_warning():
    """Verify no selected row still shows the existing warning and removes none."""
    _app()
    window = BarcodeManagerWindow(rows=_sample_rows())
    calls, original_warning, original_question = _install_messagebox_spies(
        barcode_manager.QMessageBox.StandardButton.Yes
    )
    try:
        window.table.clearSelection()
        before_count = window.table.rowCount()

        window.remove_selected_items()

        assert window.table.rowCount() == before_count
        assert len(calls["warning"]) == 1
        assert calls["warning"][0][1] == "Remove Item"
        assert "Please select an item to remove." in calls["warning"][0][2]
        assert calls["question"] == []
    finally:
        window.close()
        _restore_messagebox(original_warning, original_question)


def test_selected_decline_keeps_row_from_button():
    """Verify the real Remove Selected Item button asks and respects No."""
    _app()
    window = BarcodeManagerWindow(rows=_sample_rows())
    calls, original_warning, original_question = _install_messagebox_spies(
        barcode_manager.QMessageBox.StandardButton.No
    )
    try:
        assert not window.remove_selected_btn.autoDefault()
        assert not window.remove_selected_btn.isDefault()

        window.table.selectRow(0)
        before_count = window.table.rowCount()

        window.remove_selected_btn.click()

        assert window.table.rowCount() == before_count
        assert calls["warning"] == []
        assert len(calls["question"]) == 1
        assert calls["question"][0][1] == "Remove Item"
        assert "Are you sure you want to remove" in calls["question"][0][2]
    finally:
        window.close()
        _restore_messagebox(original_warning, original_question)


def test_selected_accept_removes_row_from_button():
    """Verify the real Remove Selected Item button removes after confirmation."""
    _app()
    window = BarcodeManagerWindow(rows=_sample_rows())
    calls, original_warning, original_question = _install_messagebox_spies(
        barcode_manager.QMessageBox.StandardButton.Yes
    )
    try:
        window.table.selectRow(0)

        window.remove_selected_btn.click()

        assert window.table.rowCount() == 1
        assert window.table.item(0, COL_SL).text() == "1"
        assert calls["warning"] == []
        assert len(calls["question"]) == 1
    finally:
        window.close()
        _restore_messagebox(original_warning, original_question)


if __name__ == "__main__":
    test_no_selection_warning()
    test_selected_decline_keeps_row_from_button()
    test_selected_accept_removes_row_from_button()
    print("Barcode remove-selected confirmation checks passed.")
