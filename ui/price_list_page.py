"""
Price List Page
Displays all inventory items with current stock and pricing tiers.
"""
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QObject, QThread, Signal, QEvent
from PySide6.QtGui import QColor
from config import active_company_manager
from db import Database
from bizora_core.product_logic import ProductLogic
from bizora_core.export_engine import ExportEngine
from ui import theme
from ui.report_preview_utils import table_widget_to_html
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class PriceListWorker(QObject):
    """Load price list data on a worker-owned database connection."""
    data_ready = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type, db_path, company_id):
        """Initialize worker with a database snapshot and company id."""
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id

    def run(self):
        """Fetch finalized price list rows outside the GUI thread."""
        worker_db = None
        try:
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            result = ProductLogic(worker_db).get_price_list(self.company_id)
            if not result.get('success'):
                self.error.emit(result.get('message') or 'Unable to load price list.')
                return
            self.data_ready.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                worker_db.force_disconnect()
            self.finished.emit()

class PriceListPageWidget(UiMemoryMixin, QWidget):
    """Price List / Stock View page."""

    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self.product_logic = ProductLogic(self.db)
        self.export_engine = ExportEngine(self.db)
        self.price_list_data = []
        self.visible_data = []
        self._loading = False
        self._price_thread = None
        self._price_worker = None
        self.setup_ui()
        self.load_price_list()
        self._init_ui_memory()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel('Price List / Stock View')
        title.setStyleSheet(theme.master_page_title_style(24))
        layout.addWidget(title)
        top_bar = QHBoxLayout()
        from ui.book_report_common import compact_label_style, compact_primary_button_style

        search_label = QLabel('Search:')
        search_label.setStyleSheet(compact_label_style())
        top_bar.addWidget(search_label)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Barcode or item name...')
        self.search_input.setFixedWidth(250)
        self.search_input.setStyleSheet(theme.sales_barcode_input_style())
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.search_input.returnPressed.connect(self.apply_exact_search)
        top_bar.addWidget(self.search_input)
        self.load_btn = QPushButton('Load')
        self.load_btn.setStyleSheet(compact_primary_button_style())
        self.load_btn.setFixedHeight(28)
        self.load_btn.setMinimumWidth(68)
        self.load_btn.clicked.connect(self.apply_exact_search)
        top_bar.addWidget(self.load_btn)
        top_bar.addStretch()
        self.export_pdf_btn = QPushButton('Export PDF')
        self.export_pdf_btn.setStyleSheet(theme.sales_compact_button_style())
        self.export_pdf_btn.clicked.connect(self.export_pdf)
        top_bar.addWidget(self.export_pdf_btn)
        self.export_excel_btn = QPushButton('Export Excel')
        self.export_excel_btn.setStyleSheet(theme.sales_compact_button_style())
        self.export_excel_btn.clicked.connect(self.export_excel)
        top_bar.addWidget(self.export_excel_btn)
        layout.addLayout(top_bar)
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(['Item Code', 'Item Name', 'Current Stock', 'Purchase Rate', 'Sales Rate', 'Wholesale Rate', 'MRP', 'Markup %', 'Gross Margin %'])
        apply_read_only_report_table_selection(self.table)
        self.table.doubleClicked.connect(self.on_item_double_clicked)
        self.search_input.installEventFilter(self)
        self.table.installEventFilter(self)
        layout.addWidget(self.table)

    def load_price_list(self):
        """Load price list data from database."""
        if self._loading:
            return
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'No Company', 'Please select a company first.')
            return
        thread = QThread(self)
        worker = PriceListWorker(getattr(self.db, 'db_type', None), getattr(self.db, 'db_path', None), active_company['id'])
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(self._apply_price_list_result)
        worker.error.connect(self._show_load_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._price_worker_finished)
        self._price_thread = thread
        self._price_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _apply_price_list_result(self, result):
        """Apply worker result on the GUI thread."""
        if result['success']:
            self.price_list_data = result['data']
            self.visible_data = self.price_list_data.copy()
            self.populate_table(self.visible_data)
        else:
            QMessageBox.critical(self, 'Error', result['message'])

    def _set_loading_state(self, is_loading):
        """Disable actions while the worker is active."""
        self._loading = is_loading
        self.search_input.setEnabled(not is_loading)
        self.load_btn.setEnabled(not is_loading)
        self.export_pdf_btn.setEnabled(not is_loading)
        self.export_excel_btn.setEnabled(not is_loading)
        self.table.setEnabled(not is_loading)
        if is_loading:
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(['Loading'])
            self.table.setItem(0, 0, QTableWidgetItem('Loading price list...'))

    def _price_worker_finished(self):
        """Clear worker state and re-enable controls."""
        self._price_thread = None
        self._price_worker = None
        self._set_loading_state(False)

    def _show_load_error(self, message):
        """Display worker errors in the table."""
        self.table.setRowCount(1)
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(['Error'])
        self.table.setItem(0, 0, QTableWidgetItem(message))
        QMessageBox.critical(self, 'Error', message)

    def populate_table(self, data):
        """Populate table with given data."""
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(['Item Code', 'Item Name', 'Current Stock', 'Purchase Rate', 'Sales Rate', 'Wholesale Rate', 'MRP', 'Markup %', 'Gross Margin %'])
        self.table.setRowCount(0)
        for row_idx, item in enumerate(data):
            self.table.insertRow(row_idx)
            item_code_item = QTableWidgetItem(str(item['item_code']))
            item_code_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row_idx, 0, item_code_item)
            item_name_item = QTableWidgetItem(str(item['item_name']))
            item_name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row_idx, 1, item_name_item)
            stock_item = QTableWidgetItem(f"{item['current_stock']:.2f}")
            stock_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 2, stock_item)
            purchase_item = QTableWidgetItem(f"{item['purchase_rate']:.2f}")
            purchase_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 3, purchase_item)
            sales_item = QTableWidgetItem(f"{item['sales_rate']:.2f}")
            sales_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 4, sales_item)
            wholesale_item = QTableWidgetItem(f"{item['wholesale_rate']:.2f}")
            wholesale_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 5, wholesale_item)
            mrp_item = QTableWidgetItem(f"{item['mrp']:.2f}")
            mrp_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 6, mrp_item)
            markup_item = QTableWidgetItem(f"{item.get('markup_percent', 0.0):.2f}")
            markup_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 7, markup_item)
            margin_item = QTableWidgetItem(f"{item.get('gross_margin_percent', 0.0):.2f}")
            margin_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 8, margin_item)
        apply_adjustable_table_columns(self.table)

    def _partial_matches(self, search_text: str) -> list:
        """Return items whose barcode or name contains the search text."""
        search_text = search_text.strip().lower()
        if not search_text:
            return self.price_list_data.copy()
        matches = []
        for item in self.price_list_data:
            item_code = str(item.get('item_code', '')).lower()
            item_name = str(item.get('item_name', '')).lower()
            if search_text in item_code or search_text in item_name:
                matches.append(item)
        return matches

    def _exact_match(self, search_text: str):
        """Resolve a single item by exact barcode or item name."""
        search_text = search_text.strip()
        if not search_text:
            return None
        search_lower = search_text.lower()
        for item in self.price_list_data:
            if str(item.get('item_code', '')).strip().lower() == search_lower:
                return item
        for item in self.price_list_data:
            if str(item.get('item_name', '')).strip().lower() == search_lower:
                return item
        return None

    def on_search_text_changed(self, search_text: str) -> None:
        """Live-filter the table while the user types barcode or item name."""
        self.visible_data = self._partial_matches(search_text)
        self.populate_table(self.visible_data)
        if self.visible_data and self.table.rowCount() > 0:
            self.table.selectRow(0)

    def apply_exact_search(self) -> None:
        """Load the exact item: barcode/name match, or the highlighted table row."""
        search_text = self.search_input.text().strip()
        if not search_text:
            self.visible_data = self.price_list_data.copy()
            self.populate_table(self.visible_data)
            return

        selected_item = self._exact_match(search_text)
        if selected_item is None:
            partial = self._partial_matches(search_text)
            if len(partial) == 1:
                selected_item = partial[0]
            elif partial:
                row = self.table.currentRow()
                if row < 0 or row >= len(partial):
                    row = 0
                selected_item = partial[row]
            else:
                QMessageBox.warning(
                    self,
                    'Item Not Found',
                    f'No item matches barcode or name: {search_text}',
                )
                self.search_input.selectAll()
                return

        display_text = str(selected_item.get('item_name') or selected_item.get('item_code') or '')
        self.search_input.blockSignals(True)
        self.search_input.setText(display_text)
        self.search_input.blockSignals(False)
        self.visible_data = [selected_item]
        self.populate_table(self.visible_data)
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
            self.table.setFocus()

    def eventFilter(self, watched, event):
        """Handle Escape on search and Enter on the item table."""
        if event.type() == QEvent.Type.KeyPress:
            if watched is self.search_input and event.key() == Qt.Key.Key_Escape:
                self.search_input.clear()
                self.on_search_text_changed('')
                return True
            if watched is self.table and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.apply_exact_search()
                return True
        return super().eventFilter(watched, event)

    def filter_table(self, search_text):
        """Backward-compatible alias for live search filtering."""
        self.on_search_text_changed(search_text)

    def on_item_double_clicked(self, index):
        """Handle double-click on item row - show product details."""
        row = index.row()
        if row < 0 or row >= len(self.visible_data):
            return
        item = self.visible_data[row]
        item_name = item.get('item_name', '')
        item_code = item.get('item_code', '')
        info_text = f"\n        <b>Item Code:</b> {item_code}<br>\n        <b>Item Name:</b> {item_name}<br>\n        <b>Current Stock:</b> {item['current_stock']:.2f}<br>\n        <b>Purchase Rate:</b> {item['purchase_rate']:.2f}<br>\n        <b>Sales Rate:</b> {item['sales_rate']:.2f}<br>\n        <b>Wholesale Rate:</b> {item['wholesale_rate']:.2f}<br>\n        <b>MRP:</b> {item['mrp']:.2f}<br>\n        <b>Markup %:</b> {item.get('markup_percent', 0.0):.2f}<br>\n        <b>Gross Margin %:</b> {item.get('gross_margin_percent', 0.0):.2f}\n        "
        from ui.message_boxes import show_message
        from PySide6.QtWidgets import QMessageBox

        show_message(
            self,
            QMessageBox.Icon.Information,
            'Product Details',
            f'Product: {item_name}',
            informative_text=info_text,
        )

    def export_pdf(self):
        """Open price list in the universal print/PDF preview dialog."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'No Company', 'Please select a company first.')
            return
        if not self.visible_data:
            QMessageBox.warning(self, 'No Data', 'No data to export.')
            return
        subtitle = f"Company: {active_company.get('name', '')}"
        summary_lines = [f"Search: {self.search_input.text().strip() or 'All Items'}", f'Visible Items: {len(self.visible_data)}']
        html_string = table_widget_to_html(self.table, 'Price List', subtitle, summary_lines)
        dialog = UniversalPreviewDialog(html_string, self)
        dialog.exec()

    def export_excel(self):
        """Export price list to Excel using ExportEngine."""
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, 'No Company', 'Please select a company first.')
            return
        if not self.visible_data:
            QMessageBox.warning(self, 'No Data', 'No data to export.')
            return
        headers = ['Item Code', 'Item Name', 'Current Stock', 'Purchase Rate', 'Sales Rate', 'Wholesale Rate', 'MRP', 'Markup %', 'Gross Margin %']
        data = []
        for item in self.visible_data:
            data.append([str(item['item_code']), str(item['item_name']), f"{item['current_stock']:.2f}", f"{item['purchase_rate']:.2f}", f"{item['sales_rate']:.2f}", f"{item['wholesale_rate']:.2f}", f"{item['mrp']:.2f}", f"{item.get('markup_percent', 0.0):.2f}", f"{item.get('gross_margin_percent', 0.0):.2f}"])
        path, _ = QFileDialog.getSaveFileName(self, 'Export Excel', 'price_list.xlsx', 'Excel Files (*.xlsx)')
        if not path:
            return
        result = self.export_engine.export_table_to_excel(title='Price List', headers=headers, data=data, filepath=path)
        if result['success']:
            QMessageBox.information(self, 'Export', 'Excel export completed successfully.')
        else:
            QMessageBox.critical(self, 'Export Error', result.get('error', 'Unknown error'))

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        from ui.book_report_common import report_data_table_style
        self.setStyleSheet(theme.master_page_background_style())
        if hasattr(self, 'search_input'):
            self.search_input.setStyleSheet(theme.sales_barcode_input_style())
        if hasattr(self, 'load_btn'):
            from ui.book_report_common import compact_primary_button_style
            self.load_btn.setStyleSheet(compact_primary_button_style())
        for button_name in ('export_pdf_btn', 'export_excel_btn'):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setStyleSheet(theme.sales_compact_button_style())
        if hasattr(self, 'table'):
            self.table.setStyleSheet(report_data_table_style())