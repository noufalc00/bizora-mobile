"""
Purchase Return table delegate.
Mirrors PurchaseBillDelegate from purchase_entry_delegate.py exactly:
- Blue outline on SL-selected row (no Qt blue fill)
- Single-click opens editor with full text selected
- Enter/Esc column flow matches Purchase Entry
- Live textEdited triggers recalculate_row
- FocusIn and MouseButtonPress both trigger selectAll
"""

from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QStyle, QStyleOptionViewItem
from PySide6.QtCore import Qt, QEvent, QTimer, QCoreApplication
from PySide6.QtGui import QPen, QColor
from ui import theme

# Column index constants — must match PurchaseReturnPageWidget COL_* (15-column layout)
COL_SL = 0
COL_SALE_RATE = 1
COL_PRODUCT = 2
COL_HSN = 3
COL_CGST = 4
COL_SGST = 5
COL_IGST = 6
COL_CESS = 7
COL_RATE = 8
COL_QTY = 9
COL_GROSS = 10
COL_DISC = 11
COL_NET = 12
COL_TAX = 13
COL_TOTAL = 14

# Columns that open an editor on single click / are editable
EDITABLE_COLS = (COL_RATE, COL_QTY, COL_GROSS, COL_DISC,
                 COL_HSN, COL_CGST, COL_SGST, COL_IGST, COL_CESS)

# Read-only columns (never open an editor)
READONLY_COLS = (COL_SL, COL_SALE_RATE, COL_NET, COL_TAX, COL_TOTAL)


