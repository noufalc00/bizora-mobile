"""
Purchase Order selection dialog for importing pending POs into Purchase Entry.
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QHeaderView, QAbstractItemView, QMessageBox
from PySide6.QtCore import Qt
from config import active_company_manager
from ui import theme
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class POSelectionDialog(UiMemoryMixin, QDialog):
    """Modal picker listing pending purchase orders for bill conversion."""
    COL_PO_ID = 0

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.selected_po_id = None
        self.setWindowTitle('Import Purchase Order')
        self.resize(720, 420)
        self.setModal(True)
        self.setStyleSheet(theme.entry_picker_dialog_style())
        self._build_ui()
        self._load_pending_orders()
        self._init_ui_memory()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        heading = QLabel('Select a Pending Purchase Order to load into this bill')
        layout.addWidget(heading)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['PO ID', 'PO Number', 'Date', 'Creditor Name', 'Grand Total'])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        load_btn = QPushButton('Load')
        load_btn.setStyleSheet(theme.entry_select_button_style())
        load_btn.clicked.connect(self._on_load_clicked)
        btn_row.addWidget(load_btn)
        layout.addLayout(btn_row)
        self.table.doubleClicked.connect(self._on_load_clicked)

    def _load_pending_orders(self):
        """Fetch purchase_orders rows where status is Pending."""
        self.table.setRowCount(0)
        company = active_company_manager.get_active_company()
        if not company or not self.db:
            return
        try:
            ph = self.db._get_placeholder()
            rows = self.db.execute_query(f'\n                SELECT id, po_number, date, creditor_name, grand_total\n                FROM purchase_orders\n                WHERE company_id = {ph} AND status = {ph}\n                ORDER BY date DESC, id DESC\n                ', (company['id'], 'Pending')) or []
        except Exception as exc:
            QMessageBox.warning(self, 'Import PO', f'Could not load pending POs: {exc}')
            return
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            if isinstance(row, dict):
                po_id = row.get('id', '')
                po_number = row.get('po_number', '')
                po_date = row.get('date', '')
                creditor = row.get('creditor_name', '')
                total = row.get('grand_total', 0)
            else:
                po_id = row[0] if len(row) > 0 else ''
                po_number = row[1] if len(row) > 1 else ''
                po_date = row[2] if len(row) > 2 else ''
                creditor = row[3] if len(row) > 3 else ''
                total = row[4] if len(row) > 4 else 0
            id_item = QTableWidgetItem(str(po_id))
            id_item.setData(Qt.ItemDataRole.UserRole, int(po_id or 0))
            self.table.setItem(row_idx, 0, id_item)
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(po_number or '')))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(po_date or '')))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(creditor or '')))
            try:
                total_text = f'{float(total or 0):.2f}'
            except (TypeError, ValueError):
                total_text = '0.00'
            self.table.setItem(row_idx, 4, QTableWidgetItem(total_text))

    def _selected_row_po_id(self):
        """Return the PO id stored on the selected table row."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, self.COL_PO_ID)
        if item is None:
            return None
        po_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            return int(po_id) if po_id else None
        except (TypeError, ValueError):
            return None

    def _on_load_clicked(self):
        po_id = self._selected_row_po_id()
        if not po_id:
            QMessageBox.information(self, 'Import PO', 'Please select a pending purchase order first.')
            return
        self.selected_po_id = po_id
        self.accept()