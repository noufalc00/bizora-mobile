"""
Stock Report Page Widget
Displays stock reports with filtering, pagination, and multiple report types.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QGroupBox, QLineEdit, QGridLayout, QDialog, QMessageBox, QSizePolicy
from PySide6.QtCore import Qt, QDate, QTimer, QObject, QThread, Signal
from PySide6.QtGui import QFont, QColor
from config import COLORS, active_company_manager, resolve_active_company_id
from bizora_core.stock_report_logic import StockReportLogic
from db import Database
from ui.book_report_common import BOOK_REPORT_ACTION_BUTTON_HEIGHT, add_labeled_filter_rows, attach_filter_action_row, compact_label_style, compact_input_style, compact_date_style, compact_primary_button_style, compact_secondary_button_style, compact_topbar_frame_style, create_filter_action_layout, page_heading_style, report_summary_label_style
from ui.report_preview_utils import table_widget_to_html
from ui.universal_preview_dialog import UniversalPreviewDialog
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin, memory_table_attr_slug

class StockReportWorker(QObject):
    """Load stock report data on a worker-owned database connection."""
    data_ready = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type, db_path, company_id, report_type, filters, page_size, offset, selected_product_id):
        """Initialize worker with immutable report inputs."""
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id
        self.report_type = report_type
        self.filters = dict(filters or {})
        self.page_size = page_size
        self.offset = offset
        self.selected_product_id = selected_product_id

    def run(self):
        """Fetch finalized report data outside the GUI thread."""
        worker_db = None
        try:
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            logic = StockReportLogic(worker_db)
            stats_result = logic.get_stock_summary_stats(self.company_id)
            if self.report_type == 'Stock Summary':
                result = logic.get_stock_summary(self.company_id, self.filters, self.page_size, self.offset)
            elif self.report_type == 'Stock Ledger':
                if not self.selected_product_id:
                    self.error.emit('Please select a product from Stock Summary first.')
                    return
                result = logic.get_stock_ledger(self.company_id, self.selected_product_id, self.filters.get('date_from'), self.filters.get('date_to'), self.page_size, self.offset)
            elif self.report_type == 'Negative Stock':
                result = logic.get_negative_stock(self.company_id, self.filters, self.page_size, self.offset)
            elif self.report_type == 'Zero Stock':
                result = logic.get_zero_stock(self.company_id, self.filters, self.page_size, self.offset)
            elif self.report_type == 'Low Stock':
                result = logic.get_low_stock(self.company_id, self.filters, self.page_size, self.offset)
            elif self.report_type == 'Stock Valuation':
                result = logic.get_stock_value(self.company_id, self.filters)
            else:
                self.error.emit(f'Unsupported stock report: {self.report_type}')
                return
            if not result.get('success'):
                self.error.emit(result.get('message') or 'Unable to load stock report.')
                return
            self.data_ready.emit({'report_type': self.report_type, 'result': result, 'stats': stats_result.get('data', {}) if stats_result.get('success') else {}})
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                worker_db.force_disconnect()
            self.finished.emit()

class StockReportPageWidget(UiMemoryMixin, QWidget):
    """Widget for displaying stock reports."""

    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self.db = db or Database()
        self.stock_logic = StockReportLogic(self.db)
        self.company_id = resolve_active_company_id(self.db)
        self.current_page = 0
        self.page_size = 100
        self.total_count = 0
        self.page_sizes = [50, 100, 250, 500]
        self.current_report_type = 'Stock Summary'
        self.selected_product_id = None
        self._loading = False
        self._stock_thread = None
        self._stock_worker = None
        self.setup_ui()
        self._sync_table_headers_for_report_type(self.current_report_type)
        self._init_ui_memory(table_attrs=("table",))
        self._restore_memory_table(
            self.table,
            f"table_{memory_table_attr_slug(self.current_report_type)}",
        )

    def _finalize_table_memory(self, report_type: str | None = None) -> None:
        """Restore saved column widths for the active stock report layout."""
        report_key = report_type or getattr(self, "current_report_type", "Stock Summary")
        attr = f"table_{memory_table_attr_slug(report_key)}"
        if self.table.columnCount() > 0:
            apply_adjustable_table_columns(self.table, sl_no_column=0)
        self._ui_memory_active_table_attr = attr
        self._ui_memory_active_table = self.table
        self._restore_memory_table(self.table, attr)

    def _stock_report_headers(self, report_type: str) -> list[str]:
        """Return column headers for a stock report layout."""
        headers_map = {
            "Stock Summary": [
                "SL No", "Product", "Barcode", "Category", "Unit", "Opening Qty",
                "Purchase Qty", "Sales Qty", "Sales Return Qty", "Purchase Return Qty",
                "Adjustment Qty", "Closing Qty", "Purchase Rate", "Sales Rate",
                "Stock Value", "Last Movement",
            ],
            "Stock Ledger": [
                "SL No", "Date", "Voucher Type", "Voucher No", "Narration",
                "Qty In", "Qty Out", "Rate", "Value", "Balance Qty", "Balance Value",
            ],
            "Negative Stock": [
                "SL No", "Product", "Barcode", "Category", "Unit",
                "Closing Qty", "Purchase Rate", "Sales Rate",
            ],
            "Zero Stock": [
                "SL No", "Product", "Barcode", "Category", "Unit",
                "Closing Qty", "Purchase Rate", "Sales Rate",
            ],
            "Low Stock": [
                "SL No", "Product", "Barcode", "Category", "Unit", "Reorder Level",
                "Closing Qty", "Purchase Rate", "Sales Rate",
            ],
            "Stock Valuation": ["Total Stock Value"],
        }
        return headers_map.get(report_type, headers_map["Stock Summary"])

    def _sync_table_headers_for_report_type(self, report_type: str | None = None) -> None:
        """Pre-fill stock table headers and restore saved widths for the layout."""
        report_key = report_type or getattr(self, "current_report_type", "Stock Summary")
        headers = self._stock_report_headers(report_key)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        apply_read_only_report_table_selection(self.table)
        attr = f"table_{memory_table_attr_slug(report_key)}"
        self._ui_memory_active_table_attr = attr
        self._ui_memory_active_table = self.table
        if hasattr(self, "settings"):
            apply_adjustable_table_columns(self.table, sl_no_column=0)
            self._restore_memory_table(self.table, attr)

    def setup_ui(self):
        """Setup the stock report page UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        header_layout = QHBoxLayout()
        title_label = QLabel('Stock Report')
        title_label.setStyleSheet(f"\n            QLabel {{\n                font-size: 24px;\n                font-weight: bold;\n                color: {COLORS['text_primary']};\n            }}\n        ")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setStyleSheet(f"\n            QPushButton {{\n                background-color: {COLORS['primary']};\n                color: white;\n                border: none;\n                border-radius: 4px;\n                padding: 8px 16px;\n                font-weight: bold;\n            }}\n            QPushButton:hover {{\n                background-color: {COLORS['primary_dark']};\n            }}\n        ")
        self.refresh_btn.clicked.connect(self.refresh_report)
        header_layout.addWidget(self.refresh_btn)
        self.export_btn = QPushButton('Export')
        self.export_btn.setStyleSheet(f"\n            QPushButton {{\n                background-color: {COLORS['success']};\n                color: white;\n                border: none;\n                border-radius: 4px;\n                padding: 8px 16px;\n                font-weight: bold;\n            }}\n            QPushButton:hover {{\n                background-color: #059669;\n            }}\n            QPushButton:disabled {{\n                background-color: {COLORS['text_secondary']};\n                color: {COLORS['surface']};\n            }}\n        ")
        self.export_btn.setEnabled(False)
        self.export_btn.setToolTip('Export will be enabled after report stabilization.')
        self.export_btn.clicked.connect(self.export_report)
        header_layout.addWidget(self.export_btn)
        layout.addLayout(header_layout)
        self.setup_summary_cards(layout)
        self.setup_filters(layout)
        self.setup_table(layout)
        self.setup_pagination(layout)
        QTimer.singleShot(100, self.load_report)

    def setup_summary_cards(self, parent_layout):
        """Setup summary cards section."""
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(8)
        self.total_products_card = self.create_summary_card('Total Products', '0', COLORS['primary'])
        cards_layout.addWidget(self.total_products_card)
        self.total_qty_card = self.create_summary_card('Total Stock Qty', '0', COLORS['info'])
        cards_layout.addWidget(self.total_qty_card)
        self.total_value_card = self.create_summary_card('Total Stock Value', '₹0', COLORS['success'])
        cards_layout.addWidget(self.total_value_card)
        self.negative_count_card = self.create_summary_card('Negative Stock', '0', COLORS['error'])
        cards_layout.addWidget(self.negative_count_card)
        self.zero_count_card = self.create_summary_card('Zero Stock', '0', COLORS['warning'])
        cards_layout.addWidget(self.zero_count_card)
        parent_layout.addLayout(cards_layout)

    def create_summary_card(self, title, value, color):
        """Create a summary card widget."""
        card = QFrame()
        card.setStyleSheet(compact_topbar_frame_style())
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet(compact_label_style())
        card_layout.addWidget(title_label)
        value_label = QLabel(value)
        value_label.setStyleSheet(f'color: {color}; font-size: 14px; font-weight: bold; background: transparent; border: none;')
        card_layout.addWidget(value_label)
        return card

    def setup_filters(self, parent_layout):
        """Setup filter section using a single aligned filter band plus action buttons."""
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QVBoxLayout(filter_frame)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(10)
        filter_grid = QGridLayout()
        filter_grid.setContentsMargins(0, 0, 0, 0)
        filter_grid.setHorizontalSpacing(10)
        filter_grid.setVerticalSpacing(6)

        field_height = BOOK_REPORT_ACTION_BUTTON_HEIGHT
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText('Search product...')
        self.product_search.setMinimumWidth(160)
        self.product_search.setFixedHeight(field_height)
        self.product_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.product_search.setStyleSheet(compact_input_style())
        self.product_search.returnPressed.connect(self.on_product_enter)

        self.report_type_combo = QComboBox()
        self.report_type_combo.addItems(
            ['Stock Summary', 'Stock Ledger', 'Negative Stock', 'Zero Stock', 'Low Stock', 'Stock Valuation']
        )
        self.report_type_combo.setMinimumWidth(130)
        self.report_type_combo.setFixedHeight(field_height)
        self.report_type_combo.setStyleSheet(compact_input_style())
        self.report_type_combo.currentTextChanged.connect(self.on_report_type_changed)

        self.status_combo = QComboBox()
        self.status_combo.addItems(['All', 'In Stock', 'Low Stock', 'Negative Stock', 'Zero Stock'])
        self.status_combo.setMinimumWidth(95)
        self.status_combo.setFixedHeight(field_height)
        self.status_combo.setStyleSheet(compact_input_style())

        self.from_date_edit = QDateEdit()
        self.from_date_edit.setDate(QDate.currentDate().addMonths(-1))
        prepare_report_date_edit(self.from_date_edit, style_sheet=compact_date_style())
        self.from_date_edit.setFixedHeight(field_height)

        self.to_date_edit = QDateEdit()
        self.to_date_edit.setDate(QDate.currentDate())
        prepare_report_date_edit(self.to_date_edit, style_sheet=compact_date_style())
        self.to_date_edit.setFixedHeight(field_height)

        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems([str(size) for size in self.page_sizes])
        self.page_size_combo.setCurrentText(str(self.page_size))
        self.page_size_combo.setMinimumWidth(72)
        self.page_size_combo.setFixedHeight(field_height)
        self.page_size_combo.setStyleSheet(compact_input_style())
        self.page_size_combo.currentTextChanged.connect(self.on_page_size_changed)

        add_labeled_filter_rows(
            filter_grid,
            [[
                ('Product', self.product_search),
                ('Report', self.report_type_combo),
                ('Status', self.status_combo),
                ('From', self.from_date_edit),
                ('To', self.to_date_edit),
                ('Page Size', self.page_size_combo),
            ]],
        )
        # Keep the product search elastic; date/page-size columns stay fixed width.
        for col in range(filter_grid.columnCount()):
            filter_grid.setColumnStretch(col, 0)
        filter_grid.setColumnStretch(0, 1)

        search_button = QPushButton('Search')
        search_button.clicked.connect(self.load_report)
        show_all_button = QPushButton('Show All')
        show_all_button.clicked.connect(self.show_all_stock)
        self.show_btn = QPushButton('Show')
        self.show_btn.clicked.connect(self.load_report)
        self.reset_btn = QPushButton('Reset')
        self.reset_btn.setStyleSheet(compact_secondary_button_style())
        self.reset_btn.clicked.connect(self.reset_filters)
        self.export_excel_btn = QPushButton('Excel')
        self.export_excel_btn.setStyleSheet(compact_secondary_button_style())
        self.export_excel_btn.clicked.connect(self.export_excel)
        self.export_pdf_btn = QPushButton('PDF')
        self.export_pdf_btn.setStyleSheet(compact_secondary_button_style())
        self.export_pdf_btn.clicked.connect(self.export_pdf)
        action_layout = create_filter_action_layout(
            [search_button, show_all_button, self.show_btn, self.reset_btn, self.export_excel_btn, self.export_pdf_btn]
        )
        for secondary_btn in (self.reset_btn, self.export_excel_btn, self.export_pdf_btn):
            secondary_btn.setStyleSheet(compact_secondary_button_style())
            secondary_btn.setFixedHeight(field_height)
            secondary_btn.setMinimumWidth(68)
        attach_filter_action_row(filter_grid, action_layout, row=2)
        filter_layout.addLayout(filter_grid)
        parent_layout.addWidget(filter_frame)

    def setup_table(self, parent_layout):
        """Setup main table."""
        self.table = QTableWidget()
        apply_read_only_report_table_selection(self.table)
        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.verticalHeader().setMinimumSectionSize(20)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(self.on_table_double_click)
        parent_layout.addWidget(self.table)

    def setup_pagination(self, parent_layout):
        """Setup pagination controls."""
        pagination_layout = QHBoxLayout()
        pagination_layout.addStretch()
        self.page_label = QLabel('Page 0 of 0')
        self.page_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        pagination_layout.addWidget(self.page_label)
        self.prev_btn = QPushButton('Previous')
        self.prev_btn.setStyleSheet(f"\n            QPushButton {{\n                background-color: {COLORS['surface']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 4px;\n                padding: 6px 16px;\n            }}\n            QPushButton:hover {{\n                background-color: {COLORS['border']};\n            }}\n            QPushButton:disabled {{\n                color: {COLORS['text_disabled']};\n            }}\n        ")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        pagination_layout.addWidget(self.prev_btn)
        self.next_btn = QPushButton('Next')
        self.next_btn.setStyleSheet(f"\n            QPushButton {{\n                background-color: {COLORS['surface']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 4px;\n                padding: 6px 16px;\n            }}\n            QPushButton:hover {{\n                background-color: {COLORS['border']};\n            }}\n            QPushButton:disabled {{\n                color: {COLORS['text_disabled']};\n            }}\n        ")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        pagination_layout.addWidget(self.next_btn)
        parent_layout.addLayout(pagination_layout)

    def load_summary_stats(self):
        """Load summary statistics."""
        if not self.company_id:
            return
        result = self.stock_logic.get_stock_summary_stats(self.company_id)
        if result['success']:
            stats = result['data']
            self.total_products_card.layout().itemAt(1).widget().setText(str(stats.get('total_products', 0)))
            self.total_qty_card.layout().itemAt(1).widget().setText(f"{stats.get('total_qty', 0):.2f}")
            self.total_value_card.layout().itemAt(1).widget().setText(f"₹{stats.get('total_value', 0):.2f}")
            self.negative_count_card.layout().itemAt(1).widget().setText(str(stats.get('negative_count', 0)))
            self.zero_count_card.layout().itemAt(1).widget().setText(str(stats.get('zero_count', 0)))

    def load_report(self):
        """Load report based on selected type."""
        if self._loading:
            return
        print(f'[STOCK DEBUG] load_report called')
        self.company_id = resolve_active_company_id(self.db)
        print(f'[STOCK DEBUG] active_company_id: {self.company_id}')
        if not self.company_id:
            print(f'[STOCK DEBUG] No active company selected')
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        report_type = self.report_type_combo.currentText()
        self.current_report_type = report_type
        print(f'[STOCK DEBUG] report_type: {report_type}')
        filters = {'search_text': self.product_search.text().strip(), 'date_from': qdate_to_db(self.from_date_edit.date()), 'date_to': qdate_to_db(self.to_date_edit.date()), 'stock_status': self.status_combo.currentText()}
        print(f'[STOCK DEBUG] filters: {filters}')
        offset = self.current_page * self.page_size
        thread = QThread(self)
        worker = StockReportWorker(getattr(self.db, 'db_type', None), getattr(self.db, 'db_path', None), self.company_id, report_type, filters, self.page_size, offset, self.selected_product_id)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(self._apply_stock_report_result)
        worker.error.connect(self._show_load_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._stock_worker_finished)
        self._stock_thread = thread
        self._stock_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _apply_stock_report_result(self, payload):
        """Populate the current report from worker results on the GUI thread."""
        stats = payload.get('stats') or {}
        if stats:
            self.total_products_card.layout().itemAt(1).widget().setText(str(stats.get('total_products', 0)))
            self.total_qty_card.layout().itemAt(1).widget().setText(f"{stats.get('total_qty', 0):.2f}")
            self.total_value_card.layout().itemAt(1).widget().setText(f"₹{stats.get('total_value', 0):.2f}")
            self.negative_count_card.layout().itemAt(1).widget().setText(str(stats.get('negative_count', 0)))
            self.zero_count_card.layout().itemAt(1).widget().setText(str(stats.get('zero_count', 0)))
        report_type = payload.get('report_type')
        result = payload.get('result') or {}
        self.total_count = result.get('total_count', 0)
        data = result.get('data', [])
        if report_type == 'Stock Summary':
            self.populate_stock_summary_table(data)
        elif report_type == 'Stock Ledger':
            self.populate_stock_ledger_table(data)
        elif report_type == 'Negative Stock':
            self.populate_negative_stock_table(data)
        elif report_type == 'Zero Stock':
            self.populate_zero_stock_table(data)
        elif report_type == 'Low Stock':
            self.populate_low_stock_table(data)
        elif report_type == 'Stock Valuation':
            value = data
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(['Total Stock Value'])
            self.table.setItem(0, 0, QTableWidgetItem(f'₹{value:.2f}'))
            apply_adjustable_table_columns(self.table)
            self._finalize_table_memory("Stock Valuation")
            self.total_count = 0
        self.update_pagination()
        if hasattr(self, '_make_table_readonly_and_aligned'):
            self._make_table_readonly_and_aligned()
        if hasattr(self, '_refresh_product_search_suggestions'):
            self._refresh_product_search_suggestions()

    def _set_loading_state(self, is_loading):
        """Disable report controls while a worker is active."""
        self._loading = is_loading
        controls = [self.refresh_btn, self.show_btn, self.reset_btn, self.export_excel_btn, self.export_pdf_btn, self.prev_btn, self.next_btn, self.product_search, self.report_type_combo, self.status_combo, self.from_date_edit, self.to_date_edit, self.page_size_combo]
        for control in controls:
            control.setEnabled(not is_loading)
        self.show_btn.setText('Loading...' if is_loading else 'Show')
        if is_loading:
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(['Loading'])
            self.table.setItem(0, 0, QTableWidgetItem('Loading stock report...'))

    def _stock_worker_finished(self):
        """Clear worker references and restore controls."""
        self._stock_thread = None
        self._stock_worker = None
        self._set_loading_state(False)
        self.update_pagination()

    def _show_load_error(self, message):
        """Display worker errors without blocking the UI thread."""
        self.table.setRowCount(1)
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(['Error'])
        self.table.setItem(0, 0, QTableWidgetItem(message))
        QMessageBox.warning(self, 'Error', message)

    def load_stock_summary(self, filters):
        """Load stock summary report."""
        print(f'[STOCK DEBUG] load_stock_summary called')
        offset = self.current_page * self.page_size
        result = self.stock_logic.get_stock_summary(self.company_id, filters, self.page_size, offset)
        print(f"[STOCK DEBUG] result success: {result['success']}")
        if result['success']:
            self.total_count = result['total_count']
            data = result['data']
            print(f'[STOCK DEBUG] rows returned from logic: {len(data)}')
            self.populate_stock_summary_table(data)
            print(f'[STOCK DEBUG] rows inserted into table: {self.table.rowCount()}')
            self.update_pagination()
        else:
            print(f"[STOCK DEBUG] Error: {result['message']}")
            QMessageBox.warning(self, 'Error', result['message'])

    def load_stock_ledger(self, filters):
        """Load stock ledger report for selected product."""
        print(f'[STOCK DEBUG] load_stock_ledger called')
        if not self.selected_product_id:
            print(f'[STOCK DEBUG] No selected_product_id')
            QMessageBox.information(self, 'Info', 'Please select a product from Stock Summary first.')
            self.report_type_combo.setCurrentText('Stock Summary')
            return
        offset = self.current_page * self.page_size
        result = self.stock_logic.get_stock_ledger(self.company_id, self.selected_product_id, filters.get('date_from'), filters.get('date_to'), self.page_size, offset)
        print(f"[STOCK DEBUG] result success: {result['success']}")
        if result['success']:
            self.total_count = result['total_count']
            data = result['data']
            print(f'[STOCK DEBUG] rows returned from logic: {len(data)}')
            self.populate_stock_ledger_table(data)
            print(f'[STOCK DEBUG] rows inserted into table: {self.table.rowCount()}')
            self.update_pagination()
        else:
            print(f"[STOCK DEBUG] Error: {result['message']}")
            QMessageBox.warning(self, 'Error', result['message'])

    def load_negative_stock(self, filters):
        """Load negative stock report."""
        print(f'[STOCK DEBUG] load_negative_stock called')
        offset = self.current_page * self.page_size
        result = self.stock_logic.get_negative_stock(self.company_id, filters, self.page_size, offset)
        print(f"[STOCK DEBUG] result success: {result['success']}")
        if result['success']:
            self.total_count = result['total_count']
            data = result['data']
            print(f'[STOCK DEBUG] rows returned from logic: {len(data)}')
            self.populate_negative_stock_table(data)
            print(f'[STOCK DEBUG] rows inserted into table: {self.table.rowCount()}')
            self.update_pagination()
        else:
            print(f"[STOCK DEBUG] Error: {result['message']}")
            QMessageBox.warning(self, 'Error', result['message'])

    def load_zero_stock(self, filters):
        """Load zero stock report."""
        print(f'[STOCK DEBUG] load_zero_stock called')
        offset = self.current_page * self.page_size
        result = self.stock_logic.get_zero_stock(self.company_id, filters, self.page_size, offset)
        print(f"[STOCK DEBUG] result success: {result['success']}")
        if result['success']:
            self.total_count = result['total_count']
            data = result['data']
            print(f'[STOCK DEBUG] rows returned from logic: {len(data)}')
            self.populate_zero_stock_table(data)
            print(f'[STOCK DEBUG] rows inserted into table: {self.table.rowCount()}')
            self.update_pagination()
        else:
            print(f"[STOCK DEBUG] Error: {result['message']}")
            QMessageBox.warning(self, 'Error', result['message'])

    def load_low_stock(self, filters):
        """Load low stock report."""
        print(f'[STOCK DEBUG] load_low_stock called')
        offset = self.current_page * self.page_size
        result = self.stock_logic.get_low_stock(self.company_id, filters, self.page_size, offset)
        print(f"[STOCK DEBUG] result success: {result['success']}")
        if result['success']:
            self.total_count = result['total_count']
            data = result['data']
            print(f'[STOCK DEBUG] rows returned from logic: {len(data)}')
            self.populate_low_stock_table(data)
            print(f'[STOCK DEBUG] rows inserted into table: {self.table.rowCount()}')
            self.update_pagination()
        else:
            print(f"[STOCK DEBUG] Error: {result['message']}")
            QMessageBox.warning(self, 'Error', result['message'])

    def load_stock_valuation(self, filters):
        """Load stock valuation report."""
        print(f'[STOCK DEBUG] load_stock_valuation called')
        result = self.stock_logic.get_stock_value(self.company_id, filters)
        print(f"[STOCK DEBUG] result success: {result['success']}")
        if result['success']:
            value = result['data']
            print(f'[STOCK DEBUG] stock value: {value}')
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(['Total Stock Value'])
            self.table.setItem(0, 0, QTableWidgetItem(f'₹{value:.2f}'))
            apply_adjustable_table_columns(self.table)
            self._finalize_table_memory("Stock Valuation")
            self.total_count = 0
            self.update_pagination()
        else:
            print(f"[STOCK DEBUG] Error: {result['message']}")
            QMessageBox.warning(self, 'Error', result['message'])

    def populate_stock_summary_table(self, data):
        """Populate stock summary table with warning color for negative stock.
        
        Formula: closing = opening + purchase - sales + sales_return - purchase_return + adjustment
        """
        columns = ['SL No', 'Product', 'Barcode', 'Category', 'Unit', 'Opening Qty', 'Purchase Qty', 'Sales Qty', 'Sales Return Qty', 'Purchase Return Qty', 'Adjustment Qty', 'Closing Qty', 'Purchase Rate', 'Sales Rate', 'Stock Value', 'Last Movement']
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        if not data:
            print(f'[STOCK DEBUG] No data found, showing message row')
            self.table.setRowCount(1)
            self.table.setItem(0, 0, QTableWidgetItem(''))
            self.table.setItem(0, 1, QTableWidgetItem('No stock data found.'))
            for col in range(2, 16):
                self.table.setItem(0, col, QTableWidgetItem(''))
            apply_adjustable_table_columns(self.table, sl_no_column=0)
            self._finalize_table_memory("Stock Summary")
            return
        self.table.setRowCount(len(data))
        for row, item in enumerate(data):
            product_id = item.get('id')
            sl_item = QTableWidgetItem(str(row + 1))
            sl_item.setData(Qt.UserRole, product_id)
            self.table.setItem(row, 0, sl_item)
            name_item = QTableWidgetItem(item.get('name', ''))
            name_item.setData(Qt.UserRole, product_id)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, QTableWidgetItem(item.get('barcode', '')))
            self.table.setItem(row, 3, QTableWidgetItem(item.get('category', '')))
            self.table.setItem(row, 4, QTableWidgetItem(item.get('unit', '')))
            self.table.setItem(row, 5, QTableWidgetItem(f"{item.get('opening_qty', 0):.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{item.get('purchase_qty', 0):.2f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{item.get('sales_qty', 0):.2f}"))
            self.table.setItem(row, 8, QTableWidgetItem(f"{item.get('sales_return_qty', 0):.2f}"))
            self.table.setItem(row, 9, QTableWidgetItem(f"{item.get('purchase_return_qty', 0):.2f}"))
            self.table.setItem(row, 10, QTableWidgetItem(f"{item.get('adjustment_qty', 0):.2f}"))
            closing_qty = item.get('closing_qty', 0)
            qty_item = QTableWidgetItem(f'{closing_qty:.2f}')
            if closing_qty < 0:
                qty_item.setBackground(QColor(254, 202, 202))
            self.table.setItem(row, 11, qty_item)
            self.table.setItem(row, 12, QTableWidgetItem(f"{item.get('purchase_rate', 0):.2f}"))
            self.table.setItem(row, 13, QTableWidgetItem(f"{item.get('sale_price', 0):.2f}"))
            stock_value = closing_qty * item.get('purchase_rate', 0)
            self.table.setItem(row, 14, QTableWidgetItem(f'₹{stock_value:.2f}'))
            self.table.setItem(row, 15, QTableWidgetItem(item.get('last_movement_date', '') or ''))
        apply_adjustable_table_columns(self.table, sl_no_column=0)
        self._finalize_table_memory("Stock Summary")

    def populate_stock_ledger_table(self, data):
        """Populate stock ledger table."""
        columns = ['SL No', 'Date', 'Voucher Type', 'Voucher No', 'Narration', 'Qty In', 'Qty Out', 'Rate', 'Value', 'Balance Qty', 'Balance Value']
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(item.get('movement_date', '')))
            self.table.setItem(row, 2, QTableWidgetItem(item.get('voucher_type', item.get('movement_type', ''))))
            self.table.setItem(row, 3, QTableWidgetItem(item.get('voucher_no', '')))
            self.table.setItem(row, 4, QTableWidgetItem(item.get('narration', '')))
            self.table.setItem(row, 5, QTableWidgetItem(f"{item.get('qty_in', 0):.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{item.get('qty_out', 0):.2f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{item.get('rate', 0):.2f}"))
            value = item.get('value_in', 0) + item.get('value_out', 0)
            self.table.setItem(row, 8, QTableWidgetItem(f'₹{value:.2f}'))
            self.table.setItem(row, 9, QTableWidgetItem(f"{item.get('balance_qty', 0):.2f}"))
            self.table.setItem(row, 10, QTableWidgetItem(f"₹{item.get('balance_value', 0):.2f}"))
        apply_adjustable_table_columns(self.table, sl_no_column=0)
        self._finalize_table_memory("Stock Ledger")

    def populate_negative_stock_table(self, data):
        """Populate negative stock table with warning color."""
        columns = ['SL No', 'Product', 'Barcode', 'Category', 'Unit', 'Closing Qty', 'Purchase Rate', 'Sales Rate']
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(item.get('name', '')))
            self.table.setItem(row, 2, QTableWidgetItem(item.get('barcode', '')))
            self.table.setItem(row, 3, QTableWidgetItem(item.get('category', '')))
            self.table.setItem(row, 4, QTableWidgetItem(item.get('unit', '')))
            qty_item = QTableWidgetItem(f"{item.get('closing_qty', 0):.2f}")
            qty_item.setBackground(QColor(254, 202, 202))
            self.table.setItem(row, 5, qty_item)
            self.table.setItem(row, 6, QTableWidgetItem(f"{item.get('purchase_rate', 0):.2f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{item.get('sale_price', 0):.2f}"))
        apply_adjustable_table_columns(self.table, sl_no_column=0)
        self._finalize_table_memory("Negative Stock")

    def populate_zero_stock_table(self, data):
        """Populate zero stock table."""
        columns = ['SL No', 'Product', 'Barcode', 'Category', 'Unit', 'Closing Qty', 'Purchase Rate', 'Sales Rate']
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(item.get('name', '')))
            self.table.setItem(row, 2, QTableWidgetItem(item.get('barcode', '')))
            self.table.setItem(row, 3, QTableWidgetItem(item.get('category', '')))
            self.table.setItem(row, 4, QTableWidgetItem(item.get('unit', '')))
            self.table.setItem(row, 5, QTableWidgetItem(f"{item.get('closing_qty', 0):.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{item.get('purchase_rate', 0):.2f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{item.get('sale_price', 0):.2f}"))
        apply_adjustable_table_columns(self.table, sl_no_column=0)
        self._finalize_table_memory("Zero Stock")

    def populate_low_stock_table(self, data):
        """Populate low stock table."""
        columns = ['SL No', 'Product', 'Barcode', 'Category', 'Unit', 'Reorder Level', 'Closing Qty', 'Purchase Rate', 'Sales Rate']
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(item.get('name', '')))
            self.table.setItem(row, 2, QTableWidgetItem(item.get('barcode', '')))
            self.table.setItem(row, 3, QTableWidgetItem(item.get('category', '')))
            self.table.setItem(row, 4, QTableWidgetItem(item.get('unit', '')))
            self.table.setItem(row, 5, QTableWidgetItem(f"{item.get('reorder_level', 0):.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{item.get('closing_qty', 0):.2f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{item.get('purchase_rate', 0):.2f}"))
            self.table.setItem(row, 8, QTableWidgetItem(f"{item.get('sale_price', 0):.2f}"))
        apply_adjustable_table_columns(self.table, sl_no_column=0)
        self._finalize_table_memory("Low Stock")

    def update_pagination(self):
        """Update pagination controls."""
        total_pages = (self.total_count + self.page_size - 1) // self.page_size if self.total_count > 0 else 0
        self.page_label.setText(f'Page {self.current_page + 1} of {total_pages}')
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)

    def prev_page(self):
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self.load_report()

    def next_page(self):
        """Go to next page."""
        total_pages = (self.total_count + self.page_size - 1) // self.page_size
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.load_report()

    def on_report_type_changed(self, text):
        """Handle report type change."""
        self.selected_product_id = None
        self.current_page = 0
        self.current_report_type = text
        self.status_combo.setEnabled(text == 'Stock Summary')
        self._sync_table_headers_for_report_type(text)

    def on_table_double_click(self, row, column):
        """Handle table double-click for drill-down."""
        if self.current_report_type == 'Stock Summary' and self.table.rowCount() > 0:
            item = self.table.item(row, 0)
            if item:
                product_id = item.data(Qt.UserRole)
                if product_id:
                    self.show_product_detail_dialog(product_id)
                else:
                    self.selected_product_id = None
                    self.report_type_combo.setCurrentText('Stock Ledger')
        elif self.current_report_type == 'Stock Ledger' and self.table.rowCount() > 0:
            self.show_movement_detail_dialog(row)

    def show_product_detail_dialog(self, product_id):
        """Show product stock detail dialog with dark theme."""
        product_data = None
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == product_id:
                product_data = {'name': self.table.item(row, 1).text() if self.table.item(row, 1) else '', 'barcode': self.table.item(row, 2).text() if self.table.item(row, 2) else '', 'category': self.table.item(row, 3).text() if self.table.item(row, 3) else '', 'unit': self.table.item(row, 4).text() if self.table.item(row, 4) else '', 'opening_qty': self.table.item(row, 5).text() if self.table.item(row, 5) else '0', 'purchase_qty': self.table.item(row, 6).text() if self.table.item(row, 6) else '0', 'sales_qty': self.table.item(row, 7).text() if self.table.item(row, 7) else '0', 'sales_return_qty': self.table.item(row, 8).text() if self.table.item(row, 8) else '0', 'purchase_return_qty': self.table.item(row, 9).text() if self.table.item(row, 9) else '0', 'adjustment_qty': self.table.item(row, 10).text() if self.table.item(row, 10) else '0', 'closing_qty': self.table.item(row, 11).text() if self.table.item(row, 11) else '0', 'purchase_rate': self.table.item(row, 12).text() if self.table.item(row, 12) else '0', 'sale_price': self.table.item(row, 13).text() if self.table.item(row, 13) else '0', 'stock_value': self.table.item(row, 14).text() if self.table.item(row, 14) else '0', 'last_movement': self.table.item(row, 15).text() if self.table.item(row, 15) else ''}
                break
        if not product_data:
            QMessageBox.information(self, 'No Data', 'Product data not found.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Product Stock Details - {product_data['name']}")
        dialog.setMinimumSize(600, 500)
        dialog.setStyleSheet(f"\n            QDialog {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n            }}\n            QLabel {{\n                color: {COLORS['text_primary']};\n                background-color: transparent;\n            }}\n            QTableWidget {{\n                background-color: {COLORS['surface']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                gridline-color: {COLORS['border']};\n            }}\n            QTableWidget::item {{\n                padding: 8px;\n                border-bottom: 1px solid {COLORS['border']};\n            }}\n            QHeaderView::section {{\n                background-color: {COLORS['primary']};\n                color: white;\n                padding: 10px;\n                border: none;\n                font-weight: bold;\n            }}\n            QPushButton {{\n                background-color: {COLORS['primary']};\n                color: white;\n                border: none;\n                border-radius: 4px;\n                padding: 8px 20px;\n                font-weight: bold;\n            }}\n            QPushButton:hover {{\n                background-color: {COLORS['primary_dark']};\n            }}\n        ")
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        title_label = QLabel(f"{product_data['name']}")
        title_label.setStyleSheet(f"\n            QLabel {{\n                font-size: 18px;\n                font-weight: bold;\n                color: {COLORS['text_primary']};\n            }}\n        ")
        layout.addWidget(title_label)
        details_table = QTableWidget()
        details_table.setColumnCount(2)
        details_table.setHorizontalHeaderLabels(['Field', 'Value'])
        details_table.setRowCount(11)
        details = [('Barcode', product_data['barcode']), ('Category', product_data['category']), ('Unit', product_data['unit']), ('Opening Qty', product_data['opening_qty']), ('Purchase Qty', product_data['purchase_qty']), ('Sales Qty', product_data['sales_qty']), ('Sales Return Qty', product_data['sales_return_qty']), ('Purchase Return Qty', product_data['purchase_return_qty']), ('Adjustment Qty', product_data['adjustment_qty']), ('Closing Qty', product_data['closing_qty']), ('Stock Value', product_data['stock_value'])]
        for i, (field, value) in enumerate(details):
            field_item = QTableWidgetItem(field)
            field_item.setForeground(QColor(COLORS['text_secondary']))
            details_table.setItem(i, 0, field_item)
            value_item = QTableWidgetItem(value)
            value_item.setForeground(QColor(COLORS['text_primary']))
            details_table.setItem(i, 1, value_item)
        apply_adjustable_table_columns(details_table)
        details_table.verticalHeader().setVisible(False)
        layout.addWidget(details_table)
        close_button = QPushButton('Close')
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.exec()

    def show_movement_detail_dialog(self, row):
        """Show movement detail dialog for stock ledger."""
        dialog = QDialog(self)
        dialog.setWindowTitle('Movement Details')
        dialog.setMinimumSize(500, 300)
        dialog.setStyleSheet(f"\n            QDialog {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n            }}\n            QLabel {{\n                color: {COLORS['text_primary']};\n                background-color: transparent;\n            }}\n            QPushButton {{\n                background-color: {COLORS['primary']};\n                color: white;\n                border: none;\n                border-radius: 4px;\n                padding: 8px 20px;\n                font-weight: bold;\n            }}\n            QPushButton:hover {{\n                background-color: {COLORS['primary_dark']};\n            }}\n        ")
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        info_label = QLabel('Movement details would be loaded here.\n\nThis is a placeholder dialog.')
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"\n            QLabel {{\n                color: {COLORS['text_secondary']};\n                padding: 10px;\n                background-color: {COLORS['surface']};\n                border-radius: 4px;\n            }}\n        ")
        layout.addWidget(info_label)
        layout.addStretch()
        close_button = QPushButton('Close')
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.exec()

    def reset_filters(self):
        """Reset all filters."""
        self.product_search.clear()
        self.from_date_edit.setDate(QDate.currentDate().addMonths(-1))
        self.to_date_edit.setDate(QDate.currentDate())
        self.status_combo.setCurrentText('All')
        self.current_page = 0
        self.load_report()

    def on_page_size_changed(self, text):
        """Handle page size change."""
        self.page_size = int(text)
        self.current_page = 0
        self.load_report()

    def export_excel(self):
        """Export current report to Excel."""
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        report_type = self.current_report_type
        filters = {'search_text': self.product_search.text().strip(), 'date_from': qdate_to_db(self.from_date_edit.date()), 'date_to': qdate_to_db(self.to_date_edit.date()), 'stock_status': self.status_combo.currentText()}
        result = self.stock_logic.export_stock_report_excel(self.company_id, report_type, filters)
        if result['success']:
            QMessageBox.information(self, 'Export', f"Excel exported successfully to: {result['data']}")
        else:
            QMessageBox.warning(self, 'Export Error', result['message'])

    def export_pdf(self):
        """Open current stock report in the universal print/PDF preview dialog."""
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        if self.table.rowCount() <= 0:
            QMessageBox.information(self, 'No Data', 'Load report data first.')
            return
        subtitle = f"{self.current_report_type} | {qdate_to_display(self.from_date_edit.date())} to {qdate_to_display(self.to_date_edit.date())}"
        summary_lines = [f"Product: {self.product_search.text().strip() or 'All'}", f'Status: {self.status_combo.currentText()}', self.page_label.text(), f'Total Rows: {self.total_count}']
        for card in (self.total_products_card, self.total_qty_card, self.total_value_card, self.negative_count_card, self.zero_count_card):
            layout = card.layout()
            if layout and layout.count() >= 2:
                title = layout.itemAt(0).widget().text()
                value = layout.itemAt(1).widget().text()
                summary_lines.append(f'{title}: {value}')
        html_string = table_widget_to_html(self.table, 'Stock Report', subtitle, summary_lines)
        dialog = UniversalPreviewDialog(html_string, self)
        dialog.exec()

    def refresh_report(self):
        """Refresh current report."""
        self.load_summary_stats()
        self.load_report()

    def export_report(self):
        """Export current report (placeholder for future)."""
        QMessageBox.information(self, 'Export', 'Export functionality to be implemented.')

    def on_product_enter(self):
        """Handle product Enter key - open full product dialog popup (like Stock Adjustment)."""
        print(f'[DEBUG] PRODUCT ENTER - opening full dialog popup')
        self.show_product_dialog()

    def show_product_dialog(self):
        """Show product search popup dialog (same pattern as Stock Adjustment)."""
        from config import active_company_manager
        company_id = active_company_manager.get_active_company_id()
        if not company_id:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView
        from PySide6.QtCore import Qt, QTimer
        popup = QDialog(self)
        popup.setWindowTitle('Select Product')
        popup.resize(620, 440)
        popup.setStyleSheet(f"\n            QDialog {{ background-color: {COLORS['background']}; color: {COLORS['text_primary']}; }}\n            QLabel {{ color: {COLORS['warning']}; font-size: 11px; font-weight: bold; }}\n            QLineEdit {{ background-color: {COLORS['surface']}; color: {COLORS['text_primary']}; padding: 4px; }}\n            QPushButton {{ background-color: {COLORS['primary']}; color: white; padding: 6px 12px; }}\n            QPushButton:hover {{ background-color: {COLORS['primary_dark']}; }}\n            QTableWidget {{ background-color: {COLORS['surface']}; color: {COLORS['text_primary']}; gridline-color: {COLORS['border']}; }}\n            QTableWidget::item {{ padding: 4px; }}\n            QTableWidget::item:selected {{ background-color: {COLORS['primary']}; }}\n        ")
        layout = QVBoxLayout(popup)
        search_layout = QHBoxLayout()
        search_label = QLabel('Search Product:')
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type product name or barcode...')
        search_layout.addWidget(search_label)
        search_layout.addWidget(search_input)
        layout.addLayout(search_layout)
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['Name', 'Barcode', 'Stock', 'Rate', ''])
        apply_read_only_report_table_selection(table)
        layout.addWidget(table)
        button_layout = QHBoxLayout()
        select_btn = QPushButton('Select')
        cancel_btn = QPushButton('Cancel')
        button_layout.addWidget(select_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        try:
            ph = self.db._get_placeholder()
            query = f"\n                SELECT p.id, p.name, p.barcode, p.purchase_rate, p.sale_price, p.mrp,\n                       (SELECT SUM(sm.quantity)\n                       FROM stock_movements sm\n                       WHERE sm.company_id = p.company_id\n                         AND sm.product_id = p.id\n                         AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')\n                       ) as quantity\n                FROM products p\n                WHERE p.company_id = {ph}\n                ORDER BY p.name\n                LIMIT 100\n            "
            products = self.db.execute_query(query, (company_id,))
        except Exception as e:
            print(f'Error loading products: {e}')
            products = []
        table.setRowCount(len(products))
        for row, product in enumerate(products):
            table.setItem(row, 0, QTableWidgetItem(str(product.get('name') or '')))
            table.setItem(row, 1, QTableWidgetItem(str(product.get('barcode') or '')))
            try:
                stock_qty = float(product.get('quantity') or 0)
            except (TypeError, ValueError):
                stock_qty = 0.0
            table.setItem(row, 2, QTableWidgetItem(f'{stock_qty:.3f}'))
            try:
                rate = float(
                    product.get('sale_price') or product.get('mrp') or product.get('purchase_rate') or 0
                )
            except (TypeError, ValueError):
                rate = 0.0
            table.setItem(row, 3, QTableWidgetItem(f'{rate:.2f}'))
        apply_adjustable_table_columns(table)
        selected_product = [None]

        def on_search_changed():
            text = search_input.text().strip().lower()
            for row in range(table.rowCount()):
                name = table.item(row, 0).text().lower()
                barcode = table.item(row, 1).text().lower()
                if text in name or text in barcode:
                    table.setRowHidden(row, False)
                else:
                    table.setRowHidden(row, True)

        def on_select():
            current_row = table.currentRow()
            if current_row >= 0:
                name = table.item(current_row, 0).text()
                for product in products:
                    if product.get('name') == name:
                        selected_product[0] = product
                        break
            popup.accept()

        def on_cancel():
            popup.reject()
        search_input.textChanged.connect(on_search_changed)
        select_btn.clicked.connect(on_select)
        cancel_btn.clicked.connect(on_cancel)
        table.doubleClicked.connect(on_select)
        popup.exec()
        if selected_product[0]:
            product_name = selected_product[0].get('name', '')
            print(f'[DEBUG] PRODUCT SELECTED FROM DIALOG = {product_name}')
            self.product_search.setText(product_name)
            self.selected_product_id = selected_product[0].get('id')
            self.load_report()

    def show_all_stock(self):
        """Show all stock report by clearing all filters."""
        self.product_search.clear()
        self.status_combo.setCurrentText('All')
        self.from_date_edit.setDate(QDate.currentDate().addMonths(-1))
        self.to_date_edit.setDate(QDate.currentDate())
        self.selected_product_id = None
        self.load_report()

def _stock_apply_final_ui_fixes(self):
    """Apply Stock Report usability fixes after original setup_ui."""
    try:
        from PySide6.QtWidgets import QCompleter, QAbstractItemView
        from PySide6.QtCore import QStringListModel
        from ui.theme import apply_completer_popup_theme, wire_line_edit_completer
        apply_read_only_report_table_selection(self.table)
        self._product_search_model = QStringListModel(self)
        self._product_search_completer = QCompleter(self._product_search_model, self)
        self._product_search_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._product_search_completer.setFilterMode(Qt.MatchContains)
        self._product_search_completer.setCompletionMode(QCompleter.PopupCompletion)
        wire_line_edit_completer(self.product_search, self._product_search_completer)
        self.product_search.textChanged.connect(self._on_stock_search_text_changed_final)
        self._refresh_product_search_suggestions()
        if self.layout():
            self.layout().setContentsMargins(12, 12, 12, 12)
            self.layout().setSpacing(8)
    except Exception as e:
        try:
            self.product_search.setCompleter(self._product_search_completer)
            from ui.theme import apply_completer_popup_theme
            apply_completer_popup_theme(self._product_search_completer)
        except Exception:
            pass
        print(f'[STOCK FINAL PATCH] UI fix error: {e}')

def _stock_refresh_product_search_suggestions(self):
    """Load product search suggestions from active company."""
    try:
        if not self.company_id:
            return
        ph = self.db._get_placeholder()
        rows = self.db.execute_query(f'\n            SELECT name, barcode, category\n            FROM products\n            WHERE company_id = {ph}\n            ORDER BY name\n            LIMIT 10000\n            ', (self.company_id,))
        values = []
        for row in rows:
            for key in ('name', 'barcode', 'category'):
                value = (row.get(key) or '').strip()
                if value and value not in values:
                    values.append(value)
        self._product_search_model.setStringList(values)
    except Exception as e:
        print(f'[STOCK FINAL PATCH] completer load error: {e}')

def _stock_search_changed_final(self, text):
    """Debounced first-letter search reload."""
    try:
        if not hasattr(self, '_stock_search_timer'):
            self._stock_search_timer = QTimer(self)
            self._stock_search_timer.setSingleShot(True)
            self._stock_search_timer.setInterval(250)
            self._stock_search_timer.timeout.connect(self.load_report)
        self._stock_search_timer.start()
    except Exception:
        pass

def _stock_make_table_readonly_and_aligned(self):
    """After any populate, make rows non-editable and numeric columns right-aligned."""
    try:
        from PySide6.QtWidgets import QAbstractItemView
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if not item:
                    continue
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col >= 5:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        apply_adjustable_table_columns(self.table, sl_no_column=0)
    except Exception as e:
        print(f'[STOCK FINAL PATCH] readonly/alignment error: {e}')

def _stock_final_show_movement_detail_dialog(self, row):
    """Show actual stock ledger row details instead of placeholder."""
    from PySide6.QtWidgets import QAbstractItemView
    dialog = QDialog(self)
    dialog.setWindowTitle('Stock Movement Details')
    dialog.resize(650, 420)
    dialog.setStyleSheet(f"\n        QDialog {{\n            background-color: {COLORS['background']};\n            color: {COLORS['text_primary']};\n        }}\n        QLabel {{\n            color: {COLORS['text_primary']};\n            background: transparent;\n        }}\n        QTableWidget {{\n            background-color: {COLORS['surface']};\n            color: {COLORS['text_primary']};\n            border: 1px solid {COLORS['border']};\n            gridline-color: {COLORS['border']};\n        }}\n        QTableWidget::item {{\n            color: {COLORS['text_primary']};\n            padding: 6px;\n        }}\n        QHeaderView::section {{\n            background-color: {COLORS['primary']};\n            color: white;\n            padding: 8px;\n            font-weight: bold;\n            border: none;\n        }}\n        QPushButton {{\n            background-color: {COLORS['primary']};\n            color: white;\n            border: none;\n            border-radius: 4px;\n            padding: 8px 20px;\n            font-weight: bold;\n        }}\n    ")
    layout = QVBoxLayout(dialog)
    title = QLabel('Stock Movement Details')
    title.setStyleSheet(page_heading_style(18))
    layout.addWidget(title)
    details = []
    headers = [self.table.horizontalHeaderItem(c).text() if self.table.horizontalHeaderItem(c) else f'Column {c + 1}' for c in range(self.table.columnCount())]
    for col, header in enumerate(headers):
        item = self.table.item(row, col)
        details.append((header, item.text() if item else ''))
    table = QTableWidget()
    apply_read_only_report_table_selection(table)
    table.setColumnCount(2)
    table.setHorizontalHeaderLabels(['Field', 'Value'])
    table.setRowCount(len(details))
    for r, (field, value) in enumerate(details):
        table.setItem(r, 0, QTableWidgetItem(str(field)))
        table.setItem(r, 1, QTableWidgetItem(str(value)))
    apply_adjustable_table_columns(table)
    layout.addWidget(table)
    close_btn = QPushButton('Close')
    close_btn.clicked.connect(dialog.accept)
    layout.addWidget(close_btn, alignment=Qt.AlignRight)
    dialog.exec()

def _stock_final_show_product_detail_dialog(self, product_id):
    """Show readable product stock details and movement history."""
    from PySide6.QtWidgets import QAbstractItemView
    try:
        summary = None
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == product_id:
                summary = {'Product': self.table.item(row, 1).text() if self.table.item(row, 1) else '', 'Barcode': self.table.item(row, 2).text() if self.table.item(row, 2) else '', 'Category': self.table.item(row, 3).text() if self.table.item(row, 3) else '', 'Unit': self.table.item(row, 4).text() if self.table.item(row, 4) else '', 'Opening Qty': self.table.item(row, 5).text() if self.table.item(row, 5) else '0.00', 'Purchase Qty': self.table.item(row, 6).text() if self.table.item(row, 6) else '0.00', 'Sales Qty': self.table.item(row, 7).text() if self.table.item(row, 7) else '0.00', 'Sales Return Qty': self.table.item(row, 8).text() if self.table.item(row, 8) else '0.00', 'Purchase Return Qty': self.table.item(row, 9).text() if self.table.item(row, 9) else '0.00', 'Adjustment Qty': self.table.item(row, 10).text() if self.table.item(row, 10) else '0.00', 'Closing Qty': self.table.item(row, 11).text() if self.table.item(row, 11) else '0.00', 'Purchase Rate': self.table.item(row, 12).text() if self.table.item(row, 12) else '0.00', 'Sales Rate': self.table.item(row, 13).text() if self.table.item(row, 13) else '0.00', 'Stock Value': self.table.item(row, 14).text() if self.table.item(row, 14) else '0.00', 'Last Movement': self.table.item(row, 15).text() if self.table.item(row, 15) else ''}
                break
        if not summary:
            QMessageBox.information(self, 'No Data', 'Product data not found.')
            return
        ph = self.db._get_placeholder()
        movements = self.db.execute_query(f"\n            SELECT COALESCE(movement_date, created_at) AS movement_date,\n                   movement_type, quantity, reference_type, reference_id, notes\n            FROM stock_movements\n            WHERE company_id = {ph} AND product_id = {ph}\n              AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')\n            ORDER BY COALESCE(movement_date, created_at), id\n            LIMIT 500\n            ", (self.company_id, product_id))
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Product Stock Details - {summary.get('Product')}")
        dialog.resize(900, 650)
        dialog.setStyleSheet(f"\n            QDialog {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n            }}\n            QLabel {{\n                color: {COLORS['text_primary']};\n                background: transparent;\n            }}\n            QTableWidget {{\n                background-color: {COLORS['surface']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                gridline-color: {COLORS['border']};\n                selection-background-color: {COLORS['primary']};\n                selection-color: white;\n            }}\n            QTableWidget::item {{\n                padding: 6px;\n                color: {COLORS['text_primary']};\n            }}\n            QHeaderView::section {{\n                background-color: {COLORS['primary']};\n                color: white;\n                padding: 8px;\n                border: none;\n                font-weight: bold;\n            }}\n            QPushButton {{\n                background-color: {COLORS['primary']};\n                color: white;\n                border: none;\n                border-radius: 4px;\n                padding: 8px 20px;\n                font-weight: bold;\n            }}\n        ")
        layout = QVBoxLayout(dialog)
        title = QLabel(summary.get('Product', 'Product'))
        title.setStyleSheet(page_heading_style(18))
        layout.addWidget(title)
        summary_table = QTableWidget()
        apply_read_only_report_table_selection(summary_table)
        summary_table.setColumnCount(2)
        summary_table.setHorizontalHeaderLabels(['Field', 'Value'])
        summary_table.setRowCount(len(summary))
        for r, (field, value) in enumerate(summary.items()):
            summary_table.setItem(r, 0, QTableWidgetItem(field))
            summary_table.setItem(r, 1, QTableWidgetItem(str(value)))
        apply_adjustable_table_columns(summary_table)
        layout.addWidget(summary_table)
        movement_label = QLabel('Movement History')
        movement_label.setStyleSheet(report_summary_label_style())
        layout.addWidget(movement_label)
        mov_table = QTableWidget()
        apply_read_only_report_table_selection(mov_table)
        mov_table.setColumnCount(6)
        mov_table.setHorizontalHeaderLabels(['Date', 'Type', 'Qty', 'Reference Type', 'Reference ID', 'Notes'])
        mov_table.setRowCount(len(movements))
        for r, m in enumerate(movements):
            values = [m.get('movement_date', ''), m.get('movement_type', ''), f"{float(m.get('quantity', 0) or 0):,.2f}", m.get('reference_type', ''), str(m.get('reference_id', '') or ''), m.get('notes', '') or '']
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                mov_table.setItem(r, c, item)
        apply_adjustable_table_columns(mov_table)

        def on_movement_double_click(item):
            row = item.row()
            reference_type = mov_table.item(row, 3).text()
            reference_id = mov_table.item(row, 4).text()
            if not reference_id:
                return
            main_window = self.window()
            while main_window and (not hasattr(main_window, 'show_sales_entry')):
                main_window = main_window.parent()
            if not main_window:
                print('[DEBUG] Could not find main window')
                return
            try:
                if reference_type == 'sale':
                    main_window.show_sales_entry()
                    if hasattr(main_window, '_open_module_windows') and 'sales_entry' in main_window._open_module_windows:
                        window = main_window._open_module_windows['sales_entry']
                        from .sales_entry_page import SalesEntryPageWidget
                        widget = window.centralWidget().findChild(SalesEntryPageWidget)
                        if widget and hasattr(widget, 'load_sales_for_edit'):
                            widget.load_sales_for_edit(int(reference_id))
                elif reference_type == 'purchase':
                    main_window.show_purchase_entry()
                    if hasattr(main_window, '_open_module_windows') and 'purchase_entry' in main_window._open_module_windows:
                        window = main_window._open_module_windows['purchase_entry']
                        from .purchase_entry_page import PurchaseEntryPageWidget
                        widget = window.centralWidget().findChild(PurchaseEntryPageWidget)
                        if widget and hasattr(widget, 'load_purchase_for_edit'):
                            widget.load_purchase_for_edit(int(reference_id))
                elif reference_type == 'sales_return':
                    main_window.show_sales_return()
                    if hasattr(main_window, '_open_module_windows') and 'sales_return' in main_window._open_module_windows:
                        window = main_window._open_module_windows['sales_return']
                        from .sales_return_page import SalesReturnPageWidget
                        widget = window.centralWidget().findChild(SalesReturnPageWidget)
                        if widget and hasattr(widget, 'load_sales_return_for_edit'):
                            widget.load_sales_return_for_edit(int(reference_id))
                elif reference_type == 'purchase_return':
                    main_window.show_purchase_return()
                    if hasattr(main_window, '_open_module_windows') and 'purchase_return' in main_window._open_module_windows:
                        window = main_window._open_module_windows['purchase_return']
                        from .purchase_return_page import PurchaseReturnPageWidget
                        widget = window.centralWidget().findChild(PurchaseReturnPageWidget)
                        if widget and hasattr(widget, 'load_purchase_return_for_edit'):
                            widget.load_purchase_return_for_edit(int(reference_id))
                elif reference_type == 'opening':
                    main_window.show_products()
                    if hasattr(main_window, '_open_module_windows') and 'products' in main_window._open_module_windows:
                        window = main_window._open_module_windows['products']
                        from .product_page import ProductPageWidget
                        widget = window.centralWidget().findChild(ProductPageWidget)
                        if widget and hasattr(widget, 'edit_product'):
                            pass
                elif reference_type == 'adjustment':
                    main_window.show_stock_adjustment()
                    if hasattr(main_window, '_open_module_windows') and 'stock_adjustment' in main_window._open_module_windows:
                        window = main_window._open_module_windows['stock_adjustment']
                        from .stock_adjustment_page import StockAdjustmentPageWidget
                        widget = window.centralWidget().findChild(StockAdjustmentPageWidget)
                        if widget and hasattr(widget, 'load_adjustment_for_edit'):
                            widget.load_adjustment_for_edit(int(reference_id))
            except Exception as e:
                print(f'[DEBUG] Error opening related entry: {e}')
        mov_table.doubleClicked.connect(on_movement_double_click)
        layout.addWidget(mov_table)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dialog.exec()
    except Exception as e:
        QMessageBox.critical(self, 'Stock Detail Error', f'Could not open stock detail:\n{e}')
if not getattr(StockReportPageWidget, '_final_patch_installed', False):
    StockReportPageWidget._final_patch_installed = True
    StockReportPageWidget._apply_final_ui_fixes = _stock_apply_final_ui_fixes
    StockReportPageWidget._refresh_product_search_suggestions = _stock_refresh_product_search_suggestions
    StockReportPageWidget._on_stock_search_text_changed_final = _stock_search_changed_final
    StockReportPageWidget._make_table_readonly_and_aligned = _stock_make_table_readonly_and_aligned
    StockReportPageWidget.show_movement_detail_dialog = _stock_final_show_movement_detail_dialog
    StockReportPageWidget.show_product_detail_dialog = _stock_final_show_product_detail_dialog
    _orig_stock_setup_ui = StockReportPageWidget.setup_ui

    def _patched_stock_setup_ui(self):
        _orig_stock_setup_ui(self)
        self._apply_final_ui_fixes()
    StockReportPageWidget.setup_ui = _patched_stock_setup_ui
    _orig_populate_stock_summary = StockReportPageWidget.populate_stock_summary_table

    def _patched_populate_stock_summary(self, data):
        _orig_populate_stock_summary(self, data)
        self._make_table_readonly_and_aligned()
        self._refresh_product_search_suggestions()
    StockReportPageWidget.populate_stock_summary_table = _patched_populate_stock_summary
    _orig_load_stock_report = StockReportPageWidget.load_report

    def _patched_stock_load_report(self):
        _orig_load_stock_report(self)
        self._make_table_readonly_and_aligned()
        self._refresh_product_search_suggestions()
    StockReportPageWidget.load_report = _patched_stock_load_report