"""
Stock Adjustment Table Delegate

Handles inline editing for Stock Adjustment items table.
Supports single-click editing, select-all on focus, stable inline behavior.
"""

from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QDoubleValidator, QPen, QColor

from .sales_entry_popup import setup_product_completer
from ui import theme


class StockAdjustmentDelegate(QStyledItemDelegate):
    """Delegate for Stock Adjustment items table."""
    
    def __init__(self, parent=None):
        table = getattr(parent, "items_table", parent)
        super().__init__(table)
        self.parent_widget = parent if hasattr(parent, "items_table") else None
        self.current_index = None
    
    def paint(self, painter, option, index):
        """Override paint to draw outline-only selection across the entire row (Sales Entry pattern)."""
        table = self.parent_widget.items_table if self.parent_widget else None
        if not table:
            super().paint(painter, option, index)
            return
        
        row = index.row()
        # Use custom rewrite selection instead of Qt selectionModel
        is_selected = (
            self.parent_widget
            and hasattr(self.parent_widget, "manually_selected_row")
            and self.parent_widget.manually_selected_row == row
        )
        
        if is_selected:
            # Draw outline selection for entire row
            # First draw the normal item background (transparent)
            option.backgroundBrush = Qt.NoBrush
            super().paint(painter, option, index)
            
            # Then draw blue border outline around the row
            rect = option.rect
            
            # Get row rect (across all columns)
            row_rect = table.visualRect(table.model().index(row, 0))
            last_col_rect = table.visualRect(table.model().index(row, table.columnCount() - 1))
            row_rect.setWidth(last_col_rect.right() - row_rect.left())
            row_rect.setHeight(last_col_rect.bottom() - row_rect.top())
            
            # Draw blue border
            pen = QPen(QColor(theme.grid_selection_pen_color()))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(row_rect)
        else:
            # Normal paint for non-selected items
            super().paint(painter, option, index)
    
    def createEditor(self, parent, option, index):
        """Create editor for editable columns."""
        column = index.column()
        
        # Get initial text from table item BEFORE creating editor
        table = self.parent_widget.items_table if self.parent_widget else None
        initial_text = ""
        if table:
            item = table.item(index.row(), index.column())
            if item:
                initial_text = item.text()
        
        # Editable columns: Physical Qty (4), Reason (8) only - all others read-only
        if column in [4, 8]:
            editor = QLineEdit(parent)
            theme.prepare_billing_cell_editor(editor)
            
            # Block editor signals while setting initial text
            editor.blockSignals(True)
            editor.setText(initial_text)
            editor.blockSignals(False)
            
            # Add validator for numeric columns (Physical Qty only)
            if column == 4:
                validator = QDoubleValidator()
                validator.setDecimals(2)
                editor.setValidator(validator)
            
            # Install event filter for keyboard handling
            editor.installEventFilter(self)
            
            # Store current index
            self.current_index = index
            
            # Connect textEdited for live calculation (Sales Entry pattern)
            editor.textEdited.connect(lambda text, idx=index: self.on_editor_changed(idx, text))
            
            QTimer.singleShot(0, editor.selectAll)
            
            return editor
        
        return None  # Read-only columns

    def updateEditorGeometry(self, editor, option, index):
        """Stretch the editor to fill the full cell area."""
        editor.setGeometry(option.rect)
    
    def setEditorData(self, editor, index):
        """Set editor data from model."""
        # If editor already has text (set in createEditor), don't overwrite it
        current_editor_text = editor.text()
        if current_editor_text and current_editor_text != "":
            return
        
        table = self.parent_widget.items_table if self.parent_widget else None
        if table:
            item = table.item(index.row(), index.column())
            if item:
                text = item.text()
            else:
                text = ""
        else:
            text = index.model().data(index, Qt.EditRole) or ""
        
        editor.setText(str(text) if text else "")
    
    def setModelData(self, editor, model, index):
        """Set model data from editor."""
        text = editor.text().strip()
        model.setData(index, text, Qt.EditRole)
    
    def closeEditor(self, editor, hint=QStyledItemDelegate.SubmitModelCache):
        """Close editor and clear index reference."""
        self.current_index = None
        super().closeEditor(editor, hint)
    
    def eventFilter(self, editor, event):
        """Filter keyboard events for custom Enter/Esc/Tab flow and special field behaviors."""
        if event.type() == QEvent.KeyPress:
            key = event.key()
            
            # Check if completer popup is visible - let it handle Up/Down/Enter/Esc
            completer = editor.completer()
            if completer and completer.popup().isVisible():
                # Let completer handle all navigation keys
                if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
                    return False
            
            # Enter: commit and move forward
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._handle_enter(editor)
                return True
            
            # Esc: close and move backward
            if key == Qt.Key_Escape:
                self._handle_esc(editor)
                return True
            
            # Tab: stop default navigation
            if key == Qt.Key_Tab:
                return True
        
        return super().eventFilter(editor, event)
    
    def _handle_enter(self, editor):
        """Commit editor, close it, then move to next cell."""
        if not self.parent_widget or not self.current_index:
            return
        row = self.current_index.row()
        col = self.current_index.column()
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QStyledItemDelegate.SubmitModelCache)
        QTimer.singleShot(10, lambda: self._move_enter(row, col))
    
    def _move_enter(self, row, col):
        """Move to next cell in Enter flow: Physical Qty(4) → Reason(8) → TOP BAR Barcode."""
        table = self.parent_widget.items_table
        if col == 4:
            self._move_to_cell(row, 8)
        elif col == 8:
            # After Reason Enter, move to TOP BAR barcode_input (Sales Entry pattern)
            self.parent_widget.barcode_input.setFocus()
            self.parent_widget.barcode_input.selectAll()
    
    def _handle_esc(self, editor):
        """Close editor, then move to previous cell."""
        if not self.parent_widget or not self.current_index:
            return
        row = self.current_index.row()
        col = self.current_index.column()
        self.closeEditor.emit(editor, QStyledItemDelegate.SubmitModelCache)
        QTimer.singleShot(10, lambda: self._move_esc(row, col))
    
    def _move_esc(self, row, col):
        """Move to previous cell in Esc flow: Reason(8) → Physical Qty(4) → TOP BAR Barcode."""
        table = self.parent_widget.items_table
        if col == 8:
            self._move_to_cell(row, 4)
        elif col == 4:
            # Esc from Physical Qty goes to barcode_input (top bar)
            self.parent_widget.barcode_input.setFocus()
    
    def _move_to_cell(self, row, col):
        """Move to cell and open editor with select-all."""
        table = self.parent_widget.items_table
        if row < 0 or row >= table.rowCount():
            return
        item = table.item(row, col)
        if not item:
            return
        table.scrollToItem(item)
        table.setFocus()
        table.setCurrentCell(row, col)
        idx = table.model().index(row, col)
        if idx.isValid():
            table.edit(idx)
            # Select all text in editor (Sales Entry pattern)
            QTimer.singleShot(0, lambda: self._select_editor_all())

    def _select_editor_all(self):
        """Select all text in current editor."""
        from PySide6.QtWidgets import QLineEdit
        widget = self.parent_widget.focusWidget()
        if isinstance(widget, QLineEdit):
            widget.selectAll()
    
    def on_editor_changed(self, index, text):
        """Handle live text change for immediate calculation (Sales Entry pattern)."""
        if not self.parent_widget:
            return
        
        row = index.row()
        column = index.column()
        
        # Live calculation for Physical Qty (4) and Rate (6)
        if column in [4, 6]:
            try:
                table = self.parent_widget.items_table
                was_blocked = table.blockSignals(True)
                
                try:
                    # Get current values
                    physical_qty = self.parent_widget.safe_float_from_cell(row, 4, 0) if column != 4 else float(text or 0)
                    rate = self.parent_widget.safe_float_from_cell(row, 6, 0) if column != 6 else float(text or 0)
                    
                    # Update source field in table
                    if column == 4:
                        qty_item = table.item(row, 4)
                        if qty_item:
                            qty_item.setText(str(physical_qty))
                    elif column == 6:
                        rate_item = table.item(row, 6)
                        if rate_item:
                            rate_item.setText(str(rate))
                    
                    # Calculate difference qty
                    system_qty_item = table.item(row, 3)
                    system_qty = float(system_qty_item.text()) if system_qty_item else 0.0
                    diff_qty = physical_qty - system_qty
                    
                    # Update difference qty
                    diff_qty_item = table.item(row, 5)
                    if diff_qty_item:
                        diff_qty_item.setText(f"{diff_qty:.2f}")
                    
                    # Calculate value
                    value = diff_qty * rate
                    
                    # Update value
                    value_item = table.item(row, 7)
                    if value_item:
                        value_item.setText(f"{value:.2f}")
                    
                    # Update totals
                    self.parent_widget._update_totals()
                    
                finally:
                    table.blockSignals(was_blocked)
                
            except (ValueError, AttributeError):
                pass