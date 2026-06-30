"""
Purchase Bill table delegate for Purchase Entry widget.
Contains PurchaseBillDelegate with custom painting, editor creation, and keyboard flow.
"""

from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QStyle, QMessageBox, QStyleOptionViewItem
from PySide6.QtCore import Qt, QEvent, QModelIndex, QTimer
from PySide6.QtGui import QPen, QColor

from .purchase_entry_popup import ProductPopupDelegate, setup_product_completer
from .purchase_entry_helpers import clear_product_linked_row_data
from ui import theme

# Column index constants for Purchase Entry table
COL_SL = 0
COL_SALES_RATE = 1   # Read-only display: product sales price
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

class PurchaseBillDelegate(QStyledItemDelegate):
    """Custom delegate for Purchase Bill table with outline-only selection and exact keyboard flow."""
    
    def __init__(self, parent_widget=None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.current_editor = None
        self.current_index = None
        self.is_editing = False
        self.qty_invalid = False
    
    def paint(self, painter, option, index):
        """Draw normal cells without Qt blue fill; draw a blue outline only for SL-selected row."""
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

        # Draw a continuous row outline using per-cell top/bottom lines and edge caps.
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

    def createEditor(self, parent, option, index):
        """Create editor for table cell."""
        column = index.column()

        table = self.parent_widget.items_table if self.parent_widget else None
        initial_text = ""
        if table:
            item = table.item(index.row(), index.column())
            if item:
                initial_text = item.text()

        if table:
            table.blockSignals(True)

        # Make SL and Sales Rate columns read-only
        if column in (COL_SL, COL_SALES_RATE):
            if table:
                table.blockSignals(False)
            return None

        # Make inactive tax columns read-only based on nature
        if self.parent_widget and hasattr(self.parent_widget, 'is_local_tax'):
            is_local = self.parent_widget.is_local_tax
            if is_local:
                # Local: IGST column is inactive
                if column == COL_IGST:
                    if table:
                        table.blockSignals(False)
                    return None
            else:
                # Inter-state: CGST and SGST columns are inactive
                if column in [COL_CGST, COL_SGST]:
                    if table:
                        table.blockSignals(False)
                    return None
        
        editor = QLineEdit(parent)
        self._prepare_billing_cell_editor(editor)
        editor.setText(initial_text)
        # Ensure editor can receive focus
        editor.setFocusPolicy(Qt.StrongFocus)
        # Auto-select all when editor is created
        QTimer.singleShot(0, editor.selectAll)

        # Setup product completer for Product column
        if column == COL_PRODUCT:
            setup_product_completer(editor, self.parent_widget, index, self.on_product_selected)

        if table:
            table.blockSignals(False)

        # Store current index
        self.current_index = index
        self.current_editor = editor
        self.editor_initialized = True
        self.initial_text = initial_text

        # Connect to textEdited for immediate live calculation (fires only on user edits, not programmatic changes)
        editor.textEdited.connect(lambda text, idx=index: self.on_editor_changed(idx, text))

        # Install event filter for Enter/Esc handling and focus/mouse select all
        editor.installEventFilter(self)
        
        return editor
    
    def setEditorData(self, editor, index):
        """Set editor data from table cell."""
        table = self.parent_widget.items_table if self.parent_widget else None
        if table:
            table.blockSignals(True)
        
        text = index.model().data(index, Qt.EditRole)
        if text:
            editor.setText(text)
        
        self.editor_initialized = True
        self.initial_text = text or ""
        
        if table:
            table.blockSignals(False)
    
    def setModelData(self, editor, model, index):
        """Set model data from editor without clearing product rows on focus/click."""
        table = self.parent_widget.items_table if self.parent_widget else None
        if not table:
            return

        new_text = editor.text()
        row = index.row()
        column = index.column()

        # Capture existing table text BEFORE writing model data.
        old_text = ""
        old_item = table.item(row, column)
        if old_item:
            old_text = old_item.text()

        was_blocked = table.blockSignals(True)
        try:
            if column == COL_PRODUCT:
                # Opening/clicking/selecting an editor must never wipe an existing product row.
                # If the editor text is unchanged, just preserve the value and return.
                if new_text == old_text:
                    model.setData(index, old_text, Qt.EditRole)
                    return

                # If an existing product cell is accidentally committed blank by editor lifecycle,
                # preserve the old product and all linked values. Intentional product clearing can
                # be handled later with a dedicated command, not by a normal click/focus.
                if old_text.strip() and not new_text.strip():
                    model.setData(index, old_text, Qt.EditRole)
                    return

                model.setData(index, new_text, Qt.EditRole)
            else:
                model.setData(index, new_text, Qt.EditRole)
        finally:
            table.blockSignals(was_blocked)

        if column == COL_PRODUCT:
            if self.parent_widget and self.parent_widget._product_selection_in_progress:
                return
            if new_text.strip() and new_text != old_text:
                self.handle_product_change(index, new_text)

    def on_product_selected(self, index, model_idx, editor):
        """Handle product selection from completer popup."""
        # Set guard flag to prevent duplicate processing
        if self.parent_widget:
            self.parent_widget._product_selection_in_progress = True

        product = model_idx.data(Qt.UserRole)
        if product:
            self.handle_product_change(index, product)

        # Reset guard flag after processing
        if self.parent_widget:
            self.parent_widget._product_selection_in_progress = False
    
    def handle_product_change(self, index, product_or_name):
        """Handle product name change or product selection."""
        table = self.parent_widget.items_table if self.parent_widget else None
        if not table:
            return

        row = index.row()

        # Check if product_or_name is a dict (from popup) or string (manual entry)
        if isinstance(product_or_name, dict):
            product = product_or_name
            product_name = product['name']
        else:
            product_name = product_or_name
            # Find product by name
            product = None
            for p in self.parent_widget.products_data:
                if p['name'] == product_name:
                    product = p
                    break

        if product:
            # Populate basic product-linked fields (HSN, Rate)
            hsn = product.get('hsn', '')
            # Use purchase_rate for purchase entry (not sale_price)
            rate = product.get('purchase_rate', 0)

            table.blockSignals(True)

            # Sales Rate (read-only display of product sales price)
            sales_rate = product.get('sale_price', 0) or product.get('sales_rate', 0) or 0
            sales_rate_item = table.item(row, COL_SALES_RATE)
            if sales_rate_item:
                sales_rate_item.setText(f"{float(sales_rate):.2f}")

            # HSN
            hsn_item = table.item(row, COL_HSN)
            if hsn_item:
                hsn_item.setText(str(hsn))

            # Rate
            rate_item = table.item(row, COL_RATE)
            if rate_item:
                rate_item.setText(str(rate))

            table.blockSignals(False)

            # Update internal purchase_items data for product_id, hsn, rate
            if row < len(self.parent_widget.purchase_items):
                self.parent_widget.purchase_items[row]['product_id'] = product['id']
                self.parent_widget.purchase_items[row]['hsn'] = hsn
                self.parent_widget.purchase_items[row]['rate'] = rate
                self.parent_widget.purchase_items[row]['source_cgst'] = float(product.get('cgst', 0) or 0)
                self.parent_widget.purchase_items[row]['source_sgst'] = float(product.get('sgst', 0) or 0)
                self.parent_widget.purchase_items[row]['source_igst'] = float(product.get('igst', 0) or 0)
                self.parent_widget.purchase_items[row]['source_cess'] = float(product.get('cess', 0) or 0)

            # Apply tax based on current nature using helper
            if hasattr(self.parent_widget, '_apply_nature_tax_to_row'):
                self.parent_widget._apply_nature_tax_to_row(row, product)

            # Recalculate row and totals
            # Note: recalculate_row will call calculate_totals when source_column is None
            self.parent_widget.recalculate_row(row)
        else:
            # Product not found or cleared
            # Only clear row data if user intentionally cleared the product name
            # (old text was not blank, new text is blank)
            if self.initial_text and self.initial_text.strip() and not product_name.strip():
                clear_product_linked_row_data(table, row, self.parent_widget.purchase_items)
                self.parent_widget.recalculate_row(row)
                self.parent_widget.calculate_totals()
            # Otherwise, preserve existing row data (editor temporarily blank)

    def eventFilter(self, obj, event):
        """Event filter for Enter/Esc/F2 keyboard handling and focus/mouse select all in editor."""
        # Handle FocusIn and MouseButtonPress for select all
        if event.type() in [QEvent.FocusIn, QEvent.MouseButtonPress] and obj == self.current_editor:
            if isinstance(obj, QLineEdit):
                QTimer.singleShot(0, obj.selectAll)
            # Return True for MouseButtonPress to prevent default cursor positioning
            if event.type() == QEvent.MouseButtonPress:
                return True
            return False  # Let FocusIn propagate normally

        if event.type() == QEvent.KeyPress and obj == self.current_editor:
            key = event.key()

            if key == Qt.Key_F2:
                # F2 key - open Product master in edit mode from Qty field
                if self.current_index.column() == COL_QTY:
                    self.open_product_master_edit_flow()
                return True

            elif key == Qt.Key_Return or key == Qt.Key_Enter:
                # Enter key - commit and handle navigation
                table = self.parent_widget.items_table if self.parent_widget else None
                if table:
                    current_row = self.current_index.row()
                    current_col = self.current_index.column()

                    # Commit editor data
                    self.commitData.emit(self.current_editor)
                    self.closeEditor.emit(self.current_editor, QStyledItemDelegate.SubmitModelCache)

                    # Product column: unlinked typed text opens Product Entry
                    # with that name prefilled; committed products move forward.
                    if current_col == COL_PRODUCT:
                        product_text = ""
                        item = table.item(current_row, COL_PRODUCT)
                        if item:
                            product_text = item.text().strip()
                        if not product_text:
                            self.open_product_master_add_flow(current_row)
                        elif (
                            self.parent_widget
                            and hasattr(self.parent_widget, 'handle_product_cell_enter')
                            and self.parent_widget.handle_product_cell_enter(current_row, product_text)
                        ):
                            return True
                        else:
                            self.move_to_cell_and_select_all(current_row, COL_HSN)
                        return True

                    if current_col == COL_HSN:
                        if self.parent_widget and getattr(self.parent_widget, 'is_local_tax', True):
                            self.move_to_cell_and_select_all(current_row, COL_CGST)
                        else:
                            self.move_to_cell_and_select_all(current_row, COL_IGST)
                        return True

                    if current_col == COL_CGST:
                        self.move_to_cell_and_select_all(current_row, COL_SGST)
                        return True

                    if current_col in (COL_SGST, COL_IGST, COL_CESS):
                        self.move_to_cell_and_select_all(current_row, COL_RATE)
                        return True

                    if current_col == COL_RATE:
                        self.move_to_cell_and_select_all(current_row, COL_QTY)
                        return True

                    if current_col == COL_GROSS:
                        self.move_to_cell_and_select_all(current_row, COL_DISC)
                        return True

                    # Handle Enter in Qty column - move to Disc column of same row
                    if current_col == COL_QTY:
                        self.move_to_cell_and_select_all(current_row, COL_DISC)
                        return True

                    # Enter flow: Disc -> next row Product, or back to barcode
                    # entry when this is the last product row.
                    if current_col == COL_DISC:
                        next_row = current_row + 1
                        if next_row < table.rowCount():
                            self.move_to_cell_and_select_all(next_row, COL_PRODUCT)
                        else:
                            if self.parent_widget and hasattr(self.parent_widget, 'barcode_input'):
                                self.parent_widget.barcode_input.setFocus()
                        return True

                return True

            elif key == Qt.Key_Escape:
                # Esc key - revert and move to previous editable cell
                table = self.parent_widget.items_table if self.parent_widget else None
                if table:
                    current_row = self.current_index.row()
                    current_col = self.current_index.column()

                    # Revert editor data
                    if self.initial_text:
                        self.current_editor.setText(self.initial_text)
                    self.closeEditor.emit(self.current_editor, QStyledItemDelegate.RevertModelCache)

                    # Esc flow: Disc -> Qty -> Rate -> HSN -> Product -> Barcode
                    if current_col == COL_DISC:
                        self.move_to_cell_and_select_all(current_row, COL_QTY)
                    elif current_col == COL_QTY:
                        self.move_to_cell_and_select_all(current_row, COL_RATE)
                    elif current_col == COL_RATE:
                        self.move_to_cell_and_select_all(current_row, COL_HSN)
                    elif current_col == COL_HSN:
                        self.move_to_cell_and_select_all(current_row, COL_PRODUCT)
                    elif current_col == COL_PRODUCT:
                        # Move to barcode input field
                        if hasattr(self.parent_widget, 'barcode_input'):
                            self.parent_widget.barcode_input.setFocus()

                return True

            elif key == Qt.Key_Down:
                # Down Arrow interprets the typed number as a PERCENTAGE of the row
                # gross and rewrites the Disc cell to the equivalent FLAT cash value.
                if self.current_index and self.current_index.column() == COL_DISC:
                    self.handle_disc_percent_conversion(obj)
                    return True
                # Any other column: allow normal caret navigation.
                return super().eventFilter(obj, event)

        if event.type() == QEvent.FocusOut and obj == self.current_editor:
            if (
                self.current_index is not None
                and self.current_index.column() == COL_PRODUCT
                and self.parent_widget
                and hasattr(self.parent_widget, '_clear_uncommitted_product_cell')
            ):
                row = self.current_index.row()
                QTimer.singleShot(
                    0,
                    lambda row=row: self.parent_widget._clear_uncommitted_product_cell(row),
                )

        return super().eventFilter(obj, event)

    def handle_disc_percent_conversion(self, editor):
        """Convert a typed percentage into the equivalent flat cash discount.

        The user types a percent (e.g. 5) in the Disc cell and presses Down: the
        cell is rewritten to the computed flat amount (5% of gross 500 -> "25.00"),
        which the engine then treats as an ordinary cash reduction. The top bar
        tracker subsequently reads out the equivalent percentage ("5.00%").
        Signals are blocked during the rewrite to avoid recursive triggers.
        """
        if not self.parent_widget or not self.current_index:
            return

        row = self.current_index.row()

        # Parse the typed value (strip any stray % sign) as a percentage.
        raw = editor.text() if editor else self.parent_widget.safe_item_text(row, COL_DISC, "0")
        raw = str(raw).replace('%', '').strip()
        if not raw:
            return
        try:
            percent = float(raw)
        except ValueError:
            return

        # Base = Gross column, falling back to Rate x Qty when Gross is empty.
        gross = self.parent_widget.safe_float_from_cell(row, COL_GROSS, 0)
        if gross <= 0:
            rate = self.parent_widget.safe_float_from_cell(row, COL_RATE, 0)
            qty = self.parent_widget.safe_float_from_cell(row, COL_QTY, 0)
            gross = rate * qty
        if gross <= 0:
            return
        if percent > 100:
            percent = 100.0

        flat_amount = round(gross * percent / 100.0, 2)
        new_text = f"{flat_amount:.2f}"

        if editor:
            editor.blockSignals(True)
            editor.setText(new_text)
            editor.blockSignals(False)
            editor.setCursorPosition(len(new_text))

        table = self.parent_widget.items_table
        disc_item = table.item(row, COL_DISC)
        if disc_item:
            was_blocked = table.blockSignals(True)
            disc_item.setText(new_text)
            table.blockSignals(was_blocked)

        # The row now carries a flat cash discount.
        items = getattr(self.parent_widget, 'purchase_items', None)
        if items is not None and row < len(items):
            items[row]['disc_mode'] = 'flat'

        # Recalculate using the flat amount (editor stays open).
        self.parent_widget.recalculate_row(row, source_column=COL_DISC, live_value=new_text)

        # Refresh the live top bar discount tracker immediately.
        if hasattr(self.parent_widget, 'update_discount_status_label'):
            self.parent_widget.update_discount_status_label(row)

    def move_to_cell_and_select_all(self, row, col):
        """Helper to move to cell and select all text in editor."""
        table = self.parent_widget.items_table if self.parent_widget else None
        if not table:
            return

        item = table.item(row, col)
        if not item:
            return

        # Set current cell and scroll to item
        table.setCurrentCell(row, col)
        table.scrollToItem(item)

        # Ensure table has focus first
        table.setFocus()

        # Open editor - createEditor will handle selection
        table.editItem(item)

    def _select_current_editor(self):
        """Select all text in the current table editor."""
        table = self.parent_widget.items_table if self.parent_widget else None
        if not table:
            return

        editor = table.focusWidget()
        if editor and isinstance(editor, QLineEdit):
            # Just focus and select all - don't set cursor position
            editor.setFocus()
            editor.selectAll()
            # Another timer to ensure focus and selection are applied
            QTimer.singleShot(100, lambda: self._ensure_selection(editor))

    def _ensure_selection(self, editor):
        """Ensure selection is applied to the editor."""
        if editor and isinstance(editor, QLineEdit):
            editor.setFocus()
            editor.selectAll()

    def _editor_select_and_focus(self, editor):
        """Select all and focus editor with delay."""
        if editor:
            editor.setFocus()
            editor.selectAll()

    def _force_editor_focus(self):
        """Force the current editor to have focus."""
        table = self.parent_widget.items_table if self.parent_widget else None
        if not table:
            return

        editor = table.focusWidget()
        if editor and isinstance(editor, QLineEdit):
            editor.setFocus()
            editor.selectAll()

    def open_product_master_add_flow(self, row):
        """Open Product master in add mode for the current row."""
        # Call parent method to open Product Entry in new mode
        self.parent_widget.open_product_entry_new_from_row(row)
    
    def open_product_master_edit_flow(self):
        """Open Product master in edit mode for the current row's product."""
        row = self.current_index.row()
        # Get product_id from purchase_items directly
        if row < len(self.parent_widget.purchase_items):
            product_id = self.parent_widget.purchase_items[row].get('product_id')
            if product_id:
                # Call parent method to open Product Entry in edit mode
                self.parent_widget.open_product_entry_edit_from_row(row, product_id)
            else:
                QMessageBox.warning(self.parent_widget, "No Product", "Please select a product first.")
        else:
            QMessageBox.warning(self.parent_widget, "No Product", "Please select a product first.")

    def on_editor_changed(self, index, text):
        """Handle live editor text change for immediate calculation."""
        column = index.column()

        # Recalculate for all numeric columns including Gross and tax columns
        if column in [COL_RATE, COL_QTY, COL_GROSS, COL_DISC, COL_CGST, COL_SGST, COL_IGST, COL_CESS]:
            row = index.row()
            # Recalculate row with live value
            # Note: recalculate_row now always calls calculate_totals for live updates
            self.parent_widget.recalculate_row(row, source_column=column, live_value=text)