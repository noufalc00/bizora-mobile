"""
Stock Checker / Physical Stock Reconciliation Page
Enterprise "Scan & Add" workflow for multi-day stock audit sessions.
"""
from PySide6.QtWidgets import *
from PySide6.QtWidgets import QStyledItemDelegate, QApplication
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QColor
from config import active_company_manager
from db import Database
from bizora_core.product_logic import ProductLogic
from bizora_core.stock_logic import StockLogic
from ui import theme
from ui.checkbox_style import create_checkbox
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.book_report_common import report_data_table_style
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class QtyDelegate(QStyledItemDelegate):
    """Simple delegate for visible text in Phys. Qty column."""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        theme.prepare_billing_cell_editor(editor)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.DisplayRole)
        editor.setText(str(value))
        QTimer.singleShot(0, editor.selectAll)

    def setModelData(self, editor, model, index):
        try:
            value = float(editor.text())
            model.setData(index, f'{value:.2f}', Qt.EditRole)
        except ValueError:
            model.setData(index, '0.00', Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

class ItemDisambiguationDialog(UiMemoryMixin, QDialog):
    """Dialog for selecting from multiple matching items."""

    def __init__(self, matches, parent=None):
        super().__init__(parent)
        self.matches = matches
        self.selected_item = None
        self.setWindowTitle('Select Item')
        self.setModal(True)
        self.setMinimumSize(500, 300)
        self.setup_ui()
        self._init_ui_memory()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel('Multiple items found. Please select:')
        title.setStyleSheet(theme.master_dialog_heading_style(14))
        layout.addWidget(title)
        self.table = QTableWidget()
        self.table.setStyleSheet(theme.editable_table_style())
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['Item Name', 'Barcode', 'Current Stock', 'Rate'])
        apply_read_only_report_table_selection(self.table)
        self.table.doubleClicked.connect(self.accept_selection)
        for row_idx, item in enumerate(self.matches):
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(item.get('name', '')) if item.get('name', '') is not None else ''))
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(item.get('barcode', '')) if item.get('barcode', '') is not None else ''))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(item.get('current_stock', 0)) if item.get('current_stock', 0) is not None else '0'))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(item.get('purchase_rate', 0)) if item.get('purchase_rate', 0) is not None else '0'))
        layout.addWidget(self.table)
        button_layout = QHBoxLayout()
        ok_btn = QPushButton('Select')
        ok_btn.setStyleSheet(theme.sales_primary_button_style())
        ok_btn.clicked.connect(self.accept_selection)
        button_layout.addWidget(ok_btn)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setStyleSheet(theme.sales_compact_button_style())
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

    def accept_selection(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.selected_item = self.matches[current_row]
            self.accept()

class StockCheckerPageWidget(UiMemoryMixin, QWidget):
    """Stock Checker / Physical Stock Reconciliation page with Scan & Add workflow."""

    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self.product_logic = ProductLogic(self.db)
        self.stock_logic = StockLogic(self.db)
        self.draft_items = []
        self.setup_ui()
        self.load_draft_session()
        self._init_ui_memory()

    def setup_ui(self):
        colors = theme._theme_colors()
        layout = QVBoxLayout(self)
        self.title_label = QLabel('Stock Checker / Scan & Add Session')
        self.title_label.setStyleSheet(theme.master_page_title_style(24))
        layout.addWidget(self.title_label)
        self.info_label = QLabel('Scan barcode or type item name to add to draft session. Enter physical quantities to calculate variance.')
        self.info_label.setStyleSheet(f"color: {colors['muted_text']}; font-size: 13px; padding: 4px;")
        layout.addWidget(self.info_label)
        scanner_bar = QHBoxLayout()
        self.scanner_label = QLabel('Scan Barcode or Type Item Name:')
        self.scanner_label.setStyleSheet(f"color: {colors['label_text']}; font-size: 14px; font-weight: bold;")
        scanner_bar.addWidget(self.scanner_label)
        self.scanner_input = QLineEdit()
        self.scanner_input.setPlaceholderText('Scan or type here, then press Enter...')
        self.scanner_input.setFixedHeight(35)
        self.scanner_input.setStyleSheet(theme.sales_compact_input_style())
        self.scanner_input.returnPressed.connect(self.on_scan_enter)
        scanner_bar.addWidget(self.scanner_input)
        self.multi_bin_checkbox = create_checkbox('Allow Multiple Rows per Item (Multi-Bin)', label_color=colors['label_text'], font_size=13, spacing=8)
        self.multi_bin_checkbox.setChecked(True)
        scanner_bar.addWidget(self.multi_bin_checkbox)
        self.load_uncounted_button = QPushButton('Load Uncounted Stock')
        self.load_uncounted_button.setStyleSheet(theme.sales_compact_button_style())
        self.load_uncounted_button.clicked.connect(self.load_uncounted_stock)
        scanner_bar.addWidget(self.load_uncounted_button)
        layout.addLayout(scanner_bar)
        action_bar = QHBoxLayout()
        action_bar.addStretch()
        self.remove_button = QPushButton('Remove Selected Item')
        self.remove_button.setStyleSheet(theme.sales_danger_button_style())
        self.remove_button.clicked.connect(self.remove_selected_item)
        action_bar.addWidget(self.remove_button)
        layout.addLayout(action_bar)
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(['Barcode', 'Item Name', 'Comp. Qty', 'Phys. Qty', 'Qty Variance', 'Rate (₹)', 'Comp. Value', 'Phys. Value', 'Value Variance'])
        self.table.setStyleSheet(theme.editable_table_style())
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self.on_item_changed)
        self.table.setItemDelegateForColumn(3, QtyDelegate())
        self.installEventFilter(self)
        layout.addWidget(self.table)
        bottom_bar = QHBoxLayout()
        self.lbl_total_comp_value = QLabel('Total System Value: ₹ 0.00')
        self.lbl_total_comp_value.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {colors['muted_text']};")
        bottom_bar.addWidget(self.lbl_total_comp_value)
        self.lbl_total_phys_value = QLabel('Total Physical Value: ₹ 0.00')
        self.lbl_total_phys_value.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {colors['input_text']};")
        bottom_bar.addWidget(self.lbl_total_phys_value)
        self.lbl_net_variance = QLabel('Net Variance: ₹ 0.00')
        self.lbl_net_variance.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {colors['muted_text']};")
        bottom_bar.addWidget(self.lbl_net_variance)
        bottom_bar.addStretch()
        self.clear_button = QPushButton('Clear/Reset Session')
        self.clear_button.setStyleSheet(theme.sales_compact_button_style())
        self.clear_button.clicked.connect(self.clear_session)
        bottom_bar.addWidget(self.clear_button)
        self.finalize_button = QPushButton('Finalize Stock Validation')
        self.finalize_button.setStyleSheet(theme.sales_danger_button_style())
        self.finalize_button.clicked.connect(self.finalize_session)
        bottom_bar.addWidget(self.finalize_button)
        layout.addLayout(bottom_bar)

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        colors = theme._theme_colors()
        self.setStyleSheet(theme.master_page_background_style())
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(theme.master_page_title_style(24))
        if hasattr(self, 'info_label'):
            self.info_label.setStyleSheet(f"color: {colors['muted_text']}; font-size: 13px; padding: 4px;")
        if hasattr(self, 'scanner_label'):
            self.scanner_label.setStyleSheet(f"color: {colors['label_text']}; font-size: 14px; font-weight: bold;")
        if hasattr(self, 'scanner_input'):
            self.scanner_input.setStyleSheet(theme.sales_compact_input_style())
        if hasattr(self, 'table'):
            self.table.setStyleSheet(theme.editable_table_style())
        for button_name, style_name in (('load_uncounted_button', 'sales_compact_button_style'), ('remove_button', 'sales_danger_button_style'), ('clear_button', 'sales_compact_button_style'), ('finalize_button', 'sales_danger_button_style')):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setStyleSheet(getattr(theme, style_name)())
        if hasattr(self, 'lbl_total_comp_value'):
            self.lbl_total_comp_value.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {colors['muted_text']};")
        if hasattr(self, 'lbl_total_phys_value'):
            self.lbl_total_phys_value.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {colors['input_text']};")
        if hasattr(self, 'lbl_net_variance'):
            self.lbl_net_variance.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {colors['muted_text']};")

    def load_draft_session(self):
        """Load existing draft session from database."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'No Company', 'Please select a company first.')
            return
        draft_items = self.db.get_stock_draft_session_items(active_company['id'])
        self.draft_items = list(draft_items) if draft_items else []
        self.populate_table()
        self.update_total_variance()

    def populate_table(self):
        """Populate table with draft items."""
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row_idx, item in enumerate(self.draft_items):
            self.table.insertRow(row_idx)
            barcode = item.get('item_code', 'N/A')
            barcode_item = QTableWidgetItem(str(barcode) if barcode is not None else '')
            barcode_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            barcode_item.setFlags(barcode_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 0, barcode_item)
            name_item = QTableWidgetItem(str(item['item_name']) if item.get('item_name') is not None else '')
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            name_item.setData(Qt.UserRole, item['item_id'])
            name_item.setData(Qt.UserRole + 1, item['id'])
            self.table.setItem(row_idx, 1, name_item)
            comp_qty = item['computer_qty']
            comp_item = QTableWidgetItem(f'{comp_qty:.2f}' if comp_qty is not None else '0.00')
            comp_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            comp_item.setFlags(comp_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 2, comp_item)
            phys_qty = item['physical_qty']
            phys_item = QTableWidgetItem(f'{phys_qty:.2f}' if phys_qty is not None else '0.00')
            phys_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 3, phys_item)
            qty_variance = phys_qty - comp_qty if phys_qty is not None and comp_qty is not None else 0.0
            qty_var_item = QTableWidgetItem(f'{qty_variance:+.2f}')
            qty_var_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            qty_var_item.setFlags(qty_var_item.flags() & ~Qt.ItemIsEditable)
            if qty_variance > 0:
                qty_var_item.setForeground(QColor(theme.semantic_positive_hex()))
            elif qty_variance < 0:
                qty_var_item.setForeground(QColor(theme.semantic_negative_hex()))
            else:
                qty_var_item.setForeground(QColor(theme.semantic_neutral_hex()))
            self.table.setItem(row_idx, 4, qty_var_item)
            rate = item['purchase_rate']
            rate_item = QTableWidgetItem(f'{rate:.2f}' if rate is not None else '0.00')
            rate_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rate_item.setFlags(rate_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 5, rate_item)
            comp_value = comp_qty * rate if comp_qty is not None and rate is not None else 0.0
            comp_val_item = QTableWidgetItem(f'{comp_value:.2f}')
            comp_val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            comp_val_item.setFlags(comp_val_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 6, comp_val_item)
            phys_value = phys_qty * rate if phys_qty is not None and rate is not None else 0.0
            phys_val_item = QTableWidgetItem(f'{phys_value:.2f}')
            phys_val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            phys_val_item.setFlags(phys_val_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 7, phys_val_item)
            value_variance = qty_variance * rate if qty_variance is not None and rate is not None else 0.0
            val_var_item = QTableWidgetItem(f'{value_variance:+.2f}')
            val_var_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_var_item.setFlags(val_var_item.flags() & ~Qt.ItemIsEditable)
            if value_variance > 0:
                val_var_item.setForeground(QColor(theme.semantic_positive_hex()))
            elif value_variance < 0:
                val_var_item.setForeground(QColor(theme.semantic_negative_hex()))
            else:
                val_var_item.setForeground(QColor(theme.semantic_neutral_hex()))
            self.table.setItem(row_idx, 8, val_var_item)
        self.table.blockSignals(False)
        apply_adjustable_table_columns(self.table)

    def eventFilter(self, source, event):
        """Event filter for Enter key navigation."""
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            current_item = self.table.currentItem()
            if current_item and current_item.column() == 3:
                QTimer.singleShot(0, self._move_focus_to_scanner)
                return False
        return super().eventFilter(source, event)

    def _move_focus_to_scanner(self):
        """Move focus to scanner input after editor commits."""
        self.scanner_input.setFocus()
        self.scanner_input.selectAll()

    def on_scan_enter(self):
        """Handle Enter key in scanner input."""
        search_text = self.scanner_input.text().strip()
        if not search_text:
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'No Company', 'Please select a company first.')
            return
        result = self.product_logic.get_products(active_company['id'])
        if not result['success']:
            QMessageBox.critical(self, 'Error', result['message'])
            return
        matches = []
        for product in result['data']:
            barcode = product.get('barcode', '').lower()
            name = product.get('name', '').lower()
            if search_text.lower() == barcode or search_text.lower() in name:
                current_stock = self.stock_logic.get_current_stock(active_company['id'], product['id'])
                product['current_stock'] = current_stock
                matches.append(product)
        if not matches:
            QMessageBox.warning(self, 'Not Found', f"No items found matching '{search_text}'")
            self.scanner_input.clear()
            return
        if len(matches) == 1:
            self.add_item_to_draft(matches[0], active_company['id'])
            self.scanner_input.clear()
            return
        dialog = ItemDisambiguationDialog(matches, self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_item:
            self.add_item_to_draft(dialog.selected_item, active_company['id'])
            self.scanner_input.clear()
        else:
            self.scanner_input.clear()

    def add_item_to_draft(self, product, company_id):
        """Add item to draft session."""
        item_id = product['id']
        item_code = product.get('barcode', '')
        item_name = product.get('name', '')
        computer_qty = product.get('current_stock', 0)
        purchase_rate = product.get('purchase_rate', 0)
        multi_bin = self.multi_bin_checkbox.isChecked()
        if multi_bin:
            ph = self.db._get_placeholder()
            query = f'\n                INSERT INTO stock_draft_session (company_id, item_id, item_code, item_name, computer_qty, physical_qty, purchase_rate)\n                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})\n            '
            self.db.execute_update(query, (company_id, item_id, item_code, item_name, computer_qty, computer_qty, purchase_rate))
        else:
            self.db.add_stock_draft_item(company_id, item_id, item_code, item_name, computer_qty, purchase_rate)
        self.load_draft_session()
        QApplication.processEvents()

        def force_edit_mode():
            self.table.setFocus()
            last_row = self.table.rowCount() - 1
            if last_row >= 0:
                self.table.setCurrentCell(last_row, 3)
                item = self.table.item(last_row, 3)
                if item:
                    self.table.editItem(item)
        QTimer.singleShot(10, force_edit_mode)

    def on_item_changed(self, item):
        """Handle item change in table (Physical Qty column)."""
        if item.column() != 3:
            return
        row = item.row()
        try:
            phys_qty = float(item.text())
        except ValueError:
            phys_qty = 0.0
            item.setText('0.00')
        name_item = self.table.item(row, 1)
        if name_item:
            item_id = name_item.data(Qt.UserRole)
            active_company = active_company_manager.get_active_company()
            if active_company and item_id:
                self.db.update_stock_draft_physical_qty(active_company['id'], item_id, phys_qty)
        self.table.blockSignals(True)
        item_totals = {}
        for row_idx in range(self.table.rowCount()):
            barcode_item = self.table.item(row_idx, 0)
            comp_qty_item = self.table.item(row_idx, 2)
            phys_qty_item = self.table.item(row_idx, 3)
            rate_item = self.table.item(row_idx, 5)
            if not all([barcode_item, comp_qty_item, phys_qty_item, rate_item]):
                continue
            barcode = barcode_item.text()
            comp_qty = float(comp_qty_item.text())
            phys_qty = float(phys_qty_item.text())
            rate = float(rate_item.text())
            if barcode not in item_totals:
                item_totals[barcode] = {'comp': comp_qty, 'phys': 0.0, 'rate': rate}
            item_totals[barcode]['phys'] += phys_qty
        for row_idx in range(self.table.rowCount()):
            barcode_item = self.table.item(row_idx, 0)
            comp_qty_item = self.table.item(row_idx, 2)
            phys_qty_item = self.table.item(row_idx, 3)
            rate_item = self.table.item(row_idx, 5)
            if not all([barcode_item, comp_qty_item, phys_qty_item, rate_item]):
                continue
            barcode = barcode_item.text()
            comp_qty = float(comp_qty_item.text())
            phys_qty = float(phys_qty_item.text())
            rate = float(rate_item.text())
            true_qty_variance = item_totals[barcode]['phys'] - item_totals[barcode]['comp']
            true_value_variance = true_qty_variance * item_totals[barcode]['rate']
            comp_value = comp_qty * rate
            phys_value = phys_qty * rate
            qty_var_item = self.table.item(row_idx, 4)
            if qty_var_item:
                qty_var_item.setText(f'{true_qty_variance:+.2f}')
                if true_qty_variance > 0:
                    qty_var_item.setForeground(QColor(theme.semantic_positive_hex()))
                elif true_qty_variance < 0:
                    qty_var_item.setForeground(QColor(theme.semantic_negative_hex()))
                else:
                    qty_var_item.setForeground(QColor(theme.semantic_neutral_hex()))
            comp_val_item = self.table.item(row_idx, 6)
            if comp_val_item:
                comp_val_item.setText(f'{comp_value:.2f}')
            phys_val_item = self.table.item(row_idx, 7)
            if phys_val_item:
                phys_val_item.setText(f'{phys_value:.2f}')
            val_var_item = self.table.item(row_idx, 8)
            if val_var_item:
                val_var_item.setText(f'{true_value_variance:+.2f}')
                if true_value_variance > 0:
                    val_var_item.setForeground(QColor(theme.semantic_positive_hex()))
                elif true_value_variance < 0:
                    val_var_item.setForeground(QColor(theme.semantic_negative_hex()))
                else:
                    val_var_item.setForeground(QColor(theme.semantic_neutral_hex()))
        self.table.blockSignals(False)
        self.update_total_variance()

    def remove_selected_item(self):
        """Remove selected item from draft session."""
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, 'No Selection', 'Please select an item to remove.')
            return
        name_item = self.table.item(current_row, 1)
        if not name_item:
            QMessageBox.warning(self, 'Error', 'Could not get item information.')
            return
        item_name = name_item.text()
        row_id = name_item.data(Qt.UserRole + 1)
        reply = QMessageBox.question(self, 'Remove Item', f"Are you sure you want to remove '{item_name}' from the draft session?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return
        self.db.delete_stock_draft_item(row_id)
        self.load_draft_session()

    def clear_session(self):
        """Clear entire draft session."""
        reply = QMessageBox.question(self, 'Clear Session', 'This will remove all items from the draft session. This action cannot be undone. Continue?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'No Company', 'Please select a company first.')
            return
        self.db.clear_stock_draft_session(active_company['id'])
        self.load_draft_session()

    def update_total_variance(self):
        """Update total financial labels using aggregated data."""
        item_totals = {}
        for row_idx in range(self.table.rowCount()):
            barcode_item = self.table.item(row_idx, 0)
            comp_qty_item = self.table.item(row_idx, 2)
            phys_qty_item = self.table.item(row_idx, 3)
            rate_item = self.table.item(row_idx, 5)
            if not all([barcode_item, comp_qty_item, phys_qty_item, rate_item]):
                continue
            barcode = barcode_item.text()
            comp_qty = float(comp_qty_item.text())
            phys_qty = float(phys_qty_item.text())
            rate = float(rate_item.text())
            if barcode not in item_totals:
                item_totals[barcode] = {'comp': comp_qty, 'phys': 0.0, 'rate': rate}
            item_totals[barcode]['phys'] += phys_qty
        total_comp_value = 0.0
        total_phys_value = 0.0
        total_variance = 0.0
        for barcode, data in item_totals.items():
            comp_value = data['comp'] * data['rate']
            phys_value = data['phys'] * data['rate']
            qty_variance = data['phys'] - data['comp']
            value_variance = qty_variance * data['rate']
            total_comp_value += comp_value
            total_phys_value += phys_value
            total_variance += value_variance
        self.lbl_total_comp_value.setText(f'Total System Value: ₹ {total_comp_value:.2f}')
        self.lbl_total_phys_value.setText(f'Total Physical Value: ₹ {total_phys_value:.2f}')
        self.lbl_net_variance.setText(f'Net Variance: ₹ {total_variance:+.2f}')
        if total_variance > 0:
            color = theme.semantic_positive_hex()
        elif total_variance < 0:
            color = theme.semantic_negative_hex()
        else:
            color = theme.semantic_neutral_hex()
        self.lbl_net_variance.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {color};')

    def load_uncounted_stock(self):
        """Load uncounted items (system stock > 0 but not scanned) into the grid with phys_qty = 0."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'No Company', 'Please select a company first.')
            return
        existing_barcodes = set()
        for row in range(self.table.rowCount()):
            barcode_item = self.table.item(row, 0)
            if barcode_item:
                existing_barcodes.add(barcode_item.text())
        ph = self.db._get_placeholder()
        query = f"\n            SELECT id, barcode, name, purchase_rate\n            FROM products\n            WHERE company_id = {ph}\n            AND barcode IS NOT NULL\n            AND barcode != ''\n        "
        products = self.db.execute_query(query, (active_company['id'],))
        if not products:
            QMessageBox.information(self, 'No Products', 'No products found in the system.')
            return
        items_to_add = []
        for product in products:
            barcode = product.get('barcode', '')
            if not barcode or barcode in existing_barcodes:
                continue
            current_stock = self.stock_logic.get_current_stock(active_company['id'], product['id'])
            if current_stock != 0:
                items_to_add.append({'id': product['id'], 'barcode': barcode, 'name': product['name'], 'purchase_rate': product.get('purchase_rate', 0), 'current_stock': current_stock})
        if not items_to_add:
            QMessageBox.information(self, 'No Uncounted Items', 'All items with system stock have already been scanned.')
            return
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            for item in items_to_add:
                row_idx = self.table.rowCount()
                self.table.insertRow(row_idx)
                barcode_item = QTableWidgetItem(str(item.get('barcode', '')) if item.get('barcode') is not None else '')
                barcode_item.setData(Qt.UserRole, item['id'])
                self.table.setItem(row_idx, 0, barcode_item)
                name_item = QTableWidgetItem(str(item.get('name', '')) if item.get('name') is not None else '')
                name_item.setData(Qt.UserRole, item['id'])
                self.table.setItem(row_idx, 1, name_item)
                current_stock = item.get('current_stock', 0)
                comp_qty_item = QTableWidgetItem(f'{current_stock:.2f}' if current_stock is not None else '0.00')
                comp_qty_item.setFlags(comp_qty_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, 2, comp_qty_item)
                phys_qty_item = QTableWidgetItem('0.00')
                self.table.setItem(row_idx, 3, phys_qty_item)
                qty_variance = 0.0 - current_stock if current_stock is not None else 0.0
                rate = item.get('purchase_rate', 0)
                qty_var_item = QTableWidgetItem(f'{qty_variance:+.2f}')
                qty_var_item.setFlags(qty_var_item.flags() & ~Qt.ItemIsEditable)
                qty_var_item.setForeground(QColor(theme.semantic_negative_hex()) if qty_variance < 0 else QColor(theme.semantic_neutral_hex()))
                self.table.setItem(row_idx, 4, qty_var_item)
                rate_item = QTableWidgetItem(f'{rate:.2f}' if rate is not None else '0.00')
                rate_item.setFlags(rate_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, 5, rate_item)
                comp_value = current_stock * rate if current_stock is not None and rate is not None else 0.0
                comp_val_item = QTableWidgetItem(f'{comp_value:.2f}')
                comp_val_item.setFlags(comp_val_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, 6, comp_val_item)
                phys_val_item = QTableWidgetItem('0.00')
                phys_val_item.setFlags(phys_val_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, 7, phys_val_item)
                value_variance = qty_variance * rate if qty_variance is not None and rate is not None else 0.0
                val_var_item = QTableWidgetItem(f'{value_variance:+.2f}')
                val_var_item.setFlags(val_var_item.flags() & ~Qt.ItemIsEditable)
                val_var_item.setForeground(QColor(theme.semantic_negative_hex()) if value_variance < 0 else QColor(theme.semantic_neutral_hex()))
                self.table.setItem(row_idx, 8, val_var_item)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
        self.update_total_variance()
        QMessageBox.information(self, 'Items Loaded', f'Loaded {len(items_to_add)} uncounted items into the grid.')

    def finalize_session(self):
        """Finalize stock validation and post adjustments using UI grid as source of truth."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'No Company', 'Please select a company first.')
            return
        if self.table.rowCount() == 0:
            QMessageBox.information(self, 'No Data', 'No items in draft session.')
            return
        final_aggregation = {}
        for row in range(self.table.rowCount()):
            barcode_item = self.table.item(row, 0)
            comp_qty_item = self.table.item(row, 2)
            phys_qty_item = self.table.item(row, 3)
            rate_item = self.table.item(row, 5)
            item_name_item = self.table.item(row, 1)
            if not all([barcode_item, comp_qty_item, phys_qty_item, rate_item, item_name_item]):
                continue
            barcode = barcode_item.text()
            comp_qty = float(comp_qty_item.text())
            phys_qty = float(phys_qty_item.text())
            rate = float(rate_item.text())
            item_name = item_name_item.text()
            if barcode not in final_aggregation:
                final_aggregation[barcode] = {'item_name': item_name, 'comp_qty': comp_qty, 'total_phys_qty': 0.0, 'rate': rate}
            final_aggregation[barcode]['total_phys_qty'] += phys_qty
        adjustments = []
        for barcode, data in final_aggregation.items():
            total_phys_qty = data['total_phys_qty']
            total_comp_qty = data['comp_qty']
            item_name = data['item_name']
            variance = total_phys_qty - total_comp_qty
            if variance != 0:
                for row in range(self.table.rowCount()):
                    barcode_item = self.table.item(row, 0)
                    if barcode_item and barcode_item.text() == barcode:
                        name_item = self.table.item(row, 1)
                        if name_item:
                            item_id = name_item.data(Qt.UserRole)
                            if item_id:
                                adjustments.append({'product_id': item_id, 'item_name': item_name, 'variance': variance})
                        break
        if not adjustments:
            QMessageBox.information(self, 'No Adjustments', 'No items have variance to adjust.')
            return
        reply = QMessageBox.question(self, 'Finalize Stock Validation', f'This will permanently update your live inventory based on this draft session.\nItems to adjust: {len(adjustments)}\n\nContinue?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return
        from datetime import date
        adjustment_date = date.today().strftime('%Y-%m-%d')
        result = self.stock_logic.post_stock_reconciliation(company_id=active_company['id'], date=adjustment_date, adjustments=adjustments)
        if result['success']:
            self.db.clear_stock_draft_session(active_company['id'])
            QMessageBox.information(self, 'Success', result['message'])
            self.load_draft_session()
        else:
            QMessageBox.critical(self, 'Error', result['message'])