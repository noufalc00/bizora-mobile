"""
Table delegate for Sales Return widget.

Column map (matches SalesReturnHelpersMixin):
  0=SL  1=Product  2=HSN  3=CGST (%)  4=SGST (%)  5=IGST (%)  6=CESS (%)
  7=Rate  8=Qty  9=Gross  10=Disc  11=Net  12=Tax  13=Total

Editable columns  : 7=Rate, 8=Qty, 10=Disc
Read-only calc cols: 9=Gross, 11=Net, 12=Tax, 13=Total

Enter flow  : Qty(8) → Gross(9) → Disc(10) → barcode field
Esc flow    : Product(1)→barcode | Qty(8)→Rate(7) | Rate(7)→Product(1)
              Gross(9)→Qty(8)   | Disc(10)→Gross(9)
"""

from PySide6.QtWidgets import (
    QStyledItemDelegate, QLineEdit, QAbstractItemDelegate, QAbstractItemView, QStyle, QStyleOptionViewItem
)
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QDoubleValidator, QPen, QColor

from ui import theme

# Editable columns
_EDIT_COLS = {7, 8, 10}          # Rate, Qty, Disc
COL_RATE = 7
COL_QTY = 8
COL_GROSS = 9
COL_DISC = 10

# Enter navigation: col → next col (same row), or None = top-bar barcode
_ENTER_NEXT = {
    7: 8,    # Rate  → Qty
    8: 9,    # Qty   → Gross  (read-only, so we just focus it; Gross→Disc handled too)
    9: 10,   # Gross → Disc
    10: None # Disc  → barcode field
}

# Esc navigation: col → (same_row_col | 'barcode')
_ESC_NEXT = {
    1:  'barcode',  # Product → barcode field
    7:  1,          # Rate    → Product same row
    8:  7,          # Qty     → Rate same row
    9:  8,          # Gross   → Qty  same row
    10: 9,          # Disc    → Gross same row
}


class SingleClickSelectAllDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            # Queue selection until the editor is fully created and visible.
            QTimer.singleShot(0, editor.selectAll)
        return editor