class PurchaseReturnDelegate(QStyledItemDelegate):
    """Custom delegate for Purchase Return items table.

    Behaviour mirrors PurchaseBillDelegate from purchase_entry_delegate.py:
    - Blue row outline when SL column is clicked (no Qt blue fill).
    - Single-click on any editable cell opens editor with text fully selected.
    - Enter moves forward through columns; Esc moves backward.
    - Live textEdited signal triggers immediate row/footer recalculation.
    """

    def __init__(self, table_widget, page_widget):
        super().__init__(table_widget)
        self.parent_widget = page_widget   # PurchaseReturnPageWidget
        self.current_editor = None
        self.current_index = None
        self.initial_text = ""

    # ------------------------------------------------------------------
    # PAINT — blue outline on SL-selected row, suppress Qt blue fill
    # ------------------------------------------------------------------

    def paint(self, painter, option, index):
        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.State_Selected
        super().paint(painter, clean_option, index)

        if not self.parent_widget or not hasattr(self.parent_widget, 'manually_selected_row'):
            return
        row = index.row()
        if self.parent_widget.manually_selected_row != row:
            return

        table = self.parent_widget.items_table
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

    def _prepare_billing_cell_editor(self, editor: QLineEdit) -> None:
        """Configure a flush in-cell editor with edit-mode highlight."""
        theme.prepare_billing_cell_editor(editor)

    def updateEditorGeometry(self, editor, option, index):
        """Stretch the editor to fill the full cell area."""
        editor.setGeometry(option.rect)

    # ------------------------------------------------------------------
    # CREATE EDITOR
    # ------------------------------------------------------------------

    def createEditor(self, parent, option, index):
        column = index.column()

        # Read-only columns — never create an editor
        if column in READONLY_COLS:
            return None

        # Nature-based tax column lock (same logic as Purchase Entry)
        if self.parent_widget and hasattr(self.parent_widget, 'nature_combo'):
            nature = self.parent_widget.nature_combo.currentText()
            is_local = (nature != 'Inter-state')
            if is_local and column == COL_IGST:
                return None
            if not is_local and column in (COL_CGST, COL_SGST):
                return None

        table = self.parent_widget.items_table if self.parent_widget else None
        initial_text = ""
        if table:
            item = table.item(index.row(), index.column())
            if item:
                initial_text = item.text()

        editor = QLineEdit(parent)
        self._prepare_billing_cell_editor(editor)
        editor.setText(initial_text)
        editor.setFocusPolicy(Qt.StrongFocus)
        # Select all immediately when editor opens
        QTimer.singleShot(0, editor.selectAll)

        self.current_index = index
        self.current_editor = editor
        self.initial_text = initial_text

        # Live recalculation on every keystroke
        editor.textEdited.connect(
            lambda text, idx=index: self._on_editor_changed(idx, text)
        )

        # Install event filter for Enter/Esc and focus/mouse select-all
        editor.installEventFilter(self)

        return editor

    # ------------------------------------------------------------------
    # SET EDITOR DATA
    # ------------------------------------------------------------------

    def setEditorData(self, editor, index):
        text = index.model().data(index, Qt.EditRole) or ""
        editor.setText(text)
        self.initial_text = text

    # ------------------------------------------------------------------
    # SET MODEL DATA
    # ------------------------------------------------------------------

    def setModelData(self, editor, model, index):
        table = self.parent_widget.items_table if self.parent_widget else None
        new_text = editor.text()
        column = index.column()

        if table:
            table.blockSignals(True)
        try:
            model.setData(index, new_text, Qt.EditRole)
        finally:
            if table:
                table.blockSignals(False)

        # Trigger recalculation for numeric columns
        if column in (COL_RATE, COL_QTY, COL_GROSS, COL_DISC,
                      COL_CGST, COL_SGST, COL_IGST, COL_CESS):
            if self.parent_widget:
                self.parent_widget._recalculate_row_in_table(index.row())

    # ------------------------------------------------------------------
    # EVENT FILTER — Enter / Esc / FocusIn / MouseButtonPress
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        # Select all on focus-in or mouse click (same as Purchase Entry)
        if event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress) and obj is self.current_editor:
            if isinstance(obj, QLineEdit):
                QTimer.singleShot(0, obj.selectAll)
            if event.type() == QEvent.MouseButtonPress:
                return True   # Prevent default cursor positioning
            return False

        if event.type() == QEvent.KeyPress and obj is self.current_editor:
            key = event.key()

            # ---- ENTER / RETURN ----
            if key in (Qt.Key_Return, Qt.Key_Enter):
                table = self.parent_widget.items_table if self.parent_widget else None
                if not table:
                    return True
                row = self.current_index.row()
                col = self.current_index.column()

                self.commitData.emit(self.current_editor)
                self.closeEditor.emit(self.current_editor,
                                      QStyledItemDelegate.SubmitModelCache)

                # Enter flow mirrors Purchase Entry exactly:
                # HSN -> CGST/IGST (by nature) -> CGST->SGST -> SGST/IGST/CESS -> RATE
                # RATE -> QTY -> DISC -> next row RATE (or barcode if last row)
                if col == COL_HSN:
                    nature = self.parent_widget.nature_combo.currentText() \
                        if hasattr(self.parent_widget, 'nature_combo') else 'Local'
                    if nature != 'Inter-state':
                        self._goto(row, COL_CGST)
                    else:
                        self._goto(row, COL_IGST)
                    return True
                if col == COL_CGST:
                    self._goto(row, COL_SGST)
                    return True
                if col in (COL_SGST, COL_IGST, COL_CESS):
                    self._goto(row, COL_RATE)
                    return True
                if col == COL_RATE:
                    self._goto(row, COL_QTY)
                    return True
                if col == COL_QTY:
                    self._goto(row, COL_DISC)
                    return True
                if col == COL_GROSS:
                    self._goto(row, COL_DISC)
                    return True
                if col == COL_DISC:
                    next_row = row + 1
                    if next_row < table.rowCount():
                        self._goto(next_row, COL_RATE)
                    else:
                        # Last row — go back to barcode
                        if hasattr(self.parent_widget, 'barcode_input'):
                            self.parent_widget.barcode_input.setFocus()
                            self.parent_widget.barcode_input.selectAll()
                    return True
                return True

            # ---- ESCAPE ----
            elif key == Qt.Key_Escape:
                row = self.current_index.row()
                col = self.current_index.column()

                if self.initial_text:
                    self.current_editor.setText(self.initial_text)
                self.closeEditor.emit(self.current_editor,
                                      QStyledItemDelegate.RevertModelCache)

                # Esc flow mirrors Purchase Entry: backward through columns
                if col == COL_DISC:
                    self._goto(row, COL_QTY)
                elif col == COL_QTY:
                    self._goto(row, COL_RATE)
                elif col == COL_RATE:
                    nature = self.parent_widget.nature_combo.currentText() \
                        if hasattr(self.parent_widget, 'nature_combo') else 'Local'
                    if nature != 'Inter-state':
                        self._goto(row, COL_SGST)   # Local: RATE <- SGST <- CGST
                    else:
                        self._goto(row, COL_CESS)   # Inter: RATE <- CESS <- IGST
                elif col == COL_CESS:
                    nature = self.parent_widget.nature_combo.currentText() \
                        if hasattr(self.parent_widget, 'nature_combo') else 'Local'
                    if nature != 'Inter-state':
                        self._goto(row, COL_SGST)
                    else:
                        self._goto(row, COL_IGST)
                elif col == COL_SGST:
                    self._goto(row, COL_CGST)
                elif col == COL_IGST:
                    self._goto(row, COL_HSN)
                elif col == COL_CGST:
                    self._goto(row, COL_HSN)
                elif col == COL_HSN:
                    if hasattr(self.parent_widget, 'barcode_input'):
                        self.parent_widget.barcode_input.setFocus()
                        self.parent_widget.barcode_input.selectAll()
                else:
                    if hasattr(self.parent_widget, 'barcode_input'):
                        self.parent_widget.barcode_input.setFocus()
                        self.parent_widget.barcode_input.selectAll()
                return True

            elif key == Qt.Key_Down:
                # Down Arrow in Disc converts the typed number from percent to
                # the flat cash amount consumed by the calculation engine.
                if self.current_index and self.current_index.column() == COL_DISC:
                    self.handle_disc_percent_conversion(obj)
                    return True

        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def handle_disc_percent_conversion(self, editor):
        """Convert typed Disc percentage to flat cash discount for the row."""
        if not self.parent_widget or not self.current_index:
            return

        row = self.current_index.row()
        raw = editor.text() if editor else self.parent_widget.safe_item_text(row, COL_DISC, "0")
        raw = str(raw).replace('%', '').strip()
        if not raw:
            return

        try:
            percent = float(raw)
        except ValueError:
            return

        gross = self.parent_widget.safe_float_from_cell(row, COL_GROSS, 0.0)
        if gross <= 0:
            rate = self.parent_widget.safe_float_from_cell(row, COL_RATE, 0.0)
            qty = self.parent_widget.safe_float_from_cell(row, COL_QTY, 0.0)
            gross = rate * qty
        if gross <= 0:
            return

        if percent > 100:
            percent = 100.0

        flat_amount = round(gross * percent / 100.0, 2)
        new_text = f"{flat_amount:.2f}"

        if editor:
            was_editor_blocked = editor.blockSignals(True)
            try:
                editor.setText(new_text)
            finally:
                editor.blockSignals(was_editor_blocked)
            editor.setCursorPosition(len(new_text))

        table = self.parent_widget.items_table
        was_blocked = table.blockSignals(True)
        try:
            disc_item = table.item(row, COL_DISC)
            if disc_item:
                disc_item.setText(new_text)
        finally:
            table.blockSignals(was_blocked)

        self.parent_widget.recalculate_row(row, source_column=COL_DISC, live_value=new_text)
        if hasattr(self.parent_widget, 'update_discount_status_label'):
            self.parent_widget.update_discount_status_label(row)
        QCoreApplication.processEvents()

    def _goto(self, row, col):
        """Move to (row, col) and open editor with text selected."""
        if self.parent_widget:
            self.parent_widget.focus_table_cell_editor(row, col)

    def _on_editor_changed(self, index, text):
        """Live recalculation as user types in a numeric cell.
        Passes source_column + live text so the engine uses the typed value,
        not the stale committed cell value.
        """
        col = index.column()
        if col in (COL_RATE, COL_QTY, COL_GROSS, COL_DISC,
                   COL_CGST, COL_SGST, COL_IGST, COL_CESS):
            if self.parent_widget:
                self.parent_widget.recalculate_row(
                    index.row(),
                    source_column=col,
                    live_value=text,
                )