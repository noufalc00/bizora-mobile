"""
Sales Bill table delegate for Sales Entry widget.
Contains SalesBillDelegate with custom painting, editor creation, and keyboard flow.
"""

from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QCompleter, QStyle, QMessageBox
from PySide6.QtCore import Qt, QTimer, QEvent, QModelIndex
from PySide6.QtGui import QPen, QColor, QStandardItemModel, QStandardItem

from .sales_entry_popup import ProductPopupDelegate, setup_product_completer
from .sales_entry_helpers import clear_product_linked_row_data
from ui import theme

# Column index constants for Sales Entry table
COL_SL = 0
COL_PRODUCT = 1
COL_HSN = 2
COL_CGST = 3
COL_SGST = 4
COL_IGST = 5
COL_CESS = 6
COL_RATE = 7
COL_QTY = 8
COL_GROSS = 9
COL_DISC = 10
COL_NET = 11
COL_TAX = 12
COL_TOTAL = 13

class SalesBillDelegate(QStyledItemDelegate):
    """Custom delegate for Sales Bill table with outline-only selection and exact keyboard flow."""
    
    def __init__(self, parent_widget=None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.current_editor = None
        self.current_index = None
        self.is_editing = False  # Flag to track if user is actively typing in editor
        self.editor_initialized = False  # Flag to track if editor has been initialized with data
        self.initial_text = ""  # Store the initial text to distinguish from user edits
        self.table_was_blocked = False  # Track if table signals were blocked
        self.is_local_tax = True  # Default to Local (CGST/SGST active)
        self.qty_invalid = False
        
        # Determine mode from parent widget
        self.mode = "sales"
        if parent_widget:
            name = parent_widget.__class__.__name__
            if name == "VanEntryWidget":
                self.mode = "van_entry"
            elif name == "VanReturnWidget":
                self.mode = "van_return"
    
    def _outline_last_column(self, table):
        """Return the last visible column used to span the row-selection outline."""
        for col in range(table.columnCount() - 1, -1, -1):
            if not table.isColumnHidden(col):
                return col
        return max(0, table.columnCount() - 1)

    def paint(self, painter, option, index):
        """Override paint to draw outline-only selection across the entire row."""
        table = self._delegate_table()
            
        if not table:
            super().paint(painter, option, index)
            return
        
        row = index.row()
        column = index.column()
        # Highlight the active edit cell with themed background and border.
        is_editing_cell = (
            self.current_index is not None
            and self.current_editor is not None
            and self.current_index.row() == row
            and self.current_index.column() == column
        )
        if is_editing_cell:
            painter.fillRect(option.rect, QColor(theme.billing_cell_edit_background()))
            option.backgroundBrush = Qt.NoBrush
            super().paint(painter, option, index)
            pen = QPen(QColor(theme.grid_selection_pen_color()))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
            return

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
            
            # Get row rect across visible columns (skip hidden product-id cols).
            row_rect = table.visualRect(table.model().index(row, 0))
            last_col = self._outline_last_column(table)
            last_col_rect = table.visualRect(table.model().index(row, last_col))
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
    
    def _prepare_billing_cell_editor(self, editor: QLineEdit) -> None:
        """Configure in-cell editor styling to match Sales Entry."""
        if self.parent_widget and self.parent_widget.__class__.__name__ in (
            "SalesEntryWidget",
            "VanEntryWidget",
            "VanReturnWidget",
        ):
            theme.prepare_sales_cell_editor(editor)
        else:
            theme.prepare_billing_cell_editor(editor)

    def _delegate_table(self):
        """Resolve the active table widget for the current delegate mode."""
        if not self.parent_widget:
            return None
        if self.mode == "sales":
            return self.parent_widget.items_table
        if self.mode == "van_return":
            return getattr(self.parent_widget, "stock_table", None)
        return getattr(self.parent_widget, "table", getattr(self.parent_widget, "items_table", None))

    def _select_all_editor_text(self, editor: QLineEdit) -> None:
        """Select all text when a cell editor opens for immediate overwrite."""
        QTimer.singleShot(0, editor.selectAll)

    def _track_editing_cell(self, editor: QLineEdit, index) -> None:
        """Remember the active editor and repaint its cell border highlight."""
        self.current_editor = editor
        self.current_index = index
        QTimer.singleShot(0, lambda: self._refresh_editing_cell_paint(index))

    def updateEditorGeometry(self, editor, option, index):
        """Stretch the editor to fill the full cell area."""
        editor.setGeometry(option.rect)
    
    def createEditor(self, parent, option, index):
        """Create editor for table cell."""
        column = index.column()
        
        # CRITICAL: Get initial text from table item BEFORE creating editor
        if self.mode == "sales":
            table = self.parent_widget.items_table if self.parent_widget else None
        else:
            table = self._delegate_table()
            
        initial_text = ""
        if table:
            item = table.item(index.row(), index.column())
            if item:
                initial_text = item.text()
        
        # CRITICAL: Block table signals during editor creation to prevent cellChanged from firing
        # and clearing data before setEditorData can populate the editor
        if table:
            self.table_was_blocked = table.blockSignals(True)
        
        # Tax field activation based on Nature (Local vs Inter-state)
        # CGST (3), SGST (4) active for Local; IGST (5) active for Inter-state
        if column == 3 and not self.is_local_tax:  # CGST - disable for Inter-state
            return None
        if column == 4 and not self.is_local_tax:  # SGST - disable for Inter-state
            return None
        if column == 5 and self.is_local_tax:  # IGST - disable for Local
            return None
        
        # Numeric columns - use QLineEdit with validator
        if column in [3, 4, 5, 6, 7, 8, 9, 10]:  # CGST, SGST, IGST, CESS, Rate, Qty, Gross, Disc
            editor = QLineEdit(parent)
            self._prepare_billing_cell_editor(editor)
            
            # Do NOT use validator for numeric columns to prevent premature formatting while typing
            # Validation will happen on commit/focus-out instead
            
            # CRITICAL: Block editor signals while setting initial text
            editor.blockSignals(True)
            editor.setText(initial_text)
            editor.blockSignals(False)
            
            # Install event filter for keyboard handling
            editor.installEventFilter(self)
            
            # Store current index
            self._track_editing_cell(editor, index)
            self.qty_invalid = False
            self.editor_initialized = True  # Mark as initialized since we set text here
            self.initial_text = initial_text  # Store initial text
            
            # Connect to textEdited for immediate live calculation (fires only on user edits, not programmatic changes)
            editor.textEdited.connect(lambda text, idx=index: self.on_editor_changed(idx, text))
            
            self._select_all_editor_text(editor)
            return editor
        
        # Product column - with completer for product search
        elif column == 1:  # Product
            editor = QLineEdit(parent)
            self._prepare_billing_cell_editor(editor)
            # CRITICAL: Block editor signals while setting initial text
            editor.blockSignals(True)
            editor.setText(initial_text)
            editor.blockSignals(False)
            
            # Install event filter for keyboard handling
            editor.installEventFilter(self)
            
            # Store current index
            self._track_editing_cell(editor, index)
            self.qty_invalid = False  # Reset qty_invalid for each new editor to prevent stale state
            self.editor_initialized = True  # Mark as initialized since we set text here
            self.initial_text = initial_text  # Store initial text
            
            # Connect to textEdited for live recalculation
            editor.textEdited.connect(lambda text, idx=index: self.on_editor_changed(idx, text))
            
            # Set up completer for product search
            if self.parent_widget and hasattr(self.parent_widget, 'products_data'):
                setup_product_completer(editor, self.parent_widget, index, self.on_product_selected)
            
            self._select_all_editor_text(editor)
            return editor
        
        # Other editable columns - HSN, Unit
        elif column == 2:  # HSN
            editor = QLineEdit(parent)
            self._prepare_billing_cell_editor(editor)
            # CRITICAL: Block editor signals while setting initial text
            editor.blockSignals(True)
            editor.setText(initial_text)
            editor.blockSignals(False)
            
            # Install event filter for keyboard handling
            editor.installEventFilter(self)
            
            # Store current index
            self._track_editing_cell(editor, index)
            self.qty_invalid = False  # Reset qty_invalid for each new editor to prevent stale state
            self.editor_initialized = True  # Mark as initialized since we set text here
            self.initial_text = initial_text  # Store initial text
            
            # Connect to textEdited for live recalculation
            editor.textEdited.connect(lambda text, idx=index: self.on_editor_changed(idx, text))
            
            self._select_all_editor_text(editor)
            return editor
        
        # Other columns - use standard QLineEdit
        else:
            editor = QLineEdit(parent)
            self._prepare_billing_cell_editor(editor)
            # CRITICAL: Block editor signals while setting initial text
            editor.blockSignals(True)
            editor.setText(initial_text)
            editor.blockSignals(False)
            
            # Install event filter for keyboard handling
            editor.installEventFilter(self)
            
            # Store current index
            self._track_editing_cell(editor, index)
            self.qty_invalid = False  # Reset qty_invalid for each new editor to prevent stale state
            self.editor_initialized = True  # Mark as initialized since we set text here
            self.initial_text = initial_text  # Store initial text
            
            self._select_all_editor_text(editor)
            return editor
    
    def setEditorData(self, editor, index):
        """Set editor data from model."""
        # Prevent model from refreshing the active editor while user is typing
        # This is critical to prevent "2.0050" bug when typing multi-digit values
        if self.is_editing and self.current_editor == editor:
            # User is actively editing - do NOT refresh from model
            return
        
        # CRITICAL: Unblock table signals to allow live updates
        # This must happen regardless of whether editor text is overwritten
        if self.mode == "sales":
            table = self.parent_widget.items_table if self.parent_widget else None
        else:
            table = self._delegate_table()
            
        if table and self.table_was_blocked:
            table.blockSignals(False)
            self.table_was_blocked = False
        
        # CRITICAL: If editor already has text (set in createEditor), don't overwrite it
        # This prevents setEditorData from clearing the editor with empty data
        current_editor_text = editor.text()
        if current_editor_text and current_editor_text != "":
            # Editor already has text from createEditor - don't overwrite
            # Mark that editor has been initialized with data
            self.editor_initialized = True
            return
        
        # CRITICAL: Get text directly from table item instead of model data
        # QTableWidget stores data in items, not in a separate model
        if table:
            item = table.item(index.row(), index.column())
            if item:
                text = item.text()
            else:
                text = ""
        else:
            # Fallback to model data if table not available
            text = index.model().data(index, Qt.EditRole)
            if text is None or text == "":
                text = index.model().data(index, Qt.DisplayRole)
        
        # Store initial text to distinguish from user edits
        self.initial_text = str(text) if text else ""
        
        # CRITICAL: Set initial text
        editor.setText(self.initial_text)
        
        # Mark that editor has been initialized with data
        self.editor_initialized = True
    
    def closeEditor(self, editor, hint=QStyledItemDelegate.SubmitModelCache):
        """Close editor and clear editing flag."""
        closed_index = self.current_index
        self.is_editing = False
        self.editor_initialized = False
        self.qty_invalid = False  # Reset qty_invalid when editor closes to prevent stale state
        self.current_editor = None
        self.current_index = None
        super().closeEditor(editor, hint)
        self._refresh_editing_cell_paint(closed_index)

    def destroyEditor(self, editor, index):
        """Clear edit highlight when the in-cell editor is destroyed."""
        super().destroyEditor(editor, index)
        self._refresh_editing_cell_paint(index)

    def _refresh_editing_cell_paint(self, index):
        """Repaint the cell that was being edited so the border highlight clears."""
        if not index or not index.isValid() or not self.parent_widget:
            return
        if self.mode == "sales":
            table = self.parent_widget.items_table
        else:
            table = getattr(
                self.parent_widget,
                "table",
                getattr(self.parent_widget, "items_table", None),
            )
        if table:
            table.viewport().update()
    
    def setModelData(self, editor, model, index):
        """Set model data from editor."""
        # CRITICAL: Block table signals during setModelData to prevent cellChanged from firing
        # and clearing data during editor initialization
        if self.mode == "sales":
            table = self.parent_widget.items_table if self.parent_widget else None
        else:
            table = self._delegate_table()
            
        was_blocked = False
        if table:
            was_blocked = table.blockSignals(True)
        
        text = editor.text()
        model.setData(index, text, Qt.EditRole)
        
        # Unblock table signals after setting data
        if table and was_blocked:
            table.blockSignals(False)
        
        # FINAL COMMIT PATH: Handle Product column clear
        # This is the guaranteed trigger after editor commits, regardless of how text became empty
        if index.column() == 1 and not text.strip():
            # Product committed as empty - clear all linked fields in the same row
            if self.parent_widget and table:
                clear_product_linked_row_data(table, index.row(), self.parent_widget.sale_items)
                self.parent_widget.calculate_totals()
        
    def on_editor_changed(self, index, text):
        """Handle live text change for immediate calculation."""
        if not self.parent_widget:
            return
        
        # CRITICAL: Ignore events during editor initialization
        # If editor is not yet initialized with data, skip processing
        if not self.editor_initialized:
            return
        
        # CRITICAL: If text matches the initial loaded text, this is not a user edit
        # This prevents overwriting the cell with the same value during initialization
        if text == self.initial_text and not self.is_editing:
            return
        
        # CRITICAL: If text is empty and this is the first signal after initialization,
        # it may be a spurious event - skip it to avoid overwriting cell with blank
        # EXCEPTION: Allow empty text for Product column to enable live clearing
        if text == "" and not self.is_editing and index.column() != 1:
            return
        
        # Mark that user is actively editing (set flag when user actually types)
        self.is_editing = True
        
        row = index.row()
        column = index.column()
        
        # Ensure row items are initialized if function exists
        if hasattr(self.parent_widget, "ensure_row_items_initialized"):
            self.parent_widget.ensure_row_items_initialized(row)
        
        # Van Entry handling
        if self.mode == "van_entry":
            if column in [1, 3, 4]:
                try:
                    table = self.parent_widget.table
                    was_blocked = table.blockSignals(True)
                    try:
                        if column == 3:
                            it = table.item(row, 3)
                            if it: it.setText(text)
                        elif column == 4:
                            it = table.item(row, 4)
                            if it: it.setText(text)
                        
                        if column == 1 and hasattr(self.parent_widget, "_add_product_to_table"):
                            # The completer will handle product selection, no need to auto-fill here
                            pass
                    finally:
                        table.blockSignals(was_blocked)
                except Exception:
                    pass
            return
            
        # Van Return handling
        if self.mode == "van_return":
            if column in [1, 2, 3]:  # Product, Return Qty, Return Rate
                try:
                    table = getattr(self.parent_widget, "stock_table", None)
                    if table:
                        was_blocked = table.blockSignals(True)
                        try:
                            it = table.item(row, column)
                            if it: it.setText(text)
                        finally:
                            table.blockSignals(was_blocked)
                except Exception:
                    pass
            return

        # For all editable fields, trigger recalculation
        if column in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:  # Product, HSN, CGST, SGST, IGST, CESS, Rate, Qty, Gross, Disc
            try:
                # Block table signals to prevent active editor from being refreshed from model
                table = self.parent_widget.items_table
                was_blocked = table.blockSignals(True)
                
                try:
                    # Get current values from table
                    qty = self.parent_widget.safe_float_from_cell(row, 8, 0) if column != 8 else float(text or 0)
                    rate = self.parent_widget.safe_float_from_cell(row, 7, 0) if column != 7 else float(text or 0)
                    disc = self.parent_widget.safe_float_from_cell(row, 10, 0) if column != 10 else float(text or 0)
                    
                    # Calculate total tax percent from CGST + SGST + IGST + CESS
                    cgst = self.parent_widget.safe_float_from_cell(row, 3, 0)
                    sgst = self.parent_widget.safe_float_from_cell(row, 4, 0)
                    igst = self.parent_widget.safe_float_from_cell(row, 5, 0)
                    cess = self.parent_widget.safe_float_from_cell(row, 6, 0)
                    total_tax_percent = cgst + sgst + igst + cess
                    
                    # Calculate gross based on source column
                    if column == 9:
                        gross = float(text or 0)
                        if qty > 0:
                            rate = gross / qty
                    else:
                        gross = rate * qty
                    
                    # CRITICAL: Update the source field in table (not calculated fields)
                    # Use raw string conversion instead of formatting to 2 decimals to prevent editor refresh
                    if column == 7:
                        rate_item = table.item(row, 7)
                        if rate_item:
                            rate_item.setText(str(rate))
                    elif column == 8:
                        qty_item = table.item(row, 8)
                        if qty_item:
                            qty_item.setText(str(qty))
                    elif column == 9:
                        gross_item = table.item(row, 9)
                        if gross_item:
                            gross_item.setText(str(gross))
                    elif column == 10:
                        disc_item = table.item(row, 10)
                        if disc_item:
                            disc_item.setText(str(disc))
                    elif column in (3, 4, 5, 6):  # CGST, SGST, IGST, CESS
                        # Update tax column in table with the live value
                        tax_item = table.item(row, column)
                        if tax_item:
                            tax_item.setText(text)
                    
                    # Call recalculate_row for proper tax calculations (including divide tax mode)
                    from .sales_entry_calculations import recalculate_row
                    recalculate_row(self.parent_widget, row, source_column=column, live_value=text)
                    
                    # Recalculate totals to ensure C/B updates live
                    self.parent_widget.calculate_totals()
                    
                    # Handle Product column - try to auto-fill related fields
                    if column == 1:
                        self.handle_product_change(row, text)
                    
                finally:
                    # Restore signal blocking
                    table.blockSignals(was_blocked)
                
            except (ValueError, AttributeError):
                pass  # Handle invalid numeric input gracefully
    
    def on_product_selected(self, index, model_idx, editor):
        """Handle product selection from completer popup using QModelIndex."""
        if not self.parent_widget:
            return
        
        row = index.row()
        
        # Get product data from QModelIndex UserRole
        product = model_idx.data(Qt.UserRole)
        if not product:
            return
        
        # Update editor text with product name ONLY
        editor.setText(product['name'])
        
        # Auto-fill other fields
        hsn_item = self.parent_widget.items_table.item(row, 2)
        if hsn_item:
            hsn_item.setText(product.get('hsn', ''))
        
        # Set individual tax columns based on Nature
        is_local = True
        if hasattr(self, 'is_local_tax'):
            is_local = self.is_local_tax
        elif hasattr(self.parent_widget, 'nature_combo'):
            is_local = (self.parent_widget.nature_combo.currentText() == "Local")
        
        cgst_item = self.parent_widget.items_table.item(row, 3)
        if cgst_item:
            if is_local:
                cgst_item.setText(f"{product.get('cgst', 0):.2f}")
            else:
                cgst_item.setText("0")
        
        sgst_item = self.parent_widget.items_table.item(row, 4)
        if sgst_item:
            if is_local:
                sgst_item.setText(f"{product.get('sgst', 0):.2f}")
            else:
                sgst_item.setText("0")
        
        igst_item = self.parent_widget.items_table.item(row, 5)
        if igst_item:
            if is_local:
                igst_item.setText("0")
            else:
                igst_item.setText(f"{product.get('igst', 0):.2f}")
        
        cess_item = self.parent_widget.items_table.item(row, 6)
        if cess_item:
            cess_item.setText(str(product.get('cess', 0)))
        
        rate = self.parent_widget.get_product_rate_from_selector(product)
        rate_item = self.parent_widget.items_table.item(row, 7)
        if rate_item:
            rate_item.setText(str(rate))
        
        # Set default Qty to 1 if empty
        qty_item = self.parent_widget.items_table.item(row, 8)
        if qty_item:
            qty_text = qty_item.text().strip()
            if not qty_text or qty_text == "0":
                qty_item.setText("1")
        
        # Calculate total tax percent
        tax_percent = product.get('cgst', 0) + product.get('sgst', 0) + product.get('igst', 0) + product.get('cess', 0)
        
        # Update sale_items
        if row < len(self.parent_widget.sale_items):
            self.parent_widget.sale_items[row]['product_id'] = product['id']
            self.parent_widget.sale_items[row]['hsn'] = product.get('hsn', '')
            self.parent_widget.sale_items[row]['cgst'] = product.get('cgst', 0)
            self.parent_widget.sale_items[row]['sgst'] = product.get('sgst', 0)
            self.parent_widget.sale_items[row]['igst'] = product.get('igst', 0)
            self.parent_widget.sale_items[row]['cess'] = product.get('cess', 0)
            self.parent_widget.sale_items[row]['tax_percent'] = tax_percent
            self.parent_widget.sale_items[row]['rate'] = rate
            self.parent_widget.sale_items[row]['qty'] = 1
        
        # Recalculate row with new values to compute tax correctly
        self.parent_widget.recalculate_row(row)
        self.parent_widget.calculate_totals()
    
    def handle_product_change(self, row, product_text):
        """Handle product text change to auto-fill related fields."""
        if not self.parent_widget or not hasattr(self.parent_widget, 'products_data'):
            return
        
        product_text = product_text.strip().lower()
        if not product_text:
            # Product field cleared - clear all linked fields
            clear_product_linked_row_data(
                self.parent_widget.items_table,
                row,
                self.parent_widget.sale_items
            )
            self.parent_widget.calculate_totals()
            return
        
        # Find matching product via exact-name cache (O(1) instead of full scan)
        product = None
        if hasattr(self.parent_widget, 'products_by_name_exact'):
            product = self.parent_widget.products_by_name_exact.get(product_text)
        # Safe fallback: scan only if cache is unavailable
        if not product:
            for p in self.parent_widget.products_data:
                if p['name'].lower() == product_text:
                    product = p
                    break
        if not product:
            return

        # Auto-fill other fields
        hsn_item = self.parent_widget.items_table.item(row, 2)
        if hsn_item:
            hsn_item.setText(product.get('hsn', ''))

        # Set individual tax columns based on Nature setting using actual product values
        is_local = True
        if hasattr(self, 'is_local_tax'):
            is_local = self.is_local_tax
        elif hasattr(self.parent_widget, 'nature_combo'):
            is_local = (self.parent_widget.nature_combo.currentText() == "Local")

        # Get tax values from product
        cgst_val = product.get('cgst', 0)
        sgst_val = product.get('sgst', 0)
        igst_val = product.get('igst', 0)
        cess_val = product.get('cess', 0)

        if is_local:
            # Local: use product's CGST and SGST, set IGST to 0
            cgst_item = self.parent_widget.items_table.item(row, 3)
            if cgst_item:
                cgst_item.setText(f"{cgst_val:.2f}")

            sgst_item = self.parent_widget.items_table.item(row, 4)
            if sgst_item:
                sgst_item.setText(f"{sgst_val:.2f}")

            igst_item = self.parent_widget.items_table.item(row, 5)
            if igst_item:
                igst_item.setText("0")
        else:
            # Inter-state: use product's IGST, set CGST and SGST to 0
            cgst_item = self.parent_widget.items_table.item(row, 3)
            if cgst_item:
                cgst_item.setText("0")

            sgst_item = self.parent_widget.items_table.item(row, 4)
            if sgst_item:
                sgst_item.setText("0")

            igst_item = self.parent_widget.items_table.item(row, 5)
            if igst_item:
                igst_item.setText(f"{igst_val:.2f}")

        cess_item = self.parent_widget.items_table.item(row, 6)
        if cess_item:
            cess_item.setText(str(product.get('cess', 0)))

        rate = self.parent_widget.get_product_rate_from_selector(product)
        rate_item = self.parent_widget.items_table.item(row, 7)
        if rate_item:
            rate_item.setText(str(rate))

        # Calculate total tax percent
        tax_percent = product.get('cgst', 0) + product.get('sgst', 0) + product.get('igst', 0) + product.get('cess', 0)

        # Update sale_items
        if row < len(self.parent_widget.sale_items):
            self.parent_widget.sale_items[row]['product_id'] = product['id']
            self.parent_widget.sale_items[row]['hsn'] = product.get('hsn', '')
            self.parent_widget.sale_items[row]['cgst'] = product.get('cgst', 0)
            self.parent_widget.sale_items[row]['sgst'] = product.get('sgst', 0)
            self.parent_widget.sale_items[row]['igst'] = product.get('igst', 0)
            self.parent_widget.sale_items[row]['cess'] = product.get('cess', 0)
            self.parent_widget.sale_items[row]['tax_percent'] = tax_percent
            self.parent_widget.sale_items[row]['rate'] = rate

        # Recalculate row with new values to compute tax correctly
        # Trigger recalculation for tax columns to ensure tax is calculated
        self.parent_widget.recalculate_row(row, source_column=3)
        self.parent_widget.calculate_totals()

    def eventFilter(self, editor, event):
        """Filter keyboard events for custom Enter/Esc/Tab flow and special field behaviors."""
        if event.type() == QEvent.KeyPress:
            if event.key() in [Qt.Key_Return, Qt.Key_Enter]:
                # Handle Enter key - commit and move to next field
                self.handle_enter_key()
                return True  # Stop default Qt behavior
            elif event.key() == Qt.Key_Escape:
                # Handle Esc key - move to previous field
                self.handle_esc_key()
                return True  # Stop default Qt behavior
            elif event.key() == Qt.Key_Tab:
                # Handle Tab key - stop default navigation
                return True  # Stop default Qt behavior
            elif event.key() == Qt.Key_Down:
                # Handle Down Arrow for Disc percent conversion
                if self.current_index and self.current_index.column() == 10:  # Disc column
                    self.handle_disc_percent_conversion(editor)
                    return True  # Stop default Qt behavior after conversion
                # Otherwise let arrow key behave normally for caret navigation
                return super().eventFilter(editor, event)
        
        return super().eventFilter(editor, event)
    
    def handle_disc_percent_conversion(self, editor):
        """Handle Disc percent conversion when Down Arrow is pressed in Disc column."""
        if not self.parent_widget or not self.current_index:
            return
        
        row = self.current_index.row()
        text = editor.text().strip()
        
        # Check if text is a simple valid number
        if not text:
            return
        
        try:
            percent = float(text)
        except ValueError:
            # Not a valid number, do nothing
            return
        
        # Get current gross/base value
        # Best base = current Gross column value if available; if Gross is empty/zero, derive from Rate × Qty
        gross = self.parent_widget.safe_float_from_cell(row, 9, 0)
        if gross <= 0:
            rate = self.parent_widget.safe_float_from_cell(row, 7, 0)
            qty = self.parent_widget.safe_float_from_cell(row, 8, 0)
            gross = rate * qty
        
        if gross <= 0:
            return
        
        # Calculate discount amount: (percent / 100) * gross
        discount_amount = (percent / 100) * gross
        
        # Replace editor text with calculated discount amount
        new_text = f"{discount_amount:.2f}"
        
        # Block signals to prevent triggering on_editor_changed during text update
        editor.blockSignals(True)
        editor.setText(new_text)
        editor.blockSignals(False)
        
        # Move cursor to end of text
        cursor_pos = len(new_text)
        editor.setCursorPosition(cursor_pos)
        
        # Update table item with new value
        if self.mode == "sales":
            table = self.parent_widget.items_table
        else:
            table = getattr(self.parent_widget, "table", getattr(self.parent_widget, "items_table", None))
        disc_item = table.item(row, 10)
        if disc_item:
            disc_item.setText(new_text)
        
        # Recalculate row without closing editor
        self.parent_widget.recalculate_row(row)
        
        # Keep editor active - do NOT close it
        # Cursor remains in Disc field for continued editing
    
    def get_enter_flow_for_current_nature(self):
        """Get Enter flow based on current Nature of Sales."""
        if not self.parent_widget:
            # Default to Local flow if parent not available
            return [COL_PRODUCT, COL_HSN, COL_CGST, COL_SGST, COL_IGST, COL_CESS, COL_RATE, COL_QTY, COL_GROSS, COL_DISC]
        
        if self.mode == "van_entry":
            return [1, 3]  # Product, Load Qty
            
        if self.mode == "van_return":
            return [1, 2, 3]  # Product, Return Qty, Rate
            
        # Check Nature of Sales
        nature_combo = self.parent_widget.nature_combo
        if nature_combo:
            nature_text = nature_combo.currentText().strip().lower()
            if 'inter' in nature_text or 'inter-state' in nature_text:
                # Inter-state: skip CGST and SGST, use IGST
                return [COL_PRODUCT, COL_HSN, COL_IGST, COL_CESS, COL_RATE, COL_QTY, COL_GROSS, COL_DISC]
        
        # Default Local: use CGST and SGST, skip IGST
        return [COL_PRODUCT, COL_HSN, COL_CGST, COL_SGST, COL_CESS, COL_RATE, COL_QTY, COL_GROSS, COL_DISC]
    
    def get_esc_flow_for_current_nature(self):
        """Get Esc flow based on current Nature of Sales."""
        if not self.parent_widget:
            # Default to Local flow if parent not available
            return [COL_DISC, COL_GROSS, COL_QTY, COL_RATE, COL_CESS, COL_SGST, COL_CGST, COL_HSN, COL_PRODUCT]
        
        if self.mode == "van_entry":
            return [4, 3, 1]
            
        if self.mode == "van_return":
            return [3, 2, 1]
            
        # Check Nature of Sales
        nature_combo = self.parent_widget.nature_combo
        if nature_combo:
            nature_text = nature_combo.currentText().strip().lower()
            if 'inter' in nature_text or 'inter-state' in nature_text:
                # Inter-state: skip CGST and SGST, use IGST
                return [COL_DISC, COL_GROSS, COL_QTY, COL_RATE, COL_CESS, COL_IGST, COL_HSN, COL_PRODUCT]
        
        # Default Local: use CGST and SGST, skip IGST
        return [COL_DISC, COL_GROSS, COL_QTY, COL_RATE, COL_CESS, COL_SGST, COL_CGST, COL_HSN, COL_PRODUCT]
    
    def handle_enter_key(self):
        """Handle Enter key for exact billing flow."""
        if not self.parent_widget or not self.current_index:
            return
        
        row = self.current_index.row()
        column = self.current_index.column()
        
        # Commit current editor value
        if self.current_editor:
            self.commitData.emit(self.current_editor)
            self.closeEditor.emit(self.current_editor, QStyledItemDelegate.SubmitModelCache)
        
        # Recalculate row
        self.parent_widget.recalculate_row(row)

        if (
            self.mode == "sales"
            and column == COL_QTY
            and hasattr(self.parent_widget, "enforce_qty_stock_limit")
        ):
            qty_text = self.parent_widget.safe_item_text(row, COL_QTY, "0")
            qty = self.parent_widget._safe_float(qty_text, 0.0)
            if self.parent_widget.enforce_qty_stock_limit(row, qty, show_warning=True):
                return
        
        # Delay cell movement slightly to ensure editor is fully closed
        QTimer.singleShot(0, lambda: self._move_after_enter(row, column))
    
    def _move_after_enter(self, row, column):
        """Move to next cell after Enter key."""
        # Get dynamic Enter flow based on current Nature
        enter_flow = self.get_enter_flow_for_current_nature()
        try:
            idx = enter_flow.index(column)
            if idx < len(enter_flow) - 1:
                self.move_to_cell(row, enter_flow[idx + 1])
            elif column == enter_flow[-1]:  # Final column, handle based on mode
                if self.mode == "van_entry" or self.mode == "van_return":
                    # Focus barcode field for VanEntry/Return
                    if hasattr(self.parent_widget, "barcode_input"):
                        self.parent_widget.barcode_input.setFocus()
                else:
                    # Check barcode tick state for Sales Entry
                    barcode_tick_on = self.parent_widget.barcode_tick.isChecked()
                    
                    # Add a new blank row
                    new_row = self.parent_widget.add_blank_row()
                    
                    if barcode_tick_on:
                        # Barcode tick ON: move to barcode field
                        self.parent_widget.barcode_input.setFocus()
                    else:
                        # Barcode tick OFF: move to Product column of new row
                        QTimer.singleShot(0, lambda: self.move_to_cell(new_row, COL_PRODUCT))
        except ValueError:
            pass
    
    def handle_esc_key(self):
        """Handle Esc key for exact billing flow."""
        if not self.parent_widget or not self.current_index:
            return
        
        row = self.current_index.row()
        column = self.current_index.column()
        
        # Commit current editor value
        if self.current_editor:
            self._esc_closing = True
            try:
                self.commitData.emit(self.current_editor)
                self.closeEditor.emit(self.current_editor, QStyledItemDelegate.SubmitModelCache)
            finally:
                self._esc_closing = False
        
        # Recalculate row
        self.parent_widget.recalculate_row(row)
        
        # Delay cell movement slightly to ensure editor is fully closed
        QTimer.singleShot(0, lambda: self._move_after_esc(row, column))
    
    def _move_after_esc(self, row, column):
        """Move to previous cell after Esc key."""
        # Get dynamic Esc flow based on current Nature
        esc_flow = self.get_esc_flow_for_current_nature()
        try:
            idx = esc_flow.index(column)
            if idx < len(esc_flow) - 1:
                self.move_to_cell(row, esc_flow[idx + 1])
            elif column == COL_PRODUCT:  # Product
                # Move to barcode field
                self.parent_widget.barcode_input.setFocus()
        except ValueError:
            pass
    
    def move_to_cell(self, row, col):
        """Move to specific cell and open editor."""
        if not self.parent_widget:
            return

        if self.mode == "sales":
            table = self.parent_widget.items_table
        elif self.mode == "van_return":
            table = getattr(self.parent_widget, "stock_table", getattr(self.parent_widget, "table", None))
        else:
            table = getattr(self.parent_widget, "table", getattr(self.parent_widget, "items_table", None))

        if not table:
            return

        if row >= 0 and row < table.rowCount() and col >= 0 and col < table.columnCount():
            # Scroll to target row to ensure it's visible before editing
            from PySide6.QtWidgets import QAbstractItemView
            target_item = table.item(row, 0)
            if target_item:
                table.scrollToItem(target_item, QAbstractItemView.PositionAtCenter)

            item = table.item(row, col)
            if item:
                # Check if item is editable
                flags = item.flags()
                if flags & Qt.ItemIsEditable:
                    # Safe edit sequence: set current cell, verify index, then edit
                    table.setCurrentCell(row, col)
                    index = table.model().index(row, col)
                    if index.isValid():
                        table.edit(index)