class SalesReturnDelegate(SingleClickSelectAllDelegate):
    """Delegate that handles Enter/Esc keyboard flow for the Sales Return table."""

    def __init__(self, table_widget, page_widget):
        """
        table_widget : the QTableWidget (items_table)
        page_widget  : the SalesReturnPageWidget (has .barcode_input, .product_input,
                       .focus_table_cell_editor(), .recalculate_row())
        """
        super().__init__(table_widget)
        self._table = table_widget
        self._page = page_widget
        self.current_editor = None
        self.current_index = None
        self._table_was_blocked = False

    def _prepare_billing_cell_editor(self, editor: QLineEdit) -> None:
        """Configure a flush in-cell editor with edit-mode highlight."""
        theme.prepare_billing_cell_editor(editor)

    def updateEditorGeometry(self, editor, option, index):
        """Stretch the editor to fill the full cell area."""
        editor.setGeometry(option.rect)

    def paint(self, painter, option, index):
        """Draw row-outline selection when SL No is clicked (matches Sales Entry)."""
        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.State_Selected
        super().paint(painter, clean_option, index)

        page = self._page
        if not page or getattr(page, 'manually_selected_row', -1) != index.row():
            return

        table = self._table
        rect = option.rect
        pen = QPen(QColor(theme.grid_selection_pen_color()))
        pen.setWidth(2)
        painter.save()
        painter.setPen(pen)
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if index.column() == 0:
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
        if index.column() == table.columnCount() - 1:
            painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.restore()

    # ------------------------------------------------------------------ #
    #  Editor creation                                                     #
    # ------------------------------------------------------------------ #

    def createEditor(self, parent, option, index):
        col = index.column()
        if col not in _EDIT_COLS:
            return None                      # non-editable cell
        table = self._table
        initial_text = ""
        if table:
            item = table.item(index.row(), index.column())
            if item:
                initial_text = item.text() or ""
        if table:
            self._table_was_blocked = table.blockSignals(True)
        editor = QLineEdit(parent)
        self._prepare_billing_cell_editor(editor)
        validator = QDoubleValidator(0.0, 9_999_999.99, 3)
        validator.setNotation(QDoubleValidator.StandardNotation)
        editor.setValidator(validator)
        editor.blockSignals(True)
        editor.setText(str(initial_text))
        editor.blockSignals(False)
        editor.installEventFilter(self)
        QTimer.singleShot(0, editor.selectAll)
        self.current_editor = editor
        self.current_index = index
        if col in _EDIT_COLS:
            editor.textChanged.connect(
                lambda text, r=index.row(), c=col: self._on_editor_changed(r, c, text)
            )
        return editor

    def setEditorData(self, editor, index):
        value = index.data(Qt.DisplayRole) or ''
        if not str(editor.text() or '').strip():
            editor.setText(str(value))
        QTimer.singleShot(0, editor.selectAll)
        self.current_editor = editor
        self.current_index = index
        col = index.column()
        if col in _EDIT_COLS:
            try:
                editor.textChanged.disconnect()
            except Exception:
                pass
            editor.textChanged.connect(
                lambda text, r=index.row(), c=col: self._on_editor_changed(r, c, text)
            )

    def destroyEditor(self, editor, index):
        if self._table and getattr(self, '_table_was_blocked', False):
            self._table.blockSignals(False)
            self._table_was_blocked = False
        self.current_editor = None
        self.current_index = None
        super().destroyEditor(editor, index)

    def _on_editor_changed(self, row, col, text):
        """Live recalculation as user types in an editable cell."""
        if self._page:
            self._page.recalculate_row_live(row, col, text)

    def setModelData(self, editor, model, index):
        text = editor.text().strip()
        try:
            num = float(text)
            model.setData(index, f"{num:.3f}", Qt.EditRole)
        except ValueError:
            pass

    # ------------------------------------------------------------------ #
    #  Key routing                                                         #
    # ------------------------------------------------------------------ #

    def eventFilter(self, editor, event):
        if event.type() != QEvent.KeyPress:
            return super().eventFilter(editor, event)

        key = event.key()

        # ---- Enter / Return ----
        if key in (Qt.Key_Return, Qt.Key_Enter):
            # MUST read row/col BEFORE closeEditor — Qt resets currentIndex after close
            row = self._table.currentIndex().row()
            col = self._table.currentIndex().column()
            self._commit(editor)
            next_col = _ENTER_NEXT.get(col)
            if next_col is None:
                # Disc(10) → top-bar barcode for the next item scan
                def _focus_barcode():
                    self._page.barcode_input.setFocus()
                    self._page.barcode_input.selectAll()
                QTimer.singleShot(0, _focus_barcode)
            else:
                # Skip non-editable columns: Gross(10) is read-only, jump straight to Disc(11)
                target = next_col
                while target not in _EDIT_COLS and target in _ENTER_NEXT and _ENTER_NEXT[target] is not None:
                    target = _ENTER_NEXT[target]
                QTimer.singleShot(0, lambda r=row, c=target: self._page.focus_table_cell_editor(r, c))
            return True

        # ---- Escape ----
        if key == Qt.Key_Escape:
            # MUST read row/col BEFORE closeEditor
            row = self._table.currentIndex().row()
            col = self._table.currentIndex().column()
            self._revert(editor)
            dest = _ESC_NEXT.get(col, 'barcode')
            if dest == 'barcode':
                QTimer.singleShot(0, self._page.barcode_input.setFocus)
            else:
                QTimer.singleShot(0, lambda r=row, c=dest: self._page.focus_table_cell_editor(r, c))
            return True

        if key == Qt.Key_Down and self.current_index and self.current_index.column() == COL_DISC:
            self._apply_discount_percent(editor)
            return True

        return super().eventFilter(editor, event)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _commit(self, editor):
        self._table.commitData(editor)
        self._table.closeEditor(editor, QAbstractItemDelegate.SubmitModelCache)

    def _revert(self, editor):
        self._table.closeEditor(editor, QAbstractItemDelegate.RevertModelCache)

    def _cell_float(self, row, col):
        item = self._table.item(row, col)
        if item is None:
            return 0.0
        try:
            return float(item.text().replace(',', '').replace('₹', '').replace('%', '').strip() or '0')
        except (TypeError, ValueError):
            return 0.0

    def _apply_discount_percent(self, editor):
        if not self.current_index:
            return
        row = self.current_index.row()
        try:
            percent = float(editor.text().strip() or '0')
        except ValueError:
            return
        if percent <= 0:
            return

        gross = self._cell_float(row, COL_GROSS)
        if gross <= 0:
            gross = self._cell_float(row, COL_RATE) * self._cell_float(row, COL_QTY)
        if gross <= 0:
            return

        new_text = f"{round(gross * percent / 100.0, 2):.2f}"
        editor.blockSignals(True)
        try:
            editor.setText(new_text)
            editor.selectAll()
        finally:
            editor.blockSignals(False)

        was_blocked = self._table.blockSignals(True)
        try:
            disc_item = self._table.item(row, COL_DISC)
            if disc_item:
                disc_item.setText(new_text)
        finally:
            self._table.blockSignals(was_blocked)

        if self._page:
            self._page.recalculate_row(row)